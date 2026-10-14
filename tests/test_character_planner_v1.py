from __future__ import annotations

import json

import pytest

from agents import ModelTurn, ScriptedAgentModel
from character_intelligence.context import (
    CHARACTER_PLANNING_CONTEXT_V2_SCHEMA,
    AcceptanceState,
    CanonContextItem,
    CharacterPlanningContextV2,
    CombatPlanningContext,
    ContextAuthority,
    ContextGap,
    ContextGapCode,
    ContextSource,
    RosterCharacterContext,
    RosterMembershipStatus,
    RosterSourceClass,
    WorldCharacterStatus,
)
from character_intelligence.intent import CharacterDesignIntent
from character_intelligence.planner import (
    CharacterDesignPlan,
    CharacterPlannerV1Error,
    plan_character_v2,
    run_character_planner_v1,
)
from character_intelligence.planner.character_plan_v2 import (
    CharacterDesignPlanV2,
    CharacterDesignPlanV2Status,
    CharacterPlanV2Owner,
    CharacterPlanV2RelationshipBinding,
    CharacterPlanV2RelationshipStrategy,
    CharacterPlanV2Source,
)
from combat_semantics import CombatRoleProfile


def _source(source_id: str, authority: ContextAuthority) -> ContextSource:
    return ContextSource(source_id, "fixture", authority, "controlled Planner test context")


def _context(*, gaps: tuple[ContextGap, ...] = ()) -> CharacterPlanningContextV2:
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",))
    intent = CharacterDesignIntent(
        raw_request="设计一个冷静但不冷漠的辅助角色",
        combat_role_profile=profile,
    )
    v1 = CharacterDesignPlan.from_intent(intent)
    request = {
        "request_id": "planner_test_001",
        "hard_constraints": ["faction=faction_005"],
        "soft_preferences": ["冷静但不冷漠"],
        "desired_connections": ["character_001"],
        "combat_role_profile": profile.to_dict(),
    }
    from character_intelligence.planner.character_plan_v2 import project_character_plan_v2

    shadow = project_character_plan_v2(v1, request=request)
    roster = RosterCharacterContext(
        character_id="character_001",
        display_name="Existing Ally",
        origin="fixture",
        source=_source("character_001", ContextAuthority.PROJECT_ROSTER),
        source_class=RosterSourceClass.CANON_PROJECT_CHARACTER,
        membership_status=RosterMembershipStatus.IN_PROJECT_ROSTER,
        world_status=WorldCharacterStatus.PROJECT_ROSTER_CHARACTER,
        acceptance_state=AcceptanceState.ACCEPTANCE_STATE_UNKNOWN,
        faction_id="faction_005",
        combat_role_profile=profile,
    )
    return CharacterPlanningContextV2(
        schema_version=CHARACTER_PLANNING_CONTEXT_V2_SCHEMA,
        snapshot_id="snapshot_planner_test_001",
        intent=intent,
        plan_v1=v1,
        plan_v2=shadow,
        roster=(roster,),
        canon=(CanonContextItem(
            "character_001",
            "character",
            "Existing Ally",
            "A Canon character.",
            _source("character_001", ContextAuthority.PROJECT_CANON),
        ),),
        canon_relationships=(),
        combat=CombatPlanningContext(
            requested_role_profile=profile,
            occupied_role_profiles=(profile,),
            semantic_metadata=("canonical support role",),
        ),
        gaps=gaps,
    )


def _run(output: dict, *, context: CharacterPlanningContextV2 | None = None):
    context = context or _context()
    proposal = dict(output)
    wrapped_plan = proposal.get("character_design_plan")
    if isinstance(wrapped_plan, dict):
        wrapped_plan = dict(wrapped_plan)
        wrapped_plan.setdefault("character_naming", _naming_proposal())
        proposal["character_design_plan"] = wrapped_plan
    else:
        proposal.setdefault("character_naming", _naming_proposal())
    model = ScriptedAgentModel([ModelTurn(structured_output=proposal)])
    result = run_character_planner_v1(context.plan_v2, context, model)
    return result, model


