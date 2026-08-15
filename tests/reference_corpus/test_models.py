from __future__ import annotations

import pytest
from pydantic import ValidationError

from reference_corpus.enums import NormalizedRole
from reference_corpus.models import (
    AbilityFact,
    AlignmentAssessment,
    AnalysisConfidence,
    CombatDesignAnalysis,
    CombatMechanics,
    LocalizedNames,
    NativeTaxonomy,
    PrimaryLoop,
)


def test_minimal_models_parse_and_defaults_are_isolated() -> None:
    first = CombatMechanics()
    second = CombatMechanics()
    first.resources.append("focus")
    assert second.resources == []

    names = LocalizedNames(canonical="Name")
    assert names.localized == {}
    assert AbilityFact(ability_id="basic", native_category="basic").ability_id == "basic"


def test_models_forbid_unknown_fields_and_invalid_enums() -> None:
    with pytest.raises(ValidationError):
        LocalizedNames(canonical="Name", unexpected=True)
    with pytest.raises(ValidationError):
        CombatDesignAnalysis(
            normalized_roles=["not-a-role"],
            primary_loop=PrimaryLoop(steps=["setup"]),
        )


def test_confidence_and_alignment_are_bounded() -> None:
    with pytest.raises(ValidationError):
        AnalysisConfidence(overall=-0.01)
    with pytest.raises(ValidationError):
        AnalysisConfidence(overall=1.01)
    with pytest.raises(ValidationError):
        AlignmentAssessment(score=1.01, reasoning="bad")


def test_localized_names_and_native_taxonomy_reject_empty_values() -> None:
    with pytest.raises(ValidationError):
        LocalizedNames(canonical=" ")
    with pytest.raises(ValidationError):
        LocalizedNames(canonical="Name", localized={"en-US": " "})
    with pytest.raises(ValidationError):
        NativeTaxonomy(labels={"weapon": {"nested": "no"}})


def test_normalized_roles_are_enum_values() -> None:
    analysis = CombatDesignAnalysis(
        normalized_roles=["support"],
        primary_loop=PrimaryLoop(steps=["setup"]),
    )
    assert analysis.normalized_roles == [NormalizedRole.SUPPORT]
