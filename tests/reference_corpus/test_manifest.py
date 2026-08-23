from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from along_street_resources import data_resource
from reference_corpus.loader import load_corpus_manifest, load_fixture_plan
from reference_corpus.errors import (
    CorpusManifestError,
    ReferenceValidationError,
    UnsupportedSchemaVersionError,
)
from reference_corpus.validator import validate_corpus
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog


CATALOG_PATH = data_resource("reference_corpus", "characters", "_catalog", "games.yaml")
CATALOG = load_game_catalog(CATALOG_PATH)
FIXTURE_ROOT = Path(__file__).parent / "fixtures"
FIXTURE_CATALOG = load_game_catalog(FIXTURE_ROOT / "test_games.yaml")
PRODUCTION_MANIFEST = (
    Path(__file__).parents[2]
    / "src"
    / "along_street_resources"
    / "data"
    / "reference_corpus"
    / "characters"
    / "_catalog"
    / "corpus_manifest.yaml"
)


def _write_manifest(tmp_path: Path, mutate) -> Path:
    payload = yaml.safe_load(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "corpus_manifest.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_catalog_manifest_and_fixture_plan_load() -> None:
    manifest = load_corpus_manifest(
        data_resource(
            "reference_corpus", "characters", "_catalog", "corpus_manifest.yaml"
        )
    )
    plan = load_fixture_plan(
        Path("docs/reference_corpus/archive/fixture_plan_v0.1.yaml")
    )
    assert manifest.games == [
        "genshin-impact",
        "honkai-impact-3rd",
        "neverness-to-everness",
        "wuthering-waves",
        "zenless-zone-zero",
    ]
    assert [(record.reference_id, record.path) for record in manifest.records] == [
        ("genshin-impact:furina", "genshin_impact/furina"),
        ("genshin-impact:keqing", "genshin_impact/keqing"),
        ("genshin-impact:nahida", "genshin_impact/nahida"),
        ("honkai-impact-3rd:songque", "honkai_impact_3rd/songque"),
        ("honkai-impact-3rd:vita", "honkai_impact_3rd/vita"),
        ("neverness-to-everness:fadia", "neverness_to_everness/fadia"),
        ("neverness-to-everness:shinku", "neverness_to_everness/shinku"),
        ("wuthering-waves:aalto", "wuthering_waves/aalto"),
        ("wuthering-waves:jinhsi", "wuthering_waves/jinhsi"),
        ("wuthering-waves:mortefi", "wuthering_waves/mortefi"),
        ("wuthering-waves:shorekeeper", "wuthering_waves/shorekeeper"),
        ("zenless-zone-zero:astra-yao", "zenless_zone_zero/astra_yao"),
        ("zenless-zone-zero:jane-doe", "zenless_zone_zero/jane_doe"),
        ("zenless-zone-zero:nicole", "zenless_zone_zero/nicole"),
        ("zenless-zone-zero:piper-wheel", "zenless_zone_zero/piper_wheel"),
        ("zenless-zone-zero:qingyi", "zenless_zone_zero/qingyi"),
    ]
    assert plan.target_count == 20
    assert sum(len(slots) for slots in plan.games.values()) == 20


def test_production_manifest_freezes_exact_reference_boundaries() -> None:
    manifest = load_corpus_manifest(
        data_resource(
            "reference_corpus", "characters", "_catalog", "corpus_manifest.yaml"
        )
    )

    assert manifest.schema_version == "character-reference-corpus-manifest/0.2"
    assert manifest.baseline_id == "reference-corpus-v0.5"
    assert manifest.status == "frozen"
    assert manifest.record_schema_versions.model_dump() == {
        "facts": "character-facts/0.3",
        "analysis": "character-analysis/0.1",
        "sources": "character-sources/0.2",
    }
    assert manifest.record_count == 16
    assert manifest.games == [
        "genshin-impact",
        "honkai-impact-3rd",
        "neverness-to-everness",
        "wuthering-waves",
        "zenless-zone-zero",
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["records"].__setitem__(
            1, {**payload["records"][1], "reference_id": payload["records"][0]["reference_id"]}
        ),
        lambda payload: payload["records"].__setitem__(
            1, {**payload["records"][1], "path": payload["records"][0]["path"]}
        ),
        lambda payload: payload["records"].__setitem__(
            0, {**payload["records"][0], "path": "../unsafe/character"}
        ),
        lambda payload: payload.__setitem__("record_count", 15),
        lambda payload: payload["record_schema_versions"].__setitem__(
            "facts", "character-facts/0.2"
        ),
    ],
)
def test_manifest_rejects_duplicate_unsafe_or_wrong_count(tmp_path: Path, mutate) -> None:
    with pytest.raises(CorpusManifestError):
        load_corpus_manifest(_write_manifest(tmp_path, mutate))


def test_manifest_schema_version_is_fail_closed(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        lambda payload: payload.__setitem__(
            "schema_version", "character-reference-corpus-manifest/0.1"
        ),
    )
    with pytest.raises(UnsupportedSchemaVersionError):
        load_corpus_manifest(path)


def test_catalog_rejects_duplicate_aliases() -> None:
    with pytest.raises(ReferenceValidationError):
        load_game_catalog(
            Path("tests/reference_corpus/fixtures/invalid_catalog.yaml")
        )


def test_corpus_validator_reports_warnings_and_errors_deterministically() -> None:
    loader = CharacterReferenceLoader(FIXTURE_CATALOG)
    missing_analysis = loader.load(FIXTURE_ROOT / "valid" / "missing_optional_analysis")
    conflicted = loader.load(FIXTURE_ROOT / "valid" / "conflicted_sources")
    valid_report = validate_corpus([conflicted, missing_analysis], FIXTURE_CATALOG)
    assert valid_report.valid is True
    assert [issue.code for issue in valid_report.warnings] == [
        "analysis_missing",
        "analysis_missing",
        "verification_conflicted",
    ]

    invalid = missing_analysis.model_copy(deep=True)
    invalid.facts.identity.game_id = "unknown-game"
    invalid_report = validate_corpus([invalid], FIXTURE_CATALOG)
    assert invalid_report.valid is False
    assert invalid_report.errors[0].code == "unknown_game"


def test_corpus_validator_reports_mechanic_integrity_issue_codes() -> None:
    reference = CharacterReferenceLoader(FIXTURE_CATALOG).load(
        FIXTURE_ROOT / "valid" / "mechanic_graph"
    )
    relation = reference.facts.combat.relations[0]
    relation.target.id = "missing-state"
    report = validate_corpus([reference], FIXTURE_CATALOG)
    assert report.valid is False
    assert any(issue.code == "UNKNOWN_MECHANIC_REFERENCE" for issue in report.errors)
