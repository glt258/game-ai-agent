"""Offline bounded Semantic IR repair tests for the four-case Hybrid path."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from character_intelligence.hybrid_ir import (
    HYBRID_MULTI_CASE_EXPERIMENT,
    MAX_REPAIR_ATTEMPTS,
    FakeProvider,
    RepairOutcome,
    SemanticRepairRequest,
    SemanticRepairSession,
    build_authoritative_generalization_cases,
    run_fake_pipeline,
    validate_semantic_repair_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "hybrid_multi_case_generalization_goldens.json"


def _goldens() -> dict[str, dict[str, object]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _cases() -> dict[str, object]:
    return {case.case_id: case for case in build_authoritative_generalization_cases()}


def _initial(case_id: str, payload: dict[str, object]):
    case = _cases()[case_id]
    return run_fake_pipeline(
        FakeProvider(payload),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
        experiment=HYBRID_MULTI_CASE_EXPERIMENT,
        cohort_purpose="multi-case-generalization-repair-validation-01",
    )


def _session(case_id: str, payload: dict[str, object]) -> SemanticRepairSession:
    case = _cases()[case_id]
    return SemanticRepairSession(
        _initial(case_id, payload),
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    )


def _wrong_dps() -> dict[str, object]:
    payload = copy.deepcopy(_goldens()["generalization_dps_v1"])
    payload["mechanic"]["feedback"]["relation"] = "terminates"
    payload["role_path"]["effect"]["intent"] = "enable_ally"
    return payload


def _wrong_reaction() -> dict[str, object]:
    payload = copy.deepcopy(_goldens()["generalization_reaction_heal_v1"])
    payload["mechanic"]["feedback"]["response_effect"]["intent"] = "enable_ally"
    return payload


def test_dps_semantic_repair_uses_humanized_bounded_diagnostics_and_passes() -> None:
    valid = _goldens()["generalization_dps_v1"]
    initial = _initial("generalization_dps_v1", _wrong_dps())
    assert initial.evidence.evaluator_outcome == "FAIL"
    requests: list[SemanticRepairRequest] = []

    def repair(request: SemanticRepairRequest) -> object:
        requests.append(request)
        return valid

    case = _cases()["generalization_dps_v1"]
    result = SemanticRepairSession(
        initial,
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    ).run(repair)

    assert result.outcome is RepairOutcome.REPAIR_SUCCESS
    assert result.repair_attempts == 1
    assert result.evidence.repair_provider_calls == 1
    assert result.evidence.repaired_evaluator_outcome == "PASS"
    assert result.revalidation is not None
    assert result.revalidation.evidence.first_failure_layer is None
    assert len(requests) == 1
    prompt = requests[0].to_prompt()
    assert "feedback relationship mismatch" in prompt
    assert "role evidence mismatch" in prompt
    for forbidden in (
        "MECHANIC_MODE_MISMATCH",
        "CONTINUATION_FAMILY_MISMATCH",
        "ROLE_EFFECT_MISMATCH",
        "authorized_paths",
        "field_path",
        "expected",
        "actual",
    ):
        assert forbidden not in prompt
    validate_semantic_repair_evidence(result.to_mapping())


def test_reaction_semantic_repair_revalidates_every_pipeline_layer() -> None:
    initial = _initial("generalization_reaction_heal_v1", _wrong_reaction())
    valid = _goldens()["generalization_reaction_heal_v1"]
    calls = 0

    def repair(_: SemanticRepairRequest) -> object:
        nonlocal calls
        calls += 1
        return valid

    result = _session("generalization_reaction_heal_v1", _wrong_reaction()).run(repair)
    assert initial.evidence.first_failure_layer == "EVALUATOR"
    assert result.outcome is RepairOutcome.REPAIR_SUCCESS
    assert calls == 1
    assert result.revalidation is not None
    assert result.revalidation.evidence.parser_invoked is True
    assert result.revalidation.evidence.evaluator_invoked is True
    assert result.revalidation.evidence.principal_verdict == "PASS"
    assert result.revalidation.evidence.first_failure_layer is None


def test_semantic_repair_failure_is_reported_without_raw_material() -> None:
    initial_payload = _wrong_reaction()
    result = _session("generalization_reaction_heal_v1", initial_payload).run(
        lambda _: initial_payload
    )
    assert result.outcome is RepairOutcome.REPAIR_FAILED_SEMANTIC
    assert result.evidence.repaired_evaluator_outcome == "FAIL"
    serialized = json.dumps(result.to_mapping(), ensure_ascii=False)
    assert "enable_ally" not in serialized
    assert "CONTINUATION_FAMILY_MISMATCH" not in serialized
    validate_semantic_repair_evidence(result.to_mapping())


@pytest.mark.parametrize(
    ("response", "expected_layer"),
    [("not-json", "JSON"), ({"unexpected": True}, "IR_PARSE")],
)
def test_structural_repair_outputs_stop_at_their_first_failed_layer(
    response: object, expected_layer: str
) -> None:
    result = _session("generalization_dps_v1", _wrong_dps()).run(lambda _: response)
    assert result.outcome is RepairOutcome.REPAIR_FAILED_STRUCTURAL
    assert result.evidence.repair_pipeline_furthest_layer == expected_layer
    assert result.evidence.repaired_evaluator_outcome == "NOT_RUN"
    validate_semantic_repair_evidence(result.to_mapping())


def test_semantic_validation_failure_is_distinguished_from_parse_failure() -> None:
    response = copy.deepcopy(_goldens()["generalization_dps_v1"])
    response["mechanic"]["effect"]["intent"] = "unknown_semantic_intent"
    result = _session("generalization_dps_v1", _wrong_dps()).run(lambda _: response)
    assert result.outcome is RepairOutcome.REPAIR_FAILED_STRUCTURAL
    assert result.evidence.repair_pipeline_furthest_layer == "IR_VALIDATION"
    validate_semantic_repair_evidence(result.to_mapping())


def test_provider_unavailable_is_bounded_and_does_not_leak_exception_text() -> None:
    def unavailable(_: SemanticRepairRequest) -> object:
        raise RuntimeError("provider secret token TOP-SECRET")

    result = _session("generalization_dps_v1", _wrong_dps()).run(unavailable)
    assert result.outcome is RepairOutcome.REPAIR_UNAVAILABLE
    assert result.evidence.repair_provider_calls == 1
    assert result.evidence.repair_pipeline_furthest_layer == "PROVIDER"
    assert "TOP-SECRET" not in json.dumps(result.to_mapping())
    validate_semantic_repair_evidence(result.to_mapping())


@pytest.mark.parametrize(
    "case_id",
    ["generalization_support_alternate_v1", "generalization_control_v1"],
)
def test_support_and_control_pass_without_repair_provider_call(case_id: str) -> None:
    session = _session(case_id, _goldens()[case_id])
    calls = 0

    def should_not_run(_: SemanticRepairRequest) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("repair provider must not run for an initial PASS")

    result = session.run(should_not_run)
    assert result.outcome is RepairOutcome.NO_REPAIR_NEEDED
    assert result.evidence.repair_attempted is False
    assert result.evidence.repair_provider_calls == 0
    assert calls == 0


def test_initial_pass_does_not_consume_repair_budget() -> None:
    session = _session("generalization_dps_v1", _goldens()["generalization_dps_v1"])
    result = session.run(lambda _: pytest.fail("unexpected repair call"))
    assert result.outcome is RepairOutcome.NO_REPAIR_NEEDED
    assert result.repair_attempts == 0
    assert MAX_REPAIR_ATTEMPTS == 1


def test_second_repair_attempt_is_blocked_before_provider_call() -> None:
    session = _session("generalization_dps_v1", _wrong_dps())
    calls = 0

    def repair(_: SemanticRepairRequest) -> object:
        nonlocal calls
        calls += 1
        return _goldens()["generalization_dps_v1"]

    first = session.run(repair)
    second = session.run(lambda _: pytest.fail("second repair provider call"))
    assert first.outcome is RepairOutcome.REPAIR_SUCCESS
    assert second.outcome is RepairOutcome.REPAIR_BUDGET_EXHAUSTED
    assert second.repair_attempts == MAX_REPAIR_ATTEMPTS
    assert second.evidence.repair_attempted is False
    assert second.evidence.repair_provider_calls == 0
    assert calls == 1


def test_non_evaluator_failure_is_not_repair_eligible() -> None:
    malformed_initial = _initial("generalization_dps_v1", {"unknown": True})
    case = _cases()["generalization_dps_v1"]
    result = SemanticRepairSession(
        malformed_initial,
        case.generation_context(),
        case.evaluation_context(),
        repo_root=ROOT,
    ).run(lambda _: pytest.fail("structural failure must not trigger repair"))
    assert result.outcome is RepairOutcome.REPAIR_NOT_ELIGIBLE
    assert result.evidence.repair_provider_calls == 0


def test_repair_evidence_rejects_unallowlisted_raw_fields() -> None:
    result = _session("generalization_dps_v1", _wrong_dps()).run(
        lambda _: _goldens()["generalization_dps_v1"]
    )
    payload = result.to_mapping()
    with pytest.raises(ValueError, match="SEMANTIC_REPAIR_EVIDENCE_SCHEMA_INVALID"):
        validate_semantic_repair_evidence({**payload, "raw_candidate": _wrong_dps()})
