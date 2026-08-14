from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from .models import ModelUsage


ProviderErrorKind = Literal[
    "authentication",
    "timeout",
    "rate_limit",
    "provider",
]


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
    ) -> ProviderCompletion: ...
