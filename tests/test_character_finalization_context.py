from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agents import (
    AgentExecutionError,
    CharacterDesignRequest,
    CharacterGenerationAgent,
    ModelMalformedResponseError,
    ModelTurn,
    ScriptedAgentModel,
    ToolCall,
    ToolDefinition,
)
from agents.character_generation import (
    AuthoringToolExecution,
    _build_finalization_context,
)
from agents.live_llm import LiveLLMAdapter
from agents.models import ConversationMessage, ToolAuditEntry
from knowledge import KnowledgeResolver

_AUDIT_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_live_character_authoring_latency.py"
)
_AUDIT_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "audit_live_character_authoring_latency_for_protocol_test",
    _AUDIT_SCRIPT_PATH,
)
assert _AUDIT_SCRIPT_SPEC is not None and _AUDIT_SCRIPT_SPEC.loader is not None
_AUDIT_SCRIPT_MODULE = importlib.util.module_from_spec(_AUDIT_SCRIPT_SPEC)
_AUDIT_SCRIPT_SPEC.loader.exec_module(_AUDIT_SCRIPT_MODULE)
_prompt_shape = _AUDIT_SCRIPT_MODULE._prompt_shape

_RAW_BRIEF_SENTINEL = "RAW_PROTOCOL_BRIEF_SENTINEL"
_RAW_TOOL_ARGUMENT_SENTINEL = "RAW_PROTOCOL_TOOL_ARGUMENT_SENTINEL"
_RAW_TOOL_RESULT_SENTINEL = "RAW_PROTOCOL_TOOL_RESULT_SENTINEL"
_RAW_MODEL_OUTPUT_SENTINEL = "RAW_PROTOCOL_MODEL_OUTPUT_SENTINEL"
_OBSERVATION_FACT_SENTINEL = "OBSERVATION_FACT_SENTINEL"
_RESOLVER_FACT_SENTINEL = "RESOLVER_FACT_SENTINEL"


def _request(brief: str = "设计一个完全原创的角色") -> CharacterDesignRequest:
    return CharacterDesignRequest(brief, request_id="finalization_context_001")


def _assistant(*calls: ToolCall) -> ConversationMessage:
    return ConversationMessage(
        "assistant",
        {
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}
                for call in calls
            ]
        },
    )


def _tool(call_id: str, content: dict[str, Any]) -> ConversationMessage:
    return ConversationMessage("tool", {"tool_call_id": call_id, **content})


def _audit(round_number: int, call: ToolCall, source_ids: list[str]) -> ToolAuditEntry:
    return ToolAuditEntry(
        round_number,
        call.name,
        call.arguments,
        "allowed",
        allowed_lore_ids=tuple(source_ids),
    )


def _search_result(source_id: str, source_type: str, *, label: str | None = None) -> dict[str, str]:
    result = {
        "id": source_id,
        "source_id": source_id,
        "source_type": source_type,
        "name": label or source_id,
        "summary": f"summary for {source_id}",
    }
    if source_type == "lore":
        result.update(
            {
                "title": label or source_id,
                "statement": f"statement for {source_id}",
                "sensitivity": "public",
            }
        )
    return result


