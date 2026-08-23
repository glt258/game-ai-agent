from __future__ import annotations

from typing import Any

import pytest

from agents import CharacterDraft, ModelMalformedResponseError
from character_intelligence import CharacterDesignIntent
from character_intelligence.intent.parser import parse_character_design_intent
from combat_semantics import CombatRoleProfile, resolve_legacy_combat_role_profile


def _draft_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": "draft_b15",
        "status": "draft",
        "name": "CI-B1.5角色",
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "occupation": "职业",
        "social_role": "角色",
        "combat_role_profile": None,
        "design_pitch": "设计概念",
        "personality": [],
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


@pytest.mark.parametrize(
    ("raw_profile", "legacy_value", "expected"),
    [
        (None, None, CombatRoleProfile()),
        (CombatRoleProfile("support", ("healer",)), None, CombatRoleProfile("support", ("healer",))),
        (
            {"primary_role": "main_dps", "secondary_roles": ["support"]},
            None,
            CombatRoleProfile("main_dps", ("support",)),
        ),
    ],
)
def test_shared_resolver_accepts_raw_profile_seam_values(
    raw_profile: object,
    legacy_value: object,
    expected: CombatRoleProfile,
) -> None:
    assert resolve_legacy_combat_role_profile(raw_profile, legacy_value) == expected


@pytest.mark.parametrize(
    ("legacy_value", "expected"),
    [
        ("dps", "main_dps"),
        ("main_dps", "main_dps"),
        ("primary_dps", "main_dps"),
        ("main damage dealer", "main_dps"),
        ("sub_dps", "sub_dps"),
        ("secondary_dps", "sub_dps"),
        ("sub_damage_dealer", "sub_dps"),
        ("off_field_dps", "sub_dps"),
        ("support", "support"),
        ("team_support", "support"),
        ("healer", "healer"),
        ("healing_support", "healer"),
        ("control", "control"),
        ("defense", "defense"),
        ("tank", "defense"),
        ("defender", "defense"),
        ("frontline_defender", "defense"),
    ],
)
def test_shared_resolver_uses_only_bounded_transport_aliases(
    legacy_value: str, expected: str
) -> None:
    assert resolve_legacy_combat_role_profile(None, legacy_value) == CombatRoleProfile(
        primary_role=expected  # type: ignore[arg-type]
    )


def test_shared_resolver_accepts_compatible_profile_and_alias() -> None:
    profile = {"primary_role": "support", "secondary_roles": ["healer"]}

    assert resolve_legacy_combat_role_profile(profile, "team-support") == CombatRoleProfile(
        "support", ("healer",)
    )


@pytest.mark.parametrize(
    ("raw_profile", "legacy_value"),
    [
        ({"primary_role": "support", "secondary_roles": []}, "healer"),
        ({"primary_role": "support", "secondary_roles": []}, "burst"),
        (None, "on_field_dps"),
        (None, "crowd_control"),
    ],
)
def test_shared_resolver_fails_closed_for_contradictions_and_cross_taxonomy(
    raw_profile: object, legacy_value: object
) -> None:
    with pytest.raises(ValueError):
        resolve_legacy_combat_role_profile(raw_profile, legacy_value)


@pytest.mark.parametrize("legacy_value", ("burst", "sustain", "flex", "hybrid", "buffer", "enabler"))
def test_non_role_labels_remain_unspecified_only_without_a_role(
    legacy_value: str,
) -> None:
    assert resolve_legacy_combat_role_profile(None, legacy_value).is_unspecified
    assert resolve_legacy_combat_role_profile(
        {"primary_role": None, "secondary_roles": []}, legacy_value
    ).is_unspecified


@pytest.mark.parametrize("legacy_value", (None, "", "none", "unspecified", " NONE "))
def test_unspecified_legacy_values_preserve_profile(legacy_value: object) -> None:
    profile = CombatRoleProfile("support")

    assert resolve_legacy_combat_role_profile(profile, legacy_value) == profile


@pytest.mark.parametrize("legacy_value", ("not_a_role", "burst_dps", "on_field_dps", "crowd_control"))
def test_unknown_and_reference_corpus_labels_are_rejected(legacy_value: str) -> None:
    with pytest.raises(ValueError, match="combat_role"):
        resolve_legacy_combat_role_profile(None, legacy_value)


@pytest.mark.parametrize(
    ("raw_profile", "legacy_value", "error_type"),
    [
        ("support", None, TypeError),
        (None, 3, TypeError),
        ({"primary_role": "support", "secondary_roles": "support"}, None, TypeError),
        ({"primary_role": "assassin", "secondary_roles": []}, None, ValueError),
        ({"primary_role": "support", "unexpected": []}, None, ValueError),
    ],
)
def test_shared_resolver_keeps_type_and_value_error_boundaries(
    raw_profile: object, legacy_value: object, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        resolve_legacy_combat_role_profile(raw_profile, legacy_value)


def test_draft_uses_shared_seam_and_serializes_only_canonical_profile() -> None:
    draft = CharacterDraft.from_mapping(
        _draft_payload(combat_role_profile={"primary_role": "sub_dps", "secondary_roles": []}, combat_role="off_field_dps")
    )

    assert draft.combat_role_profile == CombatRoleProfile("sub_dps")
    assert "combat_role" not in draft.to_dict()
    assert draft.to_dict()["combat_role_profile"] == {
        "primary_role": "sub_dps",
        "secondary_roles": [],
    }


def test_draft_wraps_shared_seam_errors_as_model_malformed() -> None:
    with pytest.raises(ModelMalformedResponseError, match="compatibility input"):
        CharacterDraft.from_mapping(_draft_payload(combat_role="on_field_dps"))


def test_intent_uses_shared_seam_and_serializes_only_canonical_profile() -> None:
    intent = CharacterDesignIntent.from_mapping(
        {
            "raw_request": "设计一个辅助角色",
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
            "combat_role": "team_support",
        }
    )

    assert intent.combat_role_profile == CombatRoleProfile("support")
    assert "combat_role" not in intent.to_dict()


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"combat_role_profile": "support"}, TypeError),
        ({"combat_role": "on_field_dps"}, ValueError),
    ],
)
def test_intent_wraps_shared_seam_errors_in_its_domain(
    payload: dict[str, object], error_type: type[Exception]
) -> None:
    with pytest.raises(error_type, match="CharacterDesignIntent.combat_role"):
        CharacterDesignIntent.from_mapping(payload)


@pytest.mark.parametrize("phrase", ("爆发", "高爆发", "爆发型", "爆发输出", "burst"))
def test_parser_drives_all_burst_detection_from_non_role_patterns(phrase: str) -> None:
    intent = parse_character_design_intent(f"设计一个{phrase}角色")

    assert intent.combat_role_profile.is_unspecified
    assert "burst" in intent.design_goals


def test_parser_keeps_buff_position_out_of_canonical_role_taxonomy() -> None:
    intent = parse_character_design_intent("设计一个增益位角色")

    assert intent.combat_role_profile.is_unspecified
    assert "buffer" in intent.design_goals


def test_parser_keeps_explicit_buff_role_as_support() -> None:
    intent = parse_character_design_intent("设计一个增益角色")

    assert intent.combat_role_profile.primary_role == "support"


def test_parser_keeps_reaction_position_out_of_canonical_role_taxonomy() -> None:
    intent = parse_character_design_intent("设计一个反应位角色")

    assert intent.combat_role_profile.is_unspecified
    assert "enabler" in intent.design_goals
