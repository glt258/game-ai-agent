from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest
from test_persistence_foundation import _artifact as _skill_artifact

from agents.character_generation import CharacterDraft
from agents.response_contracts import character_draft_root_example
from persistence.character_persistence import CharacterPersistenceService
from persistence.errors import (
    CharacterNotFoundError,
    CharacterRevisionConflictError,
    CharacterRevisionNotFoundError,
    PersistenceContractUnsupportedError,
    PersistenceIntegrityError,
)
from persistence.sqlite_store import PersistenceUnitOfWork


def _draft(name: str = "林澈") -> CharacterDraft:
    payload = character_draft_root_example()
    payload.update(
        {
            "draft_id": "draft_persistence_001",
            "name": name,
            "occupation": "城市协理人",
            "social_role": "社区协调者",
            "background": "她在雨季里负责照看一间旧社区工作室。",
            "ability_concept": "把亲自理解的方法变成有限的行动框架。",
            "design_pitch": "用观察和协作帮助队伍完成现场处置。",
            "story_hook": "一封没有寄出的信把她带回旧街区。",
        }
    )
    return CharacterDraft.from_mapping(payload)


def _authored_payload(draft: CharacterDraft) -> dict[str, object]:
    payload = draft.to_dict()
    payload.pop("draft_id")
    payload.pop("status")
    return payload


def test_create_generated_character_and_load_after_restart(tmp_path) -> None:
    database_path = tmp_path / "测试" / "studio.db"
    draft = _draft()

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(draft)
        assert character.current_revision.kind == "GENERATED"
        assert character.current_revision.parent_revision_id is None

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        loaded = unit_of_work.characters.get_character(character.character_id)
        revision = unit_of_work.characters.get_revision(
            character.character_id,
            character.current_revision_id,
        )

    assert loaded.character_id == character.character_id
    assert loaded.current_revision_id == character.current_revision_id
    assert _authored_payload(loaded.current_revision.draft) == _authored_payload(draft)
    assert _authored_payload(revision.draft) == _authored_payload(draft)
    assert loaded.current_revision.draft.status == "draft"
    assert loaded.current_revision.draft.draft_id != draft.draft_id


