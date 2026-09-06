from fastapi.testclient import TestClient

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
)
from agents.evaluation import EvaluationOutcome, EvaluationRunner, EvaluationSubject
from character_intelligence import CharacterDesignPlan
from web.app import create_app


def _subject(
    *,
    personality,
    ability_concept,
    brief=None,
    hard_constraints=(),
    background="无额外背景。",
    design_pitch="原创角色。",
    story_hook="原创钩子。",
):
    request = CharacterDesignRequest(
        brief=brief
        or "设计一个胆小、谨慎、极度回避危险、不喜欢成为注意焦点、不愿主动与敌人发生正面冲突的主输出角色。",
        hard_constraints=hard_constraints,
        request_id="personality_gameplay_alignment_test",
    )
    draft = CharacterDraft.from_mapping(
        {
            "draft_id": "draft_personality_gameplay_alignment",
            "status": "draft",
            "name": "谨慎角色",
            "canonical_character_id": None,
            "age": None,
            "age_range": None,
            "gender": None,
            "faction_id": None,
            "occupation": "原创设计者",
            "social_role": "原创角色",
            "combat_role_profile": {"primary_role": "main_dps", "secondary_roles": []},
            "design_pitch": design_pitch,
            "personality": personality,
            "background": background,
            "story_hook": story_hook,
            "relationships": [],
            "ability_concept": ability_concept,
            "knowledge_scope": "公开信息。",
            "canon_basis": [],
            "new_design_elements": ["原创角色"],
            "open_questions": [],
            "constraint_notes": [],
            "story_link": None,
            "proposed_new_content": [],
        }
    )
    plan = CharacterDesignPlan.from_text(request.brief)
    generation = CharacterGenerationResult(
        draft=draft,
        sources=(),
        audit=CharacterGenerationAudit(
            request_id=request.request_id,
            tool_rounds=0,
            tool_calls=(),
            source_ids=(),
        ),
        design_plan=plan,
    )
    return EvaluationSubject(request=request, generation_result=generation)


def test_real_conflict_is_blocking():
    result = EvaluationRunner().run(
        _subject(
            personality=["胆小", "谨慎", "极度回避危险", "不喜欢成为注意焦点"],
            ability_concept="长时间站场，主动吸引敌人攻击，并在高风险状态下获得更高输出。",
        )
    )

    assert result.outcome == EvaluationOutcome.FAIL
    assert result.blocking is True
    assert any(
        finding.code == "PERSONALITY_GAMEPLAY_CONFLICT" and finding.blocking
        for finding in result.findings
    )


def test_safe_ranged_main_dps_is_compatible_with_risk_avoidance():
    result = EvaluationRunner().run(
        _subject(
            brief="设计一个谨慎的主输出角色。",
            personality=["谨慎", "胆小"],
            ability_concept="从安全距离进行远程爆发输出，预先准备后再行动。",
        )
    )

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_protective_risk_is_a_productive_bridge():
    result = EvaluationRunner().run(
        _subject(
            personality=["谨慎", "不喜欢成为注意焦点"],
            ability_concept="通常保持距离，只有在队友受到威胁时才主动吸引敌人攻击，以保护队友。",
        )
    )

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_combat_role_alone_does_not_create_a_conflict():
    result = EvaluationRunner().run(
        _subject(
            brief="设计一个安静、低调的主输出角色。",
            personality=["安静", "低调"],
            ability_concept="持续站场输出。",
        )
    )

    assert result.outcome == EvaluationOutcome.PASS
    assert result.findings == ()


def test_direct_confrontation_conflict_is_blocking():
    result = EvaluationRunner().run(
        _subject(
            brief="设计一个回避正面冲突的角色。",
            personality=["避免正面冲突"],
            ability_concept="主动近战，贴脸正面迎战敌人。",
        )
    )

    assert result.outcome == EvaluationOutcome.FAIL
    assert result.blocking is True
    assert any(finding.code == "PERSONALITY_GAMEPLAY_CONFLICT" for finding in result.findings)


def test_character_validation_api_exposes_the_alignment_finding():
    subject = _subject(
        personality=["胆小", "谨慎", "不喜欢成为注意焦点"],
        ability_concept="长时间站场，主动吸引敌人攻击，并在高风险状态下获得更高输出。",
    )
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={
            "request": subject.request.to_dict(),
            "draft": subject.generation_result.draft.to_dict(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert any(
        item["name"] == "personality_gameplay_alignment"
        and item["code"] == "PERSONALITY_GAMEPLAY_CONFLICT"
        and item["blocking"] is True
        for item in body["validators"]
    )
