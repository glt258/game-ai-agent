from __future__ import annotations

from dataclasses import replace

from test_character_skill_association import _association, _controlled_artifact

from character_intelligence.character_kit import build_character_kit
from character_intelligence.character_kit_evaluation import (
    CharacterKitEvaluationContext,
    CharacterKitEvaluationResult,
    evaluate_character_kit_role_coverage,
)
from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_association import SkillSlot
from character_intelligence.character_skill_projection import CharacterSkillDesignContext
from combat_semantics import CombatRoleProfile


def _association_for_case(
    case_id: str,
    family: str,
    mode: str,
    slot: SkillSlot,
    profile: CombatRoleProfile,
    *,
    artifact_family: str | None = None,
    artifact_mode: str | None = None,
):
    artifact = _controlled_artifact(
        case_id,
        artifact_family or family,
        artifact_mode or mode,
    )
    context = CharacterSkillDesignContext(
        character_name="角色",
        combat_role_profile=profile,
        ability_concept="结构化战斗概念。",
        design_pitch="可验证的战斗表达。",
    )
    alignment = evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=context,
            skill_family=family,
            skill_mode=mode,
            candidate=artifact.canonical_artifact,
            skill_evaluation=artifact.original_evaluation,
            artifact_digest=artifact.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
        )
    )
    from character_intelligence.character_skill_association import build_character_skill_association

    return build_character_skill_association(
        artifact,
        context,
        alignment,
        slot=slot,
        family=family,
        mode=mode,
        display_summary=case_id,
    )


def test_evaluation_context_fingerprint_is_deterministic_for_the_role_profile() -> None:
    first = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(
            primary_role="support",
            secondary_roles=("control",),
        )
    )
    second = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(
            primary_role="support",
            secondary_roles=("control",),
        )
    )

    assert first.context_contract_version == "character-kit-evaluation-context/0.1.0"
    assert first.context_fingerprint == second.context_fingerprint
    assert len(first.context_fingerprint) == 64


def test_evaluation_context_fingerprint_changes_only_when_roles_change() -> None:
    support = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(primary_role="support")
    )
    support_with_control = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(
            primary_role="support",
            secondary_roles=("control",),
        )
    )

    assert support.context_fingerprint != support_with_control.context_fingerprint


def test_primary_support_with_uncovered_secondary_is_partial() -> None:
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    context = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(
            primary_role="support",
            secondary_roles=("control",),
        )
    )

    result = evaluate_character_kit_role_coverage(kit, context)

    assert result.status == "PARTIAL"
    assert result.coverage.primary.role == "support"
    assert result.coverage.primary.supported is True
    assert result.coverage.secondary[0].role == "control"
    assert result.coverage.secondary[0].supported is False
    assert result.findings[0].code == "KIT_PRIMARY_ROLE_SUPPORTED"


