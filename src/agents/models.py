from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


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
class ModelTurn:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    source_lore_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: Any

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant", "tool"}:
            raise ValueError(f"Unsupported conversation role: {self.role}")


@dataclass
class ConversationSession:
    session_id: str
    character_id: str
    story_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    turn_count: int = 0
    audit: list["ToolAuditEntry"] = field(default_factory=list)

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
    available_tools: tuple[str, ...]


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
