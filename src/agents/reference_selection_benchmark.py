"""Offline Reference Selection Quality Benchmark v0.4.

This module measures the existing deterministic selector.  It deliberately
does not call Character Generation, Canon Checker, Repair, or a live model.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from reference_corpus.loader import load_corpus_manifest, load_game_catalog
from reference_corpus.repository import CharacterReferenceRepository
from reference_corpus.features import (
    FEATURE_VOCABULARY_VERSION,
    DiagnosticFeatureProfile,
    diagnostic_overlap,
    extract_brief_features,
    feature_coverage,
    reference_feature_profile,
)

from .official_character_authoring import (
    DEFAULT_CORPUS_ROOT,
    _reference_summary,
    load_reference_grounding,
    rank_reference_summaries,
)


BENCHMARK_VERSION = "reference-selection-quality-benchmark/0.4"
TOP_K = 3


def _case(brief_id: str, category: str, brief: str, dimensions: Sequence[str]) -> dict[str, Any]:
    return {
        "brief_id": brief_id,
        "category": category,
        "brief": brief,
        "dimensions": list(dimensions),
    }


def benchmark_cases() -> tuple[dict[str, Any], ...]:
    """Return the frozen broad matrix plus explicit contrast-pair briefs."""

    return (
        _case(
            "case-a-urban-support",
            "A — ordinary urban support",
            "An ordinary urban support character working in an appliance repair shop: maintenance, troubleshooting, practical community service.",
            ("occupation", "support", "ordinary-life identity"),
        ),
        _case(
            "case-b-spatial-control",
            "B — control / spatial coordination",
            "A stage execution coordinator focused on spatial control, crowd routing, timing, and safe movement through a venue.",
            ("control", "spatial coordination", "occupation"),
        ),
        _case(
            "case-c-aggressive-frontline",
            "C — aggressive frontline",
            "An aggressive frontline direct-combat character with an on_field_dps fantasy centered on attacks and damage.",
            ("combat role", "direct combat", "ability fantasy"),
        ),
        _case(
            "case-d-defensive-protective",
            "D — defensive / protective",
            "A defensive protective character focused on support, healing, shielding, and stabilization.",
            ("support", "protection", "ability fantasy"),
        ),
        _case(
            "case-e-mobility-repositioning",
            "E — mobility / repositioning",
            "A mobility-focused courier and route planner: an urban runner who repositions people through complicated streets.",
            ("mobility", "repositioning", "occupation"),
        ),
        _case(
            "case-f-information-investigation",
            "F — information / investigation",
            "An archivist and fact checker who works as a field investigator for information gathering and criminal investigation.",
            ("investigation", "information", "occupation"),
        ),
        _case(
            "case-g-expressive-performer",
            "G — performer / expressive social identity",
            "A flamboyant performer with an expressive stage identity, high social presence, and a public-facing creative hook.",
            ("performer", "expressive identity", "personality"),
        ),
        _case(
            "case-h-mature-active",
            "H — mature active playable character",
            "A mature, active playable character: an experienced magistrate who remains hands-on in daily operations.",
            ("life-stage", "occupation", "active playable identity"),
        ),
        _case(
            "case-i-youthful-ambiguous",
            "I — youthful / age-ambiguous independent character",
            "A youthful but age-ambiguous independent character who works alone and is not defined by school or a formal office.",
            ("life-stage", "age ambiguity", "independence"),
        ),
        _case(
            "case-j-informal-social-role",
            "J — ordinary non-professional / informal social role",
            "An ordinary non-professional neighbor with an informal community social role and no prestigious occupation.",
            ("ordinary-life identity", "informal social role", "occupation"),
        ),
        _case(
            "case-k-charisma-low-authority",
            "K — high social charisma / low formal authority",
            "A highly charismatic social connector with low formal authority: persuasive, warm, and influential without office.",
            ("personality", "social identity", "authority"),
        ),
        _case(
            "case-l-quiet-practical",
            "L — quiet practical / low spectacle",
            "A quiet, practical character with a low-spectacle daily identity, patient problem solving, and no theatrical presentation.",
            ("personality", "occupation", "low spectacle"),
        ),
        _case(
            "contrast-occupation-role-onfield",
            "Contrast 1 before — same occupation, combat role changes",
            "A quiet practical researcher with an on_field_dps combat role.",
            ("occupation", "combat role"),
        ),
        _case(
            "contrast-occupation-role-support",
            "Contrast 1 after — same occupation, combat role changes",
            "A quiet practical researcher with a support healer combat role.",
            ("occupation", "combat role"),
        ),
        _case(
            "contrast-role-quiet",
            "Contrast 2 before — same combat role, personality / hook changes",
            "An on_field_dps character with a quiet practical personality and restrained daily hook.",
            ("combat role", "personality", "hook"),
        ),
        _case(
            "contrast-role-flamboyant",
            "Contrast 2 after — same combat role, personality / hook changes",
            "An on_field_dps character with a flamboyant expressive personality and stage performer hook.",
            ("combat role", "personality", "hook"),
        ),
        _case(
            "contrast-personality-researcher",
            "Contrast 3 before — same personality, occupation changes",
            "A quiet practical researcher with a low-spectacle daily identity.",
            ("personality", "occupation"),
        ),
        _case(
            "contrast-personality-magistrate",
            "Contrast 3 after — same personality, occupation changes",
            "A quiet practical magistrate with a low-spectacle daily identity.",
            ("personality", "occupation"),
        ),
    )


CONTRAST_PAIRS = (
    {
        "pair_id": "pair-1-occupation-combat-role",
        "dimension": "combat role",
        "before_brief_id": "contrast-occupation-role-onfield",
        "after_brief_id": "contrast-occupation-role-support",
    },
    {
        "pair_id": "pair-2-combat-role-personality-hook",
        "dimension": "personality / character hook",
        "before_brief_id": "contrast-role-quiet",
        "after_brief_id": "contrast-role-flamboyant",
    },
    {
        "pair_id": "pair-3-personality-occupation",
        "dimension": "occupation",
        "before_brief_id": "contrast-personality-researcher",
        "after_brief_id": "contrast-personality-magistrate",
    },
)


COUNTERFACTUAL_PAIRS = (
    {
        "pair_id": "counterfactual-support-to-control",
        "dimension": "role / ability fantasy",
        "before": "An ordinary character with a support healer role.",
        "after": "An ordinary character with a control role.",
    },
    {
        "pair_id": "counterfactual-quiet-to-flamboyant",
        "dimension": "personality",
        "before": "A quiet practical researcher.",
        "after": "A flamboyant expressive researcher.",
    },
    {
        "pair_id": "counterfactual-repair-to-performer",
        "dimension": "occupation",
        "before": "A practical repair worker.",
        "after": "A practical performer.",
    },
    {
        "pair_id": "counterfactual-mature-to-youthful",
        "dimension": "life-stage",
        "before": "A mature active magistrate.",
        "after": "A youthful age-ambiguous magistrate.",
    },
)


# The repository contains outcome summaries for these historical runs, but it
# does not contain their exact brief text. Keep that uncertainty explicit: the
# strings below are replay inputs derived only from the preserved brief
# characteristics in the v0.3/v0.2 documentation and the parity task.
HISTORICAL_REPLAY_FIXTURES = (
    {
        "case_id": "P1",
        "character_name": "麦嫂",
        "brief_status": "APPROXIMATE_BRIEF_REPLAY",
        "brief": "五星可操作角色\n临洲小型家电维修店\n普通都市职业\nsupport\nrepair / troubleshooting combat fantasy\nno secret identity\nno special bloodline\nno combat background",
        "historical_top_k": [
            "genshin-impact:furina",
            "genshin-impact:keqing",
            "genshin-impact:nahida",
        ],
        "preserved_sources": ["docs/live_character_authoring_demo_v0.2.md"],
    },
    {
        "case_id": "P2",
        "character_name": "土屑",
        "brief_status": "APPROXIMATE_BRIEF_REPLAY",
        "brief": "youthful / age unspecified\nindependent dangerous field work\nnot student\nno secret prodigy\nno experiment\nlimited authority\nplayable",
        "historical_top_k": [
            "genshin-impact:furina",
            "genshin-impact:keqing",
            "genshin-impact:nahida",
        ],
        "preserved_sources": ["docs/character_diversity_life_stage_v0.3.md"],
    },
    {
        "case_id": "P3",
        "character_name": "覃雪岫",
        "brief_status": "APPROXIMATE_BRIEF_REPLAY",
        "brief": "mature active playable woman\nordinary mid-level urban identity\nnot mentor\nnot retired master\ncontrol fantasy\nsupply-station operator",
        "historical_top_k": [
            "genshin-impact:furina",
            "genshin-impact:keqing",
            "genshin-impact:nahida",
        ],
        "preserved_sources": ["docs/character_diversity_life_stage_v0.3.md"],
    },
    {
        "case_id": "P4",
        "character_name": "沈蓝枝",
        "brief_status": "APPROXIMATE_BRIEF_REPLAY",
        "brief": "strict unknown age\npatchwork tailor\ncommunity social role\nsupport\nfamily responsibility allowed\nno age / school-history invention",
        "historical_top_k": [
            "genshin-impact:furina",
            "genshin-impact:keqing",
            "genshin-impact:nahida",
        ],
        "preserved_sources": [
            "docs/character_diversity_life_stage_v0.3.md",
            "docs/character_age_information_preservation_v0.3.md",
        ],
    },
)


def _compact_ranking(ranking: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": item["rank"],
            "reference_id": item["reference_id"],
            "character_name": item["character_name"],
            "source_game": item["source_game"],
            "score": item["score"],
            "score_gap_from_previous": item["score_gap_from_previous"],
        }
        for item in ranking
    ]


def _tie_groups(ranking: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    groups: dict[int, list[str]] = {}
    for item in ranking:
        groups.setdefault(int(item["score"]), []).append(str(item["reference_id"]))
    return [ids for _, ids in sorted(groups.items(), reverse=True) if len(ids) > 1]


def _run_case(
    case: Mapping[str, Any],
    summaries: Sequence[Mapping[str, Any]],
    top_k: int,
    feature_profiles: Mapping[str, DiagnosticFeatureProfile] | None = None,
) -> dict[str, Any]:
    ranking = rank_reference_summaries(str(case["brief"]), summaries)
    repeated = rank_reference_summaries(str(case["brief"]), summaries)
    compact = _compact_ranking(ranking)
    result = {
        "brief_id": case["brief_id"],
        "category": case["category"],
        "brief": case["brief"],
        "dimensions": list(case["dimensions"]),
        "selected_references": [item["reference_id"] for item in compact[:top_k]],
        "full_ranking": compact,
        "selected_top_k": top_k,
        "tie_groups": _tie_groups(compact),
        "score_gaps": [item["score_gap_from_previous"] for item in compact],
        "component_scores_available": False,
        "component_scores": None,
        "stable_on_repeat": [item["reference_id"] for item in compact]
        == [item["reference_id"] for item in _compact_ranking(repeated)],
    }
    if feature_profiles is not None:
        brief_features = extract_brief_features(str(case["brief"]))
        result["diagnostic_features"] = {
            "vocabulary_version": FEATURE_VOCABULARY_VERSION,
            "score_contribution": 0,
            "brief": brief_features.to_dict(include_evidence=False),
            "overlap_by_reference": {
                reference_id: diagnostic_overlap(
                    brief_features,
                    feature_profiles[reference_id],
                )
                for reference_id in sorted(feature_profiles)
            },
        }
    return result


def _rank_map(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item["reference_id"]): item for item in result["full_ranking"]}


def _ranking_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_map = _rank_map(before)
    after_map = _rank_map(after)
    candidates = []
    for reference_id in sorted(before_map):
        left = before_map[reference_id]
        right = after_map[reference_id]
        candidates.append(
            {
                "reference_id": reference_id,
                "character_name": left["character_name"],
                "rank_before": left["rank"],
                "rank_after": right["rank"],
                "score_before": left["score"],
                "score_after": right["score"],
                "rank_delta": right["rank"] - left["rank"],
                "score_delta": right["score"] - left["score"],
            }
        )
    changed = [item for item in candidates if item["rank_delta"] or item["score_delta"]]
    return {
        "changed_candidate_count": len(changed),
        "mean_absolute_rank_delta": round(
            sum(abs(item["rank_delta"]) for item in candidates) / len(candidates), 6
        ),
        "selected_overlap_jaccard": _jaccard(
            before["selected_references"], after["selected_references"]
        ),
        "candidates": candidates,
    }


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return round(len(a & b) / len(a | b), 6)


def _hhi(values: Sequence[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if not total:
        return 0.0
    return round(sum((count / total) ** 2 for count in counts.values()), 6)


def _frequency(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _source_frequencies(
    case_results: Sequence[Mapping[str, Any]],
    summaries_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    sources = [
        str(summaries_by_id[reference_id]["game_id"])
        for case in case_results
        for reference_id in case["selected_references"]
    ]
    return _frequency(sources)


def _corpus_audit(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = ("roles", "occupation", "ability_categories", "taxonomy")
    records = []
    coverage: dict[str, int] = {field: 0 for field in fields}
    for summary in summaries:
        missing = [field for field in fields if not summary.get(field)]
        for field in fields:
            if summary.get(field):
                coverage[field] += 1
        records.append(
            {
                "reference_id": summary["reference_id"],
                "character_name": summary["display_name"],
                "source_game": summary["game_id"],
                "primary_role_or_category": summary.get("roles") or [],
                "ability_category": summary.get("ability_categories") or [],
                "personality_tags": None,
                "detail_granularity": None,
                "other_selector_visible_fields": {
                    "occupation": summary.get("occupation"),
                    "taxonomy": summary.get("taxonomy") or {},
                },
                "missing_selector_visible_fields": missing,
            }
        )
    return {
        "selector_visible_fields": [
            "reference_id",
            "display_name",
            "game_id",
            "roles (analysis or taxonomy role labels)",
            "occupation",
            "ability_categories",
            "taxonomy",
        ],
        "component_score_fields": [],
        "records": records,
        "field_coverage_counts": coverage,
        "not_exposed_as_selector_metadata": [
            "personality tags",
            "life-stage / age",
            "character hook",
            "detail granularity",
        ],
    }


def _coverage(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    targets = {
        "mature_character": ("mature", "adult"),
        "young_age_ambiguous": ("young", "youth", "age-ambiguous"),
        "frontline_role": ("on_field_dps",),
        "support": ("support", "healer"),
        "performer": ("performer", "stage"),
        "ordinary_worker": ("worker", "repair", "courier"),
        "investigator": ("investigation", "investigator"),
        "high_charisma": ("charisma",),
    }
    output = {}
    for dimension, terms in targets.items():
        matched = []
        for summary in summaries:
            haystack = json.dumps(dict(summary), ensure_ascii=False).lower()
            if any(term in haystack for term in terms):
                matched.append(summary["reference_id"])
        if not matched:
            status = "NOT REPRESENTED"
        elif dimension == "frontline_role" and not any(
            "frontline" in json.dumps(dict(summary), ensure_ascii=False).lower()
            for summary in summaries
        ):
            status = "PARTIAL"
        else:
            status = "COVERED"
        output[dimension] = {
            "status": status,
            "selector_visible_terms": list(terms),
            "matching_reference_ids": matched,
        }
    return output


def _corpus_order_test(brief: str, summaries: Sequence[Mapping[str, Any]], top_k: int) -> dict[str, Any]:
    baseline = rank_reference_summaries(brief, summaries)
    reversed_order = rank_reference_summaries(brief, list(reversed(summaries)))
    baseline_ids = [item["reference_id"] for item in baseline[:top_k]]
    reversed_ids = [item["reference_id"] for item in reversed_order[:top_k]]
    full_baseline = [item["reference_id"] for item in baseline]
    full_reversed = [item["reference_id"] for item in reversed_order]
    return {
        "result": "ORDER_INDEPENDENT" if full_baseline == full_reversed else "CORPUS_ORDER_DEPENDENT",
        "brief": brief,
        "baseline_selected": baseline_ids,
        "reversed_selected": reversed_ids,
        "baseline_full_ranking": full_baseline,
        "reversed_full_ranking": full_reversed,
        "tie_breaking": "ascending reference_id after descending score",
        "impact": "none" if full_baseline == full_reversed else "ranking changed when iteration order changed",
    }


def _historical_match(historical: Sequence[str], replay: Sequence[str]) -> str:
    if list(historical) == list(replay):
        return "EXACT"
    if set(historical) & set(replay):
        return "PARTIAL"
    return "NO"


def _rank_differences(
    historical: Sequence[str],
    replay: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    replay_ranks = {str(item["reference_id"]): int(item["rank"]) for item in replay}
    tracked = list(dict.fromkeys([*historical, *replay_ranks]))
    historical_ranks = {reference_id: index for index, reference_id in enumerate(historical, start=1)}
    return [
        {
            "reference_id": reference_id,
            "historical_rank": historical_ranks.get(reference_id),
            "replay_rank": replay_ranks.get(reference_id),
            "rank_delta": (
                replay_ranks[reference_id] - historical_ranks[reference_id]
                if reference_id in replay_ranks and reference_id in historical_ranks
                else None
            ),
        }
        for reference_id in tracked
    ]


def run_historical_replays(
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    """Replay preserved historical cases without generation or live providers."""

    corpus_root = Path(corpus_root)
    catalog = load_game_catalog(corpus_root / "_catalog" / "games.yaml")
    repository = CharacterReferenceRepository(corpus_root, catalog=catalog)
    summaries = [_reference_summary(reference) for reference in repository.list_all()]
    replay_results: list[dict[str, Any]] = []
    for fixture in HISTORICAL_REPLAY_FIXTURES:
        brief = str(fixture["brief"])
        benchmark_ranking = rank_reference_summaries(brief, summaries)
        production_grounding = load_reference_grounding(
            brief,
            corpus_root=corpus_root,
            limit=top_k,
        )
        direct_ranking = rank_reference_summaries(brief, summaries)
        benchmark_top_k = [item["reference_id"] for item in benchmark_ranking[:top_k]]
        production_top_k = list(production_grounding.reference_ids)
        direct_top_k = [item["reference_id"] for item in direct_ranking[:top_k]]
        replay_inputs_equal = benchmark_top_k == production_top_k == direct_top_k
        replay_scores = {
            item["reference_id"]: item["score"]
            for item in benchmark_ranking
            if item["reference_id"] in set(fixture["historical_top_k"]) | set(benchmark_top_k)
        }
        replay_results.append(
            {
                "case_id": fixture["case_id"],
                "character_name": fixture["character_name"],
                "brief_status": fixture["brief_status"],
                "brief": brief,
                "historical_top_k": list(fixture["historical_top_k"]),
                "benchmark_brief_replay_top_k": benchmark_top_k,
                "production_input_replay_top_k": production_top_k,
                "direct_selector_replay_top_k": direct_top_k,
                "historical_match": _historical_match(fixture["historical_top_k"], direct_top_k),
                "historical_match_qualification": "Replay brief is approximate; list equality is not exact historical parity.",
                "rank_differences": _rank_differences(fixture["historical_top_k"], direct_ranking),
                "score_differences": {
                    "historical_scores_available": False,
                    "historical_scores_note": "Historical audit records names only; no historical selector scores were preserved.",
                    "replay_score_by_reference": replay_scores,
                    "benchmark_production_direct_scores_equal": replay_inputs_equal,
                },
                "input_differences": {
                    "historical_exact_brief_available": False,
                    "historical_input_note": "Exact historical brief text was not found in repository docs/tests.",
                    "benchmark_input_type": "raw brief string",
                    "production_input_type": "raw brief string",
                    "direct_selector_input_type": "raw brief string plus corpus summaries",
                    "benchmark_production_input_equal": True,
                    "brief_replay_is_approximate": True,
                },
                "preserved_sources": list(fixture["preserved_sources"]),
                "historical_expected_output_is_evidence_only": True,
            }
        )
    return replay_results


def _classify(summary: Mapping[str, Any], order_test: Mapping[str, Any], coverage: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons = []
    if order_test["result"] == "CORPUS_ORDER_DEPENDENT":
        reasons.append("corpus iteration order changes the ranking")
    if float(summary["selection_concentration"]["hhi"]) >= 0.25:
        reasons.append("top-k selections are highly concentrated")
    if int(summary["unique_selected"]) < 7:
        reasons.append("fewer than seven references appear in selected top-k slots")
    not_represented = sum(item["status"] == "NOT REPRESENTED" for item in coverage.values())
    if not_represented >= 3:
        reasons.append("several requested semantic dimensions have no selector-visible corpus representation")
    if int(summary["counterfactual_sensitivity"]["changed_candidate_count"]) > 0:
        reasons.append("at least one counterfactual changes scores or ranks")
    if order_test["result"] == "CORPUS_ORDER_DEPENDENT":
        return "ORDER/TIE_DOMINATED", reasons
    if len(reasons) >= 3:
        return "MULTIPLE_FACTORS", reasons
    if int(summary["unique_selected"]) < 5:
        return "HIGH_CONCENTRATION", reasons
    return "LIMITED_SENSITIVITY", reasons


def run_benchmark(
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    top_k: int = TOP_K,
) -> dict[str, Any]:
    """Run the complete offline benchmark and return deterministic JSON data."""

    if top_k < 1:
        raise ValueError("top_k must be positive")
    corpus_root = Path(corpus_root)
    catalog = load_game_catalog(corpus_root / "_catalog" / "games.yaml")
    manifest = load_corpus_manifest(corpus_root / "_catalog" / "corpus_manifest.yaml")
    repository = CharacterReferenceRepository(corpus_root, catalog=catalog)
    references = repository.list_all()
    summaries = [_reference_summary(reference) for reference in references]
    summaries_by_id = {str(item["reference_id"]): item for item in summaries}
    feature_profiles = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in references
    }

    cases = benchmark_cases()
    case_results = [_run_case(case, summaries, top_k, feature_profiles) for case in cases]
    result_by_id = {str(item["brief_id"]): item for item in case_results}
    selected_slots = [
        reference_id
        for case in case_results
        for reference_id in case["selected_references"]
    ]
    top1 = [str(case["full_ranking"][0]["reference_id"]) for case in case_results]
    broad_results = case_results[:12]
    overlaps = [
        _jaccard(left["selected_references"], right["selected_references"])
        for left, right in combinations(broad_results, 2)
    ]

    contrast_results = []
    for pair in CONTRAST_PAIRS:
        before = result_by_id[pair["before_brief_id"]]
        after = result_by_id[pair["after_brief_id"]]
        contrast_results.append(
            {
                **pair,
                "before": before,
                "after": after,
                "delta": _ranking_delta(before, after),
            }
        )

    counterfactual_results = []
    for pair in COUNTERFACTUAL_PAIRS:
        before_case = _case(pair["pair_id"] + "-before", pair["dimension"], pair["before"], (pair["dimension"],))
        after_case = _case(pair["pair_id"] + "-after", pair["dimension"], pair["after"], (pair["dimension"],))
        before = _run_case(before_case, summaries, top_k, feature_profiles)
        after = _run_case(after_case, summaries, top_k, feature_profiles)
        counterfactual_results.append(
            {
                **pair,
                "before_result": before,
                "after_result": after,
                "delta": _ranking_delta(before, after),
            }
        )

    counterfactual_changed = sum(
        item["delta"]["changed_candidate_count"] for item in counterfactual_results
    )
    counterfactual_rank_delta = round(
        sum(item["delta"]["mean_absolute_rank_delta"] for item in counterfactual_results)
        / len(counterfactual_results),
        6,
    )
    summary = {
        "top_1_frequency": _frequency(top1),
        "top_k_frequency": _frequency(selected_slots),
        "unique_selected": len(set(selected_slots)),
        "selection_concentration": {
            "metric": "HHI = sum((reference selected top-k slots / all selected slots)^2)",
            "hhi": _hhi(selected_slots),
        },
        "average_top_k_overlap": round(sum(overlaps) / len(overlaps), 6) if overlaps else 0.0,
        "overlap_metric": "Jaccard(selected top-k sets) across all pairs of the 12 broad cases",
        "counterfactual_sensitivity": {
            "pair_count": len(counterfactual_results),
            "changed_candidate_count": counterfactual_changed,
            "average_mean_absolute_rank_delta": counterfactual_rank_delta,
        },
        "stability": {
            "all_cases_stable": all(case["stable_on_repeat"] for case in case_results),
            "unstable_case_ids": [case["brief_id"] for case in case_results if not case["stable_on_repeat"]],
        },
        "source_concentration": {
            "frequency": _source_frequencies(case_results, summaries_by_id),
            "hhi": _hhi(
                [
                    str(summaries_by_id[reference_id]["game_id"])
                    for case in case_results
                    for reference_id in case["selected_references"]
                ]
            ),
        },
        "repeated_trio": {
            name: {
                "top_1": _frequency(top1).get(reference_id, 0),
                "top_k": _frequency(selected_slots).get(reference_id, 0),
            }
            for name, reference_id in {
                "Furina": "genshin-impact:furina",
                "Keqing": "genshin-impact:keqing",
                "Nahida": "genshin-impact:nahida",
            }.items()
        },
    }
    order_test = _corpus_order_test(cases[0]["brief"], summaries, top_k)
    coverage = _coverage(summaries)
    diagnostic_coverage = feature_coverage(
        [extract_brief_features(str(case["brief"])) for case in cases],
        [feature_profiles[reference_id] for reference_id in sorted(feature_profiles)],
    )
    classification, classification_reasons = _classify(summary, order_test, coverage)
    historical_replays = run_historical_replays(corpus_root=corpus_root, top_k=top_k)

    review_packet = {
        "status": "PENDING_MIMO_REVIEW",
        "instruction": "Human/model review only; null values are intentional and are not machine relevance labels.",
        "rubric": {
            "role_relevance": [0, 1, 2],
            "ability_fantasy_relevance": [0, 1, 2],
            "personality_hook_relevance": [0, 1, 2],
            "life_identity_relevance": [0, 1, 2],
            "redundancy": ["LOW", "MEDIUM", "HIGH"],
            "copy_risk": ["LOW", "MEDIUM", "HIGH"],
        },
        "cases": [
            {
                "brief_id": case["brief_id"],
                "selected_references": case["selected_references"],
                "evaluation": {
                    "role_relevance": None,
                    "ability_fantasy_relevance": None,
                    "personality_hook_relevance": None,
                    "life_identity_relevance": None,
                    "redundancy": None,
                    "copy_risk": None,
                },
            }
            for case in case_results
        ],
    }

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "corpus_version": manifest.corpus_version,
        "selector": {
            "entry_point": "agents.official_character_authoring.load_reference_grounding",
            "candidate_count": len(summaries),
            "top_k": top_k,
            "scoring": "sum(1 for brief token present in tokenized JSON reference summary)",
            "score_normalization": "none",
            "candidate_filtering": "none",
            "tie_breaking": "ascending reference_id after descending total score",
            "component_scores_available": False,
            "diagnostic_feature_scoring": "disabled; feature overlap is reported only",
            "production_behavior_changed": False,
        },
        "corpus_audit": _corpus_audit(summaries),
        "corpus_coverage": coverage,
        "diagnostic_coverage": diagnostic_coverage,
        "cases": case_results,
        "contrast_pairs": contrast_results,
        "counterfactuals": counterfactual_results,
        "corpus_order_test": order_test,
        "production_path": {
            "entry_point": "agents.official_character_authoring.main -> make_demo -> load_reference_grounding",
            "invocation_timing": "once before CharacterGenerationAgent construction and before generation",
            "input_object": "request.brief (raw str); hard_constraints, soft_preferences, and other request fields are not passed",
            "feature_extraction": "load_reference_grounding tokenizes the raw brief and JSON summaries",
            "reference_call_count_cli": 1,
            "live_model_dependency": False,
            "tool_loop_dependency": False,
            "top_k": top_k,
            "audit_path": "ReferenceGrounding.selected -> CharacterGenerationRuntimeView.reference_context -> CharacterGenerationAudit.reference_ids -> OfficialCharacterAuthoringRun",
            "selected_reference_semantics": "final deterministic pre-generation top-k inserted into generation context and mirrored in generation audit",
        },
        "benchmark_path": {
            "entry_point": "agents.reference_selection_benchmark.main -> run_benchmark",
            "input_object": "case brief string plus repository summaries",
            "feature_extraction": "same _tokens and rank_reference_summaries implementation",
            "top_k": top_k,
            "shared_production_function": True,
            "differences_from_production_path": [
                "benchmark loads summaries once and calls the diagnostic ranking helper directly; production wraps it in load_reference_grounding",
                "benchmark matrix cases are synthetic; exact historical briefs are unavailable",
            ],
            "same_selector_implementation": True,
            "same_effective_input_for_same_brief": True,
        },
        "historical_replays": historical_replays,
        "parity_classification": {
            "classification": "HISTORICAL_CASE_DIFFERENCE",
            "same_selector_implementation": True,
            "same_effective_selector_input_for_same_brief": True,
            "historical_exact_brief_inputs_available": False,
            "model_or_tool_loop_influence_on_selection": False,
            "audit_semantics_match": True,
            "benchmark_scope": "deterministic pre-generation selector quality",
            "end_to_end_live_retrieval_scope": "same selection stage; generation itself remains out of scope",
            "recommendation": "FREEZE_V0.4_THEN_EXPAND_CORPUS",
        },
        "summary": summary,
        "classification": classification,
        "classification_reasons": classification_reasons,
        "review_packet": review_packet,
    }


def render_text(result: Mapping[str, Any], *, detailed: bool = False) -> str:
    lines = ["REFERENCE SELECTION BENCHMARK v0.4", "=" * 34, ""]
    for case in result["cases"]:
        lines.extend(
            [
                f"Case: {case['brief_id']}",
                f"Brief summary: {case['brief']}",
                "Selected:",
                *[f"{index}. {reference_id}" for index, reference_id in enumerate(case["selected_references"], 1)],
            ]
        )
        if detailed:
            lines.append("Full ranking:")
            lines.extend(
                f"{item['rank']}. {item['character_name']} ({item['reference_id']}) — {item['score']} — {item['source_game']}"
                for item in case["full_ranking"]
            )
            lines.append(f"Ranking notes: ties={case['tie_groups']}; score gaps={case['score_gaps']}")
        lines.append("")
    summary = result["summary"]
    lines.extend(
        [
            "SUMMARY",
            "-------",
            f"Top-1 frequency: {summary['top_1_frequency']}",
            f"Top-k frequency: {summary['top_k_frequency']}",
            f"Unique selected: {summary['unique_selected']}",
            f"Concentration: {summary['selection_concentration']}",
            f"Average overlap: {summary['average_top_k_overlap']}",
            f"Contrast-pair sensitivity: {[item['delta']['changed_candidate_count'] for item in result['contrast_pairs']]}",
            f"Counterfactual sensitivity: {summary['counterfactual_sensitivity']}",
            f"Source concentration: {summary['source_concentration']}",
            f"Repeated trio: {summary['repeated_trio']}",
            f"Stability: {summary['stability']}",
            f"Potential collapse indicators: {result['classification_reasons']}",
            f"Classification: {result['classification']}",
            f"Corpus-order test: {result['corpus_order_test']['result']}",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline Reference Selection Quality Benchmark v0.4")
    parser.add_argument("--json", action="store_true", help="write machine-readable JSON to stdout")
    parser.add_argument("--json-file", type=Path, help="also write deterministic JSON to this path")
    parser.add_argument("--detailed", action="store_true", help="include full rankings in text output")
    args = parser.parse_args(argv)
    result = run_benchmark()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_file:
        args.json_file.parent.mkdir(parents=True, exist_ok=True)
        args.json_file.write_text(payload, encoding="utf-8")
    print(payload if args.json else render_text(result, detailed=args.detailed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
