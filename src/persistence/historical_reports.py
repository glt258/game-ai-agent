"""Typed, append-only SQLite adapters for historical domain reports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from character_intelligence.character_kit import (
    CHARACTER_KIT_CONTRACT_VERSION,
    KIT_PLACEMENT_SCHEMA_VERSION,
)
from character_intelligence.character_kit_evaluation import (
    CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION,
    CharacterKitEvaluationResult,
)
from character_intelligence.character_skill_alignment import (
    CHARACTER_SKILL_ALIGNMENT_VERSION,
    CharacterSkillAlignmentResult,
)
from character_intelligence.character_skill_projection import CHARACTER_SKILL_PROJECTION_VERSION
from character_skill import SkillFinding, SkillValidationReport

from .character_skill_persistence import _alignment_from_mapping
from .characters import CharacterRepository
from .errors import (
    PersistenceContractUnsupportedError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceRecordNotFoundError,
    PersistenceWriteConflictError,
)
from .skill_artifacts import SkillArtifactRepository, StoredSkillArtifact


@dataclass(frozen=True)
class StoredSkillEvaluationReport:
    report_id: str
    artifact_record_id: int
    artifact_digest: str
    artifact_contract_version: str
    evaluator_version: str
    report: SkillValidationReport
    created_at: str


@dataclass(frozen=True)
class StoredCharacterSkillAlignmentReport:
    report_id: str
    character_id: str
    character_revision_id: str
    artifact_record_id: int
    artifact_digest: str
    artifact_contract_version: str
    source_context_fingerprint: str
    alignment_version: str
    character_context_projection_version: str
    report: CharacterSkillAlignmentResult
    report_digest: str
    created_at: str


@dataclass(frozen=True)
class StoredCharacterKitRoleCoverageReport:
    report_id: str
    character_id: str
    character_revision_id: str
    kit_record_id: int
    kit_digest: str
    kit_contract_version: str
    evaluation_context_fingerprint: str
    evaluator_version: str
    report: CharacterKitEvaluationResult
    created_at: str


class HistoricalReportRepository:
    """Persist already-evaluated typed reports without running evaluators."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        characters: CharacterRepository,
        artifacts: SkillArtifactRepository,
    ) -> None:
        self._connection = connection
        self._characters = characters
        self._artifacts = artifacts

    def save_skill_evaluation(
        self,
        artifact_record_id: int,
        report: SkillValidationReport,
        *,
        evaluator_version: str | None = None,
    ) -> StoredSkillEvaluationReport:
        artifact = self._artifact(artifact_record_id)
        self._validate_skill_report(artifact, report)
        version = evaluator_version or artifact.artifact.versions.skill_evaluator_version
        _non_empty(version, "evaluator_version")
        payload_json = _canonical_json(report.to_mapping())
        self._connection.execute("SAVEPOINT save_skill_evaluation_report")
        try:
            existing = self._connection.execute(
                """
                SELECT * FROM skill_evaluation_reports
                WHERE artifact_record_id = ? AND evaluator_version = ?
                """,
                (artifact_record_id, version),
            ).fetchone()
            if existing is not None:
                if existing["report_payload_json"] != payload_json:
                    raise PersistenceWriteConflictError(
                        "deterministic Skill Evaluation report conflicts with stored data"
                    )
                stored = self._skill_evaluation_from_row(existing)
                self._connection.execute("RELEASE SAVEPOINT save_skill_evaluation_report")
                return stored
            report_id = _new_id()
            self._connection.execute(
                """
                INSERT INTO skill_evaluation_reports (
                    report_id, artifact_record_id, artifact_digest,
                    artifact_contract_version, evaluator_version, report_digest,
                    report_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    artifact_record_id,
                    artifact.artifact_digest,
                    artifact.artifact.artifact_contract_version,
                    version,
                    report.report_digest,
                    payload_json,
                    _utc_now(),
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM skill_evaluation_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            stored = self._skill_evaluation_from_row(row)
            self._connection.execute("RELEASE SAVEPOINT save_skill_evaluation_report")
            return stored
        except PersistenceError:
            _rollback_savepoint(self._connection, "save_skill_evaluation_report")
            raise
        except sqlite3.IntegrityError as error:
            _rollback_savepoint(self._connection, "save_skill_evaluation_report")
            raise PersistenceWriteConflictError(
                "Skill Evaluation report conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            _rollback_savepoint(self._connection, "save_skill_evaluation_report")
            raise PersistenceIntegrityError(
                "SQLite Skill Evaluation report write failed"
            ) from error

    def save_alignment(
        self,
        character_id: str,
        character_revision_id: str,
        artifact_record_id: int,
        report: CharacterSkillAlignmentResult,
        *,
        character_context_projection_version: str = CHARACTER_SKILL_PROJECTION_VERSION,
        alignment_version: str = CHARACTER_SKILL_ALIGNMENT_VERSION,
    ) -> StoredCharacterSkillAlignmentReport:
        artifact = self._artifact(artifact_record_id)
        self._characters.get_revision(character_id, character_revision_id)
        if alignment_version != CHARACTER_SKILL_ALIGNMENT_VERSION:
            raise PersistenceContractUnsupportedError(alignment_version)
        if character_context_projection_version != CHARACTER_SKILL_PROJECTION_VERSION:
            raise PersistenceContractUnsupportedError(character_context_projection_version)
        self._validate_alignment_report(artifact, report)
        payload_json = _canonical_json(report.to_mapping())
        report_digest = _payload_digest(report.to_mapping())
        self._connection.execute("SAVEPOINT save_alignment_report")
        try:
            existing = self._connection.execute(
                """
                SELECT * FROM character_skill_alignment_reports
                WHERE character_id = ? AND character_revision_id = ?
                  AND artifact_record_id = ? AND source_context_fingerprint = ?
                  AND alignment_version = ? AND character_context_projection_version = ?
                """,
                (
                    character_id,
                    character_revision_id,
                    artifact_record_id,
                    report.source_context_fingerprint,
                    alignment_version,
                    character_context_projection_version,
                ),
            ).fetchone()
            if existing is not None:
                if existing["report_payload_json"] != payload_json:
                    raise PersistenceWriteConflictError(
                        "deterministic Alignment report conflicts with stored data"
                    )
                stored = self._alignment_from_row(existing)
                self._connection.execute("RELEASE SAVEPOINT save_alignment_report")
                return stored
            report_id = _new_id()
            self._connection.execute(
                """
                INSERT INTO character_skill_alignment_reports (
                    report_id, character_id, character_revision_id,
                    artifact_record_id, artifact_digest, artifact_contract_version,
                    source_context_fingerprint, alignment_version,
                    character_context_projection_version, report_digest,
                    report_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    character_id,
                    character_revision_id,
                    artifact_record_id,
                    artifact.artifact_digest,
                    artifact.artifact.artifact_contract_version,
                    report.source_context_fingerprint,
                    alignment_version,
                    character_context_projection_version,
                    report_digest,
                    payload_json,
                    _utc_now(),
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM character_skill_alignment_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            stored = self._alignment_from_row(row)
            self._connection.execute("RELEASE SAVEPOINT save_alignment_report")
            return stored
        except PersistenceError:
            _rollback_savepoint(self._connection, "save_alignment_report")
            raise
        except sqlite3.IntegrityError as error:
            _rollback_savepoint(self._connection, "save_alignment_report")
            raise PersistenceWriteConflictError(
                "Alignment report conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            _rollback_savepoint(self._connection, "save_alignment_report")
            raise PersistenceIntegrityError("SQLite Alignment report write failed") from error

    def save_role_coverage(
        self,
        character_id: str,
        character_revision_id: str,
        kit_record_id: int,
        report: CharacterKitEvaluationResult,
    ) -> StoredCharacterKitRoleCoverageReport:
        self._characters.get_revision(character_id, character_revision_id)
        kit = self._kit_row(kit_record_id)
        self._validate_role_report(kit, report)
        payload_json = _canonical_json(report.to_mapping())
        self._connection.execute("SAVEPOINT save_role_coverage_report")
        try:
            existing = self._connection.execute(
                """
                SELECT * FROM character_kit_role_coverage_reports
                WHERE character_id = ? AND character_revision_id = ? AND kit_record_id = ?
                  AND evaluation_context_fingerprint = ? AND evaluator_version = ?
                """,
                (
                    character_id,
                    character_revision_id,
                    kit_record_id,
                    report.evaluation_context_fingerprint,
                    report.evaluator_version,
                ),
            ).fetchone()
            if existing is not None:
                if existing["report_payload_json"] != payload_json:
                    raise PersistenceWriteConflictError(
                        "deterministic Role Coverage report conflicts with stored data"
                    )
                stored = self._role_coverage_from_row(existing)
                self._connection.execute("RELEASE SAVEPOINT save_role_coverage_report")
                return stored
            report_id = _new_id()
            self._connection.execute(
                """
                INSERT INTO character_kit_role_coverage_reports (
                    report_id, character_id, character_revision_id, kit_record_id,
                    kit_digest, kit_contract_version, evaluation_context_fingerprint,
                    evaluator_version, report_digest, report_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    character_id,
                    character_revision_id,
                    kit_record_id,
                    report.kit_digest,
                    kit["kit_contract_version"],
                    report.evaluation_context_fingerprint,
                    report.evaluator_version,
                    report.report_digest,
                    payload_json,
                    _utc_now(),
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM character_kit_role_coverage_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
            stored = self._role_coverage_from_row(row)
            self._connection.execute("RELEASE SAVEPOINT save_role_coverage_report")
            return stored
        except PersistenceError:
            _rollback_savepoint(self._connection, "save_role_coverage_report")
            raise
        except sqlite3.IntegrityError as error:
            _rollback_savepoint(self._connection, "save_role_coverage_report")
            raise PersistenceWriteConflictError(
                "Role Coverage report conflicts with stored data"
            ) from error
        except sqlite3.DatabaseError as error:
            _rollback_savepoint(self._connection, "save_role_coverage_report")
            raise PersistenceIntegrityError("SQLite Role Coverage report write failed") from error

    def list_skill_evaluations(
        self, artifact_record_id: int
    ) -> tuple[StoredSkillEvaluationReport, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM skill_evaluation_reports
            WHERE artifact_record_id = ? ORDER BY report_sequence
            """,
            (artifact_record_id,),
        ).fetchall()
        self._artifact(artifact_record_id)
        return tuple(self._skill_evaluation_from_row(row) for row in rows)

    def list_alignments(
        self,
        artifact_record_id: int,
        *,
        source_context_fingerprint: str | None = None,
    ) -> tuple[StoredCharacterSkillAlignmentReport, ...]:
        self._artifact(artifact_record_id)
        if source_context_fingerprint is None:
            rows = self._connection.execute(
                """
                SELECT * FROM character_skill_alignment_reports
                WHERE artifact_record_id = ? ORDER BY report_sequence
                """,
                (artifact_record_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT * FROM character_skill_alignment_reports
                WHERE artifact_record_id = ? AND source_context_fingerprint = ?
                ORDER BY report_sequence
                """,
                (artifact_record_id, source_context_fingerprint),
            ).fetchall()
        return tuple(self._alignment_from_row(row) for row in rows)

    def list_role_coverage(
        self,
        kit_record_id: int,
        *,
        character_revision_id: str | None = None,
        evaluation_context_fingerprint: str | None = None,
    ) -> tuple[StoredCharacterKitRoleCoverageReport, ...]:
        self._kit_row(kit_record_id)
        clauses = ["kit_record_id = ?"]
        values: list[object] = [kit_record_id]
        if character_revision_id is not None:
            clauses.append("character_revision_id = ?")
            values.append(character_revision_id)
        if evaluation_context_fingerprint is not None:
            clauses.append("evaluation_context_fingerprint = ?")
            values.append(evaluation_context_fingerprint)
        rows = self._connection.execute(
            f"SELECT * FROM character_kit_role_coverage_reports WHERE {' AND '.join(clauses)} "
            "ORDER BY report_sequence",
            values,
        ).fetchall()
        return tuple(self._role_coverage_from_row(row) for row in rows)

    def _skill_evaluation_from_row(self, row: sqlite3.Row) -> StoredSkillEvaluationReport:
        artifact = self._artifact(row["artifact_record_id"])
        report = _skill_report_from_json(row["report_payload_json"])
        if row["artifact_digest"] != artifact.artifact_digest:
            raise PersistenceIntegrityError("Skill Evaluation artifact digest index mismatch")
        if row["artifact_contract_version"] != artifact.artifact.artifact_contract_version:
            raise PersistenceIntegrityError("Skill Evaluation artifact contract index mismatch")
        if row["report_digest"] != report.report_digest:
            raise PersistenceIntegrityError("Skill Evaluation report digest mismatch")
        return StoredSkillEvaluationReport(
            row["report_id"],
            row["artifact_record_id"],
            row["artifact_digest"],
            row["artifact_contract_version"],
            row["evaluator_version"],
            report,
            row["created_at"],
        )

    def _alignment_from_row(self, row: sqlite3.Row) -> StoredCharacterSkillAlignmentReport:
        artifact = self._artifact(row["artifact_record_id"])
        self._characters.get_revision(row["character_id"], row["character_revision_id"])
        if row["alignment_version"] != CHARACTER_SKILL_ALIGNMENT_VERSION:
            raise PersistenceContractUnsupportedError(row["alignment_version"])
        if row["character_context_projection_version"] != CHARACTER_SKILL_PROJECTION_VERSION:
            raise PersistenceContractUnsupportedError(row["character_context_projection_version"])
        try:
            payload = json.loads(row["report_payload_json"])
            report = _alignment_from_mapping(payload)
        except PersistenceError:
            raise
        except (TypeError, json.JSONDecodeError, ValueError) as error:
            raise PersistenceIntegrityError("Alignment report payload is invalid") from error
        if _canonical_json(payload) != row["report_payload_json"]:
            raise PersistenceIntegrityError("Alignment report payload is not canonical")
        if (
            row["artifact_digest"] != artifact.artifact_digest
            or report.artifact_digest != row["artifact_digest"]
            or report.source_context_fingerprint != row["source_context_fingerprint"]
        ):
            raise PersistenceIntegrityError("Alignment report input index mismatch")
        if row["artifact_contract_version"] != artifact.artifact.artifact_contract_version:
            raise PersistenceIntegrityError("Alignment artifact contract index mismatch")
        if row["report_digest"] != _payload_digest(payload):
            raise PersistenceIntegrityError("Alignment report digest mismatch")
        return StoredCharacterSkillAlignmentReport(
            row["report_id"],
            row["character_id"],
            row["character_revision_id"],
            row["artifact_record_id"],
            row["artifact_digest"],
            row["artifact_contract_version"],
            row["source_context_fingerprint"],
            row["alignment_version"],
            row["character_context_projection_version"],
            report,
            row["report_digest"],
            row["created_at"],
        )

    def _role_coverage_from_row(self, row: sqlite3.Row) -> StoredCharacterKitRoleCoverageReport:
        self._characters.get_revision(row["character_id"], row["character_revision_id"])
        kit = self._kit_row(row["kit_record_id"])
        try:
            payload = json.loads(row["report_payload_json"])
            report = CharacterKitEvaluationResult.from_mapping(payload)
        except (TypeError, json.JSONDecodeError, ValueError) as error:
            if row["evaluator_version"] != CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION:
                raise PersistenceContractUnsupportedError(row["evaluator_version"]) from error
            raise PersistenceIntegrityError("Role Coverage report payload is invalid") from error
        if _canonical_json(payload) != row["report_payload_json"]:
            raise PersistenceIntegrityError("Role Coverage report payload is not canonical")
        if (
            row["kit_digest"] != kit["kit_digest"]
            or row["kit_contract_version"] != kit["kit_contract_version"]
            or report.kit_digest != row["kit_digest"]
            or report.evaluation_context_fingerprint != row["evaluation_context_fingerprint"]
            or report.evaluator_version != row["evaluator_version"]
            or report.report_digest != row["report_digest"]
        ):
            raise PersistenceIntegrityError("Role Coverage report input index mismatch")
        return StoredCharacterKitRoleCoverageReport(
            row["report_id"],
            row["character_id"],
            row["character_revision_id"],
            row["kit_record_id"],
            row["kit_digest"],
            row["kit_contract_version"],
            row["evaluation_context_fingerprint"],
            row["evaluator_version"],
            report,
            row["created_at"],
        )

    def _artifact(self, record_id: int) -> StoredSkillArtifact:
        try:
            return self._artifacts.get(record_id)
        except PersistenceError as error:
            raise PersistenceRecordNotFoundError(
                f"Skill artifact record {record_id} was not found"
            ) from error

    def _kit_row(self, kit_record_id: int) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM character_kit_contents WHERE kit_record_id = ?", (kit_record_id,)
        ).fetchone()
        if row is None:
            raise PersistenceRecordNotFoundError(
                f"CharacterKit record {kit_record_id} was not found"
            )
        try:
            payload = json.loads(row["kit_payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("CharacterKit payload is invalid JSON") from error
        if not isinstance(payload, Mapping) or _canonical_json(payload) != row["kit_payload_json"]:
            raise PersistenceIntegrityError("CharacterKit payload is not canonical")
        if (
            payload.get("kit_digest") != row["kit_digest"]
            or row["kit_contract_version"] != CHARACTER_KIT_CONTRACT_VERSION
            or row["placement_schema_version"] != KIT_PLACEMENT_SCHEMA_VERSION
        ):
            raise PersistenceIntegrityError("CharacterKit digest index mismatch")
        return row

    @staticmethod
    def _validate_skill_report(
        artifact: StoredSkillArtifact, report: SkillValidationReport
    ) -> None:
        if not isinstance(report, SkillValidationReport):
            raise PersistenceIntegrityError("value is not a SkillValidationReport")
        if report.candidate_digest != artifact.artifact_digest:
            raise PersistenceIntegrityError("Skill Evaluation is not bound to artifact")
        restored = _skill_report_from_json(_canonical_json(report.to_mapping()))
        if restored != report:
            raise PersistenceIntegrityError("Skill Evaluation mapping is not stable")

    @staticmethod
    def _validate_alignment_report(
        artifact: StoredSkillArtifact, report: CharacterSkillAlignmentResult
    ) -> None:
        if not isinstance(report, CharacterSkillAlignmentResult):
            raise PersistenceIntegrityError("value is not a CharacterSkillAlignmentResult")
        if report.artifact_digest != artifact.artifact_digest:
            raise PersistenceIntegrityError("Alignment is not bound to artifact")
        try:
            restored = _alignment_from_mapping(report.to_mapping())
        except PersistenceError:
            raise
        except ValueError as error:
            raise PersistenceIntegrityError("Alignment mapping is invalid") from error
        if restored != report:
            raise PersistenceIntegrityError("Alignment mapping is not stable")

    @staticmethod
    def _validate_role_report(kit: sqlite3.Row, report: CharacterKitEvaluationResult) -> None:
        if not isinstance(report, CharacterKitEvaluationResult):
            raise PersistenceIntegrityError("value is not a CharacterKitEvaluationResult")
        if report.kit_digest != kit["kit_digest"]:
            raise PersistenceIntegrityError("Role Coverage is not bound to Kit")
        if report.evaluator_version != CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION:
            raise PersistenceContractUnsupportedError(report.evaluator_version)
        try:
            restored = CharacterKitEvaluationResult.from_mapping(report.to_mapping())
        except ValueError as error:
            raise PersistenceIntegrityError("Role Coverage mapping is invalid") from error
        if restored != report:
            raise PersistenceIntegrityError("Role Coverage mapping is not stable")


class HistoricalReportPersistenceService:
    """Explicit application seam; it never invokes a domain evaluator."""

    def __init__(self, repository: HistoricalReportRepository) -> None:
        self._repository = repository

    def record_skill_evaluation(self, *args: Any, **kwargs: Any) -> StoredSkillEvaluationReport:
        return self._repository.save_skill_evaluation(*args, **kwargs)

    def record_alignment(self, *args: Any, **kwargs: Any) -> StoredCharacterSkillAlignmentReport:
        return self._repository.save_alignment(*args, **kwargs)

    def record_role_coverage(
        self, *args: Any, **kwargs: Any
    ) -> StoredCharacterKitRoleCoverageReport:
        return self._repository.save_role_coverage(*args, **kwargs)

    def list_skill_evaluations(
        self, artifact_record_id: int
    ) -> tuple[StoredSkillEvaluationReport, ...]:
        return self._repository.list_skill_evaluations(artifact_record_id)

    def list_alignments(
        self,
        artifact_record_id: int,
        *,
        source_context_fingerprint: str | None = None,
    ) -> tuple[StoredCharacterSkillAlignmentReport, ...]:
        return self._repository.list_alignments(
            artifact_record_id,
            source_context_fingerprint=source_context_fingerprint,
        )

    def list_role_coverage(
        self,
        kit_record_id: int,
        *,
        character_revision_id: str | None = None,
        evaluation_context_fingerprint: str | None = None,
    ) -> tuple[StoredCharacterKitRoleCoverageReport, ...]:
        return self._repository.list_role_coverage(
            kit_record_id,
            character_revision_id=character_revision_id,
            evaluation_context_fingerprint=evaluation_context_fingerprint,
        )


def _skill_report_from_json(value: str) -> SkillValidationReport:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise PersistenceIntegrityError(
            "Skill Evaluation report payload is invalid JSON"
        ) from error
    expected = {
        "outcome",
        "blocking",
        "repair_allowed",
        "findings",
        "candidate_digest",
        "context_digest",
        "report_digest",
        "base_digest",
        "finding_codes",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise PersistenceIntegrityError("Skill Evaluation report fields are not exact")
    findings = payload["findings"]
    if not isinstance(findings, list) or not isinstance(payload["finding_codes"], list):
        raise PersistenceIntegrityError("Skill Evaluation findings are invalid")
    parsed: list[SkillFinding] = []
    for item in findings:
        finding_expected = {
            "code",
            "field_path",
            "blocking",
            "repairable",
            "evidence_refs",
            "authorized_paths",
            "priority",
        }
        if not isinstance(item, Mapping) or set(item) != finding_expected:
            raise PersistenceIntegrityError("Skill Evaluation finding fields are not exact")
        if not isinstance(item["evidence_refs"], list) or not isinstance(
            item["authorized_paths"], list
        ):
            raise PersistenceIntegrityError("Skill Evaluation finding references are invalid")
        finding = SkillFinding(
            _string(item["code"]),
            _string(item["field_path"]),
            _bool(item["blocking"]),
            _bool(item["repairable"]),
            tuple(_string(x) for x in item["evidence_refs"]),
            tuple(_string(x) for x in item["authorized_paths"]),
        )
        if finding.priority != item["priority"]:
            raise PersistenceIntegrityError("Skill Evaluation finding priority mismatch")
        parsed.append(finding)
    report = SkillValidationReport(
        _string(payload["outcome"]),
        _bool(payload["blocking"]),
        _bool(payload["repair_allowed"]),
        tuple(parsed),
        _string(payload["candidate_digest"]),
        _string(payload["context_digest"]),
        _string(payload["report_digest"]),
    )
    if (
        report.base_digest != payload["base_digest"]
        or list(report.finding_codes) != payload["finding_codes"]
    ):
        raise PersistenceIntegrityError("Skill Evaluation derived fields mismatch")
    expected_digest = _payload_digest(
        {
            "candidate_digest": report.candidate_digest,
            "context_digest": report.context_digest,
            "findings": [item.to_mapping() for item in report.findings],
            "outcome": report.outcome,
        }
    )
    if expected_digest != report.report_digest:
        raise PersistenceIntegrityError("Skill Evaluation report digest mismatch")
    return report


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _new_id() -> str:
    return str(uuid.uuid4())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise PersistenceIntegrityError("report field must be a string")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise PersistenceIntegrityError("report field must be a boolean")
    return value


def _rollback_savepoint(connection: sqlite3.Connection, name: str) -> None:
    try:
        connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
        connection.execute(f"RELEASE SAVEPOINT {name}")
    except sqlite3.DatabaseError:
        connection.rollback()


__all__ = [
    "HistoricalReportPersistenceService",
    "HistoricalReportRepository",
    "StoredCharacterKitRoleCoverageReport",
    "StoredCharacterSkillAlignmentReport",
    "StoredSkillEvaluationReport",
]
