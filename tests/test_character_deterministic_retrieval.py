from __future__ import annotations

import json

import pytest

from agents import (
    AgentExecutionError,
    AgentToolError,
    CharacterGenerationAgent,
    LiveLLMAdapter,
    ModelMalformedResponseError,
    ModelTurn,
    ProviderCompletion,
    ProviderToolCall,
    ScriptedAgentModel,
    ToolCall,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "draft_id": "draft_deterministic_001",
        "status": "draft",
        "name": "确定性角色",
        "canonical_character_id": None,
        "age": 23,
        "age_range": "20-25",
        "gender": "女性",
        "faction_id": None,
        "occupation": "学生",
        "social_role": "校园志愿者",
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "design_pitch": "有限的辅助型角色。",
        "personality": ["冷静"],
        "background": "新设计背景。",
        "story_hook": "新设计钩子。",
        "relationships": [],
        "ability_concept": "提供有限的行动节奏提示，不能替代专业训练。",
        "knowledge_scope": "仅接触公开信息。",
        "canon_basis": [{"source_id": "world_rules", "supports": ["world_rules"]}],
        "new_design_elements": [
            "new_design:occupation: 职业是新设计",
            "new_design:social_role: 社会角色是新设计",
            "new_design:design_pitch: 角色概念是新设计",
            "new_design:personality: 性格是新设计",
            "new_design:background: 背景是新设计",
            "new_design:story_hook: 故事钩子是新设计",
            "new_design:ability_concept: 能力概念是新设计",
            "new_design:knowledge_scope: 知识范围是新设计",
        ],
        "open_questions": [],
        "constraint_notes": [],
        "story_link": None,
        "proposed_new_content": [],
    }
    payload.update(overrides)
    return payload


class FakeProviderClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.call_count = 0
        self.requests: list[dict[str, object]] = []

    def complete(self, **request: object) -> ProviderCompletion:
        self.requests.append(request)
        self.call_count += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, ProviderCompletion)
        return outcome


def _live_agent(outcomes: list[object]) -> tuple[CharacterGenerationAgent, FakeProviderClient]:
    client = FakeProviderClient(outcomes)
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="test-model",
        sleep=lambda _: None,
    )
    return (
        CharacterGenerationAgent(adapter, retrieval_strategy="deterministic"),
        client,
    )


def _draft_response(**overrides: object) -> ProviderCompletion:
    return ProviderCompletion(text=json.dumps(_payload(**overrides), ensure_ascii=False))


def test_deterministic_original_prefetches_world_and_finalizes_once() -> None:
    agent, client = _live_agent([_draft_response()])

    result = agent.generate("设计一个完全原创的独立辅助型角色。")

    assert client.call_count == 1
    assert client.requests[0]["tools"] == []
    assert client.requests[0]["response_contract"] == {
        "name": "character_draft",
        "mode": "json_object",
        "json_schema": None,
    }
    assert [item.turn_number for item in result.audit.model_invocations] == [1]
    assert [(item.tool_name, item.round, item.result_status) for item in result.audit.tool_calls] == [
        ("get_world_rules", 1, "allowed")
    ]
    assert "world_rules" in result.sources


def test_deterministic_known_faction_alias_retrieves_and_grounds() -> None:
    agent, client = _live_agent(
        [
            _draft_response(
                faction_id="faction_002",
                canon_basis=[
                    {"source_id": "world_rules", "supports": ["world_rules"]},
                    {"source_id": "faction_002", "supports": ["faction_id"]},
                ],
            )
        ]
    )

    result = agent.generate("加入临洲大学行为与能力研究中心。")

    assert client.call_count == 1
    assert result.draft.faction_id == "faction_002"
    assert "faction_002" in result.sources
    assert [item.tool_name for item in result.audit.tool_calls] == [
        "get_world_rules",
        "get_faction",
    ]


