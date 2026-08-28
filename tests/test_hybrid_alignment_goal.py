"""Offline proof for the authoritative Hybrid generation/evaluation alignment."""

from __future__ import annotations

from pathlib import Path

from character_intelligence.hybrid_ir import (
    HybridSemanticIRRunner,
    build_authoritative_support_case,
    build_model_facing_request,
)
from character_skill import SkillValidationContext

ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_case_reuses_plan_and_evaluator_context() -> None:
    case = build_authoritative_support_case()
    context = case.generation_context()
    request = build_model_facing_request(context)
    validation = SkillValidationContext.from_mapping(case.evaluation_context())
    requirement = validation.intent.mechanic_requirements[0]

    assert context.case_id == "case_13_support_alignment_v1"
    assert context.contract_profile == "aligned_v1"
    assert context.plan is case.plan
    assert context.plan.combat_role_profile.primary_role == "support"
    assert requirement.requirement_id == case.evaluator_requirement_id
    assert requirement.trigger.events == frozenset({"ability_invoked"})
    assert requirement.effect.operations == frozenset({"ally_enablement"})
    assert request.contract.version == "semantic-skill-plan-ir-contract/0.2.0"
    assert "Semantic guidance:" in request.text
    assert "protocol_id" not in request.text
    assert "effect_id" not in request.text


def test_aligned_dry_run_binds_case_identity_without_provider() -> None:
    case = build_authoritative_support_case()
    result = HybridSemanticIRRunner(ROOT, case.generation_context()).dry_run()

    assert result["identity"]["case_id"] == "case_13_support_alignment_v1"
    assert result["identity"]["model_facing_contract_version"] == "semantic-skill-plan-ir-contract/0.2.0"
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["transport_attempts"] == 0


def test_aligned_live_is_review_blocked_before_provider_factory() -> None:
    case = build_authoritative_support_case()

    def forbidden_factory():
        raise AssertionError("aligned goal configuration must not call a provider")

    result = HybridSemanticIRRunner(ROOT, case.generation_context()).run_live(
        case.evaluation_context(), provider_factory=forbidden_factory
    )
    assert result.status == "BLOCKED_ALIGNMENT_CONFIGURATION_REQUIRES_REVIEW"
    assert result.provider_factory_constructed is False
    assert result.provider_called is False
    assert result.transport_attempts == 0
