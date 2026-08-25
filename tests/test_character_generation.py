from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace

import pytest

from agents import (
    AgentExecutionError,
    AgentToolError,
    CharacterAuthoringToolbox,
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
    LiveLLMAdapter,
    ModelAuthenticationError,
    ModelCapabilityError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelTurn,
    ProviderClientError,
    ProviderCompletion,
    ProviderToolCall,
    ProviderCapabilities,
    PROVIDER_PROFILES,
    ScriptedAgentModel,
    ThinkingModeBehavior,
    ToolCall,
    ToolAuditEntry,
)
from agents.character_generation import AuthoringToolExecution, CHARACTER_SYSTEM_CONTRACT


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
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "design_pitch": "辅助型角色",
        "personality": ["冷静"],
        "background": "新设计背景",
        "story_hook": "新设计钩子",
        "relationships": [],
        "ability_concept": "有限的个人规则概念",
        "knowledge_scope": "公开信息",
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
            "姓名与性格是新设计",
        ],
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
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(_payload(faction_id="faction_999"), ensure_ascii=False)
            ),
        ]
    )
    agent = CharacterGenerationAgent(model)
    with pytest.raises(AgentExecutionError, match="not grounded"):
        agent.generate("设计一个角色")


def test_generation_rejects_natural_language_canon_id_without_field_evidence():
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("world", "get_world_rules", {}),)),
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(
                    _payload(background="她掌握了 lore_001 的全部秘密。"),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    with pytest.raises(AgentExecutionError, match="field 'background'"):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_generation_accepts_field_level_canon_evidence_for_an_id_claim():
    model = ScriptedAgentModel(
        [
            ModelTurn(
                tool_calls=(
                    ToolCall("lore", "get_lore", {"lore_id": "lore_001"}),
                )
            ),
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(
                    _payload(
                        background="她掌握了 lore_001 的全部秘密。",
                        canon_basis=[
                            {
                                "source_id": "lore_001",
                                "supports": ["background"],
                            }
                        ],
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = CharacterGenerationAgent(model).generate("设计一个角色")

    assert result.draft.background == "她掌握了 lore_001 的全部秘密。"
    assert result.sources == ("lore_001",)


def test_canon_dependent_faction_uses_tool_evidence_before_grounded_draft():
    model = ScriptedAgentModel(
        [
            ModelTurn(
                tool_calls=(
                    ToolCall("faction", "get_faction", {"faction_id": "faction_002"}),
                )
            ),
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(
                    _payload(
                        faction_id="faction_002",
                        canon_basis=[
                            {
                                "source_id": "faction_002",
                                "supports": ["faction_id"],
                                "source_type": "faction",
                            }
                        ],
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = CharacterGenerationAgent(model).generate(
        CharacterDesignRequest("设计一个必须加入现有临洲大学研究中心的角色。")
    )

    assert result.draft.faction_id == "faction_002"
    assert "faction_002" in result.sources
    assert [(item.tool_name, item.result_status) for item in result.audit.tool_calls] == [
        ("get_faction", "allowed")
    ]


def test_canon_independent_original_brief_can_finish_without_tools():
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(canon_basis=[]), ensure_ascii=False)),
        ]
    )

    result = CharacterGenerationAgent(model).generate(
        CharacterDesignRequest(
            "设计一个完全原创的独立辅助型角色，不使用任何既有组织、角色、事件、规则或其他 Canon。"
        )
    )

    assert result.draft.faction_id is None
    assert result.sources == ()
    assert result.audit.tool_calls == ()


def test_character_contract_requires_conditional_canon_retrieval():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "conditional on Canon dependency" in contract
    assert "must first search for or retrieve it" in contract
    assert "Do not treat a name or ID in the brief as verified evidence" in contract
    assert "If required Canon cannot be found or verified, do not invent or guess it" in contract
    assert "may be produced without authoring-tool calls" in contract


def test_playable_generation_contract_requires_combat_fantasy_without_new_game_systems():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "ordinary person can plausibly enter dangerous scenes" in contract
    assert "what the player imagines doing during combat" in contract
    assert "visible or spatial feedback" in contract
    assert "what the play rhythm is" in contract
    assert "Non-damage support and control are valid" in contract
    for forbidden in (
        "elemental classes",
        "weapon taxonomies",
        "damage multipliers",
        "critical-rate systems",
        "cooldown or energy systems",
    ):
        assert forbidden in contract


def test_non_playable_generation_contract_preserves_ordinary_npc_identity():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "If the brief is NPC-only or does not request playability" in contract
    assert "do not force combat fantasy or a combat role" in contract
    assert "secret fighter, elite operative, or hidden-organization member" in contract


def test_character_hook_contract_uses_existing_three_part_semantics():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "existing `story_hook` field" in contract
    assert "`first impression`" in contract
    assert "`visual_or_behavioral_motif`" in contract
    assert "`memorable_contrast`" in contract
    assert "not a marketing gimmick" in contract


def test_reference_context_contract_is_transformative_and_non_canon():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "bounded external design precedent, not Canon evidence and not a template" in contract
    assert "do not copy a reference character's personality, combat kit, or visual identity" in contract
    assert "Field-level causal attribution is not available" in contract


def test_character_draft_prompt_repeats_required_field_completion_checklist():
    contract = CHARACTER_SYSTEM_CONTRACT

    assert "Emit every property listed by the schema exactly once" in contract
    assert "including canon_basis, new_design_elements, and open_questions" in contract
    assert "Use canon_basis=[] when no Canon claim was retrieved" in contract
    assert "never omit a required field" in contract


def test_live_character_draft_missing_canon_and_design_fields_still_fail_closed():
    incomplete = _payload(canon_basis=[])
    incomplete.pop("canon_basis")
    incomplete.pop("new_design_elements")
    incomplete.pop("open_questions")
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(incomplete, ensure_ascii=False)),
            ProviderCompletion(text=json.dumps({"canon_basis": []}, ensure_ascii=False)),
        ]
    )

    with pytest.raises(
        ModelMalformedResponseError,
        match="new_design_elements",
    ) as captured:
        agent.generate("设计一个完全原创的角色")

    assert client.call_count == 3
    assert captured.value.model_invocations[-1].outcome == "success"
    assert captured.value.audit is None
    assert captured.value.model_invocations[-1].error_message is None


def test_live_character_draft_explicit_empty_arrays_are_safe():
    payload = _payload(canon_basis=[], new_design_elements=[], open_questions=[])
    for field in (
        "occupation",
        "social_role",
        "design_pitch",
        "background",
        "story_hook",
        "ability_concept",
        "knowledge_scope",
    ):
        payload[field] = ""
    payload["personality"] = []
    agent, _ = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(payload, ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个完全原创且没有未决问题的角色")

    assert result.draft.canon_basis == ()
    assert result.draft.new_design_elements == ()
    assert result.draft.open_questions == ()


def test_missing_only_open_questions_uses_field_specific_safe_normalization():
    payload = _payload(canon_basis=[])
    payload.pop("open_questions")
    agent, _ = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(payload, ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个没有未决问题的原创角色")

    assert result.draft.open_questions == ()
    assert result.audit.normalized_fields == ("open_questions",)


def test_explicit_non_empty_open_questions_are_preserved_without_normalization():
    questions = ["需要确认她与某组织的正式关系"]
    payload = _payload(canon_basis=[], open_questions=questions)
    agent, _ = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(payload, ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个关系仍待确认的角色")

    assert result.draft.open_questions == tuple(questions)
    assert result.audit.normalized_fields == ()


@pytest.mark.parametrize("missing_field", ["canon_basis", "new_design_elements"])
def test_other_missing_core_fields_still_fail_closed(missing_field):
    payload = _payload()
    payload.pop(missing_field)
    agent, _ = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(payload, ensure_ascii=False)),
            ProviderCompletion(text=json.dumps({}, ensure_ascii=False)),
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match=missing_field):
        agent.generate("设计一个角色")


def test_multiple_missing_core_fields_are_not_fixed_by_open_questions_default():
    payload = _payload()
    payload.pop("open_questions")
    payload.pop("canon_basis")
    agent, _ = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(payload, ensure_ascii=False)),
            ProviderCompletion(text=json.dumps({}, ensure_ascii=False)),
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match="canon_basis"):
        agent.generate("设计一个角色")


def test_unknown_write_tool_is_rejected():
    model = ScriptedAgentModel(
        [ModelTurn(tool_calls=(ToolCall("x", "write_character", {"id": "x"}),))]
    )
    with pytest.raises(AgentToolError, match="forbidden"):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_malformed_draft_is_rejected_strictly():
    model = ScriptedAgentModel(
        [ModelTurn(text="FINALIZE"), ModelTurn(text=json.dumps({"age": "twenty three"}))]
    )
    with pytest.raises(ModelMalformedResponseError):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_numeric_faction_id_is_not_normalized():
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(faction_id=123), ensure_ascii=False)),
        ]
    )
    with pytest.raises(ModelMalformedResponseError):
        CharacterGenerationAgent(model).generate("设计一个角色")


