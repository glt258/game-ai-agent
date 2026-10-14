"""Project request-scoped Project Canon facts into existing B1A/B1B inputs.

This adapter only reads explicitly selected IDs from the already-loaded
Project Canon character registry. Field bindings are code-owned and exact;
Planning Context prose, retrieval, and model output are never inspected.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .context.schema import ContextAuthority
from .field_authorization import (
    CanonFieldEvidenceAuthority,
    CharacterGenerationField,
    FieldAuthorizationError,
    FieldAuthorizationErrorCode,
    FieldAuthorizationState,
)
from .finalization_input import BoundedGenerationEvidenceV1

_MAX_REQUEST_SCOPED_SOURCES = 32
_MAX_CANON_EVIDENCE_FACTS = 64
_MAX_SOURCE_ID_LENGTH = 256
_MAX_OCCUPATION_LENGTH = 512
_MISSING = object()

# WHY: the adapter and downstream CanonChecker must use one finite mapping;
# duplicating it would let the producer and verifier silently disagree.
CANON_FIELD_PATHS: Mapping[
    CharacterGenerationField, tuple[str, ...]
] = MappingProxyType({
    CharacterGenerationField.OCCUPATION: ("basic_profile", "occupation"),
})


@dataclass(frozen=True)
class RequestScopedCanonSource:
    """One selected source's bounded structured facts and system classification."""

    source_id: str
    source_classification: ContextAuthority
    field_values: Mapping[CharacterGenerationField, Any]
    source_type: str = "project_canon_character"

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "request-scoped Canon source ID must be non-empty text",
            )
        source_id = self.source_id.strip()
        if len(source_id) > _MAX_SOURCE_ID_LENGTH:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "request-scoped Canon source ID exceeds its size limit",
            )
        if not isinstance(self.source_classification, ContextAuthority):
            raise TypeError("source_classification must use ContextAuthority")
        if not isinstance(self.field_values, Mapping):
            raise TypeError("field_values must be a mapping")
        if self.source_type != "project_canon_character":
            raise ValueError("source_type must identify a Project Canon character")

        normalized: dict[CharacterGenerationField, Any] = {}
        for field_value, value in self.field_values.items():
            if not isinstance(field_value, CharacterGenerationField):
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.INVALID_FIELD,
                    "snapshot field bindings must use CharacterGenerationField",
                )
            normalized[field_value] = value
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(
            self,
            "field_values",
            MappingProxyType(dict(sorted(normalized.items(), key=lambda item: item[0].value))),
        )


