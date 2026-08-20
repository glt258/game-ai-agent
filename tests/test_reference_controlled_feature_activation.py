"""v0.4.3b controlled activation contract tests."""

from __future__ import annotations

from dataclasses import replace

from agents.official_character_authoring import (
    DEFAULT_CORPUS_ROOT,
    load_reference_grounding,
    rank_reference_summaries,
)
from agents.reference_controlled_feature_activation import run_activation_report
from agents.reference_feature_ordering import READY_DOMAINS, ready_feature_score_trace
from agents.reference_feature_shadow_scoring import (
    MODEL_3_LEGACY_READY_FEATURES,
    feature_score_trace,
    shadow_rank,
)
from reference_corpus.features import (
    DiagnosticFeatureProfile,
    extract_brief_features,
    reference_feature_profile,
)
from reference_corpus.repository import CharacterReferenceRepository


def _summary(reference_id: str, *tokens: str) -> dict[str, object]:
    return {
        "reference_id": reference_id,
        "display_name": reference_id,
        "game_id": "test-game",
        "roles": list(tokens),
        "occupation": None,
        "ability_categories": [],
        "taxonomy": {},
    }


def _profiles(**values: DiagnosticFeatureProfile) -> dict[str, DiagnosticFeatureProfile]:
    return dict(values)


def test_higher_legacy_score_always_beats_maximum_feature_score() -> None:
    summaries = [_summary("a:reference", "alpha", "one", "two"), _summary("b:reference", "alpha", "one")]
    profiles = _profiles(
        **{
            "a:reference": extract_brief_features("formal leadership"),
            "b:reference": extract_brief_features("quiet practical expressive formal leadership"),
        }
    )
    ranking = rank_reference_summaries(
        "alpha one two quiet practical expressive formal leadership",
        summaries,
        feature_profiles=profiles,
    )
    assert [item["reference_id"] for item in ranking] == ["a:reference", "b:reference"]
    assert ranking[0]["legacy_score"] > ranking[1]["legacy_score"]


def test_equal_legacy_score_uses_feature_secondary_score() -> None:
    summaries = [_summary("a:reference", "alpha"), _summary("b:reference", "alpha")]
    profiles = _profiles(
        **{
            "a:reference": extract_brief_features("quiet"),
            "b:reference": extract_brief_features("expressive"),
        }
    )
    ranking = rank_reference_summaries("alpha quiet", summaries, feature_profiles=profiles)
    assert [item["reference_id"] for item in ranking] == ["a:reference", "b:reference"]
    assert ranking[1]["ordering_reason"] == "FEATURE_SECONDARY_TIEBREAK"


def test_each_ready_domain_contributes_equally() -> None:
    brief = extract_brief_features("quiet direct combat formal leadership")
    for domain in READY_DOMAINS:
        reference = DiagnosticFeatureProfile(**{domain: brief.domain_values(domain)})
        trace = ready_feature_score_trace(brief, reference)
        assert trace["domains"][domain]["score"] == 1.0
        assert trace["feature_subtotal"] == 0.333


def test_ready_domains_are_the_only_production_feature_inputs() -> None:
    brief = extract_brief_features("quiet")
    base = extract_brief_features("quiet")
    expanded = replace(
        base,
        life_social_identity=("performer",),
        authority_scope=("state_scale",),
        hook=replace(base.hook, surface_traits=("public_performance",)),
        life_stage=("mature",),
        visual_behavioral_motifs=("weapon_signature",),
    )
    assert ready_feature_score_trace(brief, base) == ready_feature_score_trace(brief, expanded)


def test_authority_scope_contributes_zero_even_when_it_changes() -> None:
    brief = extract_brief_features("formal leadership state-scale institution")
    unknown = extract_brief_features("formal leadership")
    scoped = replace(unknown, authority_scope=("state_scale",))
    assert ready_feature_score_trace(brief, unknown)["feature_subtotal"] == ready_feature_score_trace(
        brief, scoped
    )["feature_subtotal"]


def test_missing_metadata_is_neutral_and_not_a_penalty() -> None:
    brief = extract_brief_features("quiet formal leadership")
    no_authority = extract_brief_features("quiet")
    with_authority = extract_brief_features("quiet formal leadership")
    assert ready_feature_score_trace(brief, no_authority)["domains"]["authority"]["score"] == 0.0
    assert ready_feature_score_trace(brief, no_authority)["domains"]["authority"]["missing_neutral"] is True
    assert ready_feature_score_trace(brief, no_authority)["feature_subtotal"] == 0.5
    assert ready_feature_score_trace(brief, with_authority)["feature_subtotal"] == 1.0


