"""Small SQLite transaction seam for local-first persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import PersistenceIntegrityError, PersistenceSchemaUnsupportedError

if TYPE_CHECKING:
    from .character_skill_persistence import CharacterSkillRepository
    from .skill_artifacts import SkillArtifactRepository

CURRENT_SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 1
DEFAULT_BUSY_TIMEOUT_MS = 5_000
_CHARACTER_TABLE_COLUMNS = {
    "characters": {
        "character_id",
        "current_revision_id",
        "created_at",
        "updated_at",
    },
    "character_revisions": {
        "revision_id",
        "character_id",
        "revision_contract_version",
        "revision_kind",
        "parent_revision_id",
        "revision_sequence",
        "character_payload_json",
        "created_at",
    },
    "bindings": {
        "binding_id",
        "character_id",
        "artifact_record_id",
        "artifact_digest",
        "binding_contract_version",
        "source_context_fingerprint",
        "binding_payload_json",
        "created_at",
    },
    "associations": {
        "association_id",
        "character_id",
        "current_revision_id",
        "created_at",
        "closed_at",
    },
    "association_revisions": {
        "association_revision_id",
        "association_id",
        "character_id",
        "binding_id",
        "placement",
        "placement_order",
        "ordinal",
        "family",
        "mode",
        "display_summary",
        "parent_revision_id",
        "revision_sequence",
        "created_at",
    },
    "character_kit_contents": {
        "kit_record_id",
        "kit_digest",
        "kit_contract_version",
        "placement_schema_version",
        "kit_payload_json",
        "created_at",
    },
    "character_kit_assignments": {
        "assignment_id",
        "character_id",
        "character_revision_id",
        "kit_record_id",
        "created_at",
    },
    "character_kit_current": {
        "character_id",
        "current_assignment_id",
        "updated_at",
    },
    "character_kit_assignment_members": {
        "assignment_id",
        "association_id",
        "association_revision_id",
        "artifact_record_id",
        "artifact_digest",
        "placement",
        "placement_order",
        "ordinal",
    },
}


class PersistenceUnitOfWork:
    """Own one configured SQLite connection and its transaction boundary."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if isinstance(database_path, bytes) or not isinstance(database_path, (str, Path)):
            raise TypeError("database_path must be a string or Path")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.database_path), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self._in_transaction = False
        try:
            self._configure(busy_timeout_ms)
            self._initialize_schema()
            self.begin()
            from .character_skill_persistence import CharacterSkillRepository
            from .characters import CharacterRepository
            from .skill_artifacts import SkillArtifactRepository

            self.skill_artifacts: SkillArtifactRepository = SkillArtifactRepository(self.connection)
            self.characters: CharacterRepository = CharacterRepository(self.connection)
            self.character_skills: CharacterSkillRepository = CharacterSkillRepository(
                self.connection,
                self.characters,
                self.skill_artifacts,
            )
        except Exception:
            self.connection.close()
            raise

    def __enter__(self) -> "PersistenceUnitOfWork":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.connection.close()

    @property
    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise PersistenceSchemaUnsupportedError("schema_version is missing")
        return int(row[0])

    @property
    def busy_timeout_ms(self) -> int:
        return int(self.connection.execute("PRAGMA busy_timeout").fetchone()[0])

    @property
    def journal_mode(self) -> str:
        return str(self.connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def begin(self) -> None:
        if not self._in_transaction:
            self.connection.execute("BEGIN")
            self._in_transaction = True

    def commit(self) -> None:
        if self._in_transaction:
            self.connection.commit()
            self._in_transaction = False

    def rollback(self) -> None:
        if self._in_transaction:
            self.connection.rollback()
            self._in_transaction = False

    def _configure(self, busy_timeout_ms: int) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        if self.connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise PersistenceIntegrityError("SQLite foreign keys could not be enabled")
        self.connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")

    def _initialize_schema(self) -> None:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            tables = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            required_tables = {
                "persistence_meta",
                "skill_artifact_contents",
                "skill_artifact_records",
            }
            if not tables:
                self._create_schema()
            elif not required_tables <= tables:
                raise PersistenceIntegrityError("initialized database is missing required tables")
            else:
                row = self.connection.execute(
                    "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    raise PersistenceSchemaUnsupportedError("schema_version is missing")
                try:
                    version = int(row[0])
                except (TypeError, ValueError) as error:
                    raise PersistenceSchemaUnsupportedError("schema_version is invalid") from error
                if version == LEGACY_SCHEMA_VERSION:
                    self._migrate_v1_to_v2()
                    version = 2
                if version == 2:
                    self._migrate_v2_to_v3()
                elif version != CURRENT_SCHEMA_VERSION:
                    raise PersistenceSchemaUnsupportedError(
                        f"schema version {version} is not supported"
                    )
            self._validate_schema()
            self.connection.commit()
        except (PersistenceSchemaUnsupportedError, PersistenceIntegrityError):
            self.connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            self.connection.rollback()
            raise PersistenceIntegrityError("SQLite schema initialization failed") from error

    def _create_schema(self) -> None:
        statements = (
            """
            CREATE TABLE persistence_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            INSERT INTO persistence_meta (key, value)
            VALUES ('schema_version', '3')
            """,
            """
            CREATE TABLE skill_artifact_contents (
                content_id INTEGER PRIMARY KEY,
                artifact_digest TEXT NOT NULL UNIQUE,
                canonical_schema_version TEXT NOT NULL,
                canonical_artifact_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE skill_artifact_records (
                record_id INTEGER PRIMARY KEY,
                content_id INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                artifact_contract_version TEXT NOT NULL,
                semantic_source_digest TEXT NOT NULL,
                artifact_envelope_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (content_id)
                    REFERENCES skill_artifact_contents (content_id),
                FOREIGN KEY (artifact_digest)
                    REFERENCES skill_artifact_contents (artifact_digest),
                UNIQUE (artifact_digest, artifact_envelope_json)
            )
            """,
            """
            CREATE INDEX skill_artifact_records_by_digest
                ON skill_artifact_records (artifact_digest)
            """,
        )
        for statement in statements:
            self.connection.execute(statement)

        self._create_character_schema()
        self._create_character_skill_schema()

    def _migrate_v1_to_v2(self) -> None:
        self._create_character_schema()
        updated = self.connection.execute(
            """
            UPDATE persistence_meta
            SET value = '2'
            WHERE key = 'schema_version' AND value = '1'
            """
        )
        if updated.rowcount != 1:
            raise PersistenceSchemaUnsupportedError("schema version migration precondition failed")

    def _migrate_v2_to_v3(self) -> None:
        self._create_character_skill_schema()
        updated = self.connection.execute(
            """
            UPDATE persistence_meta
            SET value = '3'
            WHERE key = 'schema_version' AND value = '2'
            """
        )
        if updated.rowcount != 1:
            raise PersistenceSchemaUnsupportedError("schema version migration precondition failed")

    def _create_character_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS characters (
                character_id TEXT PRIMARY KEY,
                current_revision_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (current_revision_id)
                    REFERENCES character_revisions (revision_id)
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_revisions (
                revision_id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                revision_contract_version TEXT NOT NULL,
                revision_kind TEXT NOT NULL CHECK (revision_kind IN ('GENERATED', 'EDITED')),
                parent_revision_id TEXT,
                revision_sequence INTEGER NOT NULL,
                character_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id)
                    DEFERRABLE INITIALLY DEFERRED,
                FOREIGN KEY (parent_revision_id)
                    REFERENCES character_revisions (revision_id)
                    DEFERRABLE INITIALLY DEFERRED,
                UNIQUE (character_id, revision_sequence)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS character_revisions_by_character
                ON character_revisions (character_id, created_at, revision_id)
            """,
        )
        for statement in statements:
            self.connection.execute(statement)

    def _create_character_skill_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS bindings (
                binding_id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                artifact_record_id INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                binding_contract_version TEXT NOT NULL,
                source_context_fingerprint TEXT NOT NULL,
                binding_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id),
                FOREIGN KEY (artifact_record_id)
                    REFERENCES skill_artifact_records (record_id),
                UNIQUE (character_id, artifact_record_id, binding_payload_json)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS associations (
                association_id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                current_revision_id TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id),
                FOREIGN KEY (current_revision_id)
                    REFERENCES association_revisions (association_revision_id)
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS association_revisions (
                association_revision_id TEXT PRIMARY KEY,
                association_id TEXT NOT NULL,
                character_id TEXT NOT NULL,
                binding_id TEXT NOT NULL,
                placement TEXT NOT NULL,
                placement_order INTEGER NOT NULL,
                ordinal INTEGER NOT NULL,
                family TEXT NOT NULL,
                mode TEXT NOT NULL,
                display_summary TEXT NOT NULL,
                parent_revision_id TEXT,
                revision_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (association_id)
                    REFERENCES associations (association_id),
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id),
                FOREIGN KEY (binding_id)
                    REFERENCES bindings (binding_id),
                FOREIGN KEY (parent_revision_id)
                    REFERENCES association_revisions (association_revision_id),
                UNIQUE (association_id, revision_sequence)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_kit_contents (
                kit_record_id INTEGER PRIMARY KEY,
                kit_digest TEXT NOT NULL UNIQUE,
                kit_contract_version TEXT NOT NULL,
                placement_schema_version TEXT NOT NULL,
                kit_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_kit_assignments (
                assignment_id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                character_revision_id TEXT NOT NULL,
                kit_record_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id),
                FOREIGN KEY (character_revision_id)
                    REFERENCES character_revisions (revision_id),
                FOREIGN KEY (kit_record_id)
                    REFERENCES character_kit_contents (kit_record_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_kit_current (
                character_id TEXT PRIMARY KEY,
                current_assignment_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (character_id)
                    REFERENCES characters (character_id),
                FOREIGN KEY (current_assignment_id)
                    REFERENCES character_kit_assignments (assignment_id)
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_kit_assignment_members (
                assignment_id TEXT NOT NULL,
                association_id TEXT NOT NULL,
                association_revision_id TEXT NOT NULL,
                artifact_record_id INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                placement TEXT NOT NULL,
                placement_order INTEGER NOT NULL,
                ordinal INTEGER NOT NULL,
                PRIMARY KEY (assignment_id, association_id),
                FOREIGN KEY (assignment_id)
                    REFERENCES character_kit_assignments (assignment_id),
                FOREIGN KEY (association_id)
                    REFERENCES associations (association_id),
                FOREIGN KEY (association_revision_id)
                    REFERENCES association_revisions (association_revision_id),
                FOREIGN KEY (artifact_record_id)
                    REFERENCES skill_artifact_records (record_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS bindings_by_character
                ON bindings (character_id, created_at, binding_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS association_revisions_by_association
                ON association_revisions (association_id, revision_sequence)
            """,
            """
            CREATE INDEX IF NOT EXISTS kit_assignments_by_character
                ON character_kit_assignments (character_id, created_at, assignment_id)
            """,
        )
        for statement in statements:
            self.connection.execute(statement)

    def _validate_schema(self) -> None:
        for table_name, required_columns in _CHARACTER_TABLE_COLUMNS.items():
            columns = {
                row[1] for row in self.connection.execute(f"PRAGMA table_info({table_name})")
            }
            if not required_columns <= columns:
                raise PersistenceIntegrityError(f"schema v2 table {table_name} is incomplete")


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_BUSY_TIMEOUT_MS",
    "LEGACY_SCHEMA_VERSION",
    "PersistenceUnitOfWork",
]
