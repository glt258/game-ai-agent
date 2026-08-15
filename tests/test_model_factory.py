from __future__ import annotations

import pytest

import agents.model_factory as model_factory_module
from agents import (
    DeterministicDemoModel,
    LiveLLMAdapter,
    LiveLLMSettings,
    ModelConfigurationError,
    OPENCODE_GO_BASE_URL,
    ProviderCompletion,
    model_from_environment,
)
from agents.model_factory import DEEPSEEK_BASE_URL


class NeverCalledClient:
    def complete(self, **_):
        return ProviderCompletion(text="unused")


def live_environment(**overrides: str) -> dict[str, str]:
    values = {
        "NPC_AGENT_MODEL": "live",
        "NPC_LLM_PROVIDER": "openai",
        "NPC_LLM_MODEL": "configured-model",
        "NPC_LLM_API_KEY": "placeholder-test-key",
    }
    values.update(overrides)
    return values


def test_offline_is_default_and_does_not_require_api_key():
    assert isinstance(model_from_environment({}), DeterministicDemoModel)


def test_live_mode_builds_injected_adapter():
    model = model_from_environment(live_environment(), client=NeverCalledClient())
    assert isinstance(model, LiveLLMAdapter)
    assert model.provider == "openai" and model.model == "configured-model"


def test_deepseek_settings_use_official_default_base_url():
    settings = LiveLLMSettings.from_environment(
        live_environment(NPC_LLM_PROVIDER="deepseek")
    )
    assert settings.provider == "deepseek"
    assert settings.model == "configured-model"
    assert settings.base_url == DEEPSEEK_BASE_URL


def test_deepseek_explicit_base_url_overrides_provider_default():
    settings = LiveLLMSettings.from_environment(
        live_environment(
            NPC_LLM_PROVIDER="deepseek",
            NPC_LLM_BASE_URL="https://example.test/v1",
        )
    )
    assert settings.base_url == "https://example.test/v1"


def test_opencode_go_known_model_uses_gateway_default_and_logical_provider():
    settings = LiveLLMSettings.from_environment(
        live_environment(
            NPC_LLM_PROVIDER="opencode_go",
            NPC_LLM_MODEL="deepseek-v4-flash",
        )
    )

    assert settings.provider == "opencode_go"
    assert settings.base_url == OPENCODE_GO_BASE_URL
    assert settings.profile.provider_options == {}


def test_opencode_go_unknown_model_requires_explicit_transport():
    environment = live_environment(
        NPC_LLM_PROVIDER="opencode_go", NPC_LLM_MODEL="future-model"
    )
    with pytest.raises(ModelConfigurationError, match="Unknown OpenCode Go model"):
        LiveLLMSettings.from_environment(environment)

    environment["NPC_LLM_TRANSPORT"] = "chat_completions"
    settings = LiveLLMSettings.from_environment(environment)
    assert settings.base_url == OPENCODE_GO_BASE_URL


def test_generic_openai_compatible_requires_explicit_base_url():
    environment = live_environment(NPC_LLM_PROVIDER="openai_compatible")
    with pytest.raises(ModelConfigurationError, match="NPC_LLM_BASE_URL is required"):
        LiveLLMSettings.from_environment(environment)

    environment["NPC_LLM_BASE_URL"] = "https://gateway.example.test/v1"
    settings = LiveLLMSettings.from_environment(environment)
    assert settings.provider == "openai_compatible"
    assert settings.base_url == "https://gateway.example.test/v1"


def test_explicit_structured_output_capability_override_is_validated():
    settings = LiveLLMSettings.from_environment(
        live_environment(NPC_LLM_STRUCTURED_OUTPUT="json_schema")
    )
    assert settings.profile.capabilities.supports_json_schema

    with pytest.raises(ModelConfigurationError, match="NPC_LLM_STRUCTURED_OUTPUT"):
        LiveLLMSettings.from_environment(
            live_environment(NPC_LLM_STRUCTURED_OUTPUT="wishful_thinking")
        )