def test_hard_age_constraint_is_enforced():
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(age=17), ensure_ascii=False)),
        ]
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
    max_tool_rounds = adapter_options.pop("max_tool_rounds", 6)
    client = FakeProviderClient(outcomes)
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="test-model",
        sleep=lambda _: None,
        **adapter_options,
    )
    return CharacterGenerationAgent(adapter, max_tool_rounds=max_tool_rounds), client


class _MalformedFinalizationToolbox(CharacterAuthoringToolbox):
    def execute(self, *, tool_name, arguments, round_number, **kwargs):
        return AuthoringToolExecution(
            {
                "status": "ok",
                "result": {
                    "source_id": "world_rules",
                    "detail": "not a safe factual observation",
                },
            },
            ToolAuditEntry(
                round_number,
                tool_name,
                arguments,
                "allowed",
                allowed_lore_ids=("world_rules",),
            ),
            frozenset({"world_rules"}),
            {"world_rules": "world_rules"},
        )


def test_live_malformed_structured_output_records_failure_audit():
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text="not valid json at all", request_id="req_bad"),
        ]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert error.audit is not None
    assert error.audit.outcome == "malformed_response"
    assert error.audit.provider == "openai" and error.audit.model == "test-model"
    assert error.audit.retry_count == 0
    assert error.audit.provider_request_id == "req_bad"
    assert error.audit.error_message == "Provider final response is not valid CharacterDraft JSON"
    assert [item.outcome for item in error.model_invocations] == [
        "success",
        "malformed_response",
    ]
    assert error.model_invocations[-1] == error.audit


