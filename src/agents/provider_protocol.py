from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Mapping, Protocol, Sequence

from .errors import ModelCapabilityError
from .models import ModelUsage
from .provider_profiles import ProviderCapabilities
from .response_contracts import ResponseContract


ProviderErrorKind = Literal[
    "authentication",
    "timeout",
    "rate_limit",
    "provider",
]

class ResponseMode(str, Enum):
    TEXT = "text"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class NegotiatedResponseContract(dict[str, Any]):
    """Capability-negotiated contract consumed by a transport adapter."""

    def __init__(
        self,
        name: str,
        mode: ResponseMode,
        json_schema: Mapping[str, Any] | None = None,
    ) -> None:
        schema = deepcopy(dict(json_schema)) if json_schema is not None else None
        super().__init__(name=name, mode=mode.value, json_schema=schema)
        self.name = name
        self.mode = mode
        self.json_schema = schema


TEXT_NEGOTIATED_RESPONSE = NegotiatedResponseContract("text", ResponseMode.TEXT)


def negotiate_response_contract(
    requested: ResponseContract,
    capabilities: ProviderCapabilities,
) -> NegotiatedResponseContract:
    if not requested.strict:
        return NegotiatedResponseContract(requested.name, ResponseMode.TEXT)
    if requested.json_schema is not None and capabilities.supports_json_schema:
        return NegotiatedResponseContract(
            requested.name,
            ResponseMode.JSON_SCHEMA,
            requested.json_schema,
        )
    if capabilities.supports_json_object:
        return NegotiatedResponseContract(requested.name, ResponseMode.JSON_OBJECT)
    raise ModelCapabilityError(
        f"Provider profile cannot satisfy strict '{requested.name}' structured output: "
        "neither JSON Schema nor JSON Object mode is supported"
    )


class ProviderClientError(Exception):
    """Sanitized failure emitted by a provider client implementation."""

    def __init__(
        self,
        kind: ProviderErrorKind,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(f"Provider request failed ({kind})")
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderToolCall:
    id: str | None
    name: str | None
    arguments: Any


@dataclass(frozen=True)
class ProviderCompletion:
    text: str | None = None
    tool_calls: tuple[ProviderToolCall, ...] = ()
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    request_id: str | None = None


class ProviderChatClient(Protocol):
    """Small provider boundary used by LiveLLMAdapter and fake clients."""

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
        response_contract: NegotiatedResponseContract = TEXT_NEGOTIATED_RESPONSE,
    ) -> ProviderCompletion: ...
