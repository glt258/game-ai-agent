"""Thin V2 character realization over the shared model and B1C boundaries.

This module accepts only B1B's frozen finalization input. It performs no
planning, retrieval, action/tool loop, Canon checking, or application routing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from agents.errors import ModelError, ModelMalformedResponseError
from agents.model_protocol import AgentModel
from agents.models import (
    AgentPrompt,
    ModelInvocationAudit,
    ModelTurn,
    NpcCharacterView,
    NpcRuntimeView,
)

from .character_draft import CharacterDraft
from .draft_output import (
    MAX_STRUCTURAL_RECOVERY_ATTEMPTS,
    CharacterDraftOutputAudit,
    CharacterDraftOutputFailureReason,
    CharacterDraftOutputStatus,
    CharacterDraftRecoveryInputV1,
    CharacterDraftStructureInspection,
    inspect_character_draft_output,
    merge_character_draft_recovery,
)
from .finalization_input import CharacterFinalizationInputV1
from .intent import ExplicitAgeRequirement, ExplicitGenderRequirement
from .naming_design import is_occupation_as_name

CHARACTER_GENERATION_V2_SYSTEM_CONTRACT = """Realize the frozen character-generation semantics in the provided B1B finalization input.

The input is the sole semantic authority. Do not reinterpret a raw request,
re-plan, search, retrieve, call tools, or add facts from outside its bounded
evidence and reference context. Preserve the resolved direction and required
generation fields exactly. When naming_design contains selected_name, copy
that exact player-facing display name to CharacterDraft.name. The selected
name is frozen Planner- or user-owned input; do not translate, transliterate,
expand, or substitute another name form or an occupation/title.

For field authorization, create new semantic content only when the field is
NEW_DESIGN_AUTHORIZED. For CANON_GROUNDED_ONLY fields, choose only an
authorized exact value; do not paraphrase or invent one. Do not create new
semantic content for UNAUTHORIZED fields.

Honor any explicit gender requirement in spec.hard_requirements exactly:
match its requested value, preserve an explicitly unspecified gender as null
or the existing unspecified value, and avoid any explicitly forbidden value.
When no explicit gender requirement is present, do not infer gender from a
name, appearance, clothing, or occupation; retain the existing creative freedom.

Honor spec.age_requirement within its exact minimum_age and maximum_age bounds.
When requested_affiliation_id is present, set faction_id to that exact Canon
faction ID; do not substitute a different organization or invent an affiliation.

Record authorship in the existing new_design_elements array. For each
non-empty narrative field that contains newly authored content and is
NEW_DESIGN_AUTHORIZED, include the standalone declaration string
new_design:<field>: (for example, new_design:background:). Add no declaration
for empty fields or fields whose content is entirely an authorized exact
CANON_GROUNDED_ONLY value. Never declare UNAUTHORIZED fields. A declaration
classifies authorship; it does not grant field authorization or bypass Canon
consistency checks. Keep Canon-grounded claims tied to their real field-specific
B1B authority. Never invent Canon source IDs or generic canon_basis entries.

B1B evidence is field-specific, system-owned authority; it does not populate
generic canon_basis. Return canon_basis as an empty array. The system independently
validates exact CANON_GROUNDED_ONLY values from B1B. Do not copy that evidence
into generic basis entries or use it to support another field.

Return only the root JSON object required by the shared CharacterDraft output
contract. Do not add an envelope, commentary, or markdown."""


CHARACTER_DRAFT_RECOVERY_SYSTEM_CONTRACT = """Complete one structural recovery for the provided B1C recovery input.

Return ONLY the explicitly requested fields listed in missing_fields. Do not
rewrite any field in original_partial_draft and do not add extra fields. Use
only the same frozen finalization authority: CANON_GROUNDED_ONLY fields must
use an authorized exact value, and UNAUTHORIZED fields must not be invented.
If canon_basis is among missing_fields, return it as an empty array. Do not
copy field-specific B1B evidence into generic basis entries. If name is among
missing_fields and naming_design contains selected_name, use that exact name.
Honor any explicit gender requirement in spec.hard_requirements for gender
fields being recovered; do not infer gender when no such requirement exists.
Do not reinterpret a raw request, re-plan, search, retrieve, or call tools.