def _build(
    request: CharacterDesignRequest,
    groups: list[tuple[int, tuple[ToolCall, ...], tuple[dict[str, Any], ...], tuple[str, ...]]],
    source_types: dict[str, str],
    *,
    known_source_ids: set[str] | None = None,
    known_source_types: dict[str, str] | None = None,
    allow_restricted_lore: bool | None = None,
) -> Any:
    messages: list[ConversationMessage] = [
        ConversationMessage("user", '{"brief":"original request"}')
    ]
    audits: list[ToolAuditEntry] = []
    for round_number, calls, observations, audit_ids in groups:
        messages.append(_assistant(*calls))
        for call_index, (call, observation) in enumerate(zip(calls, observations)):
            messages.append(_tool(call.id, observation))
            call_audit_ids = (
                [audit_ids[call_index]]
                if len(calls) == len(audit_ids)
                else list(audit_ids)
            )
            audits.append(_audit(round_number, call, call_audit_ids))
    build_kwargs: dict[str, Any] = {}
    if known_source_types is not None:
        build_kwargs["known_source_types"] = known_source_types
    if allow_restricted_lore is not None:
        build_kwargs["allow_restricted_lore"] = allow_restricted_lore
    return _build_finalization_context(
        request,
        messages=messages,
        source_ids=set(source_types),
        source_types=source_types,
        audits=audits,
        known_source_ids=set(source_types) if known_source_ids is None else known_source_ids,
        **build_kwargs,
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": "draft_finalization_001",
        "status": "draft",
        "canonical_character_id": None,
        "name": "上下文角色",
        "age": 23,
        "age_range": "20-25",
        "gender": "女性",
        "faction_id": None,
        "occupation": "学生",
        "social_role": "校园志愿者",
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "design_pitch": "一名有限辅助型角色。",
        "personality": ["冷静"],
        "background": "新设计背景。",
        "story_hook": "新设计钩子。",
        "relationships": [],
        "ability_concept": "提供有限的行动节奏提示，不能替代专业训练。",
        "knowledge_scope": "仅接触公开信息。",
        "canon_basis": [],
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


def test_direct_get_and_world_rules_survive_discovery_bound() -> None:
    search_ids = [f"lore_{index:03d}" for index in range(1, 7)]
    direct_id = "lore_999"
    search = ToolCall("search", "search_lore", {"query": "entry", "limit": 10})
    world = ToolCall("world", "get_world_rules", {})
    direct = ToolCall("direct", "get_lore", {"lore_id": direct_id})
    source_types = {source_id: "lore" for source_id in (*search_ids, direct_id)}
    source_types["world_rules"] = "world_rules"

    context = _build(
        _request(),
        [
            (
                1,
                (search,),
                ({"status": "ok", "results": [_search_result(item, "lore", label="entry") for item in search_ids]},),
                tuple(search_ids),
            ),
            (
                2,
                (world,),
                ({"status": "ok", "result": {"source_id": "world_rules", "rules": ["RULE-001"]}},),
                ("world_rules",),
            ),
            (
                3,
                (direct,),
                ({"status": "ok", "result": {"source_id": direct_id, "statement": "richer direct fact"}},),
                (direct_id,),
            ),
        ],
        source_types,
    )

    assert {"world_rules", direct_id} <= set(context.source_ids)
    assert {f"lore_{index:03d}" for index in range(1, 6)} <= set(context.source_ids)
    assert "lore_006" not in context.source_ids
    assert context.source_types["world_rules"] == "world_rules"
    assert [message.role for message in context.messages] == ["user"]
    bundle = {item["source_id"]: item for item in context.evidence_bundle}
    assert {"world_rules", direct_id} <= set(bundle)
    assert bundle["world_rules"]["provenance"] == (
        {"kind": "explicit_get", "tool_name": "get_world_rules", "round": 2},
    )
    assert bundle[direct_id]["provenance"] == (
        {"kind": "explicit_get", "tool_name": "get_lore", "round": 3},
    )


def test_zero_result_searches_do_not_enter_clean_finalization_context() -> None:
    faction_search = ToolCall(
        "faction-search",
        "search_factions",
        {"query": "missing faction", "limit": 5},
    )
    lore_search = ToolCall(
        "lore-search",
        "search_lore",
        {"query": "missing lore", "limit": 5},
    )
    direct = ToolCall("direct", "get_faction", {"faction_id": "faction_direct"})
    context = _build(
        _request(),
        [
            (
                1,
                (faction_search, lore_search),
                (
                    {"status": "ok", "results": []},
                    {"status": "ok", "results": []},
                ),
                (),
            ),
            (
                2,
                (direct,),
                (
                    {
                        "status": "ok",
                        "result": {
                            "source_id": "faction_direct",
                            "core_function": {"description": "richer direct fact"},
                        },
                    },
                ),
                ("faction_direct",),
            ),
        ],
        {"faction_direct": "faction"},
    )

    assert context.messages == (context.messages[0],)
    assert context.source_ids == ("faction_direct",)
    assert [item["source_id"] for item in context.evidence_bundle] == [
        "faction_direct"
    ]
    serialized = json.dumps(context.evidence_bundle, ensure_ascii=False)
    assert "search_factions" not in serialized
    assert "search_lore" not in serialized


def test_lore_search_summary_is_preserved_from_selected_observation() -> None:
    search = ToolCall("lore-search", "search_lore", {"query": "observed", "limit": 5})
    context = _build(
        _request(),
        [
            (
                1,
                (search,),
                (
                    {
                        "status": "ok",
                        "results": [
                            {
                                "id": "lore_001",
                                "source_id": "lore_001",
                                "source_type": "lore",
                                "title": "Observed title",
                                "summary": _OBSERVATION_FACT_SENTINEL,
                                "category": "observed",
                                "sensitivity": "public",
                            }
                        ],
                    },
                ),
                ("lore_001",),
            )
        ],
        {"lore_001": "lore"},
    )

    evidence = context.evidence_bundle[0]
    assert evidence["payload"]["summary"] == _OBSERVATION_FACT_SENTINEL
    assert evidence["summary"] == _OBSERVATION_FACT_SENTINEL


def test_repeated_dropped_searches_are_absent_from_clean_finalization_context() -> None:
    faction_first = ToolCall(
        "faction-first",
        "search_factions",
        {"query": "faction", "limit": 5},
    )
    faction_second = ToolCall(
        "faction-second",
        "search_factions",
        {"query": "nothing else", "limit": 5},
    )
    lore_first = ToolCall(
        "lore-first",
        "search_lore",
        {"query": "nothing", "limit": 5},
    )
    lore_second = ToolCall(
        "lore-second",
        "search_lore",
        {"query": "still nothing", "limit": 5},
    )
    faction_direct = ToolCall(
        "faction-direct",
        "get_faction",
        {"faction_id": "faction_direct"},
    )
    lore_direct = ToolCall("lore-direct", "get_lore", {"lore_id": "lore_direct"})
    context = _build(
        _request(),
        [
            (
                1,
                (faction_first,),
                (
                    {
                        "status": "ok",
                        "results": [_search_result("faction_direct", "faction")],
                    },
                ),
                ("faction_direct",),
            ),
            (
                2,
                (faction_second,),
                ({"status": "not_found", "results": []},),
                (),
            ),
            (
                3,
                (lore_first,),
                ({"status": "empty", "results": []},),
                (),
            ),
            (
                4,
                (lore_second,),
                ({"status": "not_found", "results": []},),
                (),
            ),
            (
                5,
                (faction_direct, lore_direct),
                (
                    {
                        "status": "ok",
                        "result": {"source_id": "faction_direct", "summary": "direct observation"},
                    },
                    {
                        "status": "ok",
                        "result": {"source_id": "lore_direct", "statement": "direct observation"},
                    },
                ),
                ("faction_direct", "lore_direct"),
            ),
        ],
        {"faction_direct": "faction", "lore_direct": "lore"},
    )

    assert context.source_ids == ("faction_direct", "lore_direct")
    assert [item["source_id"] for item in context.evidence_bundle] == [
        "faction_direct",
        "lore_direct",
    ]
    assert all(
        all(item["kind"] == "explicit_get" for item in evidence["provenance"])
        for evidence in context.evidence_bundle
    )


def test_duplicate_search_and_get_prefers_direct_source_without_search_observation() -> None:
    search = ToolCall("search", "search_factions", {"query": "faction", "limit": 5})
    direct = ToolCall("direct", "get_faction", {"faction_id": "faction_001"})
    context = _build(
        _request(),
        [
            (
                1,
                (search,),
                ({"status": "ok", "results": [_search_result("faction_001", "faction")]},),
                ("faction_001",),
            ),
            (
                2,
                (direct,),
                ({"status": "ok", "result": {"source_id": "faction_001", "core_function": {"description": "richer"}}},),
                ("faction_001",),
            ),
        ],
        {"faction_001": "faction"},
    )

    assert context.source_ids == ("faction_001",)
    assert context.evidence_bundle[0]["source_id"] == "faction_001"
    assert context.evidence_bundle[0]["payload"]["core_function"]["description"] == "richer"
    assert context.evidence_bundle[0]["provenance"] == (
        {"kind": "explicit_get", "tool_name": "get_faction", "round": 2},
    )


def test_repeated_search_only_results_are_unique_and_bound_per_source_type() -> None:
    first_ids = ["faction_001", "faction_002", "faction_003", "faction_004"]
    second_ids = ["faction_003", "faction_004", "faction_005", "faction_006", "faction_001"]
    first = ToolCall("search-1", "search_factions", {"query": "faction", "limit": 10})
    second = ToolCall("search-2", "search_factions", {"query": "faction", "limit": 10})
    all_ids = sorted(set(first_ids + second_ids))
    context = _build(
        _request(),
        [
            (
                1,
                (first,),
                ({"status": "ok", "results": [_search_result(item, "faction", label="faction") for item in first_ids]},),
                tuple(first_ids),
            ),
            (
                2,
                (second,),
                ({"status": "ok", "results": [_search_result(item, "faction", label="faction") for item in second_ids]},),
                tuple(second_ids),
            ),
        ],
        {source_id: "faction" for source_id in all_ids},
    )

    selected_ids = [item["source_id"] for item in context.evidence_bundle]
    assert len(selected_ids) == 5
    assert len(set(selected_ids)) == 5
    assert selected_ids == [f"faction_{index:03d}" for index in range(1, 6)]
    assert "faction_006" not in selected_ids


def test_request_matched_canon_survives_search_discovery_bound() -> None:
    ids = [f"faction_{index:03d}" for index in range(1, 6)] + ["faction_999"]
    search = ToolCall("search", "search_factions", {"query": "faction", "limit": 10})
    context = _build(
        _request("必须使用 faction_999 的既有信息"),
        [
            (
                1,
                (search,),
                ({"status": "ok", "results": [_search_result(item, "faction", label="faction") for item in ids]},),
                tuple(ids),
            )
        ],
        {source_id: "faction" for source_id in ids},
        known_source_ids=set(ids),
    )

    assert "faction_999" in context.source_ids
    selected_ids = [item["source_id"] for item in context.evidence_bundle]
    assert selected_ids == ids
    explicit = next(
        item for item in context.evidence_bundle if item["source_id"] == "faction_999"
    )
    assert explicit["provenance"][0]["kind"] == "request_explicit"


def test_filtered_tool_call_groups_have_no_orphan_tool_messages() -> None:
    search = ToolCall("search", "search_factions", {"query": "faction", "limit": 5})
    direct = ToolCall("direct", "get_faction", {"faction_id": "faction_001"})
    context = _build(
        _request(),
        [
            (
                1,
                (search, direct),
                (
                    {"status": "ok", "results": [_search_result("faction_001", "faction")]},
                    {"status": "ok", "result": {"source_id": "faction_001", "summary": "direct observation"}},
                ),
                ("faction_001", "faction_001"),
            )
        ],
        {"faction_001": "faction"},
    )

    assert [message.role for message in context.messages] == ["user"]
    assert "tool_calls" not in json.dumps(
        [message.content for message in context.messages], ensure_ascii=False
    )
    assert context.evidence_bundle[0]["source_id"] == "faction_001"


class _SyntheticToolbox:
    tool_definitions = (
        ToolDefinition("search_factions", "synthetic search", {"type": "object"}),
        ToolDefinition("get_world_rules", "synthetic world", {"type": "object"}),
    )
    allowed_tools = frozenset(item.name for item in tool_definitions)

    def __init__(self, source_ids: list[str]) -> None:
        self.source_ids = source_ids

    def execute(self, *, tool_name: str, arguments: dict[str, Any], round_number: int, **_: Any) -> AuthoringToolExecution:
        if tool_name == "search_factions":
            observation = {
                "status": "ok",
                "results": [_search_result(source_id, "faction", label="faction") for source_id in self.source_ids],
            }
            source_types = {source_id: "faction" for source_id in self.source_ids}
            audit = _audit(round_number, ToolCall(f"search-{round_number}", tool_name, arguments), self.source_ids)
            return AuthoringToolExecution(observation, audit, frozenset(source_types), source_types)
        if tool_name == "get_world_rules":
            audit = _audit(round_number, ToolCall(f"world-{round_number}", tool_name, arguments), ["world_rules"])
            return AuthoringToolExecution(
                {"status": "ok", "result": {"source_id": "world_rules", "rules": ["WORLD_RULE_OBSERVATION"]}},
                audit,
                frozenset({"world_rules"}),
                {"world_rules": "world_rules"},
            )
        raise AssertionError(f"unexpected tool {tool_name}")


class _GroupedProtocolToolbox:
    tool_definitions = (
        ToolDefinition("search_factions", "synthetic search", {"type": "object"}),
        ToolDefinition("get_world_rules", "synthetic world", {"type": "object"}),
        ToolDefinition("get_faction", "synthetic faction", {"type": "object"}),
    )
    allowed_tools = frozenset(item.name for item in tool_definitions)

    def __init__(self, observation_sentinel: str = _RAW_TOOL_RESULT_SENTINEL) -> None:
        self._search_call_count = 0
        self._execution_count = 0
        self.observation_sentinel = observation_sentinel

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        round_number: int,
        **_: Any,
    ) -> AuthoringToolExecution:
        self._execution_count += 1
        if tool_name == "search_factions":
            self._search_call_count += 1
            if self._search_call_count == 1:
                source_ids = [f"faction_{index:03d}" for index in range(1, 7)] + ["faction_006"]
                results = [
                    _search_result(source_id, "faction", label="faction")
                    for source_id in source_ids
                ]
                results[1]["summary"] = self.observation_sentinel
            elif self._search_call_count == 2:
                source_ids = ["faction_006"]
                results = [
                    _search_result(source_id, "faction", label="only pruned")
                    for source_id in source_ids
                ]
            else:
                raise AssertionError("unexpected extra grouped search call")
            source_types = {source_id: "faction" for source_id in source_ids}
            audit = _audit(
                round_number,
                ToolCall(
                    f"audit-search-{self._execution_count}",
                    tool_name,
                    arguments,
                ),
                source_ids,
            )
            return AuthoringToolExecution(
                {"status": "ok", "results": results},
                audit,
                frozenset(source_types),
                source_types,
            )
        if tool_name == "get_world_rules":
            audit = _audit(
                round_number,
                ToolCall(
                    f"audit-world-{self._execution_count}",
                    tool_name,
                    arguments,
                ),
                ["world_rules"],
            )
            return AuthoringToolExecution(
                {
                    "status": "ok",
                    "result": {"source_id": "world_rules", "rules": ["RULE-001"]},
                },
                audit,
                frozenset({"world_rules"}),
                {"world_rules": "world_rules"},
            )
        if tool_name == "get_faction":
            assert arguments.get("faction_id") == "faction_001"
            audit = _audit(
                round_number,
                ToolCall(
                    f"audit-faction-{self._execution_count}",
                    tool_name,
                    arguments,
                ),
                ["faction_001"],
            )
            return AuthoringToolExecution(
                {
                    "status": "ok",
                    "result": {
                        "source_id": "faction_001",
                        "core_function": {"description": "richer direct fact"},
                    },
                },
                audit,
                frozenset({"faction_001"}),
                {"faction_001": "faction"},
            )
        raise AssertionError(f"unexpected tool {tool_name}")


