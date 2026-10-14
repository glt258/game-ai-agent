from __future__ import annotations

from dataclasses import replace

import pytest

from agents import CharacterDesignRequest, ModelTurn, ScriptedAgentModel
from character_intelligence.context import (
    ContextGap,
    ContextGapCode,
    assemble_character_planning_context_v2,
)
from character_intelligence.field_authorization import (
    CHARACTER_GENERATION_FIELDS,
    build_field_authorization_policy,
)
from character_intelligence.intent import CharacterDesignIntent
from character_intelligence.planner import (
    CharacterConceptSeedStatus,
    CharacterConceptSeedV2,
    CharacterConceptSelectionV2,
    CharacterDesignPlan,
    CharacterPlanningV2Phase4Result,
    GenerationSpecValidationReason,
    GenerationSpecValidator,
    ResolvedCharacterGenerationSpecV1,
    freeze_resolved_character_generation_spec,
)
from character_intelligence.planner.character_planner_v2 import run_character_planner_v1
from character_intelligence.planner.concept_search_v2 import (
    ConceptSearchDiagnostics,
    ConceptSearchResult,
    ConceptSelectionDiagnostics,
    ConceptSelectionResult,
)
from character_intelligence.planner.decision_metadata import (
    DecisionMetadataSet,
    build_resolution_input,
    legacy_selector_to_resolution_result,
)
from combat_semantics import CombatRoleProfile


def _seed(concept_id: str, index: int, status: CharacterConceptSeedStatus) -> CharacterConceptSeedV2:
    return CharacterConceptSeedV2(
        concept_id=concept_id,
        one_line_identity=f"Direction {index} identity.",
        dramatic_axis=f"Direction {index} chooses between duty and trust.",
        character_contradiction=f"Direction {index} seeks control while fearing dependence.",
        player_hook=f"Direction {index} invites the player to test a guarded promise.",
        relationship_axis=f"Direction {index} builds tension through risk.",
        gameplay_fantasy=f"Direction {index} protects allies during a response window.",
        visual_anchor=f"Direction {index} uses an asymmetrical silhouette.",
        differentiation_basis=(f"Direction {index} uses a distinct pressure source.",),
        major_risk=f"Direction {index} could become familiar.",
        status=status,
    )


def _naming_proposal() -> dict[str, object]:
    """Keep the frozen-Spec fixture bound to the Planner naming contract."""

    common = {
        "identity_kind": "PERSONAL_NAME",
        "identity_rationale": "A distinct personal name for the proposed character.",
        "cultural_inspiration": "An original name selected for the fixture.",
        "phonetic_rationale": "The sound is clear and easy to distinguish.",
        "character_alignment": "The measured sound fits a composed character.",
        "tradeoffs": "The name favors clarity over ornament.",
    }
    return {
        "candidates": [
            {"candidate_id": "name_1", "name": "林序", "naming_style": "中文意象名：克制的双字组合", **common},
            {"candidate_id": "name_2", "name": "Mira Voss", "naming_style": "外语姓名：双音节名与短姓", **common},
            {"candidate_id": "name_3", "name": "Thalen", "naming_style": "原创幻想构词：轻辅音开头", **common},
        ],
        "selected_candidate_id": "name_2",
        "selection_reasons": ["The candidate is concise and distinct."],
        "rejected_candidates": [],
    }


