from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, replace
from typing import Any

import pytest

from agents import (
    AgentPrompt,
    CharacterAuthoringView,
    CharacterGenerationRuntimeView,
    ConversationMessage,
    KNOWN_OPENCODE_GO_MODEL_PROFILES,
    LiveLLMAdapter,
    LiveLLMSettings,
    ModelAuthenticationError,
    ModelCapabilityError,
    ModelConfigurationError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    PROVIDER_PROFILES,
    ProviderCapabilities,
    ProviderClientError,
    ProviderCompletion,
    ProviderProfile,
    ProviderToolCall,
    ResponseMode,
    ThinkingModeBehavior,
    ToolDefinition,
    TransportFamily,
    resolve_provider_profile,
)


@dataclass(frozen=True)
class ProviderContractCase:
    provider: str
    model: str
    base_url: str | None
    profile: ProviderProfile


def _provider_contract_cases() -> tuple[ProviderContractCase, ...]:
    cases = [
        ProviderContractCase("openai", "contract-model", None, PROVIDER_PROFILES["openai"]),
        ProviderContractCase(
            "deepseek",
            "deepseek-v4-flash",
            PROVIDER_PROFILES["deepseek"].default_base_url,
            PROVIDER_PROFILES["deepseek"],
        ),
        ProviderContractCase(
            "openai_compatible",
            "gateway-model",
            "https://gateway.example.test/v1",
            PROVIDER_PROFILES["openai_compatible"],
        ),
    ]
    cases.extend(
        ProviderContractCase(
            "opencode_go", model, profile.default_base_url, profile
        )
        for model, profile in KNOWN_OPENCODE_GO_MODEL_PROFILES.items()
        if profile.transport_family is TransportFamily.OPENAI_CHAT_COMPLETIONS
        and profile.capabilities.supports_structured_output
    )
    return tuple(cases)


PROVIDER_CONTRACT_CASES = _provider_contract_cases()


@pytest.mark.parametrize(
    ("models", "transport"),
    [
        (
            (
                "glm-5.3", "glm-5.2", "glm-5.1", "kimi-k3", "kimi-k2.7-code",
                "kimi-k2.6", "deepseek-v4-pro", "deepseek-v4-flash",
                "mimo-v2.5", "mimo-v2.5-pro", "hy3",
            ),
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
        ),
        (("grok-4.5", "gpt-5.6-luna"), TransportFamily.OPENAI_RESPONSES),
        (
            (
                "minimax-m3", "minimax-m2.7", "minimax-m2.5", "qwen3.8-max",
                "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
            ),
            TransportFamily.ANTHROPIC_MESSAGES,
        ),
    ],
)
def test_current_opencode_go_model_routing_is_centralized(models, transport):
    for model in models:
        profile = KNOWN_OPENCODE_GO_MODEL_PROFILES[model]
        assert profile.transport_family is transport
        assert profile.default_base_url == "https://opencode.ai/zen/go/v1"
        assert profile.capabilities.supports_tools


class ContractClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = deque(outcomes)
        self.requests: list[dict[str, Any]] = []

    def complete(self, **request: Any) -> ProviderCompletion:
        self.requests.append(request)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _prompt(*, with_tools: bool = True) -> AgentPrompt:
    tools = (
        ToolDefinition(
            "search_lore",
            "Search safe Lore",
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    ) if with_tools else ()
    return AgentPrompt(
        "contract",
        CharacterAuthoringView("character_authoring", "test", ("lore",)),
        CharacterGenerationRuntimeView("request", "brief", (), (), (), ()),
        (ConversationMessage("user", "{}"),),
        tools,
        "provider-contract",
        1,
        response_format="character_draft",
    )


@pytest.mark.parametrize("case", PROVIDER_CONTRACT_CASES, ids=lambda case: f"{case.provider}:{case.model}")
def test_provider_profile_contract_matrix_config_and_routing(case):
    environment = {
        "NPC_LLM_PROVIDER": case.provider,
        "NPC_LLM_MODEL": case.model,
        "NPC_LLM_API_KEY": "placeholder-test-key",
    }
    if case.provider == "openai_compatible":
        environment["NPC_LLM_BASE_URL"] = case.base_url or ""

    settings = LiveLLMSettings.from_environment(environment)

    assert settings.provider == case.provider
    assert settings.model == case.model
    assert settings.base_url == case.base_url
    assert settings.transport is TransportFamily.OPENAI_CHAT_COMPLETIONS
    assert settings.profile.capabilities.supports_tools
    assert settings.profile.capabilities.supports_json_object


@pytest.mark.parametrize("case", PROVIDER_CONTRACT_CASES, ids=lambda case: f"{case.provider}:{case.model}")
def test_provider_profile_contract_matrix_tools_and_structured_output(case):
    client = ContractClient(
        [
            ProviderCompletion(
                tool_calls=(
                    ProviderToolCall("provider-call", "search_lore", '{"query":"public"}'),
                ),
                request_id="request-id",
            )
        ]
    )
    adapter = LiveLLMAdapter(
        client,
        provider=case.provider,
        model=case.model,
        profile=case.profile,
        sleep=lambda _: None,
    )

    turn = adapter.generate(_prompt())

    request = client.requests[0]
    assert request["model"] == case.model
    assert request["tools"][0]["function"]["name"] == "search_lore"
    assert request["response_contract"]["mode"] == "json_object"
    assert turn.tool_calls[0].id == "provider-call"
    assert turn.tool_calls[0].arguments == {"query": "public"}
    assert turn.invocation is not None
    assert turn.invocation.provider == case.provider
    assert turn.invocation.transport == "openai_chat_completions"
    assert turn.invocation.response_contract == "json_object"


@pytest.mark.parametrize("case", PROVIDER_CONTRACT_CASES, ids=lambda case: f"{case.provider}:{case.model}")
@pytest.mark.parametrize(
    ("failure", "error_type", "attempts"),
    [
        (ProviderClientError("authentication", retryable=False, status_code=401), ModelAuthenticationError, 1),
        (ProviderClientError("timeout", retryable=True), ModelTimeoutError, 2),
        (ProviderClientError("rate_limit", retryable=True, status_code=429), ModelRateLimitError, 2),
        (ProviderClientError("provider", retryable=True, status_code=500), ModelProviderError, 2),
    ],
)
def test_provider_profile_contract_matrix_normalizes_failures(case, failure, error_type, attempts):
    client = ContractClient([failure for _ in range(attempts)])
    adapter = LiveLLMAdapter(
        client,
        provider=case.provider,
        model=case.model,
        profile=case.profile,
        max_retries=1,
        sleep=lambda _: None,
    )

    with pytest.raises(error_type) as captured:
        adapter.generate(_prompt())

    assert len(client.requests) == attempts
    assert captured.value.audit is not None
    assert captured.value.audit.provider == case.provider
    assert captured.value.audit.transport == "openai_chat_completions"


@pytest.mark.parametrize("case", PROVIDER_CONTRACT_CASES, ids=lambda case: f"{case.provider}:{case.model}")
def test_provider_profile_contract_matrix_rejects_malformed_structured_json(case):
    client = ContractClient([ProviderCompletion(text="not-json")])
    adapter = LiveLLMAdapter(
        client,
        provider=case.provider,
        model=case.model,
        profile=case.profile,
    )

    with pytest.raises(ModelMalformedResponseError, match="not valid CharacterDraft JSON"):
        adapter.generate(_prompt(with_tools=False))

    assert len(client.requests) == 1


def test_json_schema_capability_is_preferred_over_json_object():
    profile = replace(
        PROVIDER_PROFILES["openai"],
        capabilities=replace(
            PROVIDER_PROFILES["openai"].capabilities,
            supports_json_schema=True,
        ),
    )
    client = ContractClient([ProviderCompletion(text='{"draft_id":"draft_x"}')])
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="schema-capable-model",
        profile=profile,
    )

    turn = adapter.generate(_prompt(with_tools=False))

    contract = client.requests[0]["response_contract"]
    assert contract["mode"] == ResponseMode.JSON_SCHEMA.value
    assert contract["json_schema"]["type"] == "object"
    assert contract["json_schema"]["additionalProperties"] is False
    assert turn.structured_output == {"draft_id": "draft_x"}


