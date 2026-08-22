from __future__ import annotations

from pathlib import Path

from agents.character_generation import CHARACTER_SYSTEM_CONTRACT, CharacterDraft
from agents.response_contracts import CHARACTER_DRAFT_JSON_SCHEMA


ROOT = Path(__file__).resolve().parents[1]


def test_character_generation_has_no_fixed_weapon_type_contract() -> None:
    fields = set(CHARACTER_DRAFT_JSON_SCHEMA["properties"])
    forbidden_fields = {
        "weapon_type",
        "weapon_class",
        "allowed_weapon_type",
        "weapon_requirement",
    }
    assert not fields & forbidden_fields
    assert not hasattr(CharacterDraft, "weapon_type")
    assert not hasattr(CharacterDraft, "weapon_class")


def test_character_generation_prompt_does_not_require_weapon_categories() -> None:
    prompt = CHARACTER_SYSTEM_CONTRACT.lower()
    assert "weapon_type" not in prompt
    assert "weapon class" not in prompt
    assert "sword / gun" not in prompt
    assert "choose a weapon" not in prompt


def test_formal_character_schema_has_no_fixed_weapon_enum_or_mechanic_tag_contract() -> None:
    schema = (ROOT / "data" / "characters" / "character_schema.yaml").read_text(
        encoding="utf-8"
    )
    assert "weapon_type:" not in schema
    assert "WeaponType" not in schema
    assert "weapon_class:" not in schema


def test_existing_combat_role_is_role_not_armament() -> None:
    payload = {
        "draft_id": "draft_armament_audit",
        "status": "draft",
        "name": "Audit Character",
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "canon_basis": [],
        "new_design_elements": [],
        "open_questions": [],
    }
    draft = CharacterDraft.from_mapping(payload)
    assert draft.combat_role_profile.primary_role == "support"
    assert "combat_role" not in draft.to_dict()
    assert "combat_role" not in {"weapon_type", "weapon_class"}
