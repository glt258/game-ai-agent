"""Shared v0.4.3a ready-domain feature ordering semantics.

This module contains only the bounded secondary signal approved for the
v0.4.3b controlled activation.  It deliberately has no selector or corpus
dependencies, so the frozen shadow scorer and production selector can share
the exact primitive without importing one another.
"""

from __future__ import annotations

from typing import Any, Sequence

from reference_corpus.features import DiagnosticFeatureProfile


READY_DOMAINS: tuple[str, ...] = (
    "personality",
    "gameplay_fantasy",
    "authority",
)

NON_ACTIVE_DOMAINS: tuple[str, ...] = (
    "authority_scope",
    "life_social_identity",
    "hook_surface",
    "hook_contrast",
    "hook_behavioral_pattern",
    "life_stage",
    "visual_behavioral_motif",
)


def bounded_normalized_jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    """Return the frozen bounded Jaccard score; missing evidence is neutral."""

    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return round(len(left_set & right_set) / len(left_set | right_set), 3)


def ready_feature_score_trace(
    brief: DiagnosticFeatureProfile,
    reference: DiagnosticFeatureProfile,
) -> dict[str, Any]:
    """Return the v0.4.3a ready-domain subtotal and an explainable trace."""

    domains: dict[str, dict[str, Any]] = {}
    active_scores: list[float] = []
    for domain in READY_DOMAINS:
        brief_values = list(brief.domain_values(domain))
        reference_values = list(reference.domain_values(domain))
        score = bounded_normalized_jaccard(brief_values, reference_values)
        domains[domain] = {
            "brief_values": brief_values,
            "reference_values": reference_values,
            "shared_values": sorted(set(brief_values) & set(reference_values)),
            "score": score,
            "missing_neutral": not brief_values or not reference_values,
        }
        if brief_values:
            active_scores.append(score)
    return {
        "primitive": "bounded_normalized_jaccard",
        "domains": domains,
        "active_domain_count": len(active_scores),
        "feature_subtotal": round(sum(active_scores) / len(active_scores), 3)
        if active_scores
        else 0.0,
        "feature_score_cap": 1.0,
        "non_active_domains": list(NON_ACTIVE_DOMAINS),
    }


__all__ = [
    "NON_ACTIVE_DOMAINS",
    "READY_DOMAINS",
    "bounded_normalized_jaccard",
    "ready_feature_score_trace",
]