@pytest.mark.parametrize(
    ("supports_tools", "supports_json_object", "message"),
    [
        (False, True, "does not support tool calls"),
        (True, False, "cannot satisfy strict"),
    ],
)
def test_capability_mismatch_fails_before_provider_call(
    supports_tools, supports_json_object, message
):
    capabilities = ProviderCapabilities(
        supports_tools=supports_tools,
        supports_json_schema=False,
        supports_json_object=supports_json_object,
        supports_parallel_tool_calls=False,
        thinking_mode_behavior=ThinkingModeBehavior.PROVIDER_DEFAULT,
    )
    profile = replace(PROVIDER_PROFILES["openai"], capabilities=capabilities)
    client = ContractClient([ProviderCompletion(text="unused")])
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="limited-model",
        profile=profile,
    )

    with pytest.raises(ModelCapabilityError, match=message):
        adapter.generate(_prompt(with_tools=not supports_tools))

    assert client.requests == []


def test_unknown_opencode_go_model_requires_explicit_transport():
    with pytest.raises(ModelConfigurationError, match="Unknown OpenCode Go model"):
        resolve_provider_profile("opencode_go", "future-model")

    profile = resolve_provider_profile(
        "opencode_go",
        "future-model",
        transport_override="chat_completions",
    )
    assert profile.transport_family is TransportFamily.OPENAI_CHAT_COMPLETIONS
    assert profile.capabilities.supports_json_object


@pytest.mark.parametrize("model", ["glm-5.3", "kimi-k3", "mimo-v2.5", "hy3"])
def test_unverified_chat_structured_dialect_fails_closed_but_allows_explicit_override(model):
    profile = resolve_provider_profile("opencode_go", model)
    assert profile.transport_family is TransportFamily.OPENAI_CHAT_COMPLETIONS
    assert not profile.capabilities.supports_structured_output

    settings = LiveLLMSettings.from_environment(
        {
            "NPC_LLM_PROVIDER": "opencode_go",
            "NPC_LLM_MODEL": model,
            "NPC_LLM_API_KEY": "placeholder-test-key",
            "NPC_LLM_STRUCTURED_OUTPUT": "json_object",
        }
    )
    assert settings.profile.capabilities.supports_json_object


@pytest.mark.parametrize("transport", ["responses", "messages"])
def test_recognized_unimplemented_transports_fail_before_client_construction(transport):
    environment = {
        "NPC_AGENT_MODEL": "live",
        "NPC_LLM_PROVIDER": "opencode_go",
        "NPC_LLM_MODEL": "future-model",
        "NPC_LLM_API_KEY": "placeholder-test-key",
        "NPC_LLM_TRANSPORT": transport,
    }
    from agents import model_from_environment

    with pytest.raises(ModelCapabilityError, match="recognized but not implemented"):
        model_from_environment(environment, client=ContractClient([]))


@pytest.mark.parametrize("model", ["gpt-5.6-luna", "qwen3.8-max"])
def test_known_non_chat_models_resolve_then_fail_as_unimplemented(model):
    environment = {
        "NPC_AGENT_MODEL": "live",
        "NPC_LLM_PROVIDER": "opencode_go",
        "NPC_LLM_MODEL": model,
        "NPC_LLM_API_KEY": "placeholder-test-key",
    }
    from agents import model_from_environment

    with pytest.raises(ModelCapabilityError, match="recognized but not implemented"):
        model_from_environment(environment, client=ContractClient([]))


def test_invalid_transport_override_fails_fast():
    with pytest.raises(ModelConfigurationError, match="NPC_LLM_TRANSPORT"):
        resolve_provider_profile(
            "opencode_go", "future-model", transport_override="banana"
        )
