from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .errors import ModelConfigurationError


OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class TransportFamily(str, Enum):
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"

    @classmethod
    def from_config(cls, value: str) -> "TransportFamily":
        normalized = value.strip().lower()
        aliases = {
            "chat_completions": cls.OPENAI_CHAT_COMPLETIONS,
            "openai_chat_completions": cls.OPENAI_CHAT_COMPLETIONS,
            "responses": cls.OPENAI_RESPONSES,
            "openai_responses": cls.OPENAI_RESPONSES,
            "messages": cls.ANTHROPIC_MESSAGES,
            "anthropic_messages": cls.ANTHROPIC_MESSAGES,
        }
        try:
            return aliases[normalized]
        except KeyError:
            supported = ", ".join(sorted(aliases))
            raise ModelConfigurationError(
                f"Unsupported NPC_LLM_TRANSPORT '{value}'. Supported values: {supported}"
            ) from None


class ThinkingModeBehavior(str, Enum):
    PROVIDER_DEFAULT = "provider_default"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_tools: bool
    supports_json_schema: bool
    supports_json_object: bool
    supports_parallel_tool_calls: bool
    thinking_mode_behavior: ThinkingModeBehavior = (
        ThinkingModeBehavior.PROVIDER_DEFAULT
    )

    @property
    def supports_structured_output(self) -> bool:
        return self.supports_json_schema or self.supports_json_object


@dataclass(frozen=True)
class ProviderProfile:
    logical_provider: str
    default_base_url: str | None
    transport_family: TransportFamily
    capabilities: ProviderCapabilities
    provider_options: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_options",
            MappingProxyType(deepcopy(dict(self.provider_options))),
        )


CHAT_JSON_OBJECT_CAPABILITIES = ProviderCapabilities(
    supports_tools=True,
    supports_json_schema=False,
    supports_json_object=True,
    supports_parallel_tool_calls=False,
)

CHAT_TOOLS_ONLY_CAPABILITIES = ProviderCapabilities(
    supports_tools=True,
    supports_json_schema=False,
    supports_json_object=False,
    supports_parallel_tool_calls=False,
)

OPENAI_CAPABILITIES = ProviderCapabilities(
    # The direct profile remains model-agnostic. It uses conservative JSON
    # object mode rather than assuming every configured OpenAI model supports
    # strict Structured Outputs.
    supports_tools=True,
    supports_json_schema=False,
    supports_json_object=True,
    supports_parallel_tool_calls=True,
)

DEEPSEEK_CAPABILITIES = replace(
    CHAT_JSON_OBJECT_CAPABILITIES,
    thinking_mode_behavior=ThinkingModeBehavior.DISABLED,
)


PROVIDER_PROFILES: Mapping[str, ProviderProfile] = MappingProxyType(
    {
        "openai": ProviderProfile(
            "openai",
            None,
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
            OPENAI_CAPABILITIES,
            {},
        ),
        "deepseek": ProviderProfile(
            "deepseek",
            DEEPSEEK_BASE_URL,
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
            DEEPSEEK_CAPABILITIES,
            {"extra_body": {"thinking": {"type": "disabled"}}},
        ),
        "openai_compatible": ProviderProfile(
            "openai_compatible",
            None,
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
            CHAT_JSON_OBJECT_CAPABILITIES,
            {},
        ),
    }
)


# Compatibility profiles, not a permanent catalogue of everything available
# from OpenCode Go. Models with the same verified Chat Completions contract all
# share the same transport implementation and capability object.
def _opencode_go_profile(
    transport: TransportFamily,
    capabilities: ProviderCapabilities = CHAT_TOOLS_ONLY_CAPABILITIES,
) -> ProviderProfile:
    return ProviderProfile(
        "opencode_go",
        OPENCODE_GO_BASE_URL,
        transport,
        capabilities,
        {},
    )


