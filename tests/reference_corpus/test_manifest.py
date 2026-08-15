from __future__ import annotations

from pathlib import Path

import pytest
from reference_corpus.loader import load_corpus_manifest, load_fixture_plan
from reference_corpus.errors import ReferenceValidationError
from reference_corpus.validator import validate_corpus
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog


CATALOG_PATH = Path("data/reference_corpus/characters/_catalog/games.yaml")
CATALOG = load_game_catalog(CATALOG_PATH)
FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_catalog_manifest_and_fixture_plan_load() -> None:
    manifest = load_corpus_manifest(
        Path("data/reference_corpus/characters/_catalog/corpus_manifest.yaml")
    )
    plan = load_fixture_plan(
        Path("data/reference_corpus/characters/_catalog/fixture_plan.yaml")
    )
    assert manifest.games == ["test-game-alpha", "test-game-beta"]
    assert plan.target_count == 20
    assert sum(len(slots) for slots in plan.games.values()) == 20


def test_catalog_rejects_duplicate_aliases() -> None:
    with pytest.raises(ReferenceValidationError):
        load_game_catalog(
            Path("tests/reference_corpus/fixtures/invalid_catalog.yaml")
        )


def test_corpus_validator_reports_warnings_and_errors_deterministically() -> None:
    loader = CharacterReferenceLoader(CATALOG)
    missing_analysis = loader.load(FIXTURE_ROOT / "valid" / "missing_optional_analysis")
    conflicted = loader.load(FIXTURE_ROOT / "valid" / "conflicted_sources")
    valid_report = validate_corpus([conflicted, missing_analysis], CATALOG)
    assert valid_report.valid is True
    assert [issue.code for issue in valid_report.warnings] == [
        "analysis_missing",
        "analysis_missing",
        "verification_conflicted",
    ]

    invalid = missing_analysis.model_copy(deep=True)
    invalid.facts.identity.game_id = "unknown-game"
    invalid_report = validate_corpus([invalid], CATALOG)
    assert invalid_report.valid is False
    assert invalid_report.errors[0].code == "unknown_game"
