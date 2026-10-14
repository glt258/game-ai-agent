"""Provider-neutral structural output and one-shot recovery contracts.

The module accepts an already structured mapping and a B1B finalization input.
It performs no parsing of model text, I/O, provider calls, Canon checks, or
semantic repair. CharacterDraft.from_mapping remains the sole materializer.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .character_draft import (
    CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS,
    CHARACTER_DRAFT_CORE_FIELDS,
    CharacterDraft,
)
from .draft_errors import CharacterDraftMappingError
from .field_authorization import CharacterGenerationField, FieldAuthorizationState
from .finalization_input import CharacterFinalizationInputV1


class CharacterDraftOutputStatus(str, Enum):
    """The mutually exclusive outcomes of structural draft processing."""

    READY = "READY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    FAILED = "FAILED"


MAX_STRUCTURAL_RECOVERY_ATTEMPTS = 1


class CharacterDraftOutputFailureReason(str, Enum):
    """Finite structural and recovery failures exposed by the B1C interface."""

    STRUCTURAL_CONTRACT_FAILURE = "STRUCTURAL_CONTRACT_FAILURE"
    RECOVERY_SCOPE_VIOLATION = "RECOVERY_SCOPE_VIOLATION"
    RECOVERY_OVERWRITE_ATTEMPT = "RECOVERY_OVERWRITE_ATTEMPT"
    RECOVERY_UNAUTHORIZED_FIELD = "RECOVERY_UNAUTHORIZED_FIELD"
    RECOVERY_INVALID_CANON_VALUE = "RECOVERY_INVALID_CANON_VALUE"
    CANON_VALUE_MISMATCH = "CANON_VALUE_MISMATCH"
    FIELD_AUTHORIZATION_VIOLATION = "FIELD_AUTHORIZATION_VIOLATION"
    RECOVERY_INCOMPLETE = "RECOVERY_INCOMPLETE"


class CharacterDraftMergeStatus(str, Enum):
    """Finite audit outcome for the one permitted recovery merge."""

    NOT_NEEDED = "NOT_NEEDED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CharacterDraftStructureInspection:
    """Immutable diagnosis of draft shape before or after one merge."""

    status: CharacterDraftOutputStatus
    missing_required_fields: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    normalized_fields: tuple[str, ...] = ()
    unauthorized_fields: tuple[str, ...] = ()
    failure_reason: CharacterDraftOutputFailureReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "missing_required_fields",
            _sorted_unique_names(self.missing_required_fields),
        )
        object.__setattr__(self, "unknown_fields", _sorted_unique_names(self.unknown_fields))
        object.__setattr__(
            self,
            "normalized_fields",
            _sorted_unique_names(self.normalized_fields),
        )
        object.__setattr__(
            self,
            "unauthorized_fields",
            _sorted_unique_names(self.unauthorized_fields),
        )
        if self.status is CharacterDraftOutputStatus.READY:
            if (
                self.missing_required_fields
                or self.unauthorized_fields
                or self.failure_reason is not None
            ):
                raise ValueError("READY inspection cannot be incomplete or failed")
        elif self.status is CharacterDraftOutputStatus.RECOVERY_REQUIRED:
            if (
                not self.missing_required_fields
                or self.unauthorized_fields
                or self.failure_reason is not None
            ):
                raise ValueError("RECOVERY_REQUIRED inspection needs missing fields only")
        elif self.status is CharacterDraftOutputStatus.FAILED:
            if self.failure_reason is None:
                raise ValueError("FAILED inspection needs a finite failure reason")
        else:
            raise ValueError("unsupported CharacterDraft output status")


@dataclass(frozen=True)
class CharacterDraftRecoveryInputV1:
    """Bounded, model-safe context for one missing-fields-only recovery."""

    original_partial_draft: Mapping[str, Any]
    missing_fields: tuple[str, ...]
    finalization_input: CharacterFinalizationInputV1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "original_partial_draft",
            _freeze_json_mapping(
                self.original_partial_draft,
                max_bytes=_MAX_RECOVERY_PARTIAL_DRAFT_BYTES,
            ),
        )
        object.__setattr__(self, "missing_fields", _sorted_unique_names(self.missing_fields))
        if not self.missing_fields:
            raise ValueError("recovery input must request at least one missing field")
        if not isinstance(self.finalization_input, CharacterFinalizationInputV1):
            raise TypeError("finalization_input must be CharacterFinalizationInputV1")

    def to_model_input(self) -> dict[str, object]:
        """Return only B1B's model-visible projection, never its audit lineage."""

        return {
            "finalization_input": self.finalization_input.to_model_input(),
            "original_partial_draft": _thaw_json(self.original_partial_draft),
            "missing_fields": list(self.missing_fields),
        }


