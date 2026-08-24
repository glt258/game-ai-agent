from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from combat_semantics import CANONICAL_COMBAT_ROLES


@dataclass(frozen=True)
class ResponseContract:
    """Provider-neutral final-output requirement requested by an Agent."""

    name: str
    strict: bool
    json_schema: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.json_schema is not None:
            object.__setattr__(
                self,
                "json_schema",
                MappingProxyType(deepcopy(dict(self.json_schema))),
            )


TEXT_RESPONSE_CONTRACT = ResponseContract("text", strict=False)
CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL = "FINALIZE"
CHARACTER_AUTHORING_ACTION_RESPONSE_CONTRACT = ResponseContract(
    "character_authoring_action", strict=False
)


def has_terminal_authoring_finalize_signal(text: str) -> bool:
    """Accept FINALIZE only when it is the last non-empty response line."""

    if not isinstance(text, str):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and lines[-1] == CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL


CHARACTER_DRAFT_JSON_SCHEMA: Mapping[str, Any] = MappingProxyType(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "draft_id": {"type": "string", "pattern": "^draft_[A-Za-z0-9][A-Za-z0-9_.-]*$"},
            "status": {"type": "string", "enum": ["draft"]},
            "name": {"type": "string", "minLength": 1},
            "canonical_character_id": {"type": ["string", "null"]},
            "age": {"type": ["integer", "null"], "minimum": 0},
            "age_range": {"type": ["string", "null"]},
            "gender": {"type": ["string", "null"]},
            "faction_id": {"type": ["string", "null"]},
            "occupation": {"type": "string"},
            "social_role": {"type": "string"},
            "combat_role_profile": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "primary_role": {
                        "type": ["string", "null"],
                        "enum": [*CANONICAL_COMBAT_ROLES, None],
                    },
                    "secondary_roles": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(CANONICAL_COMBAT_ROLES)},
                    },
                },
                "required": ["primary_role", "secondary_roles"],
            },
            "design_pitch": {"type": "string"},
            "personality": {"type": "array", "items": {"type": "string"}},
            "background": {"type": "string"},
            "story_hook": {"type": "string"},
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "target_id": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "status": {"type": ["string", "null"]},
                        "type": {"type": ["string", "null"]},
                    },
                    "required": ["target_id", "description", "status", "type"],
                },
            },
            "ability_concept": {"type": "string"},
            "knowledge_scope": {"type": "string"},
            "canon_basis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "source_id": {"type": "string"},
                        "supports": {"type": "array", "items": {"type": "string"}},
                        "source_type": {"type": ["string", "null"]},
                    },
                    "required": ["source_id", "supports", "source_type"],
                },
            },
            "new_design_elements": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "constraint_notes": {"type": "array", "items": {"type": "string"}},
            "story_link": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "target_id": {"type": "string"},
                            "relation": {"type": "string"},
                            "status": {"type": "string"},
                        },
                        "required": ["target_id", "relation", "status"],
                    },
                    {"type": "null"},
                ]
            },
            "proposed_new_content": {"type": "array", "items": {"type": "string"}},
        },
        # Strict provider schemas require every property to be declared as
        # required; nullable values represent optional domain values.
        "required": [
            "draft_id", "status", "name", "canonical_character_id", "age",
            "age_range", "gender", "faction_id", "occupation", "social_role",
            "combat_role_profile", "design_pitch", "personality", "background",
            "story_hook", "relationships", "ability_concept", "knowledge_scope",
            "canon_basis", "new_design_elements", "open_questions",
            "constraint_notes", "story_link", "proposed_new_content",
        ],
    }
)

# These fields are required by the runtime CharacterDraft parser even though
# the provider schema declares every property required for strict transport.
# They are the only fields eligible for bounded structural recovery.
CHARACTER_DRAFT_CORE_FIELDS = frozenset(
    {"draft_id", "status", "name", "canon_basis", "new_design_elements", "open_questions"}
)


