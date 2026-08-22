from __future__ import annotations

from typing import Any

import pytest

from agents import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
    ModelMalformedResponseError,
)
from agents.response_contracts import (
    CHARACTER_DRAFT_JSON_SCHEMA,
    character_draft_root_example,
)
from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile


def _payload(*, profile: dict[str, Any] | None = None, legacy: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": "draft_b13",
        "status": "draft",
        "name": "B1.3角色",
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "occupation": "职业",
        "social_role": "角色",
        "combat_role_profile": profile or {"primary_role": "support", "secondary_roles": []},
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
    if legacy is not None:
        payload["combat_role"] = legacy
    return payload


def test_provider_schema_is_profile_only() -> None:
    properties = CHARACTER_DRAFT_JSON_SCHEMA["properties"]
    required = set(CHARACTER_DRAFT_JSON_SCHEMA["required"])
    assert "combat_role_profile" in properties
    assert "combat_role_profile" in required
    assert "combat_role" not in properties
    assert "combat_role" not in required

    example = character_draft_root_example()
    assert "combat_role_profile" in example
    assert "combat_role" not in example


def test_canonical_draft_serialization_omits_flat_role() -> None:
    draft = CharacterDraft.from_mapping(_payload())
    assert draft.combat_role_profile == CombatRoleProfile(primary_role="support")
    assert "combat_role" not in draft.to_dict()


def test_legacy_flat_input_is_adapted_but_not_reemitted() -> None:
    payload = _payload()
    payload.pop("combat_role_profile")
    draft = CharacterDraft.from_mapping({**payload, "combat_role": "support"})
    assert draft.combat_role_profile == CombatRoleProfile(primary_role="support")
    assert "combat_role" not in draft.to_dict()


def test_plan_has_no_scalar_role_generation_constraint() -> None:
    plan = CharacterDesignPlan.from_text("main_dps + support")
    assert plan.combat_role_profile == CombatRoleProfile("main_dps", ("support",))
    assert not any(item.startswith("combat_role=") for item in plan.generation_constraints)


def test_canonical_generation_does_not_emit_flat_role() -> None:
    result = CharacterGenerationAgent(DeterministicCharacterGenerationModel()).generate_with_intent(
        "healer + support"
    )
    assert result.draft.combat_role_profile == CombatRoleProfile("healer", ("support",))
    assert "combat_role" not in result.draft.to_dict()


def test_legacy_non_role_values_do_not_become_canonical_roles() -> None:
    for legacy in ("burst", "sustain", "flex", "hybrid", "none"):
        payload = _payload()
        payload.pop("combat_role_profile")
        draft = CharacterDraft.from_mapping({**payload, "combat_role": legacy})
        assert draft.combat_role_profile.is_unspecified
        assert "combat_role" not in draft.to_dict()


def test_unknown_legacy_role_fails_closed() -> None:
    payload = _payload()
    payload.pop("combat_role_profile")
    with pytest.raises(ModelMalformedResponseError, match="not a supported role"):
        CharacterDraft.from_mapping({**payload, "combat_role": "assassin"})
