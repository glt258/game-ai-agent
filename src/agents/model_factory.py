from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from .demo_model import DeterministicDemoModel
from .errors import ModelConfigurationError
from .live_llm import LiveLLMAdapter
from .model_protocol import AgentModel
from .openai_provider import OpenAIChatClient
from .provider_protocol import ProviderChatClient


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
SUPPORTED_PROVIDERS = frozenset({"openai", "deepseek"})


@dataclass(frozen=True)
class LiveLLMSettings:
    provider: str
    model: str
    api_key: str
    base_url: str | None
    timeout_seconds: float
    max_retries: int

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LiveLLMSettings":
        values = os.environ if environment is None else environment
        provider = values.get("NPC_LLM_PROVIDER", "openai").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ModelConfigurationError(
                f"Unsupported NPC_LLM_PROVIDER '{provider}'. "
                "Supported providers: openai, deepseek"
            )
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
        provider_base_url = DEEPSEEK_BASE_URL if provider == "deepseek" else None
        base_url = explicit_base_url or provider_base_url
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
        return cls(provider, model, api_key, base_url, timeout, retries)

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
    provider_client = client
    if provider_client is None:
        provider_client = OpenAIChatClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            request_options=_request_options(settings.provider),
        )
    return LiveLLMAdapter(
        provider_client,
        provider=settings.provider,
        model=settings.model,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def _request_options(provider: str) -> dict[str, object]:
    if provider == "deepseek":
        # DeepSeek thinking mode requires reasoning_content round-tripping after
        # tool calls. v0.2.1 deliberately selects normal tool-calling mode
        # instead of adding provider-specific reasoning state to Agent history.
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}
