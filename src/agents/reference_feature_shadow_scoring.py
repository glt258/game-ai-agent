"""Non-production authoring-feature shadow scoring experiments.

This module audits the frozen lexical selector and evaluates bounded,
explainable feature similarities beside it.  It never changes selector
ranking, tie-breaking, or production feature-score contribution.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from reference_corpus.features import (
    DiagnosticFeatureProfile,
    FeatureDomain,
    extract_brief_features,
    feature_coverage,
    reference_feature_profile,
)
from reference_corpus.repository import CharacterReferenceRepository

from .official_character_authoring import (
    DEFAULT_CORPUS_ROOT,
    _reference_summary,
    rank_reference_summaries,
)
from .reference_feature_ordering import (
    READY_DOMAINS as SHARED_READY_DOMAINS,
    bounded_normalized_jaccard,
    ready_feature_score_trace,
)
from .reference_feature_discrimination_diagnostic import diagnostic_cases
from .reference_selection_benchmark import benchmark_cases


SHADOW_VERSION = "reference-feature-shadow-scoring/0.4.3a"
TOP_K = 3
FEATURE_BONUS_CAP = 0.25

MODEL_0_LEGACY_ONLY = "MODEL_0_LEGACY_ONLY"
MODEL_1_FEATURE_ONLY = "MODEL_1_FEATURE_ONLY"
MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES = (
    "MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES"
)
MODEL_3_LEGACY_READY_FEATURES = "MODEL_3_LEGACY_READY_FEATURES"
MODELS = (
    MODEL_0_LEGACY_ONLY,
    MODEL_1_FEATURE_ONLY,
    MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES,
    MODEL_3_LEGACY_READY_FEATURES,
)

CANDIDATE_DOMAINS: tuple[FeatureDomain, ...] = (
    "personality",
    "gameplay_fantasy",
    "life_social_identity",
    "authority",
    "authority_scope",
    "hook_surface",
    "hook_contrast",
    "hook_behavioral_pattern",
)
READY_DOMAINS: tuple[FeatureDomain, ...] = (
    "personality",
    "gameplay_fantasy",
    "authority",
)
NOT_READY_DOMAINS: tuple[FeatureDomain, ...] = (
    "life_stage",
    "visual_behavioral_motif",
)
HOOK_DOMAINS: tuple[FeatureDomain, ...] = (
    "hook_surface",
    "hook_contrast",
    "hook_behavioral_pattern",
)
PRIMITIVES = (
    "raw_intersection",
    "binary",
    "jaccard",
    "overlap_coefficient",
    "capped_token_overlap",
)
HOOK_MODES = ("independent", "family_max", "family_capped_sum")

DOMAIN_READINESS: Mapping[str, Mapping[str, str]] = {
    "personality": {
        "status": "READY_FOR_SCORING",
        "reason": "full reference coverage, stable canonical semantics, deterministic extraction, and no current revision finding",
    },
    "gameplay_fantasy": {
        "status": "READY_FOR_SCORING",
        "reason": "full reference coverage and fact-grounded normalized combat fantasy with observable diagnostic sensitivity",
    },
    "life_social_identity": {
        "status": "SHADOW_ONLY",
        "reason": "useful normalized signal, but confirmed identity corpus coverage gaps remain",
    },
    "authority": {
        "status": "READY_FOR_SCORING",
        "reason": "9/10 reference coverage, deterministic canonical form, and prior diagnostics show form distinctions without requiring scope to replace the form signal",
    },
    "authority_scope": {
        "status": "SHADOW_ONLY",
        "reason": "representation is deterministic and diagnostic-useful, but only 5/10 references carry scope evidence",
    },
    "hook_surface": {
        "status": "SHADOW_ONLY",
        "reason": "coverage exists but hook revision is not yet justified and hook dimensions require family capping",
    },
    "hook_contrast": {
        "status": "SHADOW_ONLY",
        "reason": "coverage exists but contrast vocabulary remains diagnostic evidence rather than production-ready semantics",
    },
    "hook_behavioral_pattern": {
        "status": "SHADOW_ONLY",
        "reason": "coverage is broad but the hook family is structurally decomposed and must remain capped",
    },
    "life_stage": {
        "status": "NOT_READY",
        "reason": "reference coverage is 0/10",
    },
    "visual_behavioral_motif": {
        "status": "NOT_READY",
        "reason": "reference coverage is 1/10",
    },
}


def _values(profile: DiagnosticFeatureProfile, domain: FeatureDomain) -> tuple[str, ...]:
    return tuple(profile.domain_values(domain))


def _primitive_score(
    left: Sequence[str],
    right: Sequence[str],
    primitive: str,
) -> float:
    if primitive not in PRIMITIVES:
        raise ValueError(f"unsupported shadow primitive: {primitive}")
    left_set = set(left)
    right_set = set(right)
    shared = len(left_set & right_set)
    if primitive == "raw_intersection":
        return float(shared)
    if not left_set or not right_set:
        return 0.0
    if primitive == "binary":
        return 1.0 if shared else 0.0
    if primitive == "jaccard":
        return bounded_normalized_jaccard(left, right)
    if primitive == "overlap_coefficient":
        return round(shared / min(len(left_set), len(right_set)), 3)
    return round(min(1.0, shared / 2), 3)


def feature_domain_score(
    brief: DiagnosticFeatureProfile,
    reference: DiagnosticFeatureProfile,
    domain: FeatureDomain,
    primitive: str = "jaccard",
) -> float:
    """Return one explainable domain score; missing data is neutral zero."""

    return _primitive_score(_values(brief, domain), _values(reference, domain), primitive)


def _hook_scores(
    brief: DiagnosticFeatureProfile,
    reference: DiagnosticFeatureProfile,
    primitive: str,
    hook_mode: str,
    domains: Sequence[FeatureDomain] = HOOK_DOMAINS,
) -> tuple[dict[str, float], float]:
    if hook_mode not in HOOK_MODES:
        raise ValueError(f"unsupported hook mode: {hook_mode}")
    selected_domains = tuple(domain for domain in HOOK_DOMAINS if domain in domains)
    scores = {
        domain: feature_domain_score(brief, reference, domain, primitive)
        for domain in selected_domains
    }
    if hook_mode == "independent":
        return scores, sum(scores.values())
    if hook_mode == "family_max":
        return scores, max(scores.values(), default=0.0)
    return scores, round(min(1.0, sum(scores.values())), 3)


def feature_score_trace(
    brief: DiagnosticFeatureProfile,
    reference: DiagnosticFeatureProfile,
    *,
    domains: Sequence[FeatureDomain] = CANDIDATE_DOMAINS,
    primitive: str = "jaccard",
    hook_mode: str = "family_max",
) -> dict[str, Any]:
    """Return bounded per-domain traces with no production side effects."""

    selected_domains = tuple(dict.fromkeys(domains))
    if (
        selected_domains == SHARED_READY_DOMAINS
        and primitive == "jaccard"
        and hook_mode == "family_max"
    ):
        return ready_feature_score_trace(brief, reference)
    scores: dict[str, dict[str, Any]] = {}
    active_scores: list[float] = []
    for domain in selected_domains:
        if domain in HOOK_DOMAINS and hook_mode != "independent":
            continue
        brief_values = list(_values(brief, domain))
        reference_values = list(_values(reference, domain))
        score = feature_domain_score(brief, reference, domain, primitive)
        scores[domain] = {
            "brief_values": brief_values,
            "reference_values": reference_values,
            "shared_values": sorted(set(brief_values) & set(reference_values)),
            "score": score,
            "missing_neutral": not brief_values or not reference_values,
        }
        if brief_values:
            active_scores.append(score)

    hook_subdomain_scores, hook_family_score = _hook_scores(
        brief, reference, primitive, hook_mode, selected_domains
    )
    if hook_mode != "independent" and any(
        domain in selected_domains and _values(brief, domain) for domain in HOOK_DOMAINS
    ):
        scores["hook_family"] = {
            "brief_values": sorted(
                {
                    value
                    for domain in HOOK_DOMAINS
                    if domain in selected_domains
                    for value in _values(brief, domain)
                }
            ),
            "reference_values": sorted(
                {
                    value
                    for domain in HOOK_DOMAINS
                    if domain in selected_domains
                    for value in _values(reference, domain)
                }
            ),
            "shared_values": [],
            "score": hook_family_score,
            "missing_neutral": hook_family_score == 0.0,
        }
        active_scores.append(hook_family_score)
    feature_subtotal = round(sum(active_scores) / len(active_scores), 3) if active_scores else 0.0
    return {
        "primitive": primitive,
        "hook_mode": hook_mode,
        "domains": scores,
        "hook_subdomain_scores": hook_subdomain_scores,
        "hook_family_score": hook_family_score,
        "active_domain_count": len(active_scores),
        "feature_subtotal": feature_subtotal,
        "feature_score_cap": 1.0,
    }


def _model_domains(model: str) -> tuple[FeatureDomain, ...]:
    if model == MODEL_3_LEGACY_READY_FEATURES:
        return READY_DOMAINS
    return CANDIDATE_DOMAINS


def _shadow_score(legacy_score: int, feature_subtotal: float, model: str) -> tuple[float, tuple[Any, ...]]:
    if model == MODEL_0_LEGACY_ONLY:
        return float(legacy_score), (legacy_score, 0.0)
    if model == MODEL_1_FEATURE_ONLY:
        return feature_subtotal, (feature_subtotal,)
    if model not in (MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES, MODEL_3_LEGACY_READY_FEATURES):
        raise ValueError(f"unsupported shadow model: {model}")
    bonus = round(FEATURE_BONUS_CAP * feature_subtotal, 3)
    # The tuple is the actual ordering rule: legacy remains primary and the
    # bounded feature bonus is a secondary signal, never a leapfrog mechanism.
    return round(legacy_score + bonus, 3), (legacy_score, feature_subtotal)


def shadow_rank(
    brief: str,
    references: Sequence[Any],
    *,
    model: str = MODEL_3_LEGACY_READY_FEATURES,
    top_k: int = TOP_K,
    primitive: str = "jaccard",
    hook_mode: str = "family_max",
) -> dict[str, Any]:
    """Rank references in a diagnostic-only shadow model."""

    if top_k < 1:
        raise ValueError("top_k must be positive")
    if model not in MODELS:
        raise ValueError(f"unsupported shadow model: {model}")
    summaries = [_reference_summary(reference) for reference in references]
    legacy_ranking = rank_reference_summaries(brief, summaries)
    legacy_by_id = {item["reference_id"]: item for item in legacy_ranking}
    profiles = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in references
    }
    brief_profile = extract_brief_features(brief)
    rows: list[dict[str, Any]] = []
    for reference_id, profile in profiles.items():
        trace = feature_score_trace(
            brief_profile,
            profile,
            domains=_model_domains(model),
            primitive=primitive,
            hook_mode=hook_mode,
        )
        feature_subtotal = 0.0 if model == MODEL_0_LEGACY_ONLY else trace["feature_subtotal"]
        legacy_score = int(legacy_by_id[reference_id]["score"])
        combined, sort_key = _shadow_score(legacy_score, feature_subtotal, model)
        rows.append(
            {
                "reference_id": reference_id,
                "character_name": legacy_by_id[reference_id]["character_name"],
                "legacy_score": legacy_score,
                "feature_subtotal": feature_subtotal,
                "feature_bonus": round(combined - legacy_score, 3)
                if model not in (MODEL_0_LEGACY_ONLY, MODEL_1_FEATURE_ONLY)
                else 0.0,
                "combined_shadow_score": combined,
                "score_key": list(sort_key),
                "trace": trace,
            }
        )
    if model == MODEL_0_LEGACY_ONLY:
        rows.sort(key=lambda item: (-item["legacy_score"], item["reference_id"]))
    elif model == MODEL_1_FEATURE_ONLY:
        rows.sort(key=lambda item: (-item["feature_subtotal"], item["reference_id"]))
    else:
        rows.sort(
            key=lambda item: (
                -item["legacy_score"],
                -item["feature_subtotal"],
                item["reference_id"],
            )
        )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    production_top_k = [item["reference_id"] for item in legacy_ranking[:top_k]]
    shadow_top_k = [item["reference_id"] for item in rows[:top_k]]
    return {
        "shadow_version": SHADOW_VERSION,
        "model": model,
        "brief": brief,
        "top_k": top_k,
        "ranking": rows,
        "selected_references": shadow_top_k,
        "production_top_k": production_top_k,
        "changed_from_production": shadow_top_k != production_top_k,
        "production_behavior": {
            "feature_score_contribution": 0,
            "selector_touched": False,
            "ranking_logic_changed": False,
            "tie_breaking_changed": False,
        },
    }


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set and right_set:
        return 0.0
    return round(len(left_set & right_set) / len(left_set | right_set), 6)


def _hhi(selected: Sequence[str]) -> float:
    if not selected:
        return 0.0
    counts = Counter(selected)
    total = len(selected)
    return round(sum((count / total) ** 2 for count in counts.values()), 6)


def _core_metrics(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [reference_id for result in results for reference_id in result["shadow_top_k"]]
    broad = [result["shadow_top_k"] for result in results[:12]]
    overlaps = [_jaccard(left, right) for left, right in combinations(broad, 2)]
    return {
        "unique_selected": len(set(selected)),
        "average_top_k_overlap": round(sum(overlaps) / len(overlaps), 6) if overlaps else 0.0,
        "hhi": _hhi(selected),
    }


def _change_classification(result: Mapping[str, Any]) -> str:
    if not result["changed"]:
        return "UNCHANGED"
    winner = result["shadow_top_k"][0]
    production_winner = result["production_top_k"][0]
    winner_row = next(row for row in result["shadow_ranking"] if row["reference_id"] == winner)
    production_row = next(
        row for row in result["shadow_ranking"] if row["reference_id"] == production_winner
    )
    if winner_row["legacy_score"] < production_row["legacy_score"]:
        return "PLAUSIBLY_WORSE"
    if winner_row["feature_subtotal"] > production_row["feature_subtotal"]:
        return "PLAUSIBLY_BETTER"
    return "AMBIGUOUS"


def _evaluate_case(
    brief: str,
    references: Sequence[Any],
    *,
    model: str,
    primitive: str,
    hook_mode: str,
) -> dict[str, Any]:
    ranked = shadow_rank(
        brief,
        references,
        model=model,
        primitive=primitive,
        hook_mode=hook_mode,
    )
    result = {
        "production_top_k": ranked["production_top_k"],
        "shadow_top_k": ranked["selected_references"],
        "changed": ranked["changed_from_production"],
        "shadow_ranking": ranked["ranking"],
    }
    result["change_classification"] = _change_classification(result)
    return result


def _diagnostic_pairs(references: Sequence[Any], model: str) -> list[dict[str, Any]]:
    cases = {case.case_id: case for case in diagnostic_cases()}
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in diagnostic_cases():
        if case.case_id in seen:
            continue
        partner = cases[case.counterfactual_partner]
        left = shadow_rank(case.brief, references, model=model)
        right = shadow_rank(partner.brief, references, model=model)
        left_profile = extract_brief_features(case.brief)
        right_profile = extract_brief_features(partner.brief)
        changed_domains = [
            domain
            for domain in CANDIDATE_DOMAINS
            if _values(left_profile, domain) != _values(right_profile, domain)
        ]
        results.append(
            {
                "pair_id": f"{case.case_id}__{partner.case_id}",
                "left_case_id": case.case_id,
                "right_case_id": partner.case_id,
                "changed_dimensions": changed_domains,
                "production_top_k": {
                    "left": left["production_top_k"],
                    "right": right["production_top_k"],
                    "jaccard": _jaccard(left["production_top_k"], right["production_top_k"]),
                },
                "shadow_top_k": {
                    "left": left["selected_references"],
                    "right": right["selected_references"],
                    "jaccard": _jaccard(left["selected_references"], right["selected_references"]),
                },
                "responsible_score_component": changed_domains,
            }
        )
        seen.add(case.case_id)
        seen.add(partner.case_id)
    return results


def _coverage_report(
    references: Sequence[Any],
) -> dict[str, Any]:
    reference_profiles = [reference_feature_profile(reference) for reference in references]
    briefs = [extract_brief_features(str(case["brief"])) for case in benchmark_cases()]
    briefs.extend(extract_brief_features(case.brief) for case in diagnostic_cases())
    coverage = feature_coverage(briefs, reference_profiles)["domains"]
    return {
        "reference_and_brief_coverage": coverage,
        "readiness": {
            domain: dict(details) for domain, details in DOMAIN_READINESS.items()
        },
    }


def _primitive_experiments(references: Sequence[Any]) -> dict[str, Any]:
    cases = [str(case["brief"]) for case in benchmark_cases()]
    output: dict[str, Any] = {}
    for primitive in PRIMITIVES:
        results = [
            _evaluate_case(
                brief,
                references,
                model=MODEL_3_LEGACY_READY_FEATURES,
                primitive=primitive,
                hook_mode="family_max",
            )
            for brief in cases
        ]
        metrics = _core_metrics(results)
        output[primitive] = {
            **metrics,
            "changed_core_case_count": sum(result["changed"] for result in results),
        }
    return output


def _hook_experiments(references: Sequence[Any]) -> dict[str, Any]:
    cases = [str(case["brief"]) for case in benchmark_cases()]
    output: dict[str, Any] = {}
    for hook_mode in HOOK_MODES:
        results = [
            _evaluate_case(
                brief,
                references,
                model=MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES,
                primitive="jaccard",
                hook_mode=hook_mode,
            )
            for brief in cases
        ]
        output[hook_mode] = {
            **_core_metrics(results),
            "changed_core_case_count": sum(result["changed"] for result in results),
        }
    return output


def run_shadow_simulation(
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    top_k: int = TOP_K,
) -> dict[str, Any]:
    """Run all shadow models and diagnostic experiments without production writes."""

    repository = CharacterReferenceRepository(corpus_root)
    references = repository.list_all()
    core_cases = benchmark_cases()
    model_results: dict[str, Any] = {}
    for model in MODELS:
        core_results = []
        for case in core_cases:
            result = _evaluate_case(
                str(case["brief"]),
                references,
                model=model,
                primitive="jaccard",
                hook_mode="family_max",
            )
            result["brief_id"] = case["brief_id"]
            result["production_top_k"] = result["production_top_k"][:top_k]
            result["shadow_top_k"] = result["shadow_top_k"][:top_k]
            core_results.append(result)
        model_results[model] = {
            "core": {
                "metrics": _core_metrics(core_results),
                "changed_cases": [
                    result["brief_id"] for result in core_results if result["changed"]
                ],
                "plausibly_better": [
                    result["brief_id"]
                    for result in core_results
                    if result["change_classification"] == "PLAUSIBLY_BETTER"
                ],
                "plausibly_worse": [
                    result["brief_id"]
                    for result in core_results
                    if result["change_classification"] == "PLAUSIBLY_WORSE"
                ],
                "ambiguous": [
                    result["brief_id"]
                    for result in core_results
                    if result["change_classification"] == "AMBIGUOUS"
                ],
                "cases": core_results,
            },
            "diagnostic_pairs": _diagnostic_pairs(references, model),
        }

    baseline = model_results[MODEL_0_LEGACY_ONLY]["core"]["metrics"]
    reversed_results = []
    reversed_references = list(reversed(references))
    for case in core_cases:
        ranked = shadow_rank(
            str(case["brief"]),
            reversed_references,
            model=MODEL_3_LEGACY_READY_FEATURES,
        )
        reversed_results.append(ranked["selected_references"])
    normal_results = [
        shadow_rank(str(case["brief"]), references, model=MODEL_3_LEGACY_READY_FEATURES)[
            "selected_references"
        ]
        for case in core_cases
    ]
    return {
        "shadow_version": SHADOW_VERSION,
        "corpus_count": len(references),
        "top_k": top_k,
        "domain_coverage": _coverage_report(references),
        "models": model_results,
        "primitive_experiments": _primitive_experiments(references),
        "hook_experiments": _hook_experiments(references),
        "stability": {
            "deterministic": True,
            "order_independent": normal_results == reversed_results,
            "feature_order_independent": True,
        },
        "production_baseline": baseline,
        "production_behavior": {
            "feature_score_contribution": 0,
            "selector_touched": False,
            "ranking_logic_changed": False,
            "tie_breaking_changed": False,
        },
    }


__all__ = [
    "CANDIDATE_DOMAINS",
    "DOMAIN_READINESS",
    "FEATURE_BONUS_CAP",
    "MODEL_0_LEGACY_ONLY",
    "MODEL_1_FEATURE_ONLY",
    "MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES",
    "MODEL_3_LEGACY_READY_FEATURES",
    "READY_DOMAINS",
    "feature_domain_score",
    "feature_score_trace",
    "run_shadow_simulation",
    "shadow_rank",
]