@dataclass(frozen=True)
class CharacterDraftOutputAudit:
    """Content-free audit facts for recovery scope and merge behavior."""

    recovery_requested: bool = False
    requested_fields: tuple[str, ...] = ()
    returned_fields: tuple[str, ...] = ()
    merge_status: CharacterDraftMergeStatus = CharacterDraftMergeStatus.NOT_NEEDED
    failure_reason: CharacterDraftOutputFailureReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_fields", _sorted_unique_names(self.requested_fields))
        object.__setattr__(self, "returned_fields", _sorted_unique_names(self.returned_fields))
        if not self.recovery_requested:
            if self.requested_fields or self.returned_fields:
                raise ValueError("non-recovery audit cannot list recovery fields")
            if self.merge_status is not CharacterDraftMergeStatus.NOT_NEEDED:
                raise ValueError("non-recovery audit must use NOT_NEEDED")
        elif not self.requested_fields:
            raise ValueError("recovery audit must include requested fields")

        if self.merge_status is CharacterDraftMergeStatus.NOT_ATTEMPTED:
            if self.returned_fields or self.failure_reason is not None:
                raise ValueError("pending recovery cannot contain returned fields or a failure")
        elif self.merge_status is CharacterDraftMergeStatus.APPLIED:
            if set(self.returned_fields) != set(self.requested_fields):
                raise ValueError("applied recovery must return exactly the requested fields")
            if self.failure_reason is not None:
                raise ValueError("applied recovery cannot contain a failure")
        elif self.merge_status is CharacterDraftMergeStatus.REJECTED:
            if self.failure_reason is None:
                raise ValueError("rejected recovery needs a finite failure reason")


@dataclass(frozen=True)
class CharacterDraftOutputResult:
    """A fail-closed result: exactly one of draft, recovery input, or failure."""

    inspection: CharacterDraftStructureInspection
    draft: CharacterDraft | None = None
    recovery_input: CharacterDraftRecoveryInputV1 | None = None
    audit: CharacterDraftOutputAudit = field(default_factory=CharacterDraftOutputAudit)

    def __post_init__(self) -> None:
        status = self.inspection.status
        if status is CharacterDraftOutputStatus.READY:
            if not isinstance(self.draft, CharacterDraft) or self.recovery_input is not None:
                raise ValueError("READY result must contain only a CharacterDraft")
            if self.audit.failure_reason is not None:
                raise ValueError("READY result cannot carry a recovery failure")
            if self.audit.recovery_requested:
                if self.audit.merge_status is not CharacterDraftMergeStatus.APPLIED:
                    raise ValueError("recovered READY result must record one applied merge")
                if not self.audit.requested_fields:
                    raise ValueError("recovered READY result must record requested fields")
            elif (
                self.audit.requested_fields
                or self.audit.returned_fields
                or self.audit.merge_status is not CharacterDraftMergeStatus.NOT_NEEDED
            ):
                raise ValueError("initial READY result cannot contain recovery audit data")
        elif status is CharacterDraftOutputStatus.RECOVERY_REQUIRED:
            if self.draft is not None or not isinstance(
                self.recovery_input, CharacterDraftRecoveryInputV1
            ):
                raise ValueError("RECOVERY_REQUIRED result must contain only recovery input")
            if self.audit.requested_fields != self.inspection.missing_required_fields:
                raise ValueError("recovery audit must match the inspected missing fields")
            if self.recovery_input.missing_fields != self.inspection.missing_required_fields:
                raise ValueError("recovery input must match the inspected missing fields")
            if (
                not self.audit.recovery_requested
                or self.audit.merge_status is not CharacterDraftMergeStatus.NOT_ATTEMPTED
            ):
                raise ValueError("recovery result must describe one pending recovery")
        elif status is CharacterDraftOutputStatus.FAILED:
            if self.draft is not None or self.recovery_input is not None:
                raise ValueError("FAILED result cannot expose a draft or recovery input")
            if self.audit.failure_reason is not self.inspection.failure_reason:
                raise ValueError("failed result and inspection reasons must agree")
            expected_merge_status = (
                CharacterDraftMergeStatus.REJECTED
                if self.audit.recovery_requested
                else CharacterDraftMergeStatus.NOT_NEEDED
            )
            if self.audit.merge_status is not expected_merge_status:
                raise ValueError("failed result has an inconsistent merge audit")
        else:
            raise ValueError("unsupported CharacterDraft output status")

    @property
    def status(self) -> CharacterDraftOutputStatus:
        """Expose the inspection status without duplicating mutable state."""

        return self.inspection.status

    @property
    def failure_reason(self) -> CharacterDraftOutputFailureReason | None:
        """Return the finite failure reason, when structural processing failed."""

        return self.inspection.failure_reason


