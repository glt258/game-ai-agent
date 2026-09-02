from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from character_intelligence.character_skill_alignment import (
    CHARACTER_SKILL_ALIGNMENT_VERSION,
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_projection import CharacterSkillDesignContext
from character_intelligence.compiler import COMPILER_VERSION_V2
from character_intelligence.hybrid_ir.playground import (
    build_playground_context,
    build_playground_evaluation_context,
    run_playground_context_pipeline,
)
from character_intelligence.hybrid_ir.runner import FakeProvider
from character_intelligence.semantic_ir import SEMANTIC_IR_V2_VERSION
from character_intelligence.skill_artifact import (
    ARTIFACT_CONTRACT_VERSION,
    ArtifactBindingError,
    ArtifactDriftStatus,
    SkillDesignArtifact,
    build_character_skill_artifact_binding,
    build_skill_design_artifact,
    inspect_skill_artifact_compatibility,
)
from character_skill import SCHEMA_VERSION
from character_skill.context import VALIDATOR_CONTRACT
from combat_semantics import CombatRoleProfile

ROOT = Path(__file__).resolve().parents[1]


def _fixture(case_id: str = "character_alignment_support_v1") -> dict[str, object]:
    path = ROOT / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json"
    return json.loads(path.read_text(encoding="utf-8"))[case_id]


def _pipeline():
    context = build_playground_context(
        "support",
        "active",
        "Design a structured Chinese support skill.",
    )
    result = run_playground_context_pipeline(
        FakeProvider(_fixture()),
        context,
        build_playground_evaluation_context("support", "active"),
        model="web-offline-fixture",
        language="zh-CN",
        repo_root=ROOT,
        invocation_id="artifact-test-run",
    )
    assert result.candidate is not None
    assert result.report is not None
    assert result.validated_ir is not None
    assert result.compiler_provenance is not None
    return result


def _character_context(name: str = "林澈") -> CharacterSkillDesignContext:
    return CharacterSkillDesignContext(
        character_name=name,
        combat_role_profile=CombatRoleProfile(primary_role="support"),
        ability_concept="帮助队友完成现场处置。",
        design_pitch="将观察与协作转化为战斗作用。",
    )


def test_artifact_factory_captures_real_versions_and_round_trips() -> None:
    result = _pipeline()
    artifact = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
        run_id=result.evidence.run_id,
        provider=result.evidence.identity.provider,
        model=result.evidence.identity.model,
    )

    assert artifact.artifact_contract_version == ARTIFACT_CONTRACT_VERSION
    assert artifact.identity.artifact_digest == result.candidate.digest
    assert artifact.versions.semantic_ir_schema_version == SEMANTIC_IR_V2_VERSION
    assert artifact.versions.compiler_version == COMPILER_VERSION_V2
    assert artifact.versions.canonical_skillkit_schema_version == SCHEMA_VERSION
    assert artifact.versions.skill_evaluator_version == VALIDATOR_CONTRACT
    assert artifact.versions.character_alignment_version is None
    assert artifact.provenance.run_id == "artifact-test-run"
    assert SkillDesignArtifact.from_mapping(artifact.to_mapping()) == artifact


def test_artifact_digest_ignores_character_evaluation_alignment_and_run_metadata() -> None:
    result = _pipeline()
    first = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
        run_id="run-a",
        provider="provider-a",
        model="model-a",
    )
    changed_report = replace(result.report, outcome="FAIL", blocking=True)
    second = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        changed_report,
        result.compiler_provenance,
        run_id="run-b",
        provider="provider-b",
        model="model-b",
    )
    assert first.identity.artifact_digest == second.identity.artifact_digest
    assert first.identity.artifact_digest == result.candidate.digest


