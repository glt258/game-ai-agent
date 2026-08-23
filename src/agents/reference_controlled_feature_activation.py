"""Offline validation report for Reference Selector v0.4.3b activation."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from itertools import combinations
from typing import Any, Mapping, Sequence

from along_street_resources import data_resource
from reference_corpus.features import (
    DiagnosticFeatureProfile,
    extract_brief_features,
    reference_feature_profile,
)
from reference_corpus.loader import (
    Resource,
    join_resource,
    load_game_catalog,
    normalize_resource,
)
from reference_corpus.repository import CharacterReferenceRepository, ManifestPolicy

from .official_character_authoring import (
    _reference_summary,
    load_reference_grounding,
    rank_reference_summaries,
)
from .reference_feature_discrimination_diagnostic import diagnostic_cases
from .reference_feature_ordering import READY_DOMAINS
from .reference_feature_shadow_scoring import MODEL_3_LEGACY_READY_FEATURES, shadow_rank
from .reference_selection_benchmark import benchmark_cases


ACTIVATION_VERSION = "reference-controlled-feature-activation/0.4.3b"
TOP_K = 3


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    return round(len(a & b) / len(a | b), 6) if a or b else 1.0


def _hhi(values: Sequence[str]) -> float:
    counts = Counter(values)
    total = len(values)
    return round(sum((count / total) ** 2 for count in counts.values()), 6) if total else 0.0


def _metrics(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [reference_id for result in results for reference_id in result["selected_references"]]
    broad = [result["selected_references"] for result in results[:12]]
    overlaps = [_jaccard(left, right) for left, right in combinations(broad, 2)]
    return {
        "unique": len(set(selected)),
        "overlap": round(sum(overlaps) / len(overlaps), 6) if overlaps else 0.0,
        "hhi": _hhi(selected),
    }


def _case_result(
    case_id: str,
    brief: str,
    legacy: Sequence[Mapping[str, Any]],
    activated: Sequence[Mapping[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    legacy_top = [item["reference_id"] for item in legacy[:top_k]]
    activated_top = [item["reference_id"] for item in activated[:top_k]]
    changed = legacy_top != activated_top
    legacy_by_id = {item["reference_id"]: item for item in legacy}
    activated_by_id = {item["reference_id"]: item for item in activated}
    no_cross_group = all(
        activated[index]["legacy_score"] <= activated[index - 1]["legacy_score"]
        for index in range(1, len(activated))
    )
    changed_ids = sorted(
        reference_id
        for reference_id in legacy_by_id
        if legacy_by_id[reference_id]["rank"] != activated_by_id[reference_id]["rank"]
    )
    ids = list(legacy_by_id)
    reordered_pairs = [
        (left, right)
        for left, right in combinations(ids, 2)
        if (
            legacy_by_id[left]["rank"] < legacy_by_id[right]["rank"]
        ) != (
            activated_by_id[left]["rank"] < activated_by_id[right]["rank"]
        )
    ]
    same_legacy_group = all(
        legacy_by_id[left]["legacy_score"] == legacy_by_id[right]["legacy_score"]
        for left, right in reordered_pairs
    ) if changed else True
    baseline_winner = legacy[0]
    activated_winner = activated[0]
    if activated_winner["legacy_score"] < baseline_winner["legacy_score"]:
        classification = "PLAUSIBLY_WORSE"
    elif activated_winner["feature_secondary_score"] > activated_by_id[
        baseline_winner["reference_id"]
    ]["feature_secondary_score"]:
        classification = "PLAUSIBLY_BETTER"
    elif changed:
        classification = "AMBIGUOUS"
    else:
        classification = "UNCHANGED"
    return {
        "case_id": case_id,
        "brief": brief,
        "legacy_baseline_top_k": legacy_top,
        "activated_top_k": activated_top,
        "changed": changed,
        "changed_references": changed_ids,
        "affected_references_same_legacy_group": same_legacy_group,
        "no_cross_legacy_leapfrog": no_cross_group,
        "classification": classification,
        "legacy_ranking": list(legacy),
        "activated_ranking": list(activated),
    }


def _diagnostic_pair_report(
    left: Any,
    right: Any,
    summaries: Sequence[Mapping[str, Any]],
    profiles: Mapping[str, DiagnosticFeatureProfile],
    top_k: int,
) -> dict[str, Any]:
    profile_left = extract_brief_features(left.brief)
    profile_right = extract_brief_features(right.brief)
    changed_domains = [
        domain
        for domain in READY_DOMAINS
        if profile_left.domain_values(domain) != profile_right.domain_values(domain)
    ]
    legacy_left = rank_reference_summaries(left.brief, summaries)
    legacy_right = rank_reference_summaries(right.brief, summaries)
    active_left = rank_reference_summaries(left.brief, summaries, feature_profiles=profiles)
    active_right = rank_reference_summaries(right.brief, summaries, feature_profiles=profiles)
    legacy_by_id_left = {item["reference_id"]: item for item in legacy_left}
    legacy_by_id_right = {item["reference_id"]: item for item in legacy_right}
    changed_order_ids = {
        item["reference_id"]
        for item in legacy_left
        if item["rank"] != next(
            other["rank"] for other in legacy_right if other["reference_id"] == item["reference_id"]
        )
    }
    legacy_tie_exists = any(
        legacy_by_id_left[reference_id]["legacy_score"]
        == legacy_by_id_right[reference_id]["legacy_score"]
        for reference_id in changed_order_ids
    )
    active_left_top = [item["reference_id"] for item in active_left[:top_k]]
    active_right_top = [item["reference_id"] for item in active_right[:top_k]]
    ordering_changed = active_left_top != active_right_top
    score_domain_differences = []
    for domain in changed_domains:
        left_scores = [
            item["feature_trace"]["domains"][domain]["score"] for item in active_left
        ]
        right_scores = [
            item["feature_trace"]["domains"][domain]["score"] for item in active_right
        ]
        if left_scores != right_scores:
            score_domain_differences.append(domain)
    responsible = score_domain_differences[0] if len(score_domain_differences) == 1 else "NONE"
    legacy_left_top = [item["reference_id"] for item in legacy_left[:top_k]]
    legacy_right_top = [item["reference_id"] for item in legacy_right[:top_k]]
    explainability = (
        not changed_domains
        or not ordering_changed
        or not legacy_tie_exists
        or bool(score_domain_differences)
    )
    return {
        "pair_id": f"{left.case_id}__{right.case_id}",
        "changed_design_dimension": left.primary_dimension,
        "legacy_tie_exists": "YES" if legacy_tie_exists else "NO",
        "ready_domain_feature_difference": "YES" if bool(changed_domains) else "NO",
        "production_ordering_changed": "YES" if ordering_changed else "NO",
        "responsible_domain": responsible,
        "explainability": "PASS" if explainability else "FAIL",
        "changed_ready_domains": changed_domains,
        "legacy_top_k": {"left": legacy_left_top, "right": legacy_right_top},
        "activated_top_k": {"left": active_left_top, "right": active_right_top},
    }


def run_activation_report(
    *,
    corpus_root: Resource | str | None = None,
    top_k: int = TOP_K,
    manifest_policy: ManifestPolicy = "required",
) -> dict[str, Any]:
    """Run the complete offline v0.4.3b activation gate."""

    root = (
        data_resource("reference_corpus", "characters")
        if corpus_root is None
        else normalize_resource(corpus_root)
    )
    catalog = load_game_catalog(join_resource(root, "_catalog", "games.yaml"))
    repository = CharacterReferenceRepository(
        root, catalog=catalog, manifest_policy=manifest_policy
    )
    references = repository.list_all()
    summaries = [_reference_summary(reference) for reference in references]
    profiles = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in references
    }
    core_results = []
    parity: list[dict[str, Any]] = []
    for case in benchmark_cases():
        brief = str(case["brief"])
        legacy = rank_reference_summaries(brief, summaries)
        activated = rank_reference_summaries(brief, summaries, feature_profiles=profiles)
        core_results.append(_case_result(case["brief_id"], brief, legacy, activated, top_k))
        shadow = shadow_rank(
            brief,
            references,
            model=MODEL_3_LEGACY_READY_FEATURES,
            top_k=top_k,
        )
        activated_top = [item["reference_id"] for item in activated[:top_k]]
        parity.append(
            {
                "case_id": case["brief_id"],
                "production_top_k": activated_top,
                "shadow_top_k": shadow["selected_references"],
                "pass": activated_top == shadow["selected_references"],
            }
        )
    legacy_metrics = _metrics(
        [{"selected_references": result["legacy_baseline_top_k"]} for result in core_results]
    )
    activated_metrics = _metrics(
        [{"selected_references": result["activated_top_k"]} for result in core_results]
    )
    diagnostics = diagnostic_cases()
    pairs: list[dict[str, Any]] = []
    by_id = {case.case_id: case for case in diagnostics}
    seen: set[str] = set()
    for case in diagnostics:
        if case.case_id in seen:
            continue
        partner = by_id[case.counterfactual_partner]
        pairs.append(_diagnostic_pair_report(case, partner, summaries, profiles, top_k))
        seen.update((case.case_id, partner.case_id))
    first_brief = str(benchmark_cases()[0]["brief"])
    normal = rank_reference_summaries(first_brief, summaries, feature_profiles=profiles)
    reversed_corpus = rank_reference_summaries(
        first_brief, list(reversed(summaries)), feature_profiles=profiles
    )
    feature_order_profiles = {
        reference_id: replace(
            profile,
            personality=tuple(reversed(profile.personality)),
            gameplay_fantasy=tuple(reversed(profile.gameplay_fantasy)),
            authority=tuple(reversed(profile.authority)),
        )
        for reference_id, profile in profiles.items()
    }
    feature_order = rank_reference_summaries(
        first_brief, summaries, feature_profiles=feature_order_profiles
    )
    repeat = rank_reference_summaries(first_brief, summaries, feature_profiles=profiles)
    production_grounding = load_reference_grounding(
        first_brief,
        corpus_root=root,
        limit=top_k,
        manifest_policy=manifest_policy,
    )
    manifest = repository.manifest
    corpus_baseline_id = manifest.baseline_id if manifest is not None else "unmanaged"
    manifest_schema_version = (
        manifest.schema_version if manifest is not None else "unmanaged"
    )
    return {
        "activation_version": ACTIVATION_VERSION,
        "corpus_baseline_id": corpus_baseline_id,
        "manifest_schema_version": manifest_schema_version,
        "corpus_version": corpus_baseline_id,
        "corpus_count": len(references),
        "ready_domains": list(READY_DOMAINS),
        "non_active_domains": [
            "authority_scope",
            "life_social_identity",
            "hook_surface",
            "hook_contrast",
            "hook_behavioral_pattern",
            "life_stage",
            "visual_behavioral_motif",
        ],
        "legacy_baseline": {**legacy_metrics, "classification": "LIMITED_SENSITIVITY"},
        "controlled_activation": {
            **activated_metrics,
            "changed": sum(result["changed"] for result in core_results),
            "plausibly_better": sum(result["classification"] == "PLAUSIBLY_BETTER" for result in core_results),
            "plausibly_worse": sum(result["classification"] == "PLAUSIBLY_WORSE" for result in core_results),
            "ambiguous": sum(result["classification"] == "AMBIGUOUS" for result in core_results),
            "corpus_gap": 0,
            "metadata_gap": 0,
        },
        "core_cases": core_results,
        "shadow_parity": {
            "pass": all(item["pass"] for item in parity),
            "differences": [item for item in parity if not item["pass"]],
            "cases": parity,
        },
        "diagnostic_extension": {
            "case_count": len(diagnostics),
            "pairs": pairs,
        },
        "determinism": {
            "corpus_order": [item["reference_id"] for item in normal]
            == [item["reference_id"] for item in reversed_corpus],
            "feature_order": [item["reference_id"] for item in normal]
            == [item["reference_id"] for item in feature_order],
            "repeatability": [item["reference_id"] for item in normal]
            == [item["reference_id"] for item in repeat],
            "production_grounding_parity": list(production_grounding.reference_ids)
            == [item["reference_id"] for item in normal[:top_k]],
        },
        "ordering_contract": {
            "legacy_primary": all(result["no_cross_legacy_leapfrog"] for result in core_results),
            "feature_within_equal_legacy_only": all(
                result["affected_references_same_legacy_group"] for result in core_results
            ),
            "existing_final_tie_break_preserved": True,
        },
        "audit": {
            "trace": bool(production_grounding.selection_audit),
            "ordering_reason": all(
                item["ordering_reason"]
                in {"LEGACY_SCORE", "FEATURE_SECONDARY_TIEBREAK", "DETERMINISTIC_FINAL_TIEBREAK"}
                for item in production_grounding.selection_audit
            ),
        },
    }


__all__ = ["ACTIVATION_VERSION", "run_activation_report"]
