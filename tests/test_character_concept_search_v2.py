from __future__ import annotations

import json
from dataclasses import replace

import pytest

from agents import ModelTurn, ScriptedAgentModel
from character_intelligence.context import assemble_character_planning_context_v2
from character_intelligence.intent import CharacterDesignIntent
from character_intelligence.planner import (
    CharacterConceptSeedStatus,
    CharacterConceptSeedV2,
    CharacterConceptSelectionV2,
    CharacterConceptV2Error,
    CharacterDesignPlan,
    CharacterPlanningV2Phase4Result,
    build_character_concept_search_schema,
    build_concept_search_prompt,
    build_concept_selector_prompt,
    run_character_planning_v2_phase4,
    run_concept_selector_v2,
    validate_character_concept_search_response,
    validate_concept_seed_set,
)
from character_intelligence.planner.character_plan_v2 import CharacterPlanV2Source
from combat_semantics import CombatRoleProfile


def _context():
    profile = CombatRoleProfile(primary_role="support", secondary_roles=("control",))
    plan = CharacterDesignPlan.from_intent(
        CharacterDesignIntent(
            raw_request="设计一个冷静但不冷漠的辅助角色",
            combat_role_profile=profile,
        )
    )
    return assemble_character_planning_context_v2(
        plan,
        request={
            "request_id": "concept_search_test_001",
            "hard_constraints": ["faction=faction_005"],
            "soft_preferences": ["冷静但不冷漠"],
            "desired_connections": ["character_001"],
            "combat_role_profile": profile.to_dict(),
        },
        canon_records={
            "character_001": {
                "id": "character_001",
                "name": {"display_name": "Existing Ally"},
            }
        },
        project_roster_records=(
            {"id": "character_001", "name": {"display_name": "Existing Ally"}},
        ),
        combat_role_profiles={"character_001": profile},
    )


def _seed(concept_id: str, index: int) -> dict[str, object]:
    return {
        "concept_id": concept_id,
        "one_line_identity": f"Direction {index} identity.",
        "dramatic_axis": f"Direction {index} must choose between duty and trust.",
        "character_contradiction": f"Direction {index} seeks control while fearing dependence.",
        "player_hook": f"Direction {index} invites the player to test a guarded promise.",
        "relationship_axis": f"Direction {index} builds tension through different risk tolerances.",
        "gameplay_fantasy": f"Direction {index} protects allies during a short response window.",
        "visual_anchor": f"Direction {index} uses a clear asymmetrical silhouette.",
        "differentiation_basis": [f"Direction {index} is grounded in a different source of pressure."],
        "major_risk": f"Direction {index} could become too familiar if its contradiction is not sharpened.",
    }


def _seeds() -> tuple[CharacterConceptSeedV2, ...]:
    return tuple(
        CharacterConceptSeedV2.from_provider_mapping(_seed(f"concept_{index}", index))
        for index in range(1, 4)
    )


def _search_output() -> dict[str, object]:
    return {"concepts": [_seed(f"concept_{index}", index) for index in range(1, 4)]}


def test_seed_is_thin_immutable_and_planner_proposal_sourced() -> None:
    seed = _seeds()[0]

    assert seed.source is CharacterPlanV2Source.PLANNER_PROPOSAL
    assert seed.status is CharacterConceptSeedStatus.PROPOSED
    assert set(seed.to_provider_dict()) == {
        "concept_id",
        "one_line_identity",
        "dramatic_axis",
        "character_contradiction",
        "player_hook",
        "relationship_axis",
        "gameplay_fantasy",
        "visual_anchor",
        "differentiation_basis",
        "major_risk",
    }
    assert CharacterConceptSeedV2.from_mapping(seed.to_dict()) == seed
    assert json.loads(json.dumps(seed.to_dict())) == seed.to_dict()
    with pytest.raises(Exception):
        seed.concept_id = "changed"  # type: ignore[misc]


def test_search_schema_requires_exactly_three_thin_seeds() -> None:
    schema = build_character_concept_search_schema()

    assert schema["properties"]["concepts"]["minItems"] == 3
    assert schema["properties"]["concepts"]["maxItems"] == 3
    assert set(schema["properties"]["concepts"]["items"]["required"]) == set(
        _seed("x", 0)
    )
    assert "product_roster_positioning" not in schema["properties"]["concepts"]["items"]["properties"]


def test_search_validation_requires_unique_ids_and_three_distinct_axes() -> None:
    assert validate_character_concept_search_response(_search_output()) == _seeds()

    duplicate = _search_output()
    duplicate["concepts"] = [_seed("concept_1", 1), _seed("concept_1", 2), _seed("concept_3", 3)]
    with pytest.raises(CharacterConceptV2Error, match="unique"):
        validate_character_concept_search_response(duplicate)

    insufficient = tuple(
        replace(_seeds()[0], concept_id=f"concept_{index}")
        for index in range(1, 4)
    )
    with pytest.raises(CharacterConceptV2Error, match="diverse"):
        validate_concept_seed_set(insufficient)


def test_prompts_bound_search_and_selection_without_product_or_most_unique_claims() -> None:
    context = _context()
    search_prompt = build_concept_search_prompt(context)
    selector_prompt = build_concept_selector_prompt(context, _seeds())

    assert search_prompt.response_format == "character_concept_search"
    assert search_prompt.authoring_payload["required_concept_count"] == 3
    search_text = json.dumps(search_prompt.authoring_payload, ensure_ascii=False)
    assert "PRODUCT_POSITIONING_UNAVAILABLE" in search_text
    assert "stylistic or adjective variations" in search_prompt.system_contract
    assert selector_prompt.response_format == "character_concept_selection"
    assert {seed["concept_id"] for seed in selector_prompt.authoring_payload["candidate_seeds"]} == {
        "concept_1",
        "concept_2",
        "concept_3",
    }
    assert "most unique" in selector_prompt.system_contract


