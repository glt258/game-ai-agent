"""Focused tests for the non-production v0.4.3a shadow scorer."""

from __future__ import annotations

from agents.official_character_authoring import DEFAULT_CORPUS_ROOT, load_reference_grounding
from agents.reference_feature_shadow_scoring import (
    MODEL_0_LEGACY_ONLY,
    MODEL_3_LEGACY_READY_FEATURES,
    feature_domain_score,
    feature_score_trace,
    run_shadow_simulation,
    shadow_rank,
)
from agents.reference_selection_benchmark import run_benchmark
from reference_corpus.features import extract_brief_features, reference_feature_profile
from reference_corpus.repository import CharacterReferenceRepository


def _references():
    return CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()


def test_domain_primitives_are_bounded_and_missing_is_neutral() -> None:
    brief = extract_brief_features("quiet practical")
    dense = extract_brief_features("quiet practical expressive")
    missing_scope = extract_brief_features("quiet practical")

    assert feature_domain_score(brief, dense, "personality", "raw_intersection") == 2.0
    assert feature_domain_score(brief, dense, "personality", "binary") == 1.0
    assert feature_domain_score(brief, dense, "personality", "jaccard") == 0.667
    assert feature_domain_score(brief, dense, "personality", "overlap_coefficient") == 1.0
    assert feature_domain_score(brief, dense, "personality", "capped_token_overlap") == 1.0
    assert feature_domain_score(
        missing_scope,
        dense,
        "authority_scope",
        "jaccard",
    ) == 0.0


def test_jaccard_does_not_reward_reference_metadata_density() -> None:
    brief = extract_brief_features("quiet")
    sparse = extract_brief_features("quiet")
    dense = extract_brief_features("quiet expressive practical serious")

    assert feature_domain_score(brief, sparse, "personality", "jaccard") == 1.0
    assert feature_domain_score(brief, dense, "personality", "jaccard") == 0.25


def test_authority_form_and_scope_remain_orthogonal() -> None:
    brief = extract_brief_features(
        "formal leadership with broad public responsibilities for a city-state institution"
    )
    references = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in _references()
    }
    nicole = feature_score_trace(brief, references["zenless-zone-zero:nicole"])
    jinhsi = feature_score_trace(brief, references["wuthering-waves:jinhsi"])

    assert nicole["domains"]["authority"]["score"] == 1.0
    assert jinhsi["domains"]["authority"]["score"] == 1.0
    assert nicole["domains"]["authority_scope"]["score"] == 0.0
    assert jinhsi["domains"]["authority_scope"]["score"] == 1.0


def test_unknown_authority_scope_is_neutral() -> None:
    brief = extract_brief_features(
        "formal leadership for a city-state institution with broad public responsibilities"
    )
    references = {
        reference.reference_id: reference_feature_profile(reference)
        for reference in _references()
    }

    unknown = feature_score_trace(brief, references["genshin-impact:furina"])
    known = feature_score_trace(brief, references["wuthering-waves:jinhsi"])

    assert unknown["domains"]["authority_scope"]["score"] == 0.0
    assert unknown["domains"]["authority_scope"]["missing_neutral"] is True
    assert known["domains"]["authority_scope"]["score"] == 1.0


def test_hook_family_has_one_bounded_contribution() -> None:
    brief = extract_brief_features(
        "public performance formal role personal action routine problem solving"
    )
    reference = extract_brief_features(
        "public performance formal role personal action routine problem solving"
    )
    trace = feature_score_trace(brief, reference)

    assert trace["hook_subdomain_scores"] == {
        "hook_surface": 1.0,
        "hook_contrast": 1.0,
        "hook_behavioral_pattern": 1.0,
    }
    assert trace["hook_family_score"] == 1.0
    assert trace["feature_subtotal"] <= 1.0


def test_shadow_rank_is_deterministic_and_production_remains_unchanged() -> None:
    brief = "A quiet practical researcher with an on_field_dps combat role."
    references = _references()
    first = shadow_rank(brief, references, model=MODEL_3_LEGACY_READY_FEATURES)
    second = shadow_rank(brief, list(reversed(references)), model=MODEL_3_LEGACY_READY_FEATURES)

    assert first["selected_references"] == second["selected_references"]
    before = load_reference_grounding(brief).reference_ids
    after = load_reference_grounding(brief).reference_ids
    assert before == after
    core = run_benchmark()
    assert core["summary"]["unique_selected"] == 8
    assert core["summary"]["average_top_k_overlap"] == 0.448485
    assert core["summary"]["selection_concentration"]["hhi"] == 0.159808
    assert first["production_behavior"]["feature_score_contribution"] == 0
    assert first["production_behavior"]["selector_touched"] is False


def test_legacy_only_shadow_model_exposes_legacy_score_without_features() -> None:
    result = shadow_rank("A formal leader", _references(), model=MODEL_0_LEGACY_ONLY)
    assert all(item["feature_subtotal"] == 0.0 for item in result["ranking"])
    assert all(item["combined_shadow_score"] == item["legacy_score"] for item in result["ranking"])


def test_shadow_simulation_is_non_scoring_and_reports_models() -> None:
    result = run_shadow_simulation()
    assert result["production_behavior"] == {
        "feature_score_contribution": 0,
        "selector_touched": False,
        "ranking_logic_changed": False,
        "tie_breaking_changed": False,
    }
    assert set(result["models"]) == {
        MODEL_0_LEGACY_ONLY,
        "MODEL_1_FEATURE_ONLY",
        "MODEL_2_LEGACY_PLUS_ALL_CANDIDATE_FEATURES",
        MODEL_3_LEGACY_READY_FEATURES,
    }
    assert result["stability"]["order_independent"] is True