_SKILL_KIT_ID_SEGMENT = r"[a-z0-9]+(?:_[a-z0-9]+)*"
_SKILL_KIT_REF_KINDS = ("protocol", "effect", "resource", "state", "summon")
_SKILL_KIT_SUBJECT_KINDS = ("self", "ally", "team", "enemy", "scene", "summon")
_SKILL_KIT_ABILITY_MODES = ("active", "passive", "reaction")
_SKILL_KIT_TRIGGER_EVENTS = (
    "ability_invoked",
    "action_completed",
    "damage_received",
    "healing_received",
    "resource_gained",
    "resource_spent",
    "state_entered",
    "state_exited",
    "summon_spawned",
    "summon_acted",
    "summon_departed",
    "scene_entered",
    "scene_exited",
    "feedback_received",
)
_SKILL_KIT_FEEDBACK_EVENTS = (
    "effect_resolved",
    "resource_changed",
    "state_changed",
    "summon_changed",
)
_SKILL_KIT_FEEDBACK_OPERATIONS = ("enables", "modifies", "terminates")
_SKILL_KIT_EFFECT_OPERATIONS = (
    "direct_output",
    "follow_up_output",
    "ally_enablement",
    "recover_or_mitigate",
    "enemy_action_control",
    "threat_protection",
    "resource_gain",
    "resource_use",
    "resource_transform",
    "resource_clear",
    "state_enter",
    "state_apply",
    "state_exit",
    "state_replace",
    "summon_spawn",
    "summon_act",
    "summon_exit",
    "summon_replace",
    "emit_event",
)
_SKILL_KIT_CENTRALITIES = ("core", "secondary")
_SKILL_KIT_REPEAT_POLICIES = ("replace", "refresh", "reject")


def _skill_kit_id(pattern: str = _SKILL_KIT_ID_SEGMENT) -> dict[str, Any]:
    return {"type": "string", "pattern": f"^{pattern}$"}


def _skill_kit_ref_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["protocol"]},
                    "id": _skill_kit_id(rf"{_SKILL_KIT_ID_SEGMENT}/{_SKILL_KIT_ID_SEGMENT}"),
                },
                "required": ["kind", "id"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["effect"]},
                    "id": _skill_kit_id(
                        rf"{_SKILL_KIT_ID_SEGMENT}/{_SKILL_KIT_ID_SEGMENT}/{_SKILL_KIT_ID_SEGMENT}"
                    ),
                },
                "required": ["kind", "id"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["resource", "state", "summon"]},
                    "id": _skill_kit_id(),
                },
                "required": ["kind", "id"],
            },
        ]
    }