def test_selector_points_to_existing_seed_without_mutating_provider_content() -> None:
    context = _context()
    seeds = _seeds()
    before = [seed.to_provider_dict() for seed in seeds]
    model = ScriptedAgentModel(
        [ModelTurn(structured_output={"selected_concept_id": "concept_2", "selection_reasons": ["Best fit."]})]
    )

    result = run_concept_selector_v2(context, seeds, model)

    assert isinstance(result.selection, CharacterConceptSelectionV2)
    assert result.selected_seed.status is CharacterConceptSeedStatus.SELECTED
    assert result.selected_seed.to_provider_dict() == before[1]
    assert [seed.to_provider_dict() for seed in seeds] == before
    assert result.diagnostics.logical_invocation_count == 1
    assert len(model.prompts) == 1

    with pytest.raises(CharacterConceptV2Error, match="unknown concept ID"):
        run_concept_selector_v2(
            context,
            seeds,
            ScriptedAgentModel(
                [ModelTurn(structured_output={"selected_concept_id": "unknown", "selection_reasons": ["No."]})]
            ),
        )


def test_phase4_pipeline_has_three_calls_and_bridges_selected_seed_to_planner() -> None:
    model = ScriptedAgentModel(
        [
            ModelTurn(structured_output=_search_output()),
            ModelTurn(
                structured_output={
                    "selected_concept_id": "concept_2",
                    "selection_reasons": ["It preserves the hard requirement and offers the clearest relationship tension."],
                    "preserve_elements": ["dramatic_axis", "player_hook"],
                }
            ),
            ModelTurn(
                structured_output={
                    "character_core": {
                        "core_desire": "To protect a team without controlling it."
                    },
                    "gameplay_identity": {
                        "gameplay_fantasy": "Protect an ally during a brief response window."
                    },
                    "character_naming": {
                        "candidates": [
                            {
                                "candidate_id": "name_1",
                                "name": "林序",
                                "identity_kind": "PERSONAL_NAME",
                                "identity_rationale": "A personal name for the proposed character.",
                                "naming_style": "中文意象名：克制的双字组合",
                                "cultural_inspiration": "An original name for this fixture.",
                                "phonetic_rationale": "Its sound is distinct and easy to remember.",
                                "character_alignment": "The measured sound fits the concept.",
                                "tradeoffs": "The name favors clarity over ornament.",
                            },
                            {
                                "candidate_id": "name_2",
                                "name": "Mira Voss",
                                "identity_kind": "PERSONAL_NAME",
                                "identity_rationale": "A personal name for the proposed character.",
                                "naming_style": "外语姓名：双音节名与短姓",
                                "cultural_inspiration": "An original name for this fixture.",
                                "phonetic_rationale": "Its sound is distinct and easy to remember.",
                                "character_alignment": "The measured sound fits the concept.",
                                "tradeoffs": "The name favors clarity over ornament.",
                            },
                            {
                                "candidate_id": "name_3",
                                "name": "Thalen",
                                "identity_kind": "PERSONAL_NAME",
                                "identity_rationale": "A personal name for the proposed character.",
                                "naming_style": "原创幻想构词：轻辅音开头",
                                "cultural_inspiration": "An original name for this fixture.",
                                "phonetic_rationale": "Its sound is distinct and easy to remember.",
                                "character_alignment": "The measured sound fits the concept.",
                                "tradeoffs": "The name favors clarity over ornament.",
                            },
                        ],
                        "selected_candidate_id": "name_2",
                        "selection_reasons": ["The candidate is concise and distinct."],
                        "rejected_candidates": [],
                    },
                }
            ),
        ]
    )
    context = _context()

    result = run_character_planning_v2_phase4(context, model)

    assert isinstance(result, CharacterPlanningV2Phase4Result)
    assert len(model.prompts) == 3
    assert [prompt.response_format for prompt in model.prompts] == [
        "character_concept_search",
        "character_concept_selection",
        "character_planner_proposal",
    ]
    assert result.selection.selected_seed.concept_id == "concept_2"
    assert result.planner.plan.status.value == "PROPOSED"
    assert result.planner.diagnostics.selected_concept_id == "concept_2"
    assert result.logical_invocation_count == 3
    assert any(
        decision.source is CharacterPlanV2Source.CONCEPT_SELECTION
        and decision.field_path == "selected_concept_seed"
        for decision in result.planner.plan.decisions
    )
    planner_payload = model.prompts[2].authoring_payload
    assert planner_payload["selected_concept_seed"]["concept_id"] == "concept_2"
    assert planner_payload["selected_concept_seed"]["dramatic_axis"] == _seed("x", 2)["dramatic_axis"]
    assert planner_payload["selected_concept_seed"]["player_hook"] == _seed("x", 2)["player_hook"]
    assert result.planner.plan.constraints == context.plan_v2.constraints
    assert result.planner.plan.gameplay_identity.combat_role_profile == context.plan_v2.gameplay_identity.combat_role_profile
    assert result.planner.plan.product_roster_positioning == context.plan_v2.product_roster_positioning
    assert result.planner.plan.relationship_strategy.canon_grounded_relationships == ()
