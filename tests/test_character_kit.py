from __future__ import annotations

from dataclasses import replace

import pytest
from test_character_skill_association import _association

from character_intelligence.character_kit import (
    CHARACTER_KIT_CONTRACT_VERSION,
    CharacterKit,
    CharacterKitContractError,
    CharacterKitStructuralValidator,
    build_character_kit,
)
from character_intelligence.character_skill_association import (
    CharacterSkillCollection,
    SkillSlot,
)


def test_empty_and_single_skill_kits_are_structurally_valid() -> None:
    empty = build_character_kit(CharacterSkillCollection())
    single = build_character_kit((_association(SkillSlot.PRIMARY),))

    assert empty.contract_version == CHARACTER_KIT_CONTRACT_VERSION
    assert empty.associations == ()
    assert CharacterKitStructuralValidator().validate(empty).status == "PASS"
    assert CharacterKitStructuralValidator().validate(single).status == "PASS"


def test_builder_canonicalizes_input_order_and_allows_multiple_passives() -> None:
    primary = _association(SkillSlot.PRIMARY)
    passive_one = _association(SkillSlot.PASSIVE, case_id="generalization_basic_passive_v1")
    passive_two = _association(SkillSlot.PASSIVE, case_id="generalization_defense_v1")

    first = build_character_kit((passive_one, primary, passive_two))
    second = build_character_kit((passive_two, passive_one, primary))

    assert first.associations == second.associations
    assert first.kit_digest == second.kit_digest
    assert [item.slot for item in first.associations] == [
        SkillSlot.PRIMARY,
        SkillSlot.PASSIVE,
        SkillSlot.PASSIVE,
    ]


def test_structural_validator_rejects_duplicate_artifact_and_primary() -> None:
    primary = _association(SkillSlot.PRIMARY)
    duplicate_artifact = CharacterKit(
        CHARACTER_KIT_CONTRACT_VERSION,
        (primary, _association(SkillSlot.SECONDARY, name="顾澄")),
        "0" * 64,
    )
    duplicate_primary = CharacterKit(
        CHARACTER_KIT_CONTRACT_VERSION,
        (primary, _association(SkillSlot.PRIMARY, case_id="character_alignment_control_v1")),
        "0" * 64,
    )

    artifact_result = CharacterKitStructuralValidator().validate(duplicate_artifact)
    primary_result = CharacterKitStructuralValidator().validate(duplicate_primary)

    assert artifact_result.status == "FAIL"
    assert "KIT_DUPLICATE_ARTIFACT" in {item.code for item in artifact_result.findings}
    assert primary_result.status == "FAIL"
    assert "KIT_PLACEMENT_CARDINALITY_EXCEEDED" in {item.code for item in primary_result.findings}


def test_digest_tampering_fails_closed_and_round_trip_is_stable() -> None:
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    restored = CharacterKit.from_mapping(kit.to_mapping())
    tampered = replace(kit, kit_digest="f" * 64)

    assert restored == kit
    assert CharacterKitStructuralValidator().validate(restored).status == "PASS"
    result = CharacterKitStructuralValidator().validate(tampered)
    assert result.status == "FAIL"
    assert "KIT_DIGEST_MISMATCH" in {item.code for item in result.findings}


def test_digest_excludes_character_binding_state_and_historical_evaluation() -> None:
    first = _association(SkillSlot.PRIMARY, name="林澈")
    other_character = _association(SkillSlot.PRIMARY, name="顾澄")
    changed_alignment = replace(
        first.binding.alignment,
        status="FAIL",
        summary="changed historical alignment",
    )
    changed_binding = replace(first.binding, alignment=changed_alignment)
    changed_evaluation = replace(first.artifact.original_evaluation, outcome="FAIL")
    changed_artifact = replace(first.artifact, original_evaluation=changed_evaluation)
    changed_association = replace(first, binding=changed_binding, artifact=changed_artifact)

    assert (
        build_character_kit((first,)).kit_digest
        == build_character_kit((other_character,)).kit_digest
    )
    assert (
        build_character_kit((first,)).kit_digest
        == build_character_kit((changed_association,)).kit_digest
    )


def test_unsupported_contract_version_is_rejected() -> None:
    with pytest.raises(CharacterKitContractError, match="KIT_UNSUPPORTED_CONTRACT_VERSION"):
        CharacterKit.from_mapping(
            {
                "contract_version": "character-kit/9.9.9",
                "associations": [],
                "kit_digest": "0" * 64,
            }
        )


def test_structural_validator_reports_unknown_placement_and_binding_tamper() -> None:
    invalid_placement = _association(SkillSlot.UTILITY)
    object.__setattr__(invalid_placement, "slot", "ultimate")
    placement_kit = CharacterKit(
        CHARACTER_KIT_CONTRACT_VERSION,
        (invalid_placement,),
        "0" * 64,
    )
    placement_result = CharacterKitStructuralValidator().validate(placement_kit)

    invalid_binding = _association(SkillSlot.PRIMARY, case_id="character_alignment_control_v1")
    object.__setattr__(invalid_binding.binding, "artifact_digest", "0" * 64)
    binding_kit = CharacterKit(
        CHARACTER_KIT_CONTRACT_VERSION,
        (invalid_binding,),
        "0" * 64,
    )
    binding_result = CharacterKitStructuralValidator().validate(binding_kit)

    assert placement_result.status == "FAIL"
    assert "KIT_UNKNOWN_PLACEMENT" in {item.code for item in placement_result.findings}
    assert binding_result.status == "FAIL"
    assert "KIT_ASSOCIATION_BINDING_INVALID" in {item.code for item in binding_result.findings}