def test_generated_and_edited_revisions_preserve_lineage_and_current_pointer(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    first_draft = _draft()
    second_draft = _draft("顾澄")
    third_draft = replace(second_draft, background="她把工作室交给了新的邻居。")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        service = CharacterPersistenceService(unit_of_work.characters)
        character = service.save_generated_character(first_draft)
        second = service.save_edited_character(
            character.character_id,
            second_draft,
            expected_current_revision_id=character.current_revision_id,
        )
        third = service.save_edited_character(
            character.character_id,
            third_draft,
            expected_current_revision_id=second.current_revision_id,
        )
        summaries = unit_of_work.characters.list_revisions(character.character_id)

    assert third.current_revision.kind == "EDITED"
    assert third.current_revision.parent_revision_id == second.current_revision_id
    assert third.current_revision_id != second.current_revision_id != character.current_revision_id
    assert [item.kind for item in summaries] == ["GENERATED", "EDITED", "EDITED"]
    assert summaries[-1].is_current is True

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first = unit_of_work.characters.get_revision(
            character.character_id,
            third.current_revision.parent_revision_id,
        )
    assert first.kind == "EDITED"
    assert first.parent_revision_id == character.current_revision_id


def test_identical_current_payload_save_is_idempotent(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    draft = _draft()

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(draft)
        service = CharacterPersistenceService(unit_of_work.characters)
        saved = service.save_edited_character(
            character.character_id,
            draft,
            expected_current_revision_id=character.current_revision_id,
        )
        revisions = unit_of_work.characters.list_revisions(character.character_id)

    assert saved.current_revision_id == character.current_revision_id
    assert len(revisions) == 1


def test_stale_edit_fails_without_automatic_merge(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    draft = _draft()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(draft)

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        service = CharacterPersistenceService(unit_of_work.characters)
        newer = service.save_edited_character(
            character.character_id,
            replace(draft, name="新版本"),
            expected_current_revision_id=character.current_revision_id,
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(CharacterRevisionConflictError) as error:
            unit_of_work.characters.append_revision(
                character.character_id,
                replace(draft, name="过期版本"),
                expected_current_revision_id=character.current_revision_id,
            )
        loaded = unit_of_work.characters.get_character(character.character_id)
        revisions = unit_of_work.characters.list_revisions(character.character_id)

    assert error.value.expected_revision_id == character.current_revision_id
    assert error.value.current_revision_id == newer.current_revision_id
    assert loaded.current_revision_id == newer.current_revision_id
    assert len(revisions) == 2


def test_unknown_character_revision_and_wrong_ownership_fail_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first = unit_of_work.characters.create(_draft())
        second = unit_of_work.characters.create(_draft("另一个角色"))
        with pytest.raises(CharacterNotFoundError):
            unit_of_work.characters.get_character("missing-character")
        with pytest.raises(CharacterRevisionNotFoundError):
            unit_of_work.characters.get_revision(first.character_id, "missing-revision")
        with pytest.raises(CharacterRevisionNotFoundError):
            unit_of_work.characters.get_revision(second.character_id, first.current_revision_id)


def test_revision_payload_tampering_and_unsupported_contract_fail_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(_draft())

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT character_payload_json FROM character_revisions WHERE revision_id = ?",
            (character.current_revision_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload.pop("name")
        connection.execute(
            "UPDATE character_revisions SET character_payload_json = ? WHERE revision_id = ?",
            (json.dumps(payload, ensure_ascii=False), character.current_revision_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            unit_of_work.characters.get_current_revision(character.character_id)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE character_revisions SET revision_contract_version = ? WHERE revision_id = ?",
            ("character-revision/99.0.0", character.current_revision_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceContractUnsupportedError):
            unit_of_work.characters.get_current_revision(character.character_id)


def test_edit_rollback_does_not_leave_orphan_revision(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    draft = _draft()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(draft)
        unit_of_work.connection.execute(
            """
            CREATE TRIGGER fail_character_pointer_update
            BEFORE UPDATE OF current_revision_id ON characters
            BEGIN
                SELECT RAISE(ABORT, 'forced pointer failure');
            END
            """
        )
        with pytest.raises(PersistenceIntegrityError):
            unit_of_work.characters.append_revision(
                character.character_id,
                replace(draft, name="不会保存"),
                expected_current_revision_id=character.current_revision_id,
            )
        assert len(unit_of_work.characters.list_revisions(character.character_id)) == 1


def _bootstrap_v1_database(database_path, artifact) -> int:
    created_at = "2026-01-01T00:00:00+00:00"
    envelope_json = json.dumps(
        artifact.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE persistence_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO persistence_meta (key, value) VALUES ('schema_version', '1');
            CREATE TABLE skill_artifact_contents (
                content_id INTEGER PRIMARY KEY,
                artifact_digest TEXT NOT NULL UNIQUE,
                canonical_schema_version TEXT NOT NULL,
                canonical_artifact_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE skill_artifact_records (
                record_id INTEGER PRIMARY KEY,
                content_id INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                artifact_contract_version TEXT NOT NULL,
                semantic_source_digest TEXT NOT NULL,
                artifact_envelope_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (content_id) REFERENCES skill_artifact_contents (content_id),
                FOREIGN KEY (artifact_digest) REFERENCES skill_artifact_contents (artifact_digest),
                UNIQUE (artifact_digest, artifact_envelope_json)
            );
            CREATE INDEX skill_artifact_records_by_digest
                ON skill_artifact_records (artifact_digest);
            """
        )
        connection.execute(
            """
            INSERT INTO skill_artifact_contents (
                artifact_digest, canonical_schema_version, canonical_artifact_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                artifact.artifact_digest,
                artifact.identity.canonical_schema_version,
                artifact.canonical_artifact.canonical_json(),
                created_at,
            ),
        )
        content_id = connection.execute(
            "SELECT content_id FROM skill_artifact_contents"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO skill_artifact_records (
                content_id, artifact_digest, artifact_contract_version,
                semantic_source_digest, artifact_envelope_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                content_id,
                artifact.artifact_digest,
                artifact.artifact_contract_version,
                artifact.semantic_source_digest,
                envelope_json,
                created_at,
            ),
        )
        return connection.execute("SELECT record_id FROM skill_artifact_records").fetchone()[0]


def test_schema_v1_migrates_to_v2_without_changing_skill_artifact(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    artifact = _skill_artifact()
    record_id = _bootstrap_v1_database(database_path, artifact)

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert unit_of_work.schema_version == 4
        restored = unit_of_work.skill_artifacts.get(record_id)
        assert restored.artifact == artifact
        assert unit_of_work.characters.exists("missing-character") is False
        assert (
            unit_of_work.connection.execute(
                "SELECT COUNT(*) FROM skill_artifact_contents"
            ).fetchone()[0]
            == 1
        )
        assert (
            unit_of_work.connection.execute(
                "SELECT COUNT(*) FROM skill_artifact_records"
            ).fetchone()[0]
            == 1
        )


def test_character_revision_payload_excludes_runtime_and_skill_state(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    draft = _draft()
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = unit_of_work.characters.create(draft)

    with sqlite3.connect(database_path) as connection:
        payload = connection.execute(
            "SELECT character_payload_json FROM character_revisions WHERE revision_id = ?",
            (character.current_revision_id,),
        ).fetchone()[0]

    assert "draft_id" not in payload
    assert '"status"' not in payload
    assert "attachedSkills" not in payload
    assert "roleCoverage" not in payload
