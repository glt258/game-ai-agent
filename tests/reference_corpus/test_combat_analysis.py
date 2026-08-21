from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_corpus.combat_vocabulary import CombatVocabulary
from reference_corpus.combat_taxonomy import (
    LEGACY_COMBAT_CROSSWALK,
    validate_legacy_crosswalk,
)
from reference_corpus.errors import ProvenanceValidationError
from reference_corpus.loader import CharacterReferenceLoader, load_combat_vocabulary
from reference_corpus.models import CombatDesignAnalysis, PrimaryLoop
from reference_corpus.provenance import validate_combat_analysis


JANE_DIR = Path("data/reference_corpus/characters/zenless_zone_zero/jane_doe")
VOCABULARY_PATH = Path("data/reference_corpus/combat_vocabulary.yaml")


def test_jane_doe_structured_combat_profile_loads_and_preserves_legacy_analysis() -> None:
    reference = CharacterReferenceLoader().load(JANE_DIR)
    assert reference.analysis is not None
    combat = reference.analysis.combat_design

    assert combat.combat_roles == ["main_dps"]
    assert combat.damage_patterns == ["sustained"]
    assert combat.mechanics == ["mark_target", "mobility", "resource_management"]
    assert combat.team_position == ["selfish_carry"]
    assert combat.normalized_roles[0].value == "on_field_dps"
    assert combat.primary_loop.steps[-1] == "rebuild_resource"
    assert combat.role_rationale["main_dps"]
    assert combat.confidence == 0.8


def test_unknown_structured_combat_token_is_rejected() -> None:
    vocabulary = load_combat_vocabulary(VOCABULARY_PATH)
    combat = CombatDesignAnalysis(
        combat_roles=["not_a_role"],
        role_rationale={"not_a_role": "unsupported"},
        primary_loop=PrimaryLoop(steps=[]),
    )
    with pytest.raises(ValueError, match="unknown combat_role combat vocabulary token"):
        combat.validate_vocabulary(vocabulary)


def test_combat_evidence_must_reference_existing_fact_nodes() -> None:
    reference = CharacterReferenceLoader().load(JANE_DIR)
    assert reference.analysis is not None
    analysis = reference.analysis.model_copy(deep=True)
    analysis.combat_design.evidence[0].ability_ids.append("missing_ability")

    with pytest.raises(ProvenanceValidationError, match="UNKNOWN_COMBAT_EVIDENCE_ABILITY"):
        validate_combat_analysis(
            analysis,
            reference.facts,
            load_combat_vocabulary(VOCABULARY_PATH),
        )


def test_roles_require_matching_rationales() -> None:
    with pytest.raises(ValidationError, match="role_rationale keys"):
        CombatDesignAnalysis(
            combat_roles=["main_dps"],
            primary_loop=PrimaryLoop(steps=[]),
        )


def test_vocabulary_shape_remains_file_backed() -> None:
    vocabulary = load_combat_vocabulary(VOCABULARY_PATH)
    assert isinstance(vocabulary, CombatVocabulary)


def test_legacy_crosswalk_keeps_role_and_behavior_domains_separate() -> None:
    crosswalk = {item.legacy_role: item for item in LEGACY_COMBAT_CROSSWALK}

    assert crosswalk["on_field_dps"].combat_roles == ("main_dps",)
    assert crosswalk["off_field_dps"].combat_roles == ("sub_dps",)
    assert crosswalk["burst_dps"].combat_roles == ()
    assert crosswalk["burst_dps"].damage_patterns == ("burst",)
    assert crosswalk["sustain"].combat_roles == ()
    assert crosswalk["sustain"].status == "ambiguous"

    validate_legacy_crosswalk(load_combat_vocabulary(VOCABULARY_PATH))


def test_legacy_and_structured_combat_roles_cannot_silently_contradict() -> None:
    reference = CharacterReferenceLoader().load(JANE_DIR)
    assert reference.analysis is not None
    analysis = reference.analysis.model_copy(deep=True)
    analysis.combat_design.combat_roles = ["support"]
    analysis.combat_design.role_rationale = {"support": "test"}
    for evidence in analysis.combat_design.evidence:
        if evidence.dimension == "combat_roles":
            evidence.token = "support"

    with pytest.raises(ProvenanceValidationError, match="contradicts"):
        validate_combat_analysis(
            analysis,
            reference.facts,
            load_combat_vocabulary(VOCABULARY_PATH),
        )
