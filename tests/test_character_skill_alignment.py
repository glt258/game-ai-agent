from __future__ import annotations

import copy
import json
from pathlib import Path

from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_design import (
    CharacterSkillDesignInput,
    run_character_skill_design,
)
from character_intelligence.character_skill_projection import CharacterSkillDesignContext
from character_intelligence.hybrid_ir.runner import FakeProvider
from combat_semantics import CombatRoleProfile

ROOT = Path(__file__).resolve().parents[1]


def _fixture(case_id: str) -> dict[str, object]:
    filename = (
        "hybrid_final_coverage_v2_goldens.json"
        if case_id
        in {
            "generalization_sub_dps_v1",
            "generalization_defense_v1",
            "generalization_basic_passive_v1",
            "character_alignment_support_v1",
            "character_alignment_main_dps_v1",
            "character_alignment_control_v1",
        }
        else "hybrid_multi_case_generalization_goldens.json"
    )
    values = json.loads((ROOT / "tests" / "fixtures" / filename).read_text(encoding="utf-8"))
    return values[case_id]


def _run_alignment(
    fixture_id: str,
    family: str,
    profile: CombatRoleProfile,
):
    context = CharacterSkillDesignContext(
        character_name="林澈",
        combat_role_profile=profile,
        ability_concept="以有限范围的行动引导帮助队友完成现场处置。",
        design_pitch="将观察与协作转化为可验证的战斗作用。",
    )
    skill_input = CharacterSkillDesignInput(
        family=family,
        mode="passive" if family == "basic_passive" else "active",
        brief="中文技能设计。",
        language="zh-CN",
        preset_id=fixture_id,
    )
    execution = run_character_skill_design(
        FakeProvider(_fixture(fixture_id)),
        context,
        skill_input,
        repo_root=ROOT,
    )
    pipeline = execution.pipeline_result
    return evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=context,
            skill_family=family,
            skill_mode=skill_input.mode,
            candidate=pipeline.candidate,
            skill_evaluation=pipeline.report,
            artifact_digest=pipeline.report.candidate_digest if pipeline.report else None,
            source_context_fingerprint=context.source_context_fingerprint,
        )
    ), pipeline


def test_valid_support_skill_aligns_with_primary_role_without_text_matching():
    alignment, pipeline = _run_alignment(
        "character_alignment_support_v1",
        "support",
        CombatRoleProfile(primary_role="support", secondary_roles=("control",)),
    )

    assert pipeline.report is not None and pipeline.report.outcome == "PASS"
    assert alignment.status == "PASS"
    assert alignment.coverage == "primary"
    assert alignment.findings[0].code == "CHARACTER_ROLE_EVIDENCE_SUPPORTED"
    assert alignment.evidence[0].operation == "ally_enablement"


def test_secondary_control_role_is_compatible_without_family_equality():
    alignment, pipeline = _run_alignment(
        "character_alignment_control_v1",
        "control",
        CombatRoleProfile(primary_role="support", secondary_roles=("control",)),
    )

    assert pipeline.report is not None and pipeline.report.outcome == "PASS"
    assert alignment.status == "PASS"
    assert alignment.coverage == "secondary"
    assert "control" in alignment.skill_roles


def test_valid_pure_main_dps_skill_fails_character_alignment():
    alignment, pipeline = _run_alignment(
        "character_alignment_main_dps_v1",
        "main_dps",
        CombatRoleProfile(primary_role="support", secondary_roles=("control",)),
    )

    assert pipeline.report is not None and pipeline.report.outcome == "PASS"
    assert alignment.status == "FAIL"
    assert alignment.blocking is True
    assert alignment.findings[0].code == "SKILL_ROLE_CONTRADICTS_CHARACTER_IDENTITY"
    assert "internally valid" in alignment.summary


def test_basic_passive_uses_structured_effect_without_active_trigger_requirement():
    alignment, pipeline = _run_alignment(
        "generalization_basic_passive_v1",
        "basic_passive",
        CombatRoleProfile(primary_role="support"),
    )

    assert pipeline.report is not None and pipeline.report.outcome == "PASS"
    assert alignment.status == "PASS"
    assert alignment.coverage == "primary"
    assert alignment.evidence[0].mode == "passive"


def test_internal_skill_failure_is_not_evaluated_for_alignment():
    invalid = copy.deepcopy(_fixture("character_alignment_support_v1"))
    invalid["role_path"]["effect"]["actor"] = "enemy"
    context = CharacterSkillDesignContext(
        character_name="林澈",
        combat_role_profile=CombatRoleProfile(primary_role="support"),
        ability_concept="帮助队友。",
        design_pitch="辅助。",
    )
    skill_input = CharacterSkillDesignInput(
        family="support",
        mode="active",
        brief="中文技能设计。",
        language="zh-CN",
    )
    execution = run_character_skill_design(
        FakeProvider(invalid), context, skill_input, repo_root=ROOT
    )
    pipeline = execution.pipeline_result

    alignment = evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=context,
            skill_family="support",
            skill_mode="active",
            candidate=pipeline.candidate,
            skill_evaluation=pipeline.report,
            artifact_digest=pipeline.report.candidate_digest if pipeline.report else None,
            source_context_fingerprint=context.source_context_fingerprint,
        )
    )

    assert pipeline.report is not None and pipeline.report.outcome == "FAIL"
    assert alignment.status == "NOT_EVALUATED"
    assert alignment.findings[0].code == "SKILL_ALIGNMENT_NOT_EVALUATED"


def test_alignment_result_is_bound_to_skill_digest_and_context_fingerprint():
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",))
    support, support_pipeline = _run_alignment("character_alignment_support_v1", "support", profile)
    control, control_pipeline = _run_alignment("character_alignment_control_v1", "control", profile)

    assert support.source_context_fingerprint == control.source_context_fingerprint
    assert support.artifact_digest != control.artifact_digest
    assert support.artifact_digest == support_pipeline.report.candidate_digest
    assert control.artifact_digest == control_pipeline.report.candidate_digest
