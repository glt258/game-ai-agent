"""Focused tests for the separate v0.4.2b feature diagnostic extension."""

from __future__ import annotations

from agents.official_character_authoring import load_reference_grounding
from agents.reference_feature_discrimination_diagnostic import (
    CLASSIFICATIONS,
    diagnostic_cases,
    run_diagnostic,
)
from agents.reference_selection_benchmark import benchmark_cases, run_benchmark


CORE_CASE_IDS = {
    "case-a-urban-support",
    "case-b-spatial-control",
    "case-c-aggressive-frontline",
    "case-d-defensive-protective",
    "case-e-mobility-repositioning",
    "case-f-information-investigation",
    "case-g-expressive-performer",
    "case-h-mature-active",
    "case-i-youthful-ambiguous",
    "case-j-informal-social-role",
    "case-k-charisma-low-authority",
    "case-l-quiet-practical",
    "contrast-occupation-role-onfield",
    "contrast-occupation-role-support",
    "contrast-role-quiet",
    "contrast-role-flamboyant",
    "contrast-personality-researcher",
    "contrast-personality-magistrate",
}


def test_frozen_core_cases_remain_separate_and_unchanged() -> None:
    cases = benchmark_cases()
    assert len(cases) == 18
    assert {case["brief_id"] for case in cases} == CORE_CASE_IDS
    assert len(diagnostic_cases()) == 12
    assert not CORE_CASE_IDS & {case.case_id for case in diagnostic_cases()}


def test_diagnostic_cases_are_name_free_and_pairwise_complete() -> None:
    names = ("furina", "keqing", "nahida", "fadia", "shinku", "jinhsi", "mortefi", "shorekeeper", "jane", "nicole")
    cases = diagnostic_cases()
    by_id = {case.case_id: case for case in cases}
    assert len(by_id) == 12
    for case in cases:
        lowered = case.brief.lower()
        assert not any(name in lowered for name in names)
        assert case.counterfactual_partner in by_id
        assert by_id[case.counterfactual_partner].counterfactual_partner == case.case_id
        assert "expected_reference_id" not in case.__dict__


def test_diagnostic_extraction_and_failure_labels_are_deterministic() -> None:
    first = run_diagnostic()
    second = run_diagnostic()
    assert first == second
    assert first["case_count"] == 12
    assert len(first["counterfactual_pairs"]) == 6
    assert all(not case["feature_delta"]["missing"] for case in first["cases"])
    assert all(not case["feature_delta"]["unexpected"] for case in first["cases"])
    assert all(case["failure_classification"] in CLASSIFICATIONS for case in first["cases"])
    assert first["classification_counts"] == {
        "CORPUS_COVERAGE_GAP": 3,
        "EXPECTED_SHARED_TRAIT": 1,
        "MULTI_REFERENCE_COLLISION": 4,
        "PASS_CURRENT_REPRESENTATION": 2,
        "VOCABULARY_REPRESENTATION_GAP": 2,
    }


def test_shadow_overlap_is_diagnostic_only() -> None:
    result = run_diagnostic()
    assert result["production_behavior"] == {
        "feature_score_contribution": 0,
        "selector_touched": False,
        "winner_criterion": None,
    }
    for case in result["cases"]:
        assert case["shadow_overlap"]["non_scoring"] is True
        assert "selected_reference_id" not in case
        assert "expected_reference_id" not in case


def test_core_benchmark_metrics_and_selector_remain_unchanged() -> None:
    brief = "A quiet practical researcher with an on_field_dps combat role."
    before = load_reference_grounding(brief).reference_ids
    diagnostic = run_diagnostic()
    after = load_reference_grounding(brief).reference_ids
    core = run_benchmark()
    assert diagnostic["case_count"] == 12
    assert before == after
    assert core["summary"]["unique_selected"] == 9
    assert core["summary"]["average_top_k_overlap"] == 0.360606
    assert core["summary"]["selection_concentration"]["hhi"] == 0.146776
    assert core["classification"] == "LIMITED_SENSITIVITY"
    assert core["corpus_order_test"]["result"] == "ORDER_INDEPENDENT"
    assert all(case["diagnostic_features"]["score_contribution"] == 0 for case in core["cases"])
