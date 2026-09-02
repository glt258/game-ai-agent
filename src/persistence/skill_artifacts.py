"""SQLite adapter for immutable SkillDesignArtifact records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from character_intelligence.skill_artifact import (
    ArtifactContractError,
    SkillDesignArtifact,
)

from .errors import (
    PersistenceContractUnsupportedError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceRecordNotFoundError,
    PersistenceWriteConflictError,
)


@dataclass(frozen=True)
class StoredSkillArtifactContent:
    """Storage metadata for one deduplicated canonical artifact content row."""

    content_id: int
    artifact_digest: str
    canonical_schema_version: str
    canonical_artifact_json: str
    created_at: str


@dataclass(frozen=True)
class StoredSkillArtifact:
    """Storage metadata plus the restored domain artifact."""

    record_id: int
    content_id: int
    artifact_digest: str
    artifact: SkillDesignArtifact
    created_at: str


class SkillArtifactRepository:
    """Deep adapter for saving and restoring verified Skill artifacts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, artifact: SkillDesignArtifact) -> StoredSkillArtifact:
        """Persist one envelope, deduplicating only canonical content."""

        envelope_json, canonical_json = self._validated_payload(artifact)
        created_at = _utc_now()
        try:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO skill_artifact_contents (
                    artifact_digest,
                    canonical_schema_version,
                    canonical_artifact_json,
                    created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    artifact.artifact_digest,
                    artifact.identity.canonical_schema_version,
                    canonical_json,
                    created_at,
                ),
            )
            content = self._content_row(artifact.artifact_digest)
            if content["canonical_artifact_json"] != canonical_json:
                raise PersistenceIntegrityError("canonical content conflicts with artifact_digest")

            self._connection.execute(
                """
                INSERT OR IGNORE INTO skill_artifact_records (
                    content_id,
                    artifact_digest,
                    artifact_contract_version,
                    semantic_source_digest,
                    artifact_envelope_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    content["content_id"],
                    artifact.artifact_digest,
                    artifact.artifact_contract_version,
                    artifact.semantic_source_digest,
                    envelope_json,
                    created_at,
                ),
            )
            row = self._connection.execute(
                """
                SELECT record_id, content_id, artifact_digest, artifact_envelope_json, created_at
                FROM skill_artifact_records
                WHERE artifact_digest = ? AND artifact_envelope_json = ?
                """,
                (artifact.artifact_digest, envelope_json),
            ).fetchone()
            if row is None:
                raise PersistenceWriteConflictError("artifact record was not retained")
            return self._restore(row, content)
        except PersistenceError:
            raise
        except sqlite3.IntegrityError as error:
            raise PersistenceWriteConflictError(
                "artifact record conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            raise PersistenceIntegrityError("SQLite artifact write failed") from error

    def get(self, record_id: int) -> StoredSkillArtifact:
        if isinstance(record_id, bool) or not isinstance(record_id, int):
            raise TypeError("record_id must be an integer")
        row = self._connection.execute(
            """
            SELECT record_id, content_id, artifact_digest, artifact_envelope_json, created_at
            FROM skill_artifact_records
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            raise PersistenceRecordNotFoundError(f"artifact record {record_id} was not found")
        return self._restore(row, self._content_row(row["artifact_digest"]))

    def find_by_digest(self, artifact_digest: str) -> tuple[StoredSkillArtifact, ...]:
        rows = self._connection.execute(
            """
            SELECT record_id, content_id, artifact_digest, artifact_envelope_json, created_at
            FROM skill_artifact_records
            WHERE artifact_digest = ?
            ORDER BY record_id
            """,
            (artifact_digest,),
        ).fetchall()
        content = self._content_row(artifact_digest, required=False)
        if content is None:
            if rows:
                raise PersistenceIntegrityError("artifact records reference missing content")
            return ()
        return tuple(self._restore(row, content) for row in rows)

    def get_content(self, artifact_digest: str) -> StoredSkillArtifactContent:
        row = self._content_row(artifact_digest)
        return StoredSkillArtifactContent(
            content_id=row["content_id"],
            artifact_digest=row["artifact_digest"],
            canonical_schema_version=row["canonical_schema_version"],
            canonical_artifact_json=row["canonical_artifact_json"],
            created_at=row["created_at"],
        )

    def exists(self, artifact_digest: str) -> bool:
        return self._content_row(artifact_digest, required=False) is not None

    def _validated_payload(self, artifact: SkillDesignArtifact) -> tuple[str, str]:
        if not isinstance(artifact, SkillDesignArtifact):
            raise PersistenceIntegrityError("value is not a SkillDesignArtifact")
        mapping = artifact.to_mapping()
        try:
            restored = SkillDesignArtifact.from_mapping(mapping)
        except ArtifactContractError as error:
            if "UNSUPPORTED" in error.code:
                raise PersistenceContractUnsupportedError(error.code) from error
            raise PersistenceIntegrityError(error.code) from error
        if restored != artifact:
            raise PersistenceIntegrityError("artifact mapping is not a stable round trip")
        envelope_json = _canonical_json(mapping)
        canonical_json = artifact.canonical_artifact.canonical_json()
        return envelope_json, canonical_json

    def _content_row(self, artifact_digest: str, *, required: bool = True) -> sqlite3.Row | None:
        row = self._connection.execute(
            """
            SELECT content_id, artifact_digest, canonical_schema_version,
                   canonical_artifact_json, created_at
            FROM skill_artifact_contents
            WHERE artifact_digest = ?
            """,
            (artifact_digest,),
        ).fetchone()
        if row is None and required:
            raise PersistenceIntegrityError("artifact content is missing")
        return row

    def _restore(self, row: sqlite3.Row, content: sqlite3.Row | None) -> StoredSkillArtifact:
        if content is None:
            raise PersistenceIntegrityError("artifact content is missing")
        try:
            payload = json.loads(row["artifact_envelope_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("artifact envelope JSON is malformed") from error
        try:
            artifact = SkillDesignArtifact.from_mapping(payload)
        except ArtifactContractError as error:
            if "UNSUPPORTED" in error.code:
                raise PersistenceContractUnsupportedError(error.code) from error
            raise PersistenceIntegrityError(error.code) from error
        if artifact.artifact_digest != row["artifact_digest"]:
            raise PersistenceIntegrityError("artifact record digest does not match envelope")
        semantic_source_digest = payload.get("semantic_source_digest")
        if artifact.semantic_source_digest != semantic_source_digest:
            raise PersistenceIntegrityError("semantic source digest is not canonical")
        if content["content_id"] != row["content_id"]:
            raise PersistenceIntegrityError("artifact content relation is inconsistent")
        if content["artifact_digest"] != artifact.artifact_digest:
            raise PersistenceIntegrityError("artifact content digest does not match envelope")
        if content["canonical_schema_version"] != artifact.identity.canonical_schema_version:
            raise PersistenceIntegrityError("canonical schema version is inconsistent")
        if content["canonical_artifact_json"] != artifact.canonical_artifact.canonical_json():
            raise PersistenceIntegrityError("canonical artifact content has been tampered with")
        return StoredSkillArtifact(
            record_id=row["record_id"],
            content_id=content["content_id"],
            artifact_digest=artifact.artifact_digest,
            artifact=artifact,
            created_at=row["created_at"],
        )


def _canonical_json(value: Mapping[str, Any]) -> str:
    """Serialize the existing domain mapping; this is not a domain identity."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SkillArtifactRepository",
    "StoredSkillArtifact",
    "StoredSkillArtifactContent",
]
