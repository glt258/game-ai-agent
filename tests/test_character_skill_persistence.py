from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest
from character_skill_fixtures import _context, _controlled_artifact

from agents.character_generation import CharacterDraft
from agents.response_contracts import character_draft_root_example
from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_association import (
    SkillSlot,
    build_character_skill_association,
)
from character_intelligence.skill_artifact import current_skill_artifact_versions
from persistence.character_persistence import CharacterPersistenceService
from persistence.character_skill_persistence import CharacterSkillPersistenceService
from persistence.errors import (
    CharacterSkillPersistenceConflictError,
    PersistenceContractUnsupportedError,
    PersistenceIntegrityError,
)
from persistence.sqlite_store import PersistenceUnitOfWork


def _draft(name: str = "林澈") -> CharacterDraft:
    payload = character_draft_root_example()
    payload.update(
        {
            "draft_id": "draft_skill_persistence_001",
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


def _association(case_id: str, context, slot: SkillSlot):
    family, mode = {
        "character_alignment_support_v1": ("support", "active"),
        "generalization_defense_v1": ("defense", "reaction"),
        "generalization_basic_passive_v1": ("basic_passive", "passive"),
    }[case_id]
    artifact = _controlled_artifact(case_id, family, mode)
    alignment = evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=context,
            skill_family=family,
            skill_mode=mode,
            candidate=artifact.canonical_artifact,
            skill_evaluation=artifact.original_evaluation,
            artifact_digest=artifact.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
        )
    )
    assert alignment.status == "PASS"
    return build_character_skill_association(
        artifact,
        context,
        alignment,
        slot=slot,
        family=family,
        mode=mode,
        display_summary=f"{case_id} summary",
    )


def _character(unit_of_work: PersistenceUnitOfWork):
    return unit_of_work.characters.create(_draft())


def _save_association_artifact(unit_of_work: PersistenceUnitOfWork, association) -> int:
    return unit_of_work.skill_artifacts.save(association.artifact).record_id


def test_schema_v3_migrates_v2_and_preserves_character_and_artifact(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")
    association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        record_id = _save_association_artifact(unit_of_work, association)

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE persistence_meta SET value = '2' WHERE key = 'schema_version'")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert unit_of_work.schema_version == 3
        assert (
            unit_of_work.characters.get_character(character.character_id).current_revision_id
            == character.current_revision_id
        )
        assert unit_of_work.skill_artifacts.get(record_id).artifact == association.artifact


def test_attach_persists_exact_binding_association_kit_and_reconstructs_after_restart(
    tmp_path,
) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        state = service.attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
            character.character_id,
            current_context=context,
        )

    assert state.character_revision_id == character.current_revision_id
    assert len(state.active_associations) == 1
    assert state.active_associations[0].association_id != association.association_id
    assert state.active_associations[0].association.artifact == association.artifact
    assert state.active_associations[0].association.binding == association.binding
    assert state.current_kit is not None
    assert state.current_kit.kit_digest == state.current_kit.kit_digest
    assert (
        state.freshness_by_association_id[state.active_associations[0].association_id] == "current"
    )
    assert state.structural_validation.status == "PASS"


