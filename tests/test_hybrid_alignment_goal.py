"""Offline proof for the authoritative Hybrid generation/evaluation alignment."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from character_intelligence.hybrid_ir import (
    CONTEXT_PROJECTION_VERSION,
    FakeProvider,
    HybridExperimentIdentity,
    HybridGenerationContext,
    HybridSemanticIRRunner,
    build_authoritative_support_case,
    build_model_facing_request,
)
from character_intelligence.planner import build_character_design_plan
from character_intelligence.semantic_ir import SEMANTIC_IR_VERSION
from character_skill import SkillValidationContext

ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_case_reuses_plan_and_evaluator_context() -> None:
    case = build_authoritative_support_case()
    context = case.generation_context()
    request = build_model_facing_request(context)
    trigger_domain = request.contract.projection.domain("trigger_event")
    validation = SkillValidationContext.from_mapping(case.evaluation_context())
    requirement = validation.intent.mechanic_requirements[0]

    assert context.case_id == "case_13_support_alignment_v1"
    assert context.contract_profile == "aligned_v1"
    assert context.plan is case.plan
    assert context.plan.combat_role_profile.primary_role == "support"
    assert requirement.requirement_id == case.evaluator_requirement_id
    assert requirement.trigger.events == frozenset({"ability_invoked"})
    assert requirement.effect.operations == frozenset({"ally_enablement"})
    assert trigger_domain.values == ("ability_invoked", "feedback_received")
    assert request.contract.version == "semantic-skill-plan-ir-contract/0.3.0"
    assert "response trigger actor must match the mechanic effect actor" in request.text
    assert "Semantic guidance:" in request.text
    assert "protocol_id" not in request.text
    assert "effect_id" not in request.text
    assert context.context_projection_version == CONTEXT_PROJECTION_VERSION
    assert len(context.context_projection_digest) == 64


def test_aligned_dry_run_binds_case_identity_without_provider() -> None:
    case = build_authoritative_support_case()
    result = HybridSemanticIRRunner(ROOT, case.generation_context()).dry_run()

    assert result["identity"]["case_id"] == "case_13_support_alignment_v1"
    assert result["identity"]["model_facing_contract_version"] == "semantic-skill-plan-ir-contract/0.3.0"
    assert result["identity"]["context_projection_version"] == CONTEXT_PROJECTION_VERSION
    assert result["identity"]["context_projection_digest"] == case.generation_context().context_projection_digest
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["transport_attempts"] == 0


def test_aligned_live_accepts_injected_fake_provider(tmp_path, monkeypatch) -> None:
    case = build_authoritative_support_case()
    monkeypatch.setenv("NPC_LLM_API_KEY", "offline-test-key")

    response = {
        "ir_version": SEMANTIC_IR_VERSION,
        "ability_name": "Support Echo",
        "summary": "Enable an ally after invocation.",
        "mode": "active",
        "role": "support",
        "centrality": "core",
        "mechanic": {
            "trigger": {"actor": "self", "event": "ability_invoked", "qualifier": None},
            "effect": {"actor": "ally", "intent": "enable_ally", "description": "Support an ally."},
            "feedback": {
                "event": "effect_resolved",
                "relation": "enables",
                "response_trigger": {"actor": "ally", "event": "feedback_received", "qualifier": None},
                "response_effect": {"actor": "ally", "intent": "enable_ally", "description": "Continue support."},
            },
        },
        "role_path": {
            "trigger": {"actor": "self", "event": "ability_invoked", "qualifier": None},
            "effect": {"actor": "ally", "intent": "enable_ally", "description": "Support an ally."},
        },
    }
    result = HybridSemanticIRRunner(ROOT, case.generation_context()).run_live(
        case.evaluation_context(),
        provider_factory=lambda: FakeProvider(response),
        output_path=tmp_path / "aligned.json",
        enforce_clean_tree=False,
    )
    assert result.status == "HYBRID_SEMANTIC_IR_END_TO_END_PASS"
    assert result.provider_factory_constructed is True
    assert result.provider_called is True
    assert result.transport_attempts == 1


def test_aligned_fake_pipeline_is_formally_semantic_and_not_case_prefilled() -> None:
    case = build_authoritative_support_case()
    request = build_model_facing_request(case.generation_context())
    assert "Support Echo" not in request.text
    assert "Support an ally." not in request.text


def test_context_digest_is_bound_to_identity_and_mapping_round_trips() -> None:
    case = build_authoritative_support_case()
    context = case.generation_context()
    identity = HybridSemanticIRRunner(ROOT, context).dry_run()["identity"]
    assert HybridExperimentIdentity.from_mapping(identity).to_mapping() == identity
    changed = replace(context, allowed_modes=("passive",))
    changed_identity = HybridSemanticIRRunner(ROOT, changed).dry_run()["identity"]
    assert identity["context_projection_digest"] != changed_identity["context_projection_digest"]
    assert (
        HybridSemanticIRRunner(ROOT, context).dry_run()["run_id"]
        != HybridSemanticIRRunner(ROOT, changed).dry_run()["run_id"]
    )


def test_context_projection_changes_for_role_and_constraints_but_not_order() -> None:
    base = HybridGenerationContext(
        "Design a control ability.",
        plan=build_character_design_plan("Design a control ability."),
        contract_profile="aligned_v1",
        allowed_actors=("self", "enemy"),
        allowed_trigger_events=("action_completed", "ability_invoked"),
        allowed_modes=("reaction", "active"),
        allowed_roles=("control",),
    )
    reordered = HybridGenerationContext(
        "Design a control ability.",
        plan=build_character_design_plan("Design a control ability."),
        contract_profile="aligned_v1",
        allowed_actors=("enemy", "self"),
        allowed_trigger_events=("ability_invoked", "action_completed"),
        allowed_modes=("active", "reaction"),
        allowed_roles=("control",),
    )
    role_variant = HybridGenerationContext(
        "Design a damage ability.",
        plan=build_character_design_plan("Design a damage ability."),
        contract_profile="aligned_v1",
        allowed_actors=("self", "enemy"),
        allowed_trigger_events=("ability_invoked",),
        allowed_roles=("main_dps",),
    )
    constrained = HybridGenerationContext(
        base.brief,
        plan=replace(base.plan, generation_constraints=("constraint=bounded",)),
        contract_profile="aligned_v1",
        allowed_actors=base.allowed_actors,
        allowed_trigger_events=base.allowed_trigger_events,
        allowed_roles=base.allowed_roles,
    )
    passive = HybridGenerationContext(
        "Design a passive support ability.",
        plan=build_character_design_plan("Design a passive support ability."),
        contract_profile="aligned_v1",
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked",),
        allowed_modes=("passive",),
        allowed_roles=("support",),
    )
    assert base.context_projection_digest == reordered.context_projection_digest
    assert base.context_projection_digest != role_variant.context_projection_digest
    assert base.context_projection_digest != constrained.context_projection_digest
    assert passive.context_projection_digest != base.context_projection_digest
