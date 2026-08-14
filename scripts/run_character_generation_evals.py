"""Small deterministic Character Generation eval suite."""

from __future__ import annotations

import json
import sys

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
from knowledge import KnowledgeResolver


def _payload(**changes):
    value = {
        "draft_id": "draft_eval_001",
        "status": "draft",
        "name": "评测角色",
        "age": 23,
        "age_range": "20-25",
        "gender": "女性",
        "faction_id": None,
        "occupation": "学生",
        "social_role": "志愿协调者",
        "combat_role": "support",
        "design_pitch": "辅助型角色",
        "personality": ["冷静"],
        "background": "新设计",
        "story_hook": "新设计",
        "relationships": [],
        "ability_concept": "有限个人规则",
        "knowledge_scope": "公开信息",
        "canon_basis": [{"source_id": "world_rules", "supports": ["world_rules"]}],
        "new_design_elements": ["新角色个人设计"],
        "open_questions": [],
        "constraint_notes": [],
        "story_link": None,
        "proposed_new_content": [],
    }
    value.update(changes)
    return value


def main() -> int:
    checks = []
    request = CharacterDesignRequest(
        "设计一个与临洲大学有关的年轻女性角色，与南栈事件间接联系。",
        hard_constraints=("20～25岁",),
        forbidden_elements=("秘密政府组织",),
    )
    resolver = KnowledgeResolver()
    before_counts = (len(resolver.characters), len(resolver.factions), len(resolver.lore), len(resolver.cases), len(resolver.incidents))
    result = CharacterGenerationAgent(DeterministicCharacterGenerationModel(), resolver=resolver).generate(request)
    checks.extend(
        [
            result.draft.status == "draft",
            result.draft.faction_id is None or result.draft.faction_id.startswith("faction_"),
            any(item.source_id.startswith("incident_") or item.source_id.startswith("story_") for item in result.draft.canon_basis),
            bool(result.draft.new_design_elements),
            result.draft.age in range(20, 26),
            all(item.source_id in result.sources for item in result.draft.canon_basis),
            bool(result.draft.new_design_elements),
            before_counts == (len(resolver.characters), len(resolver.factions), len(resolver.lore), len(resolver.cases), len(resolver.incidents)),
        ]
    )
    try:
        CharacterGenerationAgent(
            ScriptedAgentModel([ModelTurn(tool_calls=(ToolCall("x", "write_character", {}),))])
        ).generate("设计一个角色")
    except AgentToolError:
        checks.append(True)
    else:
        checks.append(False)
    try:
        CharacterGenerationAgent(
            ScriptedAgentModel([ModelTurn(text=json.dumps(_payload(story_link={"target_id": "incident_999", "relation": "related_context", "status": "canon_backed"}), ensure_ascii=False))])
        ).generate("设计一个角色")
    except AgentExecutionError:
        checks.append(True)
    else:
        checks.append(False)
    try:
        CharacterGenerationAgent(
            ScriptedAgentModel([ModelTurn(text=json.dumps(_payload(proposed_new_content=["秘密政府组织"]), ensure_ascii=False))])
        ).generate(CharacterDesignRequest("不要新增秘密政府组织"))
    except AgentExecutionError:
        checks.append(True)
    else:
        checks.append(False)
    try:
        CharacterGenerationAgent(
            ScriptedAgentModel([ModelTurn(text=json.dumps(_payload(faction_id="faction_999"), ensure_ascii=False))])
        ).generate("设计一个角色")
    except AgentExecutionError:
        checks.append(True)
    else:
        checks.append(False)
    try:
        CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(text=json.dumps({"age": "twenty three"}))])).generate("设计一个角色")
    except ModelMalformedResponseError:
        checks.append(True)
    else:
        checks.append(False)
    passed = sum(checks)
    failed = len(checks) - passed
    print(f"Character Generation evals: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
