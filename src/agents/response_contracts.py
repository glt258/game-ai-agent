from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from character_intelligence.character_draft import (
    CHARACTER_DRAFT_CORE_FIELDS,
    CHARACTER_DRAFT_JSON_SCHEMA,
)


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
CHARACTER_DESIGN_PLAN_RESPONSE_CONTRACT = ResponseContract(
    "character_design_plan", strict=True
)
CHARACTER_PLANNER_PROPOSAL_RESPONSE_CONTRACT = ResponseContract(
    "character_planner_proposal", strict=True
)

CHARACTER_CONCEPT_SEED_JSON_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "concept_id": {"type": "string", "minLength": 1},
        "one_line_identity": {"type": "string", "minLength": 1},
        "dramatic_axis": {"type": "string", "minLength": 1},
        "character_contradiction": {"type": "string", "minLength": 1},
        "player_hook": {"type": "string", "minLength": 1},
        "relationship_axis": {"type": "string", "minLength": 1},
        "gameplay_fantasy": {"type": "string", "minLength": 1},
        "visual_anchor": {"type": "string", "minLength": 1},
        "differentiation_basis": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "major_risk": {"type": "string", "minLength": 1},
    },
    "required": [
        "concept_id",
        "one_line_identity",
        "dramatic_axis",
        "character_contradiction",
        "player_hook",
        "relationship_axis",
        "gameplay_fantasy",
        "visual_anchor",
        "differentiation_basis",
        "major_risk",
    ],
}
CHARACTER_CONCEPT_SEARCH_JSON_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "concepts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": CHARACTER_CONCEPT_SEED_JSON_SCHEMA,
        }
    },
    "required": ["concepts"],
}
CHARACTER_CONCEPT_SELECTION_JSON_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_concept_id": {"type": "string", "minLength": 1},
        "selection_reasons": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "tradeoffs": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "preserve_elements": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "rejected_reasons": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["selected_concept_id", "selection_reasons"],
}
CHARACTER_CONCEPT_SEARCH_RESPONSE_CONTRACT = ResponseContract(
    "character_concept_search",
    strict=True,
    json_schema=CHARACTER_CONCEPT_SEARCH_JSON_SCHEMA,
)
CHARACTER_CONCEPT_SELECTION_RESPONSE_CONTRACT = ResponseContract(
    "character_concept_selection",
    strict=True,
    json_schema=CHARACTER_CONCEPT_SELECTION_JSON_SCHEMA,
)


def has_terminal_authoring_finalize_signal(text: str) -> bool:
    """Accept only the exact FINALIZE signal with surrounding whitespace."""

    if not isinstance(text, str):
        return False
    return text.strip() == CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL


