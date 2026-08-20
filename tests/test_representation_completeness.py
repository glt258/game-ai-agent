from __future__ import annotations

from types import SimpleNamespace

from agents import CharacterDesignRequest, CharacterGenerationAudit, CharacterGenerationResult
from agents.evaluation import (
    EvaluationOutcome,
    EvaluationRunner,
    EvaluationSubject,
)
from character_intelligence import CharacterDesignIntent
from character_intelligence.planner import CharacterDesignPlan


def _subject(**overrides) -> EvaluationSubject:
    values = {
        "name": "完整角色",
        "description": "角色概述。",
        "personality": ("冷静",),
        "background": "角色背景。",
        "motivation": "保护同伴。",
        "conflict": "必须在责任与自由之间选择。",
        "combat_role": "support",
        "abilities": ("有限的辅助能力",),
    }
    values.update(overrides)
    request = CharacterDesignRequest(
        "设计一个辅助角色。",
        request_id="representation_test",
    )
    intent = CharacterDesignIntent(
        combat_role="support",
        raw_request=request.brief,
    )
    generation = CharacterGenerationResult(
        draft=SimpleNamespace(**values),  # type: ignore[arg-type]
        sources=(),
        audit=CharacterGenerationAudit(
            request_id=request.request_id,
            tool_rounds=0,
            tool_calls=(),
            source_ids=(),
        ),
        design_plan=CharacterDesignPlan.from_intent(intent),
    )
    return EvaluationSubject(request=request, generation_result=generation)


def test_complete_character_passes():
    result = EvaluationRunner().run(_subject())

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_missing_motivation_produces_warning():
    result = EvaluationRunner().run(_subject(motivation=""))

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.code == "MISSING_MOTIVATION"
    assert finding.severity == "WARNING"
    assert finding.blocking is False
    assert result.outcome == EvaluationOutcome.WARN


def test_multiple_missing_fields_have_deterministic_ordering():
    result = EvaluationRunner().run(
        _subject(
            description="",
            personality=(),
            motivation="",
            conflict="",
            abilities=(),
        )
    )

    assert [finding.code for finding in result.findings] == [
        "MISSING_ABILITIES",
        "MISSING_CHARACTER_DESCRIPTION",
        "MISSING_CONFLICT",
        "MISSING_MOTIVATION",
        "MISSING_PERSONALITY",
    ]
    assert result.to_dict() == EvaluationRunner().run(
        _subject(
            description="",
            personality=(),
            motivation="",
            conflict="",
            abilities=(),
        )
    ).to_dict()
