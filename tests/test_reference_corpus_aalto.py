from __future__ import annotations

import json
from pathlib import Path

from agents.official_character_authoring import load_reference_grounding
from agents.reference_selection_benchmark import TOP_K, benchmark_cases, run_benchmark
from reference_corpus.features import reference_feature_profile, validate_feature_provenance
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.provenance import validate_provenance
from reference_corpus.repository import CharacterReferenceRepository


CORPUS_ROOT = Path("data/reference_corpus/characters")
AALTO_DIR = CORPUS_ROOT / "wuthering_waves" / "aalto"
CATALOG = load_game_catalog(CORPUS_ROOT / "_catalog" / "games.yaml")
EXPECTED_EXISTING_IDS = {
    "genshin-impact:furina",
    "genshin-impact:keqing",
    "genshin-impact:nahida",
    "neverness-to-everness:fadia",
    "neverness-to-everness:shinku",
    "wuthering-waves:jinhsi",
    "wuthering-waves:mortefi",
    "wuthering-waves:shorekeeper",
    "zenless-zone-zero:jane-doe",
    "zenless-zone-zero:nicole",
}


def _aalto():
    return CharacterReferenceLoader(CATALOG).load(AALTO_DIR)


def test_wave2_records_load_alongside_aalto() -> None:
    reference = _aalto()
    repository = CharacterReferenceRepository(CORPUS_ROOT, catalog=CATALOG)
    ids = {item.reference_id for item in repository.list_all()}

    assert reference.reference_id == "wuthering-waves:aalto"
    assert len(ids) == 14
    assert ids == EXPECTED_EXISTING_IDS | {
        "wuthering-waves:aalto",
        "zenless-zone-zero:astra-yao",
        "zenless-zone-zero:piper-wheel",
        "zenless-zone-zero:qingyi",
    }


def test_aalto_primary_sources_resolve_and_preserve_article_ids() -> None:
    reference = _aalto()
    sources = {source.source_id: source for source in reference.provenance.sources}

    assert set(sources) == {
        "official-developer-notes-aalto",
        "official-profile-reveal-aalto",
    }
    assert all(source.source_type.value == "official" for source in sources.values())
    assert all(source.reliability.value == "primary" for source in sources.values())
    assert "497" in sources["official-developer-notes-aalto"].title
    assert "475" in sources["official-profile-reveal-aalto"].title
    assert sources["official-developer-notes-aalto"].url.endswith("/497")
    assert sources["official-profile-reveal-aalto"].url.endswith("/475")
    validate_provenance(reference.provenance, reference.facts, reference.analysis)


def test_aalto_membership_and_source_safe_identity_boundary_are_preserved() -> None:
    reference = _aalto()
    narrative = reference.facts.narrative
    assert narrative.faction == "Black Shores"
    assert narrative.affiliations == ["Black Shores"]
    assert narrative.occupation == "Information Broker"

    facts_text = json.dumps(reference.facts.model_dump(mode="json"), ensure_ascii=False).lower()
    analysis_text = json.dumps(reference.analysis.model_dump(mode="json"), ensure_ascii=False).lower()
    for unsafe in ("fully independent", "unaffiliated", "pure outsider", "outsider"):
        assert unsafe not in facts_text
        assert unsafe not in analysis_text


def test_aalto_gameplay_facts_and_analysis_provenance_validate() -> None:
    reference = _aalto()
    ability_names = {ability.native_name for ability in reference.facts.combat.abilities}
    assert {"Normal Attack", "Mist Avatar", "Gate of Quandary"} <= ability_names
    assert reference.facts.combat.mechanics.mobility_mechanics
    assert reference.facts.combat.team_mechanics.buffs
    assert reference.analysis.character_design.authoring_features is not None
    features = reference.analysis.character_design.authoring_features
    assert features.authority_scope is None
    assert features.life_stage == []
    assert features.personality == []
    assert features.gameplay_fantasy == ["mobility_repositioning", "setup_payoff"]
    assert features.life_social_identity == [
        "informal_worker",
        "organization_member",
        "independent_operator",
    ]
    validate_feature_provenance(reference_feature_profile(reference), reference=reference)


def test_existing_ten_records_are_unchanged_in_corpus_membership_and_identity_scoring_is_non_scoring() -> None:
    repository = CharacterReferenceRepository(CORPUS_ROOT, catalog=CATALOG)
    references = repository.list_all()
    assert {
        item.reference_id
        for item in references
    } - {
        "wuthering-waves:aalto",
        "zenless-zone-zero:astra-yao",
        "zenless-zone-zero:piper-wheel",
        "zenless-zone-zero:qingyi",
    } == EXPECTED_EXISTING_IDS
    result = run_benchmark()
    assert result["selector"]["candidate_count"] == 14
    assert result["selector"]["feature_domains"] == ["personality", "gameplay_fantasy", "authority"]
    assert "life_social_identity" in result["selector"]["non_active_domains"]
    assert all(case["diagnostic_features"]["score_contribution"] == 0 for case in result["cases"])


def test_selector_is_deterministic_and_has_no_cross_score_leapfrog() -> None:
    brief = benchmark_cases()[5]["brief"]
    first = load_reference_grounding(brief)
    second = load_reference_grounding(brief)
    assert first.selection_audit == second.selection_audit
    result = run_benchmark()
    for case in result["cases"]:
        ranking = case["full_ranking"]
        assert all(
            ranking[index]["legacy_score"] >= ranking[index + 1]["legacy_score"]
            for index in range(len(ranking) - 1)
        )


def test_aalto_selection_trace_is_explainable_and_tie_break_artifact_free() -> None:
    result = run_benchmark()
    selected_cases = []
    zero_evidence_artifacts = []
    for case in result["cases"]:
        row = next(item for item in case["full_ranking"] if item["reference_id"] == "wuthering-waves:aalto")
        if row["rank"] <= TOP_K:
            selected_cases.append(case["brief_id"])
            if (
                row["legacy_score"] == 0
                and row["feature_secondary_score"] == 0
                and row["ordering_reason"] == "DETERMINISTIC_FINAL_TIEBREAK"
            ):
                zero_evidence_artifacts.append(case["brief_id"])

    assert selected_cases == ["case-f-information-investigation"]
    assert zero_evidence_artifacts == []
    audit = load_reference_grounding(benchmark_cases()[5]["brief"]).selection_audit
    aalto = next(item for item in audit if item["reference_id"] == "wuthering-waves:aalto")
    assert aalto["legacy_score"] == 1
    assert aalto["ordering_reason"] == "LEGACY_SCORE"
    assert aalto["personality_match"] == 0.0
    assert aalto["gameplay_fantasy_match"] == 0.0
    assert aalto["authority_match"] == 0.0
    assert "wuthering-waves:aalto" not in load_reference_grounding(benchmark_cases()[10]["brief"]).reference_ids
