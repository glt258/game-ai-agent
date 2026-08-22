from __future__ import annotations

from dataclasses import dataclass
from agents import (
    CharacterDraft,
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
from combat_semantics import CombatRoleProfile


def _subject(*, intent: CharacterDesignIntent, primary_role: str = "support", rarity: int | None = None, role_type: str = "character") -> EvaluationSubject:
    request = CharacterDesignRequest(intent.raw_request or "设计一个角色。", request_id="request_alignment_test")
    del rarity, role_type
    draft = CharacterDraft.from_mapping(
        {
            "draft_id": "draft_request_alignment",
            "status": "draft",
            "name": "对齐角色",
            "canonical_character_id": None,
            "age": None,
            "age_range": None,
            "gender": None,
            "faction_id": None,
            "occupation": "职业",
            "social_role": "角色",
            "combat_role_profile": {"primary_role": primary_role, "secondary_roles": []},
            "design_pitch": "设计概念",
            "personality": ["冷静"],
            "background": "背景",
            "story_hook": "钩子",
            "relationships": [],
            "ability_concept": "能力",
            "knowledge_scope": "公开信息",
            "canon_basis": [],
            "new_design_elements": [],
            "open_questions": [],
            "constraint_notes": [],
            "story_link": None,
            "proposed_new_content": [],
        }
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
        combat_role_profile=CombatRoleProfile(primary_role="support"),
        rarity=5,
        raw_request="设计一个五星辅助角色。",
    )

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, rarity=5)
    )

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_non_role_legacy_input_does_not_create_a_role_mismatch():
    intent = CharacterDesignIntent.from_mapping(
        {"combat_role": "burst", "raw_request": "设计一个爆发角色。"}
    )

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, primary_role="support")
    )

    assert result.findings == ()
    assert result.outcome == EvaluationOutcome.PASS


def test_findings_ordering_is_deterministic():
    intent = CharacterDesignIntent.from_mapping(
        {
            "combat_role": "burst",
            "raw_request": "设计一个爆发角色。",
        }
    )
    runner = EvaluationRunner([RequestAlignmentValidator()])

    first = runner.run(_subject(intent=intent, primary_role="support"))
    second = runner.run(_subject(intent=intent, primary_role="support"))

    assert first.findings == ()
    assert first.to_dict() == second.to_dict()
