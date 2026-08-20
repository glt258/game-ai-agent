from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from agents import (
    CharacterDesignRequest,
    CharacterGenerationAudit,
    CharacterGenerationResult,
)
from agents.evaluation import (
    EvaluationContext,
    EvaluationOutcome,
    EvaluationRunner,
    EvaluationSubject,
    RequestAlignmentValidator,
)
from character_intelligence import CharacterDesignIntent
from character_intelligence.planner import CharacterDesignPlan


def _subject(*, intent: CharacterDesignIntent, combat_role: str = "support", rarity: int | None = None, role_type: str = "character") -> EvaluationSubject:
    request = CharacterDesignRequest(intent.raw_request or "设计一个角色。", request_id="request_alignment_test")
    draft = SimpleNamespace(
        combat_role=combat_role,
        rarity=rarity,
        role_type=role_type,
    )
    generation = CharacterGenerationResult(
        draft=draft,  # type: ignore[arg-type]
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


def test_matching_intent_returns_no_findings():
    intent = CharacterDesignIntent(
        role_type="character",
        combat_role="support",
        rarity=5,
        raw_request="设计一个五星辅助角色。",
    )

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, rarity=5)
    )

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_combat_role_mismatch_produces_blocking_finding():
    intent = CharacterDesignIntent(combat_role="burst", raw_request="设计一个爆发角色。")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, combat_role="support")
    )

    finding = result.findings[0]
    assert finding.code == "REQUEST_COMBAT_ROLE_MISMATCH"
    assert finding.severity == "ERROR"
    assert finding.blocking is True
    assert result.outcome == EvaluationOutcome.FAIL


def test_rarity_mismatch_produces_warning():
    intent = CharacterDesignIntent(rarity=5, raw_request="设计一个五星角色。")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, rarity=4)
    )

    finding = result.findings[0]
    assert finding.code == "REQUEST_RARITY_MISMATCH"
    assert finding.severity == "WARNING"
    assert finding.blocking is False
    assert result.outcome == EvaluationOutcome.WARN


def test_role_type_mismatch_produces_blocking_finding():
    intent = CharacterDesignIntent(role_type="少女", raw_request="设计一个少女角色。")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, role_type="character")
    )

    finding = result.findings[0]
    assert finding.code == "REQUEST_ROLE_TYPE_MISMATCH"
    assert finding.severity == "ERROR"
    assert finding.blocking is True
    assert result.outcome == EvaluationOutcome.FAIL


def test_findings_ordering_is_deterministic():
    intent = CharacterDesignIntent(
        role_type="少女",
        combat_role="burst",
        rarity=5,
        raw_request="设计一个五星少女爆发角色。",
    )
    runner = EvaluationRunner([RequestAlignmentValidator()])

    first = runner.run(_subject(intent=intent, combat_role="support", rarity=4, role_type="character"))
    second = runner.run(_subject(intent=intent, combat_role="support", rarity=4, role_type="character"))

    assert [finding.code for finding in first.findings] == [
        "REQUEST_COMBAT_ROLE_MISMATCH",
        "REQUEST_RARITY_MISMATCH",
        "REQUEST_ROLE_TYPE_MISMATCH",
    ]
    assert first.to_dict() == second.to_dict()