def test_real_agent_finalization_uses_clean_bundle_and_keeps_full_audit_trail() -> None:
    request = _request(
        f"设计一个完全原创的角色。输入标记：{_RAW_BRIEF_SENTINEL}"
    )
    model = ScriptedAgentModel(
        [
            ModelTurn(
                tool_calls=(
                    ToolCall(
                        "search-primary",
                        "search_factions",
                        {
                            "query": "faction",
                            "limit": 10,
                            "audit_marker": _RAW_TOOL_ARGUMENT_SENTINEL,
                        },
                    ),
                    ToolCall(
                        "search-pruned",
                        "search_factions",
                        {"query": "only-pruned", "limit": 1},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ToolCall("world-rules", "get_world_rules", {}),
                    ToolCall(
                        "get-faction",
                        "get_faction",
                        {"faction_id": "faction_001"},
                    ),
                )
            ),
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(
                    _payload(open_questions=[_RAW_MODEL_OUTPUT_SENTINEL]),
                    ensure_ascii=False,
                )
            ),
        ]
    )
    agent = CharacterGenerationAgent(model)
    agent.tools = _GroupedProtocolToolbox()

    result = agent.generate(request)

    assert len(model.prompts) == 4
    full_history_prompt = model.prompts[2]
    final_prompt = model.prompts[3]
    assert [
        len(full_history_prompt.messages[index].content["tool_calls"])
        for index in (1, 4)
    ] == [2, 2]
    assert final_prompt.available_tools == ()
    assert LiveLLMAdapter._provider_tools(final_prompt) == []

    assert [message.role for message in final_prompt.messages] == ["user"]
    provider_messages = LiveLLMAdapter._provider_messages(final_prompt)
    assert [message["role"] for message in provider_messages] == ["system", "user"]
    assert all("tool_calls" not in message for message in provider_messages)
    assert all(message["role"] != "tool" for message in provider_messages)
    provider_payload = json.loads(provider_messages[1]["content"])
    assert provider_payload["request"]["brief"] == request.brief
    bundle_ids = tuple(item["source_id"] for item in provider_payload["evidence_bundle"])
    assert bundle_ids == tuple(
        [f"faction_{index:03d}" for index in range(1, 7)] + ["world_rules"]
    )
    serialized_provider_payload = json.dumps(provider_messages, ensure_ascii=False)
    assert _RAW_TOOL_RESULT_SENTINEL in serialized_provider_payload
    for sentinel in (
        _RAW_TOOL_ARGUMENT_SENTINEL,
        _RAW_MODEL_OUTPUT_SENTINEL,
        "search-primary",
        "search-pruned",
        "tool_call_id",
    ):
        assert sentinel not in serialized_provider_payload
    assert [item.tool_name for item in result.audit.tool_calls] == [
        "search_factions",
        "search_factions",
        "get_world_rules",
        "get_faction",
    ]

    expected_sources = tuple(
        [f"faction_{index:03d}" for index in range(1, 7)] + ["world_rules"]
    )
    assert final_prompt.evidence
    assert result.sources == expected_sources
    assert result.audit.source_ids == expected_sources

    prompt_shape_json = json.dumps(
        {"prompt_shape": _prompt_shape(final_prompt)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert _prompt_shape(final_prompt)["available_tool_count"] == 0
    for sentinel in (_RAW_TOOL_ARGUMENT_SENTINEL, _RAW_TOOL_RESULT_SENTINEL, _RAW_MODEL_OUTPUT_SENTINEL):
        assert sentinel not in prompt_shape_json


def test_evidence_bundle_uses_observation_fact_not_resolver_fact() -> None:
    resolver = KnowledgeResolver()
    faction = dict(resolver.factions["faction_002"])
    core_function = dict(faction.get("core_function", {}))
    core_function["description"] = _RESOLVER_FACT_SENTINEL
    faction["core_function"] = core_function
    resolver.factions["faction_002"] = faction

    model = ScriptedAgentModel(
        [
            ModelTurn(
                tool_calls=(
                    ToolCall(
                        "search-primary",
                        "search_factions",
                        {"query": "faction", "limit": 10},
                    ),
                    ToolCall(
                        "search-pruned",
                        "search_factions",
                        {"query": "only-pruned", "limit": 1},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ToolCall("world-rules", "get_world_rules", {}),
                    ToolCall(
                        "get-faction",
                        "get_faction",
                        {"faction_id": "faction_001"},
                    ),
                )
            ),
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )
    agent = CharacterGenerationAgent(model, resolver=resolver)
    agent.tools = _GroupedProtocolToolbox(_OBSERVATION_FACT_SENTINEL)

    result = agent.generate(_request())

    final_prompt = model.prompts[-1]
    provider_messages = LiveLLMAdapter._provider_messages(final_prompt)
    serialized = json.dumps(provider_messages, ensure_ascii=False)
    assert _OBSERVATION_FACT_SENTINEL in serialized
    assert _RESOLVER_FACT_SENTINEL not in serialized
    assert result.sources == result.audit.source_ids


def test_unknown_retrieved_source_id_fails_closed() -> None:
    call = ToolCall("unknown", "get_faction", {"faction_id": "faction_unknown"})

    with pytest.raises(ModelMalformedResponseError, match="known"):
        _build(
            _request(),
            [
                (
                    1,
                    (call,),
                    (
                        {
                            "status": "ok",
                            "result": {
                                "source_id": "faction_unknown",
                                "summary": "untrusted observation",
                            },
                        },
                    ),
                    ("faction_unknown",),
                )
            ],
            {"faction_unknown": "faction"},
            known_source_ids={"world_rules"},
        )


def test_unknown_retrieved_source_type_fails_closed() -> None:
    call = ToolCall("unknown-type", "get_faction", {"faction_id": "faction_001"})

    with pytest.raises(ModelMalformedResponseError, match="source type"):
        _build(
            _request(),
            [
                (
                    1,
                    (call,),
                    (
                        {
                            "status": "ok",
                            "result": {
                                "source_id": "faction_001",
                                "summary": "untrusted source type",
                            },
                        },
                    ),
                    ("faction_001",),
                )
            ],
            {"faction_001": "unknown_type"},
            known_source_ids={"faction_001"},
        )


def test_missing_observation_fact_fails_closed_without_generic_summary() -> None:
    call = ToolCall("missing-fact", "get_faction", {"faction_id": "faction_001"})

    with pytest.raises(ModelMalformedResponseError, match="observation payload"):
        _build(
            _request(),
            [
                (
                    1,
                    (call,),
                    (
                        {
                            "status": "ok",
                            "result": {
                                "source_id": "faction_001",
                                "detail": "not an allowed factual field",
                            },
                        },
                    ),
                    ("faction_001",),
                )
            ],
            {"faction_001": "faction"},
        )


def test_restricted_lore_without_public_observation_fails_closed() -> None:
    call = ToolCall("restricted", "get_lore", {"lore_id": "lore_secret_001"})

    with pytest.raises(ModelMalformedResponseError, match="restricted lore"):
        _build(
            _request(),
            [
                (
                    1,
                    (call,),
                    (
                        {
                            "status": "ok",
                            "result": {
                                "source_id": "lore_secret_001",
                                "statement": "restricted observation",
                                "sensitivity": "restricted",
                            },
                        },
                    ),
                    ("lore_secret_001",),
                )
            ],
            {"lore_secret_001": "lore"},
            allow_restricted_lore=False,
        )


def test_retrieved_but_pruned_canon_id_is_rejected_by_grounding() -> None:
    source_ids = [f"faction_{index:03d}" for index in range(1, 7)]
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("search", "search_factions", {"query": "faction", "limit": 10}),)),
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(background="她参考了 faction_006 的制度经验。"), ensure_ascii=False)),
        ]
    )
    agent = CharacterGenerationAgent(model)
    agent.tools = _SyntheticToolbox(source_ids)

    with pytest.raises(AgentExecutionError) as captured:
        agent.generate(_request())

    assert captured.value.grounding_failure.check == "field:background"
    assert captured.value.grounding_failure.canon_id == "faction_006"
    final_prompt = model.prompts[-1]
    assert "faction_006" not in {e.source_lore_id for e in final_prompt.evidence}
    assert all(
        "faction_006" not in str(message.content)
        for message in final_prompt.messages
    )