def test_attach_two_passives_preserves_order_and_kit_content_deduplicates_across_characters(
    tmp_path,
) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        first_character = _character(unit_of_work)
        second_character = unit_of_work.characters.create(_draft("顾澄"))
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        associations = []
        first_assignment = None
        for case_id in (
            "generalization_basic_passive_v1",
            "generalization_defense_v1",
        ):
            association = _association(case_id, context, SkillSlot.PASSIVE)
            record_id = _save_association_artifact(unit_of_work, association)
            associations.append((association, record_id))
            state = service.attach(
                first_character.character_id,
                association,
                artifact_record_id=record_id,
                expected_character_revision_id=first_character.current_revision_id,
                expected_current_kit_assignment_id=first_assignment,
                current_context=context,
            )
            first_assignment = state.current_kit_assignment_id

        second_assignment = None
        for association, record_id in associations:
            second_state = service.attach(
                second_character.character_id,
                association,
                artifact_record_id=record_id,
                expected_character_revision_id=second_character.current_revision_id,
                expected_current_kit_assignment_id=second_assignment,
                current_context=context,
            )
            second_assignment = second_state.current_kit_assignment_id
        first_state = service.load_current_state(
            first_character.character_id, current_context=context
        )
        second_state = service.load_current_state(
            second_character.character_id, current_context=context
        )
        kit_records = unit_of_work.connection.execute(
            """
            SELECT kit_record_id FROM character_kit_assignments
            WHERE assignment_id IN (?, ?)
            """,
            (first_state.current_kit_assignment_id, second_state.current_kit_assignment_id),
        ).fetchall()

    assert [item.ordinal for item in first_state.active_associations] == [0, 1]
    assert first_state.current_kit is not None
    assert second_state.current_kit is not None
    assert first_state.current_kit.kit_digest == second_state.current_kit.kit_digest
    assert len(kit_records) == 2
    assert kit_records[0][0] == kit_records[1][0]


