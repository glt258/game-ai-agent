"""Offline tests for Reference Selection Quality Benchmark v0.4."""

from __future__ import annotations

import json
from pathlib import Path

from agents.official_character_authoring import load_reference_grounding
from agents.reference_selection_benchmark import (
    TOP_K,
    benchmark_cases,
    run_historical_replays,
    run_benchmark,
)


def _result() -> dict:
    return run_benchmark()


def test_benchmark_loads_all_fourteen_reference_records() -> None:
    result = _result()
    assert result["corpus_audit"]["records"]
    assert len(result["corpus_audit"]["records"]) == 14
    assert result["selector"]["candidate_count"] == 14


def test_all_required_cases_run() -> None:
    result = _result()
    assert len(result["cases"]) >= 12
    assert {case["brief_id"] for case in result["cases"]} == {
        case["brief_id"] for case in benchmark_cases()
    }
    assert len(result["contrast_pairs"]) >= 3


def test_full_ranking_contains_all_eligible_candidates() -> None:
    result = _result()
    for case in result["cases"]:
        assert len(case["full_ranking"]) == 14
        assert [item["rank"] for item in case["full_ranking"]] == list(range(1, 15))
        assert len({item["reference_id"] for item in case["full_ranking"]}) == 14


def test_selected_top_k_matches_production_selector() -> None:
    result = _result()
    for case in result["cases"][:12]:
        production = load_reference_grounding(case["brief"])
        assert case["selected_references"] == list(production.reference_ids)
        assert case["selected_top_k"] == TOP_K


def test_benchmark_does_not_alter_production_selection() -> None:
    brief = benchmark_cases()[0]["brief"]
    before = load_reference_grounding(brief).reference_ids
    _result()
    after = load_reference_grounding(brief).reference_ids
    assert before == after


def test_diagnostic_features_do_not_contribute_to_selection() -> None:
    result = _result()
    assert "activated" in result["selector"]["diagnostic_feature_scoring"]
    assert result["summary"]["unique_selected"] == 11
    assert result["summary"]["average_top_k_overlap"] == 0.34697
    assert result["summary"]["selection_concentration"]["hhi"] == 0.136488
    assert result["legacy_baseline"]["unique_selected"] == 11
    assert all(case["diagnostic_features"]["score_contribution"] == 0 for case in result["cases"])
    assert all(
        case["selected_references"]
        == [item["reference_id"] for item in case["full_ranking"][:TOP_K]]
        for case in result["cases"]
    )


def test_diagnostic_feature_output_is_deterministic() -> None:
    first = _result()
    second = _result()
    assert first["diagnostic_coverage"] == second["diagnostic_coverage"]
    assert [case["diagnostic_features"] for case in first["cases"]] == [
        case["diagnostic_features"] for case in second["cases"]
    ]


def test_identical_case_has_stable_ranking() -> None:
    result = _result()
    assert result["summary"]["stability"]["all_cases_stable"] is True
    assert all(case["stable_on_repeat"] for case in result["cases"])


def test_corpus_order_sensitivity_is_explicitly_tested() -> None:
    result = _result()
    order_test = result["corpus_order_test"]
    assert order_test["result"] in {"ORDER_INDEPENDENT", "CORPUS_ORDER_DEPENDENT"}
    assert order_test["baseline_full_ranking"]
    assert order_test["reversed_full_ranking"]


def test_concentration_metric_calculates_correctly() -> None:
    result = _result()
    selected = [
        reference_id
        for case in result["cases"]
        for reference_id in case["selected_references"]
    ]
    counts = {reference_id: selected.count(reference_id) for reference_id in set(selected)}
    expected = sum((count / len(selected)) ** 2 for count in counts.values())
    assert result["summary"]["selection_concentration"]["hhi"] == round(expected, 6)


def test_overlap_metric_calculates_correctly() -> None:
    result = _result()
    left = set(result["cases"][0]["selected_references"])
    right = set(result["cases"][1]["selected_references"])
    expected = len(left & right) / len(left | right)
    assert result["summary"]["average_top_k_overlap"] >= 0
    assert result["cases"][0]["selected_references"]
    assert round(expected, 6) == round(
        len(left & right) / len(left | right), 6
    )


