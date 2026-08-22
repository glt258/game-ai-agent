from __future__ import annotations

from typing import Any

import pytest

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
    ModelMalformedResponseError,
)
from agents.evaluation import EvaluationOutcome, EvaluationRunner, EvaluationSubject
from agents.response_contracts import CHARACTER_DRAFT_JSON_SCHEMA
from character_intelligence import CharacterDesignIntent
from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": "draft_b12",
        "status": "draft",
        "name": "B1.2角色",
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "occupation": "职业",
        "social_role": "角色",
        "combat_role_profile": {"primary_role": "main_dps", "secondary_roles": ["support"]},
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
    payload.update(overrides)
    return payload


def _subject(intent: CharacterDesignIntent, draft: CharacterDraft) -> EvaluationSubject:
    request = CharacterDesignRequest(intent.raw_request or "设计一个角色。", request_id="b12_eval")
    return EvaluationSubject(
        request=request,
        generation_result=CharacterGenerationResult(
            draft=draft,
            sources=(),
            audit=CharacterGenerationAudit(request.request_id, 0, (), ()),
            design_plan=CharacterDesignPlan.from_intent(intent),
        ),
    )


@pytest.mark.parametrize("role", ("main_dps", "sub_dps", "support", "healer", "control", "defense"))
def test_draft_accepts_every_canonical_primary_role(role: str) -> None:
    draft = CharacterDraft.from_mapping(_payload(
        combat_role_profile={"primary_role": role, "secondary_roles": []},
    ))
    assert draft.combat_role_profile == CombatRoleProfile(primary_role=role)


@pytest.mark.parametrize(
    "profile",
    (
        {"primary_role": "main_dps", "secondary_roles": ["support"]},
        {"primary_role": "support", "secondary_roles": ["sub_dps"]},
        {"primary_role": "healer", "secondary_roles": ["support"]},
    ),
)
def test_draft_round_trip_preserves_multi_role_profile(profile: dict[str, Any]) -> None:
    draft = CharacterDraft.from_mapping(_payload(combat_role_profile=profile))
    restored = CharacterDraft.from_mapping(draft.to_dict())
    assert restored.combat_role_profile.to_dict() == profile


def test_draft_rejects_invalid_and_duplicate_roles() -> None:
    with pytest.raises(ModelMalformedResponseError):
        CharacterDraft.from_mapping(_payload(combat_role_profile={"primary_role": "assassin", "secondary_roles": []}))
    with pytest.raises(ModelMalformedResponseError):
        CharacterDraft.from_mapping(_payload(combat_role_profile={"primary_role": "support", "secondary_roles": ["support"]}))
    with pytest.raises(ModelMalformedResponseError):
        CharacterDraft.from_mapping(_payload(combat_role_profile={"primary_role": "main_dps", "secondary_roles": ["support", "support"]}))


def test_flat_legacy_role_is_adapted_but_cannot_contradict_profile() -> None:
    draft = CharacterDraft.from_mapping(_payload(combat_role_profile=None, combat_role="healer"))
    assert draft.combat_role_profile == CombatRoleProfile(primary_role="healer")
    with pytest.raises(ModelMalformedResponseError):
        CharacterDraft.from_mapping(_payload(
            combat_role_profile={"primary_role": "healer", "secondary_roles": []},
            combat_role="support",
        ))


def test_provider_schema_uses_canonical_role_set_and_excludes_legacy_patterns() -> None:
    profile = CHARACTER_DRAFT_JSON_SCHEMA["properties"]["combat_role_profile"]
    assert set(profile["properties"]["primary_role"]["enum"]) == {
        "main_dps", "sub_dps", "support", "healer", "control", "defense", None,
    }
    assert set(profile["properties"]["secondary_roles"]["items"]["enum"]) == {
        "main_dps", "sub_dps", "support", "healer", "control", "defense",
    }
    assert "burst" not in profile["properties"]["secondary_roles"]["items"]["enum"]
    assert "sustain" not in profile["properties"]["secondary_roles"]["items"]["enum"]


def test_plan_generation_and_evaluation_preserve_primary_and_secondary_roles() -> None:
    model = DeterministicCharacterGenerationModel()
    result = CharacterGenerationAgent(model).generate_with_intent("main_dps + support")
    assert result.design_plan is not None
    assert result.design_plan.combat_role_profile == CombatRoleProfile("main_dps", ("support",))
    assert result.draft.combat_role_profile == CombatRoleProfile("main_dps", ("support",))

    evaluation = EvaluationRunner().run(
        _subject(
            CharacterDesignIntent(
                raw_request="main_dps + support",
                combat_role_profile=CombatRoleProfile("main_dps", ("support",)),
            ),
            result.draft,
        )
    )
    assert evaluation.outcome == EvaluationOutcome.PASS


def test_evaluation_checks_primary_secondary_and_allows_extra_secondary() -> None:
    requested = CharacterDesignIntent(
        raw_request="main_dps + support",
        combat_role_profile=CombatRoleProfile("main_dps", ("support",)),
    )
    wrong_primary = CharacterDraft.from_mapping(_payload(
        combat_role_profile={"primary_role": "support", "secondary_roles": ["main_dps"]},
    ))
    missing_secondary = CharacterDraft.from_mapping(_payload(
        combat_role_profile={"primary_role": "main_dps", "secondary_roles": []},
    ))
    extra_secondary = CharacterDraft.from_mapping(_payload(
        combat_role_profile={"primary_role": "main_dps", "secondary_roles": ["support", "control"]},
    ))

    assert EvaluationRunner().run(_subject(requested, wrong_primary)).outcome == EvaluationOutcome.FAIL
    assert EvaluationRunner().run(_subject(requested, missing_secondary)).outcome == EvaluationOutcome.FAIL
    assert EvaluationRunner().run(_subject(requested, extra_secondary)).outcome == EvaluationOutcome.PASS


@pytest.mark.parametrize("role", ("main_dps", "sub_dps", "healer"))
def test_evaluation_does_not_bypass_canonical_primary_roles(role: str) -> None:
    intent = CharacterDesignIntent(
        raw_request=role,
        combat_role_profile=CombatRoleProfile(primary_role=role),
    )
    draft = CharacterDraft.from_mapping(_payload(
        combat_role_profile={"primary_role": role, "secondary_roles": []},
    ))
    result = EvaluationRunner().run(_subject(intent, draft))
    assert result.outcome == EvaluationOutcome.PASS
