from __future__ import annotations

from agents import CharacterDesignRequest, CharacterGenerationAudit, CharacterGenerationResult
from agents import CharacterDraft
from agents.evaluation import (
    EvaluationOutcome,
    EvaluationRunner,
    EvaluationSubject,
)
from character_intelligence import CharacterDesignIntent
from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile


def _subject(**overrides) -> EvaluationSubject:
    values = {
        "name": "完整角色",
        "design_pitch": "角色概述。",
        "personality": ("冷静",),
        "background": "角色背景。",
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "ability_concept": "有限的辅助能力",
    }
    values.update(overrides)
    request = CharacterDesignRequest(
        "设计一个辅助角色。",
        request_id="representation_test",
    )
    intent = CharacterDesignIntent(
        combat_role_profile=CombatRoleProfile(primary_role="support"),
        raw_request=request.brief,
    )
    payload = {
        "draft_id": "draft_representation",
        "status": "draft",
        "name": values["name"],
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "occupation": "职业",
        "social_role": "角色",
        "combat_role_profile": values["combat_role_profile"],
        "design_pitch": values["design_pitch"],
        "personality": list(values["personality"]),
        "background": values["background"],
        "story_hook": "钩子",
        "relationships": [],
        "ability_concept": values["ability_concept"],
        "knowledge_scope": "公开信息",
        "canon_basis": [],
        "new_design_elements": [],
        "open_questions": [],
        "constraint_notes": [],
        "story_link": None,
        "proposed_new_content": [],
    }
    draft = CharacterDraft.from_mapping(payload)
    generation = CharacterGenerationResult(
        draft=draft,
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


def test_missing_design_pitch_produces_warning():
    result = EvaluationRunner().run(_subject(design_pitch=""))

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.code == "MISSING_CHARACTER_DESCRIPTION"
    assert finding.severity == "WARNING"
    assert finding.blocking is False
    assert result.outcome == EvaluationOutcome.WARN


def test_multiple_missing_fields_have_deterministic_ordering():
    result = EvaluationRunner().run(
        _subject(
            design_pitch="",
            personality=(),
            ability_concept="",
        )
    )

    assert [finding.code for finding in result.findings] == [
        "MISSING_ABILITIES",
        "MISSING_CHARACTER_DESCRIPTION",
        "MISSING_PERSONALITY",
    ]
    assert result.to_dict() == EvaluationRunner().run(
        _subject(
            design_pitch="",
            personality=(),
            ability_concept="",
        )
    ).to_dict()