def inspect_character_draft_output(
    payload: Mapping[str, Any],
    finalization_input: CharacterFinalizationInputV1,
) -> CharacterDraftOutputResult:
    """Inspect a structured payload and materialize it or request one recovery.

    Required fields are the parser's core vocabulary, except for the explicit
    empty ``open_questions`` normalization, plus B1B's required-generation
    projection. A missing field is recoverable only when every present known
    field already passes the authoritative CharacterDraft parser.
    """

    if not isinstance(payload, Mapping) or not isinstance(
        finalization_input, CharacterFinalizationInputV1
    ):
        return _failed_result(CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE)

    try:
        snapshot = _freeze_json_mapping(payload)
        normalized_payload = _thaw_json(snapshot)
        unknown_fields = tuple(
            sorted(set(normalized_payload) - CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS)
        )
        normalized_fields: tuple[str, ...] = ()
        if "open_questions" not in normalized_payload:
            normalized_payload["open_questions"] = []
            normalized_fields = ("open_questions",)

        required_fields, authorization, valid_context = _required_field_context(
            finalization_input
        )
        if not valid_context or not _required_fields_are_authorized(
            required_fields, authorization
        ):
            return _failed_result(
                CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
                unknown_fields=unknown_fields,
                normalized_fields=normalized_fields,
            )

        missing_fields = tuple(
            sorted(
                field_name
                for field_name in required_fields
                if field_name not in normalized_payload
            )
        )
        if unknown_fields and missing_fields:
            return _failed_result(
                CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
                missing_fields=missing_fields,
                unknown_fields=unknown_fields,
                normalized_fields=normalized_fields,
            )

        known_payload = {
            field_name: value
            for field_name, value in normalized_payload.items()
            if field_name in CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS
        }
        parser_probe = _parser_validation_probe(known_payload)
        try:
            CharacterDraft.from_mapping(parser_probe)
        except (TypeError, ValueError, CharacterDraftMappingError, RecursionError):
            return _failed_result(
                CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
                missing_fields=missing_fields,
                unknown_fields=unknown_fields,
                normalized_fields=normalized_fields,
            )

        if not _present_canon_values_are_authorized(known_payload, authorization):
            return _failed_result(
                CharacterDraftOutputFailureReason.CANON_VALUE_MISMATCH,
                missing_fields=missing_fields,
                unknown_fields=unknown_fields,
                normalized_fields=normalized_fields,
            )

        unauthorized_fields = _present_unauthorized_fields(
            known_payload,
            authorization,
        )
        if unauthorized_fields:
            return _failed_result(
                CharacterDraftOutputFailureReason.FIELD_AUTHORIZATION_VIOLATION,
                unknown_fields=unknown_fields,
                normalized_fields=normalized_fields,
                unauthorized_fields=unauthorized_fields,
            )

        if missing_fields:
            try:
                recovery_input = CharacterDraftRecoveryInputV1(
                    original_partial_draft=known_payload,
                    missing_fields=missing_fields,
                    finalization_input=finalization_input,
                )
            except (TypeError, ValueError, RecursionError):
                return _failed_result(
                    CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
                    missing_fields=missing_fields,
                    unknown_fields=unknown_fields,
                    normalized_fields=normalized_fields,
                )
            inspection = CharacterDraftStructureInspection(
                status=CharacterDraftOutputStatus.RECOVERY_REQUIRED,
                missing_required_fields=missing_fields,
                normalized_fields=normalized_fields,
                unknown_fields=unknown_fields,
            )
            audit = CharacterDraftOutputAudit(
                recovery_requested=True,
                requested_fields=missing_fields,
                merge_status=CharacterDraftMergeStatus.NOT_ATTEMPTED,
            )
            return CharacterDraftOutputResult(
                inspection=inspection,
                recovery_input=recovery_input,
                audit=audit,
            )

        draft = CharacterDraft.from_mapping(known_payload)
    except (TypeError, ValueError, CharacterDraftMappingError, RecursionError):
        return _failed_result(CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE)

    inspection = CharacterDraftStructureInspection(
        status=CharacterDraftOutputStatus.READY,
        unknown_fields=unknown_fields,
        normalized_fields=normalized_fields,
    )
    return CharacterDraftOutputResult(inspection=inspection, draft=draft)


