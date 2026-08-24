from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from character_skill import LegacyAbilityConcept, parse_candidate, render_ability_concept


_EXPECTED_RENDERINGS = {
    "case_01": "Resource: scene/scene scene_exited -> resource_clear; self/owner ability_invoked -> resource_gain; self/owner ability_invoked -> resource_use",
    "case_02": "Resource: self/owner ability_invoked -> resource_use",
    "case_03": "Resource: scene/scene scene_exited -> resource_clear; self/owner ability_invoked -> resource_gain; self/owner ability_invoked -> resource_use",
    "case_04": "Focus: self/owner ability_invoked -> state_apply; self/owner ability_invoked -> state_enter",
    "case_05": "Ambiguous: self/owner ability_invoked -> ally_enablement; ally event -> ally_enablement",
    "case_06": "Control: self/owner ability_invoked -> enemy_action_control; summon/field summon_acted -> summon_act; self/owner ability_invoked -> summon_spawn",
    "case_07": "Support: self/owner ability_invoked -> ally_enablement",
    "case_08": "Support: self/owner ability_invoked -> ally_enablement",
    "case_09": "Direct: self/owner ability_invoked -> direct_output",
    "case_10": "Direct: self/owner ability_invoked -> direct_output",
    "case_11": "Direct: self/owner ability_invoked -> direct_output",
    "case_12": "Direct: self/owner ability_invoked -> direct_output",
    "case_13": "echo echo resonance Base: self/owner ability_invoked -> ally_enablement",
    "case_14": "SkillKit concept: no ability entries declared.",
    "case_15": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_16": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_17": "First: ally/ally action_completed -> follow_up_output; self/owner ability_invoked -> ally_enablement Second: self/owner ability_invoked -> resource_use",
    "case_18": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_19": "Echo: self/owner feedback_received -> ally_enablement; self/owner ability_invoked -> ally_enablement; ally/ally action_completed -> ally_enablement",
}


def _public_cases():
    return json.loads(
        Path(
            "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json"
        ).read_text(encoding="utf-8")
    )["cases"]


def _empty_candidate():
    return parse_candidate(
        {
            "schema_version": "skill-kit-candidate/0.1.1",
            "entries": [],
            "feedback_relations": [],
            "resources": [],
            "states": [],
            "summons": [],
            "role_evidence": [],
            "display_summary": "",
        }
    )


def test_empty_protocol_candidate_uses_the_fixed_compatibility_fallback():
    assert render_ability_concept(_empty_candidate()) == (
        "SkillKit concept: no ability entries declared."
    )


def test_renderer_rejects_legacy_and_unparsed_values():
    with pytest.raises(TypeError):
        render_ability_concept({})
    with pytest.raises(TypeError):
        render_ability_concept(LegacyAbilityConcept("legacy prose"))


def test_all_public_cases_match_fixed_renderer_goldens():
    assert set(_EXPECTED_RENDERINGS) == {item["case_id"] for item in _public_cases()}

    for item in _public_cases():
        candidate = parse_candidate(item["candidate"])
        assert render_ability_concept(candidate) == _EXPECTED_RENDERINGS[item["case_id"]]


def test_renderer_is_invariant_to_entry_and_protocol_order_and_roundtrip():
    item = next(case for case in _public_cases() if case["case_id"] == "case_19")
    original = parse_candidate(item["candidate"])
    shuffled = copy.deepcopy(item["candidate"])
    shuffled["entries"] = list(reversed(shuffled["entries"]))
    for entry in shuffled["entries"]:
        entry["protocols"] = list(reversed(entry["protocols"]))

    first = render_ability_concept(original)
    second = render_ability_concept(parse_candidate(shuffled))
    assert first == second
    assert first == render_ability_concept(parse_candidate(original.to_mapping()))
    assert first == render_ability_concept(original)


def test_renderer_uses_fixed_nullable_trigger_and_empty_effect_phrases():
    candidate = parse_candidate(
        {
            "schema_version": "skill-kit-candidate/0.1.1",
            "entries": [
                {
                    "ability_id": "b",
                    "name": "",
                    "mode": "active",
                    "protocols": [
                        {
                            "protocol_id": "z",
                            "when": {
                                "subject": None,
                                "event": None,
                                "source_ref": None,
                                "qualifier": None,
                            },
                            "causes": [],
                        },
                        {
                            "protocol_id": "a",
                            "when": {
                                "subject": None,
                                "event": "scene_entered",
                                "source_ref": None,
                                "qualifier": None,
                            },
                            "causes": [
                                {
                                    "effect_id": "effect",
                                    "subject": None,
                                    "operation": None,
                                    "object_ref": None,
                                    "description": "",
                                }
                            ],
                        },
                    ],
                    "display_text": "",
                }
            ],
            "feedback_relations": [],
            "resources": [],
            "states": [],
            "summons": [],
            "role_evidence": [],
            "display_summary": "",
        }
    )

    assert render_ability_concept(candidate) == (
        "b: scene_entered -> unspecified effect; unspecified trigger -> no effects"
    )