def test_jaccard_does_not_reward_metadata_density() -> None:
    brief = extract_brief_features("quiet")
    sparse = extract_brief_features("quiet")
    dense = extract_brief_features("quiet expressive practical")
    assert ready_feature_score_trace(brief, sparse)["feature_subtotal"] == 1.0
    assert ready_feature_score_trace(brief, dense)["feature_subtotal"] == 0.333


def test_zero_feature_evidence_preserves_reference_id_tie_break() -> None:
    summaries = [_summary("z:reference", "alpha"), _summary("a:reference", "alpha")]
    profiles = _profiles(
        **{
            "z:reference": DiagnosticFeatureProfile(),
            "a:reference": DiagnosticFeatureProfile(),
        }
    )
    ranking = rank_reference_summaries("alpha", summaries, feature_profiles=profiles)
    assert [item["reference_id"] for item in ranking] == ["a:reference", "z:reference"]
    assert ranking[1]["ordering_reason"] == "DETERMINISTIC_FINAL_TIEBREAK"


def test_feature_and_corpus_order_permutations_are_invariant() -> None:
    summaries = [_summary("a:reference", "alpha"), _summary("b:reference", "alpha")]
    profiles = _profiles(
        **{
            "a:reference": extract_brief_features("quiet practical"),
            "b:reference": extract_brief_features("quiet"),
        }
    )
    reversed_profiles = {
        reference_id: replace(
            profile,
            personality=tuple(reversed(profile.personality)),
            gameplay_fantasy=tuple(reversed(profile.gameplay_fantasy)),
            authority=tuple(reversed(profile.authority)),
        )
        for reference_id, profile in profiles.items()
    }
    first = rank_reference_summaries("alpha quiet practical", summaries, feature_profiles=profiles)
    second = rank_reference_summaries(
        "alpha quiet practical", list(reversed(summaries)), feature_profiles=reversed_profiles
    )
    assert [item["reference_id"] for item in first] == [item["reference_id"] for item in second]


def test_production_audit_exposes_trace_and_ordering_reason() -> None:
    grounding = load_reference_grounding("A flamboyant expressive performer with formal leadership")
    assert len(grounding.selection_audit) == 16
    row = grounding.selection_audit[0]
    assert {"legacy_score", "personality_match", "gameplay_fantasy_match", "authority_match"} <= row.keys()
    assert row["ordering_reason"] in {
        "LEGACY_SCORE",
        "FEATURE_SECONDARY_TIEBREAK",
        "DETERMINISTIC_FINAL_TIEBREAK",
    }


def test_production_matches_frozen_shadow_model_3_for_all_core_cases() -> None:
    report = run_activation_report()
    assert report["shadow_parity"]["pass"] is True
    assert report["shadow_parity"]["differences"] == []


def test_activation_metrics_and_review_gate_match_approved_model() -> None:
    report = run_activation_report()
    assert report["legacy_baseline"] == {
        "unique": 11,
        "overlap": 0.348485,
        "hhi": 0.139232,
        "classification": "LIMITED_SENSITIVITY",
    }
    assert report["controlled_activation"] == {
        "unique": 11,
        "overlap": 0.34697,
        "hhi": 0.136488,
        "changed": 6,
        "plausibly_better": 4,
        "plausibly_worse": 0,
        "ambiguous": 2,
        "corpus_gap": 0,
        "metadata_gap": 0,
    }


def test_no_changed_core_case_crosses_legacy_score_groups() -> None:
    report = run_activation_report()
    changed = [case for case in report["core_cases"] if case["changed"]]
    assert len(changed) == 6
    assert all(case["affected_references_same_legacy_group"] for case in changed)
    assert all(case["no_cross_legacy_leapfrog"] for case in report["core_cases"])


def test_all_six_diagnostic_pairs_are_reported_and_explainable() -> None:
    report = run_activation_report()
    pairs = report["diagnostic_extension"]["pairs"]
    assert len(pairs) == 6
    assert all(pair["explainability"] == "PASS" for pair in pairs)
    assert any(pair["responsible_domain"] == "authority" for pair in pairs)
    assert all(pair["responsible_domain"] != "authority_scope" for pair in pairs)


def test_production_reference_corpus_has_sixteen_records() -> None:
    references = CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()
    assert len(references) == 16


def test_shadow_ready_trace_has_same_semantics_as_production_trace() -> None:
    references = CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()
    reference = next(item for item in references if item.reference_id == "zenless-zone-zero:nicole")
    brief = extract_brief_features("formal leadership with broad public responsibilities")
    profile = reference_feature_profile(reference)
    production = ready_feature_score_trace(brief, profile)
    shadow = feature_score_trace(
        brief,
        profile,
        domains=READY_DOMAINS,
        primitive="jaccard",
        hook_mode="family_max",
    )
    assert shadow["feature_subtotal"] == production["feature_subtotal"]
    assert shadow["domains"] == production["domains"]
