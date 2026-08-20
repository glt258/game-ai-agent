from __future__ import annotations

import json

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
    assert intent.role_type == "少女"
    assert {"外向", "隐藏压力"} <= set(intent.personality_keywords)
    assert {"fire", "element:fire", "burst"} <= set(intent.design_goals)


def test_parser_extracts_combat_roles_and_forbidden_patterns():
    intent = CharacterDesignIntentParser().parse("设计一个治疗辅助角色，避免复杂数值系统")

    assert intent.combat_role == "support"
    assert intent.forbidden_patterns == ("复杂数值系统",)


def test_parser_has_safe_defaults_when_keywords_are_missing():
    intent = CharacterDesignIntentParser().parse("设计一个角色")

    assert intent == CharacterDesignIntent(raw_request="设计一个角色")
    assert intent.to_dict()["personality_keywords"] == []
    assert json.dumps(intent.to_dict(), ensure_ascii=False)


def test_plan_serializes_and_projects_intent_to_generation_constraints():
    plan = CharacterDesignPlan.from_text("五星火属性少女，主C，外向")

    assert "rarity=5" in plan.generation_constraints
    assert "element=fire" in plan.generation_constraints
    assert "combat_role=dps" in plan.generation_constraints
    assert "外向" in plan.recommended_traits
    assert json.dumps(plan.to_dict(), ensure_ascii=False)


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
    assert "rarity=5" in first_runtime.hard_constraints
    assert "element=fire" in first_runtime.hard_constraints
    assert "combat_role=dps" in first_runtime.hard_constraints
