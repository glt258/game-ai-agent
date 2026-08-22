from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAgent,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    DeterministicCharacterGenerationModel,
    ModelMalformedResponseError,
)
from agents.evaluation import EvaluationOutcome, EvaluationRunner, EvaluationSubject, RequestAlignmentValidator
from character_intelligence import CharacterDesignIntent, CharacterDesignIntentParser
from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile


ROLES = ("main_dps", "sub_dps", "support", "healer", "control", "defense")


def _draft_payload(
    *,
    profile: dict[str, Any] | None = None,
    legacy: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": "draft_b14",
        "status": "draft",
        "name": "B1.4角色",
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "occupation": "职业",
        "social_role": "角色",
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
    if profile is not None:
        payload["combat_role_profile"] = profile
    if legacy is not None:
        payload["combat_role"] = legacy
    return payload


def _subject(intent: CharacterDesignIntent, profile: CombatRoleProfile) -> EvaluationSubject:
    request = CharacterDesignRequest(intent.raw_request or "设计一个角色。", request_id="b14_eval")
    draft = CharacterDraft.from_mapping(
        _draft_payload(profile=profile.to_dict())
    )
    result = CharacterGenerationResult(
        draft=draft,
        sources=(),
        audit=CharacterGenerationAudit(request.request_id, 0, (), ()),
        design_plan=CharacterDesignPlan.from_intent(intent),
    )
    return EvaluationSubject(request=request, generation_result=result)


def test_scalar_is_not_an_in_memory_draft_or_intent_member() -> None:
    assert "combat_role" not in {item.name for item in fields(CharacterDraft)}
    assert "combat_role" not in {item.name for item in fields(CharacterDesignIntent)}
    with pytest.raises(TypeError):
        CharacterDraft(draft_id="draft_b14", status="draft", name="角色", combat_role="support")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        CharacterDesignIntent(combat_role="support")  # type: ignore[call-arg]


@pytest.mark.parametrize("legacy", ("burst", "sustain", "flex", "hybrid", "none"))
def test_draft_legacy_non_roles_stay_unspecified(legacy: str) -> None:
    draft = CharacterDraft.from_mapping(_draft_payload(legacy=legacy))
    assert draft.combat_role_profile.is_unspecified
    assert "combat_role" not in draft.to_dict()


def test_draft_legacy_adapter_has_profile_precedence_and_rejects_contradictions() -> None:
    compatible = CharacterDraft.from_mapping(
        _draft_payload(
            profile={"primary_role": "support", "secondary_roles": []},
            legacy="team_support",
        )
    )
    assert compatible.combat_role_profile == CombatRoleProfile(primary_role="support")

    with pytest.raises(ModelMalformedResponseError, match="contradict"):
        CharacterDraft.from_mapping(
            _draft_payload(
                profile={"primary_role": "support", "secondary_roles": []},
                legacy="main_dps",
            )
        )
    with pytest.raises(ModelMalformedResponseError, match="supported role"):
        CharacterDraft.from_mapping(_draft_payload(legacy="assassin"))


def test_intent_legacy_adapter_is_deserialization_only_and_profile_only_on_output() -> None:
    intent = CharacterDesignIntent.from_mapping(
        {"combat_role": "dps", "raw_request": "设计一个主C角色。"}
    )
    assert not hasattr(intent, "combat_role")
    assert intent.combat_role_profile == CombatRoleProfile(primary_role="main_dps")
    assert "combat_role" not in intent.to_dict()

    compatible = CharacterDesignIntent.from_mapping(
        {
            "combat_role": "team_support",
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        }
    )
    assert compatible.combat_role_profile == CombatRoleProfile(primary_role="support")
    with pytest.raises(ValueError, match="contradict"):
        CharacterDesignIntent.from_mapping(
            {
                "combat_role": "healer",
                "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
            }
        )
    with pytest.raises(ValueError, match="supported role"):
        CharacterDesignIntent.from_mapping({"combat_role": "assassin"})


def test_parser_keeps_damage_pattern_semantics_out_of_role_profile() -> None:
    for text, semantic in (("burst", "burst"), ("sustain", "sustain"), ("hybrid", "hybrid")):
        intent = CharacterDesignIntentParser().parse(text)
        assert intent.combat_role_profile.is_unspecified
        assert semantic in intent.design_goals
        assert "combat_role" not in intent.to_dict()


@pytest.mark.parametrize("role", ROLES)
def test_evaluation_blocks_each_primary_role_mismatch(role: str) -> None:
    other = next(item for item in ROLES if item != role)
    intent = CharacterDesignIntent(
        raw_request=f"{role}角色",
        combat_role_profile=CombatRoleProfile(primary_role=role),
    )
    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(intent, CombatRoleProfile(primary_role=other))
    )
    assert result.outcome == EvaluationOutcome.FAIL
    assert any(item.code == "REQUEST_PRIMARY_ROLE_MISMATCH" and item.blocking for item in result.findings)


def test_evaluation_preserves_secondary_role_rules() -> None:
    requested = CharacterDesignIntent(
        raw_request="main_dps + support",
        combat_role_profile=CombatRoleProfile("main_dps", ("support",)),
    )
    reversed_roles = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(requested, CombatRoleProfile("support", ("main_dps",)))
    )
    missing = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(requested, CombatRoleProfile("main_dps"))
    )
    extra = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(requested, CombatRoleProfile("main_dps", ("support", "control")))
    )
    assert reversed_roles.outcome == EvaluationOutcome.FAIL
    assert missing.outcome == EvaluationOutcome.FAIL
    assert extra.outcome == EvaluationOutcome.PASS


@pytest.mark.parametrize(
    ("input_text", "profile"),
    (
        ("main_dps", CombatRoleProfile("main_dps")),
        ("sub_dps", CombatRoleProfile("sub_dps")),
        ("support", CombatRoleProfile("support")),
        ("healer", CombatRoleProfile("healer")),
        ("control", CombatRoleProfile("control")),
        ("defense", CombatRoleProfile("defense")),
        ("main_dps + support", CombatRoleProfile("main_dps", ("support",))),
        ("support + sub_dps", CombatRoleProfile("support", ("sub_dps",))),
        ("healer + support", CombatRoleProfile("healer", ("support",))),
    ),
)
def test_generation_preserves_the_end_to_end_role_matrix(
    input_text: str, profile: CombatRoleProfile
) -> None:
    result = CharacterGenerationAgent(DeterministicCharacterGenerationModel()).generate_with_intent(input_text)
    assert result.design_plan is not None
    assert result.design_plan.combat_role_profile == profile
    assert result.draft.combat_role_profile == profile
    assert "combat_role" not in result.draft.to_dict()
