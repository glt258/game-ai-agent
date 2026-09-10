from __future__ import annotations

import re
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from character_skill.errors import SkillKitShapeDiagnostic

_PROVIDER_METADATA_SECRET = re.compile(
    r"(?:authorization|bearer|api[_-]?key|secret|password|token)",
    re.IGNORECASE,
)


def safe_provider_metadata(value: Any, *, max_length: int = 128) -> str | None:
    """Keep only bounded, printable provider scalars at the audit boundary."""

    if not isinstance(value, str) or not value or len(value) > max_length:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    if _PROVIDER_METADATA_SECRET.search(value):
        return None
    return value


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

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                object.__setattr__(self, name, None)


@dataclass(frozen=True)
class ModelAttemptAudit:
    """Safe summary of one transport attempt within a logical invocation."""

    attempt_number: int
    outcome: str
    latency_ms: float | None = None
    error_code: str | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    usage: ModelUsage | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_request_id",
            safe_provider_metadata(self.provider_request_id),
        )


class ActionPhase(str, Enum):
    """Finite phases for the Character authoring action protocol."""

    INITIAL_CANON_REQUIRED = "INITIAL_CANON_REQUIRED"
    LATER_ACTION = "LATER_ACTION"
    FINALIZATION = "FINALIZATION"


class ActionTerminationReason(str, Enum):
    """Finite, content-free reasons for action-loop termination."""

    NO_TOOL_CALL_NON_FINALIZE = "NO_TOOL_CALL_NON_FINALIZE"
    EMPTY_COMPLETION = "EMPTY_COMPLETION"
    MALFORMED_TOOL_CALL = "MALFORMED_TOOL_CALL"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    ACTION_ROUNDS_EXHAUSTED = "ACTION_ROUNDS_EXHAUSTED"
    INVALID_FINALIZE = "INVALID_FINALIZE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ActionTerminationDiagnostic:
    """Bounded metadata for one failing action turn; never carries content."""

    action_phase: ActionPhase
    action_round_index: int
    request_tool_invocation: str
    outbound_tool_choice: str | None
    tools_present: bool
    tool_count: int
    structured_tool_call_count: int
    assistant_content_present: bool
    assistant_content_length: int
    finish_reason: str | None
    exact_finalize_match: bool
    action_termination_reason: ActionTerminationReason

    def __post_init__(self) -> None:
        if self.action_round_index < 0:
            raise ValueError("action_round_index must not be negative")
        if self.request_tool_invocation not in {"REQUIRED", "OPTIONAL", "DISABLED"}:
            raise ValueError("request_tool_invocation must be finite")
        if self.outbound_tool_choice not in {None, "required"}:
            raise ValueError("outbound_tool_choice must be required or absent")
        for name in ("tool_count", "structured_tool_call_count", "assistant_content_length"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_phase": self.action_phase.value,
            "action_round_index": self.action_round_index,
            "request_tool_invocation": self.request_tool_invocation,
            "outbound_tool_choice": self.outbound_tool_choice,
            "tools_present": self.tools_present,
            "tool_count": self.tool_count,
            "structured_tool_call_count": self.structured_tool_call_count,
            "assistant_content_present": self.assistant_content_present,
            "assistant_content_length": self.assistant_content_length,
            "finish_reason": self.finish_reason,
            "exact_finalize_match": self.exact_finalize_match,
            "action_termination_reason": self.action_termination_reason.value,
        }


def action_termination_reason_for_text(text: Any) -> ActionTerminationReason:
    if not isinstance(text, str) or not text.strip():
        return ActionTerminationReason.EMPTY_COMPLETION
    return (
        ActionTerminationReason.INVALID_FINALIZE
        if "FINALIZE" in text
        else ActionTerminationReason.NO_TOOL_CALL_NON_FINALIZE
    )


