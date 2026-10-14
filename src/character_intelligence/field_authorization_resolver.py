"""Resolve trusted internal field-authority facts into the B1A policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .field_authorization import (
    CanonFieldEvidenceAuthority,
    CharacterGenerationField,
    FieldAuthorizationError,
    FieldAuthorizationErrorCode,
    FieldAuthorizationPolicy,
    build_field_authorization_policy,
)


@dataclass(frozen=True)
class CharacterFieldAuthorizationRequest:
    """Structured internal field requests and request-scoped Canon source IDs.

    This value is accepted only at the application seam, not by the public
    Web request DTO. It carries IDs, never Canon classifications or exact
    values; the Canon adapter resolves those from the loaded Project registry.
    """

    new_design_fields: tuple[CharacterGenerationField, ...] = ()
    canon_source_ids: Mapping[
        CharacterGenerationField, tuple[str, ...]
    ] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.new_design_fields, (str, bytes, Mapping)):
            raise TypeError("new_design_fields must be a collection of B1A fields")
        requested_fields = tuple(self.new_design_fields)
        if any(not isinstance(item, CharacterGenerationField) for item in requested_fields):
            raise TypeError("new_design_fields must use CharacterGenerationField")
        if len(requested_fields) != len(set(requested_fields)):
            raise ValueError("new_design_fields must not contain duplicates")
        object.__setattr__(self, "new_design_fields", requested_fields)

        if not isinstance(self.canon_source_ids, Mapping):
            raise TypeError("canon_source_ids must be a mapping")
        source_ids_by_field: dict[CharacterGenerationField, tuple[str, ...]] = {}
        for field_value, raw_source_ids in self.canon_source_ids.items():
            if not isinstance(field_value, CharacterGenerationField):
                raise TypeError("canon_source_ids keys must use CharacterGenerationField")
            if isinstance(raw_source_ids, (str, bytes, Mapping)):
                raise TypeError("each Canon source ID value must be a collection")
            try:
                source_ids = tuple(raw_source_ids)
            except TypeError as error:
                raise TypeError("each Canon source ID value must be iterable") from error
            if not source_ids:
                raise ValueError(f"Canon field {field_value.value!r} requires source IDs")
            if any(not isinstance(item, str) or not item.strip() for item in source_ids):
                raise ValueError("Canon source IDs must be non-empty strings")
            source_ids_by_field[field_value] = tuple(
                sorted({item.strip() for item in source_ids})
            )
        object.__setattr__(
            self,
            "canon_source_ids",
            MappingProxyType(
                dict(sorted(source_ids_by_field.items(), key=lambda item: item[0].value))
            ),
        )


def resolve_character_field_authorization(
    request: CharacterFieldAuthorizationRequest | None = None,
    *,
    canon_evidence: Mapping[
        CharacterGenerationField, CanonFieldEvidenceAuthority
    ] | None = None,
) -> FieldAuthorizationPolicy:
    """Build B1A from explicit design fields and adapter-projected evidence.

    The separate evidence argument must match the IDs requested by this
    request exactly. IDs alone never authorize a field or supply a value.
    """

    if request is None:
        request = CharacterFieldAuthorizationRequest()
    if not isinstance(request, CharacterFieldAuthorizationRequest):
        raise TypeError("request must be CharacterFieldAuthorizationRequest")
    if canon_evidence is not None and not isinstance(canon_evidence, Mapping):
        raise TypeError("canon_evidence must be a mapping")
    # The policy builder accepts a wider mapping type; checks below preserve
    # this resolver's narrower request-scoped evidence contract.
    evidence: dict[
        CharacterGenerationField | str,
        CanonFieldEvidenceAuthority | Mapping[str, Any],
    ] = dict((canon_evidence or {}).items())
    if set(evidence) != set(request.canon_source_ids):
        raise FieldAuthorizationError(
            FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
            "adapter evidence fields must exactly match requested Canon fields",
        )
    for field_value, authority in evidence.items():
        if not isinstance(field_value, CharacterGenerationField):
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.INVALID_FIELD,
                "adapter evidence keys must use CharacterGenerationField",
            )
        if not isinstance(authority, CanonFieldEvidenceAuthority):
            raise TypeError("adapter evidence values must use CanonFieldEvidenceAuthority")
        if authority.authorized_source_ids != request.canon_source_ids[field_value]:
            raise FieldAuthorizationError(
                FieldAuthorizationErrorCode.UNAUTHORIZED_SOURCE_ID,
                f"adapter source IDs do not match the request for {field_value.value!r}",
            )
    return build_field_authorization_policy(
        new_design_fields=request.new_design_fields,
        canon_evidence=evidence,
    )


__all__ = [
    "CharacterFieldAuthorizationRequest",
    "resolve_character_field_authorization",
]
