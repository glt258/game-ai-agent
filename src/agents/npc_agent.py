from __future__ import annotations

import logging
from typing import Iterable

from knowledge import KnowledgeResolver
from story import KnowledgeContextProvider, StoryRepository, StoryState, load_story_repository

from .errors import (
    AgentExecutionError,
    AgentToolError,
    GroundingError,
    ModelError,
    SessionValidationError,
)
from .grounding import GroundingEvidenceBuilder, GroundingValidator, safe_fallback_segments
from .knowledge_tools import KnowledgeToolbox
from .model_protocol import AgentModel
from .models import (
    AgentPrompt,
    ClaimGroundingStatus,
    ConversationMessage,
    ConversationSession,
    GroundingAudit,
    GroundingEvidence,
    GroundingRepairRequest,
    GroundingReport,
    GroundedResponseSegment,
    NpcResponse,
    NpcCharacterView,
    NpcRuntimeView,
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

LOGGER = logging.getLogger(__name__)


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
        self.evidence_builder = GroundingEvidenceBuilder()
        self.grounding_validator = GroundingValidator()

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
            evidence = self.evidence_builder.build(character, runtime, pending)
            prompt = AgentPrompt(
                SYSTEM_CONTRACT,
                character,
                runtime,
                tuple([*session.messages, *pending]),
                self.tools.tool_definitions,
                session.session_id,
                session.turn_count + 1,
                evidence,
            )
            try:
                model_turn = self.model.generate(prompt)
            except ModelError as error:
                self._append_failure_audit(session.model_audit, error)
                raise
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
            claimed_sources = set(model_turn.source_lore_ids)
            if claimed_sources - allowed_this_turn:
                raise GroundingError(
                    f"Model cited Lore not returned this turn: {sorted(claimed_sources - allowed_this_turn)}"
                )
            if not model_turn.segments:
                raise AgentExecutionError(
                    "Model returned no grounded response segments"
                )
            candidate_report = self.grounding_validator.validate(
                model_turn.segments, evidence
            )
            final_segments = model_turn.segments
            final_report = candidate_report
            repair_attempted = False
            repair_succeeded = False
            fallback_used = False
            if not candidate_report.passed:
                repair_attempted = True
                repaired = self._repair_once(
                    session=session,
                    character=character,
                    runtime=runtime,
                    evidence=evidence,
                    candidate=model_turn.segments,
                    report=candidate_report,
                    allowed_this_turn=allowed_this_turn,
                    model_audit=model_audit,
                )
                if repaired is not None:
                    final_segments, final_report = repaired
                    repair_succeeded = True
                else:
                    final_segments = safe_fallback_segments()
                    final_report = self.grounding_validator.validate(
                        final_segments, evidence
                    )
                    fallback_used = True
            final_text = self.grounding_validator.render(final_segments)
            if not final_report.passed or not final_text:
                raise AgentExecutionError("Grounded response pipeline failed closed")
            grounding_audit = self._grounding_audit(
                session,
                candidate_report,
                repair_attempted=repair_attempted,
                repair_succeeded=repair_succeeded,
                fallback_used=fallback_used,
            )
            assistant_message = ConversationMessage("assistant", final_text)
            session.messages.extend([*pending, assistant_message])
            session.turn_count += 1
            session.audit.extend(turn_audit)
            session.model_audit.extend(model_audit)
            session.grounding_audit.append(grounding_audit)
            denials = tuple(
                lore_id
                for entry in turn_audit
                for lore_id in entry.denied_requested_ids
            )
            return NpcResponse(
                final_text,
                final_report.source_lore_ids,
                tuple(turn_audit),
                denials,
                character,
                runtime,
                tuple(model_audit),
                grounding_audit,
            )
        raise AgentExecutionError("Agent loop ended without a response")

    @staticmethod
    def successful_lore_ids(audit: Iterable[ToolAuditEntry]) -> frozenset[str]:
        return frozenset(lore_id for entry in audit for lore_id in entry.allowed_lore_ids)

    @staticmethod
    def _append_failure_audit(
        target: list[ModelInvocationAudit], error: ModelError
    ) -> None:
        """Record sanitized metadata for a failed model call.

        Appends only the failure audit attached by the adapter; never commits
        model output or session content. Callers either re-raise (candidate
        path) or continue to fallback (repair path).
        """
        if error.audit is not None:
            target.append(error.audit)

    def _repair_once(
        self,
        *,
        session: ConversationSession,
        character: NpcCharacterView,
        runtime: NpcRuntimeView,
        evidence: tuple[GroundingEvidence, ...],
        candidate: tuple[GroundedResponseSegment, ...],
        report: GroundingReport,
        allowed_this_turn: set[str],
        model_audit: list[ModelInvocationAudit],
    ) -> tuple[tuple[GroundedResponseSegment, ...], GroundingReport] | None:
        rejected = tuple(
            claim.segment_id
            for claim in report.claims
            if claim.status == ClaimGroundingStatus.UNSUPPORTED
        )
        repair_prompt = AgentPrompt(
            SYSTEM_CONTRACT,
            character,
            runtime,
            (),
            (),
            session.session_id,
            session.turn_count + 1,
            tuple(evidence),
            GroundingRepairRequest(
                candidate,
                rejected,
                tuple("no available supporting evidence" for _ in rejected),
            ),
        )
        try:
            repair_turn = self.model.generate(repair_prompt)
        except ModelError as error:
            # Record the failed repair call into the turn-local audit list so
            # it is committed with the candidate success audit when the turn
            # completes via fallback (order preserved: candidate, then repair).
            self._append_failure_audit(model_audit, error)
            return None
        if repair_turn.invocation is not None:
            model_audit.append(repair_turn.invocation)
        if repair_turn.tool_calls or not repair_turn.segments:
            return None
        if set(repair_turn.source_lore_ids) - allowed_this_turn:
            return None
        repaired_report = self.grounding_validator.validate(
            repair_turn.segments, evidence
        )
        if not repaired_report.passed:
            return None
        return repair_turn.segments, repaired_report

    @staticmethod
    def _grounding_audit(
        session: ConversationSession,
        report: GroundingReport,
        *,
        repair_attempted: bool,
        repair_succeeded: bool,
        fallback_used: bool,
    ) -> GroundingAudit:
        counts = {
            status: sum(claim.status == status for claim in report.claims)
            for status in ClaimGroundingStatus
        }
        audit = GroundingAudit(
            session.session_id,
            session.turn_count + 1,
            len(report.claims),
            counts[ClaimGroundingStatus.SUPPORTED],
            counts[ClaimGroundingStatus.UNSUPPORTED],
            counts[ClaimGroundingStatus.UNCERTAIN],
            counts[ClaimGroundingStatus.NON_FACTUAL],
            repair_attempted,
            repair_succeeded,
            fallback_used,
        )
        LOGGER.info(
            "grounding_validation session_id=%s turn=%d claims=%d supported=%d "
            "unsupported=%d uncertain=%d non_factual=%d repair_attempted=%s "
            "repair_succeeded=%s fallback_used=%s",
            audit.session_id,
            audit.turn_number,
            audit.candidate_claim_count,
            audit.supported_claim_count,
            audit.unsupported_claim_count,
            audit.uncertain_claim_count,
            audit.non_factual_count,
            audit.repair_attempted,
            audit.repair_succeeded,
            audit.fallback_used,
        )
        return audit