def _character_draft_source_ids(source_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(source_ids, (str, bytes)) or not isinstance(source_ids, Sequence):
        raise ValueError("source_ids must be a sequence of exact IDs")
    normalized = tuple(source_ids)
    if any(
        not isinstance(source_id, str)
        or not source_id
        or source_id != source_id.strip()
        or "\n" in source_id
        or "\r" in source_id
        for source_id in normalized
    ):
        raise ValueError("source_ids must contain non-empty exact IDs")
    if len(set(normalized)) != len(normalized):
        raise ValueError("source_ids must be unique")
    return normalized


def character_draft_schema_for_source_ids(
    source_ids: Sequence[str],
    *,
    field_value_enums: Mapping[str, Sequence[Any]] | None = None,
) -> dict[str, Any]:
    """Build an isolated CharacterDraft schema for one grounding scope.

    ``field_value_enums`` is request-local data derived from the finalization
    evidence.  It is applied only to the deep-copied transport schema; the
    public ``CHARACTER_DRAFT_JSON_SCHEMA`` remains unconstrained so ordinary
    authoring and legacy callers keep their existing contract.
    """

    allowed_source_ids = _character_draft_source_ids(source_ids)
    schema = deepcopy(dict(CHARACTER_DRAFT_JSON_SCHEMA))
    canon_basis = schema["properties"]["canon_basis"]
    source_id_schema = canon_basis["items"]["properties"]["source_id"]
    if allowed_source_ids:
        source_id_schema["enum"] = list(allowed_source_ids)
    else:
        canon_basis["maxItems"] = 0
    if field_value_enums is not None:
        if not isinstance(field_value_enums, Mapping):
            raise ValueError("field_value_enums must be a mapping")
        for field_name, raw_values in field_value_enums.items():
            if field_name not in schema["properties"]:
                raise ValueError("field_value_enums contains an unknown field")
            if isinstance(raw_values, (str, bytes)) or not isinstance(
                raw_values, Sequence
            ):
                raise ValueError("field_value_enums values must be sequences")
            values = deepcopy(list(raw_values))
            try:
                encoded_values = [
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    for value in values
                ]
            except (TypeError, ValueError):
                raise ValueError("field_value_enums must contain JSON values") from None
            if len(set(encoded_values)) != len(encoded_values):
                raise ValueError("field_value_enums must not contain duplicates")
            schema["properties"][field_name]["enum"] = values
    return schema


def character_draft_grounding_prompt(
    source_ids: Sequence[str],
    *,
    system_provenance_fields: Sequence[str] = (),
) -> str:
    """Describe request-scoped Canon source and provenance ownership.

    System-owned fields still use the public ``canon_basis`` shape for the
    final Draft, but the provider is not an authority for their provenance.
    This instruction complements the finalization projection, which is the
    fail-closed enforcement boundary for providers that ignore the guidance.
    """

    allowed_source_ids = _character_draft_source_ids(source_ids)
    if isinstance(system_provenance_fields, (str, bytes)) or not isinstance(
        system_provenance_fields, Sequence
    ):
        raise ValueError("system_provenance_fields must be a sequence")
    normalized_system_fields = tuple(system_provenance_fields)
    if any(
        not isinstance(field_name, str) or not field_name
        for field_name in normalized_system_fields
    ) or len(set(normalized_system_fields)) != len(normalized_system_fields):
        raise ValueError("system_provenance_fields must contain unique field names")
    if not allowed_source_ids:
        lines = [
            "Request-scoped Canon source allowlist: (none).\n"
            "For canon_basis: emit an empty array; do not cite unavailable Canon "
            "as evidence."
        ]
    else:
        lines = [
            "Request-scoped Canon source allowlist (exact IDs):",
            *(f"- {source_id}" for source_id in allowed_source_ids),
            "For canon_basis.source_id:",
            "- use only an exact ID from the list above;",
            "- never invent, rename, abbreviate, normalize, or transform an ID;",
            "- if no supplied source supports a claim, omit that canon_basis entry;",
            "- do not cite unavailable Canon as evidence.",
        ]
    if normalized_system_fields:
        lines.extend(
            [
                "Request-scoped system-owned Canon provenance fields:",
                *(f"- {field_name}" for field_name in normalized_system_fields),
                "- choose only the exact field value supplied by the request-scoped enum;",
                "- do not include these exact field names in canon_basis.supports;",
                "- the system materializes their primary and dependency provenance after selection.",
            ]
        )
    return "\n".join(lines)

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


def character_skill_kit_prompt_contract() -> str:
    """Render the frozen SkillKit contract into bounded model-facing guidance."""

    schema = CHARACTER_SKILL_KIT_JSON_SCHEMA
    properties = schema["properties"]
    required = tuple(schema["required"])
    lines = [
        "Return exactly one SkillKit candidate JSON object, directly at the root.",
        "The root object must contain exactly these required keys:",
        *[f"- {name}" for name in required],
        "Every required root key must be present even when its value is empty.",
        "Array-valued sections may be empty; do not omit their keys.",
        "Do not add any other root keys.",
        "Do not wrap the object in candidate, result, data, output, response, payload, envelope, skill_kit, or ability_concept.",
        "Do not return prose, Markdown, code fences, explanations, or reasoning; return only the JSON object.",
        "Nested shape summary (all listed object fields are required):",
    ]
    definitions = schema["$defs"]
    for root_name, root_schema in properties.items():
        item = root_schema.get("items") if root_schema.get("type") == "array" else root_schema
        if not isinstance(item, Mapping) or "$ref" not in item:
            continue
        definition_name = str(item["$ref"]).rsplit("/", 1)[-1]
        definition = definitions.get(definition_name)
        if not isinstance(definition, Mapping):
            continue
        fields = definition.get("properties", {})
        if isinstance(fields, Mapping):
            lines.append(f"- {root_name}: array of {definition_name} objects with fields {', '.join(str(key) for key in fields)}")

    enum_lines: list[str] = []

    def collect_enums(node: object, path: str) -> None:
        if not isinstance(node, Mapping):
            return
        values = node.get("enum")
        if isinstance(values, list) and values:
            rendered = ", ".join("null" if value is None else str(value) for value in values)
            enum_lines.append(f"- {path}: {rendered}")
        child_properties = node.get("properties")
        if isinstance(child_properties, Mapping):
            for key, child in child_properties.items():
                collect_enums(child, f"{path}.{key}" if path else str(key))
        items = node.get("items")
        if isinstance(items, Mapping):
            collect_enums(items, path)
        for branch_key in ("anyOf", "oneOf"):
            branches = node.get(branch_key)
            if isinstance(branches, list):
                for branch in branches:
                    collect_enums(branch, path)
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.rsplit("/", 1)[-1]
            collect_enums(definitions.get(name), path)

    collect_enums(schema, "")
    if enum_lines:
        lines.append("Closed enum vocabulary:")
        lines.extend(enum_lines)
    return "\n".join(lines)


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
HYBRID_SEMANTIC_IR_RESPONSE_CONTRACT = ResponseContract(
    "hybrid_semantic_ir", strict=True
)


def response_contract_for(response_format: str) -> ResponseContract:
    if response_format == "character_draft":
        return CHARACTER_DRAFT_RESPONSE_CONTRACT
    if response_format == "character_design_plan":
        return CHARACTER_DESIGN_PLAN_RESPONSE_CONTRACT
    if response_format == "character_planner_proposal":
        return CHARACTER_PLANNER_PROPOSAL_RESPONSE_CONTRACT
    if response_format == "character_concept_search":
        return CHARACTER_CONCEPT_SEARCH_RESPONSE_CONTRACT
    if response_format == "character_concept_selection":
        return CHARACTER_CONCEPT_SELECTION_RESPONSE_CONTRACT
    if response_format == "character_skill_kit":
        return CHARACTER_SKILL_KIT_RESPONSE_CONTRACT
    if response_format == "character_authoring_action":
        return CHARACTER_AUTHORING_ACTION_RESPONSE_CONTRACT
    if response_format == "grounded_response":
        return GROUNDED_RESPONSE_CONTRACT
    if response_format == "hybrid_semantic_ir":
        return HYBRID_SEMANTIC_IR_RESPONSE_CONTRACT
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
    "character_draft_grounding_prompt",
    "character_draft_schema_for_source_ids",
    "CHARACTER_DESIGN_PLAN_RESPONSE_CONTRACT",
    "CHARACTER_PLANNER_PROPOSAL_RESPONSE_CONTRACT",
    "CHARACTER_CONCEPT_SEED_JSON_SCHEMA",
    "CHARACTER_CONCEPT_SEARCH_JSON_SCHEMA",
    "CHARACTER_CONCEPT_SELECTION_JSON_SCHEMA",
    "CHARACTER_CONCEPT_SEARCH_RESPONSE_CONTRACT",
    "CHARACTER_CONCEPT_SELECTION_RESPONSE_CONTRACT",
    "CHARACTER_SKILL_KIT_RESPONSE_CONTRACT",
    "CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL",
    "CHARACTER_AUTHORING_ACTION_RESPONSE_CONTRACT",
    "GROUNDED_RESPONSE_CONTRACT",
    "GROUNDED_RESPONSE_JSON_SCHEMA",
    "HYBRID_SEMANTIC_IR_RESPONSE_CONTRACT",
    "ResponseContract",
    "TEXT_RESPONSE_CONTRACT",
    "character_draft_root_example",
    "character_skill_kit_prompt_contract",
    "character_draft_prompt_contract",
    "has_terminal_authoring_finalize_signal",
    "response_contract_for",
]
