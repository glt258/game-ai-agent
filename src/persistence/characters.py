"""SQLite adapter for durable Character identities and revisions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from agents.character_generation import CharacterDraft
from agents.errors import ModelMalformedResponseError
from agents.response_contracts import CHARACTER_DRAFT_JSON_SCHEMA

from .errors import (
    CharacterNotFoundError,
    CharacterRevisionConflictError,
    CharacterRevisionNotFoundError,
    PersistenceContractUnsupportedError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceWriteConflictError,
)

CHARACTER_REVISION_CONTRACT_VERSION = "character-revision/0.1.0"
RevisionKind = Literal["GENERATED", "EDITED"]
REVISION_KINDS = frozenset({"GENERATED", "EDITED"})
_PERSISTED_FIELDS = frozenset(CHARACTER_DRAFT_JSON_SCHEMA["properties"]) - {
    "draft_id",
    "status",
}


@dataclass(frozen=True)
class CharacterRevision:
    revision_id: str
    character_id: str
    revision_contract_version: str
    kind: RevisionKind
    parent_revision_id: str | None
    draft: CharacterDraft
    created_at: str


@dataclass(frozen=True)
class CharacterRevisionSummary:
    revision_id: str
    kind: RevisionKind
    parent_revision_id: str | None
    created_at: str
    is_current: bool


@dataclass(frozen=True)
class PersistedCharacter:
    character_id: str
    current_revision_id: str
    created_at: str
    updated_at: str
    current_revision: CharacterRevision


@dataclass(frozen=True)
class SavedCharacterSummary:
    character_id: str
    display_name: str
    current_revision_id: str
    revision_kind: RevisionKind
    created_at: str
    updated_at: str
    has_kit: bool
    skill_count: int


class CharacterRepository:
    """Deep adapter for Character identity, immutable revisions, and lineage."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, draft: CharacterDraft) -> PersistedCharacter:
        payload_json = self._validated_payload_json(draft)
        character_id = str(uuid.uuid4())
        revision_id = str(uuid.uuid4())
        created_at = _utc_now()
        self._connection.execute("SAVEPOINT create_character")
        try:
            self._connection.execute(
                """
                INSERT INTO characters (
                    character_id, current_revision_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (character_id, revision_id, created_at, created_at),
            )
            self._connection.execute(
                """
                INSERT INTO character_revisions (
                revision_id, character_id, revision_contract_version,
                    revision_kind, parent_revision_id, revision_sequence,
                    character_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    character_id,
                    CHARACTER_REVISION_CONTRACT_VERSION,
                    "GENERATED",
                    None,
                    1,
                    payload_json,
                    created_at,
                ),
            )
            self._connection.execute("RELEASE SAVEPOINT create_character")
        except PersistenceError:
            self._rollback_savepoint("create_character")
            raise
        except sqlite3.IntegrityError as error:
            self._rollback_savepoint("create_character")
            raise PersistenceWriteConflictError(
                "Character creation conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            self._rollback_savepoint("create_character")
            raise PersistenceIntegrityError("SQLite Character creation failed") from error
        return self.get_character(character_id)

    def append_revision(
        self,
        character_id: str,
        draft: CharacterDraft,
        *,
        expected_current_revision_id: str,
        revision_kind: RevisionKind = "EDITED",
    ) -> CharacterRevision:
        if revision_kind not in REVISION_KINDS:
            raise ValueError("revision_kind must be GENERATED or EDITED")
        payload_json = self._validated_payload_json(draft)
        character = self._character_row(character_id)
        current_revision_id = character["current_revision_id"]
        if current_revision_id != expected_current_revision_id:
            raise CharacterRevisionConflictError(
                expected_current_revision_id,
                current_revision_id,
            )
        current_row = self._revision_row(character_id, current_revision_id, required=True)
        if current_row["character_payload_json"] == payload_json:
            return self._revision_from_row(current_row)

        revision_id = str(uuid.uuid4())
        created_at = _utc_now()
        revision_sequence = self._next_revision_sequence(character_id)
        self._connection.execute("SAVEPOINT append_character_revision")
        try:
            self._connection.execute(
                """
                INSERT INTO character_revisions (
                revision_id, character_id, revision_contract_version,
                    revision_kind, parent_revision_id, revision_sequence,
                    character_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    character_id,
                    CHARACTER_REVISION_CONTRACT_VERSION,
                    revision_kind,
                    expected_current_revision_id,
                    revision_sequence,
                    payload_json,
                    created_at,
                ),
            )
            try:
                updated = self._connection.execute(
                    """
                    UPDATE characters
                    SET current_revision_id = ?, updated_at = ?
                    WHERE character_id = ? AND current_revision_id = ?
                    """,
                    (revision_id, created_at, character_id, expected_current_revision_id),
                )
            except sqlite3.DatabaseError as error:
                raise PersistenceIntegrityError(
                    "current Character revision pointer update failed"
                ) from error
            if updated.rowcount != 1:
                current = self._character_row(character_id)["current_revision_id"]
                raise CharacterRevisionConflictError(expected_current_revision_id, current)
            self._connection.execute("RELEASE SAVEPOINT append_character_revision")
        except PersistenceError:
            self._rollback_savepoint("append_character_revision")
            raise
        except sqlite3.IntegrityError as error:
            self._rollback_savepoint("append_character_revision")
            raise PersistenceWriteConflictError(
                "Character revision conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            self._rollback_savepoint("append_character_revision")
            raise PersistenceIntegrityError("SQLite Character revision write failed") from error
        return self.get_revision(character_id, revision_id)

    def get_character(self, character_id: str) -> PersistedCharacter:
        row = self._character_row(character_id)
        current_revision = self._revision_row(
            character_id,
            row["current_revision_id"],
            required=True,
        )
        return PersistedCharacter(
            character_id=row["character_id"],
            current_revision_id=row["current_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            current_revision=self._revision_from_row(current_revision),
        )

    def get_current_revision(self, character_id: str) -> CharacterRevision:
        return self.get_character(character_id).current_revision

    def get_revision(self, character_id: str, revision_id: str) -> CharacterRevision:
        return self._revision_from_row(self._revision_row(character_id, revision_id, required=True))

    def list_revisions(self, character_id: str) -> tuple[CharacterRevisionSummary, ...]:
        character = self._character_row(character_id)
        rows = self._connection.execute(
            """
            SELECT revision_id, revision_kind, parent_revision_id, created_at
            FROM character_revisions
            WHERE character_id = ?
            ORDER BY revision_sequence
            """,
            (character_id,),
        ).fetchall()
        return tuple(
            CharacterRevisionSummary(
                revision_id=row["revision_id"],
                kind=row["revision_kind"],
                parent_revision_id=row["parent_revision_id"],
                created_at=row["created_at"],
                is_current=row["revision_id"] == character["current_revision_id"],
            )
            for row in rows
        )

    def exists(self, character_id: str) -> bool:
        return self._character_row(character_id, required=False) is not None

    def list_summaries(self) -> tuple[SavedCharacterSummary, ...]:
        rows = self._connection.execute(
            """
            SELECT c.character_id, c.current_revision_id, c.created_at, c.updated_at,
                   r.revision_kind, json_extract(r.character_payload_json, '$.name') AS display_name,
                   (cc.current_assignment_id IS NOT NULL) AS has_kit,
                   COUNT(a.association_id) AS skill_count
            FROM characters AS c
            JOIN character_revisions AS r ON r.revision_id = c.current_revision_id
            LEFT JOIN character_kit_current AS cc ON cc.character_id = c.character_id
            LEFT JOIN associations AS a
              ON a.character_id = c.character_id
             AND a.current_revision_id IS NOT NULL
             AND a.closed_at IS NULL
            GROUP BY c.character_id, c.current_revision_id, c.created_at, c.updated_at,
                     r.revision_kind, r.character_payload_json, cc.current_assignment_id
            ORDER BY c.updated_at DESC, c.character_id
            """
        ).fetchall()
        return tuple(
            SavedCharacterSummary(
                character_id=row["character_id"],
                display_name=row["display_name"],
                current_revision_id=row["current_revision_id"],
                revision_kind=row["revision_kind"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                has_kit=bool(row["has_kit"]),
                skill_count=int(row["skill_count"]),
            )
            for row in rows
        )

    def _character_row(self, character_id: str, *, required: bool = True) -> sqlite3.Row | None:
        row = self._connection.execute(
            """
            SELECT character_id, current_revision_id, created_at, updated_at
            FROM characters WHERE character_id = ?
            """,
            (character_id,),
        ).fetchone()
        if row is None and required:
            raise CharacterNotFoundError(f"Character {character_id} was not found")
        return row

    def _revision_row(
        self,
        character_id: str,
        revision_id: str,
        *,
        required: bool = True,
    ) -> sqlite3.Row | None:
        row = self._connection.execute(
            """
            SELECT revision_id, character_id, revision_contract_version,
                   revision_kind, parent_revision_id, revision_sequence,
                   character_payload_json, created_at
            FROM character_revisions
            WHERE character_id = ? AND revision_id = ?
            """,
            (character_id, revision_id),
        ).fetchone()
        if row is None and required:
            if not self.exists(character_id):
                raise CharacterNotFoundError(f"Character {character_id} was not found")
            raise CharacterRevisionNotFoundError(
                f"revision {revision_id} was not found for Character {character_id}"
            )
        return row

    def _next_revision_sequence(self, character_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT COALESCE(MAX(revision_sequence), 0) + 1
            FROM character_revisions WHERE character_id = ?
            """,
            (character_id,),
        ).fetchone()
        return int(row[0])

    def _revision_from_row(self, row: sqlite3.Row) -> CharacterRevision:
        contract_version = row["revision_contract_version"]
        if contract_version != CHARACTER_REVISION_CONTRACT_VERSION:
            raise PersistenceContractUnsupportedError(
                f"unsupported revision contract {contract_version}"
            )
        kind = row["revision_kind"]
        if kind not in REVISION_KINDS:
            raise PersistenceIntegrityError("revision kind is invalid")
        try:
            payload = json.loads(row["character_payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("Character payload JSON is malformed") from error
        if not isinstance(payload, Mapping):
            raise PersistenceIntegrityError("Character payload JSON must be an object")
        if _canonical_json(payload) != row["character_payload_json"]:
            raise PersistenceIntegrityError("Character payload JSON is not canonical")
        parent_revision_id = row["parent_revision_id"]
        if parent_revision_id is not None:
            parent = self._connection.execute(
                """
                SELECT character_id
                FROM character_revisions
                WHERE revision_id = ?
                """,
                (parent_revision_id,),
            ).fetchone()
            if parent is None or parent["character_id"] != row["character_id"]:
                raise PersistenceIntegrityError("revision parent does not belong to Character")
        draft = _draft_from_payload(payload, row["revision_id"])
        return CharacterRevision(
            revision_id=row["revision_id"],
            character_id=row["character_id"],
            revision_contract_version=contract_version,
            kind=kind,
            parent_revision_id=row["parent_revision_id"],
            draft=draft,
            created_at=row["created_at"],
        )

    @staticmethod
    def _validated_payload_json(draft: CharacterDraft) -> str:
        if not isinstance(draft, CharacterDraft):
            raise PersistenceIntegrityError("value is not a CharacterDraft")
        payload = dict(draft.to_dict())
        payload.pop("draft_id", None)
        payload.pop("status", None)
        if set(payload) != _PERSISTED_FIELDS:
            raise PersistenceIntegrityError("Character authored payload fields are not exact")
        _draft_from_payload(payload, "validation")
        return _canonical_json(payload)

    def _rollback_savepoint(self, name: str) -> None:
        try:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
            self._connection.execute(f"RELEASE SAVEPOINT {name}")
        except sqlite3.DatabaseError:
            self._connection.rollback()


def _draft_from_payload(payload: object, revision_id: str) -> CharacterDraft:
    if not isinstance(payload, Mapping) or set(payload) != _PERSISTED_FIELDS:
        raise PersistenceIntegrityError("Character authored payload fields are invalid")
    restored = dict(payload)
    restored["draft_id"] = f"draft_{revision_id}"
    restored["status"] = "draft"
    try:
        return CharacterDraft.from_mapping(restored)
    except (ModelMalformedResponseError, TypeError, ValueError) as error:
        raise PersistenceIntegrityError(
            "Character payload is not a valid CharacterDraft"
        ) from error


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "CHARACTER_REVISION_CONTRACT_VERSION",
    "CharacterRepository",
    "CharacterRevision",
    "CharacterRevisionSummary",
    "PersistedCharacter",
    "SavedCharacterSummary",
]