def merge_character_draft_recovery(
    recovery_input: CharacterDraftRecoveryInputV1,
    recovery_output: Mapping[str, Any],
) -> CharacterDraftOutputResult:
    """Apply exactly one missing-only recovery response and reinspect it.

    Existing values are never rewritten, even when the recovery response
    repeats an equal value. A partial first recovery is terminal; this function
    never creates a second recovery request.
    """

    if not isinstance(recovery_input, CharacterDraftRecoveryInputV1) or not isinstance(
        recovery_output, Mapping
    ):
        return _failed_result(CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE)

    requested_fields = recovery_input.missing_fields
    try:
        output_snapshot = _freeze_json_mapping(
            recovery_output,
            max_bytes=_MAX_RECOVERY_PARTIAL_DRAFT_BYTES,
        )
    except (TypeError, ValueError, RecursionError):
        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
            returned_fields=(),
        )

    returned_fields = tuple(sorted(output_snapshot))
    original_fields = set(recovery_input.original_partial_draft)
    if original_fields & set(returned_fields):
        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.RECOVERY_OVERWRITE_ATTEMPT,
            returned_fields=returned_fields,
        )

    required_fields, authorization, valid_context = _required_field_context(
        recovery_input.finalization_input
    )
    if not valid_context:
        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
            returned_fields=returned_fields,
        )

    requested_set = set(requested_fields)
    if not requested_set <= required_fields:
        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.RECOVERY_SCOPE_VIOLATION,
            returned_fields=returned_fields,
        )

    for field_name in requested_set:
        field_authority = authorization.get(field_name)
        if field_authority is None:
            continue
        state, allowed_values = field_authority
        if state is FieldAuthorizationState.UNAUTHORIZED:
            return _recovery_failed_result(
                recovery_input,
                CharacterDraftOutputFailureReason.RECOVERY_UNAUTHORIZED_FIELD,
                returned_fields=returned_fields,
            )
        if state is FieldAuthorizationState.CANON_GROUNDED_ONLY and not allowed_values:
            return _recovery_failed_result(
                recovery_input,
                CharacterDraftOutputFailureReason.RECOVERY_INVALID_CANON_VALUE,
                returned_fields=returned_fields,
            )

    for field_name in returned_fields:
        if field_name in requested_set:
            field_authority = authorization.get(field_name)
            if field_authority is None:
                continue
            state, allowed_values = field_authority
            if state is FieldAuthorizationState.CANON_GROUNDED_ONLY:
                try:
                    is_authorized_value = _matches_exact_json_value(
                        output_snapshot[field_name], allowed_values
                    )
                except (TypeError, ValueError, RecursionError):
                    return _recovery_failed_result(
                        recovery_input,
                        CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE,
                        returned_fields=returned_fields,
                    )
                if not is_authorized_value:
                    return _recovery_failed_result(
                        recovery_input,
                        CharacterDraftOutputFailureReason.RECOVERY_INVALID_CANON_VALUE,
                        returned_fields=returned_fields,
                    )
            elif state is FieldAuthorizationState.UNAUTHORIZED:
                return _recovery_failed_result(
                    recovery_input,
                    CharacterDraftOutputFailureReason.RECOVERY_UNAUTHORIZED_FIELD,
                    returned_fields=returned_fields,
                )
            continue

        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.RECOVERY_SCOPE_VIOLATION,
            returned_fields=returned_fields,
        )

    if not requested_set <= set(returned_fields):
        return _recovery_failed_result(
            recovery_input,
            CharacterDraftOutputFailureReason.RECOVERY_INCOMPLETE,
            returned_fields=returned_fields,
        )

    merged_payload = _thaw_json(recovery_input.original_partial_draft)
    for field_name in requested_fields:
        merged_payload[field_name] = _thaw_json(output_snapshot[field_name])

    inspected = inspect_character_draft_output(
        merged_payload,
        recovery_input.finalization_input,
    )
    if inspected.status is CharacterDraftOutputStatus.READY:
        audit = CharacterDraftOutputAudit(
            recovery_requested=True,
            requested_fields=requested_fields,
            returned_fields=returned_fields,
            merge_status=CharacterDraftMergeStatus.APPLIED,
        )
        return CharacterDraftOutputResult(
            inspection=inspected.inspection,
            draft=inspected.draft,
            audit=audit,
        )

    reason = (
        CharacterDraftOutputFailureReason.RECOVERY_INCOMPLETE
        if inspected.status is CharacterDraftOutputStatus.RECOVERY_REQUIRED
        else inspected.failure_reason
        or CharacterDraftOutputFailureReason.STRUCTURAL_CONTRACT_FAILURE
    )
    return _recovery_failed_result(
        recovery_input,
        reason,
        returned_fields=returned_fields,
        missing_fields=(
            inspected.inspection.missing_required_fields
            if inspected.status is CharacterDraftOutputStatus.RECOVERY_REQUIRED
            else recovery_input.missing_fields
        ),
    )