def _naming_proposal() -> dict[str, object]:
    """Supply a valid naming decision so Planner fixtures exercise the full contract."""

    common = {
        "identity_kind": "PERSONAL_NAME",
        "identity_rationale": "The name reads as a personal name rather than a job title.",
        "cultural_inspiration": "An original name selected for this test fixture.",
        "phonetic_rationale": "The spoken form is distinct and easy to remember.",
        "character_alignment": "The measured sound supports a composed character.",
        "tradeoffs": "The name favors clarity over elaborate symbolism.",
    }
    candidates = (
        {
            "candidate_id": "name_1",
            "name": "林序",
            "naming_style": "中文意象名：克制的双字组合",
            **common,
        },
        {
            "candidate_id": "name_2",
            "name": "Mira Voss",
            "naming_style": "外语姓名：双音节名与短姓",
            **common,
        },
        {
            "candidate_id": "name_3",
            "name": "Thalen",
            "naming_style": "原创幻想构词：轻辅音开头",
            **common,
        },
    )
    return {
        "candidates": candidates,
        "selected_candidate_id": "name_2",
        "selection_reasons": ["The candidate is concise and distinct from existing names."],
        "rejected_candidates": [],
    }


def test_planner_prompt_keeps_name_identity_and_cultural_evidence_separate() -> None:
    _, model = _run({"character_core": {"core_desire": "To protect a team without controlling it."}})

    prompt = model.prompts[0].system_contract
    assert "Chinese-script name is not evidence of Chinese cultural origin" in prompt
    assert "proposed player-facing display name" in prompt
    assert "Do not construct a Chinese name by joining personality, occupation, ability" in prompt
    assert "same-sounding or confusing names of well-known real people" in prompt
    assert "User-explicit names are preserved deterministically after your proposal" in prompt


def test_planner_makes_one_structured_call_and_marks_provenance() -> None:
    result, model = _run(
        {
            "character_core": {
                "surface_impression": "Measured and attentive.",
                "core_desire": "To protect a team without controlling it.",
            },
            "narrative_role": {
                "dramatic_function": "Expose the cost of a group's untested assumptions."
            },
            "visual_identity": {"silhouette_direction": "Compact, stable, and easy to read at a glance."},
        }
    )

    assert len(model.prompts) == 1
    assert model.prompts[0].response_format == "character_planner_proposal"
    assert model.prompts[0].invocation_purpose == "character_planner_v1"
    assert result.plan.status is CharacterDesignPlanV2Status.PROPOSED
    assert result.plan.character_core.core_desire == "To protect a team without controlling it."
    assert any(
        item.field_path == "character_core.core_desire"
        and item.owner is CharacterPlanV2Owner.PLANNER
        and item.source is CharacterPlanV2Source.PLANNER_PROPOSAL
        for item in result.plan.decisions
    )
    assert result.diagnostics.logical_invocation_count == 1
    assert json.loads(json.dumps(result.to_dict(), ensure_ascii=False))


def test_planner_preserves_hard_constraints_canon_combat_and_requested_relations() -> None:
    context = _context()
    result, _ = _run(
        {
            "gameplay_identity": {
                "gameplay_fantasy": "Protect an ally during a brief response window.",
                "mechanic_identity_direction": "enemy_driven",
            },
            "relationship_strategy": {
                "proposed_relationship_opportunities": [
                    {"target": "character_001", "description": "Their different risk tolerances create a useful cooperation/conflict axis."}
                ]
            },
        },
        context=context,
    )

    assert result.plan.constraints == context.plan_v2.constraints
    assert result.plan.gameplay_identity.combat_role_profile == context.plan_v2.gameplay_identity.combat_role_profile
    assert result.plan.relationship_strategy.requested_relationships == context.plan_v2.relationship_strategy.requested_relationships
    proposal = result.plan.relationship_strategy.proposed_relationship_opportunities[0]
    assert proposal.source is CharacterPlanV2Source.PLANNER_PROPOSAL
    assert result.plan.relationship_strategy.canon_grounded_relationships == ()
    assert result.plan.product_roster_positioning == context.plan_v2.product_roster_positioning


def test_provider_full_plan_drift_is_projected_without_overwriting_authority() -> None:
    context = _context()
    result, _ = _run(
        {
            "status": "proposed",
            "constraints": [{"key": "provider-drift"}],
            "gameplay_identity": {
                "combat_role_profile": {
                    "primary_role": "dps",
                    "secondary_roles": [],
                },
                "gameplay_fantasy": "Protect an ally during a brief response window.",
            },
        },
        context=context,
    )

    assert result.plan.gameplay_identity.gameplay_fantasy == (
        "Protect an ally during a brief response window."
    )
    assert result.plan.gameplay_identity.combat_role_profile == (
        context.plan_v2.gameplay_identity.combat_role_profile
    )