def test_recovery_receives_the_same_clean_source_set_as_finalization() -> None:
    source_ids = [f"faction_{index:03d}" for index in range(1, 7)]
    incomplete = _payload()
    incomplete.pop("new_design_elements")
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("search", "search_factions", {"query": "faction", "limit": 10}),)),
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(incomplete, ensure_ascii=False)),
            ModelTurn(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )
    agent = CharacterGenerationAgent(model)
    agent.tools = _SyntheticToolbox(source_ids)

    result = agent.generate(_request())

    final_prompt = model.prompts[2]
    recovery_prompt = model.prompts[3]
    final_ids = tuple(
        item["source_id"] for item in final_prompt.authoring_payload["evidence_bundle"]
    )
    assert final_ids == tuple(f"faction_{index:03d}" for index in range(1, 6))
    assert tuple(recovery_prompt.authoring_payload["available_canon_source_ids"]) == final_ids
    assert recovery_prompt.messages == final_prompt.messages == (final_prompt.messages[0],)
    assert recovery_prompt.authoring_payload["evidence_bundle"] == final_prompt.authoring_payload["evidence_bundle"]
    recovery_provider_messages = LiveLLMAdapter._provider_messages(recovery_prompt)
    assert [message["role"] for message in recovery_provider_messages] == ["system", "user"]
    assert all("tool_calls" not in message for message in recovery_provider_messages)
    assert all(message["role"] != "tool" for message in recovery_provider_messages)
    assert result.sources == final_ids
    assert result.audit.source_ids == final_ids
    assert set(result.audit.tool_calls[0].allowed_lore_ids) == set(source_ids)


