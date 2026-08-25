from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
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

    def __post_init__(self) -> None:
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
        object.__setattr__(self, "provider_retryable", retryable)


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
