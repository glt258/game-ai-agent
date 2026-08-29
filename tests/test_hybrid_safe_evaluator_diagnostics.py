"""Offline safety and compatibility tests for Hybrid evaluator diagnostics."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from character_intelligence.hybrid_ir import (
    SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
    SAFE_EVALUATOR_DIAGNOSTIC_VERSION_V010,
    FindingCategory,
    Repairability,
    SafeEvaluatorDiagnostics,
    SemanticDimension,
    adapt_skill_validation_report,
    validate_hybrid_evidence,
)
from character_skill.models import SkillFinding, SkillValidationReport
from tests.historical_fixtures import historical_fixture_path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = historical_fixture_path("character_skill_s2_hybrid_ir_run_01_v0.2.0.json")
HISTORICAL_DIAGNOSTIC = historical_fixture_path("character_skill_s2_hybrid_ir_run_01_v0.3.0.json")


def _report(*findings: SkillFinding, outcome: str = "FAIL") -> SkillValidationReport:
    return SkillValidationReport(
        outcome=outcome,
        blocking=outcome != "PASS",
        repair_allowed=outcome == "REPAIR",
        findings=tuple(findings),
        candidate_digest="candidate-digest",
        context_digest="context-digest",
        report_digest="report-digest",
    )


def test_pass_contract_is_empty_and_typed() -> None:
    result = adapt_skill_validation_report(_report(outcome="PASS"))
    assert result.to_mapping() == {
        "schema_version": SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
        "complete": True,
        "finding_count": 0,
        "dimensions": [],
        "categories": [],
        "counts_by_dimension": {},
        "counts_by_category": {},
        "repairability": "NOT_APPLICABLE",
    }


def test_mapping_preserves_duplicates_and_is_order_independent() -> None:
    findings = (
        SkillFinding("ROLE_EFFECT_MISMATCH", "/secret/path", False, False, ("effect-secret-id",)),
        SkillFinding("MECHANIC_SKELETON_ABSENT", "/entries", True, False),
        SkillFinding("ROLE_EFFECT_MISMATCH", "/another/path", False, False),
    )
    first = adapt_skill_validation_report(_report(*findings))
    second = adapt_skill_validation_report(_report(*reversed(findings)))
    assert first == second
    assert first.finding_count == 3
    assert first.counts_by_dimension[SemanticDimension.ROLE_EVIDENCE] == 2
    assert first.counts_by_dimension[SemanticDimension.MECHANIC_SKELETON] == 1
    assert first.repairability is Repairability.NON_REPAIRABLE
    assert first.to_mapping()["dimensions"] == ["MECHANIC_SKELETON", "ROLE_EVIDENCE"]


def test_repairability_aggregate_and_failure_authority_are_separate() -> None:
    repair = adapt_skill_validation_report(
        _report(SkillFinding("REQUESTED_MECHANIC_UNREPRESENTED", "/x", True, True), outcome="REPAIR")
    )
    mixed = adapt_skill_validation_report(
        _report(
            SkillFinding("REQUESTED_MECHANIC_UNREPRESENTED", "/x", True, True),
            SkillFinding("ROLE_EFFECT_MISMATCH", "/y", True, False),
            outcome="FAIL",
        )
    )
    assert repair.repairability is Repairability.REPAIRABLE
    assert mixed.repairability is Repairability.MIXED


def test_unknown_finding_is_bounded_and_does_not_leak_sentinels() -> None:
    report = _report(
        SkillFinding(
            "FUTURE_SECRET_FINDING_TOP_SECRET",
            "secret/path/TOP-SECRET-GENERATED-VALUE",
            True,
            True,
            ("effect-secret-id",),
            ("protocol-secret-id",),
        )
    )
    serialized = json.dumps(adapt_skill_validation_report(report).to_mapping())
    assert serialized == json.dumps({
        "schema_version": SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
        "complete": False,
        "finding_count": 1,
        "dimensions": ["OTHER_SEMANTIC"],
        "categories": ["UNKNOWN"],
        "counts_by_dimension": {"OTHER_SEMANTIC": 1},
        "counts_by_category": {"UNKNOWN": 1},
        "repairability": "UNKNOWN",
    })
    for sentinel in (
        "FUTURE_SECRET_FINDING_TOP_SECRET", "TOP-SECRET-GENERATED-VALUE",
        "effect-secret-id", "protocol-secret-id",
    ):
        assert sentinel not in serialized


def test_diagnostic_mapping_does_not_mutate_report() -> None:
    report = _report(SkillFinding("REFERENCE_COPYING", "/context/reference_review_context"))
    before = copy.deepcopy(report.to_mapping())
    adapt_skill_validation_report(report)
    assert report.to_mapping() == before


def test_v020_historical_bundle_dispatch_still_passes_without_new_field() -> None:
    payload = json.loads(HISTORICAL.read_text(encoding="utf-8"))
    validate_hybrid_evidence(payload)
    assert payload["evidence_version"] == "character-skill-s2-hybrid-ir-shadow/0.2.0"
    assert "evaluator_diagnostics" not in payload


def test_v030_diagnostic_schema_rejects_unknown_fields_and_bad_counts() -> None:
    good = SafeEvaluatorDiagnostics(
        SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
        True,
        0,
        (),
        (),
        {},
        {},
        Repairability.NOT_APPLICABLE,
    ).to_mapping()
    with pytest.raises(ValueError, match="SAFE_DIAGNOSTIC_SCHEMA_INVALID"):
        SafeEvaluatorDiagnostics.from_mapping({**good, "unexpected": True})
    with pytest.raises(ValueError, match="SAFE_DIAGNOSTIC_COUNT_VALUE_INVALID"):
        SafeEvaluatorDiagnostics(
            SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
            True,
            1,
            (SemanticDimension.ROLE_EVIDENCE,),
            (FindingCategory.ROLE_EVIDENCE_MISMATCH,),
            {SemanticDimension.ROLE_EVIDENCE: 0},
            {FindingCategory.ROLE_EVIDENCE_MISMATCH: 1},
            Repairability.NON_REPAIRABLE,
        )


def test_v010_diagnostic_payload_remains_readable_after_wire_version_bump() -> None:
    payload = json.loads(HISTORICAL_DIAGNOSTIC.read_text(encoding="utf-8"))
    validate_hybrid_evidence(payload)
    diagnostic = SafeEvaluatorDiagnostics.from_mapping(payload["evaluator_diagnostics"])
    assert diagnostic.schema_version == SAFE_EVALUATOR_DIAGNOSTIC_VERSION_V010
    assert diagnostic.to_mapping() == payload["evaluator_diagnostics"]


def test_new_finding_codes_have_safe_semantic_dimensions() -> None:
    report = _report(
        SkillFinding("MECHANIC_MODE_MISMATCH", "/entries", False, False),
        SkillFinding("CONTINUATION_FAMILY_MISMATCH", "/feedback_relations", False, False),
    )
    diagnostic = adapt_skill_validation_report(report)
    assert diagnostic.schema_version == SAFE_EVALUATOR_DIAGNOSTIC_VERSION
    assert diagnostic.complete is True
    assert diagnostic.finding_count == 2
    assert diagnostic.dimensions == (
        SemanticDimension.CONTINUATION_FAMILY,
        SemanticDimension.MODE,
    )
    assert diagnostic.categories == (FindingCategory.SEMANTIC_MISMATCH,)
    assert diagnostic.repairability is Repairability.NON_REPAIRABLE