def _skill_kit_schema() -> dict[str, Any]:
    ref = {"$ref": "#/$defs/typed_ref"}
    nullable_ref = {"anyOf": [ref, {"type": "null"}]}
    subject = {
        "anyOf": [
            {"type": "null"},
            {"$ref": "#/$defs/subject_object"},
        ]
    }
    trigger = {
        "anyOf": [
            {"type": "null"},
            {"$ref": "#/$defs/trigger_object"},
        ]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "$defs": {
            "typed_ref": _skill_kit_ref_schema(),
            "subject_object": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": list(_SKILL_KIT_SUBJECT_KINDS)},
                    "selector": {"type": ["string", "null"]},
                    "entity_ref": nullable_ref,
                },
                "required": ["kind", "selector", "entity_ref"],
            },
            "trigger_object": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": subject,
                    "event": {"type": ["string", "null"], "enum": [* _SKILL_KIT_TRIGGER_EVENTS, None]},
                    "source_ref": nullable_ref,
                    "qualifier": {"type": ["string", "null"]},
                },
                "required": ["subject", "event", "source_ref", "qualifier"],
            },
            "effect": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "effect_id": _skill_kit_id(),
                    "subject": subject,
                    "operation": {
                        "type": ["string", "null"],
                        "enum": [* _SKILL_KIT_EFFECT_OPERATIONS, None],
                    },
                    "object_ref": nullable_ref,
                    "description": {"type": "string"},
                },
                "required": ["effect_id", "subject", "operation", "object_ref", "description"],
            },
            "protocol": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "protocol_id": _skill_kit_id(),
                    "when": trigger,
                    "causes": {"type": "array", "items": {"$ref": "#/$defs/effect"}},
                },
                "required": ["protocol_id", "when", "causes"],
            },
            "ability": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ability_id": _skill_kit_id(),
                    "name": {"type": "string"},
                    "mode": {"type": "string", "enum": list(_SKILL_KIT_ABILITY_MODES)},
                    "protocols": {"type": "array", "items": {"$ref": "#/$defs/protocol"}},
                    "display_text": {"type": "string"},
                },
                "required": ["ability_id", "name", "mode", "protocols", "display_text"],
            },
            "feedback": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "feedback_id": _skill_kit_id(),
                    "source_effect": ref,
                    "target_protocol": ref,
                    "event": {"type": "string", "enum": list(_SKILL_KIT_FEEDBACK_EVENTS)},
                    "operation": {"type": "string", "enum": list(_SKILL_KIT_FEEDBACK_OPERATIONS)},
                },
                "required": ["feedback_id", "source_effect", "target_protocol", "event", "operation"],
            },
            "resource": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "resource_id": _skill_kit_id(),
                    "opened_by": {"type": "array", "items": ref},
                    "used_or_transformed_by": {"type": "array", "items": ref},
                    "closed_by": {"type": "array", "items": ref},
                },
                "required": ["resource_id", "opened_by", "used_or_transformed_by", "closed_by"],
            },
            "state": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "state_id": _skill_kit_id(),
                    "established_by": {"type": "array", "items": ref},
                    "active_effects": {"type": "array", "items": ref},
                    "ended_or_replaced_by": {"type": "array", "items": ref},
                },
                "required": ["state_id", "established_by", "active_effects", "ended_or_replaced_by"],
            },
            "summon": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summon_id": _skill_kit_id(),
                    "spawned_by": {"type": "array", "items": ref},
                    "active_effects": {"type": "array", "items": ref},
                    "departed_or_replaced_by": {"type": "array", "items": ref},
                    "repeat_policy": {
                        "type": ["string", "null"],
                        "enum": [* _SKILL_KIT_REPEAT_POLICIES, None],
                    },
                },
                "required": [
                    "summon_id",
                    "spawned_by",
                    "active_effects",
                    "departed_or_replaced_by",
                    "repeat_policy",
                ],
            },
            "role_evidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "effect_refs": {"type": "array", "items": ref},
                    "centrality": {"type": "string", "enum": list(_SKILL_KIT_CENTRALITIES)},
                },
                "required": ["effect_refs", "centrality"],
            },
        },
        "properties": {
            "schema_version": {"type": "string", "enum": ["skill-kit-candidate/0.1.1"]},
            "entries": {"type": "array", "items": {"$ref": "#/$defs/ability"}},
            "feedback_relations": {"type": "array", "items": {"$ref": "#/$defs/feedback"}},
            "resources": {"type": "array", "items": {"$ref": "#/$defs/resource"}},
            "states": {"type": "array", "items": {"$ref": "#/$defs/state"}},
            "summons": {"type": "array", "items": {"$ref": "#/$defs/summon"}},
            "role_evidence": {"type": "array", "items": {"$ref": "#/$defs/role_evidence"}},
            "display_summary": {"type": "string"},
        },
        "required": [
            "schema_version",
            "entries",
            "feedback_relations",
            "resources",
            "states",
            "summons",
            "role_evidence",
            "display_summary",
        ],
    }


CHARACTER_SKILL_KIT_JSON_SCHEMA: Mapping[str, Any] = MappingProxyType(_skill_kit_schema())


GROUNDED_RESPONSE_JSON_SCHEMA: Mapping[str, Any] = MappingProxyType(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "segments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "segment_id": {"type": "string", "minLength": 1},
                        "kind": {
                            "type": "string",
                            "enum": ["supported_claim", "uncertain", "non_factual"],
                        },
                        "text": {"type": "string", "minLength": 1},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["segment_id", "kind", "text", "evidence_ids"],
                },
            }
        },
        "required": ["segments"],
    }
)