def build_action_termination_diagnostic(
    prompt: "AgentPrompt",
    *,
    reason: ActionTerminationReason,
    text: Any = None,
    tool_call_count: int = 0,
    finish_reason: Any = None,
    exact_finalize_match: bool | None = None,
) -> ActionTerminationDiagnostic:
    """Build bounded action metadata from a provider-neutral prompt/shape."""

    semantic = {
        "required": "REQUIRED",
        "optional": "OPTIONAL",
        "disabled": "DISABLED",
    }[prompt.tool_invocation]
    phase = {
        "required": ActionPhase.INITIAL_CANON_REQUIRED,
        "optional": ActionPhase.LATER_ACTION,
        "disabled": ActionPhase.FINALIZATION,
    }[prompt.tool_invocation]
    content_present = isinstance(text, str)
    normalized_finish_reason = (
        finish_reason
        if isinstance(finish_reason, str)
        and finish_reason in {"stop", "tool_calls", "length", "content_filter", "null"}
        else (None if finish_reason is None else "other")
    )
    safe_tool_call_count = (
        tool_call_count
        if isinstance(tool_call_count, int) and not isinstance(tool_call_count, bool) and tool_call_count >= 0
        else 0
    )
    return ActionTerminationDiagnostic(
        action_phase=phase,
        action_round_index=prompt.turn_number,
        request_tool_invocation=semantic,
        outbound_tool_choice="required" if prompt.tool_invocation == "required" else None,
        tools_present=bool(prompt.available_tools),
        tool_count=len(prompt.available_tools),
        structured_tool_call_count=safe_tool_call_count,
        assistant_content_present=content_present,
        assistant_content_length=min(len(text), 4096) if content_present else 0,
        finish_reason=normalized_finish_reason,
        exact_finalize_match=(
            text.strip() == "FINALIZE"
            if exact_finalize_match is None and isinstance(text, str)
            else bool(exact_finalize_match)
        ),
        action_termination_reason=reason,
    )


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
    transport: str | None = None
    response_contract: str | None = None
    # Sanitized failure detail only (schema-shape or normalized transport
    # messages). Must never contain raw model output, prompts, tool results,
    # restricted lore, or player input.
    error_message: str | None = None
    # Provider-neutral purpose marker.  Existing callers default to ordinary
    # generation; bounded structural recovery marks its own invocation.
    purpose: str = "generation"
    # Safe provider diagnostics only; values are sanitized at this audit seam.
    provider_status_code: int | None = None
    provider_retryable: bool | None = None
    # One logical invocation owns all provider attempts.  The tuple is an
    # allowlisted summary and never contains prompts, bodies, headers, or
    # model output.
    attempts: tuple[ModelAttemptAudit, ...] = ()
    upstream_status: int | None = None
    upstream_error_type: str | None = None
    upstream_error_code: str | None = None
    upstream_error_param: str | None = None

    def __post_init__(self) -> None:
        status_code = self.upstream_status
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            status_code = self.provider_status_code
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            status_code = None
        retryable = (
            self.provider_retryable
            if isinstance(self.provider_retryable, bool)
            else None
        )
        object.__setattr__(self, "provider_status_code", status_code)
        object.__setattr__(self, "upstream_status", status_code)
        object.__setattr__(self, "provider_retryable", retryable)
        for name in (
            "upstream_error_type",
            "upstream_error_code",
            "upstream_error_param",
            "provider_request_id",
        ):
            object.__setattr__(self, name, safe_provider_metadata(getattr(self, name)))
        object.__setattr__(self, "attempts", tuple(self.attempts))


@dataclass(frozen=True)
class ModelUsageSummary:
    invocation_count: int
    reported_usage_count: int
    known_input_tokens: int | None
    known_output_tokens: int | None
    known_total_tokens: int | None
    complete: bool


def summarize_model_usage(
    invocations: Sequence[ModelInvocationAudit],
) -> ModelUsageSummary:
    """Aggregate reported usage without turning unknown values into zero."""

    if not invocations:
        return ModelUsageSummary(0, 0, None, None, None, True)
    usage = [item.usage for item in invocations]
    totals = tuple(
        (sum(value for value in values if value is not None) if any(value is not None for value in values) else None)
        for values in zip(
            *(tuple(getattr(item, field_name) for field_name in ("input_tokens", "output_tokens", "total_tokens")) if item else (None, None, None) for item in usage),
            strict=False,
        )
    )
    complete = all(
        item is not None
        and item.input_tokens is not None
        and item.output_tokens is not None
        and item.total_tokens is not None
        for item in usage
    )
    return ModelUsageSummary(
        len(invocations),
        sum(item is not None for item in usage),
        totals[0],
        totals[1],
        totals[2],
        complete,
    )


@dataclass(frozen=True)
class SkillShadowConfig:
    """Explicit feature configuration for the optional SkillKit shadow call."""

    enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("SkillShadowConfig.enabled must be a boolean")


@dataclass(frozen=True)
class SkillShadowAudit:
    """Sanitized metadata for one independent SkillKit shadow invocation."""

    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    provider_request_id: str | None = None
    response_contract: str = "character_skill_kit"
    invocation_purpose: str = "character_skill_shadow"
    session_id: str | None = None
    turn_number: int | None = None
    outcome: str | None = None
    transport: str | None = None
    context_digest: str | None = None
    request_alignment_measured: bool = False
    reference_review_measured: bool = False

