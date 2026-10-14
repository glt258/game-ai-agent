"""Shared, provider-independent field authorization semantics.

This module is deliberately smaller than either the Planner or the Generator.
It defines the vocabulary and authority rules that later adapters may project
into a generation spec, a prompt, or a validator.  It never reads Planner
objects, retrieval transcripts, provider output, or CharacterDraft instances.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


class FieldAuthorizationErrorCode(str, Enum):
    """Finite failure reasons for the shared authorization contract."""

    INVALID_FIELD = "INVALID_FIELD"
    INVALID_SOURCE_ID = "INVALID_SOURCE_ID"
    INVALID_EXACT_VALUE = "INVALID_EXACT_VALUE"
    INVALID_POLICY = "INVALID_POLICY"
    AUTHORIZATION_CONFLICT = "AUTHORIZATION_CONFLICT"
    CANON_AUTHORITY_REQUIRED = "CANON_AUTHORITY_REQUIRED"
    UNAUTHORIZED_SOURCE_ID = "UNAUTHORIZED_SOURCE_ID"
    UNAUTHORIZED_EXACT_VALUE = "UNAUTHORIZED_EXACT_VALUE"
    INVALID_MARKER = "INVALID_MARKER"
    UNKNOWN_MARKER_FIELD = "UNKNOWN_MARKER_FIELD"


class FieldAuthorizationError(ValueError):
    """Fail-closed error raised for an invalid field authorization contract."""

    def __init__(self, code: FieldAuthorizationErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class CharacterGenerationField(str, Enum):
    """The bounded CharacterDraft fields governed by Canon/design authority."""

    OCCUPATION = "occupation"
    SOCIAL_ROLE = "social_role"
    DESIGN_PITCH = "design_pitch"
    PERSONALITY = "personality"
    BACKGROUND = "background"
    STORY_HOOK = "story_hook"
    ABILITY_CONCEPT = "ability_concept"
    KNOWLEDGE_SCOPE = "knowledge_scope"


CHARACTER_GENERATION_FIELDS: tuple[CharacterGenerationField, ...] = tuple(
    CharacterGenerationField
)


class FieldAuthorizationState(str, Enum):
    """The only three authority states a governed generation field may have."""

    NEW_DESIGN_AUTHORIZED = "NEW_DESIGN_AUTHORIZED"
    CANON_GROUNDED_ONLY = "CANON_GROUNDED_ONLY"
    UNAUTHORIZED = "UNAUTHORIZED"


_MARKER_PATTERN = re.compile(
    r"^new_design:(?P<field>[A-Za-z_][A-Za-z0-9_.]*)(?::|$)"
)
_MARKER_PREFIX = "new_design:"


def _field(value: CharacterGenerationField | str) -> CharacterGenerationField:
    if isinstance(value, CharacterGenerationField):
        return value
    if isinstance(value, str):
        try:
            return CharacterGenerationField(value.strip())
        except ValueError:
            pass
    raise FieldAuthorizationError(
        FieldAuthorizationErrorCode.INVALID_FIELD,
        f"unknown character generation field: {value!r}",
    )


def _field_label(value: CharacterGenerationField | str) -> str:
    return value.value if isinstance(value, CharacterGenerationField) else value


def _source_ids(
    value: Iterable[str], *, field: CharacterGenerationField | str
) -> tuple[str, ...]:
    field_label = _field_label(field)
    if isinstance(value, (str, bytes, Mapping)):
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
            f"source IDs for {field_label!r} must be a collection, not text",
        )
    normalized: set[str] = set()
    try:
        items = tuple(value)
    except TypeError as error:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
            f"source IDs for {field_label!r} must be iterable",
        ) from error
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_SOURCE_ID,
                f"source IDs for {field_label!r} must be non-empty strings",
            )
        normalized.add(item.strip())
    return tuple(sorted(normalized))


def _freeze_json(
    value: Any, *, field: CharacterGenerationField | str
) -> Any:
    """Detach nested caller data while preserving JSON value semantics.

    Exact Canon values may be strings, arrays, or objects.  Mapping keys are
    sorted because object order is not semantic; array order is preserved
    because it can be semantic for fields such as ``personality``.
    """

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
                f"exact value for {_field_label(field)!r} is not finite",
            )
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
                    f"exact value object keys for {_field_label(field)!r} must be strings",
                )
            frozen[key] = _freeze_json(item, field=field)
        return MappingProxyType(
            {key: frozen[key] for key in sorted(frozen)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, field=field) for item in value)
    raise FieldAuthorizationError(
        FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
        f"unsupported exact value type for {_field_label(field)!r}: {type(value).__name__}",
    )


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _exact_key(value: Any) -> str:
    return json.dumps(
        _plain_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _exact_values(
    value: Iterable[Any], *, field: CharacterGenerationField | str
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
            f"exact values for {_field_label(field)!r} must be a collection",
        )
    try:
        frozen = tuple(_freeze_json(item, field=field) for item in value)
    except TypeError as error:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_EXACT_VALUE,
            f"exact values for {_field_label(field)!r} must be iterable",
        ) from error
    unique = {_exact_key(item): item for item in frozen}
    return tuple(unique[key] for key in sorted(unique))


@dataclass(frozen=True)
class CanonFieldEvidenceAuthority:
    """Normalized evidence metadata for one Canon-grounded field.

    Only source identity and optional exact choices cross this boundary.
    Full Canon payloads, tool observations, and provider audit data remain in
    their owning adapters.
    """

    authorized_source_ids: tuple[str, ...]
    allowed_exact_values: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        field = "Canon evidence"
        object.__setattr__(
            self,
            "authorized_source_ids",
            _source_ids(self.authorized_source_ids, field=field),
        )
        if not self.authorized_source_ids:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.CANON_AUTHORITY_REQUIRED,
                "Canon evidence authority requires at least one source ID",
            )
        object.__setattr__(
            self,
            "allowed_exact_values",
            _exact_values(self.allowed_exact_values, field=field),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CanonFieldEvidenceAuthority":
        """Build evidence metadata from the bounded, payload-free mapping shape."""

        if not isinstance(value, Mapping):
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                "Canon evidence authority must be a mapping",
            )
        allowed = {"authorized_source_ids", "allowed_exact_values"}
        unknown = set(value) - allowed
        if unknown:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                f"unknown Canon evidence authority keys: {sorted(unknown)!r}",
            )
        return cls(
            value.get("authorized_source_ids", ()),
            value.get("allowed_exact_values", ()),
        )


@dataclass(frozen=True)
class FieldAuthorization:
    """Immutable authority decision for one bounded generation field."""

    field: CharacterGenerationField
    state: FieldAuthorizationState
    authorized_source_ids: tuple[str, ...] = ()
    allowed_exact_values: tuple[Any, ...] = ()
    requires_grounding: bool = False

    def __post_init__(self) -> None:
        field = _field(self.field)
        try:
            state = (
                self.state
                if isinstance(self.state, FieldAuthorizationState)
                else FieldAuthorizationState(self.state)
            )
        except (TypeError, ValueError) as error:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                f"invalid authorization state for {field.value!r}",
            ) from error
        source_ids = _source_ids(self.authorized_source_ids, field=field)
        exact_values = _exact_values(self.allowed_exact_values, field=field)
        if state is FieldAuthorizationState.CANON_GROUNDED_ONLY and not source_ids:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.CANON_AUTHORITY_REQUIRED,
                f"Canon-grounded field {field.value!r} requires source IDs",
            )
        if state is not FieldAuthorizationState.CANON_GROUNDED_ONLY and source_ids:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
                f"field {field.value!r} cannot carry Canon source IDs in state {state.value!r}",
            )
        if state is not FieldAuthorizationState.CANON_GROUNDED_ONLY and exact_values:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.UNAUTHORIZED_EXACT_VALUE,
                f"field {field.value!r} cannot carry exact values in state {state.value!r}",
            )
        expected_grounding = state is FieldAuthorizationState.CANON_GROUNDED_ONLY
        if self.requires_grounding != expected_grounding:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                f"requires_grounding contradicts state for {field.value!r}",
            )
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "authorized_source_ids", source_ids)
        object.__setattr__(self, "allowed_exact_values", exact_values)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh, deterministic domain serialization."""

        return {
            "field": self.field.value,
            "state": self.state.value,
            "authorized_source_ids": list(self.authorized_source_ids),
            "allowed_exact_values": [_plain_json(item) for item in self.allowed_exact_values],
            "requires_grounding": self.requires_grounding,
        }


