from __future__ import annotations

import json
from pathlib import Path

import pytest
from character_skill_fixtures import _context, _controlled_artifact

from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_association import (
    CharacterSkillAssociationError,
    CharacterSkillCollection,
    SkillSlot,
    build_character_skill_association,
    slot_metadata,
)
from character_intelligence.hybrid_ir.playground import (
    build_playground_context,
    build_playground_evaluation_context,
    run_playground_context_pipeline,
)
from character_intelligence.hybrid_ir.runner import FakeProvider
from character_intelligence.skill_artifact import build_skill_design_artifact_from_pipeline_result

ROOT = Path(__file__).resolve().parents[1]


def _artifact(case_id: str = "character_alignment_support_v1"):
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json").read_text(
            encoding="utf-8"
        )
    )[case_id]
    context = build_playground_context("support", "active", "Association fixture")
    result = run_playground_context_pipeline(
        FakeProvider(fixture),
        context,
        build_playground_evaluation_context("support", "active"),
        model="web-offline-fixture",
        language="zh-CN",
        repo_root=ROOT,
        invocation_id="association-test-run",
    )
    assert result.candidate and result.report and result.validated_ir and result.compiler_provenance
    return build_skill_design_artifact_from_pipeline_result(result)


def _association(
    slot: SkillSlot | str,
    name: str = "林澈",
    case_id: str = "character_alignment_support_v1",
):
    artifact = _artifact(case_id)
    context = _context(name)
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
        slot=slot,
        family="support",
        mode="active",
        display_summary="Measured Rally",
    )


def test_slot_metadata_is_stable_and_independent_from_family_and_mode() -> None:
    values = slot_metadata()
    assert [item.slot for item in values] == [
        SkillSlot.PRIMARY,
        SkillSlot.SECONDARY,
        SkillSlot.PASSIVE,
        SkillSlot.UTILITY,
    ]
    assert [item.order for item in values] == [0, 1, 2, 3]
    assert _association("primary").slot == SkillSlot.PRIMARY
    assert _association("passive").mode == "active"
    assert _association("passive").family == "support"


def test_unknown_slot_is_rejected() -> None:
    with pytest.raises(CharacterSkillAssociationError, match="UNKNOWN_SLOT"):
        _association("ultimate")


def test_collection_is_ordered_and_supports_two_different_slots() -> None:
    first = _association(SkillSlot.SECONDARY, case_id="character_alignment_control_v1")
    second = _association(SkillSlot.PRIMARY, name="顾澄")
    collection = CharacterSkillCollection().attach(first).attach(second)
    assert [item.slot for item in collection.ordered] == [SkillSlot.PRIMARY, SkillSlot.SECONDARY]
    assert collection.ordered[0].artifact_digest == second.artifact_digest


def test_controlled_pipeline_artifacts_attach_to_one_character_context() -> None:
    context = _context("Controlled Character")
    definitions = (
        ("character_alignment_support_v1", "support", "active", SkillSlot.PRIMARY),
        ("generalization_defense_v1", "defense", "reaction", SkillSlot.SECONDARY),
        ("generalization_basic_passive_v1", "basic_passive", "passive", SkillSlot.PASSIVE),
    )
    associations = []
    for case_id, family, mode, slot in definitions:
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
        assert artifact.original_evaluation.outcome == "PASS"
        assert alignment.status == "PASS"
        associations.append(
            build_character_skill_association(
                artifact,
                context,
                alignment,
                slot=slot,
                family=family,
                mode=mode,
                display_summary=case_id,
            )
        )

    collection = CharacterSkillCollection().attach(associations[1]).attach(associations[0]).attach(associations[2])
    assert len(collection.ordered) == 3
    assert [item.slot for item in collection.ordered] == [SkillSlot.PRIMARY, SkillSlot.SECONDARY, SkillSlot.PASSIVE]
    assert len({item.artifact_digest for item in collection.ordered}) == 3
    assert {item.source_context_fingerprint for item in collection.ordered} == {context.source_context_fingerprint}


def test_duplicate_artifact_and_duplicate_slot_are_explicit() -> None:
    first = _association(SkillSlot.PRIMARY)
    with pytest.raises(CharacterSkillAssociationError, match="DUPLICATE_ARTIFACT"):
        CharacterSkillCollection((first, _association(SkillSlot.SECONDARY, name="顾澄")))
    with pytest.raises(CharacterSkillAssociationError, match="SLOT_OCCUPIED"):
        CharacterSkillCollection((first,)).attach(
            _association(
                SkillSlot.PRIMARY,
                name="顾澄",
                case_id="character_alignment_control_v1",
            )
        )


def test_replace_is_explicit_and_detach_removes_only_association() -> None:
    old = _association(SkillSlot.PRIMARY)
    replacement = _association(
        SkillSlot.PRIMARY,
        name="顾澄",
        case_id="character_alignment_control_v1",
    )
    collection = CharacterSkillCollection((old,)).replace(replacement)
    assert collection.ordered == (replacement,)
    assert collection.detach(replacement.association_id).ordered == ()
    assert replacement.artifact_digest != old.artifact_digest


def test_freshness_is_per_association_and_artifact_is_not_mutated() -> None:
    first = _association(SkillSlot.PRIMARY, name="林澈")
    second = _association(
        SkillSlot.SECONDARY,
        name="顾澄",
        case_id="character_alignment_control_v1",
    )
    collection = CharacterSkillCollection((first, second))
    assert first.freshness_for(_context("林澈")) == "current"
    assert first.freshness_for(_context("顾澄")) == "stale"
    assert second.freshness_for(_context("林澈")) == "stale"
    assert collection.ordered[0].artifact.versions == first.artifact.versions