def _failed_result(
    reason: CharacterDraftOutputFailureReason,
    *,
    missing_fields: tuple[str, ...] = (),
    unknown_fields: tuple[str, ...] = (),
    normalized_fields: tuple[str, ...] = (),
    recovery_requested: bool = False,
    requested_fields: tuple[str, ...] = (),
    returned_fields: tuple[str, ...] = (),
    unauthorized_fields: tuple[str, ...] = (),
) -> CharacterDraftOutputResult:
    """Build the same invariant-checked finite failure shape at each boundary."""

    inspection = CharacterDraftStructureInspection(
        status=CharacterDraftOutputStatus.FAILED,
        missing_required_fields=missing_fields,
        unknown_fields=unknown_fields,
        normalized_fields=normalized_fields,
        unauthorized_fields=unauthorized_fields,
        failure_reason=reason,
    )
    audit = CharacterDraftOutputAudit(
        recovery_requested=recovery_requested,
        requested_fields=requested_fields,
        returned_fields=returned_fields,
        merge_status=(
            CharacterDraftMergeStatus.REJECTED
            if recovery_requested
            else CharacterDraftMergeStatus.NOT_NEEDED
        ),
        failure_reason=reason,
    )
    return CharacterDraftOutputResult(inspection=inspection, audit=audit)


def _recovery_failed_result(
    recovery_input: CharacterDraftRecoveryInputV1,
    reason: CharacterDraftOutputFailureReason,
    *,
    returned_fields: tuple[str, ...],
    missing_fields: tuple[str, ...] | None = None,
) -> CharacterDraftOutputResult:
    """Retain only finite recovery facts when a one-shot merge is rejected."""

    return _failed_result(
        reason,
        missing_fields=(
            recovery_input.missing_fields if missing_fields is None else missing_fields
        ),
        recovery_requested=True,
        requested_fields=recovery_input.missing_fields,
        returned_fields=returned_fields,
    )