def test_action_loop_sequence_and_count_remain_unchanged_before_finalization() -> None:
    model = ScriptedAgentModel(
        [
            ModelTurn(tool_calls=(ToolCall("world", "get_world_rules", {}),)),
            ModelTurn(tool_calls=(ToolCall("search", "search_factions", {"query": "nothing", "limit": 5}),)),
            ModelTurn(text="FINALIZE"),
            ModelTurn(text=json.dumps(_payload(), ensure_ascii=False)),
        ]
    )

    result = CharacterGenerationAgent(model).generate(_request())

    assert len(model.prompts) == 4
    assert [prompt.response_format for prompt in model.prompts[:3]] == [
        "character_authoring_action",
        "character_authoring_action",
        "character_authoring_action",
    ]
    assert model.prompts[3].response_format == "character_draft"
    assert [entry.tool_name for entry in result.audit.tool_calls] == [
        "get_world_rules",
        "search_factions",
    ]
    assert result.audit.tool_rounds == 2
    assert [prompt.turn_number for prompt in model.prompts] == [1, 2, 3, 4]


def test_finalization_provider_payload_is_clean_and_bundle_is_deterministic() -> None:
    request = _request(f"设计一个完全原创的角色。输入标记：{_RAW_BRIEF_SENTINEL}")
    model = ScriptedAgentModel(
        [
            ModelTurn(
                tool_calls=(
                    ToolCall(
                        "search-primary",
                        "search_factions",
                        {
                            "query": "faction",
                            "limit": 10,
                            "audit_marker": _RAW_TOOL_ARGUMENT_SENTINEL,
                        },
                    ),
                    ToolCall(
                        "search-pruned",
                        "search_factions",
                        {"query": "only-pruned", "limit": 1},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ToolCall("world-rules", "get_world_rules", {}),
                    ToolCall("get-faction", "get_faction", {"faction_id": "faction_001"}),
                )
            ),
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(
                    _payload(open_questions=[_RAW_MODEL_OUTPUT_SENTINEL]),
                    ensure_ascii=False,
                )
            ),
        ]
    )
    agent = CharacterGenerationAgent(model)
    agent.tools = _GroupedProtocolToolbox()

    result = agent.generate(request)

    final_prompt = model.prompts[3]
    provider_messages = LiveLLMAdapter._provider_messages(final_prompt)
    assert [message["role"] for message in provider_messages] == ["system", "user"]
    assert all("tool_calls" not in message for message in provider_messages)
    assert all(message["role"] != "tool" for message in provider_messages)
    provider_payload = json.loads(provider_messages[1]["content"])
    bundle = provider_payload["evidence_bundle"]
    assert bundle
    assert all(
        {"source_id", "source_type", "payload", "summary", "provenance"}
        <= set(item)
        for item in bundle
    )
    serialized = json.dumps(provider_messages, ensure_ascii=False)
    assert _RAW_TOOL_RESULT_SENTINEL in serialized
    for sentinel in (
        _RAW_TOOL_ARGUMENT_SENTINEL,
        _RAW_MODEL_OUTPUT_SENTINEL,
        "search-primary",
        "search-pruned",
        "tool_call_id",
    ):
        assert sentinel not in serialized

    assert result.sources == result.audit.source_ids
