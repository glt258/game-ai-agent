from __future__ import annotations

import pytest

from agents import (
    DeterministicDemoModel,
    LiveLLMAdapter,
    LiveLLMSettings,
    ModelConfigurationError,
    ProviderCompletion,
    model_from_environment,
)


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


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"NPC_AGENT_MODEL": "online"}, "Supported modes"),
        (live_environment(NPC_LLM_PROVIDER="banana"), "Supported providers"),
        (live_environment(NPC_LLM_MODEL=""), "NPC_LLM_MODEL"),
        (live_environment(NPC_LLM_API_KEY=""), "NPC_LLM_API_KEY"),
        (live_environment(NPC_LLM_BASE_URL="relative/path"), "absolute HTTP"),
        (live_environment(NPC_LLM_TIMEOUT_SECONDS="0"), "from 1 to 300"),
        (live_environment(NPC_LLM_TIMEOUT_SECONDS="forever"), "must be a number"),
        (live_environment(NPC_LLM_MAX_RETRIES="4"), "from 0 to 3"),
        (live_environment(NPC_LLM_MAX_RETRIES="many"), "must be an integer"),
    ],
)
def test_invalid_model_configuration_fails_fast(environment, message):
    with pytest.raises(ModelConfigurationError, match=message):
        model_from_environment(environment, client=NeverCalledClient())


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
