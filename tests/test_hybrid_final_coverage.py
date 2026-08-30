"""Offline v2 coverage proof for Sub-DPS, Defense, and Basic Passive."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from character_intelligence.compiler import COMPILER_VERSION_V2
from character_intelligence.hybrid_ir import (
    CONTEXT_PROJECTION_VERSION_V2,
    HYBRID_MULTI_CASE_EXPERIMENT,
    MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2,
    MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_HISTORICAL,
    MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_LEGACY,
    SEMANTIC_REPAIR_CONTRACT_VERSION_V2,
    FakeProvider,
    HybridExperimentIdentity,
    HybridSemanticIRRunner,
    SemanticRepairSession,
    build_authoritative_final_coverage_cases,
    build_model_facing_request,
    run_fake_pipeline,
)
from character_intelligence.semantic_ir import (
    SEMANTIC_IR_V2_VERSION,
    SEMANTIC_IR_VERSION,
    SemanticEffect,
    SemanticFeedback,
    SemanticIRShapeError,
    SemanticIRValidationError,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SkillSemanticIR,
    parse_semantic_ir,
    validate_skill_semantic_ir,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json"


def _goldens() -> dict[str, dict[str, object]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _cases() -> dict[str, object]:
    return {case.case_id: case for case in build_authoritative_final_coverage_cases()}


def test_final_coverage_cases_are_distinct_and_use_v2_contracts() -> None:
    cases = _cases()
    assert set(cases) == {
        "generalization_sub_dps_v1",
        "generalization_defense_v1",
        "generalization_basic_passive_v1",
    }
    assert {case.plan.combat_role_profile.primary_role for case in cases.values()} == {
        "sub_dps",
        "defense",
        "support",
    }
    assert {case.mechanic_kind for case in cases.values()} == {"triggered", "passive"}
    requests = [build_model_facing_request(case.generation_context()) for case in cases.values()]
    assert {request.contract.version for request in requests} == {
        MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2
    }
    assert {request.contract.ir_version for request in requests} == {SEMANTIC_IR_V2_VERSION}
    assert all("mechanic.kind" in request.contract.enum_text for request in requests)
    assert all("mechanic.persistence" in request.contract.enum_text for request in requests)


def test_v2_contract_explains_triggered_feedback_wire_shape_and_passive_exclusion() -> None:
    request = build_model_facing_request(
        _cases()["generalization_sub_dps_v1"].generation_context()
    )
    text = request.contract.text
    assert request.contract.version == "semantic-skill-plan-ir-contract/0.7.2"
    assert "all four keys are required" in text
    assert '"feedback": null' in text
    assert "never omit that field" in text
    assert "event, relation, response_trigger, and response_effect" in text
    assert "response_trigger has actor, event, qualifier" in text
    assert "response_effect has actor, intent, description" in text
    assert "passive mechanics have no trigger or feedback" in text
    assert "response_effect_family" not in text


def test_historical_v2_contract_version_remains_identity_compatible() -> None:
    assert MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_HISTORICAL == (
        "semantic-skill-plan-ir-contract/0.7.0"
    )
    assert MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_LEGACY == (
        "semantic-skill-plan-ir-contract/0.7.1"
    )
    assert MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2 not in {
        MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_HISTORICAL,
        MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_LEGACY,
    }
    for version in (
        MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_HISTORICAL,
        MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION_V2_LEGACY,
    ):
        identity = HybridExperimentIdentity(
            experiment=HYBRID_MULTI_CASE_EXPERIMENT,
            source_commit="3dc0c4204a57bf6284683cf3a3e5a4ba8c9d7f12",
            ir_schema_version=SEMANTIC_IR_V2_VERSION,
            model_facing_contract_version=version,
            model_facing_contract_digest="0" * 64,
            compiler_version=COMPILER_VERSION_V2,
            case_id="historical-v2",
            context_projection_version=CONTEXT_PROJECTION_VERSION_V2,
            context_projection_digest="1" * 64,
        )
        assert HybridExperimentIdentity.from_mapping(identity.to_mapping()) == identity


def test_v2_goldens_pass_the_complete_offline_pipeline() -> None:
    cases = _cases()
    goldens = _goldens()
    assert set(goldens) == set(cases)
    for case_id, case in cases.items():
        result = run_fake_pipeline(
            FakeProvider(goldens[case_id]),
            case.generation_context(),
            case.evaluation_context(),
            repo_root=ROOT,
        )
        assert result.evidence.first_failure_layer is None
        assert result.evidence.evaluator_outcome == "PASS"
        assert result.evidence.fake_provider_called is True
        assert result.evidence.identity.ir_schema_version == SEMANTIC_IR_V2_VERSION
        assert result.evidence.identity.compiler_version == COMPILER_VERSION_V2
        assert result.candidate is not None


def test_v2_runner_dry_run_has_future_identity_and_never_calls_provider() -> None:
    for case in _cases().values():
        runner = HybridSemanticIRRunner(
            ROOT,
            case.generation_context(),
            experiment=HYBRID_MULTI_CASE_EXPERIMENT,
            cohort_purpose="final-coverage-v2",
        )
        dry = runner.dry_run()
        assert dry["provider_factory_constructed"] is False
        assert dry["provider_called"] is False
        assert dry["identity"]["ir_schema_version"] == SEMANTIC_IR_V2_VERSION
        assert dry["identity"]["compiler_version"] == COMPILER_VERSION_V2
        assert dry["identity"]["context_projection_version"] == CONTEXT_PROJECTION_VERSION_V2
        assert dry["run_id"].startswith("cs-s2-hybrid-semantic-ir-v1-sample-01-")


def test_v1_rejects_v2_only_intent() -> None:
    source = SkillSemanticIR(
        SEMANTIC_IR_VERSION,
        "Legacy",
        "Legacy semantic plan",
        "active",
        "main_dps",
        "core",
        SemanticMechanic(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("enemy", "deal_follow_up_damage", "Follow-up damage."),
            SemanticFeedback(
                "effect_resolved",
                "enables",
                SemanticTrigger("enemy", "feedback_received"),
                SemanticEffect("enemy", "deal_damage", "Continue damage."),
            ),
        ),
        SemanticRolePath(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("enemy", "deal_follow_up_damage", "Role evidence."),
        ),
    )
    with pytest.raises(SemanticIRValidationError, match="UNSUPPORTED_SEMANTIC_MAPPING"):
        validate_skill_semantic_ir(source)


def test_v2_semantic_repair_keeps_version_and_calls_only_the_injected_adapter() -> None:
    case = _cases()["generalization_sub_dps_v1"]
    gold = _goldens()[case.case_id]
    broken = json.loads(json.dumps(gold))
    broken["mode"] = "reaction"
    initial = run_fake_pipeline(
        FakeProvider(broken),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    )
    session = SemanticRepairSession(
        initial,
        case.generation_context(),
        case.evaluation_context(),
        repo_root=str(ROOT),
    )
    repaired = session.run(lambda _request: gold)
    assert repaired.outcome.value == "REPAIR_SUCCESS"
    assert repaired.evidence.identity.repair_contract_version == SEMANTIC_REPAIR_CONTRACT_VERSION_V2
    assert repaired.evidence.repair_provider_calls == 1
    assert repaired.revalidation is not None
    assert repaired.revalidation.evidence.identity.ir_schema_version == SEMANTIC_IR_V2_VERSION


@pytest.mark.parametrize(
    ("case_id", "mutate"),
    [
        (
            "generalization_sub_dps_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(intent="deal_damage"),
                payload["role_path"]["effect"].update(intent="deal_damage"),
            ),
        ),
        (
            "generalization_defense_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(intent="mitigate_ally"),
                payload["role_path"]["effect"].update(intent="mitigate_ally"),
            ),
        ),
        (
            "generalization_basic_passive_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(actor="enemy"),
                payload["role_path"]["effect"].update(actor="enemy"),
            ),
        ),
    ],
)
def test_new_family_wrong_responsibility_fails_generic_evaluator(case_id, mutate) -> None:
    case = _cases()[case_id]
    payload = json.loads(json.dumps(_goldens()[case_id]))
    mutate(payload)
    result = run_fake_pipeline(
        FakeProvider(payload),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    )
    assert result.evidence.first_failure_layer == "EVALUATOR"
    assert result.evidence.evaluator_outcome == "FAIL"


@pytest.mark.parametrize(
    ("case_id", "mutate"),
    [
        (
            "generalization_sub_dps_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(intent="deal_damage"),
                payload["role_path"]["effect"].update(intent="deal_damage"),
            ),
        ),
        (
            "generalization_defense_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(intent="enable_ally"),
                payload["role_path"]["effect"].update(intent="enable_ally"),
            ),
        ),
        (
            "generalization_basic_passive_v1",
            lambda payload: (
                payload["mechanic"]["effect"].update(actor="enemy"),
                payload["role_path"]["effect"].update(actor="enemy"),
            ),
        ),
    ],
)
def test_all_new_families_have_one_bounded_repair_to_pass(case_id, mutate) -> None:
    case = _cases()[case_id]
    broken = json.loads(json.dumps(_goldens()[case_id]))
    mutate(broken)
    initial = run_fake_pipeline(
        FakeProvider(broken),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    )
    assert initial.evidence.evaluator_outcome == "FAIL"
    repaired = SemanticRepairSession(
        initial,
        case.generation_context(),
        case.evaluation_context(),
        repo_root=str(ROOT),
    ).run(lambda _request: _goldens()[case_id])
    assert repaired.outcome.value == "REPAIR_SUCCESS"
    assert repaired.repair_attempts == 1
    assert repaired.evidence.repair_provider_calls == 1
    assert repaired.revalidation is not None
    assert repaired.revalidation.evidence.evaluator_outcome == "PASS"


def test_v2_variant_absence_invariants_fail_closed() -> None:
    passive = json.loads(json.dumps(_goldens()["generalization_basic_passive_v1"]))
    passive["mechanic"]["trigger"] = {
        "actor": "self",
        "event": "ability_invoked",
        "qualifier": None,
    }
    with pytest.raises(SemanticIRShapeError, match="UNKNOWN_FIELD"):
        parse_semantic_ir(passive)

    passive = json.loads(json.dumps(_goldens()["generalization_basic_passive_v1"]))
    passive["mechanic"]["feedback"] = None
    with pytest.raises(SemanticIRShapeError, match="UNKNOWN_FIELD"):
        parse_semantic_ir(passive)

    triggered = json.loads(json.dumps(_goldens()["generalization_sub_dps_v1"]))
    triggered["mechanic"].pop("trigger")
    with pytest.raises(SemanticIRShapeError, match="MISSING_FIELD"):
        parse_semantic_ir(triggered)

    unknown = json.loads(json.dumps(_goldens()["generalization_sub_dps_v1"]))
    unknown["mechanic"]["kind"] = "custom"
    with pytest.raises(SemanticIRShapeError, match="unsupported mechanic variant"):
        parse_semantic_ir(unknown)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("mechanic", "kind"),
        ("mechanic", "trigger"),
        ("mechanic", "effect"),
        ("mechanic", "feedback"),
        ("role_path", "kind"),
        ("role_path", "trigger"),
        ("role_path", "effect"),
    ],
)
def test_v2_missing_required_fields_are_typed_and_safely_classified(
    section: str, field: str
) -> None:
    case = _cases()["generalization_sub_dps_v1"]
    payload = json.loads(json.dumps(_goldens()[case.case_id]))
    del payload[section][field]

    with pytest.raises(SemanticIRShapeError) as error:
        parse_semantic_ir(payload)
    assert error.value.code == "MISSING_FIELD"
    assert error.value.path == f"/semantic_skill_plan/{section}/{field}"

    result = run_fake_pipeline(
        FakeProvider(payload),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    )
    assert result.evidence.first_failure_layer == "IR_PARSE"
    assert result.evidence.failure_code == "IR_MISSING_REQUIRED_FIELD"
    assert result.evidence.evaluator_invoked is False


def test_v2_feedback_null_is_valid_and_passive_wire_shape_remains_valid() -> None:
    triggered = json.loads(json.dumps(_goldens()["generalization_sub_dps_v1"]))
    triggered["mechanic"]["feedback"] = None
    parsed = parse_semantic_ir(triggered)
    assert parsed.mechanic.feedback is None

    passive = json.loads(json.dumps(_goldens()["generalization_basic_passive_v1"]))
    parsed_passive = parse_semantic_ir(passive)
    assert parsed_passive.mechanic.kind == "passive"
    assert parsed_passive.role_path.kind == "passive"
