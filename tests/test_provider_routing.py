from __future__ import annotations

import pytest

from agents import (
    LiveLLMSettings,
    ModelConfigurationError,
    ProviderRoute,
    resolve_provider_route,
)


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "NPC_LLM_PROVIDER": "openai",
        "NPC_LLM_MODEL": "default-model",
        "NPC_LLM_API_KEY": "test-only-key",
    }
    values.update(overrides)
    return values


def test_default_route_is_secret_free_and_provider_model_are_distinct() -> None:
    route = resolve_provider_route("character_generation", environment=_environment())

    assert isinstance(route, ProviderRoute)
    assert route.provider_id == "openai"
    assert route.model_id == "default-model"
    assert route.source == "environment"
    assert "test-only-key" not in repr(route)


@pytest.mark.parametrize(
    "operation",
    [
        "character_generation",
        "character_structural_recovery",
        "character_repair",
        "skill_generation",
        "skill_repair",
    ],
)
def test_authoritative_v41_route_resolves_for_all_live_operations(operation: str) -> None:
    route = resolve_provider_route(
        operation,
        environment=_environment(
            NPC_LLM_PROVIDER="opencode_go",
            NPC_LLM_MODEL="deepseek-v4.1-flash",
        ),
    )

    assert (route.provider_id, route.model_id) == (
        "opencode_go",
        "deepseek-v4.1-flash",
    )


def test_operation_override_beats_default_without_prompt_input() -> None:
    route = resolve_provider_route(
        "skill_generation",
        environment=_environment(
            NPC_LLM_SKILL_GENERATION_PROVIDER="deepseek",
            NPC_LLM_SKILL_GENERATION_MODEL="skill-model",
        ),
    )

    assert (route.provider_id, route.model_id) == ("deepseek", "skill-model")
    assert route.source == "operation_override"


def test_trusted_runtime_override_beats_operation_override_and_environment() -> None:
    route = resolve_provider_route(
        "skill_generation",
        environment=_environment(
            NPC_LLM_SKILL_GENERATION_PROVIDER="deepseek",
            NPC_LLM_SKILL_GENERATION_MODEL="skill-model",
        ),
        runtime_override={"provider": "openai", "model": "trusted-model"},
    )

    assert (route.provider_id, route.model_id) == ("openai", "trusted-model")
    assert route.source == "runtime_override"


def test_missing_operation_override_pair_fails_closed() -> None:
    with pytest.raises(ModelConfigurationError, match="must be configured together"):
        resolve_provider_route(
            "character_repair",
            environment=_environment(NPC_LLM_CHARACTER_REPAIR_PROVIDER="deepseek"),
        )


def test_unknown_provider_fails_closed_without_fallback() -> None:
    with pytest.raises(ModelConfigurationError, match="Unsupported NPC_LLM_PROVIDER"):
        resolve_provider_route(
            "character_generation", environment=_environment(NPC_LLM_PROVIDER="unknown")
        )


def test_settings_repr_redacts_secret() -> None:
    settings = LiveLLMSettings.from_environment(
        _environment(NPC_LLM_API_KEY="super-secret-test-value")
    )

    assert "super-secret-test-value" not in repr(settings)
    assert "super-secret-test-value" not in str(settings)


def test_route_rejects_invalid_model_identifier() -> None:
    with pytest.raises(ModelConfigurationError, match="NPC_LLM_MODEL"):
        resolve_provider_route("character_generation", environment=_environment(NPC_LLM_MODEL=""))


def test_base_url_credentials_are_rejected_without_network_call() -> None:
    with pytest.raises(ModelConfigurationError, match="must not contain credentials"):
        resolve_provider_route(
            "character_generation",
            environment=_environment(NPC_LLM_BASE_URL="https://user:pass@example.test/v1"),
        )