def test_deepseek_factory_configures_shared_openai_compatible_transport(monkeypatch):
    captured = {}

    class CapturingClient(NeverCalledClient):
        def __init__(self, **options):
            captured.update(options)

    monkeypatch.setattr(model_factory_module, "OpenAIChatClient", CapturingClient)

    model = model_factory_module.model_from_environment(
        live_environment(NPC_LLM_PROVIDER="deepseek")
    )

    assert isinstance(model, LiveLLMAdapter)
    assert model.provider == "deepseek"
    assert captured["base_url"] == DEEPSEEK_BASE_URL
    assert captured["request_options"] == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }


def test_openai_factory_path_keeps_provider_defaults_unchanged(monkeypatch):
    captured = {}

    class CapturingClient(NeverCalledClient):
        def __init__(self, **options):
            captured.update(options)

    monkeypatch.setattr(model_factory_module, "OpenAIChatClient", CapturingClient)

    model = model_factory_module.model_from_environment(live_environment())

    assert isinstance(model, LiveLLMAdapter)
    assert model.provider == "openai"
    assert captured["base_url"] is None
    assert captured["request_options"] == {}


def test_opencode_go_does_not_inherit_direct_deepseek_request_options(monkeypatch):
    captured = {}

    class CapturingClient(NeverCalledClient):
        def __init__(self, **options):
            captured.update(options)

    monkeypatch.setattr(model_factory_module, "OpenAIChatClient", CapturingClient)

    model = model_factory_module.model_from_environment(
        live_environment(
            NPC_LLM_PROVIDER="opencode_go",
            NPC_LLM_MODEL="deepseek-v4-flash",
        )
    )

    assert isinstance(model, LiveLLMAdapter)
    assert model.provider == "opencode_go"
    assert captured["base_url"] == OPENCODE_GO_BASE_URL
    assert captured["request_options"] == {}


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"NPC_AGENT_MODEL": "online"}, "Supported modes"),
        (live_environment(NPC_LLM_PROVIDER="banana"), "Supported providers"),
        (
            live_environment(NPC_LLM_PROVIDER="deepseek", NPC_LLM_MODEL=""),
            "NPC_LLM_MODEL",
        ),
        (
            live_environment(NPC_LLM_PROVIDER="deepseek", NPC_LLM_API_KEY=""),
            "NPC_LLM_API_KEY",
        ),
        (live_environment(NPC_LLM_MODEL=""), "NPC_LLM_MODEL"),
        (live_environment(NPC_LLM_API_KEY=""), "NPC_LLM_API_KEY"),
        (live_environment(NPC_LLM_BASE_URL="relative/path"), "absolute HTTP"),
        (live_environment(NPC_LLM_TIMEOUT_SECONDS="0"), "from 1 to 300"),
        (live_environment(NPC_LLM_TIMEOUT_SECONDS="forever"), "must be a number"),
        (live_environment(NPC_LLM_MAX_RETRIES="4"), "from 0 to 3"),
        (live_environment(NPC_LLM_MAX_RETRIES="many"), "must be an integer"),
        (live_environment(NPC_LLM_TRANSPORT="banana"), "NPC_LLM_TRANSPORT"),
    ],
)
def test_invalid_model_configuration_fails_fast(environment, message):
    with pytest.raises(ModelConfigurationError, match=message):
        model_from_environment(environment, client=NeverCalledClient())


def test_unknown_provider_error_lists_all_supported_providers():
    with pytest.raises(ModelConfigurationError) as captured:
        model_from_environment(
            live_environment(NPC_LLM_PROVIDER="banana"),
            client=NeverCalledClient(),
        )
    assert "openai" in str(captured.value)
    assert "deepseek" in str(captured.value)


def test_live_settings_accept_compatible_https_base_url():
    settings = LiveLLMSettings.from_environment(
        live_environment(
            NPC_LLM_BASE_URL="https://gateway.example.test/v1",
            NPC_LLM_TIMEOUT_SECONDS="12.5",
            NPC_LLM_MAX_RETRIES="1",
        )
    )
    assert settings.base_url == "https://gateway.example.test/v1"
    assert settings.timeout_seconds == 12.5 and settings.max_retries == 1