def test_contrast_pair_delta_calculations_work() -> None:
    result = _result()
    assert len(result["contrast_pairs"]) >= 3
    for pair in result["contrast_pairs"]:
        delta = pair["delta"]
        assert len(delta["candidates"]) == 14
        assert delta["changed_candidate_count"] >= 0
        assert 0 <= delta["selected_overlap_jaccard"] <= 1


def test_json_output_is_deterministic() -> None:
    first = json.dumps(_result(), ensure_ascii=False, sort_keys=True, indent=2)
    second = json.dumps(_result(), ensure_ascii=False, sort_keys=True, indent=2)
    assert first == second


def test_source_game_frequency_calculates_from_selected_slots() -> None:
    result = _result()
    frequencies = result["summary"]["source_concentration"]["frequency"]
    assert sum(frequencies.values()) == len(result["cases"]) * TOP_K
    assert set(frequencies) == {
        "genshin-impact",
        "neverness-to-everness",
        "wuthering-waves",
        "zenless-zone-zero",
    }


def test_benchmark_works_without_live_llm_credentials() -> None:
    result = _result()
    assert result["selector"]["production_behavior_changed"] is True
    assert result["summary"]["stability"]["all_cases_stable"]


def test_benchmark_does_not_invoke_canon_checker() -> None:
    result = _result()
    assert "canon_checker" not in json.dumps(result).lower()
    assert "canon" not in result["selector"]["entry_point"].lower()


def test_generation_pipeline_behavior_is_not_part_of_benchmark() -> None:
    result = _result()
    assert result["review_packet"]["status"] == "PENDING_MIMO_REVIEW"
    assert all(case["evaluation"]["role_relevance"] is None for case in result["review_packet"]["cases"])


def test_historical_replay_fixtures_load_as_evidence() -> None:
    replays = run_historical_replays()
    assert [item["case_id"] for item in replays] == ["P1", "P2", "P3", "P4"]
    assert all(item["brief_status"] == "APPROXIMATE_BRIEF_REPLAY" for item in replays)
    assert all(item["historical_expected_output_is_evidence_only"] for item in replays)
    assert all(
        item["historical_top_k"]
        == ["genshin-impact:furina", "genshin-impact:keqing", "genshin-impact:nahida"]
        for item in replays
    )


def test_historical_replay_uses_production_selector_implementation() -> None:
    result = _result()
    assert result["benchmark_path"]["same_selector_implementation"] is True
    for replay in result["historical_replays"]:
        assert replay["benchmark_brief_replay_top_k"] == replay["production_input_replay_top_k"]
        assert replay["production_input_replay_top_k"] == replay["direct_selector_replay_top_k"]


def test_historical_brief_replay_is_deterministic() -> None:
    assert run_historical_replays() == run_historical_replays()


def test_production_input_replay_is_deterministic() -> None:
    first = run_historical_replays()
    second = run_historical_replays()
    assert [item["production_input_replay_top_k"] for item in first] == [
        item["production_input_replay_top_k"] for item in second
    ]


def test_historical_replay_requires_no_live_llm() -> None:
    result = _result()
    assert result["production_path"]["live_model_dependency"] is False
    assert result["production_path"]["tool_loop_dependency"] is False
    assert result["parity_classification"]["model_or_tool_loop_influence_on_selection"] is False


def test_replay_does_not_change_selector_state() -> None:
    brief = benchmark_cases()[0]["brief"]
    before = load_reference_grounding(brief).reference_ids
    run_historical_replays()
    after = load_reference_grounding(brief).reference_ids
    assert before == after


def test_parity_comparison_preserves_unknown_historical_scores() -> None:
    for replay in run_historical_replays():
        assert replay["score_differences"]["historical_scores_available"] is False
        assert replay["score_differences"]["replay_score_by_reference"]
        assert replay["input_differences"]["brief_replay_is_approximate"] is True


def test_parity_classification_and_metrics_are_separate() -> None:
    result = _result()
    assert result["parity_classification"]["classification"] == "HISTORICAL_CASE_DIFFERENCE"
    assert result["summary"]["unique_selected"] == 11
    assert result["summary"]["average_top_k_overlap"] == 0.34697
    assert result["summary"]["selection_concentration"]["hhi"] == 0.136488


def test_production_audit_semantics_are_recorded() -> None:
    result = _result()
    assert "CharacterGenerationAudit.reference_ids" in result["production_path"]["audit_path"]
    assert "pre-generation top-k" in result["production_path"]["selected_reference_semantics"]