CHARACTER_DRAFT_RESPONSE_CONTRACT = ResponseContract(
    "character_draft", strict=True, json_schema=CHARACTER_DRAFT_JSON_SCHEMA
)
CHARACTER_SKILL_KIT_RESPONSE_CONTRACT = ResponseContract(
    "character_skill_kit", strict=True, json_schema=CHARACTER_SKILL_KIT_JSON_SCHEMA
)
GROUNDED_RESPONSE_CONTRACT = ResponseContract(
    "grounded_response", strict=True, json_schema=GROUNDED_RESPONSE_JSON_SCHEMA
)


def response_contract_for(response_format: str) -> ResponseContract:
    if response_format == "character_draft":
        return CHARACTER_DRAFT_RESPONSE_CONTRACT
    if response_format == "character_skill_kit":
        return CHARACTER_SKILL_KIT_RESPONSE_CONTRACT
    if response_format == "character_authoring_action":
        return CHARACTER_AUTHORING_ACTION_RESPONSE_CONTRACT
    if response_format == "grounded_response":
        return GROUNDED_RESPONSE_CONTRACT
    return TEXT_RESPONSE_CONTRACT


def character_draft_root_example() -> dict[str, Any]:
    """Build a complete root example from the schema's property names."""

    values: dict[str, Any] = {
        "draft_id": "draft_request_001",
        "status": "draft",
        "name": "Candidate Name",
        "canonical_character_id": None,
        "age": None,
        "age_range": None,
        "gender": None,
        "faction_id": None,
        "combat_role_profile": {"primary_role": None, "secondary_roles": []},
        "story_link": None,
    }
    properties = CHARACTER_DRAFT_JSON_SCHEMA["properties"]
    result: dict[str, Any] = {}
    for name, schema in properties.items():
        if name in values:
            result[name] = values[name]
        elif schema.get("type") == "array":
            result[name] = []
        else:
            result[name] = ""
    return result


def character_draft_prompt_contract() -> str:
    return (
        "The root JSON object itself is the CharacterDraft.\n"
        "Do not wrap it in character_draft, draft, result, data, response, "
        "payload, or any other envelope.\n"
        "Do not return markdown, prose, or any keys outside the schema.\n"
        "Authoritative CharacterDraft JSON Schema:\n"
        + json.dumps(dict(CHARACTER_DRAFT_JSON_SCHEMA), ensure_ascii=False, separators=(",", ":"))
        + "\nValid root-object shape example:\n"
        + json.dumps(character_draft_root_example(), ensure_ascii=False, separators=(",", ":"))
        + "\nFinal mandatory checklist before sending the JSON:\n"
        "1. Emit every property listed by the schema exactly once, including "
        "canon_basis, new_design_elements, and open_questions.\n"
        "2. Emit an empty array when one of those fields has no entries; never "
        "omit a required field.\n"
        "3. Use canon_basis=[] when no Canon claim was retrieved; never invent "
        "a Canon source merely to complete the shape.\n"
        "4. Return the complete root object only after checking the required "
        "field list. The nested combat_role_profile is authoritative; "
        "do not emit any flat combat-role field."
    )


__all__ = [
    "CHARACTER_DRAFT_JSON_SCHEMA",
    "CHARACTER_SKILL_KIT_JSON_SCHEMA",
    "CHARACTER_DRAFT_CORE_FIELDS",
    "CHARACTER_DRAFT_RESPONSE_CONTRACT",
    "CHARACTER_SKILL_KIT_RESPONSE_CONTRACT",
    "CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL",
    "CHARACTER_AUTHORING_ACTION_RESPONSE_CONTRACT",
    "GROUNDED_RESPONSE_CONTRACT",
    "GROUNDED_RESPONSE_JSON_SCHEMA",
    "ResponseContract",
    "TEXT_RESPONSE_CONTRACT",
    "character_draft_root_example",
    "character_draft_prompt_contract",
    "has_terminal_authoring_finalize_signal",
    "response_contract_for",
]
