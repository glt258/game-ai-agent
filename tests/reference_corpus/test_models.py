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
    CombatFacts,
    LocalizedNames,
    MechanicRef,
    MechanicRelation,
    NativeTaxonomy,
    PrimaryLoop,
    ResourceFact,
    StateFact,
    TeamInteractionFact,
    TeamMechanics,
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


def test_structured_mechanic_nodes_and_relation_types() -> None:
    assert ResourceFact(resource_id="focus", cap=None).cap is None
    assert StateFact(state_id="empowered", subject_scope="self").state_id == "empowered"
    assert TeamInteractionFact(
        interaction_id="team-charge", description_summary="Generates focus."
    ).interaction_id == "team-charge"
    assert MechanicRef(kind="resource", id="focus").kind == "resource"
    relation = MechanicRelation(
        relation_id="team-generates-focus",
        source={"kind": "team_interaction", "id": "team-charge"},
        relation_type="generates",
        target={"kind": "resource", "id": "focus"},
    )
    assert relation.relation_type == "generates"


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: CombatMechanics(
                resources=[ResourceFact(resource_id="focus"), ResourceFact(resource_id="focus")]
            ),
            "DUPLICATE_RESOURCE_ID",
        ),
        (
            lambda: CombatMechanics(
                states=[
                    StateFact(state_id="empowered", subject_scope="self"),
                    StateFact(state_id="empowered", subject_scope="self"),
                ]
            ),
            "DUPLICATE_STATE_ID",
        ),
        (
            lambda: TeamMechanics(
                interactions=[
                    TeamInteractionFact(interaction_id="charge", description_summary="x"),
                    TeamInteractionFact(interaction_id="charge", description_summary="y"),
                ]
            ),
            "DUPLICATE_TEAM_INTERACTION_ID",
        ),
    ],
)
def test_duplicate_mechanic_node_ids_are_rejected(factory, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        factory()


def test_relation_ids_and_references_are_validated() -> None:
    ability = AbilityFact(ability_id="skill", native_category="skill")
    with pytest.raises(ValidationError, match="DUPLICATE_RELATION_ID"):
        CombatFacts(
            native_taxonomy=NativeTaxonomy(),
            abilities=[ability],
            relations=[
                {
                    "relation_id": "same",
                    "source": {"kind": "ability", "id": "skill"},
                    "relation_type": "grants",
                    "target": {"kind": "state", "id": "missing"},
                },
                {
                    "relation_id": "same",
                    "source": {"kind": "ability", "id": "skill"},
                    "relation_type": "grants",
                    "target": {"kind": "state", "id": "missing"},
                },
            ],
        )
    with pytest.raises(ValidationError, match="UNKNOWN_MECHANIC_REFERENCE"):
        CombatFacts(
            native_taxonomy=NativeTaxonomy(),
            abilities=[ability],
            relations=[
                {
                    "relation_id": "unknown-target",
                    "source": {"kind": "ability", "id": "skill"},
                    "relation_type": "grants",
                    "target": {"kind": "state", "id": "missing"},
                }
            ],
        )


def test_invalid_mechanic_reference_and_relation_type_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MechanicRef(kind="unknown", id="x")
    with pytest.raises(ValidationError):
        MechanicRelation(
            relation_id="bad",
            source={"kind": "ability", "id": "a"},
            relation_type="Not Natural Language",
            target={"kind": "state", "id": "s"},
        )


@pytest.mark.parametrize(
    ("kind", "target_id"),
    [
        ("ability", "missing-ability"),
        ("state", "missing-state"),
        ("resource", "missing-resource"),
        ("team_interaction", "missing-interaction"),
    ],
)
def test_all_unknown_mechanic_reference_kinds_are_rejected(kind: str, target_id: str) -> None:
    with pytest.raises(ValidationError, match="UNKNOWN_MECHANIC_REFERENCE"):
        CombatFacts(
            native_taxonomy=NativeTaxonomy(),
            relations=[
                {
                    "relation_id": "unknown-reference",
                    "source": {"kind": kind, "id": target_id},
                    "relation_type": "requires",
                    "target": {"kind": "ability", "id": "missing-ability"},
                }
            ],
        )


@pytest.mark.parametrize("relation_type", ["", "Not Natural Language", "two-words"])
def test_empty_or_non_snake_relation_types_are_rejected(relation_type: str) -> None:
    with pytest.raises(ValidationError):
        MechanicRelation(
            relation_id="bad-type",
            source={"kind": "ability", "id": "a"},
            relation_type=relation_type,
            target={"kind": "state", "id": "s"},
        )


@pytest.mark.parametrize("subject_scope", ["self", "target", "unknown"])
def test_state_subject_scope_accepts_provisional_values(subject_scope: str) -> None:
    state = StateFact(state_id="state", subject_scope=subject_scope)
    assert state.subject_scope == subject_scope


@pytest.mark.parametrize("subject_scope", ["", "enemy", "player", "ally", "self_state"])
def test_state_subject_scope_rejects_missing_or_uncontrolled_values(subject_scope: str) -> None:
    with pytest.raises(ValidationError, match="subject_scope"):
        StateFact(state_id="state", subject_scope=subject_scope)


def test_state_subject_scope_is_required() -> None:
    with pytest.raises(ValidationError, match="subject_scope"):
        StateFact(state_id="state")