def test_provider_proposal_wrapper_is_unwrapped_at_the_boundary() -> None:
    result, _ = _run(
        {
            "character_design_plan": {
                "character_core": {"core_desire": "To protect a team without controlling it."}
            }
        }
    )

    assert result.plan.character_core.core_desire == (
        "To protect a team without controlling it."
    )


def test_gaps_stay_visible_and_product_acceptance_story_claims_cannot_be_added() -> None:
    gaps = (
        ContextGap(ContextGapCode.PRODUCT_POSITIONING_UNAVAILABLE, "product", "No product data."),
        ContextGap(ContextGapCode.ROSTER_COMBAT_COVERAGE_INCOMPLETE, "combat", "Combat coverage is incomplete."),
        ContextGap(ContextGapCode.ROSTER_STORY_STATUS_UNAVAILABLE, "story", "Story status is unavailable."),
        ContextGap(ContextGapCode.HUMAN_ACCEPTANCE_STATE_UNAVAILABLE, "acceptance", "Acceptance is unavailable."),
    )
    result, model = _run(
        {
            "character_core": {"core_fear": "Acting too soon."},
            "reference_basis": {"coverage_notes": ["Combat differentiation cannot be established from current roster evidence."]},
        },
        context=_context(gaps=gaps),
    )

    assert result.plan.product_roster_positioning.roster_role is None
    assert all(f"CONTEXT_GAP:{gap.code.value}" in result.plan.warnings for gap in gaps)
    assert set(result.diagnostics.gap_codes) == {gap.code.value for gap in gaps}
    serialized_prompt = json.dumps(model.prompts[0].authoring_payload, ensure_ascii=False)
    assert "PRODUCT_POSITIONING_UNAVAILABLE" in serialized_prompt
    assert "ACCEPTANCE_STATE_UNKNOWN" in serialized_prompt


@pytest.mark.parametrize(
    "case_output",
    [
        {"character_core": {"core_desire": "A bounded desire."}},
        {"narrative_role": {"story_entry_function": "An entry opportunity, not an existing plot fact."}},
        {"visual_identity": {"motif_direction": "A motif with a clear narrative reason."}},
        {"arc_seed": {"unresolved_future_hook": "A future question remains open."}},
        {"risks": {"roster_overlap_risks": ["Observed overlap requires a later authoring distinction."]}},
    ],
)
def test_focused_planner_fixtures_produce_a_proposed_plan(case_output: dict) -> None:
    result, _ = _run(case_output)
    assert result.plan.status is CharacterDesignPlanV2Status.PROPOSED
    assert result.diagnostics.structured_parse_succeeded is True


@pytest.mark.parametrize(
    "bad_output",
    [
        {"status": "CANON"},
        {"product_roster_positioning": {"roster_role": "premium"}},
        {"gameplay_identity": {"combat_role_profile": {"primary_role": "healer"}}},
        {"relationship_strategy": {"canon_grounded_relationships": []}},
        {"character_core": {"core_desire": None}},
    ],
)
def test_planner_rejects_authority_collapsing_or_unresolved_output(bad_output: dict) -> None:
    with pytest.raises(CharacterPlannerV1Error):
        _run(bad_output)


def test_planner_requires_the_context_shadow_binding() -> None:
    context = _context()
    other = replace_plan_status(context.plan_v2)
    model = ScriptedAgentModel([ModelTurn(structured_output={"character_core": {"core_desire": "x"}})])
    with pytest.raises(ValueError, match="context.plan_v2"):
        plan_character_v2(other, context, model)


def replace_plan_status(plan: CharacterDesignPlanV2) -> CharacterDesignPlanV2:
    return CharacterDesignPlanV2(
        intent=plan.intent,
        request_id="different_shadow",
        status=plan.status,
        constraints=plan.constraints,
        relationship_strategy=CharacterPlanV2RelationshipStrategy(
            requested_relationships=(
                CharacterPlanV2RelationshipBinding("other", CharacterPlanV2Source.USER_SUPPLIED),
            )
        ),
    )