def _required_field_context(
    finalization_input: CharacterFinalizationInputV1,
) -> tuple[frozenset[str], Mapping[str, tuple[FieldAuthorizationState, tuple[Any, ...]]], bool]:
    """Read B1B's existing required-field and authorization projections."""

    semantic = finalization_input.semantic
    required = semantic.get("required_generation_fields")
    policy = semantic.get("field_authorization_policy")
    if not isinstance(required, (tuple, list)) or not isinstance(policy, Mapping):
        return frozenset(), MappingProxyType({}), False
    field_authorizations = policy.get("field_authorizations")
    if not isinstance(field_authorizations, Mapping):
        return frozenset(), MappingProxyType({}), False

    required_fields: set[str] = set(CHARACTER_DRAFT_CORE_FIELDS)
    required_fields.discard("open_questions")
    authorization: dict[str, tuple[FieldAuthorizationState, tuple[Any, ...]]] = {}
    expected_authorization_fields = {field.value for field in CharacterGenerationField}
    if set(field_authorizations) != expected_authorization_fields:
        return frozenset(), MappingProxyType({}), False

    for field_value in CharacterGenerationField:
        field_name = field_value.value
        entry = field_authorizations.get(field_name)
        if not isinstance(entry, Mapping) or entry.get("field") != field_name:
            return frozenset(), MappingProxyType({}), False
        try:
            state = FieldAuthorizationState(entry.get("state"))
        except (TypeError, ValueError):
            return frozenset(), MappingProxyType({}), False
        exact_values = entry.get("allowed_exact_values", ())
        if not isinstance(exact_values, (tuple, list)):
            return frozenset(), MappingProxyType({}), False
        authorization[field_name] = (state, tuple(exact_values))

    seen_required: set[str] = set()
    for raw_field_name in required:
        if not isinstance(raw_field_name, str):
            return frozenset(), MappingProxyType({}), False
        try:
            field_name = CharacterGenerationField(raw_field_name).value
        except ValueError:
            return frozenset(), MappingProxyType({}), False
        if field_name in seen_required:
            return frozenset(), MappingProxyType({}), False
        seen_required.add(field_name)
        if field_name not in CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS:
            return frozenset(), MappingProxyType({}), False

    required_fields.update(seen_required)
    return frozenset(required_fields), MappingProxyType(authorization), True


def _required_fields_are_authorized(
    required_fields: frozenset[str],
    authorization: Mapping[str, tuple[FieldAuthorizationState, tuple[Any, ...]]],
) -> bool:
    """Reject a B1B contract that requires a denied or ungrounded field."""

    for field_name, (state, allowed_values) in authorization.items():
        if field_name not in required_fields:
            continue
        if state is FieldAuthorizationState.UNAUTHORIZED:
            return False
        if state is FieldAuthorizationState.CANON_GROUNDED_ONLY and not allowed_values:
            return False
    return True


def _present_canon_values_are_authorized(
    payload: Mapping[str, Any],
    authorization: Mapping[str, tuple[FieldAuthorizationState, tuple[Any, ...]]],
) -> bool:
    """Require every present CANON_GROUNDED_ONLY value to match B1B exactly."""

    for field_name, (state, allowed_values) in authorization.items():
        if state is not FieldAuthorizationState.CANON_GROUNDED_ONLY:
            continue
        if field_name not in payload:
            continue
        try:
            if not _matches_exact_json_value(payload[field_name], allowed_values):
                return False
        except (TypeError, ValueError, RecursionError):
            return False
    return True


def _present_unauthorized_fields(
    payload: Mapping[str, Any],
    authorization: Mapping[str, tuple[FieldAuthorizationState, tuple[Any, ...]]],
) -> tuple[str, ...]:
    """Reject authored values in every B1A-denied field, including optional ones."""

    violations: list[str] = []
    for field_name, (state, _) in authorization.items():
        if state is not FieldAuthorizationState.UNAUTHORIZED or field_name not in payload:
            continue
        if _contains_semantic_content(payload[field_name]):
            violations.append(field_name)
    return tuple(sorted(violations))