Return only a root JSON object containing the requested missing fields."""


class CharacterGenerationV2Status(str, Enum):
    """Finite outcomes from one V2 generation orchestration."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CharacterGenerationV2FailureReason(str, Enum):
    """Content-free failures that callers may handle without parsing errors."""

    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    STRUCTURED_OUTPUT_FAILURE = "STRUCTURED_OUTPUT_FAILURE"
    DRAFT_STRUCTURE_FAILURE = "DRAFT_STRUCTURE_FAILURE"
    STRUCTURAL_RECOVERY_FAILURE = "STRUCTURAL_RECOVERY_FAILURE"
    RECOVERY_PROVIDER_FAILURE = "RECOVERY_PROVIDER_FAILURE"
    FIELD_AUTHORIZATION_VIOLATION = "FIELD_AUTHORIZATION_VIOLATION"
    NAMING_VALIDATION_FAILURE = "NAMING_VALIDATION_FAILURE"
    HARD_REQUIREMENT_VIOLATION = "HARD_REQUIREMENT_VIOLATION"


@dataclass(frozen=True)
class CharacterGenerationV2Audit:
    """Bounded lineage, logical-call accounting, and sanitized runtime audits."""

    request_id: str
    spec_id: str
    spec_digest: str
    initial_call_count: int
    recovery_call_count: int
    model_invocations: tuple[ModelInvocationAudit, ...] = ()
    draft_output_audit: CharacterDraftOutputAudit | None = None
    draft_output_inspection: CharacterDraftStructureInspection | None = None
    naming_enforcement: str = "NOT_APPLICABLE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_invocations", tuple(self.model_invocations))
        if self.initial_call_count not in (0, 1):
            raise ValueError("V2 permits at most one initial logical model call")
        if not 0 <= self.recovery_call_count <= MAX_STRUCTURAL_RECOVERY_ATTEMPTS:
            raise ValueError("V2 recovery calls exceed the shared B1C recovery limit")
        if self.recovery_call_count and self.initial_call_count != 1:
            raise ValueError("a recovery call requires one initial logical call")
        if self.logical_call_count > 2 or len(self.model_invocations) > 2:
            raise ValueError("V2 generation audit exceeds its two-call bound")

    @property
    def logical_call_count(self) -> int:
        """Count semantic invocations, not provider transport attempts."""

        return self.initial_call_count + self.recovery_call_count

    @property
    def recovery_used(self) -> bool:
        """Report whether the single structural recovery invocation ran."""

        return self.recovery_call_count == 1


@dataclass(frozen=True)
class CharacterGenerationV2Result:
    """One completed shared CharacterDraft or one finite terminal failure."""

    status: CharacterGenerationV2Status
    audit: CharacterGenerationV2Audit
    draft: CharacterDraft | None = None
    failure_reason: CharacterGenerationV2FailureReason | None = None

    def __post_init__(self) -> None:
        if self.status is CharacterGenerationV2Status.COMPLETED:
            if not isinstance(self.draft, CharacterDraft) or self.failure_reason is not None:
                raise ValueError("COMPLETED result requires only a shared CharacterDraft")
        elif self.status is CharacterGenerationV2Status.FAILED:
            if self.draft is not None or self.failure_reason is None:
                raise ValueError("FAILED result requires a finite reason and no draft")
        else:
            raise ValueError("unsupported V2 generation result status")


