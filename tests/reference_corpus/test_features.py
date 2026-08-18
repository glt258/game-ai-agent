"""Tests for the v0.4.1c diagnostic-only feature contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import json

import pytest
import yaml

from reference_corpus.features import (
    FEATURE_VOCABULARY_VERSION,
    VOCABULARY,
    FeatureEvidence,
    diagnostic_overlap,
    extract_brief_features,
    normalize_values,
    reference_feature_profile,
    validate_feature_provenance,
)
from reference_corpus.errors import ReferenceValidationError
from reference_corpus.loader import CharacterReferenceLoader
from agents.official_character_authoring import DEFAULT_CORPUS_ROOT
from reference_corpus.repository import CharacterReferenceRepository


FIXTURE = "tests/reference_corpus/fixtures/valid/complete_valid"


def _reference():
    return CharacterReferenceLoader().load(FIXTURE)


def _schema_reference(tmp_path: Path, authoring_features: dict) -> object:
    target = tmp_path / "reference"
    target.mkdir()
    for name in ("facts.yaml", "sources.yaml", "analysis.yaml"):
        shutil.copy(Path(FIXTURE) / name, target / name)
    analysis_path = target / "analysis.yaml"
    analysis = yaml.safe_load(analysis_path.read_text(encoding="utf-8"))
    analysis["character_design"]["authoring_features"] = authoring_features
    analysis_path.write_text(
        yaml.safe_dump(analysis, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return CharacterReferenceLoader().load(target)


AUTHORING_FEATURES = {
    "personality": ["expressive", "practical"],
    "gameplay_fantasy": ["direct_frontline_pressure"],
    "life_social_identity": ["performer"],
    "life_stage": ["age_ambiguous"],
    "authority": ["ordinary_member"],
    "hook": {
        "surface_traits": ["public_performance"],
        "contrast_traits": [],
        "behavioral_patterns": ["public_performance"],
    },
    "visual_behavioral_motifs": ["performance_behavior"],
    "evidence": {
        "personality": [
            {
                "kind": "source_fact",
                "source_id": "synthetic-official",
                "fact_path": "narrative.occupation",
            },
            {"kind": "analyst_derivation", "note": "Authoring descriptor from identity evidence."},
        ],
        "gameplay_fantasy": [
            {
                "kind": "source_fact",
                "source_id": "synthetic-official",
                "fact_path": "combat.abilities",
            },
            {"kind": "analyst_derivation", "note": "Combat facts interpreted at authoring level."},
        ],
        "life_stage": [
            {"kind": "analyst_derivation", "note": "Presentation is intentionally age ambiguous."}
        ],
    },
}


def test_existing_production_records_validate_unchanged() -> None:
    references = CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()
    assert len(references) == 10
    assert all(reference.analysis is None or reference.analysis.character_design.authoring_features is None for reference in references)


def test_analysis_without_authoring_features_remains_valid() -> None:
    reference = _reference()
    assert reference.analysis.character_design.authoring_features is None


def test_empty_authoring_feature_block_is_valid_and_neutral(tmp_path: Path) -> None:
    reference = _schema_reference(tmp_path, {})
    block = reference.analysis.character_design.authoring_features
    assert block is not None
    assert block.personality == []
    assert block.life_stage == []
    assert block.hook is None
    assert reference_feature_profile(reference).life_stage == ()


def test_valid_authoring_features_load_and_normalize(tmp_path: Path) -> None:
    reference = _schema_reference(tmp_path, AUTHORING_FEATURES)
    block = reference.analysis.character_design.authoring_features
    assert block is not None
    assert block.personality == ["expressive", "practical"]
    assert block.hook is not None
    profile = reference_feature_profile(reference)
    assert profile.life_stage == ("age_ambiguous",)
    assert "performance_behavior" in profile.visual_behavioral_motifs
    assert any(
        item.source_ids == ("synthetic-official",)
        and item.support_status == "derived_from_fact"
        for item in profile.evidence
    )


def test_invalid_canonical_feature_is_rejected(tmp_path: Path) -> None:
    invalid = dict(AUTHORING_FEATURES)
    invalid["personality"] = ["unsupported_selector_token"]
    with pytest.raises(ReferenceValidationError, match="unsupported canonical token"):
        _schema_reference(tmp_path, invalid)


def test_nonexistent_feature_source_id_is_rejected(tmp_path: Path) -> None:
    invalid = dict(AUTHORING_FEATURES)
    invalid["evidence"] = dict(AUTHORING_FEATURES["evidence"])
    invalid["evidence"]["personality"] = [
        {
            "kind": "source_fact",
            "source_id": "missing-source",
            "fact_path": "narrative.occupation",
        }
    ]
    with pytest.raises(ReferenceValidationError, match="UNKNOWN_AUTHORING_FEATURE_SOURCE"):
        _schema_reference(tmp_path, invalid)


def test_nonexistent_feature_fact_path_is_rejected(tmp_path: Path) -> None:
    invalid = dict(AUTHORING_FEATURES)
    invalid["evidence"] = dict(AUTHORING_FEATURES["evidence"])
    invalid["evidence"]["personality"] = [
        {
            "kind": "source_fact",
            "source_id": "synthetic-official",
            "fact_path": "narrative.does_not_exist",
        }
    ]
    with pytest.raises(ReferenceValidationError, match="UNKNOWN_AUTHORING_FEATURE_FACT"):
        _schema_reference(tmp_path, invalid)


def test_schema_serialization_is_deterministic_and_analysis_is_not_canon(tmp_path: Path) -> None:
    reference = _schema_reference(tmp_path, AUTHORING_FEATURES)
    first = json.dumps(reference.analysis.model_dump(mode="json"), sort_keys=True)
    second = json.dumps(reference.analysis.model_dump(mode="json"), sort_keys=True)
    assert first == second
    assert "authoring_features" not in reference.facts.model_dump(mode="json")


def test_vocabulary_is_bounded_and_canonical_tokens_are_stable() -> None:
    assert FEATURE_VOCABULARY_VERSION == "reference-feature-vocabulary/0.4.1c"
    assert set(VOCABULARY) == {
        "personality",
        "gameplay_fantasy",
        "life_social_identity",
        "life_stage",
        "authority",
        "hook_surface",
        "hook_contrast",
        "hook_behavioral_pattern",
        "visual_behavioral_motif",
    }
    for domain, values in VOCABULARY.items():
        assert len(values) <= 14, domain
        assert all(value == value.strip() and " " not in value for value in values)


def test_unknown_values_remain_absent() -> None:
    normalized, evidence = normalize_values(
        "personality",
        ["invented_psychology_label", "aggressive"],
        provenance_kind="brief",
        source_path="brief",
    )
    assert normalized == ()
    assert evidence == ()


def test_aliases_are_deterministic_and_ambiguous_terms_are_not_forced() -> None:
    brief = "quiet practical researcher; mature active magistrate; limited authority"
    first = extract_brief_features(brief)
    second = extract_brief_features(brief)
    assert first == second
    assert first.personality == ("restrained", "practical")
    assert first.life_stage == ("mature_presentation",)
    assert first.authority == ("low_formal_authority", "formal_leadership")
    assert "confrontational" not in first.personality


def test_brief_extraction_keeps_life_stage_unknown_without_inference() -> None:
    profile = extract_brief_features(
        "playable character with independent dangerous field work; no age or school-history invention"
    )
    assert profile.life_stage == ()
    assert profile.authority == ()
    assert profile.life_social_identity == ("independent_operator",)


def test_reference_normalization_preserves_analysis_and_marks_provenance() -> None:
    reference = _reference()
    original_analysis = reference.analysis.model_dump(mode="json")
    profile = reference_feature_profile(reference)
    assert reference.analysis.model_dump(mode="json") == original_analysis
    assert profile.personality == ("expressive",)
    assert "direct_frontline_pressure" in profile.gameplay_fantasy
    assert "performer" in profile.life_social_identity
    assert "public_performance" in profile.hook.surface_traits
    assert any(item.provenance_kind == "analyst_derivation" for item in profile.evidence)
    assert any(item.provenance_kind == "source_fact" for item in profile.evidence)
    validate_feature_provenance(profile, reference=reference)


def test_provenance_rejects_unknown_source_ids() -> None:
    reference = _reference()
    profile = reference_feature_profile(reference)
    bad = replace(
        profile,
        evidence=profile.evidence
        + (
            FeatureEvidence(
                domain="life_social_identity",
                canonical_token="performer",
                provenance_kind="source_fact",
                source_path="facts.narrative.occupation",
                source_ids=("missing-source",),
                support_status="direct_normalization",
            ),
        ),
    )
    with pytest.raises(ValueError, match="unknown feature provenance"):
        validate_feature_provenance(bad, reference=reference)


def test_overlap_is_diagnostic_only_and_exposes_shared_terms() -> None:
    brief = extract_brief_features("A quiet practical performer with a mature presentation")
    reference = extract_brief_features("quiet practical performer mature")
    overlap = diagnostic_overlap(brief, reference)
    assert overlap["personality"]["shared"] == ["practical", "restrained"]
    assert overlap["life_stage"]["shared"] == ["mature_presentation"]
    assert overlap["life_social_identity"]["shared"] == ["performer"]
