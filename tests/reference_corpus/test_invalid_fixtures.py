from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from reference_corpus.errors import ReferenceValidationError
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.models import (
    AlignmentAssessment,
    CharacterAnalysis,
    CharacterProvenance,
)


FIXTURE = Path(__file__).parent / "fixtures" / "valid" / "complete_valid"
CATALOG = load_game_catalog(Path("data/reference_corpus/characters/_catalog/games.yaml"))


def _payloads() -> tuple[dict, dict, dict]:
    def read(name: str) -> dict:
        return yaml.safe_load((FIXTURE / name).read_text(encoding="utf-8"))

    return read("facts.yaml"), read("analysis.yaml"), read("sources.yaml")


def _write_case(tmp_path: Path, facts: dict, analysis: dict, sources: dict) -> Path:
    target = tmp_path / "case"
    target.mkdir()
    (target / "facts.yaml").write_text(yaml.safe_dump(facts, allow_unicode=True), encoding="utf-8")
    (target / "analysis.yaml").write_text(
        yaml.safe_dump(analysis, allow_unicode=True), encoding="utf-8"
    )
    (target / "sources.yaml").write_text(
        yaml.safe_dump(sources, allow_unicode=True), encoding="utf-8"
    )
    return target


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda f, a, s: f["combat"]["abilities"].append(f["combat"]["abilities"][0]), "ability_id"),
        (lambda f, a, s: s["sources"].append(dict(s["sources"][0])), "source_id"),
        (lambda f, a, s: s["sources"][0].update(url="ftp://invalid.example.com"), "url"),
        (lambda f, a, s: s["field_evidence"].update({"combat.abilities": ["missing"]}), "unknown evidence"),
        (lambda f, a, s: f["identity"]["names"].update(canonical=""), "canonical"),
        (lambda f, a, s: f.update(extra_unknown_field=True), "extra_forbidden"),
    ],
)
def test_invalid_fixtures_are_rejected(tmp_path: Path, mutation, match: str) -> None:
    facts, analysis, sources = _payloads()
    mutation(facts, analysis, sources)
    with pytest.raises(ReferenceValidationError, match=match):
        CharacterReferenceLoader(CATALOG).load(_write_case(tmp_path, facts, analysis, sources))


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_invalid_confidence_is_rejected(value: float) -> None:
    facts, analysis, sources = _payloads()
    analysis["confidence"]["overall"] = value
    with pytest.raises(ValidationError):
        CharacterAnalysis.model_validate(analysis)


def test_invalid_alignment_score_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AlignmentAssessment(score=-0.1, reasoning="invalid")


@pytest.mark.parametrize(
    "status, conflicts",
    [("verified", [{"field_path": "x", "source_ids": ["a"], "description": "x"}]), ("conflicted", [])],
)
def test_verification_conflict_invariants_are_rejected(status: str, conflicts: list[dict]) -> None:
    with pytest.raises(ValidationError):
        CharacterProvenance(
            schema_version="character-sources/0.2",
            reference_id="test-game-alpha:test-character-complete",
            sources=[
                {
                    "source_id": "a",
                    "source_type": "official",
                    "url": "https://example.com/a",
                    "reliability": "primary",
                }
            ],
            field_evidence={},
            verification={"status": status, "conflicts": conflicts, "notes": []},
        )


def test_duplicate_reference_ids_are_reported() -> None:
    from reference_corpus.loader import CharacterReferenceLoader
    from reference_corpus.validator import validate_corpus

    reference = CharacterReferenceLoader(CATALOG).load(FIXTURE)
    report = validate_corpus([reference, reference], CATALOG)
    assert report.valid is False
    assert any(issue.code == "duplicate_reference_id" for issue in report.errors)
