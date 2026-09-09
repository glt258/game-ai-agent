from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping
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
    ProviderProfile,
    ProviderRoute,
    SUPPORTED_OPERATIONS,
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
    operation: str = "character_generation"
    route_source: str = "environment"

    @property
    def transport(self) -> TransportFamily:
        return self.profile.transport_family

    @property
    def route(self) -> ProviderRoute:
        return ProviderRoute(
            operation=self.operation,
            provider_id=self.provider,
            model_id=self.model,
            profile=self.profile,
            base_url=self.base_url,
            source=self.route_source,
        )

    def __repr__(self) -> str:
        return (
            "LiveLLMSettings("
            f"provider={self.provider!r}, model={self.model!r}, "
            "api_key='<redacted>', "
            f"base_url={self.base_url!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"max_retries={self.max_retries!r}, profile={self.profile!r}, "
            f"operation={self.operation!r})"
        )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        operation: str = "character_generation",
    ) -> "LiveLLMSettings":
        values = os.environ if environment is None else environment
        route = resolve_provider_route(operation, environment=values)
        provider = route.provider_id
        model = route.model_id
        api_key = values.get("NPC_LLM_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError(
                "Live model selected but NPC_LLM_API_KEY is not configured"
            )
        explicit_base_url = values.get("NPC_LLM_BASE_URL", "").strip() or None
        profile = route.profile
        structured_output_override = (
            values.get("NPC_LLM_STRUCTURED_OUTPUT", "").strip() or None
        )
        profile = apply_structured_output_override(
            profile,
            structured_output_override,
        )
        base_url = explicit_base_url or route.base_url
        if provider == "openai_compatible" and base_url is None:
            raise ModelConfigurationError(
                "NPC_LLM_BASE_URL is required for provider 'openai_compatible'"
            )
        _validate_base_url(base_url)
        timeout = cls._float(values, "NPC_LLM_TIMEOUT_SECONDS", 30.0)
        if not 1 <= timeout <= 300:
            raise ModelConfigurationError(
                "NPC_LLM_TIMEOUT_SECONDS must be from 1 to 300"
            )
        retries = cls._integer(values, "NPC_LLM_MAX_RETRIES", 2)
        if not 0 <= retries <= 3:
            raise ModelConfigurationError("NPC_LLM_MAX_RETRIES must be from 0 to 3")
        return cls(
            provider,
            model,
            api_key,
            base_url,
            timeout,
            retries,
            profile,
            operation,
            route.source,
        )

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


def _validate_base_url(base_url: str | None) -> None:
    if base_url is None:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelConfigurationError(
            "NPC_LLM_BASE_URL must be an absolute HTTP(S) URL"
        )
    if parsed.username or parsed.password:
        raise ModelConfigurationError("NPC_LLM_BASE_URL must not contain credentials")


def _route_pair(value: Any, *, operation: str, source: str) -> tuple[str, str]:
    if isinstance(value, ProviderRoute):
        if value.operation != operation:
            raise ModelConfigurationError(
                f"Provider route operation mismatch: expected '{operation}'"
            )
        return value.provider_id, value.model_id
    if isinstance(value, Mapping):
        provider = value.get("provider_id", value.get("provider"))
        model = value.get("model_id", value.get("model"))
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        provider, model = value
    else:
        raise ModelConfigurationError(
            f"{source} for operation '{operation}' must provide provider and model"
        )
    if not isinstance(provider, str) or not isinstance(model, str):
        raise ModelConfigurationError(
            f"{source} for operation '{operation}' must provide provider and model"
        )
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        raise ModelConfigurationError(
            f"{source} for operation '{operation}' must provide provider and model"
        )
    return provider, model