class CharacterGenerationV2Generator:
    """Invoke one injected shared model and delegate all draft structure to B1C."""

    def __init__(self, model: AgentModel) -> None:
        self._model = model

    def generate(self, finalization_input: CharacterFinalizationInputV1) -> CharacterGenerationV2Result:
        """Generate once, with at most one B1C-authorized missing-only recovery."""

        if not isinstance(finalization_input, CharacterFinalizationInputV1):
            raise TypeError("finalization_input must be CharacterFinalizationInputV1")

        model_invocations: list[ModelInvocationAudit] = []
        initial_call_count = 1
        try:
            turn = self._model.generate(
                _generation_prompt(finalization_input)
            )
        except ModelMalformedResponseError as error:
            _append_error_audit(model_invocations, error)
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.STRUCTURED_OUTPUT_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
            )
        except ModelError as error:
            _append_error_audit(model_invocations, error)
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.PROVIDER_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
            )

        _append_turn_audit(model_invocations, turn)
        if not _has_structured_mapping(turn):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.STRUCTURED_OUTPUT_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
            )

        initial_output = inspect_character_draft_output(
            turn.structured_output,
            finalization_input,
        )
        if initial_output.status is CharacterDraftOutputStatus.READY:
            return _completed(
                finalization_input,
                initial_output.draft,
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
                output_audit=initial_output.audit,
                output_inspection=initial_output.inspection,
            )
        if initial_output.status is CharacterDraftOutputStatus.FAILED:
            return _failed(
                finalization_input,
                _output_failure_reason(
                    initial_output.failure_reason,
                    fallback=CharacterGenerationV2FailureReason.DRAFT_STRUCTURE_FAILURE,
                ),
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
                output_audit=initial_output.audit,
                output_inspection=initial_output.inspection,
            )

        recovery_input = initial_output.recovery_input
        if not isinstance(recovery_input, CharacterDraftRecoveryInputV1):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.DRAFT_STRUCTURE_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=0,
                model_invocations=model_invocations,
                output_audit=initial_output.audit,
                output_inspection=initial_output.inspection,
            )

        # INVARIANT: this direct second invocation is reachable only from the
        # one B1C RECOVERY_REQUIRED result; no loop or semantic retry exists.
        recovery_call_count = 1
        try:
            recovery_turn = self._model.generate(_recovery_prompt(recovery_input))
        except ModelError as error:
            _append_error_audit(model_invocations, error)
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.RECOVERY_PROVIDER_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=initial_output.audit,
                output_inspection=initial_output.inspection,
            )

        _append_turn_audit(model_invocations, recovery_turn)
        if not _has_structured_mapping(recovery_turn):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.STRUCTURAL_RECOVERY_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=initial_output.audit,
                output_inspection=initial_output.inspection,
            )

        recovered = merge_character_draft_recovery(
            recovery_input,
            recovery_turn.structured_output,
        )
        if recovered.status is CharacterDraftOutputStatus.READY:
            return _completed(
                finalization_input,
                recovered.draft,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=recovered.audit,
                output_inspection=recovered.inspection,
            )
        return _failed(
            finalization_input,
            _output_failure_reason(
                recovered.failure_reason,
                fallback=CharacterGenerationV2FailureReason.STRUCTURAL_RECOVERY_FAILURE,
            ),
            initial_call_count=initial_call_count,
            recovery_call_count=recovery_call_count,
            model_invocations=model_invocations,
            output_audit=recovered.audit,
            output_inspection=recovered.inspection,
        )


def _generation_prompt(finalization_input: CharacterFinalizationInputV1) -> AgentPrompt:
    """Build a deterministic prompt from B1B's semantic projection only."""

    return _prompt(
        finalization_input,
        system_contract=CHARACTER_GENERATION_V2_SYSTEM_CONTRACT,
        payload=finalization_input.to_model_input(),
        response_format="character_draft",
        invocation_purpose="generation",
        turn_number=1,
    )


def _recovery_prompt(recovery_input: CharacterDraftRecoveryInputV1) -> AgentPrompt:
    """Use the B1C recovery projection without rebuilding generation authority."""

    return _prompt(
        recovery_input.finalization_input,
        system_contract=CHARACTER_DRAFT_RECOVERY_SYSTEM_CONTRACT,
        payload=recovery_input.to_model_input(),
        response_format="character_draft_recovery",
        invocation_purpose="structural_recovery",
        turn_number=2,
    )