def test_live_character_draft_request_uses_structured_json_mode():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", {}),),
                finish_reason="tool_calls",
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个角色")

    assert result.draft.status == "draft"
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert client.requests[1]["response_contract"]["mode"] == "text"
    assert client.requests[2]["response_contract"]["mode"] == "json_object"


def test_live_character_generation_separates_retrieval_and_finalization_contracts():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-faction",
                        "search_factions",
                        '{"query":"大学","limit":5}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            ProviderCompletion(text="FINALIZE", finish_reason="stop"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        faction_id="faction_002",
                        canon_basis=[
                            {
                                "source_id": "faction_002",
                                "supports": ["faction_id"],
                                "source_type": "faction",
                            }
                        ],
                    ),
                    ensure_ascii=False,
                ),
                finish_reason="stop",
            ),
        ]
    )

    result = agent.generate("设计一个必须加入现有临洲大学研究中心的角色")

    assert result.draft.faction_id == "faction_002"
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert client.requests[0]["tools"]
    retrieval_prompt = client.requests[0]["messages"][0]["content"]
    assert "FINALIZE" in retrieval_prompt
    assert "Authoritative CharacterDraft JSON Schema" not in retrieval_prompt
    assert "root JSON object itself is the CharacterDraft" not in retrieval_prompt
    assert client.requests[1]["response_contract"]["mode"] == "text"
    assert client.requests[2]["response_contract"]["mode"] == "json_object"
    assert client.requests[2]["tools"] == []


