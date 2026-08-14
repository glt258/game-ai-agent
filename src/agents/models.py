from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.name or not self.description:
            raise ValueError("ToolDefinition name and description must be non-empty")
        object.__setattr__(
            self, "input_schema", MappingProxyType(deepcopy(dict(self.input_schema)))
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("ToolCall id and name must be non-empty")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelInvocationAudit:
    session_id: str
    turn_number: int
    provider: str
    model: str
    outcome: str
    latency_ms: float
    retry_count: int
    finish_reason: str | None = None
    tool_call_count: int = 0
    usage: ModelUsage | None = None
    provider_request_id: str | None = None


@dataclass(frozen=True)
class ModelTurn:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    source_lore_ids: tuple[str, ...] = ()
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    provider_request_id: str | None = None
    invocation: ModelInvocationAudit | None = None


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: Any

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported conversation role: {self.role}")


@dataclass
class ConversationSession:
    session_id: str
    character_id: str
    story_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    turn_count: int = 0
    audit: list["ToolAuditEntry"] = field(default_factory=list)
    model_audit: list[ModelInvocationAudit] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id or not self.character_id or not self.story_id:
            raise ValueError("Session IDs must be non-empty")


@dataclass(frozen=True)
class NpcCharacterView:
    character_id: str
    display_name: str
    occupation: str
    surface_traits: tuple[str, ...]
    values: tuple[str, ...]
    knowledge_style: str
    speech_style: str
    communication_habits: tuple[str, ...]
    default_information_behavior: str
    public_address: str


@dataclass(frozen=True)
class NpcRuntimeView:
    story_id: str
    story_title: str
    participation_role: str | None
    active_case_ids: tuple[str, ...]
    active_incident_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentPrompt:
    system_contract: str
    character: NpcCharacterView
    runtime: NpcRuntimeView
    messages: tuple[ConversationMessage, ...]
    available_tools: tuple[ToolDefinition, ...]
    session_id: str
    turn_number: int


@dataclass(frozen=True)
class ToolAuditEntry:
    round: int
    tool_name: str
    arguments: Mapping[str, Any]
    result_status: str
    allowed_lore_ids: tuple[str, ...] = ()
    denied_requested_ids: tuple[str, ...] = ()
    resolver_reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class NpcResponse:
    text: str
    source_lore_ids: tuple[str, ...]
    tool_calls: tuple[ToolAuditEntry, ...]
    access_denials: tuple[str, ...]
    character_view: NpcCharacterView
    runtime_view: NpcRuntimeView
    model_invocations: tuple[ModelInvocationAudit, ...] = ()


@dataclass(frozen=True)
class LoreFact:
    lore_id: str
    title: str
    statement: str
    category: str | None

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "lore_id": self.lore_id,
            "title": self.title,
            "statement": self.statement,
            "category": self.category,
        }
