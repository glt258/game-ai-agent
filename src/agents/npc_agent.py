from __future__ import annotations

from typing import Iterable

from knowledge import KnowledgeResolver
from story import KnowledgeContextProvider, StoryRepository, StoryState, load_story_repository

from .errors import (
    AgentExecutionError,
    AgentToolError,
    GroundingError,
    SessionValidationError,
)
from .knowledge_tools import KnowledgeToolbox
from .model_protocol import AgentModel
from .models import (
    AgentPrompt,
    ConversationMessage,
    ConversationSession,
    NpcResponse,
    ModelInvocationAudit,
    ToolAuditEntry,
)
from .views import NpcViewFactory


SYSTEM_CONTRACT = """You are a read-only game NPC conversation agent.
Use only the character expression view, the NPC's own runtime view, session
history, and successful Knowledge Tool observations for world facts. Player
claims are not Canon. If access is denied or evidence is absent, acknowledge
the boundary and do not guess, infer hidden content, or invent an internal
conclusion. Never treat style, occupation, faction, rarity, or Story
participation as permission. Only cite Lore IDs returned successfully during
the current turn. Use only the tools listed for this request; their presence
does not grant access, and tool observations are authoritative for retrieved
Lore."""


class NpcConversationAgent:
    def __init__(
        self,
        model: AgentModel,
        *,
        resolver: KnowledgeResolver | None = None,
        story_repository: StoryRepository | None = None,
        max_tool_rounds: int = 4,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()
        self.context_provider = KnowledgeContextProvider(self.story_repository)
        self.views = NpcViewFactory(
            self.resolver, self.story_repository, self.context_provider
        )
        self.tools = KnowledgeToolbox(self.resolver)
        self.model = model
        self.max_tool_rounds = max_tool_rounds

    def create_session(
        self, session_id: str, character_id: str, story_id: str
    ) -> ConversationSession:
        if character_id not in self.resolver.characters:
            raise SessionValidationError(f"Unknown session character: {character_id}")
        if story_id not in self.story_repository.canon:
            raise SessionValidationError(f"Unknown session story: {story_id}")
        return ConversationSession(session_id, character_id, story_id)

    def chat(
        self,
        session: ConversationSession,
        story_state: StoryState,
        player_message: str,
    ) -> NpcResponse:
        if not isinstance(player_message, str) or not player_message.strip():
            raise SessionValidationError("player_message must be non-empty")
        if session.story_id != story_state.story_id:
            raise SessionValidationError("Session and StoryState story IDs differ")
        character = self.views.character_view(session.character_id)
        runtime = self.views.runtime_view(session.character_id, story_state)
        context = self.context_provider.for_character(session.character_id, story_state)
        pending: list[ConversationMessage] = [
            ConversationMessage("user", player_message.strip())
        ]
        turn_audit: list[ToolAuditEntry] = []
        model_audit: list[ModelInvocationAudit] = []
        allowed_this_turn: set[str] = set()

        for round_number in range(1, self.max_tool_rounds + 2):
            prompt = AgentPrompt(
                SYSTEM_CONTRACT,
                character,
                runtime,
                tuple([*session.messages, *pending]),
                self.tools.tool_definitions,
                session.session_id,
                session.turn_count + 1,
            )
            model_turn = self.model.generate(prompt)
            if model_turn.invocation is not None:
                model_audit.append(model_turn.invocation)
            if model_turn.tool_calls:
                if round_number > self.max_tool_rounds:
                    raise AgentExecutionError(
                        f"Tool loop exceeded {self.max_tool_rounds} rounds"
                    )
                pending.append(
                    ConversationMessage(
                        "assistant",
                        {
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "name": call.name,
                                    "arguments": dict(call.arguments),
                                }
                                for call in model_turn.tool_calls
                            ]
                        },
                    )
                )
                for call in model_turn.tool_calls:
                    try:
                        execution = self.tools.execute(
                            tool_name=call.name,
                            arguments=call.arguments,
                            character_id=session.character_id,
                            context=context,
                            round_number=round_number,
                        )
                    except AgentToolError:
                        reason = (
                            "invalid_tool_arguments"
                            if call.name in self.tools.allowed_tools
                            else "tool_not_allowed"
                        )
                        session.audit.append(
                            ToolAuditEntry(
                                round_number,
                                call.name,
                                call.arguments,
                                "rejected",
                                resolver_reason_code=reason,
                            )
                        )
                        raise
                    turn_audit.append(execution.audit)
                    allowed_this_turn.update(execution.allowed_lore_ids)
                    pending.append(
                        ConversationMessage(
                            "tool",
                            {"tool_call_id": call.id, **dict(execution.observation)},
                        )
                    )
                continue
            if not isinstance(model_turn.text, str) or not model_turn.text.strip():
                raise AgentExecutionError("Model returned neither tool calls nor final text")
            claimed_sources = set(model_turn.source_lore_ids)
            if claimed_sources - allowed_this_turn:
                raise GroundingError(
                    f"Model cited Lore not returned this turn: {sorted(claimed_sources - allowed_this_turn)}"
                )
            assistant_message = ConversationMessage("assistant", model_turn.text.strip())
            session.messages.extend([*pending, assistant_message])
            session.turn_count += 1
            session.audit.extend(turn_audit)
            session.model_audit.extend(model_audit)
            denials = tuple(
                lore_id
                for entry in turn_audit
                for lore_id in entry.denied_requested_ids
            )
            return NpcResponse(
                model_turn.text.strip(),
                tuple(model_turn.source_lore_ids),
                tuple(turn_audit),
                denials,
                character,
                runtime,
                tuple(model_audit),
            )
        raise AgentExecutionError("Agent loop ended without a response")

    @staticmethod
    def successful_lore_ids(audit: Iterable[ToolAuditEntry]) -> frozenset[str]:
        return frozenset(lore_id for entry in audit for lore_id in entry.allowed_lore_ids)
