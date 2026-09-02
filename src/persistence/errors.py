"""Stable errors exposed by the persistence adapters."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for safe, provider-independent persistence failures."""

    code = "PERSISTENCE_ERROR"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"{self.code}: {detail}")


class PersistenceSchemaUnsupportedError(PersistenceError):
    code = "PERSISTENCE_SCHEMA_UNSUPPORTED"


class PersistenceRecordNotFoundError(PersistenceError):
    code = "PERSISTENCE_RECORD_NOT_FOUND"


class PersistenceIntegrityError(PersistenceError):
    code = "PERSISTENCE_INTEGRITY_ERROR"


class PersistenceContractUnsupportedError(PersistenceError):
    code = "PERSISTENCE_CONTRACT_UNSUPPORTED"


class PersistenceWriteConflictError(PersistenceError):
    code = "PERSISTENCE_WRITE_CONFLICT"


class CharacterNotFoundError(PersistenceRecordNotFoundError):
    """Raised when a durable Character identity is unavailable."""


class CharacterRevisionNotFoundError(PersistenceRecordNotFoundError):
    """Raised when a revision is unavailable for the requested Character."""


class CharacterRevisionConflictError(PersistenceWriteConflictError):
    """Raised when an edit is based on a stale current revision."""

    def __init__(self, expected_revision_id: str, current_revision_id: str) -> None:
        self.expected_revision_id = expected_revision_id
        self.current_revision_id = current_revision_id
        super().__init__(
            "current revision changed "
            f"(expected={expected_revision_id}, current={current_revision_id})"
        )


class CharacterSkillPersistenceConflictError(PersistenceWriteConflictError):
    """Raised when Character or current Kit state is stale for a mutation."""

    def __init__(self, resource: str, expected: str | None, current: str | None) -> None:
        self.resource = resource
        self.expected = expected
        self.current = current
        super().__init__(f"{resource} changed (expected={expected}, current={current})")


__all__ = [
    "PersistenceContractUnsupportedError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "PersistenceRecordNotFoundError",
    "PersistenceSchemaUnsupportedError",
    "PersistenceWriteConflictError",
    "CharacterNotFoundError",
    "CharacterRevisionNotFoundError",
    "CharacterRevisionConflictError",
    "CharacterSkillPersistenceConflictError",
]
