from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_corpus.errors import ProvenanceValidationError
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.provenance import resolve_fact_field_path, validate_provenance
from reference_corpus.models import CharacterProvenance
from reference_corpus.validator import validate_corpus


CATALOG = load_game_catalog(Path("data/reference_corpus/characters/_catalog/games.yaml"))
FIXTURE = Path(__file__).parent / "fixtures" / "valid" / "complete_valid"


def test_valid_evidence_resolves() -> None:
    reference = CharacterReferenceLoader(CATALOG).load(FIXTURE)
    assert resolve_fact_field_path(
        reference.facts, "identity.names.canonical"
    ) == "测试完整角色"
    validate_provenance(reference.provenance, reference.facts)


def test_unknown_source_and_indexed_path_are_rejected() -> None:
    reference = CharacterReferenceLoader(CATALOG).load(FIXTURE)
    bad = reference.provenance.model_copy(deep=True)
    bad.field_evidence = {"combat.abilities": ["missing-source"]}
    with pytest.raises(ProvenanceValidationError, match="unknown evidence"):
        validate_provenance(bad, reference.facts)
    with pytest.raises(ProvenanceValidationError, match="indexed"):
        resolve_fact_field_path(reference.facts, "combat.abilities.0.native_name")


def test_source_and_conflict_invariants_are_enforced() -> None:
    with pytest.raises(ValidationError):
        CharacterProvenance(
            schema_version="character-sources/0.2",
            reference_id="test-game-alpha:test-character-a",
            sources=[],
            field_evidence={},
            verification={"status": "conflicted", "conflicts": [], "notes": []},
        )


def test_supersession_and_clarification_have_field_aware_evidence_rules() -> None:
    loader = CharacterReferenceLoader(CATALOG)
    supersession = loader.load(FIXTURE.parent / "supersession")
    clarification = loader.load(FIXTURE.parent / "clarification")

    assert supersession.provenance.source_relations[0].relation_type == "supersedes"
    assert supersession.provenance.field_evidence["combat.native_taxonomy.labels.weapon_type"] == [
        "new-source"
    ]
    assert clarification.provenance.source_relations[0].relation_type == "clarifies"
    assert clarification.provenance.field_evidence["combat.native_taxonomy.labels.weapon_type"] == [
        "old-source",
        "new-source",
    ]


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda provenance: setattr(provenance.source_relations[0], "source_id", "missing"), "UNKNOWN_SOURCE_RELATION_SOURCE"),
        (lambda provenance: setattr(provenance.source_relations[0], "target_source_id", "missing"), "UNKNOWN_SOURCE_RELATION_TARGET"),
        (lambda provenance: provenance.source_relations[0].field_paths.__setitem__(0, "combat.missing"), "UNKNOWN_SOURCE_RELATION_FIELD"),
        (lambda provenance: setattr(provenance.sources[1], "published_at", provenance.sources[0].published_at.replace(year=2023)), "INVALID_SOURCE_RELATION_CHRONOLOGY"),
        (lambda provenance: provenance.field_evidence.__setitem__("combat.native_taxonomy.labels.weapon_type", ["old-source"]), "SUPERSEDED_SOURCE_IN_CURRENT_EVIDENCE"),
    ],
)
def test_source_relation_provenance_invariants_are_rejected(mutation, match: str) -> None:
    reference = CharacterReferenceLoader(CATALOG).load(FIXTURE.parent / "supersession")
    bad = reference.provenance.model_copy(deep=True)
    mutation(bad)
    with pytest.raises(ProvenanceValidationError, match=match):
        validate_provenance(bad, reference.facts)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda relation: relation.model_copy(update={"relation_type": "not-valid"}), "INVALID_SOURCE_RELATION_TYPE"),
        (lambda relation: relation.model_copy(update={"field_paths": []}), "EMPTY_SOURCE_RELATION_FIELDS"),
        (lambda relation: relation.model_copy(update={"source_id": "same", "target_source_id": "same"}), "SELF_SOURCE_RELATION"),
    ],
)
def test_source_relation_model_invariants_are_rejected(mutation, match: str) -> None:
    from reference_corpus.models import SourceRelation

    relation = {
        "relation_id": "relation",
        "source_id": "source-a",
        "relation_type": "supersedes",
        "target_source_id": "source-b",
        "field_paths": ["identity.names.canonical"],
    }
    with pytest.raises(ValidationError, match=match):
        SourceRelation.model_validate(mutation(SourceRelation.model_validate(relation)).model_dump())


def test_duplicate_source_relation_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="DUPLICATE_SOURCE_RELATION_ID"):
        CharacterProvenance.model_validate(
            {
                "schema_version": "character-sources/0.2",
                "reference_id": "test-game-alpha:test-character-a",
                "sources": [
                    {"source_id": "a", "source_type": "official", "url": "https://example.com/a", "reliability": "primary"},
                    {"source_id": "b", "source_type": "official", "url": "https://example.com/b", "reliability": "primary"},
                ],
                "source_relations": [
                    {"relation_id": "same", "source_id": "a", "relation_type": "clarifies", "target_source_id": "b", "field_paths": ["identity.names.canonical"]},
                    {"relation_id": "same", "source_id": "b", "relation_type": "clarifies", "target_source_id": "a", "field_paths": ["identity.names.canonical"]},
                ],
                "field_evidence": {},
                "verification": {"status": "verified", "conflicts": [], "notes": []},
            }
        )


def test_corpus_report_exposes_supersession_issue_code() -> None:
    reference = CharacterReferenceLoader(CATALOG).load(FIXTURE.parent / "supersession")
    reference.provenance.field_evidence["combat.native_taxonomy.labels.weapon_type"] = ["old-source"]
    report = validate_corpus([reference], CATALOG)
    assert report.valid is False
    assert any(issue.code == "SUPERSEDED_SOURCE_IN_CURRENT_EVIDENCE" for issue in report.errors)