def _prompt(
    finalization_input: CharacterFinalizationInputV1,
    *,
    system_contract: str,
    payload: Mapping[str, object],
    response_format: str,
    invocation_purpose: str,
    turn_number: int,
) -> AgentPrompt:
    # AgentPrompt requires NPC views for compatibility. LiveLLMAdapter sends
    # only authoring_payload on this path, so these fixed sentinels are never
    # provider-visible and cannot smuggle runtime or identity context.
    return AgentPrompt(
        system_contract=system_contract,
        character=NpcCharacterView(
            "v2-no-character", "", "", (), (), "", "", (), "", ""
        ),
        runtime=NpcRuntimeView("v2-no-runtime", "", None, (), ()),
        messages=(),
        available_tools=(),
        session_id=finalization_input.request_id,
        turn_number=turn_number,
        response_format=response_format,
        authoring_payload=payload,
        invocation_purpose=invocation_purpose,
    )


def _has_structured_mapping(turn: object) -> bool:
    """Reject tools, text-only turns, and unexpected model return values."""

    return (
        isinstance(turn, ModelTurn)
        and not turn.tool_calls
        and isinstance(turn.structured_output, Mapping)
    )


def _output_failure_reason(
    reason: CharacterDraftOutputFailureReason | None,
    *,
    fallback: CharacterGenerationV2FailureReason,
) -> CharacterGenerationV2FailureReason:
    """Expose B1A value violations separately from structural draft failures."""

    if reason in {
        CharacterDraftOutputFailureReason.FIELD_AUTHORIZATION_VIOLATION,
        CharacterDraftOutputFailureReason.CANON_VALUE_MISMATCH,
        CharacterDraftOutputFailureReason.RECOVERY_UNAUTHORIZED_FIELD,
        CharacterDraftOutputFailureReason.RECOVERY_INVALID_CANON_VALUE,
    }:
        return CharacterGenerationV2FailureReason.FIELD_AUTHORIZATION_VIOLATION
    return fallback


def _append_turn_audit(
    audits: list[ModelInvocationAudit], turn: object
) -> None:
    if isinstance(turn, ModelTurn) and isinstance(turn.invocation, ModelInvocationAudit):
        audits.append(turn.invocation)


def _append_error_audit(
    audits: list[ModelInvocationAudit], error: ModelError
) -> None:
    if isinstance(error.audit, ModelInvocationAudit):
        audits.append(error.audit)