@dataclass(frozen=True)
class FieldAuthorizationPolicy:
    """Complete immutable authorization matrix for all governed fields."""

    field_authorizations: Mapping[CharacterGenerationField, FieldAuthorization]
    schema_version: str = "character-field-authorization/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "character-field-authorization/v1":
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                f"unsupported schema version: {self.schema_version!r}",
            )
        if not isinstance(self.field_authorizations, Mapping):
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                "field_authorizations must be a mapping",
            )
        normalized: dict[CharacterGenerationField, FieldAuthorization] = {}
        for raw_field, authorization in self.field_authorizations.items():
            field = _field(raw_field)
            if not isinstance(authorization, FieldAuthorization):
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.INVALID_POLICY,
                    f"authorization for {field.value!r} has an invalid type",
                )
            if authorization.field is not field:
                raise FieldAuthorizationError(
                    FieldAuthorizationErrorCode.INVALID_POLICY,
                    f"authorization key and entry disagree for {field.value!r}",
                )
            normalized[field] = authorization
        expected = set(CHARACTER_GENERATION_FIELDS)
        if set(normalized) != expected:
            missing = sorted(item.value for item in expected - set(normalized))
            extra = sorted(item.value for item in set(normalized) - expected)
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_POLICY,
                f"authorization matrix must cover exactly all governed fields; missing={missing}, extra={extra}",
            )
        object.__setattr__(
            self,
            "field_authorizations",
            MappingProxyType(dict(normalized)),
        )

    def for_field(
        self, field: CharacterGenerationField | str
    ) -> FieldAuthorization:
        """Return the authority decision for one bounded field."""

        return self.field_authorizations[_field(field)]

    def to_dict(self) -> dict[str, Any]:
        """Return stable JSON-shaped data without exposing internal containers."""

        return {
            "schema_version": self.schema_version,
            "field_authorizations": {
                field.value: self.field_authorizations[field].to_dict()
                for field in CHARACTER_GENERATION_FIELDS
            },
        }