KNOWN_OPENCODE_GO_MODEL_PROFILES: Mapping[str, ProviderProfile] = MappingProxyType(
    {
        **{
            model: _opencode_go_profile(
                TransportFamily.OPENAI_CHAT_COMPLETIONS
            )
            for model in (
                "glm-5.3",
                "glm-5.2",
                "glm-5.1",
                "kimi-k3",
                "kimi-k2.7-code",
                "kimi-k2.6",
                "mimo-v2.5",
                "mimo-v2.5-pro",
                "hy3",
            )
        },
        "deepseek-v4-pro": _opencode_go_profile(
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
            CHAT_JSON_OBJECT_CAPABILITIES,
        ),
        "deepseek-v4-flash": _opencode_go_profile(
            TransportFamily.OPENAI_CHAT_COMPLETIONS,
            CHAT_JSON_OBJECT_CAPABILITIES,
        ),
        **{
            model: _opencode_go_profile(TransportFamily.OPENAI_RESPONSES)
            for model in ("grok-4.5", "gpt-5.6-luna")
        },
        **{
            model: _opencode_go_profile(TransportFamily.ANTHROPIC_MESSAGES)
            for model in (
                "minimax-m3",
                "minimax-m2.7",
                "minimax-m2.5",
                "qwen3.8-max",
                "qwen3.7-max",
                "qwen3.7-plus",
                "qwen3.6-plus",
            )
        },
    }
)

SUPPORTED_PROVIDERS = frozenset((*PROVIDER_PROFILES, "opencode_go"))


def resolve_provider_profile(
    logical_provider: str,
    model: str,
    *,
    transport_override: str | None = None,
) -> ProviderProfile:
    provider = logical_provider.strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ModelConfigurationError(
            f"Unsupported NPC_LLM_PROVIDER '{provider}'. Supported providers: {supported}"
        )

    explicit_transport = (
        TransportFamily.from_config(transport_override)
        if transport_override is not None
        else None
    )
    if provider == "opencode_go":
        known = KNOWN_OPENCODE_GO_MODEL_PROFILES.get(model)
        if known is None and explicit_transport is None:
            raise ModelConfigurationError(
                f"Unknown OpenCode Go model '{model}'. Set NPC_LLM_TRANSPORT "
                "explicitly or add a verified model compatibility profile."
            )
        profile = known or ProviderProfile(
            "opencode_go",
            OPENCODE_GO_BASE_URL,
            explicit_transport or TransportFamily.OPENAI_CHAT_COMPLETIONS,
            CHAT_JSON_OBJECT_CAPABILITIES,
            {},
        )
    else:
        profile = PROVIDER_PROFILES[provider]

    if explicit_transport is not None:
        profile = replace(profile, transport_family=explicit_transport)
    return profile


def apply_structured_output_override(
    profile: ProviderProfile,
    value: str | None,
) -> ProviderProfile:
    if value is None:
        return profile
    normalized = value.strip().lower()
    if normalized == "json_schema":
        capabilities = replace(
            profile.capabilities,
            supports_json_schema=True,
            supports_json_object=True,
        )
    elif normalized == "json_object":
        capabilities = replace(
            profile.capabilities,
            supports_json_schema=False,
            supports_json_object=True,
        )
    elif normalized == "none":
        capabilities = replace(
            profile.capabilities,
            supports_json_schema=False,
            supports_json_object=False,
        )
    else:
        raise ModelConfigurationError(
            f"Unsupported NPC_LLM_STRUCTURED_OUTPUT '{value}'. "
            "Supported values: json_schema, json_object, none"
        )
    return replace(profile, capabilities=capabilities)


__all__ = [
    "CHAT_JSON_OBJECT_CAPABILITIES",
    "CHAT_TOOLS_ONLY_CAPABILITIES",
    "DEEPSEEK_BASE_URL",
    "KNOWN_OPENCODE_GO_MODEL_PROFILES",
    "OPENCODE_GO_BASE_URL",
    "PROVIDER_PROFILES",
    "ProviderCapabilities",
    "ProviderProfile",
    "SUPPORTED_PROVIDERS",
    "ThinkingModeBehavior",
    "TransportFamily",
    "resolve_provider_profile",
    "apply_structured_output_override",
]
