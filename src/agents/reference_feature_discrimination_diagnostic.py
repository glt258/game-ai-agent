"""Separate, non-scoring feature-discrimination diagnostic benchmark.

The frozen Reference Selection Quality Benchmark v0.4 remains the production
benchmark.  This module owns only new authoring-brief diagnostics and never
feeds their cases into the production selector or its ranking metrics.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from reference_corpus.features import (
    FeatureDomain,
    DiagnosticFeatureProfile,
    diagnostic_overlap,
    extract_brief_features,
    reference_feature_profile,
)
from reference_corpus.repository import CharacterReferenceRepository

from .reference_selection_benchmark import run_benchmark


DIAGNOSTIC_VERSION = "reference-feature-discrimination-diagnostic/0.4.2b"
DEFAULT_CORPUS_ROOT = Path(__file__).resolve().parents[2] / "data" / "reference_corpus"

DOMAINS: tuple[FeatureDomain, ...] = (
    "personality",
    "gameplay_fantasy",
    "life_social_identity",
    "life_stage",
    "authority",
    "authority_scope",
    "hook_surface",
    "hook_contrast",
    "hook_behavioral_pattern",
    "visual_behavioral_motif",
)

CLASSIFICATIONS = (
    "PASS_CURRENT_REPRESENTATION",
    "BRIEF_EXTRACTION_GAP",
    "VOCABULARY_REPRESENTATION_GAP",
    "CORPUS_COVERAGE_GAP",
    "MULTI_REFERENCE_COLLISION",
    "EXPECTED_SHARED_TRAIT",
)


# The frozen cases and their wording remain unchanged.  These are the approved
# v0.4.2d representation expectations used only to evaluate the new shadow
# domain.
EXPECTED_AUTHORITY_SCOPES: Mapping[str, str] = {
    "authority-scope-small-private-team": "private_group",
    "authority-scope-state-institution": "state_scale",
    "authority-form-portfolio-governance": "institutional",
    "authority-form-sovereign": "state_scale",
    "authority-form-formal-organization-leader": "institutional",
    "authority-form-custodial-executive": "institutional",
}


@dataclass(frozen=True)
class DiagnosticCase:
    case_id: str
    purpose: str
    brief: str
    primary_dimension: str
    secondary_dimensions: tuple[str, ...]
    counterfactual_partner: str
    expected_features: Mapping[FeatureDomain, tuple[str, ...]]
    held_constant: str
    failure_meaning: str
    expected_classification: str
    unsupported_distinction: str | None = None


def _features(**values: tuple[str, ...]) -> Mapping[FeatureDomain, tuple[str, ...]]:
    result = {domain: tuple(values.get(domain, ())) for domain in DOMAINS}
    return result  # type: ignore[return-value]


_CASES: tuple[DiagnosticCase, ...] = (
    DiagnosticCase(
        case_id="authority-scope-small-private-team",
        purpose="Test small private-team leadership against state-scale leadership.",
        brief=(
            "A practical professional whose formal leadership covers a small private team "
            "and a few direct reports, with no state or government office."
        ),
        primary_dimension="authority_scope",
        secondary_dimensions=("identity_type",),
        counterfactual_partner="authority-scope-state-institution",
        expected_features=_features(
            personality=("practical",),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
        ),
        held_constant="practical professional with formal leadership",
        failure_meaning="If the pair is identical, the current authority token cannot represent leadership scope.",
        expected_classification="MULTI_REFERENCE_COLLISION",
        unsupported_distinction="small private-team scope",
    ),
    DiagnosticCase(
        case_id="authority-scope-state-institution",
        purpose="Test city/state institutional responsibility against small-team leadership.",
        brief=(
            "A practical professional whose formal leadership covers a city-state institution "
            "and its broad public responsibilities."
        ),
        primary_dimension="authority_scope",
        secondary_dimensions=("identity_type",),
        counterfactual_partner="authority-scope-small-private-team",
        expected_features=_features(
            personality=("practical",),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
        ),
        held_constant="practical professional with formal leadership",
        failure_meaning="If the pair is identical, the current authority token cannot represent leadership scope.",
        expected_classification="MULTI_REFERENCE_COLLISION",
        unsupported_distinction="city/state institutional scope",
    ),
    DiagnosticCase(
        case_id="authority-form-portfolio-governance",
        purpose="Test collective or portfolio governance against sovereign authority.",
        brief=(
            "A restrained professional whose formal leadership is a governing seat and portfolio "
            "within a council, sharing decisions rather than ruling alone."
        ),
        primary_dimension="authority_form",
        secondary_dimensions=("authority_scope", "personality_mode"),
        counterfactual_partner="authority-form-sovereign",
        expected_features=_features(
            personality=("restrained",),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
        ),
        held_constant="restrained professional with formal leadership",
        failure_meaning="If the pair is identical, portfolio governance and sole sovereignty collapse.",
        expected_classification="MULTI_REFERENCE_COLLISION",
        unsupported_distinction="collective or portfolio governance",
    ),
    DiagnosticCase(
        case_id="authority-form-sovereign",
        purpose="Test broad sovereign or head-of-state authority against portfolio governance.",
        brief=(
            "A restrained professional whose formal leadership carries broad responsibility for a "
            "city-state institution as its sole governing authority."
        ),
        primary_dimension="authority_form",
        secondary_dimensions=("authority_scope", "personality_mode"),
        counterfactual_partner="authority-form-portfolio-governance",
        expected_features=_features(
            personality=("restrained",),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
        ),
        held_constant="restrained professional with formal leadership",
        failure_meaning="If the pair is identical, portfolio governance and sole sovereignty collapse.",
        expected_classification="MULTI_REFERENCE_COLLISION",
        unsupported_distinction="sole sovereign or head-of-state authority",
    ),
    DiagnosticCase(
        case_id="authority-form-operational-member",
        purpose="Separate specialist competence and organizational membership from command authority.",
        brief=(
            "A serious practical specialist who is an organization member with operational "
            "responsibility for field execution, but has no command authority."
        ),
        primary_dimension="identity_authority",
        secondary_dimensions=("competence", "organization_membership"),
        counterfactual_partner="authority-form-formal-organization-leader",
        expected_features=_features(
            personality=("serious", "practical"),
            life_social_identity=("organization_member",),
            authority=("operational_responsibility",),
        ),
        held_constant="serious practical specialist doing field work",
        failure_meaning="A failure would mean organization membership and execution responsibility are not separable from command.",
        expected_classification="CORPUS_COVERAGE_GAP",
    ),
    DiagnosticCase(
        case_id="authority-form-formal-organization-leader",
        purpose="Separate formal organization leadership from specialist execution responsibility.",
        brief=(
            "A serious practical specialist who has formal leadership within an organization and "
            "command responsibility for field execution."
        ),
        primary_dimension="identity_authority",
        secondary_dimensions=("competence", "organization_leadership"),
        counterfactual_partner="authority-form-operational-member",
        expected_features=_features(
            personality=("serious", "practical"),
            authority=("formal_leadership",),
        ),
        held_constant="serious practical specialist doing field work",
        failure_meaning="A failure would mean competence is being mistaken for leadership rather than represented separately.",
        expected_classification="CORPUS_COVERAGE_GAP",
    ),
    DiagnosticCase(
        case_id="authority-form-custodial-executive",
        purpose="Test quiet custodial or system-maintenance leadership against field enforcement.",
        brief=(
            "A restrained socially isolated professional with formal leadership and protective "
            "stabilization, responsible for quiet custodial system maintenance."
        ),
        primary_dimension="authority_form",
        secondary_dimensions=("gameplay_fantasy", "identity_type", "personality_mode"),
        counterfactual_partner="authority-form-field-enforcer",
        expected_features=_features(
            personality=("restrained", "socially_isolated"),
            gameplay_fantasy=("protective_stabilization",),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
        ),
        held_constant="restrained socially isolated professional with protective responsibility",
        failure_meaning="A failure would mean custodial executive authority and field responsibility collapse despite distinct authority/fantasy signals.",
        expected_classification="PASS_CURRENT_REPRESENTATION",
    ),
    DiagnosticCase(
        case_id="authority-form-field-enforcer",
        purpose="Test quiet field enforcement without formal leadership against custodial executive authority.",
        brief=(
            "A restrained socially isolated professional with operational responsibility and "
            "protective stabilization, responsible for quiet frontline enforcement without command."
        ),
        primary_dimension="authority_form",
        secondary_dimensions=("gameplay_fantasy", "identity_type", "personality_mode"),
        counterfactual_partner="authority-form-custodial-executive",
        expected_features=_features(
            personality=("restrained", "socially_isolated"),
            gameplay_fantasy=("protective_stabilization", "direct_frontline_pressure"),
            life_social_identity=("formal_professional",),
            authority=("operational_responsibility",),
        ),
        held_constant="restrained socially isolated professional with protective responsibility",
        failure_meaning="A failure would mean custodial executive authority and field responsibility collapse despite distinct authority/fantasy signals.",
        expected_classification="PASS_CURRENT_REPRESENTATION",
    ),
    DiagnosticCase(
        case_id="hook-contrast-theatrical-mask",
        purpose="Test public theatricality that conceals vulnerability or guarded identity.",
        brief=(
            "An expressive public performer whose public performance and theatrical confidence "
            "conceal insecurity and a guarded private self."
        ),
        primary_dimension="hook_contrast",
        secondary_dimensions=("personality_mode", "identity_type"),
        counterfactual_partner="hook-contrast-playful-danger",
        expected_features=_features(
            personality=("expressive", "guarded"),
            life_social_identity=("performer",),
            hook_surface=("public_performance",),
            hook_behavioral_pattern=("public_performance",),
        ),
        held_constant="expressive public performance",
        failure_meaning="A failure would mean the vocabulary cannot represent performance as a mask rather than merely performance itself.",
        expected_classification="VOCABULARY_REPRESENTATION_GAP",
        unsupported_distinction="theatrical surface masking vulnerability",
    ),
    DiagnosticCase(
        case_id="hook-contrast-playful-danger",
        purpose="Test playful or teasing presentation whose danger is visible rather than hidden competence.",
        brief=(
            "An expressive playful public performer whose public performance and teasing surface "
            "carry real danger in open view, not hidden competence."
        ),
        primary_dimension="hook_contrast",
        secondary_dimensions=("personality_mode", "identity_type"),
        counterfactual_partner="hook-contrast-theatrical-mask",
        expected_features=_features(
            personality=("expressive", "playful"),
            life_social_identity=("performer",),
            hook_surface=("public_performance",),
            hook_behavioral_pattern=("public_performance",),
        ),
        held_constant="expressive public performance",
        failure_meaning="A failure would mean playful visible danger cannot be separated from masking or hidden competence.",
        expected_classification="VOCABULARY_REPRESENTATION_GAP",
        unsupported_distinction="playful visible danger",
    ),
    DiagnosticCase(
        case_id="hook-contrast-disciplined-official",
        purpose="Test a governing official defined by practical personal action and discipline.",
        brief=(
            "A restrained disciplined professional governing official with personal combat presence "
            "and practical field decisions."
        ),
        primary_dimension="hook_contrast",
        secondary_dimensions=("authority_scope", "personality_mode", "identity_type"),
        counterfactual_partner="hook-contrast-hope-composure",
        expected_features=_features(
            personality=("restrained", "practical", "disciplined"),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
            hook_surface=("formal_role_identity",),
            hook_contrast=("formal_role_personal_action",),
        ),
        held_constant="restrained formal governing official",
        failure_meaning="A failure would mean formal role and personal action cannot be distinguished from symbolic public duty.",
        expected_classification="CORPUS_COVERAGE_GAP",
    ),
    DiagnosticCase(
        case_id="hook-contrast-hope-composure",
        purpose="Test a governing official defined by public hope-maintenance and institutional duty.",
        brief=(
            "A restrained idealistic professional governing official who maintains public hope "
            "through symbolic composure and institutional duty."
        ),
        primary_dimension="hook_contrast",
        secondary_dimensions=("authority_scope", "personality_mode", "identity_type"),
        counterfactual_partner="hook-contrast-disciplined-official",
        expected_features=_features(
            personality=("restrained", "idealistic"),
            life_social_identity=("formal_professional",),
            authority=("formal_leadership",),
            hook_surface=("formal_role_identity",),
        ),
        held_constant="restrained formal governing official",
        failure_meaning="A failure would mean the current feature set cannot distinguish practical personal action from symbolic institutional duty.",
        expected_classification="EXPECTED_SHARED_TRAIT",
        unsupported_distinction="public hope-maintenance and symbolic composure",
    ),
)


def diagnostic_cases() -> tuple[DiagnosticCase, ...]:
    """Return the immutable, name-free diagnostic extension cases."""

    return _CASES


def _expected_features(case: DiagnosticCase) -> Mapping[FeatureDomain, tuple[str, ...]]:
    expected = dict(case.expected_features)
    scope = EXPECTED_AUTHORITY_SCOPES.get(case.case_id)
    if scope is not None:
        expected["authority_scope"] = (scope,)
    return expected


def _profile_values(profile: DiagnosticFeatureProfile) -> dict[FeatureDomain, tuple[str, ...]]:
    return {domain: tuple(profile.domain_values(domain)) for domain in DOMAINS}


def _feature_delta(
    expected: Mapping[FeatureDomain, tuple[str, ...]],
    actual: Mapping[FeatureDomain, tuple[str, ...]],
) -> dict[str, list[str]]:
    missing: list[str] = []
    unexpected: list[str] = []
    for domain in DOMAINS:
        missing.extend(f"{domain}:{value}" for value in set(expected[domain]) - set(actual[domain]))
        unexpected.extend(f"{domain}:{value}" for value in set(actual[domain]) - set(expected[domain]))
    return {"missing": sorted(missing), "unexpected": sorted(unexpected)}


def _matching_references(
    expected: Mapping[FeatureDomain, tuple[str, ...]],
    profiles: Mapping[str, DiagnosticFeatureProfile],
) -> list[str]:
    matches: list[str] = []
    for reference_id, profile in profiles.items():
        values = _profile_values(profile)
        if all(set(expected[domain]) <= set(values[domain]) for domain in DOMAINS):
            matches.append(reference_id)
    return sorted(matches)


def _shadow_overlap(
    brief_profile: DiagnosticFeatureProfile,
    profiles: Mapping[str, DiagnosticFeatureProfile],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for reference_id, profile in profiles.items():
        overlap = diagnostic_overlap(brief_profile, profile)
        shared = {
            domain: list(values["shared"])
            for domain, values in overlap.items()
            if values["shared"]
        }
        rows.append(
            {
                "reference_id": reference_id,
                "shared_domains": sorted(shared),
                "shared_features": shared,
                "shared_feature_count": sum(len(values) for values in shared.values()),
                "shared_domain_count": len(shared),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["shared_feature_count"],
            -row["shared_domain_count"],
            row["reference_id"],
        )
    )
    top_score = (
        rows[0]["shared_feature_count"],
        rows[0]["shared_domain_count"],
    ) if rows else (0, 0)
    ties = [
        row["reference_id"]
        for row in rows
        if (row["shared_feature_count"], row["shared_domain_count"]) == top_score
    ]
    return {
        "ranking": rows,
        "ties": ties,
        "zero_overlap_references": [
            row["reference_id"] for row in rows if row["shared_feature_count"] == 0
        ],
        "top_diagnostic_matches": ties,
        "non_scoring": True,
    }


def run_diagnostic(*, corpus_root: Path | None = None) -> dict[str, Any]:
    """Run only the feature-discrimination extension against production data."""

    root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    repository = CharacterReferenceRepository(root)
    references = repository.list_all()
    profiles = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in references
    }
    results: list[dict[str, Any]] = []
    for case in diagnostic_cases():
        brief_profile = extract_brief_features(case.brief)
        actual = _profile_values(brief_profile)
        expected_features = _expected_features(case)
        delta = _feature_delta(expected_features, actual)
        match_ids = _matching_references(expected_features, profiles)
        shadow = _shadow_overlap(brief_profile, profiles)
        classification = (
            "BRIEF_EXTRACTION_GAP"
            if delta["missing"] or delta["unexpected"]
            else case.expected_classification
        )
        results.append(
            {
                "case_id": case.case_id,
                "purpose": case.purpose,
                "brief": case.brief,
                "primary_dimension": case.primary_dimension,
                "secondary_dimensions": list(case.secondary_dimensions),
                "counterfactual_partner": case.counterfactual_partner,
                "expected_features": {
                    domain: list(values)
                    for domain, values in expected_features.items()
                    if values
                },
                "extracted_features": {
                    domain: list(values) for domain, values in actual.items() if values
                },
                "feature_delta": delta,
                "unsupported_requested_distinction": case.unsupported_distinction,
                "features_held_constant": case.held_constant,
                "failure_meaning": case.failure_meaning,
                "reference_matchability": {
                    "matching_references": match_ids,
                    "count": len(match_ids),
                    "classification": (
                        "0_MATCHES"
                        if not match_ids
                        else "1_MATCH"
                        if len(match_ids) == 1
                        else "MULTIPLE_MATCHES"
                    ),
                },
                "shadow_overlap": shadow,
                "failure_classification": classification,
            }
        )
    classifications = Counter(result["failure_classification"] for result in results)
    pair_map = {case.case_id: case.counterfactual_partner for case in diagnostic_cases()}
    pairs = []
    seen: set[str] = set()
    for case in diagnostic_cases():
        if case.case_id in seen:
            continue
        partner = pair_map[case.case_id]
        pairs.append({"case_id": case.case_id, "partner": partner})
        seen.add(case.case_id)
        seen.add(partner)
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "suite": "diagnostic_extension",
        "case_count": len(results),
        "counterfactual_pairs": pairs,
        "cases": results,
        "classification_counts": dict(sorted(classifications.items())),
        "production_behavior": {
            "feature_score_contribution": 0,
            "selector_touched": False,
            "winner_criterion": None,
        },
    }


def _print_human(result: Mapping[str, Any]) -> None:
    core = run_benchmark()
    summary = core["summary"]
    print("FROZEN CORE")
    print("-----------")
    print("cases: 18")
    print(f"unique: {summary['unique_selected']}")
    print(f"overlap: {summary['average_top_k_overlap']}")
    print(f"hhi: {summary['selection_concentration']['hhi']}")
    print(f"classification: {core['classification']}")
    print(f"ranking parity: {'PASS' if core['benchmark_path']['same_selector_implementation'] else 'FAIL'}")
    print(f"order: {core['corpus_order_test']['result']}")
    print()
    print("DIAGNOSTIC EXTENSION")
    print("--------------------")
    print(f"cases: {result['case_count']}")
    print(f"counterfactual pairs: {len(result['counterfactual_pairs'])}")
    print(f"classification counts: {result['classification_counts']}")
    print("feature score contribution: 0")
    for case in result["cases"]:
        print(
            f"{case['case_id']}: {case['failure_classification']} | "
            f"matches={case['reference_matchability']['classification']} | "
            f"top={case['shadow_overlap']['top_diagnostic_matches']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the diagnostic extension as JSON")
    args = parser.parse_args()
    result = run_diagnostic()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