def test_support_and_control_coverage_is_pass() -> None:
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",))
    support = _association_for_case(
        "character_alignment_support_v1", "support", "active", SkillSlot.PRIMARY, profile
    )
    control = _association_for_case(
        "character_alignment_control_v1", "control", "active", SkillSlot.SECONDARY, profile
    )

    result = evaluate_character_kit_role_coverage(
        build_character_kit((support, control)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "PASS"
    assert result.coverage.primary.supported is True
    assert [item.supported for item in result.coverage.secondary] == [True]
    assert {item.code for item in result.findings} == {
        "KIT_PRIMARY_ROLE_SUPPORTED",
        "KIT_SECONDARY_ROLE_SUPPORTED",
    }


def test_empty_kit_is_not_evaluated() -> None:
    profile = CombatRoleProfile(primary_role="support")
    result = evaluate_character_kit_role_coverage(
        build_character_kit(()),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "NOT_EVALUATED"
    assert result.findings[0].code == "KIT_ROLE_COVERAGE_NOT_EVALUATED"


def test_structural_failure_is_not_evaluated() -> None:
    profile = CombatRoleProfile(primary_role="support")
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    result = evaluate_character_kit_role_coverage(
        replace(kit, kit_digest="f" * 64),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "NOT_EVALUATED"
    assert result.findings[0].code == "KIT_ROLE_COVERAGE_NOT_EVALUATED"


def test_pure_main_dps_kit_fails_support_control_identity() -> None:
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",))
    dps = _association_for_case(
        "character_alignment_main_dps_v1", "main_dps", "active", SkillSlot.PRIMARY, profile
    )

    result = evaluate_character_kit_role_coverage(
        build_character_kit((dps,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "FAIL"
    assert result.blocking is True
    assert "KIT_PRIMARY_ROLE_UNSUPPORTED" in {item.code for item in result.findings}
    assert "KIT_UNSUPPORTED_ROLE_DOMINANCE" in {item.code for item in result.findings}


def test_one_artifact_can_cover_multiple_roles() -> None:
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("defense",))
    defense = _association_for_case(
        "generalization_defense_v1", "defense", "reaction", SkillSlot.PRIMARY, profile
    )

    result = evaluate_character_kit_role_coverage(
        build_character_kit((defense,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "PASS"
    assert result.coverage.primary.supported is True
    assert result.coverage.secondary[0].supported is True
    assert {item.role for item in result.coverage.primary.evidence} == {"support"}
    assert {item.role for item in result.coverage.secondary[0].evidence} == {"defense"}


def test_placement_family_and_mode_do_not_override_canonical_role_evidence() -> None:
    profile = CombatRoleProfile(primary_role="support")
    association = _association_for_case(
        "character_alignment_support_v1",
        "main_dps",
        "reaction",
        SkillSlot.UTILITY,
        profile,
        artifact_family="support",
        artifact_mode="active",
    )

    result = evaluate_character_kit_role_coverage(
        build_character_kit((association,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "PASS"
    assert result.coverage.primary.supported is True
    assert {item.operation for item in result.coverage.primary.evidence} == {"ally_enablement"}
    assert {item.family for item in result.coverage.primary.evidence} == {"main_dps"}
    assert {item.mode for item in result.coverage.primary.evidence} == {"reaction"}


def test_stale_skill_binding_is_not_evaluated_when_current_fingerprint_is_supplied() -> None:
    profile = CombatRoleProfile(primary_role="support")
    association = _association(SkillSlot.PRIMARY)
    result = evaluate_character_kit_role_coverage(
        build_character_kit((association,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
        current_skill_context_fingerprint="0" * 64,
    )

    assert result.status == "NOT_EVALUATED"
    assert result.findings[0].artifact_digests == (association.artifact_digest,)


def test_result_round_trip_and_report_digest_are_deterministic() -> None:
    profile = CombatRoleProfile(primary_role="support")
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    context = CharacterKitEvaluationContext(combat_role_profile=profile)

    first = evaluate_character_kit_role_coverage(kit, context)
    second = evaluate_character_kit_role_coverage(kit, context)
    restored = CharacterKitEvaluationResult.from_mapping(first.to_mapping())

    assert first.report_digest == second.report_digest
    assert restored == first
    assert restored.report_digest != restored.kit_digest


def test_context_round_trip_rejects_a_tampered_fingerprint() -> None:
    context = CharacterKitEvaluationContext(
        combat_role_profile=CombatRoleProfile(primary_role="support")
    )
    payload = context.to_mapping()
    payload["context_fingerprint"] = "0" * 64

    try:
        CharacterKitEvaluationContext.from_mapping(payload)
    except ValueError as error:
        assert "fingerprint mismatch" in str(error)
    else:
        raise AssertionError("tampered context fingerprint was accepted")


def test_historical_skill_failure_is_not_current_kit_evidence() -> None:
    profile = CombatRoleProfile(primary_role="support")
    association = _association(SkillSlot.PRIMARY)
    historical_artifact = replace(
        association.artifact,
        original_evaluation=replace(association.artifact.original_evaluation, outcome="FAIL"),
    )
    historical_association = replace(association, artifact=historical_artifact)

    result = evaluate_character_kit_role_coverage(
        build_character_kit((historical_association,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "NOT_EVALUATED"
    assert result.findings[0].artifact_digests == (association.artifact_digest,)


def test_artifact_version_drift_is_not_current_kit_evidence() -> None:
    profile = CombatRoleProfile(primary_role="support")
    association = _association(SkillSlot.PRIMARY)
    drifted_artifact = replace(
        association.artifact,
        versions=replace(
            association.artifact.versions,
            skill_evaluator_version="skill-kit-validator/9.9.9",
        ),
    )
    drifted_association = replace(association, artifact=drifted_artifact)

    result = evaluate_character_kit_role_coverage(
        build_character_kit((drifted_association,)),
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert result.status == "NOT_EVALUATED"
    assert result.findings[0].artifact_digests == (association.artifact_digest,)


def test_report_does_not_change_kit_digest() -> None:
    profile = CombatRoleProfile(primary_role="support")
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))

    evaluate_character_kit_role_coverage(
        kit,
        CharacterKitEvaluationContext(combat_role_profile=profile),
    )

    assert kit.kit_digest == build_character_kit(kit.associations).kit_digest