def build_field_authorization_policy(
    *,
    new_design_fields: Iterable[CharacterGenerationField | str] = (),
    canon_evidence: Mapping[
        CharacterGenerationField | str,
        CanonFieldEvidenceAuthority | Mapping[str, Any],
    ] | None = None,
) -> FieldAuthorizationPolicy:
    """Build a complete, deterministic, request-independent authority matrix.

    The caller supplies normalized authority metadata rather than a Planner,
    Evidence Bundle, tool transcript, or provider response.  Unmentioned
    fields become ``UNAUTHORIZED`` so omission cannot silently grant freedom.
    """

    design_fields = {_field(item) for item in new_design_fields}
    evidence_by_field: dict[CharacterGenerationField, CanonFieldEvidenceAuthority] = {}
    for raw_field, raw_authority in (canon_evidence or {}).items():
        field = _field(raw_field)
        if field in design_fields:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.AUTHORIZATION_CONFLICT,
                f"field {field.value!r} is both new-design and Canon-grounded",
            )
        authority = (
            raw_authority
            if isinstance(raw_authority, CanonFieldEvidenceAuthority)
            else CanonFieldEvidenceAuthority.from_mapping(raw_authority)
        )
        evidence_by_field[field] = authority

    authorizations: dict[CharacterGenerationField, FieldAuthorization] = {}
    for field in CHARACTER_GENERATION_FIELDS:
        if field in design_fields:
            authorizations[field] = FieldAuthorization(
                field,
                FieldAuthorizationState.NEW_DESIGN_AUTHORIZED,
            )
        elif field in evidence_by_field:
            authority = evidence_by_field[field]
            authorizations[field] = FieldAuthorization(
                field,
                FieldAuthorizationState.CANON_GROUNDED_ONLY,
                authority.authorized_source_ids,
                authority.allowed_exact_values,
                True,
            )
        else:
            authorizations[field] = FieldAuthorization(
                field,
                FieldAuthorizationState.UNAUTHORIZED,
            )
    return FieldAuthorizationPolicy(authorizations)


def encode_new_design_marker(
    field: CharacterGenerationField | str,
) -> str:
    """Encode the legacy marker form without making it the domain source of truth."""

    return f"new_design:{_field(field).value}:"


def parse_new_design_marker(value: str) -> CharacterGenerationField | None:
    """Parse one transitional marker, or return ``None`` for ordinary prose."""

    if not isinstance(value, str) or not value.strip():
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_MARKER,
            "marker must be non-empty text",
        )
    text = value.strip()
    if not text.startswith(_MARKER_PREFIX):
        return None
    match = _MARKER_PATTERN.match(text)
    if match is None:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.INVALID_MARKER,
            "marker must use new_design:<field>: syntax",
        )
    try:
        return CharacterGenerationField(match.group("field"))
    except ValueError as error:
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.UNKNOWN_MARKER_FIELD,
            f"unknown marker field: {match.group('field')!r}",
        ) from error


__all__ = [
    "CHARACTER_GENERATION_FIELDS",
    "CanonFieldEvidenceAuthority",
    "CharacterGenerationField",
    "FieldAuthorization",
    "FieldAuthorizationError",
    "FieldAuthorizationErrorCode",
    "FieldAuthorizationPolicy",
    "FieldAuthorizationState",
    "build_field_authorization_policy",
    "encode_new_design_marker",
    "parse_new_design_marker",
]
