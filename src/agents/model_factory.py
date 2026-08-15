from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from .demo_model import DeterministicDemoModel
from .character_generation import DeterministicCharacterGenerationModel
from .errors import ModelCapabilityError, ModelConfigurationError
from .live_llm import LiveLLMAdapter
from .model_protocol import AgentModel
from .openai_provider import OpenAIChatClient
from .provider_protocol import ProviderChatClient
from .provider_profiles import (
    DEEPSEEK_BASE_URL,
    SUPPORTED_PROVIDERS,
    ProviderProfile,
    TransportFamily,
    apply_structured_output_override,
    resolve_provider_profile,
)


@dataclass(frozen=True)
class LiveLLMSettings:
    provider: str
    model: str
    api_key: str
    base_url: str | None
    timeout_seconds: float
    max_retries: int
    profile: ProviderProfile

    @property
    def transport(self) -> TransportFamily:
        return self.profile.transport_family

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LiveLLMSettings":
        values = os.environ if environment is None else environment
        provider = values.get("NPC_LLM_PROVIDER", "openai").strip().lower()
        model = values.get("NPC_LLM_MODEL", "").strip()
        if not model:
            raise ModelConfigurationError(
                "Live model selected but NPC_LLM_MODEL is not configured"
            )
        api_key = values.get("NPC_LLM_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError(
                "Live model selected but NPC_LLM_API_KEY is not configured"
            )
        explicit_base_url = values.get("NPC_LLM_BASE_URL", "").strip() or None
        transport_override = values.get("NPC_LLM_TRANSPORT", "").strip() or None
        profile = resolve_provider_profile(
            provider,
            model,
            transport_override=transport_override,
        )
        structured_output_override = (
            values.get("NPC_LLM_STRUCTURED_OUTPUT", "").strip() or None
        )
        profile = apply_structured_output_override(
            profile,
            structured_output_override,
        )
        if provider == "openai_compatible" and explicit_base_url is None:
            raise ModelConfigurationError(
                "NPC_LLM_BASE_URL is required for provider 'openai_compatible'"
            )
        base_url = explicit_base_url or profile.default_base_url
        if base_url is not None:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ModelConfigurationError(
                    "NPC_LLM_BASE_URL must be an absolute HTTP(S) URL"
                )
        timeout = cls._float(values, "NPC_LLM_TIMEOUT_SECONDS", 30.0)
        if not 1 <= timeout <= 300:
            raise ModelConfigurationError(
                "NPC_LLM_TIMEOUT_SECONDS must be from 1 to 300"
            )
        retries = cls._integer(values, "NPC_LLM_MAX_RETRIES", 2)
        if not 0 <= retries <= 3:
            raise ModelConfigurationError("NPC_LLM_MAX_RETRIES must be from 0 to 3")
        return cls(provider, model, api_key, base_url, timeout, retries, profile)

    @staticmethod
    def _float(values: Mapping[str, str], name: str, default: float) -> float:
        raw = values.get(name, str(default)).strip()
        try:
            return float(raw)
        except ValueError:
            raise ModelConfigurationError(f"{name} must be a number") from None

    @staticmethod
    def _integer(values: Mapping[str, str], name: str, default: int) -> int:
        raw = values.get(name, str(default)).strip()
        try:
            return int(raw)
        except ValueError:
            raise ModelConfigurationError(f"{name} must be an integer") from None


def model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    mode_override: str | None = None,
    client: ProviderChatClient | None = None,
) -> AgentModel:
    values = os.environ if environment is None else environment
    mode = (mode_override or values.get("NPC_AGENT_MODEL", "offline")).strip().lower()
    if mode == "offline":
        return DeterministicDemoModel()
    if mode != "live":
        raise ModelConfigurationError(
            f"Unsupported NPC_AGENT_MODEL '{mode}'. Supported modes: offline, live"
        )
    settings = LiveLLMSettings.from_environment(values)
    _ensure_transport_implemented(settings.profile)
    provider_client = client
    if provider_client is None:
        provider_client = OpenAIChatClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            request_options=settings.profile.provider_options,
        )
    return LiveLLMAdapter(
        provider_client,
        provider=settings.provider,
        model=settings.model,
        profile=settings.profile,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def character_model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    mode_override: str | None = None,
    client: ProviderChatClient | None = None,
) -> AgentModel:
    """Build the same provider-neutral model boundary for authoring.

    Configuration remains backward-compatible with the existing NPC_* names;
    only the offline fixture differs by agent consumer.
    """
    values = os.environ if environment is None else environment
    mode = (mode_override or values.get("NPC_AGENT_MODEL", "offline")).strip().lower()
    if mode == "offline":
        return DeterministicCharacterGenerationModel()
    if mode != "live":
        raise ModelConfigurationError(
            f"Unsupported NPC_AGENT_MODEL '{mode}'. Supported modes: offline, live"
        )
    settings = LiveLLMSettings.from_environment(values)
    _ensure_transport_implemented(settings.profile)
    provider_client = client
    if provider_client is None:
        provider_client = OpenAIChatClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            request_options=settings.profile.provider_options,
        )
    return LiveLLMAdapter(
        provider_client,
        provider=settings.provider,
        model=settings.model,
        profile=settings.profile,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def _ensure_transport_implemented(profile: ProviderProfile) -> None:
    if profile.transport_family is not TransportFamily.OPENAI_CHAT_COMPLETIONS:
        raise ModelCapabilityError(
            f"Transport '{profile.transport_family.value}' is recognized but not implemented"
        )
