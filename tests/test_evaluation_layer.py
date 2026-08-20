from __future__ import annotations

from dataclasses import dataclass

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
)
from agents.evaluation import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationFinding,
    EvaluationOutcome,
    EvaluationResult,
    EvaluationRunner,
    EvaluationSubject,
)


def _subject() -> EvaluationSubject:
    request = CharacterDesignRequest("设计一个原创辅助角色。", request_id="eval_foundation")
    draft = CharacterDraft.from_mapping(
        {
            "draft_id": "draft_eval_foundation",
            "status": "draft",
            "name": "评估角色",
            "canonical_character_id": None,
            "age": None,
            "age_range": None,
            "gender": None,
            "faction_id": None,
            "occupation": "独立设计者",
            "social_role": "原创角色",
            "combat_role": "support",
            "design_pitch": "有限的辅助能力。",
            "personality": ["冷静"],
            "background": "原创背景。",
            "story_hook": "原创钩子。",
            "relationships": [],
            "ability_concept": "有限的辅助能力。",
            "knowledge_scope": "公开信息。",
            "canon_basis": [],
            "new_design_elements": ["原创角色"],
            "open_questions": [],
            "constraint_notes": [],
            "story_link": None,
            "proposed_new_content": [],
        }
    )
    generation = CharacterGenerationResult(
        draft=draft,
        sources=(),
        audit=CharacterGenerationAudit(
            request_id=request.request_id,
            tool_rounds=0,
            tool_calls=(),
            source_ids=(),
        ),
    )
    return EvaluationSubject(request=request, generation_result=generation)


def test_evaluation_result_serialization():
    result = EvaluationResult(
        schema_version=EVALUATION_SCHEMA_VERSION,
        evaluation_id="evaluation:eval_foundation",
        request_id="eval_foundation",
        outcome=EvaluationOutcome.WARN,
        blocking=False,
        dimensions=("canon",),
        findings=(
            EvaluationFinding(
                validator_id="canon",
                code="PROPOSAL_REVIEW",
                severity="warning",
                blocking=False,
                stage="initial",
                field_path="background",
                message="proposal requires review",
            ),
        ),
    )

    assert result.to_dict() == {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": "evaluation:eval_foundation",
        "request_id": "eval_foundation",
        "outcome": "warn",
        "blocking": False,
        "dimensions": ["canon"],
        "findings": [
            {
                "validator_id": "canon",
                "code": "PROPOSAL_REVIEW",
                "severity": "warning",
                "blocking": False,
                "stage": "initial",
                "field_path": "background",
                "message": "proposal requires review",
            }
        ],
    }


def test_evaluation_subject_creation():
    subject = _subject()

    assert subject.request.request_id == "eval_foundation"
    assert subject.generation_result is not None
    assert subject.authoring_result is None
    assert subject.generation_error is None


def test_empty_evaluation_passes():
    result = EvaluationRunner([]).run(_subject())

    assert result.outcome == EvaluationOutcome.PASS
    assert result.blocking is False
    assert result.dimensions == ()
    assert result.findings == ()


@dataclass(frozen=True)
class _UnorderedValidator:
    validator_id: str = "fixture"
    dimension: str = "canon"

    def validate(self, subject: EvaluationSubject):
        del subject
        return (
            EvaluationFinding("fixture", "Z_CODE", "warning", False, "final", "z", "z"),
            EvaluationFinding("fixture", "A_CODE", "warning", False, "initial", "a", "a"),
        )


def test_runner_orders_findings_and_dimensions_deterministically():
    result = EvaluationRunner([_UnorderedValidator()]).run(_subject())

    assert result.dimensions == ("canon",)
    assert [finding.code for finding in result.findings] == ["A_CODE", "Z_CODE"]
    assert result.to_dict() == EvaluationRunner([_UnorderedValidator()]).run(
        _subject()
    ).to_dict()