def _prepared(*, combat: bool = True):
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",)) if combat else None
    seeds = tuple(_seed(f"concept_{index}", index, CharacterConceptSeedStatus.PROPOSED) for index in range(1, 4))
    selected = _seed("concept_2", 2, CharacterConceptSeedStatus.SELECTED)
    selection = CharacterConceptSelectionV2(
        selected_concept_id=selected.concept_id,
        selection_reasons=("The selected direction preserves the requested tension.",),
    )
    phase4 = CharacterPlanningV2Phase4Result(
        search=ConceptSearchResult(
            seeds=seeds,
            diagnostics=ConceptSearchDiagnostics(
                logical_invocation_count=1,
                concept_count=3,
                distinct_axes=("dramatic_axis", "visual_anchor"),
                structured_parse_succeeded=True,
            ),
        ),
        selection=ConceptSelectionResult(
            seeds=seeds,
            selection=selection,
            selected_seed=selected,
            diagnostics=ConceptSelectionDiagnostics(
                logical_invocation_count=1,
                selected_concept_id=selected.concept_id,
                structured_parse_succeeded=True,
            ),
        ),
        planner=object(),
    )
    metadata = DecisionMetadataSet.from_selector(seeds, selection)
    resolution = legacy_selector_to_resolution_result(build_resolution_input(phase4, metadata))

    request = CharacterDesignRequest(
        "A calm support character.",
        hard_constraints=("faction_id=faction_001",),
        soft_preferences=("calm",),
        desired_connections=("char_001",),
        request_id="spec_test_001",
        combat_role_profile=profile,
    )
    plan = CharacterDesignPlan.from_intent(
        CharacterDesignIntent(raw_request=request.brief, combat_role_profile=profile)
    )
    context = assemble_character_planning_context_v2(
        plan,
        request=request.to_dict(),
        canon_records={"char_001": {"id": "char_001", "name": {"display_name": "Ally"}}},
        project_roster_records=(
            {"id": "char_001", "name": {"display_name": "Ally"}, "faction_id": "faction_001"},
        ),
        relationships=(
            {"relation_id": "rel_001", "source_id": "char_001", "target_id": "char_001", "relation_type": "ally"},
        ),
        story_records={"story_001": {"title": "Opening", "premise": "A bounded fact."}},
        combat_role_profiles={"char_001": profile} if profile else {},
    )
    planner = run_character_planner_v1(
        context.plan_v2,
        context,
        ScriptedAgentModel(
            [
                ModelTurn(
                    structured_output={
                        "character_core": {"core_desire": "Protect without control."},
                        "character_naming": _naming_proposal(),
                    }
                )
            ]
        ),
        selected_concept_seed=selected,
    )
    evidence_source = context.canon[0].source.source_id
    typed_policy = build_field_authorization_policy(
        new_design_fields=CHARACTER_GENERATION_FIELDS
    ).to_dict()
    field_states = {
        field_name: authorization["state"]
        for field_name, authorization in typed_policy["field_authorizations"].items()
    }
    field_states.update(
        {
            "faction_id": "CANON_GROUNDED_ONLY",
            "identity": "NEW_DESIGN_AUTHORIZED",
            "combat_role": "CANON_GROUNDED_ONLY",
        }
    )
    field_authorization = {
        **typed_policy,
        "field_states": field_states,
        "FIELD_AUTHORIZATION_COMPLETE": "YES",
        "FIELD_AUTHORIZATION_DISJOINT": "YES",
        "rules": {"identity": ["planner proposal"]},
    }
    return {
        "request": request,
        "context": context,
        "resolution": resolution,
        "planner": planner,
        "selected": selected,
        "evidence_source": evidence_source,
        "field_authorization": field_authorization,
        "profile": profile,
    }


def _freeze(data: dict[str, object], **overrides: object) -> ResolvedCharacterGenerationSpecV1:
    values = {
        **data,
        "evidence_snapshot_id": "evidence:spec-test",
        "authorized_evidence_source_ids": (data["evidence_source"],),
        "evidence_supported_fields": ("faction_id",),
        "field_authorization": data["field_authorization"],
        "canon_exact_values": {"faction_id": "faction_001"},
        "required_generation_fields": {
            "identity": {"authority": "PLANNER", "boundary": "story", "allowed_freedom": True}
        },
        **overrides,
    }
    selected = values.pop("selected_seed", values.pop("selected"))
    values.pop("evidence_source")
    values.pop("profile")
    return freeze_resolved_character_generation_spec(
        values.pop("request"),
        values.pop("context"),
        values.pop("resolution"),
        values.pop("planner"),
        selected_seed=selected,
        **values,
    )


