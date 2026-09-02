from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest
from character_skill_fixtures import _context, _controlled_artifact

from agents.character_generation import CharacterDraft
from agents.response_contracts import character_draft_root_example
from character_intelligence.character_kit_evaluation import (
    CharacterKitEvaluationContext,
    evaluate_character_kit_role_coverage,
)
from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_association import (
    SkillSlot,
    build_character_skill_association,
)
from persistence.errors import PersistenceIntegrityError
from persistence.sqlite_store import PersistenceUnitOfWork


def _draft(name: str = "林澈") -> CharacterDraft:
    payload = character_draft_root_example()
    payload.update(
        {
            "draft_id": "draft_historical_report_character",
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


def _association(context):
    artifact = _controlled_artifact("character_alignment_support_v1", "support", "active")
    alignment = evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=context,
            skill_family="support",
            skill_mode="active",
            candidate=artifact.canonical_artifact,
            skill_evaluation=artifact.original_evaluation,
            artifact_digest=artifact.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
        )
    )
    return build_character_skill_association(
        artifact,
        context,
        alignment,
        slot=SkillSlot.PRIMARY,
        family="support",
        mode="active",
        display_summary="中文技能摘要",
    )


def _attached_state(unit_of_work: PersistenceUnitOfWork):
    context = _context("林澈")
    character = unit_of_work.characters.create(_draft())
    association = _association(context)
    artifact_record_id = unit_of_work.skill_artifacts.save(association.artifact).record_id
    state = unit_of_work.character_skills.attach(
        character.character_id,
        association,
        artifact_record_id=artifact_record_id,
        expected_character_revision_id=character.current_revision_id,
        expected_current_kit_assignment_id=None,
        current_context=context,
    )
    kit_record_id = unit_of_work.connection.execute(
        "SELECT kit_record_id FROM character_kit_assignments WHERE assignment_id = ?",
        (state.current_kit_assignment_id,),
    ).fetchone()[0]
    return character, context, association, artifact_record_id, kit_record_id, state


def test_v3_to_v4_preserves_existing_character_skill_data(tmp_path) -> None:
    database_path = tmp_path / "历史" / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character, context, association, artifact_record_id, _, state = _attached_state(
            unit_of_work
        )

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE persistence_meta SET value = '3' WHERE key = 'schema_version'")

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        assert unit_of_work.schema_version == 4
        assert unit_of_work.skill_artifacts.get(artifact_record_id).artifact == association.artifact
        restored = unit_of_work.character_skills.load_current_state(
            character.character_id, current_context=context
        )
        assert restored.current_kit_assignment_id == state.current_kit_assignment_id
        assert restored.current_kit.kit_digest == state.current_kit.kit_digest


def test_skill_evaluation_history_is_typed_versioned_idempotent_and_restartable(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        _, _, association, artifact_record_id, _, _ = _attached_state(unit_of_work)
        report = association.artifact.original_evaluation
        first = unit_of_work.historical_reports.save_skill_evaluation(artifact_record_id, report)
        duplicate = unit_of_work.historical_reports.save_skill_evaluation(
            artifact_record_id, report
        )
        second_version = unit_of_work.historical_reports.save_skill_evaluation(
            artifact_record_id, report, evaluator_version="skill-kit-validator/2.0.0"
        )
        assert first.report_id == duplicate.report_id
        assert first.report_id != second_version.report_id
        assert [
            item.report_id
            for item in unit_of_work.historical_reports.list_skill_evaluations(artifact_record_id)
        ] == [
            first.report_id,
            second_version.report_id,
        ]

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        history = unit_of_work.historical_reports.list_skill_evaluations(artifact_record_id)
        assert [item.evaluator_version for item in history] == [
            association.artifact.versions.skill_evaluator_version,
            "skill-kit-validator/2.0.0",
        ]


def test_alignment_history_keeps_context_and_does_not_mutate_binding(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character, context, association, artifact_record_id, _, state = _attached_state(
            unit_of_work
        )
        stored = unit_of_work.historical_reports.save_alignment(
            character.character_id,
            character.current_revision_id,
            artifact_record_id,
            replace(association.binding.alignment, summary="中文历史 Alignment"),
        )
        duplicate = unit_of_work.historical_reports.save_alignment(
            character.character_id,
            character.current_revision_id,
            artifact_record_id,
            replace(association.binding.alignment, summary="中文历史 Alignment"),
        )
        assert stored.report_id == duplicate.report_id
        assert stored.source_context_fingerprint == context.source_context_fingerprint
        assert (
            unit_of_work.character_skills.get_binding(
                character.character_id, state.active_associations[0].binding_id
            ).binding.alignment.summary
            != "中文历史 Alignment"
        )

    with PersistenceUnitOfWork(database_path) as unit_of_work:
        history = unit_of_work.historical_reports.list_alignments(artifact_record_id)
        assert len(history) == 1
        assert history[0].report.summary == "中文历史 Alignment"


def test_role_coverage_history_binds_kit_and_character_revision(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        character, _, _, _, kit_record_id, state = _attached_state(unit_of_work)
        result = evaluate_character_kit_role_coverage(
            state.current_kit,
            CharacterKitEvaluationContext(_context("林澈").combat_role_profile),
        )
        stored = unit_of_work.historical_reports.save_role_coverage(
            character.character_id, character.current_revision_id, kit_record_id, result
        )
        assert stored.kit_digest == state.current_kit.kit_digest
        assert (
            unit_of_work.historical_reports.list_role_coverage(
                kit_record_id, character_revision_id=character.current_revision_id
            )[0].report
            == result
        )


def test_historical_report_tampering_and_deterministic_conflict_fail_closed(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        _, _, association, artifact_record_id, _, _ = _attached_state(unit_of_work)
        unit_of_work.historical_reports.save_skill_evaluation(
            artifact_record_id, association.artifact.original_evaluation
        )
        unit_of_work.connection.execute("DROP TRIGGER skill_evaluation_reports_immutable_update")
        unit_of_work.connection.execute(
            "UPDATE skill_evaluation_reports SET artifact_digest = ?",
            ("f" * 64,),
        )

    with pytest.raises(PersistenceIntegrityError):
        with PersistenceUnitOfWork(database_path) as unit_of_work:
            unit_of_work.historical_reports.list_skill_evaluations(artifact_record_id)


def test_reports_have_no_current_truth_columns_and_are_append_only(tmp_path) -> None:
    database_path = tmp_path / "studio.db"
    with PersistenceUnitOfWork(database_path) as unit_of_work:
        tables = {
            row[0]
            for row in unit_of_work.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert (
            not {"is_current", "is_stale", "current_compatibility", "current_role_coverage"}
            & tables
        )
        _, _, association, artifact_record_id, _, _ = _attached_state(unit_of_work)
        saved = unit_of_work.historical_reports.save_skill_evaluation(
            artifact_record_id, association.artifact.original_evaluation
        )
        with pytest.raises(sqlite3.IntegrityError):
            unit_of_work.connection.execute(
                "UPDATE skill_evaluation_reports SET report_digest = ? WHERE report_id = ?",
                ("f" * 64, saved.report_id),
            )