@pytest.mark.parametrize(
    "action_text",
    [
        "FINALIZE",
        " FINALIZE ",
        "\n\tFINALIZE\n\n",
    ],
)
def test_live_authoring_action_accepts_exact_finalize_with_outer_whitespace(action_text):
    agent, client = live_agent(
        [
            ProviderCompletion(text=action_text),
            ProviderCompletion(text=json.dumps(_payload(canon_basis=[]), ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个完全原创的角色")

    assert result.draft.status == "draft"
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert client.requests[1]["response_contract"]["mode"] == "json_object"
    assert client.requests[1]["tools"] == []


@pytest.mark.parametrize(
    "action_text",
    [
        "FINALIZE please",
        "I have enough Canon evidence.\nFINALIZE",
        '{"action":"FINALIZE"}',
        "```text\nFINALIZE\n```",
        json.dumps(_payload(canon_basis=[]), ensure_ascii=False),
        "I think we should finalize",
        "FINALIZE and use faction_005",
        '{"/users/.../search_factions":null}',
    ],
)
def test_live_authoring_action_rejects_non_terminal_finalize_text(action_text):
    agent, client = live_agent([ProviderCompletion(text=action_text)])

    with pytest.raises(ModelMalformedResponseError, match="real tool call") as captured:
        agent.generate("选择一个已有阵营的角色")

    assert client.call_count == 1
    assert getattr(captured.value, "phase", None) == "action_termination"
    assert getattr(captured.value, "reason", None) == "invalid_termination_signal"


def test_live_finalization_tool_call_fails_closed_and_preserves_success_audit():
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                tool_calls=(ProviderToolCall("unexpected", "search_lore", {}),)
            ),
        ]
    )

    with pytest.raises(AgentExecutionError, match="attempted a tool call") as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert [item.outcome for item in error.model_invocations] == ["success", "success"]
    assert error.contract_recovery.status == "not_attempted"


def test_live_protocol_tool_calls_take_precedence_over_action_text():
    agent, client = live_agent(
        [
            ProviderCompletion(
                text="I will retrieve the faction first.\nFINALIZE",
                tool_calls=(
                    ProviderToolCall(
                        "search-faction",
                        "search_factions",
                        '{"query":"大学","limit":5}',
                    ),
                ),
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        faction_id="faction_002",
                        canon_basis=[
                            {
                                "source_id": "faction_002",
                                "supports": ["faction_id"],
                                "source_type": "faction",
                            }
                        ],
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = agent.generate("设计一个必须加入现有临洲大学研究中心的角色")

    assert result.draft.faction_id == "faction_002"
    assert result.audit.tool_calls[0].tool_name == "search_factions"
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert client.requests[2]["response_contract"]["mode"] == "json_object"


def test_live_character_generation_supports_multiple_retrieval_rounds():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-faction",
                        "search_factions",
                        '{"query":"大学","limit":5}',
                    ),
                )
            ),
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "get-faction",
                        "get_faction",
                        '{"faction_id":"faction_002"}',
                    ),
                )
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        faction_id="faction_002",
                        canon_basis=[
                            {
                                "source_id": "faction_002",
                                "supports": ["faction_id"],
                                "source_type": "faction",
                            }
                        ],
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = agent.generate("设计一个必须使用现有临洲大学研究中心的角色")

    assert result.draft.faction_id == "faction_002"
    assert "faction_002" in result.sources
    assert [request["response_contract"]["mode"] for request in client.requests] == [
        "text",
        "text",
        "text",
        "json_object",
    ]
    assert client.requests[3]["tools"] == []
    assert [entry.tool_name for entry in result.audit.tool_calls] == [
        "search_factions",
        "get_faction",
    ]


