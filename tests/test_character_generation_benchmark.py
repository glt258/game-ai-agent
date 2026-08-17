from __future__ import annotations

from dataclasses import replace

from agents import CanonCheckStatus, CanonFindingCode
from agents.character_benchmark import (
    ALL_CASE_IDS,
    CORE_CASE_IDS,
    WATCH_CASE_IDS,
    case_a_alignment_failures,
    case_b_over_invention_findings,
    compute_metrics,
    run_benchmark,
)


def _results():
    return {result.case_id: result for result in run_benchmark()}


def test_all_core_and_watch_cases_execute_through_authoring_workflow():
    results = _results()
    assert tuple(results) == ALL_CASE_IDS
    assert set(results) == set(CORE_CASE_IDS + WATCH_CASE_IDS)
    assert all(result.authoring_result.initial_draft == result.initial_draft for result in results.values())


def test_case_a_checks_the_requested_loop_without_mechanic_schema_vocabulary():
    result = _results()["A"]
    assert result.initial_report.status == CanonCheckStatus.PASS
    assert result.final_report.status == CanonCheckStatus.PASS
    assert result.repair_triggered is False
    assert result.accepted is True
    assert case_a_alignment_failures(result.final_draft) == ()


def test_case_b_detects_prohibited_personal_resource_over_invention():
    result = _results()["B"]
    assert result.accepted is True
    invented = replace(
        result.final_draft,
        ability_concept="每次攻击命中都会积累个人资源，满层后进入强化状态。",
    )
    assert case_b_over_invention_findings(invented)


def test_case_c_detects_repairs_and_minimally_rechecks_one_canon_finding():
    result = _results()["C"]
    repair = result.authoring_result.repair_result
    assert any(
        finding.code == CanonFindingCode.UNSUPPORTED_CANON_CLAIM
        and finding.field_path == "relationships[0].status"
        for finding in result.initial_report.findings
    )
    assert result.repair_triggered is True
    assert result.repair_succeeded is True
    assert result.minimal_repair is True
    assert result.final_report.status == CanonCheckStatus.PASS
    assert result.accepted is True
    assert repair.changed_fields == ("relationships",)
    before = result.initial_draft.to_dict()
    after = result.final_draft.to_dict()
    assert [field for field in before if before[field] != after[field]] == ["relationships"]


def test_case_d_accepts_truthful_unresolved_conflict_without_fake_compromise():
    result = _results()["D"]
    assert result.initial_report.status == CanonCheckStatus.FAIL
    assert result.final_report.status == CanonCheckStatus.FAIL
    assert result.repair_triggered is True
    assert result.repair_succeeded is False
    assert result.final_draft == result.initial_draft
    assert result.accepted is True


def test_watch_cases_are_observed_but_never_blocking():
    results = _results()
    for case_id in WATCH_CASE_IDS:
        result = results[case_id]
        assert result.blocking is False
        assert result.accepted is True
        assert result.watch_observation
        assert result.representation_pressure is True


def test_metrics_exclude_watch_cases_from_all_primary_denominators():
    metrics = compute_metrics(tuple(_results().values()))
    assert metrics.evaluable_core_cases == 4
    assert metrics.first_pass_passes == 2
    assert metrics.repair_attempts == 2
    assert metrics.repair_successes == 1
    assert metrics.minimal_repairs == 1
    assert metrics.final_end_to_end_passes == 4
    assert metrics.first_pass_pass_rate == 0.5
    assert metrics.repair_success_rate == 0.5
    assert metrics.minimal_repair_rate == 1.0
    assert metrics.final_end_to_end_pass_rate == 1.0
