from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_corpus.errors import ProvenanceValidationError
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.provenance import resolve_fact_field_path, validate_provenance
from reference_corpus.models import CharacterProvenance


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
            schema_version="character-sources/0.1",
            reference_id="test-game-alpha:test-character-a",
            sources=[],
            field_evidence={},
            verification={"status": "conflicted", "conflicts": [], "notes": []},
        )
