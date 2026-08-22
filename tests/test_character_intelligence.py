from __future__ import annotations

import json

import pytest

from agents import CharacterGenerationAgent, DeterministicCharacterGenerationModel
from character_intelligence import CharacterDesignIntent, CharacterDesignIntentParser
from character_intelligence.planner import CharacterDesignPlan


def test_parser_extracts_a_regular_character_brief():
    intent = CharacterDesignIntentParser().parse("设计一个冷静的辅助型女性角色")

    assert intent.role_type == "女性"
    assert intent.combat_role == "support"
    assert "冷静" in intent.personality_keywords
    assert intent.rarity is None
    assert intent.target_audience == "general"


def test_parser_extracts_five_star_fire_main_dps_girl():
    intent = CharacterDesignIntentParser().parse(
        "设计一个五星火属性爆发型少女角色，定位为主C，性格外向但有隐藏压力"
    )

    assert intent.rarity == 5
    assert intent.element == "fire"
    assert intent.combat_role == "dps"
    assert intent.combat_role_profile.primary_role == "main_dps"
    assert intent.combat_role_profile.secondary_roles == ()
    assert intent.role_type == "少女"
    assert {"外向", "隐藏压力"} <= set(intent.personality_keywords)
    assert {"fire", "element:fire", "burst"} <= set(intent.design_goals)


def test_parser_extracts_combat_roles_and_forbidden_patterns():
    intent = CharacterDesignIntentParser().parse("设计一个治疗辅助角色，避免复杂数值系统")

    assert intent.combat_role == "healer"
    assert intent.combat_role_profile.primary_role == "healer"
    assert intent.combat_role_profile.secondary_roles == ("support",)
    assert intent.forbidden_patterns == ("复杂数值系统",)


def test_parser_has_safe_defaults_when_keywords_are_missing():
    intent = CharacterDesignIntentParser().parse("设计一个角色")

    assert intent == CharacterDesignIntent(raw_request="设计一个角色")
    assert intent.to_dict()["personality_keywords"] == []
    assert json.dumps(intent.to_dict(), ensure_ascii=False)


def test_plan_serializes_and_projects_intent_to_generation_constraints():
    plan = CharacterDesignPlan.from_text("五星火属性少女，主C，外向")

    assert "rarity=5" not in plan.generation_constraints
    assert "element=fire" not in plan.generation_constraints
    assert "combat_role=dps" not in plan.generation_constraints
    assert "外向" in plan.recommended_traits
    assert json.dumps(plan.to_dict(), ensure_ascii=False)


def test_plan_projects_only_draft_representable_combat_roles():
    plan = CharacterDesignPlan.from_text("设计一个辅助角色")

    assert plan.generation_constraints == ()
    assert plan.combat_role_profile.primary_role == "support"


def test_plan_propagates_main_dps_into_generation_contract():
    plan = CharacterDesignPlan.from_text("设计一个主C角色")

    assert plan.parsed_intent.combat_role == "dps"
    assert plan.combat_role_profile.primary_role == "main_dps"
    assert plan.generation_constraints == ()


def test_parser_preserves_multi_role_mention_order():
    intent = CharacterDesignIntentParser().parse("support + sub_dps")

    assert intent.combat_role_profile.primary_role == "support"
    assert intent.combat_role_profile.secondary_roles == ("sub_dps",)


def test_parser_supports_literal_main_and_sub_roles():
    main = CharacterDesignIntentParser().parse("main_dps")
    sub = CharacterDesignIntentParser().parse("sub_dps")

    assert main.combat_role_profile.primary_role == "main_dps"
    assert sub.combat_role_profile.primary_role == "sub_dps"


def test_parser_preserves_main_dps_plus_support():
    intent = CharacterDesignIntentParser().parse("main_dps + support")

    assert intent.combat_role_profile.primary_role == "main_dps"
    assert intent.combat_role_profile.secondary_roles == ("support",)


def test_explicit_primary_marker_overrides_mention_order():
    intent = CharacterDesignIntentParser().parse("support，主定位为 sub_dps")

    assert intent.combat_role_profile.primary_role == "sub_dps"
    assert intent.combat_role_profile.secondary_roles == ("support",)


def test_healer_is_not_collapsed_into_support():
    intent = CharacterDesignIntentParser().parse("healer + support")

    assert intent.combat_role_profile.primary_role == "healer"
    assert intent.combat_role_profile.secondary_roles == ("support",)


def test_non_role_combat_terms_do_not_become_canonical_roles():
    for text, legacy_value in (("burst", "burst"), ("sustain", "sustain"), ("hybrid", "hybrid")):
        intent = CharacterDesignIntentParser().parse(text)
        assert intent.combat_role_profile.is_unspecified
        assert intent.combat_role == legacy_value


def test_duplicate_aliases_are_rejected_by_canonical_profile():
    from combat_semantics import CombatRoleProfile

    with pytest.raises(ValueError, match="primary_role"):
        CombatRoleProfile(primary_role="support", secondary_roles=("support",))


def test_duplicate_role_aliases_do_not_create_duplicate_profile_roles():
    intent = CharacterDesignIntentParser().parse("support + team_support")

    assert intent.combat_role_profile.primary_role == "support"
    assert intent.combat_role_profile.secondary_roles == ()


def test_duplicate_defense_aliases_do_not_create_duplicate_profile_roles():
    intent = CharacterDesignIntentParser().parse("tank + defender + frontline_defender")

    assert intent.combat_role_profile.primary_role == "defense"
    assert intent.combat_role_profile.secondary_roles == ()


def test_bare_dps_requires_role_context():
    role_request = CharacterDesignIntentParser().parse("design a DPS character")
    unrelated_text = CharacterDesignIntentParser().parse("show the DPS number")

    assert role_request.combat_role_profile.primary_role == "main_dps"
    assert unrelated_text.combat_role_profile.is_unspecified


def test_intent_rejects_conflicting_scalar_and_profile_sources():
    from combat_semantics import CombatRoleProfile

    with pytest.raises(ValueError, match="derived compatibility projection"):
        CharacterDesignIntent(
            combat_role="support",
            combat_role_profile=CombatRoleProfile(primary_role="main_dps"),
        )


def test_generation_constraints_do_not_project_combat_roles():
    for request in ("support", "healer", "main_dps", "sub_dps", "control", "defense"):
        assert CharacterDesignPlan.from_text(request).generation_constraints == ()


def test_optional_intent_generation_keeps_legacy_entry_point_unchanged():
    legacy = CharacterGenerationAgent(DeterministicCharacterGenerationModel()).generate(
        "设计一个完全原创的角色"
    )
    model = DeterministicCharacterGenerationModel()
    result = CharacterGenerationAgent(model).generate_with_intent("设计一个五星火属性主C角色")

    assert legacy.design_plan is None
    assert result.design_plan is not None
    assert result.design_plan.parsed_intent.rarity == 5
    assert result.design_plan.parsed_intent.element == "fire"
    first_runtime = model.prompts[0].runtime
    assert "rarity=5" not in first_runtime.hard_constraints
    assert "element=fire" not in first_runtime.hard_constraints
    assert "combat_role=dps" not in first_runtime.hard_constraints
