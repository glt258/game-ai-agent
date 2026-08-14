import copy
import json

import pytest

from agents import (
    AgentExecutionError,
    AgentToolError,
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
    ModelMalformedResponseError,
    ModelTurn,
    ScriptedAgentModel,
    ToolCall,
)


def _payload(**overrides):
    payload = {
        "draft_id": "draft_test_001",
        "status": "draft",
        "name": "测试角色",
        "age": 23,
        "age_range": "20-25",
        "gender": "女性",
        "faction_id": None,
        "occupation": "学生",
        "social_role": "校园志愿者",
        "combat_role": "support",
        "design_pitch": "辅助型角色",
        "personality": ["冷静"],
        "background": "新设计背景",
        "story_hook": "新设计钩子",
        "relationships": [],
        "ability_concept": "有限的个人规则概念",
        "knowledge_scope": "公开信息",
        "canon_basis": [{"source_id": "world_rules", "supports": ["world_rules"]}],
        "new_design_elements": ["姓名与性格是新设计"],
        "open_questions": [],
        "constraint_notes": [],
        "story_link": None,
        "proposed_new_content": [],
    }
    payload.update(overrides)
    return payload


def test_offline_generation_returns_grounded_draft_without_mutation():
    from knowledge import KnowledgeResolver

    resolver = KnowledgeResolver()
    before = copy.deepcopy(resolver.characters)
    result = CharacterGenerationAgent(DeterministicCharacterGenerationModel(), resolver=resolver).generate(
        CharacterDesignRequest(
            "设计一个和临洲大学有关的年轻女性角色。与南栈事件存在间接联系。",
            hard_constraints=("20～25岁",),
            forbidden_elements=("秘密政府组织",),
        )
    )
    assert result.draft.status == "draft"
    assert result.draft.draft_id.startswith("draft_")
    assert result.draft.age in range(20, 26)
    assert result.sources
    assert resolver.characters == before


def test_fake_faction_id_is_rejected():
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("w", "get_world_rules", {}),)),
            ModelTurn(
                text=json.dumps(_payload(faction_id="faction_999"), ensure_ascii=False)
            ),
        ]
    )
    agent = CharacterGenerationAgent(model)
    with pytest.raises(AgentExecutionError, match="not grounded"):
        agent.generate("设计一个角色")


def test_unknown_write_tool_is_rejected():
    model = ScriptedAgentModel(
        [ModelTurn(tool_calls=(ToolCall("x", "write_character", {"id": "x"}),))]
    )
    with pytest.raises(AgentToolError, match="forbidden"):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_malformed_draft_is_rejected_strictly():
    model = ScriptedAgentModel([ModelTurn(text=json.dumps({"age": "twenty three"}))])
    with pytest.raises(ModelMalformedResponseError):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_numeric_faction_id_is_not_normalized():
    model = ScriptedAgentModel(
        [ModelTurn(text=json.dumps(_payload(faction_id=123), ensure_ascii=False))]
    )
    with pytest.raises(ModelMalformedResponseError):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_hard_age_constraint_is_enforced():
    model = ScriptedAgentModel(
        [ModelTurn(text=json.dumps(_payload(age=17), ensure_ascii=False))]
    )
    with pytest.raises(AgentExecutionError, match="violates hard constraint"):
        CharacterGenerationAgent(model).generate(
            CharacterDesignRequest("设计一个角色", hard_constraints=("20～25岁",))
        )


def test_authoring_tools_are_read_only_and_reject_paths():
    agent = CharacterGenerationAgent(DeterministicCharacterGenerationModel())
    result = agent.tools.execute(
        tool_name="search_factions", arguments={"query": "大学", "limit": 3}
    )
    assert result.observation["status"] == "ok"
    with pytest.raises(AgentToolError):
        agent.tools.execute(
            tool_name="get_faction", arguments={"faction_id": "../../secret"}
        )