def test_deterministic_ambiguous_existing_dependency_uses_one_action_then_finalization() -> None:
    agent, client = _live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-factions",
                        "search_factions",
                        {"query": "existing canon", "limit": 5},
                    ),
                    ProviderToolCall(
                        "search-lore",
                        "search_lore",
                        {"query": "existing canon", "limit": 5},
                    ),
                ),
                text="ignored while real tool calls are present",
            ),
            _draft_response(),
        ]
    )

    result = agent.generate("请考虑 existing canon，但没有具体对象或类别。")

    assert result.draft.status == "draft"
    assert client.call_count == 2
    assert [request["response_contract"]["mode"] for request in client.requests] == [
        "text",
        "json_object",
    ]
    assert client.requests[0]["tools"]
    assert client.requests[1]["tools"] == []
    assert [item.turn_number for item in result.audit.model_invocations] == [1, 2]
    assert [item.tool_name for item in result.audit.tool_calls] == [
        "get_world_rules",
        "search_factions",
        "search_lore",
    ]


def test_deterministic_fallback_finalize_still_has_two_provider_calls() -> None:
    agent, client = _live_agent(
        [ProviderCompletion(text="FINALIZE"), _draft_response()]
    )

    result = agent.generate("请考虑 existing canon，但没有具体对象或类别。")

    assert result.draft.status == "draft"
    assert client.call_count == 2
    assert [item.turn_number for item in result.audit.model_invocations] == [1, 2]


def test_deterministic_malformed_fallback_stops_before_finalization() -> None:
    agent, client = _live_agent([ProviderCompletion(text="NOT_FINALIZE")])

    with pytest.raises(ModelMalformedResponseError):
        agent.generate("请考虑 existing canon，但没有具体对象或类别。")

    assert client.call_count == 1


@pytest.mark.parametrize(
    "tool_call",
    [
        ProviderToolCall("illegal", "not_a_character_tool", {}),
        ProviderToolCall("bad-args", "get_world_rules", {"unexpected": True}),
    ],
)
def test_deterministic_fallback_tool_errors_fail_closed(tool_call: ProviderToolCall) -> None:
    agent, client = _live_agent([ProviderCompletion(tool_calls=(tool_call,))])

    with pytest.raises(AgentToolError):
        agent.generate("请考虑 existing canon，但没有具体对象或类别。")

    assert client.call_count == 1


def test_deterministic_unknown_faction_id_is_not_prefetched_or_added_to_history() -> None:
    agent, client = _live_agent(
        [
            _draft_response(
                faction_id="faction_999",
                canon_basis=[{"source_id": "world_rules", "supports": ["world_rules"]}],
            )
        ]
    )

    with pytest.raises(AgentExecutionError) as captured:
        agent.generate("引用 faction_999，不要查询。")

    assert captured.value.grounding_failure.canon_id == "faction_999"
    assert client.call_count == 1
    history = client.requests[0]["messages"]
    assert not any(
        message.get("role") in {"assistant", "tool"}
        and "faction_999" in json.dumps(message, ensure_ascii=False)
        for message in history
    )


def test_default_retrieval_strategy_keeps_model_loop_behavior() -> None:
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("world", "get_world_rules", {}),)),
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )
    agent = CharacterGenerationAgent(model)

    result = agent.generate("设计一个角色。")

    assert agent.retrieval_strategy == "model_loop"
    assert result.draft.status == "draft"
    assert len(model.prompts) == 3


def test_retrieval_strategy_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        CharacterGenerationAgent(
            ScriptedAgentModel([]), retrieval_strategy="unsupported"
        )


def test_deterministic_finalization_uses_clean_bundle_and_no_tools() -> None:
    agent, client = _live_agent([_draft_response()])

    agent.generate("加入临洲大学行为与能力研究中心。")

    request = client.requests[0]
    assert request["tools"] == []
    assert request["response_contract"]["mode"] == "json_object"
    assert [message["role"] for message in request["messages"]] == ["system", "user"]
    assert all("tool_calls" not in message for message in request["messages"])
    payload = json.loads(request["messages"][1]["content"])
    assert [item["source_id"] for item in payload["evidence_bundle"]] == [
        "faction_002",
        "world_rules",
    ]
    assert {
        item["kind"]
        for evidence in payload["evidence_bundle"]
        for item in evidence["provenance"]
    } == {"explicit_get"}
