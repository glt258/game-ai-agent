"""Focused v0.4.2d authority-scope representation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.official_character_authoring import DEFAULT_CORPUS_ROOT
from agents.reference_feature_discrimination_diagnostic import run_diagnostic
from reference_corpus.features import (
    VOCABULARY,
    canonical_tokens,
    extract_brief_features,
    reference_feature_profile,
    validate_feature_provenance,
)
from reference_corpus.models import AuthoringFeatureBlock
from reference_corpus.provenance import validate_analysis_feature_provenance
from reference_corpus.repository import CharacterReferenceRepository


EXPECTED_SCOPE = {
    "zenless-zone-zero:nicole": "private_group",
    "genshin-impact:keqing": "institutional",
    "genshin-impact:nahida": "state_scale",
    "wuthering-waves:jinhsi": "state_scale",
    "wuthering-waves:shorekeeper": "institutional",
}
UNKNOWN_SCOPE = {
    "genshin-impact:furina",
    "wuthering-waves:mortefi",
    "wuthering-waves:aalto",
    "zenless-zone-zero:jane-doe",
    "neverness-to-everness:fadia",
    "neverness-to-everness:shinku",
    "honkai-impact-3rd:vita",
    "honkai-impact-3rd:songque",
}


def test_authority_scope_vocabulary_is_exact_and_bounded() -> None:
    assert canonical_tokens("authority_scope") == (
        "private_group",
        "institutional",
        "state_scale",
    )
    assert set(VOCABULARY["authority_scope"]) == {
        "private_group",
        "institutional",
        "state_scale",
    }


def test_authority_scope_is_optional_and_rejects_noncanonical_values() -> None:
    assert AuthoringFeatureBlock().authority_scope is None
    assert AuthoringFeatureBlock(authority_scope="institutional").authority_scope == (
        "institutional"
    )
    with pytest.raises(ValidationError, match="unsupported canonical token"):
        AuthoringFeatureBlock(authority_scope="sovereign")


@pytest.mark.parametrize(
    ("brief", "expected"),
    [
        (
            "A practical leader of a small private team with a few direct reports.",
            ("private_group",),
        ),
        (
            "A small private agency with no government authority.",
            ("private_group",),
        ),
        ("A leader who leads a few members.", ("private_group",)),
        (
            "A formal organization executive with a governing portfolio.",
            ("institutional",),
        ),
        ("A leader of a large organization, but not a government.", ("institutional",)),
        ("A serious organization member with field responsibility.", ()),
        (
            "A leader who governs the entire city with broad public responsibilities.",
            ("state_scale",),
        ),
        ("A magistrate with personal combat presence.", ()),
        (
            "A small department inside a government institution with no command claim.",
            (),
        ),
    ],
)
def test_authority_scope_brief_extraction_is_conservative(
    brief: str, expected: tuple[str, ...]
) -> None:
    assert extract_brief_features(brief).authority_scope == expected


def test_scope_migration_is_exact_and_provenance_valid() -> None:
    references = CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()
    assert len(references) == 16
    populated: dict[str, str] = {}
    for reference in references:
        profile = reference_feature_profile(reference)
        validate_feature_provenance(profile, reference=reference)
        validate_analysis_feature_provenance(
            reference.provenance,
            reference.facts,
            reference.analysis,
        )
        if profile.authority_scope:
            populated[reference.reference_id] = profile.authority_scope[0]
    assert populated == EXPECTED_SCOPE
    assert {
        reference.reference_id
        for reference in references
        if not reference_feature_profile(reference).authority_scope
    } == UNKNOWN_SCOPE | {
        "zenless-zone-zero:astra-yao",
        "zenless-zone-zero:piper-wheel",
        "zenless-zone-zero:qingyi",
    }


def test_scope_profile_serialization_is_separate_from_authority_form() -> None:
    reference = next(
        reference
        for reference in CharacterReferenceRepository(DEFAULT_CORPUS_ROOT).list_all()
        if reference.reference_id == "genshin-impact:nahida"
    )
    profile = reference_feature_profile(reference)
    assert profile.authority == ("formal_leadership",)
    assert profile.authority_scope == ("state_scale",)
    assert profile.to_dict(include_evidence=False)["authority"] == ["formal_leadership"]
    assert profile.to_dict(include_evidence=False)["authority_scope"] == ["state_scale"]


def test_diagnostic_shadow_reports_scope_without_production_scoring() -> None:
    result = run_diagnostic()
    cases = {case["case_id"]: case for case in result["cases"]}
    assert cases["authority-scope-small-private-team"]["extracted_features"][
        "authority_scope"
    ] == ["private_group"]
    assert cases["authority-scope-state-institution"]["extracted_features"][
        "authority_scope"
    ] == ["state_scale"]
    assert cases["authority-form-portfolio-governance"]["extracted_features"][
        "authority_scope"
    ] == ["institutional"]
    assert cases["authority-form-sovereign"]["extracted_features"][
        "authority_scope"
    ] == ["state_scale"]
    assert result["production_behavior"]["feature_score_contribution"] == 0
    assert result["production_behavior"]["selector_touched"] is False