def test_live_three_round_repeated_search_and_zero_result_replay_builds_bundle():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-lore-1",
                        "search_lore",
                        '{"query":"大学","limit":5}',
                    ),
                    ProviderToolCall(
                        "search-empty-1",
                        "search_lore",
                        '{"query":"no_such_canon_marker","limit":5}',
                    ),
                )
            ),
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-lore-2",
                        "search_lore",
                        '{"query":"大学","limit":5}',
                    ),
                    ProviderToolCall(
                        "search-empty-2",
                        "search_lore",
                        '{"query":"no_such_canon_marker","limit":5}',
                    ),
                )
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(_payload(canon_basis=[]), ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个完全原创的角色")

    assert result.draft.status == "draft"
    assert client.call_count == 4
    assert [request["response_contract"]["mode"] for request in client.requests] == [
        "text",
        "text",
        "text",
        "json_object",
    ]
    assert [item.tool_name for item in result.audit.tool_calls] == [
        "search_lore",
        "search_lore",
        "search_lore",
        "search_lore",
    ]
    assert all(item.result_status == "allowed" for item in result.audit.tool_calls)
    final_payload = json.loads(client.requests[-1]["messages"][1]["content"])
    assert final_payload["evidence_bundle"]
    assert all(item["source_type"] == "lore" for item in final_payload["evidence_bundle"])
    assert client.requests[-1]["tools"] == []


def test_live_character_generation_requires_exact_finalize_before_retrieval_budget():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search-faction",
                        "search_factions",
                        '{"query":"大学","limit":5}',
                    ),
                )
            ),
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "get-faction",
                        "get_faction",
                        '{"faction_id":"faction_002"}',
                    ),
                )
            ),
        ],
        max_tool_rounds=2,
    )

    with pytest.raises(ModelMalformedResponseError, match="round limit") as captured:
        agent.generate("设计一个必须参考现有临洲大学研究中心的角色")

    error = captured.value
    assert client.call_count == 2
    assert all(request["response_contract"]["mode"] == "text" for request in client.requests)
    assert [entry.tool_call_count for entry in error.model_invocations] == [1, 1]
    assert getattr(error, "phase", None) == "action_termination"
    assert getattr(error, "reason", None) == "tool_round_limit_exhausted"


def test_live_budget_exhaustion_fails_closed_without_finalization_invocation():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", "{}"),)
            ),
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "search",
                        "search_factions",
                        '{"query":"大学","limit":5}',
                    ),
                )
            ),
        ],
        max_tool_rounds=2,
    )

    with pytest.raises(ModelMalformedResponseError, match="round limit") as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert all(request["response_contract"]["mode"] == "text" for request in client.requests)
    assert [item.tool_call_count for item in error.model_invocations] == [1, 1]
    assert getattr(error, "phase", None) == "action_termination"
    assert getattr(error, "reason", None) == "tool_round_limit_exhausted"


def test_termination_then_context_construction_failure_is_classified_without_finalization():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", "{}"),)
            ),
            ProviderCompletion(text="FINALIZE"),
        ]
    )
    agent.tools = _MalformedFinalizationToolbox()

    with pytest.raises(ModelMalformedResponseError, match="observation payload") as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 2
    assert all(request["response_contract"]["mode"] == "text" for request in client.requests)
    assert [item.tool_call_count for item in error.model_invocations] == [1, 0]
    assert getattr(error, "phase", None) == "finalization_context"
    assert getattr(error, "reason", None) == "context_construction_failed"


def test_live_budget_exhaustion_fails_closed_before_draft_grounding_validation():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", {}),)
            ),
        ],
        max_tool_rounds=1,
    )

    with pytest.raises(ModelMalformedResponseError, match="round limit") as captured:
        agent.generate("设计一个角色")

    assert client.call_count == 1
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert [entry.tool_call_count for entry in captured.value.model_invocations] == [1]
    assert getattr(captured.value, "phase", None) == "action_termination"
    assert getattr(captured.value, "reason", None) == "tool_round_limit_exhausted"


def test_live_pseudo_tool_json_is_not_recognized_as_a_tool_call():
    agent, client = live_agent(
        [ProviderCompletion(text=json.dumps({"/users/.../search_factions": None}))]
    )

    with pytest.raises(ModelMalformedResponseError, match="real tool call") as captured:
        agent.generate("选择一个已有阵营的角色")

    assert client.call_count == 1
    assert client.requests[0]["response_contract"]["mode"] == "text"
    assert captured.value.model_invocations[0].tool_call_count == 0


