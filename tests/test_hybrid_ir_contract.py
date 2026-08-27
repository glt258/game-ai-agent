"""Offline H2 model-facing contract, projection, and fake pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from character_intelligence.compiler import SemanticMappingRegistry
from character_intelligence.hybrid_ir import (
    FORBIDDEN_MODEL_TOKENS,
    GLOBAL_STRUCTURAL_TRIGGER_EVENTS,
    HYBRID_EVIDENCE_VERSION,
    HybridGenerationContext,
    HybridSemanticIRRunner,
    ModelFacingContract,
    build_model_facing_contract,
    build_model_facing_request,
    project_semantic_enums,
    run_fake_pipeline,
    validate_hybrid_evidence,
    write_evidence_atomic,
)
from character_intelligence.semantic_ir import (
    SEMANTIC_IR_VERSION,
    SemanticEffect,
    SemanticFeedback,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SkillSemanticIR,
)

ROOT = Path(__file__).resolve().parents[1]


def _generic_ir() -> SkillSemanticIR:
    return SkillSemanticIR(
        SEMANTIC_IR_VERSION,
        "Support",
        "Support action",
        "active",
        "support",
        "core",
        SemanticMechanic(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("ally", "enable_ally", "Enable an ally."),
            SemanticFeedback(
                "effect_resolved",
                "enables",
                SemanticTrigger("ally", "feedback_received"),
                SemanticEffect("ally", "enable_ally", "Continue enabling the ally."),
            ),
        ),
        SemanticRolePath(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("ally", "enable_ally", "Support an ally."),
        ),
    )


def _generation_context() -> HybridGenerationContext:
    return HybridGenerationContext(
        "Design a support ability that enables an ally after the ability is invoked.",
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked", "feedback_received"),
        allowed_feedback_events=("effect_resolved",),
        allowed_feedback_relations=("enables",),
        allowed_modes=("active",),
        allowed_roles=("support",),
        allowed_centralities=("core",),
    )


def _evaluation_context() -> dict[str, object]:
    return {
        "intent": {
            "mechanic_requirements": [
                {
                    "requirement_id": "req_support",
                    "trigger": {"subject_kinds": ["self"], "events": ["ability_invoked"], "source_kinds": []},
                    "effect": {"subject_kinds": ["ally"], "operations": ["ally_enablement"], "object_kinds": []},
                    "feedback": {"required": True, "events": ["effect_resolved"], "operations": ["enables"]},
                }
            ],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "reference_review_context": None,
    }


def test_contract_is_deterministic_compact_and_example_free() -> None:
    first = build_model_facing_request(_generation_context())
    second = build_model_facing_request(_generation_context())
    assert isinstance(first.contract, ModelFacingContract)
    assert first.contract.text == second.contract.text
    assert first.contract.digest == second.contract.digest
    assert first.metrics.to_mapping() == second.metrics.to_mapping()
    assert first.metrics.total_chars <= 1700
    assert first.metrics.total_chars == len(first.text)
    assert first.metrics.total_bytes == len(first.text.encode("utf-8"))
    assert first.metrics.total_chars == (
        first.metrics.base_chars
        + first.metrics.enum_chars
        + first.metrics.case_chars
        + first.metrics.suffix_chars
        + first.metrics.separator_chars
    )
    assert "Echo" not in first.contract.text
    assert "character_skill_interface_prototype" not in first.contract.text
    assert all(token not in first.contract.text for token in FORBIDDEN_MODEL_TOKENS)
    assert "ir_version" in first.contract.text
    assert "qualifier" in first.contract.text


def test_contract_digest_binds_projection_and_wording() -> None:
    first = build_model_facing_contract(_generation_context())
    changed = build_model_facing_contract(
        HybridGenerationContext(
            _generation_context().brief,
            allowed_actors=("self",),
            allowed_trigger_events=("ability_invoked",),
            allowed_feedback_events=("effect_resolved",),
            allowed_feedback_relations=("enables",),
            allowed_modes=("active",),
            allowed_roles=("support",),
            allowed_centralities=("core",),
        )
    )
    assert first.digest != changed.digest


def test_projection_is_fair_and_excludes_validator_rejected_summon() -> None:
    projected = project_semantic_enums(_generation_context())
    assert projected.domain("actor").values == ("ally", "self")
    assert projected.domain("actor").source == "REQUEST_ALLOWED"
    assert "summon" not in projected.domain("actor").values
    assert projected.domain("intent").values == ("enable_ally",)
    assert projected.domain("intent").source == "VOCABULARY_REQUIRED"

    broad = project_semantic_enums(HybridGenerationContext("generic skill"))
    assert broad.domain("trigger_event").values == GLOBAL_STRUCTURAL_TRIGGER_EVENTS
    assert len(broad.domain("trigger_event").values) < 14


def test_projection_can_reuse_plan_role_without_accepting_evaluator_objects() -> None:
    from character_intelligence.intent import CharacterDesignIntent
    from character_intelligence.planner import CharacterDesignPlan
    from combat_semantics import CombatRoleProfile

    plan = CharacterDesignPlan(
        CharacterDesignIntent(combat_role_profile=CombatRoleProfile(primary_role="support")),
        generation_constraints=("avoid resource mechanics",),
    )
    projected = project_semantic_enums(HybridGenerationContext("support ability", plan=plan))
    assert projected.domain("role").values == ("support",)
    assert projected.domain("role").source == "PLAN_ALLOWED"


def test_fake_full_pipeline_reaches_evaluator_pass() -> None:
    ir = _generic_ir()
    provider = __import__("character_intelligence.hybrid_ir", fromlist=["FakeProvider"]).FakeProvider(
        ir.to_mapping()
    )
    result = run_fake_pipeline(provider, _generation_context(), _evaluation_context(), repo_root=ROOT)
    evidence = result.evidence.to_mapping()
    assert provider.calls == 1
    assert evidence["first_failure_layer"] is None
    assert evidence["principal_verdict"] == "PASS"
    assert evidence["evaluator_invoked"] is True
    assert evidence["evaluator_outcome"] == "PASS"
    assert result.report is not None
    assert result.report.outcome == "PASS"
    assert result.candidate is not None
    validate_hybrid_evidence(evidence)


@pytest.mark.parametrize(
    ("response", "layer", "code"),
    [
        ("{malformed", "JSON", "JSON_MALFORMED"),
        ({"ir_version": SEMANTIC_IR_VERSION}, "IR_PARSE", "IR_MISSING_REQUIRED_FIELD"),
    ],
)
def test_fake_pipeline_stops_at_first_parse_layer(response: object, layer: str, code: str) -> None:
    from character_intelligence.hybrid_ir import FakeProvider

    provider = FakeProvider(response)
    result = run_fake_pipeline(provider, _generation_context(), _evaluation_context(), repo_root=ROOT)
    evidence = result.evidence.to_mapping()
    assert evidence["first_failure_layer"] == layer
    assert evidence["failure_code"] == code
    assert evidence["parser_invoked"] is False
    assert evidence["evaluator_invoked"] is False


def test_fake_pipeline_wrong_type_and_invalid_enum_are_safe() -> None:
    from character_intelligence.hybrid_ir import FakeProvider

    wrong_type = _generic_ir().to_mapping()
    wrong_type["mode"] = {"not": "a string"}
    result = run_fake_pipeline(FakeProvider(wrong_type), _generation_context(), _evaluation_context(), repo_root=ROOT)
    assert result.evidence.first_failure_layer == "IR_PARSE"
    assert result.evidence.failure_code == "IR_WRONG_TYPE"

    invalid = _generic_ir().to_mapping()
    invalid["mode"] = "TOP-SECRET-GENERATED-VALUE"
    result = run_fake_pipeline(FakeProvider(invalid), _generation_context(), _evaluation_context(), repo_root=ROOT)
    serialized = json.dumps(result.evidence.to_mapping(), ensure_ascii=False)
    assert result.evidence.first_failure_layer == "IR_VALIDATION"
    assert result.evidence.failure_code == "IR_INVALID_SEMANTIC_VALUE"
    assert "TOP-SECRET-GENERATED-VALUE" not in serialized


def test_fake_pipeline_relationship_and_compiler_failures_are_distinct() -> None:
    from character_intelligence.hybrid_ir import FakeProvider

    invalid = _generic_ir().to_mapping()
    invalid["mechanic"]["feedback"]["response_trigger"]["actor"] = "self"
    relationship = run_fake_pipeline(FakeProvider(invalid), _generation_context(), _evaluation_context(), repo_root=ROOT)
    assert relationship.evidence.first_failure_layer == "IR_VALIDATION"
    assert relationship.evidence.diagnostics.relationship_failure_category == "INVALID_RELATIONSHIP"

    compiler = run_fake_pipeline(
        FakeProvider(_generic_ir().to_mapping()),
        _generation_context(),
        _evaluation_context(),
        repo_root=ROOT,
        compiler_registry=SemanticMappingRegistry(effect_operations={}),
    )
    assert compiler.evidence.first_failure_layer == "COMPILER"
    assert compiler.evidence.failure_code == "UNSUPPORTED_SEMANTIC_MAPPING"
    assert compiler.evidence.evaluator_invoked is False


def test_fake_pipeline_evaluator_failure_is_last_layer_and_is_invoked() -> None:
    from character_intelligence.hybrid_ir import FakeProvider

    context = _evaluation_context()
    context["combat_role_profile"] = {"primary_role": "control", "secondary_roles": []}
    result = run_fake_pipeline(FakeProvider(_generic_ir().to_mapping()), _generation_context(), context, repo_root=ROOT)
    assert result.evidence.first_failure_layer == "EVALUATOR"
    assert result.evidence.evaluator_invoked is True
    assert result.evidence.evaluator_outcome == "FAIL"
    assert result.report is not None
    assert result.report.outcome == "FAIL"


def test_evidence_is_positive_allowlist_and_atomic(tmp_path: Path) -> None:
    from character_intelligence.hybrid_ir import FakeProvider

    result = run_fake_pipeline(FakeProvider(_generic_ir().to_mapping()), _generation_context(), _evaluation_context(), repo_root=ROOT)
    payload = result.evidence.to_mapping()
    assert payload["evidence_version"] == HYBRID_EVIDENCE_VERSION
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("candidate", "Authorization", "Bearer", "sk-FAKE", "TOP-SECRET-GENERATED-VALUE"):
        if forbidden == "candidate":
            assert '"candidate"' not in serialized
        else:
            assert forbidden not in serialized
    target = write_evidence_atomic(result.evidence, tmp_path / "hybrid.json")
    assert target.exists()
    validate_hybrid_evidence(json.loads(target.read_text(encoding="utf-8")))

    with pytest.raises(ValueError, match="HYBRID_EVIDENCE_SCHEMA_INVALID"):
        write_evidence_atomic({"unexpected": "field"}, tmp_path / "invalid.json")


def test_independent_hybrid_dry_run_is_provider_free_and_n1() -> None:
    runner = HybridSemanticIRRunner(ROOT, _generation_context())
    result = runner.dry_run()
    assert result["identity"]["experiment"] == "character_skill_s2_hybrid_semantic_ir"
    assert result["identity"]["source_commit"]
    assert result["identity"]["model_facing_contract_version"] == "semantic-skill-plan-ir-contract/0.1.0"
    assert result["identity"]["compiler_version"] == "skillkit-compiler/0.1.0"
    assert result["target_sample_count"] == 1
    assert result["existing_sample_count"] == 0
    assert result["existing_sample_indexes"] == []
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["complete"] is False
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["transport_attempts"] == 0