def test_placement_change_and_detach_preserve_association_history(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        attached = service.attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        durable_id = attached.active_associations[0].association_id
        moved = service.change_placement(
            character.character_id,
            durable_id,
            slot=SkillSlot.SECONDARY,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=attached.current_kit_assignment_id,
            current_context=context,
        )
        detached = service.detach(
            character.character_id,
            durable_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=moved.current_kit_assignment_id,
            current_context=context,
        )
        history = unit_of_work.character_skills.list_association_revisions(
            character.character_id,
            durable_id,
        )

    assert [item.placement for item in history] == [SkillSlot.PRIMARY, SkillSlot.SECONDARY]
    assert detached.active_associations == ()
    assert detached.current_kit is not None
    assert detached.current_kit.associations == ()


def test_replace_closes_old_association_and_creates_new_identity(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        old = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        new = _association("generalization_defense_v1", context, SkillSlot.PRIMARY)
        old_record_id = _save_association_artifact(unit_of_work, old)
        new_record_id = _save_association_artifact(unit_of_work, new)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        attached = service.attach(
            character.character_id,
            old,
            artifact_record_id=old_record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        replaced = service.replace(
            character.character_id,
            attached.active_associations[0].association_id,
            new,
            artifact_record_id=new_record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=attached.current_kit_assignment_id,
            current_context=context,
        )
        old_history = unit_of_work.character_skills.list_association_revisions(
            character.character_id,
            attached.active_associations[0].association_id,
        )

    assert (
        replaced.active_associations[0].association_id
        != attached.active_associations[0].association_id
    )
    assert old_history
    assert replaced.active_associations[0].association.artifact == new.artifact


def test_character_and_kit_guards_reject_stale_operations_without_mutation(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        attached = service.attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        with pytest.raises(CharacterSkillPersistenceConflictError):
            service.attach(
                character.character_id,
                association,
                artifact_record_id=record_id,
                expected_character_revision_id="stale-character-revision",
                expected_current_kit_assignment_id=attached.current_kit_assignment_id,
                current_context=context,
            )
        with pytest.raises(CharacterSkillPersistenceConflictError):
            service.change_placement(
                character.character_id,
                attached.active_associations[0].association_id,
                slot=SkillSlot.SECONDARY,
                expected_character_revision_id=character.current_revision_id,
                expected_current_kit_assignment_id="stale-assignment",
                current_context=context,
            )
        assert (
            len(
                service.load_current_state(
                    character.character_id, current_context=context
                ).active_associations
            )
            == 1
        )


def test_freshness_and_compatibility_are_derived_after_restart(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")
    changed_context = _context("顾澄")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        state = service.attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        current = service.load_current_state(character.character_id, current_context=context)
        stale = service.load_current_state(character.character_id, current_context=changed_context)

    durable_id = state.active_associations[0].association_id
    assert current.freshness_by_association_id[durable_id] == "current"
    assert stale.freshness_by_association_id[durable_id] == "stale"
    assert current.compatibility_by_association_id[durable_id].status.value == "CURRENT_COMPATIBLE"
    drifted_versions = replace(
        current_skill_artifact_versions(), compiler_version="compiler/future"
    )
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        drifted = CharacterSkillPersistenceService(
            unit_of_work.character_skills
        ).load_current_state(
            character.character_id,
            current_context=context,
            current_versions=drifted_versions,
        )
    assert drifted.compatibility_by_association_id[durable_id].status.value == "RECOMPILE_REQUIRED"


def test_irrelevant_character_edit_does_not_make_binding_stale(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        edited_draft = replace(character.current_revision.draft, age=35)
        CharacterPersistenceService(unit_of_work.characters).save_edited_character(
            character.character_id,
            edited_draft,
            expected_current_revision_id=character.current_revision_id,
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        loaded = CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
            character.character_id, current_context=context
        )

    durable_id = state.active_associations[0].association_id
    assert loaded.freshness_by_association_id[durable_id] == "current"


def test_tampered_binding_kit_relation_and_assignment_fail_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        binding_id = state.active_associations[0].binding_id
        assignment_id = state.current_kit_assignment_id
        original_kit_payload = unit_of_work.connection.execute(
            "SELECT kit_payload_json FROM character_kit_contents WHERE kit_record_id = (SELECT kit_record_id FROM character_kit_assignments WHERE assignment_id = ?)",
            (assignment_id,),
        ).fetchone()[0]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE bindings SET source_context_fingerprint = ? WHERE binding_id = ?",
            ("0" * 64, binding_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
                character.character_id,
                current_context=context,
            )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE character_kit_contents SET kit_payload_json = ? WHERE kit_digest = (SELECT kit_digest FROM character_kit_assignments WHERE assignment_id = ?)",
            (original_kit_payload, assignment_id),
        )
        connection.execute(
            "UPDATE character_kit_current SET current_assignment_id = ? WHERE character_id = ?",
            ("missing-assignment", character.character_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
                character.character_id,
                current_context=context,
            )


def test_tampered_association_relation_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        durable_id = state.active_associations[0].association_id

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE association_revisions SET placement = ?, placement_order = ? WHERE association_id = ? AND revision_sequence = 1",
            ("secondary", 1, durable_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceIntegrityError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
                character.character_id,
                current_context=context,
            )


def test_detach_rollback_keeps_old_association_and_kit_current(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        attached = service.attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        unit_of_work.connection.execute(
            """
            CREATE TRIGGER fail_detach_kit_content
            BEFORE INSERT ON character_kit_contents
            BEGIN SELECT RAISE(ABORT, 'forced Kit content failure'); END
            """
        )
        with pytest.raises(PersistenceIntegrityError):
            service.detach(
                character.character_id,
                attached.active_associations[0].association_id,
                expected_character_revision_id=character.current_revision_id,
                expected_current_kit_assignment_id=attached.current_kit_assignment_id,
                current_context=context,
            )
        current = service.load_current_state(character.character_id, current_context=context)

    assert len(current.active_associations) == 1
    assert current.current_kit_assignment_id == attached.current_kit_assignment_id


def test_replace_rollback_keeps_old_association_current(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        old = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        new = _association("generalization_defense_v1", context, SkillSlot.PRIMARY)
        old_record_id = _save_association_artifact(unit_of_work, old)
        new_record_id = _save_association_artifact(unit_of_work, new)
        service = CharacterSkillPersistenceService(unit_of_work.character_skills)
        attached = service.attach(
            character.character_id,
            old,
            artifact_record_id=old_record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )
        unit_of_work.connection.execute(
            """
            CREATE TRIGGER fail_replace_assignment
            BEFORE UPDATE OF current_assignment_id ON character_kit_current
            BEGIN SELECT RAISE(ABORT, 'forced assignment failure'); END
            """
        )
        with pytest.raises(PersistenceIntegrityError):
            service.replace(
                character.character_id,
                attached.active_associations[0].association_id,
                new,
                artifact_record_id=new_record_id,
                expected_character_revision_id=character.current_revision_id,
                expected_current_kit_assignment_id=attached.current_kit_assignment_id,
                current_context=context,
            )
        current = service.load_current_state(character.character_id, current_context=context)

    assert (
        current.active_associations[0].association_id
        == attached.active_associations[0].association_id
    )
    assert current.active_associations[0].association.artifact == old.artifact


def test_attach_rejects_stale_character_revision_without_mutation(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        edited = CharacterPersistenceService(unit_of_work.characters).save_edited_character(
            character.character_id,
            replace(_draft(), name="新版本"),
            expected_current_revision_id=character.current_revision_id,
        )
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        with pytest.raises(CharacterSkillPersistenceConflictError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
                character.character_id,
                association,
                artifact_record_id=record_id,
                expected_character_revision_id=character.current_revision_id,
                expected_current_kit_assignment_id=None,
                current_context=context,
            )
        assert (
            unit_of_work.characters.get_character(character.character_id).current_revision_id
            == edited.current_revision_id
        )
        assert (
            unit_of_work.connection.execute("SELECT COUNT(*) FROM associations").fetchone()[0] == 0
        )


def test_unsupported_kit_contract_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE character_kit_contents SET kit_contract_version = ? WHERE kit_record_id = (SELECT kit_record_id FROM character_kit_assignments WHERE assignment_id = ?)",
            ("character-kit/99.0.0", state.current_kit_assignment_id),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceContractUnsupportedError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
                character.character_id,
                current_context=context,
            )


def test_v2_to_v3_migration_failure_rolls_back_schema_version(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path):
        pass
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE persistence_meta SET value = '2' WHERE key = 'schema_version'")
        for table_name in (
            "character_kit_current",
            "character_kit_assignment_members",
            "character_kit_assignments",
            "character_kit_contents",
            "association_revisions",
            "associations",
            "bindings",
        ):
            connection.execute(f"DROP TABLE {table_name}")
        connection.execute("CREATE TABLE bindings (binding_id TEXT PRIMARY KEY)")

    with pytest.raises(PersistenceIntegrityError):
        PersistenceUnitOfWork(database_path)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
        ).fetchone() == ("2",)


def test_attach_rollback_leaves_no_partial_association_or_kit_assignment(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        unit_of_work.connection.execute(
            """
            CREATE TRIGGER fail_kit_assignment_insert
            BEFORE INSERT ON character_kit_assignments
            BEGIN SELECT RAISE(ABORT, 'forced kit assignment failure'); END
            """
        )
        with pytest.raises(PersistenceIntegrityError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
                character.character_id,
                association,
                artifact_record_id=record_id,
                expected_character_revision_id=character.current_revision_id,
                expected_current_kit_assignment_id=None,
                current_context=context,
            )
        assert (
            unit_of_work.connection.execute("SELECT COUNT(*) FROM associations").fetchone()[0] == 0
        )
        assert (
            unit_of_work.connection.execute(
                "SELECT COUNT(*) FROM character_kit_assignments"
            ).fetchone()[0]
            == 0
        )


def test_unsupported_binding_contract_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    context = _context("林澈")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character = _character(unit_of_work)
        association = _association("character_alignment_support_v1", context, SkillSlot.PRIMARY)
        record_id = _save_association_artifact(unit_of_work, association)
        state = CharacterSkillPersistenceService(unit_of_work.character_skills).attach(
            character.character_id,
            association,
            artifact_record_id=record_id,
            expected_character_revision_id=character.current_revision_id,
            expected_current_kit_assignment_id=None,
            current_context=context,
        )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE bindings SET binding_payload_json = ? WHERE binding_id = ?",
            (
                json.dumps(
                    {
                        **association.binding.to_mapping(),
                        "binding_contract_version": "character-skill-artifact-binding/99.0.0",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                state.active_associations[0].binding_id,
            ),
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        with pytest.raises(PersistenceContractUnsupportedError):
            CharacterSkillPersistenceService(unit_of_work.character_skills).load_current_state(
                character.character_id,
                current_context=context,
            )