def resolve_provider_route(
    operation: str,
    *,
    environment: Mapping[str, str] | None = None,
    runtime_override: ProviderRoute | Mapping[str, str] | tuple[str, str] | None = None,
    operation_overrides: Mapping[str, ProviderRoute | Mapping[str, str] | tuple[str, str]]
    | None = None,
) -> ProviderRoute:
    """Resolve one trusted, secret-free route for a live operation."""

    operation = operation.strip()
    if operation not in SUPPORTED_OPERATIONS:
        raise ModelConfigurationError(
            f"Unsupported provider operation '{operation}'. Supported operations: "
            f"{', '.join(sorted(SUPPORTED_OPERATIONS))}"
        )
    values = os.environ if environment is None else environment
    source = "environment"
    if runtime_override is not None:
        provider, model = _route_pair(
            runtime_override, operation=operation, source="runtime_override"
        )
        source = "runtime_override"
    else:
        configured = operation_overrides.get(operation) if operation_overrides else None
        if configured is not None:
            provider, model = _route_pair(
                configured, operation=operation, source="operation_overrides"
            )
            source = "operation_override"
        else:
            prefix = f"NPC_LLM_{operation.upper()}_"
            op_provider = values.get(prefix + "PROVIDER", "").strip()
            op_model = values.get(prefix + "MODEL", "").strip()
            if bool(op_provider) != bool(op_model):
                raise ModelConfigurationError(
                    f"{prefix}PROVIDER and {prefix}MODEL must be configured together"
                )
            if op_provider and op_model:
                provider, model = op_provider.lower(), op_model
                source = "operation_override"
            else:
                provider = values.get("NPC_LLM_PROVIDER", "openai").strip().lower()
                model = values.get("NPC_LLM_MODEL", "").strip()
                if not model:
                    raise ModelConfigurationError(
                        "Live model selected but NPC_LLM_MODEL is not configured"
                    )
    transport_override = values.get("NPC_LLM_TRANSPORT", "").strip() or None
    profile = resolve_provider_profile(
        provider,
        model,
        transport_override=transport_override,
    )
    profile = apply_structured_output_override(
        profile,
        values.get("NPC_LLM_STRUCTURED_OUTPUT", "").strip() or None,
    )
    explicit_base_url = values.get("NPC_LLM_BASE_URL", "").strip() or None
    base_url = explicit_base_url or profile.default_base_url
    if provider == "openai_compatible" and base_url is None:
        raise ModelConfigurationError(
            "NPC_LLM_BASE_URL is required for provider 'openai_compatible'"
        )
    _validate_base_url(base_url)
    return ProviderRoute(
        operation=operation,
        provider_id=provider,
        model_id=model,
        profile=profile,
        base_url=base_url,
        source=source,
    )


def model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    mode_override: str | None = None,
    client: ProviderChatClient | None = None,
    operation: str = "character_generation",
    runtime_route: ProviderRoute | Mapping[str, str] | tuple[str, str] | None = None,
    operation_routes: Mapping[str, ProviderRoute | Mapping[str, str] | tuple[str, str]]
    | None = None,
) -> AgentModel:
    values = os.environ if environment is None else environment
    mode = (mode_override or values.get("NPC_AGENT_MODEL", "offline")).strip().lower()
    if mode == "offline":
        return DeterministicDemoModel()
    if mode != "live":
        raise ModelConfigurationError(
            f"Unsupported NPC_AGENT_MODEL '{mode}'. Supported modes: offline, live"
        )
    settings = LiveLLMSettings.from_environment(values, operation=operation)
    if runtime_route is not None or operation_routes:
        route = resolve_provider_route(
            operation,
            environment=values,
            runtime_override=runtime_route,
            operation_overrides=operation_routes,
        )
        settings = LiveLLMSettings(
            route.provider_id,
            route.model_id,
            settings.api_key,
            route.base_url,
            settings.timeout_seconds,
            settings.max_retries,
            route.profile,
            operation,
            route.source,
        )
    _ensure_transport_implemented(settings.profile)
    provider_client = client
    if provider_client is None:
        provider_client = OpenAIChatClient(
            api_key=settings.api_key,
            provider=settings.provider,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            request_options=settings.profile.provider_options,
        )
    return LiveLLMAdapter(
        provider_client,
        provider=settings.provider,
        model=settings.model,
        profile=settings.profile,
        route=settings.route,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def character_model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    mode_override: str | None = None,
    client: ProviderChatClient | None = None,
    operation: str = "character_generation",
    runtime_route: ProviderRoute | Mapping[str, str] | tuple[str, str] | None = None,
    operation_routes: Mapping[str, ProviderRoute | Mapping[str, str] | tuple[str, str]]
    | None = None,
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
    settings = LiveLLMSettings.from_environment(values, operation=operation)
    if runtime_route is not None or operation_routes:
        route = resolve_provider_route(
            operation,
            environment=values,
            runtime_override=runtime_route,
            operation_overrides=operation_routes,
        )
        settings = LiveLLMSettings(
            route.provider_id,
            route.model_id,
            settings.api_key,
            route.base_url,
            settings.timeout_seconds,
            settings.max_retries,
            route.profile,
            operation,
            route.source,
        )
    _ensure_transport_implemented(settings.profile)
    provider_client = client
    if provider_client is None:
        provider_client = OpenAIChatClient(
            api_key=settings.api_key,
            provider=settings.provider,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            request_options=settings.profile.provider_options,
        )
    return LiveLLMAdapter(
        provider_client,
        provider=settings.provider,
        model=settings.model,
        profile=settings.profile,
        route=settings.route,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def _ensure_transport_implemented(profile: ProviderProfile) -> None:
    if profile.transport_family is not TransportFamily.OPENAI_CHAT_COMPLETIONS:
        raise ModelCapabilityError(
            f"Transport '{profile.transport_family.value}' is recognized but not implemented"
        )
