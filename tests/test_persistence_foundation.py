from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from character_intelligence.hybrid_ir.playground import (
    build_playground_context,
    build_playground_evaluation_context,
    run_playground_context_pipeline,
)
from character_intelligence.hybrid_ir.runner import FakeProvider
from character_intelligence.skill_artifact import build_skill_design_artifact
from persistence.errors import (
    PersistenceContractUnsupportedError,
    PersistenceIntegrityError,
    PersistenceSchemaUnsupportedError,
)
from persistence.sqlite_store import PersistenceUnitOfWork

ROOT = Path(__file__).resolve().parents[1]


def _fixture(case_id: str = "character_alignment_support_v1") -> dict[str, object]:
    path = ROOT / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json"
    return json.loads(path.read_text(encoding="utf-8"))[case_id]


def _artifact(
    *,
    case_id: str = "character_alignment_support_v1",
    provider: str | None = "provider-a",
    run_id: str | None = "run-a",
):
    context = build_playground_context("support", "active", "Design a Chinese support skill.")
    result = run_playground_context_pipeline(
        FakeProvider(_fixture(case_id)),
        context,
        build_playground_evaluation_context("support", "active"),
        model="offline-fixture",
        language="zh-CN",
        repo_root=ROOT,
        invocation_id=run_id or "artifact-test",
    )
    assert result.candidate and result.report and result.validated_ir and result.compiler_provenance
    return build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
        provider=provider,
        model="fixture-model",
        run_id=run_id,
    )


def test_new_database_bootstraps_versioned_schema_and_foreign_keys(tmp_path) -> None:
    database_path = tmp_path / "测试" / "studio.db"

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert unit_of_work.schema_version == 3
        assert unit_of_work.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {
            row[0]
            for row in unit_of_work.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "persistence_meta",
        "skill_artifact_contents",
        "skill_artifact_records",
        "characters",
        "character_revisions",
        "bindings",
        "associations",
        "association_revisions",
        "character_kit_contents",
        "character_kit_assignments",
        "character_kit_current",
        "character_kit_assignment_members",
    } <= tables
    assert (
        not {
            "role_coverage_reports",
            "alignment_reports",
            "evaluation_reports",
        }
        & tables
    )
    assert database_path.is_file()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
        ).fetchone() == ("3",)


def test_artifact_round_trip_survives_connection_restart(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        saved = unit_of_work.skill_artifacts.save(artifact)

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        restored = unit_of_work.skill_artifacts.get(saved.record_id)

    assert restored.artifact == artifact
    assert restored.artifact_digest == artifact.artifact_digest


def test_duplicate_authoring_record_is_idempotent_and_content_is_deduplicated(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first = unit_of_work.skill_artifacts.save(artifact)
        second = unit_of_work.skill_artifacts.save(artifact)
        records = unit_of_work.skill_artifacts.find_by_digest(artifact.artifact_digest)

    assert first.record_id == second.record_id
    assert len(records) == 1
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM skill_artifact_contents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM skill_artifact_records").fetchone()[0] == 1


def test_same_content_with_different_provenance_keeps_two_records(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    first_artifact = _artifact(provider="provider-a", run_id="run-a")
    second_artifact = replace(
        first_artifact,
        provenance=replace(first_artifact.provenance, provider="provider-b", run_id="run-b"),
    )
    assert first_artifact.artifact_digest == second_artifact.artifact_digest
    assert first_artifact.to_mapping() != second_artifact.to_mapping()

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first = unit_of_work.skill_artifacts.save(first_artifact)
        second = unit_of_work.skill_artifacts.save(second_artifact)
        records = unit_of_work.skill_artifacts.find_by_digest(first_artifact.artifact_digest)

    assert first.record_id != second.record_id
    assert [item.artifact.provenance.provider for item in records] == ["provider-a", "provider-b"]
    assert len({item.content_id for item in records}) == 1


def test_different_canonical_content_creates_independent_content_rows(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    first_artifact = _artifact(case_id="character_alignment_support_v1")
    second_artifact = _artifact(case_id="character_alignment_main_dps_v1")
    assert first_artifact.artifact_digest != second_artifact.artifact_digest

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        unit_of_work.skill_artifacts.save(first_artifact)
        unit_of_work.skill_artifacts.save(second_artifact)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM skill_artifact_contents").fetchone()[0] == 2


def test_failed_unit_of_work_rolls_back_artifact_write(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()

    with pytest.raises(RuntimeError, match="abort"):
        with PersistenceUnitOfWork(database_path) as unit_of_work:
            unit_of_work.skill_artifacts.save(artifact)
            raise RuntimeError("abort")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert not unit_of_work.skill_artifacts.exists(artifact.artifact_digest)


def test_unknown_database_schema_fails_closed_without_reset(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path):
        pass
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE persistence_meta SET value = '99' WHERE key = 'schema_version'")

    with pytest.raises(PersistenceSchemaUnsupportedError):
        PersistenceUnitOfWork(database_path)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
        ).fetchone() == ("99",)


def test_existing_database_reopens_without_resetting_records(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        saved = unit_of_work.skill_artifacts.save(artifact)

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert unit_of_work.skill_artifacts.get(saved.record_id).artifact == artifact


def test_tampered_canonical_payload_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        saved = unit_of_work.skill_artifacts.save(artifact)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT canonical_artifact_json FROM skill_artifact_contents WHERE artifact_digest = ?",
            (artifact.artifact_digest,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["display_summary"] = "tampered"
        connection.execute(
            "UPDATE skill_artifact_contents SET canonical_artifact_json = ? WHERE artifact_digest = ?",
            (json.dumps(payload, ensure_ascii=False), artifact.artifact_digest),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            unit_of_work.skill_artifacts.get(saved.record_id)


def test_tampered_record_digest_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    first_artifact = _artifact(case_id="character_alignment_support_v1")
    second_artifact = _artifact(case_id="character_alignment_main_dps_v1")
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first = unit_of_work.skill_artifacts.save(first_artifact)
        unit_of_work.skill_artifacts.save(second_artifact)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE skill_artifact_records SET artifact_digest = ? WHERE record_id = ?",
            (second_artifact.artifact_digest, first.record_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            unit_of_work.skill_artifacts.get(first.record_id)


def test_unsupported_artifact_contract_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        saved = unit_of_work.skill_artifacts.save(artifact)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT artifact_envelope_json FROM skill_artifact_records WHERE record_id = ?",
            (saved.record_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["artifact_contract_version"] = "skill-design-artifact/9.0"
        connection.execute(
            "UPDATE skill_artifact_records SET artifact_envelope_json = ? WHERE record_id = ?",
            (json.dumps(payload, ensure_ascii=False), saved.record_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceContractUnsupportedError):
            unit_of_work.skill_artifacts.get(saved.record_id)


def test_sqlite_configuration_is_bounded_and_storage_has_no_secret_fields(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _artifact()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        unit_of_work.skill_artifacts.save(artifact)
        assert unit_of_work.busy_timeout_ms == 5_000
        assert unit_of_work.journal_mode in {
            "delete",
            "truncate",
            "persist",
            "memory",
            "wal",
            "off",
        }

    with sqlite3.connect(database_path) as connection:
        values = (
            connection.execute("SELECT canonical_artifact_json FROM skill_artifact_contents")
            .fetchone()[0]
            .lower()
        )
        values += (
            connection.execute("SELECT artifact_envelope_json FROM skill_artifact_records")
            .fetchone()[0]
            .lower()
        )
    for forbidden in ("api_key", "authorization", "cookie", "raw_response", "system_prompt"):
        assert forbidden not in values