@dataclass(frozen=True)
class RequestScopedCanonSourceSnapshot:
    """Immutable, bounded snapshot containing only IDs selected for one request."""

    sources: tuple[RequestScopedCanonSource, ...] = ()

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        if any(not isinstance(item, RequestScopedCanonSource) for item in sources):
            raise TypeError("sources must contain RequestScopedCanonSource values")
        if len(sources) > _MAX_REQUEST_SCOPED_SOURCES:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "request-scoped Canon source count exceeds the B1B source limit",
            )
        source_ids = [item.source_id for item in sources]
        if len(source_ids) != len(set(source_ids)):
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "request-scoped Canon snapshot contains duplicate source IDs",
            )
        object.__setattr__(
            self,
            "sources",
            tuple(sorted(sources, key=lambda item: item.source_id)),
        )

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Return the stable source membership of this request snapshot."""

        return tuple(item.source_id for item in self.sources)


@dataclass(frozen=True)
class CanonFieldEvidenceAudit:
    """Safe authority projection; never includes a source's raw Canon record."""

    field: CharacterGenerationField
    state_candidate: FieldAuthorizationState
    source_ids: tuple[str, ...]
    exact_values: tuple[Any, ...]
    source_classification: ContextAuthority
    request_scope_source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return only the field, exact allowlist, source class, and scope proof."""

        return {
            "field": self.field.value,
            "state_candidate": self.state_candidate.value,
            "source_ids": list(self.source_ids),
            "exact_values": list(self.exact_values),
            "source_classification": self.source_classification.value,
            "request_scope_source_ids": list(self.request_scope_source_ids),
            "all_sources_in_request_scope": set(self.source_ids).issubset(
                self.request_scope_source_ids
            ),
        }


@dataclass(frozen=True)
class CanonFieldEvidenceAdapterResult:
    """B1A authority plus separate bounded B1B evidence and safe audit data."""

    authority_by_field: Mapping[
        CharacterGenerationField, CanonFieldEvidenceAuthority
    ]
    bounded_generation_evidence: tuple[BoundedGenerationEvidenceV1, ...]
    audit: tuple[CanonFieldEvidenceAudit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authority_by_field",
            MappingProxyType(dict(self.authority_by_field)),
        )
        object.__setattr__(
            self, "bounded_generation_evidence", tuple(self.bounded_generation_evidence)
        )
        object.__setattr__(self, "audit", tuple(self.audit))


def _normalize_source_ids(value: Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
            "Canon source IDs must be a collection, not text or a mapping",
        )
    try:
        items = tuple(value)
    except TypeError as error:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
            "Canon source IDs must be iterable",
        ) from error

    normalized: set[str] = set()
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "Canon source IDs must be non-empty strings",
            )
        source_id = item.strip()
        if len(source_id) > _MAX_SOURCE_ID_LENGTH:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                "Canon source ID exceeds its size limit",
            )
        normalized.add(source_id)
    source_ids = tuple(sorted(normalized))
    if len(source_ids) > _MAX_REQUEST_SCOPED_SOURCES:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
            "request-scoped Canon source count exceeds the B1B source limit",
        )
    return source_ids


def _read_path(record: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = record
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _validate_exact_field_value(
    field_value: CharacterGenerationField,
    value: Any,
) -> str:
    if field_value is not CharacterGenerationField.OCCUPATION:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_FIELD,
            f"no authoritative structured binding is defined for {field_value.value!r}",
        )
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_OCCUPATION_LENGTH
    ):
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
            "Project Canon occupation must be non-empty bounded text",
        )
    # Preserve the stored value exactly; validation must not rewrite authority.
    return value


def build_request_scoped_canon_source_snapshot(
    project_canon_records: Mapping[str, Any],
    source_ids: Iterable[str],
) -> RequestScopedCanonSourceSnapshot:
    """Select exact IDs from the loaded Project Canon character registry.

    The caller provides IDs, not values or classifications. Exact dictionary
    lookups avoid turning the global registry into the request's authority set.
    """

    if not isinstance(project_canon_records, Mapping):
        raise TypeError("project_canon_records must be the loaded character registry")
    selected_ids = _normalize_source_ids(source_ids)
    selected: list[RequestScopedCanonSource] = []
    for source_id in selected_ids:
        record = project_canon_records.get(source_id)
        if not isinstance(record, Mapping) or record.get("id") != source_id:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
                f"source {source_id!r} is not a matching Project Canon character record",
            )

        field_values: dict[CharacterGenerationField, str] = {}
        for field_value, path in CANON_FIELD_PATHS.items():
            value = _read_path(record, path)
            if value is not _MISSING:
                field_values[field_value] = _validate_exact_field_value(field_value, value)
        selected.append(
            RequestScopedCanonSource(
                source_id=source_id,
                source_classification=ContextAuthority.PROJECT_CANON,
                field_values=field_values,
            )
        )
    return RequestScopedCanonSourceSnapshot(tuple(selected))


def adapt_request_scoped_canon_field_evidence(
    snapshot: RequestScopedCanonSourceSnapshot,
    field_source_ids: Mapping[
        CharacterGenerationField | str,
        Iterable[str],
    ],
) -> CanonFieldEvidenceAdapterResult:
    """Project scoped structured facts into B1A authority and bounded B1B facts."""

    if not isinstance(snapshot, RequestScopedCanonSourceSnapshot):
        raise TypeError("snapshot must be RequestScopedCanonSourceSnapshot")
    if not isinstance(field_source_ids, Mapping):
        raise TypeError("field_source_ids must be a mapping")

    normalized_sources: dict[CharacterGenerationField, tuple[str, ...]] = {}
    for raw_field, raw_ids in field_source_ids.items():
        try:
            field_value = (
                raw_field
                if isinstance(raw_field, CharacterGenerationField)
                else CharacterGenerationField(raw_field)
            )
        except (TypeError, ValueError) as error:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_FIELD,
                f"unknown Canon-grounded field: {raw_field!r}",
            ) from error
        if field_value in normalized_sources:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_FIELD,
                f"duplicate Canon-grounded field: {field_value.value!r}",
            )
        if field_value not in CANON_FIELD_PATHS:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_FIELD,
                f"no authoritative structured binding is defined for {field_value.value!r}",
            )
        ids = _normalize_source_ids(raw_ids)
        if not ids:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.CANON_AUTHORITY_REQUIRED,
                f"Canon-grounded field {field_value.value!r} requires a source ID",
            )
        normalized_sources[field_value] = ids

    requested_scope = tuple(
        sorted({source_id for ids in normalized_sources.values() for source_id in ids})
    )
    if requested_scope != snapshot.source_ids:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
            "snapshot source membership does not exactly match this request's selected IDs",
        )
    if not normalized_sources:
        return CanonFieldEvidenceAdapterResult({}, (), ())

    sources_by_id = {item.source_id: item for item in snapshot.sources}
    authorities: dict[CharacterGenerationField, CanonFieldEvidenceAuthority] = {}
    evidence_by_source: dict[
        str, dict[CharacterGenerationField, tuple[str, ...]]
    ] = {}
    audit: list[CanonFieldEvidenceAudit] = []
    evidence_fact_count = 0

    for field_value in sorted(normalized_sources, key=lambda item: item.value):
        source_ids = normalized_sources[field_value]
        exact_values: list[str] = []
        for source_id in source_ids:
            source = sources_by_id.get(source_id)
            if source is None:
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
                    f"source {source_id!r} is outside the request-scoped Canon snapshot",
                )
            if source.source_classification is not ContextAuthority.PROJECT_CANON:
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
                    f"source {source_id!r} is not classified as PROJECT_CANON",
                )
            raw_value = source.field_values.get(field_value, _MISSING)
            if raw_value is _MISSING:
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
                    f"source {source_id!r} has no structured {field_value.value!r} value",
                )
            exact_value = _validate_exact_field_value(field_value, raw_value)
            exact_values.append(exact_value)
            evidence_by_source.setdefault(source_id, {})[field_value] = (exact_value,)
            evidence_fact_count += 1

        if evidence_fact_count > _MAX_CANON_EVIDENCE_FACTS:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
                "Canon evidence fact count exceeds the B1B limit",
            )
        authority = CanonFieldEvidenceAuthority(
            authorized_source_ids=source_ids,
            allowed_exact_values=tuple(exact_values),
        )
        authorities[field_value] = authority
        audit.append(
            CanonFieldEvidenceAudit(
                field=field_value,
                state_candidate=FieldAuthorizationState.CANON_GROUNDED_ONLY,
                source_ids=source_ids,
                exact_values=authority.allowed_exact_values,
                source_classification=ContextAuthority.PROJECT_CANON,
                request_scope_source_ids=snapshot.source_ids,
            )
        )

    bounded_evidence = tuple(
        BoundedGenerationEvidenceV1(
            source_id=source_id,
            source_type=sources_by_id[source_id].source_type,
            field_values=field_values,
        )
        for source_id, field_values in sorted(evidence_by_source.items())
    )
    return CanonFieldEvidenceAdapterResult(
        authority_by_field=authorities,
        bounded_generation_evidence=bounded_evidence,
        audit=tuple(audit),
    )


__all__ = [
    "CANON_FIELD_PATHS",
    "CanonFieldEvidenceAdapterResult",
    "CanonFieldEvidenceAudit",
    "RequestScopedCanonSource",
    "RequestScopedCanonSourceSnapshot",
    "adapt_request_scoped_canon_field_evidence",
    "build_request_scoped_canon_source_snapshot",
]