def test_character_binding_keeps_alignment_outside_artifact_identity() -> None:
    result = _pipeline()
    character = _character_context()
    alignment = evaluate_character_skill_alignment(
        CharacterSkillAlignmentContext(
            character_context=character,
            skill_family="support",
            skill_mode="active",
            candidate=result.candidate,
            skill_evaluation=result.report,
            artifact_digest=result.candidate.digest,
            source_context_fingerprint=character.source_context_fingerprint,
        )
    )
    artifact = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
        alignment=alignment,
        character_context=character,
    )
    binding = build_character_skill_artifact_binding(artifact, character, alignment)
    assert artifact.identity.artifact_digest == result.candidate.digest
    assert binding.artifact_digest == artifact.identity.artifact_digest
    assert binding.source_context_fingerprint == character.source_context_fingerprint
    assert artifact.versions.character_alignment_version == CHARACTER_SKILL_ALIGNMENT_VERSION
    assert artifact.versions.character_context_projection_version == character.projection_version
    assert "character_name" not in artifact.to_mapping()


def test_character_name_is_a_semantic_fingerprint_input() -> None:
    first = _character_context("林澈")
    second = _character_context("顾澄")
    assert first.projection_version == "character-skill-context/0.2"
    assert first.source_context_fingerprint != second.source_context_fingerprint
    assert first.to_projection_mapping()["character_name"] == "林澈"


def test_alignment_fails_closed_for_mismatched_identity_values() -> None:
    result = _pipeline()
    character = _character_context()
    with pytest.raises(ArtifactBindingError, match="ARTIFACT_DIGEST_MISMATCH"):
        evaluate_character_skill_alignment(
            CharacterSkillAlignmentContext(
                character_context=character,
                skill_family="support",
                skill_mode="active",
                candidate=result.candidate,
                skill_evaluation=result.report,
                artifact_digest="0" * 64,
                source_context_fingerprint=character.source_context_fingerprint,
            )
        )
    with pytest.raises(ArtifactBindingError, match="SOURCE_CONTEXT_FINGERPRINT_MISMATCH"):
        evaluate_character_skill_alignment(
            CharacterSkillAlignmentContext(
                character_context=character,
                skill_family="support",
                skill_mode="active",
                candidate=result.candidate,
                skill_evaluation=result.report,
                artifact_digest=result.candidate.digest,
                source_context_fingerprint="1" * 64,
            )
        )


def test_artifact_factory_rejects_mismatched_evaluation_binding() -> None:
    result = _pipeline()
    bad_report = replace(result.report, candidate_digest="0" * 64)
    with pytest.raises(ArtifactBindingError, match="EVALUATION_CANDIDATE_DIGEST_MISMATCH"):
        build_skill_design_artifact(
            result.validated_ir,
            result.candidate,
            bad_report,
            result.compiler_provenance,
        )


def test_drift_inspection_is_deterministic_and_does_not_recompute() -> None:
    result = _pipeline()
    artifact = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
    )
    current = replace(
        artifact.versions,
        compiler_version="skillkit-compiler/9.9.9",
        skill_evaluator_version="skill-kit-validator/9.9.9",
    )
    inspection = inspect_skill_artifact_compatibility(artifact.versions, current)
    assert inspection.status == ArtifactDriftStatus.RECOMPILE_REQUIRED
    assert [item.code for item in inspection.findings] == [
        "ARTIFACT_COMPILER_VERSION_DRIFT",
        "ARTIFACT_EVALUATOR_VERSION_DRIFT",
    ]


def test_standalone_artifact_has_no_character_owner_or_binding() -> None:
    result = _pipeline()
    artifact = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
    )
    assert artifact.versions.character_alignment_version is None
    assert artifact.versions.character_context_projection_version is None
    assert artifact.provenance.run_id is None
    assert "character_id" not in artifact.to_mapping()


def test_unknown_artifact_contract_version_is_rejected() -> None:
    result = _pipeline()
    artifact = build_skill_design_artifact(
        result.validated_ir,
        result.candidate,
        result.report,
        result.compiler_provenance,
    )
    payload = copy.deepcopy(artifact.to_mapping())
    payload["artifact_contract_version"] = "skill-design-artifact/9.9.9"
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_VERSION_UNSUPPORTED"):
        SkillDesignArtifact.from_mapping(payload)
