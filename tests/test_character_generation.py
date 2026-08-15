from __future__ import annotations

import copy
import json
from dataclasses import asdict

import pytest

from agents import (
    AgentExecutionError,
    AgentToolError,
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
    LiveLLMAdapter,
    ModelAuthenticationError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelTurn,
    ProviderClientError,
    ProviderCompletion,
    ProviderToolCall,
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


class FakeProviderClient:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.call_count = 0
        self.requests: list[dict] = []

    def complete(self, **request: object) -> ProviderCompletion:
        self.requests.append(request)
        self.call_count += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def live_agent(outcomes: list, **adapter_options):
    client = FakeProviderClient(outcomes)
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="test-model",
        sleep=lambda _: None,
        **adapter_options,
    )
    return CharacterGenerationAgent(adapter), client


def test_live_malformed_structured_output_records_failure_audit():
    agent, client = live_agent(
        [ProviderCompletion(text="not valid json at all", request_id="req_bad")]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 1
    assert error.audit is not None
    assert error.audit.outcome == "malformed_response"
    assert error.audit.provider == "openai" and error.audit.model == "test-model"
    assert error.audit.retry_count == 0
    assert error.audit.provider_request_id == "req_bad"
    assert error.audit.error_message == "Provider final response is not valid CharacterDraft JSON"
    assert error.model_invocations == (error.audit,)


def test_live_character_draft_request_uses_structured_json_mode():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", {}),),
                finish_reason="tool_calls",
            ),
            ProviderCompletion(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个角色")

    assert result.draft.status == "draft"
    assert client.requests[0]["response_mode"] == "structured_json"
    assert client.requests[1]["response_mode"] == "structured_json"


def test_live_timeout_exhaustion_records_single_failure_invocation():
    timeout = ProviderClientError("timeout", retryable=True)
    agent, client = live_agent([timeout, timeout, timeout], max_retries=2)

    with pytest.raises(ModelTimeoutError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 3
    assert error.audit is not None and error.audit.outcome == "timeout"
    assert error.audit.retry_count == 2
    # 3 provider attempts = 1 logical invocation with 2 internal retries.
    assert len(error.model_invocations) == 1
    assert error.model_invocations == (error.audit,)


@pytest.mark.parametrize(
    ("failure", "error_type", "outcome"),
    [
        (
            ProviderClientError("rate_limit", retryable=False, status_code=429),
            ModelRateLimitError,
            "rate_limit",
        ),
        (
            ProviderClientError("authentication", retryable=False, status_code=401),
            ModelAuthenticationError,
            "authentication",
        ),
        (
            ProviderClientError("provider", retryable=False, status_code=500),
            ModelProviderError,
            "provider",
        ),
    ],
)
def test_live_provider_failures_keep_mapping(failure, error_type, outcome):
    agent, client = live_agent([failure])

    with pytest.raises(error_type) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 1
    assert error.audit is not None and error.audit.outcome == outcome
    assert error.audit.finish_reason is None and error.audit.usage is None
    assert error.model_invocations == (error.audit,)


def test_live_draft_schema_failure_keeps_success_invocation_trail():
    # Valid transport JSON, but the draft schema itself is malformed: the
    # adapter recorded a success audit, so the exception must still show the
    # model was called rather than looking like a call that never happened.
    agent, client = live_agent(
        [
            ProviderCompletion(
                text=json.dumps({"age": "twenty three"}), request_id="req_schema"
            )
        ]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert error.audit is None
    assert client.call_count == 1
    assert len(error.model_invocations) == 1
    assert error.model_invocations[0].outcome == "success"
    assert error.model_invocations[0].provider_request_id == "req_schema"


def test_live_tool_round_then_failure_preserves_prior_success_audit():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("t1", "get_world_rules", {}),)
            ),
            ProviderCompletion(text="not valid json", request_id="req_bad2"),
        ]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert [item.outcome for item in error.model_invocations] == [
        "success",
        "malformed_response",
    ]
    assert error.model_invocations[0].tool_call_count == 1


def test_live_validation_failure_keeps_invocation_trail():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("t1", "get_world_rules", {}),)
            ),
            ProviderCompletion(
                text=json.dumps(
                    _payload(faction_id="faction_999"), ensure_ascii=False
                ),
                request_id="req_draft",
            ),
        ]
    )

    with pytest.raises(AgentExecutionError, match="not grounded") as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert [item.outcome for item in error.model_invocations] == [
        "success",
        "success",
    ]
    assert error.model_invocations[1].provider_request_id == "req_draft"


def test_live_failure_audit_excludes_raw_model_content():
    secret = "RESTRICTED_TEST_SECRET_123"
    agent, client = live_agent(
        [ProviderCompletion(text=f"prefix {secret} not json", request_id="req_secret")]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    audit_payload = json.dumps(asdict(error.audit), ensure_ascii=False)
    trail_payload = json.dumps(
        [asdict(item) for item in error.model_invocations], ensure_ascii=False
    )
    assert secret not in audit_payload
    assert secret not in trail_payload
    assert secret not in str(error)


def test_live_success_records_success_invocations():
    payload = json.dumps(_payload(canon_basis=[]), ensure_ascii=False)
    agent, client = live_agent(
        [
            ProviderCompletion(
                text=payload, request_id="req_ok", finish_reason="stop"
            )
        ]
    )

    result = agent.generate("设计一个角色")

    assert client.call_count == 1
    assert [item.outcome for item in result.audit.model_invocations] == ["success"]
    assert result.audit.model_invocations[0].provider_request_id == "req_ok"
    assert result.audit.model_invocations[0].finish_reason == "stop"
