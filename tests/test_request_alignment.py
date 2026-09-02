from __future__ import annotations

import pytest

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
)
from agents.evaluation import (
    EvaluationOutcome,
    EvaluationRunner,
    EvaluationSubject,
    IdentityCoherenceValidator,
    RequestAlignmentValidator,
)
from character_intelligence import CharacterDesignIntent
from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile
from knowledge.resolver import KnowledgeResolver


def _subject(*, intent: CharacterDesignIntent, primary_role: str = "support", rarity: int | None = None, role_type: str = "character", faction_id: str | None = None, plan: CharacterDesignPlan | None = None, occupation: str = "职业", social_role: str = "角色", background: str = "背景", design_pitch: str = "设计概念") -> EvaluationSubject:
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
            "faction_id": faction_id,
            "occupation": occupation,
            "social_role": social_role,
            "combat_role_profile": {"primary_role": primary_role, "secondary_roles": []},
            "design_pitch": design_pitch,
            "personality": ["冷静"],
            "background": background,
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
        design_plan=plan or CharacterDesignPlan.from_intent(intent),
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


@pytest.mark.parametrize("draft_faction_id", [None, "faction_002"])
def test_explicit_affiliation_must_match_requested_faction(draft_faction_id):
    intent = CharacterDesignIntent(
        raw_request="角色必须属于 faction_005。",
        requested_affiliation_id="faction_005",
        combat_role_profile=CombatRoleProfile(primary_role="support"),
    )

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, faction_id=draft_faction_id)
    )

    assert [
        (finding.code, finding.field_path, finding.blocking)
        for finding in result.findings
    ] == [
        ("AFFILIATION_CONSTRAINT_UNSATISFIED", "faction_id", True)
    ] if draft_faction_id != "faction_005" else []
    assert result.outcome == (
        EvaluationOutcome.FAIL if draft_faction_id != "faction_005" else EvaluationOutcome.PASS
    )


def test_affiliation_is_not_required_when_request_has_no_explicit_affiliation():
    intent = CharacterDesignIntent(
        raw_request="设计一个原创辅助角色。",
        combat_role_profile=CombatRoleProfile(primary_role="support"),
    )

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent=intent, faction_id=None)
    )

    assert result.findings == ()
    assert result.outcome == EvaluationOutcome.PASS


def test_identity_coherence_rejects_campus_identity_under_public_safety_affiliation():
    plan = CharacterDesignPlan.from_text(
        "设计一个必须属于临洲市公共安全联席体系的女性辅助角色。",
        factions=KnowledgeResolver().factions,
    )

    result = EvaluationRunner([IdentityCoherenceValidator()]).run(
        _subject(
            intent=plan.parsed_intent,
            plan=plan,
            faction_id="faction_005",
            occupation="临洲大学学生助理",
            social_role="校园活动与社区安全志愿协调者",
            background="她在校园与社区活动中逐渐形成了谨慎处理复杂关系的习惯。",
        )
    )

    assert result.outcome == EvaluationOutcome.FAIL
    assert [
        (finding.code, finding.field_path, finding.blocking)
        for finding in result.findings
    ] == [("IDENTITY_AFFILIATION_INCONSISTENT", "occupation", True)]


def test_identity_coherence_accepts_identity_grounded_in_affiliation_context():
    plan = CharacterDesignPlan.from_text(
        "设计一个必须属于临洲市公共安全联席体系的女性辅助角色。",
        factions=KnowledgeResolver().factions,
    )
    context = plan.affiliation_context
    assert context is not None

    result = EvaluationRunner([IdentityCoherenceValidator()]).run(
        _subject(
            intent=plan.parsed_intent,
            plan=plan,
            faction_id="faction_005",
            occupation=context.typical_roles[0],
            social_role=f"参与{context.name}相关现场协调与信息联络",
            background=f"她在{context.semantic_terms[0]}相关工作中积累了现场协作经验。",
        )
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