def test_live_tools_only_provider_fails_closed_at_finalization():
    profile = replace(
        PROVIDER_PROFILES["openai"],
        capabilities=ProviderCapabilities(
            supports_tools=True,
            supports_json_schema=False,
            supports_json_object=False,
            supports_parallel_tool_calls=False,
            thinking_mode_behavior=ThinkingModeBehavior.PROVIDER_DEFAULT,
        ),
    )
    client = FakeProviderClient([ProviderCompletion(text="FINALIZE")])
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="tools-only",
        profile=profile,
        sleep=lambda _: None,
    )

    with pytest.raises(ModelCapabilityError, match="cannot satisfy strict"):
        CharacterGenerationAgent(adapter).generate("设计一个完全原创的角色")

    assert client.call_count == 1
    assert client.requests[0]["response_contract"]["mode"] == "text"


@pytest.mark.parametrize(
    "wrapper", ["character_draft", "draft", "result", "data", "response", "payload"]
)
def test_live_character_draft_envelopes_are_rejected(wrapper):
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps({wrapper: _payload()}, ensure_ascii=False)),
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match="unknown field") as captured:
        agent.generate("设计一个角色")

    assert wrapper in str(captured.value)
    assert client.call_count == 2


def test_live_character_prompt_requires_direct_root_and_forbids_wrappers():
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=json.dumps(_payload(canon_basis=[]), ensure_ascii=False)),
        ]
    )

    result = agent.generate("设计一个角色")

    retrieval_prompt = client.requests[0]["messages"][0]["content"]
    system_prompt = client.requests[1]["messages"][0]["content"]
    assert result.draft.draft_id == "draft_test_001"
    assert "Authoritative CharacterDraft JSON Schema" not in retrieval_prompt
    assert "root JSON object itself is the CharacterDraft" not in retrieval_prompt
    assert "root JSON object itself is the CharacterDraft" in system_prompt
    assert "Do not wrap it" in system_prompt
    for wrapper in ("character_draft", "draft", "result", "data", "response", "payload"):
        assert wrapper in system_prompt
    assert '"draft_id":"draft_request_001"' in system_prompt


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
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps({"age": "twenty three"}), request_id="req_schema"
            )
        ]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert error.audit is None
    assert client.call_count == 2
    assert len(error.model_invocations) == 2
    assert error.model_invocations[1].outcome == "success"
    assert error.model_invocations[1].provider_request_id == "req_schema"


def test_live_tool_round_then_failure_preserves_prior_success_audit():
    agent, client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("t1", "get_world_rules", {}),)
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text="not valid json", request_id="req_bad2"),
        ]
    )

    with pytest.raises(ModelMalformedResponseError) as captured:
        agent.generate("设计一个角色")

    error = captured.value
    assert client.call_count == 3
    assert [item.outcome for item in error.model_invocations] == [
        "success",
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
            ProviderCompletion(text="FINALIZE"),
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
    assert client.call_count == 3
    assert [item.outcome for item in error.model_invocations] == [
        "success",
        "success",
        "success",
    ]
    assert error.model_invocations[2].provider_request_id == "req_draft"


def _without_occupation_design_marker():
    return tuple(
        item
        for item in _payload()["new_design_elements"]
        if not item.startswith("new_design:occupation:")
    )


@pytest.mark.parametrize(
    "occupation",
    ["自由摄影师", "独立活动策划", "私人顾问"],
)
def test_live_ordinary_occupation_with_explicit_new_design_is_allowed(occupation):
    design_elements = list(_payload()["new_design_elements"])
    agent, _client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        occupation=occupation,
                        canon_basis=[],
                        new_design_elements=design_elements,
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = agent.generate("设计一个完全原创的成年角色")

    assert result.draft.occupation == occupation


def test_live_known_organization_without_retrieval_fails_with_entity_id():
    agent, _client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        occupation="衡信保险风险分析师",
                        canon_basis=[],
                        new_design_elements=_without_occupation_design_marker(),
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    with pytest.raises(AgentExecutionError) as captured:
        agent.generate("职业必须与现有商业组织有关的成年角色")

    assert captured.value.grounding_failure.check == "field:occupation"
    assert captured.value.grounding_failure.canon_id == "faction_003"


def test_live_retrieved_organization_without_occupation_attribution_stays_fail_closed():
    agent, _client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall("world", "get_world_rules", {}),
                )
            ),
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall(
                        "faction", "get_faction", {"faction_id": "faction_003"}
                    ),
                )
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        occupation="衡信保险风险分析师",
                        canon_basis=[
                            {"source_id": "world_rules", "supports": ["world_rules"]},
                            {"source_id": "faction_003", "supports": ["faction_id"]},
                        ],
                        new_design_elements=_without_occupation_design_marker(),
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    with pytest.raises(AgentExecutionError) as captured:
        agent.generate("职业必须与现有商业组织有关的成年角色")

    assert captured.value.grounding_failure.check == "field:occupation"
    assert captured.value.grounding_failure.canon_id == "faction_003"