@dataclass(frozen=True)
class CharacterSkillShadowResult:
    """Independent, legacy-neutral result of a SkillKit shadow evaluation."""

    draft_id: str
    response_compliant: bool = False
    candidate: Any | None = None
    validation_report: Any | None = None
    audit: SkillShadowAudit = field(default_factory=SkillShadowAudit)
    failure_stage: str | None = None
    shape_diagnostic: SkillKitShapeDiagnostic | None = None
    error_message: str | None = None
    rendered_ability_concept: str | None = None
    legacy_ability_concept: str = ""
    ability_concept_diff: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.draft_id, str) or not self.draft_id:
            raise ValueError("draft_id must be a non-empty string")
        if not isinstance(self.response_compliant, bool):
            raise TypeError("response_compliant must be a boolean")
        if not isinstance(self.audit, SkillShadowAudit):
            raise TypeError("audit must be a SkillShadowAudit")
        if self.shape_diagnostic is not None and not isinstance(
            self.shape_diagnostic, SkillKitShapeDiagnostic
        ):
            raise TypeError("shape_diagnostic must be SkillKitShapeDiagnostic or None")
        object.__setattr__(
            self,
            "ability_concept_diff",
            MappingProxyType(dict(self.ability_concept_diff)),
        )

class SegmentKind(str, Enum):
    SUPPORTED_CLAIM = "supported_claim"
    UNCERTAIN = "uncertain"
    NON_FACTUAL = "non_factual"


class GroundingEvidenceType(str, Enum):
    CHARACTER_FACT = "character_fact"
    RUNTIME_FACT = "runtime_fact"
    TOOL_LORE = "tool_lore"


class ClaimGroundingStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"
    NON_FACTUAL = "non_factual"


@dataclass(frozen=True)
class GroundedResponseSegment:
    segment_id: str
    kind: SegmentKind
    text: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundingEvidence:
    evidence_id: str
    source_type: GroundingEvidenceType
    text: str
    source_lore_id: str | None = None


@dataclass(frozen=True)
class ClaimValidation:
    segment_id: str
    status: ClaimGroundingStatus
    valid_evidence_ids: tuple[str, ...] = ()
    invalid_evidence_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class GroundingReport:
    claims: tuple[ClaimValidation, ...]
    passed: bool
    source_lore_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundingRepairRequest:
    candidate_segments: tuple[GroundedResponseSegment, ...]
    rejected_segment_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CharacterDraftRecoveryAudit:
    """Audit metadata for structural CharacterDraft recovery.

    This is deliberately separate from Canon repair: it records shape
    completion/cleanup before a valid draft reaches CanonChecker.
    """

    status: str = "not_attempted"
    attempted: bool = False
    missing_required: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    recovered_fields: tuple[str, ...] = ()
    discarded_unknown_fields: tuple[str, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True)
class GroundingAudit:
    session_id: str
    turn_number: int
    candidate_claim_count: int
    supported_claim_count: int
    unsupported_claim_count: int
    uncertain_claim_count: int
    non_factual_count: int
    repair_attempted: bool
    repair_succeeded: bool
    fallback_used: bool


@dataclass(frozen=True)
class ModelTurn:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    source_lore_ids: tuple[str, ...] = ()
    segments: tuple[GroundedResponseSegment, ...] = ()
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    provider_request_id: str | None = None
    invocation: ModelInvocationAudit | None = None
    # Provider-neutral structured payloads used by authoring agents.  NPC
    # turns leave this unset and continue to use grounded response segments.
    structured_output: Any | None = None


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
    grounding_audit: list[GroundingAudit] = field(default_factory=list)

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
    evidence: tuple[GroundingEvidence, ...] = ()
    repair_request: GroundingRepairRequest | None = None
    # Kept optional so the existing NPC prompt contract remains unchanged.
    # Authoring consumers use ``character_authoring_action`` for tool
    # retrieval and ``character_draft`` for strict final JSON in the shared
    # LiveLLMAdapter.
    response_format: str = "grounded_response"
    # Bounded, provider-neutral payload for authoring operations that do not
    # use the NPC conversation message history (for example character repair).
    # It is serialized as data by the live adapter, never interpolated into
    # the system contract.
    authoring_payload: Mapping[str, Any] | None = None
    # Allows provider-neutral audit consumers to distinguish a bounded
    # structural recovery invocation from ordinary generation.
    invocation_purpose: str = "generation"
    # Provider-neutral action intent.  ``optional`` preserves provider auto
    # selection; only semantically action-required turns map to ``required``.
    tool_invocation: str = "optional"

    def __post_init__(self) -> None:
        if self.tool_invocation not in {"required", "optional", "disabled"}:
            raise ValueError(
                "tool_invocation must be required, optional, or disabled"
            )


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
    grounding: GroundingAudit | None = None


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
