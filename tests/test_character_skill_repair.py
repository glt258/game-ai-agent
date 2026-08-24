"""Public-seam tests for bounded SkillKit repair."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from character_skill import (
    SkillKitPatch,
    SkillKitPatchError,
    SkillValidationReport,
    evaluate,
    parse_candidate,
    repair_once,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE = (
    ROOT
    / "evals"
    / "fixtures"
    / "character_skill_interface_prototype_cases_v0.1.1.public.json"
)


def _case(case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    fixture = json.loads(PUBLIC_FIXTURE.read_text(encoding="utf-8"))
    row = next(item for item in fixture["cases"] if item["case_id"] == case_id)
    return copy.deepcopy(row["candidate"]), copy.deepcopy(row["context"])


def _case19() -> tuple[object, object, SkillValidationReport]:
    candidate_payload, context_payload = _case("case_19")
    candidate = parse_candidate(candidate_payload)
    report = evaluate(candidate, context_payload)
    return candidate, context_payload, report


def _feedback_relation(*, operation: str = "enables") -> dict[str, object]:
    return {
        "feedback_id": "echo_feedback",
        "source_effect": {"kind": "effect", "id": "echo/trigger/apply"},
        "target_protocol": {"kind": "protocol", "id": "echo/feedback"},
        "event": "effect_resolved",
        "operation": operation,
    }


def _provider_for(report: SkillValidationReport, value: object) -> tuple[list[object], object]:
    calls: list[object] = []

    def provider(request: object) -> object:
        calls.append(request)
        if value == "valid":
            return {
                "base_digest": request.base_digest,
                "report_digest": request.report_digest,
                "operations": [
                    {
                        "op": "add",
                        "path": "/feedback_relations/-",
                        "value": _feedback_relation(),
                    }
                ],
            }
        return value

    return calls, provider


def test_repair_once_is_publicly_exposed() -> None:
    assert callable(repair_once)


def test_case19_repair_is_one_shot_and_returns_pass_without_mutating_input() -> None:
    candidate, context, report = _case19()
    original_digest = candidate.digest
    calls, provider = _provider_for(report, "valid")

    result = repair_once(candidate, report, context, provider)

    assert result.attempts == 1
    assert result.report.outcome == "PASS"
    assert result.report.findings == ()
    assert result.candidate.digest != original_digest
    assert candidate.digest == original_digest
    assert len(calls) == 1
    request = calls[0]
    assert request.finding_codes == ("REQUESTED_MECHANIC_UNREPRESENTED",)
    assert request.authorized_paths == ("/feedback_relations/-",)
    assert not hasattr(request, "canon_basis")


@pytest.mark.parametrize("case_id", ["case_13", "case_14", "case_15"])
def test_nonrepairable_cases_reject_before_provider_call(case_id: str) -> None:
    candidate_payload, context_payload = _case(case_id)
    candidate = parse_candidate(candidate_payload)
    report = evaluate(candidate, context_payload)
    calls: list[object] = []

    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, report, context_payload, lambda request: calls.append(request))

    assert report.outcome == "FAIL"
    assert calls == []


def test_tampered_report_is_rejected_before_provider_call() -> None:
    candidate, context, report = _case19()
    tampered = replace(report, report_digest="0" * 64)
    calls: list[object] = []

    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, tampered, context, lambda request: calls.append(request))

    assert calls == []


@pytest.mark.parametrize(
    "patch_value",
    [
        {
            "base_digest": "0" * 64,
            "report_digest": "unused",
            "operations": [],
        },
        {
            "base_digest": "unused",
            "report_digest": "unused",
            "operations": [{"op": "remove", "path": "/feedback_relations/-", "value": None}],
        },
        {
            "base_digest": "unused",
            "report_digest": "unused",
            "operations": [{"op": "add", "path": "/canon_basis/-", "value": {}}],
        },
        {
            "base_digest": "unused",
            "report_digest": "unused",
            "operations": [
                {
                    "op": "add",
                    "path": "/feedback_relations/-",
                    "value": _feedback_relation(),
                    "scope": "canon",
                }
            ],
        },
    ],
)
def test_digest_path_and_operation_scope_are_fail_closed(patch_value: object) -> None:
    candidate, context, report = _case19()
    calls, provider = _provider_for(report, patch_value)

    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, report, context, provider)

    assert len(calls) == 1


def test_empty_patch_is_rejected_as_no_improvement() -> None:
    candidate, context, report = _case19()
    calls, provider = _provider_for(
        report,
        {
            "base_digest": report.base_digest,
            "report_digest": report.report_digest,
            "operations": [],
        },
    )

    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, report, context, provider)

    assert len(calls) == 1


def test_patch_that_creates_a_new_finding_is_rejected() -> None:
    candidate, context, report = _case19()
    calls, provider = _provider_for(
        report,
        {
            "base_digest": report.base_digest,
            "report_digest": report.report_digest,
            "operations": [
                {
                    "op": "add",
                    "path": "/feedback_relations/-",
                    "value": _feedback_relation(operation="terminates"),
                }
            ],
        },
    )

    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, report, context, provider)

    assert len(calls) == 1


def test_provider_exception_is_contained_and_called_once() -> None:
    candidate, context, report = _case19()
    calls = 0

    def provider(request: object) -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider secret must not be surfaced")

    with pytest.raises(SkillKitPatchError, match="patch provider failed"):
        repair_once(candidate, report, context, provider)

    assert calls == 1


def test_frozen_patch_value_can_be_returned_by_provider() -> None:
    candidate, context, report = _case19()

    def provider(request: object) -> SkillKitPatch:
        return SkillKitPatch(
            request.base_digest,
            request.report_digest,
            (
                {
                    "op": "add",
                    "path": "/feedback_relations/-",
                    "value": _feedback_relation(),
                },
            ),
        )

    result = repair_once(candidate, report, context, provider)

    assert result.report.outcome == "PASS"