def test_live_unknown_organization_is_rejected_even_if_marked_new_design():
    agent, _client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        occupation="临洲未来科技集团高级顾问",
                        canon_basis=[],
                        new_design_elements=_payload()["new_design_elements"],
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    with pytest.raises(AgentExecutionError, match="unverified organization"):
        agent.generate("设计一个不能新建组织的成年角色")


def test_live_mixed_occupation_requires_known_organization_edge_but_allows_new_role_tail():
    agent, _client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall("faction", "get_faction", {"faction_id": "faction_003"}),
                )
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(
                    _payload(
                        occupation="为衡信保险提供外部活动协调服务的自由顾问",
                        canon_basis=[
                            {"source_id": "faction_003", "supports": ["occupation"]}
                        ],
                        new_design_elements=_without_occupation_design_marker(),
                    ),
                    ensure_ascii=False,
                )
            ),
        ]
    )

    result = agent.generate("职业必须与现有商业组织有关的成年角色")

    assert result.draft.occupation.startswith("为衡信保险")


@pytest.mark.parametrize(
    ("label", "overrides", "expected_check", "expected_id"),
    [
        (
            "faction_id",
            {"faction_id": "faction_999"},
            "faction_id",
            "faction_999",
        ),
        (
            "canon_basis",
            {
                "canon_basis": [
                    {"source_id": "world_rules", "supports": ["world_rules"]},
                    {"source_id": "lore_999", "supports": []},
                ]
            },
            "canon_basis",
            "lore_999",
        ),
        (
            "story_link",
            {
                "story_link": {
                    "target_id": "story_999",
                    "relation": "related_context",
                    "status": "canon_backed",
                }
            },
            "story_link",
            "story_999",
        ),
        (
            "relationships",
            {
                "relationships": [
                    {
                        "target_id": "char_999",
                        "description": "未确认关系",
                        "status": "canon_backed",
                    }
                ]
            },
            "relationships",
            "char_999",
        ),
        (
            "field:background",
            {"background": "她掌握 lore_001 的秘密。"},
            "field:background",
            "lore_001",
        ),
    ],
)
def test_live_grounding_failure_carries_safe_check_and_canon_id(
    label, overrides, expected_check, expected_id
):
    agent, _client = live_agent(
        [
            ProviderCompletion(
                tool_calls=(ProviderToolCall("world", "get_world_rules", {}),)
            ),
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=json.dumps(_payload(**overrides), ensure_ascii=False)
            ),
        ]
    )

    with pytest.raises(AgentExecutionError) as captured:
        agent.generate("设计一个角色")

    diagnostic = getattr(captured.value, "grounding_failure", None)
    assert diagnostic is not None
    assert diagnostic.check == expected_check
    assert diagnostic.canon_id == expected_id


def test_live_failure_audit_excludes_raw_model_content():
    secret = "RESTRICTED_TEST_SECRET_123"
    agent, client = live_agent(
        [
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(text=f"prefix {secret} not json", request_id="req_secret"),
        ]
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
            ProviderCompletion(text="FINALIZE"),
            ProviderCompletion(
                text=payload, request_id="req_ok", finish_reason="stop"
            )
        ]
    )

    result = agent.generate("设计一个角色")

    assert client.call_count == 2
    assert [item.outcome for item in result.audit.model_invocations] == [
        "success",
        "success",
    ]
    assert result.audit.model_invocations[1].provider_request_id == "req_ok"
    assert result.audit.model_invocations[1].finish_reason == "stop"
