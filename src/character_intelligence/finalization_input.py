"""Build a provider-neutral input from frozen character-generation semantics.

This boundary consumes only the resolved spec and caller-supplied bounded
domain evidence. It deliberately does not know about Agents, retrieval,
providers, application routes, or CharacterDraft recovery.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from .field_authorization import (
    CharacterGenerationField,
    FieldAuthorizationState,
)

if TYPE_CHECKING:
    from .planner.character_generation_spec import ResolvedCharacterGenerationSpecV1

CHARACTER_FINALIZATION_INPUT_V1_SCHEMA = "character-finalization-input/v1"

# Four source entries per governed field is enough for a few independent
# observations; a separate fact count bounds payload growth across all sources.
_MAX_EVIDENCE_SOURCES = 32
_MAX_EVIDENCE_FACTS = 64
_MAX_VALUES_PER_FIELD = 8
_MAX_EVIDENCE_VALUE_BYTES = 4096
_MAX_EVIDENCE_VALUE_DEPTH = 8
_MAX_REFERENCE_CONTEXTS = 16
_MAX_REFERENCE_ITEMS_PER_CATEGORY = 16
_MAX_REFERENCE_TEXT_LENGTH = 512


class FinalizationInputFailureReason(str, Enum):
    """Finite failures for cross-contract input inconsistencies."""

    SPEC_INPUT_MISMATCH = "SPEC_INPUT_MISMATCH"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    EVIDENCE_LIMIT_EXCEEDED = "EVIDENCE_LIMIT_EXCEEDED"
    UNAUTHORIZED_EVIDENCE_SOURCE = "UNAUTHORIZED_EVIDENCE_SOURCE"
    UNAUTHORIZED_EVIDENCE_VALUE = "UNAUTHORIZED_EVIDENCE_VALUE"
    MISSING_CANON_VALUE_AUTHORITY = "MISSING_CANON_VALUE_AUTHORITY"
    INVALID_REFERENCE_CONTEXT = "INVALID_REFERENCE_CONTEXT"
    REFERENCE_LIMIT_EXCEEDED = "REFERENCE_LIMIT_EXCEEDED"


class FinalizationInputError(ValueError):
    """Raised when evidence or references do not match the frozen spec."""

    def __init__(self, reason: FinalizationInputFailureReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


def _error(reason: FinalizationInputFailureReason, detail: str) -> FinalizationInputError:
    return FinalizationInputError(reason, detail)


def _freeze_json(value: Any) -> Any:
    """Detach JSON data into immutable containers with deterministic keys."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return MappingProxyType(
            {key: _freeze_json(value[key]) for key in sorted(value)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ValueError("value is not JSON-compatible")


def _freeze_bounded_value(value: Any, *, depth: int = 0) -> Any:
    """Freeze one evidence value while enforcing the input's payload ceiling."""

    if depth > _MAX_EVIDENCE_VALUE_DEPTH:
        raise ValueError("evidence value is too deeply nested")
    frozen: Any
    if value is None or isinstance(value, (str, bool, int)):
        frozen = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evidence numbers must be finite")
        frozen = value
    elif isinstance(value, Mapping):
        if len(value) > 64 or not all(isinstance(key, str) for key in value):
            raise ValueError("evidence object exceeds its key or item limit")
        frozen = MappingProxyType(
            {
                key: _freeze_bounded_value(value[key], depth=depth + 1)
                for key in sorted(value)
            }
        )
    elif isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise ValueError("evidence array exceeds its item limit")
        frozen = tuple(
            _freeze_bounded_value(item, depth=depth + 1) for item in value
        )
    else:
        raise ValueError("evidence value is not JSON-compatible")
    encoded = json.dumps(
        _plain_json(frozen),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_EVIDENCE_VALUE_BYTES:
        raise ValueError("evidence value exceeds its size limit")
    return frozen


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _plain_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _required_text(value: object, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{label} must be non-empty text within its size limit")
    return value.strip()


def _bounded_texts(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a bounded sequence of text")
    if len(value) > _MAX_REFERENCE_ITEMS_PER_CATEGORY:
        raise ValueError(f"{label} exceeds its item limit")
    return tuple(
        sorted(
            {
                _required_text(item, label, maximum=_MAX_REFERENCE_TEXT_LENGTH)
                for item in value
            }
        )
    )


@dataclass(frozen=True)
class BoundedGenerationEvidenceV1:
    """One source's field-specific factual values, without retrieval history.

    The source ID is the evidence provenance that crosses this boundary. Tool
    calls, observations, ranking metadata, and action-round details do not.
    """

    source_id: str
    source_type: str
    field_values: Mapping[CharacterGenerationField, Sequence[Any]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _required_text(self.source_id, "source_id"))
        object.__setattr__(
            self, "source_type", _required_text(self.source_type, "source_type", maximum=64)
        )
        if not isinstance(self.field_values, Mapping) or not self.field_values:
            raise ValueError("field_values must be a non-empty mapping")

        normalized: dict[CharacterGenerationField, tuple[Any, ...]] = {}
        for field_value, values in self.field_values.items():
            if not isinstance(field_value, CharacterGenerationField):
                raise ValueError("field_values keys must use CharacterGenerationField")
            if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Sequence):
                raise ValueError("each field value must be a bounded sequence")
            if not values or len(values) > _MAX_VALUES_PER_FIELD:
                raise ValueError("each field must contain one to eight factual values")
            normalized[field_value] = tuple(
                _freeze_bounded_value(value) for value in values
            )
        object.__setattr__(
            self,
            "field_values",
            MappingProxyType(dict(sorted(normalized.items(), key=lambda item: item[0].value))),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a fresh, deterministic JSON-shaped evidence record."""

        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "field_values": {
                field_value.value: [_plain_json(item) for item in values]
                for field_value, values in self.field_values.items()
            },
        }


@dataclass(frozen=True)
class AllowedReferenceContextV1:
    """A bounded, non-authoritative design precedent selected by the spec."""

    reference_id: str
    display_name: str | None = None
    game_id: str | None = None
    roles: Sequence[str] = ()
    narrative: Sequence[str] = ()
    visual: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference_id", _required_text(self.reference_id, "reference_id")
        )
        for field_name in ("display_name", "game_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _required_text(value, field_name, maximum=_MAX_REFERENCE_TEXT_LENGTH),
                )
        for field_name in ("roles", "narrative", "visual"):
            object.__setattr__(
                self, field_name, _bounded_texts(getattr(self, field_name), field_name)
            )
        if not any((self.display_name, self.game_id, self.roles, self.narrative, self.visual)):
            raise ValueError("reference context must contain bounded precedent data")

    def to_dict(self) -> dict[str, object]:
        """Return only the bounded precedent fields admitted by this DTO."""

        return {
            "reference_id": self.reference_id,
            "display_name": self.display_name,
            "game_id": self.game_id,
            "roles": list(self.roles),
            "narrative": list(self.narrative),
            "visual": list(self.visual),
        }


@dataclass(frozen=True)
class CharacterFinalizationInputV1:
    """Immutable model-facing semantics with separately held audit lineage."""

    semantic: Mapping[str, Any]
    evidence: tuple[BoundedGenerationEvidenceV1, ...]
    reference_context: tuple[AllowedReferenceContextV1, ...]
    request_id: str
    spec_id: str
    spec_digest: str
    spec_audit_lineage: Mapping[str, Any]
    schema_version: str = CHARACTER_FINALIZATION_INPUT_V1_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != CHARACTER_FINALIZATION_INPUT_V1_SCHEMA:
            raise ValueError(f"unsupported schema_version: {self.schema_version!r}")
        if not isinstance(self.semantic, Mapping):
            raise TypeError("semantic must be a mapping")
        if not all(isinstance(item, BoundedGenerationEvidenceV1) for item in self.evidence):
            raise TypeError("evidence must contain BoundedGenerationEvidenceV1 values")
        if not all(
            isinstance(item, AllowedReferenceContextV1) for item in self.reference_context
        ):
            raise TypeError("reference_context must contain AllowedReferenceContextV1 values")
        if not isinstance(self.spec_audit_lineage, Mapping):
            raise TypeError("spec_audit_lineage must be a mapping")
        object.__setattr__(self, "semantic", _freeze_json(self.semantic))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "reference_context", tuple(self.reference_context))
        object.__setattr__(self, "request_id", _required_text(self.request_id, "request_id"))
        object.__setattr__(self, "spec_id", _required_text(self.spec_id, "spec_id"))
        object.__setattr__(self, "spec_digest", _required_text(self.spec_digest, "spec_digest"))
        object.__setattr__(self, "spec_audit_lineage", _freeze_json(self.spec_audit_lineage))

    def to_model_input(self) -> dict[str, object]:
        """Return the deterministic model-visible payload, excluding all audit IDs."""

        return {
            "schema_version": self.schema_version,
            "spec": _plain_json(self.semantic),
            "evidence": [item.to_dict() for item in self.evidence],
            "reference_context": [item.to_dict() for item in self.reference_context],
        }

    def audit_dict(self) -> dict[str, object]:
        """Return request/spec lineage separately from the model-facing payload."""

        return {
            "request_id": self.request_id,
            "spec_id": self.spec_id,
            "spec_digest": self.spec_digest,
            "spec_audit_lineage": _plain_json(self.spec_audit_lineage),
        }

    def to_dict(self) -> dict[str, object]:
        """Return both projections with an explicit boundary between them."""

        return {"model_input": self.to_model_input(), "audit": self.audit_dict()}


def _as_bounded_sequence(
    value: object,
    label: str,
    reason: FinalizationInputFailureReason,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _error(reason, f"{label} must be a finite sequence")
    return tuple(value)


def _canonicalize_evidence(
    spec: ResolvedCharacterGenerationSpecV1,
    evidence: Sequence[BoundedGenerationEvidenceV1],
) -> tuple[BoundedGenerationEvidenceV1, ...]:
    if len(evidence) > _MAX_EVIDENCE_SOURCES:
        raise _error(
            FinalizationInputFailureReason.EVIDENCE_LIMIT_EXCEEDED,
            "evidence source count exceeds the finalization input limit",
        )

    policy = spec.field_authorization_policy
    values_by_source: dict[str, dict[CharacterGenerationField, dict[str, Any]]] = {}
    source_types: dict[str, str] = {}
    evidence_fact_count = 0
    for item in evidence:
        if not isinstance(item, BoundedGenerationEvidenceV1):
            raise _error(
                FinalizationInputFailureReason.INVALID_EVIDENCE,
                "evidence must use the bounded domain DTO",
            )
        existing_type = source_types.setdefault(item.source_id, item.source_type)
        if existing_type != item.source_type:
            raise _error(
                FinalizationInputFailureReason.INVALID_EVIDENCE,
                "one evidence source ID has conflicting source types",
            )
        per_source = values_by_source.setdefault(item.source_id, {})
        for field_value, values in item.field_values.items():
            evidence_fact_count += len(values)
            if evidence_fact_count > _MAX_EVIDENCE_FACTS:
                raise _error(
                    FinalizationInputFailureReason.EVIDENCE_LIMIT_EXCEEDED,
                    "evidence fact count exceeds the finalization input limit",
                )
            authorization = policy.for_field(field_value)
            if (
                authorization.state is not FieldAuthorizationState.CANON_GROUNDED_ONLY
                or item.source_id not in authorization.authorized_source_ids
            ):
                raise _error(
                    FinalizationInputFailureReason.UNAUTHORIZED_EVIDENCE_SOURCE,
                    "evidence source is not authorized for its declared field",
                )
            allowed = {_canonical_json(value) for value in authorization.allowed_exact_values}
            field_values = per_source.setdefault(field_value, {})
            for value in values:
                key = _canonical_json(value)
                if key not in allowed:
                    raise _error(
                        FinalizationInputFailureReason.UNAUTHORIZED_EVIDENCE_VALUE,
                        "evidence value is not one of the spec-authorized exact values",
                    )
                field_values[key] = value

    merged: list[BoundedGenerationEvidenceV1] = []
    for source_id in sorted(values_by_source):
        field_values = {
            field_value: tuple(values[key] for key in sorted(values))
            for field_value, values in values_by_source[source_id].items()
        }
        merged.append(
            BoundedGenerationEvidenceV1(
                source_id=source_id,
                source_type=source_types[source_id],
                field_values=field_values,
            )
        )

    for field_value, authorization in policy.field_authorizations.items():
        if authorization.state is not FieldAuthorizationState.CANON_GROUNDED_ONLY:
            continue
        available_values = {
            _canonical_json(value)
            for item in merged
            for value in item.field_values.get(field_value, ())
        }
        authorized_values = {
            _canonical_json(value) for value in authorization.allowed_exact_values
        }
        if not available_values.intersection(authorized_values):
            raise _error(
                FinalizationInputFailureReason.MISSING_CANON_VALUE_AUTHORITY,
                "Canon-grounded field has no usable exact-value evidence",
            )
    return tuple(merged)


def _reference_allowlist(
    semantic: Mapping[str, Any],
) -> dict[str, str | None]:
    reference_basis = semantic.get("bounded_reference_precedent")
    if not isinstance(reference_basis, Mapping):
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec has no bounded reference precedent projection",
        )
    provenance = reference_basis.get("provenance", ())
    if isinstance(provenance, (str, bytes)) or not isinstance(provenance, Sequence):
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec reference provenance is not a bounded sequence",
        )

    allowed: dict[str, str | None] = {}
    for item in provenance:
        if not isinstance(item, Mapping):
            raise _error(
                FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
                "spec reference provenance contains an invalid entry",
            )
        reference_id = item.get("source_reference_id")
        if reference_id is None:
            continue
        if not isinstance(reference_id, str) or not reference_id.strip():
            raise _error(
                FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
                "spec reference provenance contains an invalid reference ID",
            )
        display_name = item.get("source_display_name")
        if display_name is not None and not isinstance(display_name, str):
            raise _error(
                FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
                "spec reference provenance contains an invalid display name",
            )
        normalized_id = reference_id.strip()
        normalized_name = display_name.strip() if display_name else None
        if normalized_id in allowed and allowed[normalized_id] != normalized_name:
            raise _error(
                FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
                "spec has conflicting display names for one reference ID",
            )
        allowed[normalized_id] = normalized_name
    return allowed


def _canonicalize_references(
    semantic: Mapping[str, Any],
    references: Sequence[AllowedReferenceContextV1],
) -> tuple[AllowedReferenceContextV1, ...]:
    if len(references) > _MAX_REFERENCE_CONTEXTS:
        raise _error(
            FinalizationInputFailureReason.REFERENCE_LIMIT_EXCEEDED,
            "reference context count exceeds the planning-context limit",
        )
    allowed = _reference_allowlist(semantic)
    selected: dict[str, AllowedReferenceContextV1] = {}
    for item in references:
        if not isinstance(item, AllowedReferenceContextV1):
            raise _error(
                FinalizationInputFailureReason.INVALID_REFERENCE_CONTEXT,
                "references must use the bounded domain DTO",
            )
        if item.reference_id not in allowed:
            raise _error(
                FinalizationInputFailureReason.INVALID_REFERENCE_CONTEXT,
                "reference ID is not authorized by the frozen spec",
            )
        expected_name = allowed[item.reference_id]
        if expected_name is not None and item.display_name != expected_name:
            raise _error(
                FinalizationInputFailureReason.INVALID_REFERENCE_CONTEXT,
                "reference display name conflicts with spec provenance",
            )
        previous = selected.setdefault(item.reference_id, item)
        if previous != item:
            raise _error(
                FinalizationInputFailureReason.INVALID_REFERENCE_CONTEXT,
                "duplicate reference ID has conflicting bounded context",
            )
    return tuple(selected[key] for key in sorted(selected))


def build_character_finalization_input(
    spec: ResolvedCharacterGenerationSpecV1,
    *,
    evidence: Sequence[BoundedGenerationEvidenceV1] = (),
    reference_context: Sequence[AllowedReferenceContextV1] = (),
) -> CharacterFinalizationInputV1:
    """Project a frozen spec and its authorized bounded context into V1 input.

    The caller must pass a Slice 1-validated spec. This adapter checks only
    cross-contract evidence/reference consistency and never reruns the spec or
    field-authorization validators.
    """

    # Keep consumers of the immutable B1B value free of the Planner's legacy
    # import closure; only the construction adapter needs the concrete spec.
    from .planner.character_generation_spec import ResolvedCharacterGenerationSpecV1

    if not isinstance(spec, ResolvedCharacterGenerationSpecV1):
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec must be ResolvedCharacterGenerationSpecV1",
        )
    evidence_items = _as_bounded_sequence(
        evidence, "evidence", FinalizationInputFailureReason.INVALID_EVIDENCE
    )
    reference_items = _as_bounded_sequence(
        reference_context,
        "reference_context",
        FinalizationInputFailureReason.INVALID_REFERENCE_CONTEXT,
    )

    semantic = spec.to_model_input()
    if not isinstance(semantic, Mapping):
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec semantic projection must be a mapping",
        )
    semantic = dict(semantic)
    request_id = semantic.pop("request_id", None)
    if not isinstance(request_id, str) or not request_id.strip():
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec semantic projection has no request identity",
        )

    # INVARIANT: the concept identity remains in the spec audit lineage; the
    # Generator receives only the resolved direction, never seed identity.
    direction = semantic.get("resolved_direction")
    if not isinstance(direction, Mapping) or "concept_id" not in direction:
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "spec has no resolved direction with a separated seed identity",
        )
    semantic["resolved_direction"] = {
        key: value for key, value in direction.items() if key != "concept_id"
    }

    expected_required_fields = list(spec.required_generation_fields)
    if semantic.get("required_generation_fields") != expected_required_fields:
        raise _error(
            FinalizationInputFailureReason.SPEC_INPUT_MISMATCH,
            "required fields differ from the frozen spec",
        )

    canonical_evidence = _canonicalize_evidence(spec, evidence_items)
    canonical_references = _canonicalize_references(semantic, reference_items)
    return CharacterFinalizationInputV1(
        semantic=semantic,
        evidence=canonical_evidence,
        reference_context=canonical_references,
        request_id=request_id,
        spec_id=spec.spec_id,
        spec_digest=spec.spec_digest,
        spec_audit_lineage=spec.audit_dict(),
    )


__all__ = [
    "AllowedReferenceContextV1",
    "BoundedGenerationEvidenceV1",
    "CHARACTER_FINALIZATION_INPUT_V1_SCHEMA",
    "CharacterFinalizationInputV1",
    "FinalizationInputError",
    "FinalizationInputFailureReason",
    "build_character_finalization_input",
]
