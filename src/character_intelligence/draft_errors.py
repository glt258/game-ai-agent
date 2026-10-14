"""Provider-independent errors for CharacterDraft mapping."""

from __future__ import annotations

from enum import Enum


class CharacterDraftMappingReason(str, Enum):
    """Finite failure categories for draft mapping and materialization."""

    INVALID_MAPPING = "INVALID_MAPPING"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FIELD_TYPE = "INVALID_FIELD_TYPE"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"
    INVALID_NESTED_STRUCTURE = "INVALID_NESTED_STRUCTURE"
    INVALID_CANON_BASIS = "INVALID_CANON_BASIS"
    INVALID_RELATIONSHIP = "INVALID_RELATIONSHIP"
    INVALID_COMBAT_ROLE = "INVALID_COMBAT_ROLE"
    INVALID_DOMAIN_CONSTRUCTION = "INVALID_DOMAIN_CONSTRUCTION"


class CharacterDraftMappingError(ValueError):
    """A neutral, bounded failure to parse or materialize a CharacterDraft.

    The exception carries only a finite reason, an optional field path, and a
    safe diagnostic. Provider responses, prompts, runtime audits, and recovery
    state belong to their respective adapters and must not be attached here.
    """

    def __init__(
        self,
        reason: CharacterDraftMappingReason,
        detail: str,
        *,
        field_path: str | None = None,
    ) -> None:
        self.reason = reason
        self.field_path = field_path
        self.detail = detail
        super().__init__(detail)