def test_freeze_returns_versioned_immutable_semantic_and_audit_sections() -> None:
    data = _prepared()
    spec = _freeze(data)

    assert isinstance(spec, ResolvedCharacterGenerationSpecV1)
    assert spec.spec_version == "resolved-character-generation-spec/v1"
    assert spec.route_identity == "CHARACTER_GENERATION_V2"
    assert spec.resolved_direction.concept_id == "concept_2"
    assert spec.audit_metadata.resolution_action == "SELECT"
    assert "evidence_snapshot_id" not in spec.to_model_input()
    assert "metadata" not in spec.to_model_input()
    with pytest.raises((AttributeError, TypeError)):
        spec.request_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        spec.field_authorization["field_states"]["identity"] = "UNAUTHORIZED"  # type: ignore[index]


def test_freeze_is_deterministic_and_canonicalizes_id_order() -> None:
    first_data = _prepared()
    second_data = _prepared()
    first = _freeze(first_data, allowed_relationship_targets=("char_001",), allowed_faction_ids=("faction_001",))
    second = _freeze(second_data, allowed_relationship_targets=("char_001",), allowed_faction_ids=("faction_001",))

    assert first.spec_id == second.spec_id
    assert first.spec_digest == second.spec_digest
    assert first.semantic_dict() == second.semantic_dict()
    assert GenerationSpecValidator().validate(first).reason is GenerationSpecValidationReason.VALID


def test_source_mutation_does_not_change_frozen_nested_values() -> None:
    data = _prepared()
    mutable_policy = data["field_authorization"]
    spec = _freeze(data, field_authorization=mutable_policy)
    mutable_policy["rules"]["identity"].append("mutated")  # type: ignore[index]
    assert tuple(spec.field_authorization["rules"]["identity"]) == ("planner proposal",)  # type: ignore[index]


def test_freeze_rejects_lineage_hard_canon_relationship_evidence_and_gap_failures() -> None:
    data = _prepared()
    wrong_seed = _seed("concept_1", 1, CharacterConceptSeedStatus.SELECTED)
    with pytest.raises(Exception) as seed_error:
        _freeze(data, selected_seed=wrong_seed)
    assert getattr(seed_error.value, "reason", None) is GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH

    conflict_request = replace(data["request"], hard_constraints=("same",), forbidden_elements=("same",))
    with pytest.raises(Exception) as constraint_error:
        _freeze({**data, "request": conflict_request})
    assert getattr(constraint_error.value, "reason", None) is GenerationSpecValidationReason.HARD_FORBIDDEN_CONFLICT

    with pytest.raises(Exception) as canon_error:
        _freeze(data, canon_exact_values={"faction_id": "faction_999"})
    assert getattr(canon_error.value, "reason", None) is GenerationSpecValidationReason.CANON_CONFLICT

    with pytest.raises(Exception) as evidence_error:
        _freeze(data, authorized_evidence_source_ids=("unknown-source",))
    assert getattr(evidence_error.value, "reason", None) is GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE

    with pytest.raises(Exception) as relation_error:
        _freeze(data, allowed_relationship_targets=("unknown-character",))
    assert getattr(relation_error.value, "reason", None) is GenerationSpecValidationReason.INVALID_RELATIONSHIP_TARGET

    blocking_context = replace(
        data["context"],
        gaps=data["context"].gaps + (ContextGap(ContextGapCode.CANON_CONTEXT_UNAVAILABLE, "canon", "missing"),),
    )
    with pytest.raises(Exception) as gap_error:
        _freeze({**data, "context": blocking_context})
    assert getattr(gap_error.value, "reason", None) is GenerationSpecValidationReason.BLOCKING_GAP


def test_non_combat_and_combat_specs_have_explicit_optional_semantics() -> None:
    non_combat = _freeze(_prepared(combat=False))
    combat = _freeze(_prepared(combat=True))
    assert non_combat.combat_semantics is None
    assert combat.combat_semantics is not None