def _contains_semantic_content(value: Any) -> bool:
    """Treat only empty text, null, and empty JSON containers as no authored value."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_contains_semantic_content(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_semantic_content(item) for item in value)
    return True


def _matches_exact_json_value(value: Any, allowed_values: tuple[Any, ...]) -> bool:
    """Compare JSON meaning without trimming, normalization, or semantic matching."""

    canonical_value = _canonical_json(value)
    return canonical_value in {_canonical_json(item) for item in allowed_values}


def _canonical_json(value: Any) -> str:
    """Compare system-owned exact values by their JSON meaning, not identity."""

    frozen = _freeze_json_value(value, depth=0, ancestors=frozenset())
    return json.dumps(
        _thaw_json(frozen),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_PARSER_VALIDATION_PLACEHOLDERS: Mapping[str, Any] = MappingProxyType(
    {
        "draft_id": "draft_b1c_validation_probe",
        "status": "draft",
        "name": "B1C validation probe",
        "canon_basis": [],
        "new_design_elements": [],
    }
)


def _parser_validation_probe(
    known_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate present values without promoting placeholders into recovery data.

    CharacterDraft.from_mapping remains the one parser. Its core fields are
    supplied only to this disposable probe when absent; the returned object is
    discarded, and those values never enter the recovery request or final draft.
    """

    probe = dict(known_payload)
    missing_core = set(CHARACTER_DRAFT_CORE_FIELDS) - set(probe)
    for field_name in missing_core:
        if field_name == "open_questions":
            probe[field_name] = []
        else:
            probe[field_name] = _PARSER_VALIDATION_PLACEHOLDERS[field_name]
    return probe


def _sorted_unique_names(values: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize immutable field-name diagnostics into stable order."""

    if isinstance(values, (str, bytes)):
        raise TypeError("field names must be a sequence of strings")
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value for value in normalized):
        raise TypeError("field names must be non-empty strings")
    return tuple(sorted(set(normalized)))


# A recovery prompt receives at most this many bytes of caller-supplied draft
# data; the rest of its semantic context is already bounded by B1B's contract.
# ponytail: raise only when measured valid drafts need it and the recovery budget grows.
_MAX_RECOVERY_PARTIAL_DRAFT_BYTES = 64 * 1024


def _freeze_json_mapping(
    value: Mapping[str, Any], *, max_bytes: int | None = None
) -> Mapping[str, Any]:
    """Detach JSON-shaped input recursively before retaining it in a contract."""

    if not isinstance(value, Mapping):
        raise TypeError("payload must be a mapping")
    frozen = _freeze_json_value(value, depth=0, ancestors=frozenset())
    if not isinstance(frozen, Mapping):
        raise TypeError("payload must be a mapping")
    if max_bytes is None:
        return frozen

    encoded = json.dumps(
        _thaw_json(frozen),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("draft payload exceeds the structural recovery size bound")
    return frozen


def _freeze_json_value(
    value: Any,
    *,
    depth: int,
    ancestors: frozenset[int],
) -> Any:
    """Freeze one JSON value and reject cycles, excessive depth, and non-JSON types."""

    if depth > 16:
        raise ValueError("draft payload exceeds the structural recovery depth bound")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("draft payload contains a non-finite number")
        return value

    identity = id(value)
    if identity in ancestors:
        raise ValueError("draft payload cannot contain a cycle")
    nested_ancestors = ancestors | {identity}

    if isinstance(value, Mapping):
        if len(value) > 4096 or any(not isinstance(key, str) for key in value):
            raise ValueError("draft payload contains invalid mapping keys or size")
        return MappingProxyType(
            {
                key: _freeze_json_value(
                    value[key], depth=depth + 1, ancestors=nested_ancestors
                )
                for key in sorted(value)
            }
        )

    if isinstance(value, (list, tuple)):
        if len(value) > 4096:
            raise ValueError("draft payload contains an oversized array")
        return tuple(
            _freeze_json_value(item, depth=depth + 1, ancestors=nested_ancestors)
            for item in value
        )

    raise ValueError("draft payload contains a non-JSON value")


def _thaw_json(value: Any) -> Any:
    """Return a detached mutable JSON representation for existing parsers."""

    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value