def _completed(
    finalization_input: CharacterFinalizationInputV1,
    draft: CharacterDraft | None,
    *,
    initial_call_count: int,
    recovery_call_count: int,
    model_invocations: list[ModelInvocationAudit],
    output_audit: CharacterDraftOutputAudit,
    output_inspection: CharacterDraftStructureInspection,
) -> CharacterGenerationV2Result:
    if not isinstance(draft, CharacterDraft):
        return _failed(
            finalization_input,
            CharacterGenerationV2FailureReason.DRAFT_STRUCTURE_FAILURE,
            initial_call_count=initial_call_count,
            recovery_call_count=recovery_call_count,
            model_invocations=model_invocations,
            output_audit=output_audit,
            output_inspection=output_inspection,
        )
    naming_design = finalization_input.semantic.get("naming_design")
    naming_enforcement = "NOT_APPLICABLE"
    if isinstance(naming_design, Mapping):
        selected_name = naming_design.get("selected_name")
        if not isinstance(selected_name, str) or not selected_name.strip():
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.NAMING_VALIDATION_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
            )
        if is_occupation_as_name(selected_name, draft.occupation):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.NAMING_VALIDATION_FAILURE,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
                naming_enforcement_status="REJECTED_OCCUPATION_COLLISION",
            )
        naming_enforcement = "PRESERVED" if draft.name == selected_name else "RESTORED"
        draft = replace(draft, name=selected_name)
    gender_requirement_data = finalization_input.semantic.get("gender_requirement")
    if gender_requirement_data is not None:
        try:
            if not isinstance(gender_requirement_data, Mapping):
                raise TypeError("gender_requirement must be a mapping")
            gender_requirement = ExplicitGenderRequirement.from_mapping(
                gender_requirement_data
            )
        except (TypeError, ValueError):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.HARD_REQUIREMENT_VIOLATION,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
            )
        if not gender_requirement.satisfied_by(draft.gender):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.HARD_REQUIREMENT_VIOLATION,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
            )
    age_requirement_data = finalization_input.semantic.get("age_requirement")
    if age_requirement_data is not None:
        try:
            if not isinstance(age_requirement_data, Mapping):
                raise TypeError("age_requirement must be a mapping")
            age_requirement = ExplicitAgeRequirement.from_mapping(
                age_requirement_data
            )
        except (TypeError, ValueError):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.HARD_REQUIREMENT_VIOLATION,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
            )
        if not age_requirement.satisfied_by(draft.age):
            return _failed(
                finalization_input,
                CharacterGenerationV2FailureReason.HARD_REQUIREMENT_VIOLATION,
                initial_call_count=initial_call_count,
                recovery_call_count=recovery_call_count,
                model_invocations=model_invocations,
                output_audit=output_audit,
                output_inspection=output_inspection,
            )
    requested_affiliation_id = finalization_input.semantic.get(
        "requested_affiliation_id"
    )
    if requested_affiliation_id is not None and (
        not isinstance(requested_affiliation_id, str)
        or not requested_affiliation_id
        or draft.faction_id != requested_affiliation_id
    ):
        return _failed(
            finalization_input,
            CharacterGenerationV2FailureReason.HARD_REQUIREMENT_VIOLATION,
            initial_call_count=initial_call_count,
            recovery_call_count=recovery_call_count,
            model_invocations=model_invocations,
            output_audit=output_audit,
            output_inspection=output_inspection,
        )
    return CharacterGenerationV2Result(
        status=CharacterGenerationV2Status.COMPLETED,
        draft=draft,
        audit=_audit(
            finalization_input,
            initial_call_count,
            recovery_call_count,
            model_invocations,
            output_audit,
            output_inspection,
            naming_enforcement,
        ),
    )


def _failed(
    finalization_input: CharacterFinalizationInputV1,
    reason: CharacterGenerationV2FailureReason,
    *,
    initial_call_count: int,
    recovery_call_count: int,
    model_invocations: list[ModelInvocationAudit],
    output_audit: CharacterDraftOutputAudit | None = None,
    output_inspection: CharacterDraftStructureInspection | None = None,
    naming_enforcement_status: str = "NOT_APPLICABLE",
) -> CharacterGenerationV2Result:
    return CharacterGenerationV2Result(
        status=CharacterGenerationV2Status.FAILED,
        failure_reason=reason,
        audit=_audit(
            finalization_input,
            initial_call_count,
            recovery_call_count,
            model_invocations,
            output_audit,
            output_inspection,
            naming_enforcement_status,
        ),
    )


def _audit(
    finalization_input: CharacterFinalizationInputV1,
    initial_call_count: int,
    recovery_call_count: int,
    model_invocations: list[ModelInvocationAudit],
    output_audit: CharacterDraftOutputAudit | None,
    output_inspection: CharacterDraftStructureInspection | None,
    naming_enforcement_status: str = "NOT_APPLICABLE",
) -> CharacterGenerationV2Audit:
    return CharacterGenerationV2Audit(
        request_id=finalization_input.request_id,
        spec_id=finalization_input.spec_id,
        spec_digest=finalization_input.spec_digest,
        initial_call_count=initial_call_count,
        recovery_call_count=recovery_call_count,
        model_invocations=tuple(model_invocations[:2]),
        draft_output_audit=output_audit,
        draft_output_inspection=output_inspection,
        naming_enforcement=naming_enforcement_status,
    )
