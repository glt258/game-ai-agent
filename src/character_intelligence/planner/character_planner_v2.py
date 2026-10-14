"""Single-proposal Planner stage for Character Generation V2 production."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from agents import (
    AgentModel,
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    NpcCharacterView,
    NpcRuntimeView,
)

from ..context.schema import CharacterPlanningContextV2
from ..naming_design import (
    CharacterNamingDesignV1,
    CharacterNamingOwner,
    NamingDesignError,
    naming_design_schema,
    validate_character_naming_design,
)
from .character_concept_v2 import CharacterConceptSeedV2
from .character_plan_v2 import (
    CharacterDesignPlanV2,
    CharacterDesignPlanV2Status,
    CharacterPlanV2Decision,
    CharacterPlanV2Owner,
    CharacterPlanV2RelationshipBinding,
    CharacterPlanV2RelationshipStrategy,
    CharacterPlanV2Source,
)

PLANNER_V1_RESPONSE_FORMAT = "character_planner_proposal"
PLANNER_V1_INVOCATION_PURPOSE = "character_planner_v1"
_FORBIDDEN_PROPOSAL_KEYS = frozenset(
    {
        "intent",
        "request_id",
        "product_roster_positioning",
        "combat_role_profile",
        "reference_id",
        "reference_ids",
    }
)

PLANNER_V1_SYSTEM_CONTRACT = """You are Character Planner v1 in the Character Generation V2 production pipeline.

SYSTEM ROLE
Answer what character should be designed. Produce one high-level structured design proposal; never write a final character draft.

PLANNING RULES
- Preserve USER HARD REQUIREMENT, PROJECT CANON, DETERMINISTIC PROJECT SEMANTICS, and explicit PROJECT ROSTER/RELATION DATA.
- A USER SOFT PREFERENCE is weaker than a hard requirement. REFERENCE PRECEDENT is precedent, not project truth. Your proposal is the lowest-authority layer.
- Missing context is uncertainty, never permission to fabricate repository facts. State limits in coverage notes or risks.
- Existing Canon relationships are facts. Relationship opportunities are proposals only and must remain in their separate output fields.
- Reuse the supplied CombatRoleProfile. Do not assign or rename canonical combat roles.
- Product positioning is unavailable unless explicitly supplied as a user requirement. Do not invent rarity, banner, sales, release, or commercial placement.
- Reference Corpus is for contrast and structural precedent. Do not copy or name-drop reference characters in the in-universe proposal.
- Before naming, separate the character's occupation, organization, and social identity from the character's individual identity using the supplied request and evidence.
- Infer naming culture only from explicit user, setting, or Canon evidence. A Chinese-language brief or Chinese-script name is not evidence of Chinese cultural origin; name script, display language, nationality, family background, and naming culture are separate facts. Never invent a Canon constraint, nationality, origin, or localized-name source; leave unsupported facts unknown.
- Treat each candidate's name as the proposed player-facing display name that will become selected_name and then CharacterDraft.name. It may differ from an evidenced native, legal, or source-language name. Use the existing cultural_inspiration, naming_style, and tradeoffs fields to explain only distinctions supported by the supplied evidence; do not present a proposed localization as established without its source or current use, and do not invent a missing counterpart name.
- In an open naming context, do not default to a realistic Chinese surname-plus-given-name form solely because the brief is in Chinese or project material is Chinese. Such names remain fully valid when they suit the character and setting; do not reject them or give another script automatic preference.
- Do not construct a Chinese name by joining personality, occupation, ability, or visual-keyword characters or nouns just because those concepts appear in the brief. Treat them as character context, not a default name recipe. Word-based or coined candidates remain eligible when they work independently as a natural, memorable person-level display name.
- Consider genuinely different naming possibilities that fit this person and world. Style families are open descriptions, not a checklist: do not require a fixed count, proportion, or rotation of Chinese, foreign-language, coined, word-based, alias, or title forms. Do not force cross-language or cross-cultural names to manufacture variety. When evidence truly constrains naming, identify that evidence; do not invent a cultural restriction.
- A Latin spelling alone does not establish a foreign-language name or etymology. Treat language or cultural origin as unconfirmed unless supported by the supplied context, and describe an original coinage without fabricating a source.
- Produce three to five meaningfully different character-name candidates. Each must identify a particular person, not merely describe who holds a job. A place, rank, contract, assignment, or incident modifier does not turn a job description into an independent name; if another person could take the same role and use the same label, classify it as OCCUPATION_DESCRIPTION.
- Compare the candidates' actual forms and person-level identities, not only their different style labels. If they share essentially the same name structure, do not describe label changes as meaningful diversity; explore another suitable form when one naturally fits, without forcing a template.
- Give each candidate an identity_kind from PERSONAL_NAME, ALIAS, CODENAME, HONORIFIC_TITLE, OCCUPATION_DESCRIPTION, or PLACEHOLDER. A formal title or codename is allowed when it functions as this character's own recognizable identity, rather than a duty label.
- For every candidate, provide identity_rationale: cite a concrete person-level anchor from the supplied brief, Canon, or selected concept, and explain why the name identifies this character independently of their occupation. A generic claim that the name is distinctive, attractive, or fitting is not enough. Do not invent Canon support or etymology.
- Also include a concise form description, cultural inspiration, phonetic rationale, character alignment, and tradeoffs. Use the phonetic rationale for a plausible spoken reading and cadence, and state when the reading or origin is uncertain. These are reasons for review, not verified origins or proof of quality. A name need not explain the character's personality, carry a literary allusion, or have a symbolic interpretation; do not invent one to make a candidate sound meaningful.
- Select only a candidate that meets the person-identity requirement. Compare how naturally each candidate reads aloud, how easily players can recall and distinguish it from the roster, its fit with available cultural/world evidence, and its actual advantage over the alternatives. Consider obvious same-sounding or confusing names of well-known real people, but do not invent matches or claim an exhaustive external search; record unresolved reading or association risks for human review. An appealing meaning, personality symbolism, novelty, rarity, or foreign appearance cannot rescue an awkward spoken name. If selecting a conventional Chinese surname-plus-given-name form in an open naming context, state its concrete advantage over the available candidates rather than relying only on generic fit or symbolism. List considered but rejected candidates with concise reasons. If no candidate is acceptable, set selected_candidate_id to NO_VALID_CANDIDATE and explain that the pool contains no independent person name; do not select the least-bad role description. User-explicit names are preserved deterministically after your proposal.
- If a selected concept seed is supplied, preserve its dramatic axis and player hook while elaborating it. Do not silently replace the selected direction.
- Do not output biography prose, dialogue, voice lines, a complete skill kit, an image prompt, Canon facts, or relationship writes.
- Keep field values concise: use short phrases or brief sentences, not essay-length explanations.
- Do not restate input context, repeat Canon evidence, or duplicate GAP descriptions unnecessarily.

OUTPUT CONTRACT
Return one JSON object with optional sections narrative_role, character_core, relationship_strategy, gameplay_identity, visual_identity, arc_seed, reference_basis, and risks, plus the required character_naming section.
Use only the field names supplied in the request contract. Omit unresolved fields; do not output nulls. Do not output status, intent, request_id, constraints, product_roster_positioning, combat_role_profile, canon_grounded_relationships, requested_relationships, or reference IDs.
Relationship entries contain only target and description. Descriptions explain a useful tension or complementary need and are proposals, not existing facts.
All risk values are advisory string arrays; do not output scores or percentages.
"""

_TEXT_FIELDS = frozenset(
    {
        "dramatic_function",
        "story_entry_function",
        "protagonist_connection",
        "faction_story_function",
        "long_term_narrative_utility",
        "surface_impression",
        "core_desire",
        "core_fear",
        "internal_contradiction",
        "false_belief",
        "emotional_need",
        "values_or_moral_boundary",
        "behavioral_pressure_point",
        "gameplay_fantasy",
        "mechanic_identity_direction",
        "narrative_gameplay_linkage",
        "field_time",
        "team_handoff",
        "silhouette_direction",
        "motif_direction",
        "costume_logic",
        "signature_visual_feature",
        "initial_state",
        "pressure_point",
        "possible_transformation",
        "unresolved_future_hook",
        "novelty_basis",
    }
)
_SEQUENCE_FIELDS = frozenset({"resource_model", "state_model", "core_loop", "payoff", "coverage_notes"})
_ROLE_FIELDS = frozenset(
    {
        "dramatic_function",
        "story_entry_function",
        "protagonist_connection",
        "faction_story_function",
        "long_term_narrative_utility",
    }
)
_CORE_FIELDS = frozenset(
    {
        "surface_impression",
        "core_desire",
        "core_fear",
        "internal_contradiction",
        "false_belief",
        "emotional_need",
        "values_or_moral_boundary",
        "behavioral_pressure_point",
    }
)
_GAMEPLAY_FIELDS = frozenset(
    {
        "gameplay_fantasy",
        "mechanic_identity_direction",
        "narrative_gameplay_linkage",
        "field_time",
        "resource_model",
        "state_model",
        "core_loop",
        "payoff",
        "team_handoff",
    }
)
_VISUAL_FIELDS = frozenset(
    {"silhouette_direction", "motif_direction", "costume_logic", "signature_visual_feature"}
)
_ARC_FIELDS = frozenset(
    {"initial_state", "pressure_point", "possible_transformation", "unresolved_future_hook"}
)
_RISK_FIELDS = frozenset(
    {
        "roster_overlap_risks",
        "trope_dependence_risks",
        "genericness_risks",
        "canon_risks",
        "relationship_contradiction_risks",
        "combat_identity_overlap_risks",
        "visual_overlap_risks",
    }
)
_RELATION_FIELDS = frozenset(
    {"proposed_relationship_opportunities", "conflict_opportunities", "affinity_opportunities"}
)
_SECTION_FIELDS = {
    "narrative_role": _ROLE_FIELDS,
    "character_core": _CORE_FIELDS,
    "gameplay_identity": _GAMEPLAY_FIELDS,
    "visual_identity": _VISUAL_FIELDS,
    "arc_seed": _ARC_FIELDS,
    "reference_basis": frozenset({"novelty_basis", "coverage_notes"}),
    "risks": _RISK_FIELDS,
    "relationship_strategy": _RELATION_FIELDS,
}
_PROPOSAL_FIELDS = frozenset((*_SECTION_FIELDS, "character_naming"))


class CharacterPlannerV1Error(ValueError):
    """Raised when one bounded Planner response cannot satisfy its contract."""


@dataclass(frozen=True)
class CharacterPlannerV1Diagnostics:
    context_snapshot_id: str
    logical_invocation_count: int
    structured_parse_succeeded: bool
    status: CharacterDesignPlanV2Status
    unresolved_fields: tuple[str, ...]
    gap_codes: tuple[str, ...]
    model_invocation: ModelInvocationAudit | None = None
    selected_concept_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        audit = self.model_invocation
        return {
            "context_snapshot_id": self.context_snapshot_id,
            "logical_invocation_count": self.logical_invocation_count,
            "structured_parse_succeeded": self.structured_parse_succeeded,
            "status": self.status.value,
            "unresolved_fields": list(self.unresolved_fields),
            "gap_codes": list(self.gap_codes),
            "selected_concept_id": self.selected_concept_id,
            "model_invocation": (
                {
                    "provider": audit.provider,
                    "model": audit.model,
                    "outcome": audit.outcome,
                    "latency_ms": audit.latency_ms,
                    "retry_count": audit.retry_count,
                    "response_contract": audit.response_contract,
                    "purpose": audit.purpose,
                }
                if audit is not None
                else None
            ),
        }


@dataclass(frozen=True)
class CharacterPlannerV1Result:
    """Inspectable, non-persistent result for the Planner developer harness."""

    input_shadow_plan: Mapping[str, Any]
    context_snapshot: Mapping[str, Any]
    plan: CharacterDesignPlanV2
    proposal: Mapping[str, Any]
    diagnostics: CharacterPlannerV1Diagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_shadow_plan": dict(self.input_shadow_plan),
            "context_snapshot": dict(self.context_snapshot),
            "proposal": dict(self.proposal),
            "plan": self.plan.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CharacterPlannerV1Error(f"{field_name} must be an array of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CharacterPlannerV1Error(f"{field_name} must contain non-empty strings")
        cleaned = item.strip()
        if cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterPlannerV1Error(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_relationships(value: object, field_name: str) -> tuple[Mapping[str, str], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CharacterPlannerV1Error(f"{field_name} must be an array")
    result: list[Mapping[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"target", "description"}:
            raise CharacterPlannerV1Error(
                f"{field_name}[{index}] must contain only target and description"
            )
        result.append(
            {"target": _text(item["target"], f"{field_name}[{index}].target"),
             "description": _text(item["description"], f"{field_name}[{index}].description")}
        )
    return tuple(result)


def _validate_proposal(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterPlannerV1Error("Planner output must be a JSON object")
    if "character_naming" not in value:
        raise CharacterPlannerV1Error("Planner output is missing required character_naming")
    unknown = set(value) - _PROPOSAL_FIELDS
    if unknown:
        raise CharacterPlannerV1Error(f"Planner output has unknown field(s): {sorted(unknown)}")
    if not value:
        raise CharacterPlannerV1Error("Planner output must contain one proposal section")
    result: dict[str, Any] = {}
    for section, allowed in _SECTION_FIELDS.items():
        if section not in value:
            continue
        raw_section = value[section]
        if not isinstance(raw_section, Mapping):
            raise CharacterPlannerV1Error(f"{section} must be an object")
        section_unknown = set(raw_section) - allowed
        if section_unknown:
            raise CharacterPlannerV1Error(
                f"{section} has unknown field(s): {sorted(section_unknown)}"
            )
        parsed: dict[str, Any] = {}
        for field_name, raw in raw_section.items():
            path = f"{section}.{field_name}"
            if section == "relationship_strategy":
                parsed[field_name] = _validate_relationships(raw, path)
            elif field_name in _SEQUENCE_FIELDS or field_name in _RISK_FIELDS:
                parsed[field_name] = _strings(raw, path)
            elif field_name in _TEXT_FIELDS:
                parsed[field_name] = _text(raw, path)
            else:
                raise CharacterPlannerV1Error(f"Unsupported Planner field: {path}")
        result[section] = parsed
    if "character_naming" in value:
        if not isinstance(value["character_naming"], Mapping):
            raise CharacterPlannerV1Error("character_naming must be an object")
        result["character_naming"] = dict(value["character_naming"])
    return result


def build_character_planner_proposal_schema() -> dict[str, Any]:
    """Build the provider-facing schema from the Planner validation contract."""

    properties: dict[str, Any] = {}
    for section, allowed_fields in _SECTION_FIELDS.items():
        section_properties: dict[str, Any] = {}
        for field_name in sorted(allowed_fields):
            if section == "relationship_strategy":
                section_properties[field_name] = {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "target": {"type": "string", "minLength": 1},
                            "description": {"type": "string", "minLength": 1},
                        },
                        "required": ["target", "description"],
                    },
                }
            elif field_name in _SEQUENCE_FIELDS or field_name in _RISK_FIELDS:
                section_properties[field_name] = {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                }
            else:
                section_properties[field_name] = {"type": "string", "minLength": 1}
        properties[section] = {
            "type": "object",
            "additionalProperties": False,
            "properties": section_properties,
        }
    properties["character_naming"] = naming_design_schema()
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["character_naming"],
    }


def validate_character_planner_proposal(value: object) -> dict[str, Any]:
    """Validate one provider payload without accepting an envelope or full plan."""

    return _validate_proposal(value)


def _parse_provider_proposal_output(turn: ModelTurn) -> dict[str, Any]:
    """Project provider drift to the proposal contract before strict validation."""

    if not isinstance(turn, ModelTurn):
        raise CharacterPlannerV1Error("AgentModel must return ModelTurn")
    output = turn.structured_output
    if output is None and isinstance(turn.text, str) and turn.text.strip():
        try:
            output = json.loads(turn.text)
        except json.JSONDecodeError as exc:
            raise CharacterPlannerV1Error("Planner returned malformed JSON") from exc
    if not isinstance(output, Mapping):
        raise CharacterPlannerV1Error("Planner output must be a JSON object")
    for wrapper in ("character_planner_proposal", "character_design_plan", "plan"):
        nested = output.get(wrapper)
        if len(output) == 1 and isinstance(nested, Mapping):
            output = nested
            break
    _reject_forbidden_proposal_keys(output)
    for section, raw_section in output.items():
        if section not in _SECTION_FIELDS or not isinstance(raw_section, Mapping):
            continue
        authority_only = {
            "combat_role_profile",
            "canon_grounded_relationships",
            "requested_relationships",
        } & set(raw_section)
        if authority_only and not (set(raw_section) & _SECTION_FIELDS[section]):
            raise CharacterPlannerV1Error(
                f"Planner section {section!r} contains only protected authority fields"
            )
    projected: dict[str, Any] = {}
    for section, allowed_fields in _SECTION_FIELDS.items():
        raw_section = output.get(section)
        if not isinstance(raw_section, Mapping):
            continue
        if section == "relationship_strategy":
            section_value: dict[str, Any] = {}
            for field_name in _RELATION_FIELDS:
                raw_entries = raw_section.get(field_name)
                if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
                    continue
                entries = [
                    {"target": item["target"], "description": item["description"]}
                    for item in raw_entries
                    if isinstance(item, Mapping)
                    and "target" in item
                    and "description" in item
                ]
                if entries:
                    section_value[field_name] = entries
            if section_value:
                projected[section] = section_value
            continue
        section_value = {
            field_name: raw_section[field_name]
            for field_name in allowed_fields
            if field_name in raw_section
        }
        if section_value:
            projected[section] = section_value
    if isinstance(output.get("character_naming"), Mapping):
        projected["character_naming"] = output["character_naming"]
    return _validate_proposal(projected)


def _reject_forbidden_proposal_keys(value: object, *, location: str = "$") -> None:
    """Fail closed when a proposal attempts to author protected plan fields."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "status":
                if not isinstance(nested, str) or nested.casefold() != "proposed":
                    raise CharacterPlannerV1Error(
                        f"Planner proposal contains non-proposal status at {location}.status"
                    )
                continue
            if key in {
                "constraints",
                "combat_role_profile",
                "canon_grounded_relationships",
                "requested_relationships",
            }:
                continue
            if isinstance(key, str) and key in _FORBIDDEN_PROPOSAL_KEYS:
                raise CharacterPlannerV1Error(
                    f"Planner proposal contains forbidden field {location}.{key}"
                )
            _reject_forbidden_proposal_keys(nested, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_forbidden_proposal_keys(nested, location=f"{location}[{index}]")


def _drop_empty(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: cleaned
            for key, raw in value.items()
            if (cleaned := _drop_empty(raw)) not in (None, "", [], {})
        }
    if isinstance(value, (list, tuple)):
        return [cleaned for raw in value if (cleaned := _drop_empty(raw)) not in (None, "", [], {})]
    return value


def _context_payload(
    context: CharacterPlanningContextV2,
    selected_concept_seed: CharacterConceptSeedV2 | None = None,
) -> dict[str, Any]:
    snapshot = context.to_dict()
    constraints = {
        "hard": [
            item for item in snapshot["plan_v2"]["constraints"] if item["kind"] == "HARD"
        ],
        "soft": [
            item for item in snapshot["plan_v2"]["constraints"] if item["kind"] == "SOFT"
        ],
        "inferred": [
            item for item in snapshot["plan_v2"]["constraints"] if item["kind"] == "INFERRED"
        ],
    }
    plan = snapshot["plan_v2"]
    shadow_binding = {
        "status": plan["status"],
        "constraints": constraints,
        "requested_relationships": plan["relationship_strategy"]["requested_relationships"],
        "combat_role_profile": plan["gameplay_identity"]["combat_role_profile"],
        "unresolved_questions": plan["unresolved_questions"],
    }
    payload = {
        "authority_order": [
            "USER_HARD_REQUIREMENT",
            "PROJECT_CANON",
            "DETERMINISTIC_PROJECT_SEMANTICS",
            "EXPLICIT_PROJECT_ROSTER_AND_RELATION_DATA",
            "USER_SOFT_PREFERENCE",
            "REFERENCE_PRECEDENT",
            "PLANNER_CREATIVE_PROPOSAL",
        ],
        "user_requirements": {
            "intent": _drop_empty(snapshot["intent"]),
            "constraints": constraints,
            "requested_relationships": snapshot["requested_relationships"],
        },
        "authoritative_canon": {
            "items": _drop_empty(snapshot["canon"]),
            "relationships": snapshot["canon_relationships"],
            "story": snapshot["story"],
        },
        "deterministic_project_semantics": snapshot["combat"],
        "project_roster_evidence": {
            "characters": _drop_empty(snapshot["roster"]),
            "coverage": snapshot["roster_coverage"],
            "signatures": snapshot["roster_signatures"],
            "overlap_evidence": snapshot["overlap_evidence"],
        },
        "relationship_context": {
            "requested": snapshot["requested_relationships"],
            "unresolved": snapshot["unresolved_relationships"],
            "canon": snapshot["canon_relationships"],
            "reference": snapshot["reference_relationships"],
            "draft": snapshot["draft_relationships"],
            "evaluation": snapshot["evaluation_relationships"],
            "vocabulary": snapshot["relationship_vocabulary"],
        },
        "reference_precedent": _drop_empty(snapshot["references"]),
        "known_gaps": snapshot["gaps"],
        "input_shadow_plan": shadow_binding,
    }
    if selected_concept_seed is not None:
        payload["selected_concept_seed"] = selected_concept_seed.to_provider_dict()
    return payload


def build_character_planner_prompt(
    context: CharacterPlanningContextV2,
    *,
    selected_concept_seed: CharacterConceptSeedV2 | None = None,
) -> AgentPrompt:
    """Build the provider-neutral, sectioned Planner prompt."""

    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    if selected_concept_seed is not None and not isinstance(
        selected_concept_seed, CharacterConceptSeedV2
    ):
        raise TypeError("selected_concept_seed must be a CharacterConceptSeedV2")
    payload = _context_payload(context, selected_concept_seed)
    return AgentPrompt(
        system_contract=PLANNER_V1_SYSTEM_CONTRACT,
        character=NpcCharacterView(
            "planner_v1",
            "Character Planner v1",
            "planning",
            (),
            (),
            "structured planning",
            "structured planning",
            (),
            "no factual claims",
            "planner",
        ),
        runtime=NpcRuntimeView(
            "planner_v1",
            "Character Planning V2",
            None,
            (),
            (),
        ),
        messages=(ConversationMessage("user", "Produce one structured high-level design proposal."),),
        available_tools=(),
        session_id=f"character-planner-v1:{context.plan_v2.request_id}",
        turn_number=1,
        response_format=PLANNER_V1_RESPONSE_FORMAT,
        authoring_payload=payload,
        invocation_purpose=PLANNER_V1_INVOCATION_PURPOSE,
    )


def _decision(field_path: str, note: str) -> CharacterPlanV2Decision:
    return CharacterPlanV2Decision(
        field_path,
        CharacterPlanV2Owner.PLANNER,
        CharacterPlanV2Source.PLANNER_PROPOSAL,
        note=note,
    )


def _merge_optional_section(current: Any, proposal: Mapping[str, Any], field_path: str, decisions: list[CharacterPlanV2Decision]) -> Any:
    updates: dict[str, Any] = {}
    for field_name, value in proposal.items():
        existing = getattr(current, field_name)
        if existing is not None and existing != ():
            continue
        updates[field_name] = value
        decisions.append(_decision(f"{field_path}.{field_name}", "Proposed by one bounded Planner invocation."))
    return replace(current, **updates) if updates else current


def _merge_relationships(
    current: CharacterPlanV2RelationshipStrategy,
    proposal: Mapping[str, Sequence[Mapping[str, str]]],
    decisions: list[CharacterPlanV2Decision],
) -> CharacterPlanV2RelationshipStrategy:
    updates: dict[str, tuple[CharacterPlanV2RelationshipBinding, ...]] = {}
    for field_name, entries in proposal.items():
        existing = list(getattr(current, field_name))
        known = {(item.target, item.description) for item in existing}
        added = 0
        for entry in entries:
            marker = (entry["target"], entry["description"])
            if marker in known:
                continue
            existing.append(
                CharacterPlanV2RelationshipBinding(
                    target=entry["target"],
                    source=CharacterPlanV2Source.PLANNER_PROPOSAL,
                    description=entry["description"],
                )
            )
            known.add(marker)
            added += 1
        if added:
            updates[field_name] = tuple(existing)
            decisions.append(_decision(f"relationship_strategy.{field_name}", "Proposal only; not an existing relationship."))
    return replace(current, **updates) if updates else current


def _merge_plan(
    shadow: CharacterDesignPlanV2,
    context: CharacterPlanningContextV2,
    proposal: Mapping[str, Any],
    selected_concept_seed: CharacterConceptSeedV2 | None = None,
) -> CharacterDesignPlanV2:
    decisions = list(shadow.decisions)
    if selected_concept_seed is not None:
        decisions.append(
            CharacterPlanV2Decision(
                "selected_concept_seed",
                CharacterPlanV2Owner.PLANNER,
                CharacterPlanV2Source.CONCEPT_SELECTION,
                note="Selected seed is the bounded creative direction for this Planner invocation.",
            )
        )
    narrative = _merge_optional_section(shadow.narrative_role, proposal.get("narrative_role", {}), "narrative_role", decisions)
    core = _merge_optional_section(shadow.character_core, proposal.get("character_core", {}), "character_core", decisions)
    gameplay = _merge_optional_section(shadow.gameplay_identity, proposal.get("gameplay_identity", {}), "gameplay_identity", decisions)
    visual = _merge_optional_section(shadow.visual_identity, proposal.get("visual_identity", {}), "visual_identity", decisions)
    arc = _merge_optional_section(shadow.arc_seed, proposal.get("arc_seed", {}), "arc_seed", decisions)
    risks = _merge_optional_section(shadow.risks, proposal.get("risks", {}), "risks", decisions)
    relationships = _merge_relationships(
        shadow.relationship_strategy,
        proposal.get("relationship_strategy", {}),
        decisions,
    )
    reference = shadow.reference_basis
    reference_proposal = proposal.get("reference_basis", {})
    reference_updates: dict[str, Any] = {}
    if reference.novelty_basis is None and "novelty_basis" in reference_proposal:
        reference_updates["novelty_basis"] = reference_proposal["novelty_basis"]
        decisions.append(_decision("reference_basis.novelty_basis", "Planner rationale; reference provenance remains deterministic."))
    if "coverage_notes" in reference_proposal:
        notes = tuple(dict.fromkeys((*reference.coverage_notes, *reference_proposal["coverage_notes"])))
        if notes != reference.coverage_notes:
            reference_updates["coverage_notes"] = notes
            decisions.append(_decision("reference_basis.coverage_notes", "Planner limitation note; precedent remains separate."))
    if reference_updates:
        reference = replace(reference, **reference_updates)

    raw_naming = proposal.get("character_naming")
    if not isinstance(raw_naming, Mapping):
        raise CharacterPlannerV1Error("Planner naming design is required")
    naming_design = CharacterNamingDesignV1.from_mapping(raw_naming)
    decisions.append(
        CharacterPlanV2Decision(
            "naming_design.selected_name",
            (
                CharacterPlanV2Owner.USER
                if naming_design.owner is CharacterNamingOwner.USER_SPECIFIED
                else CharacterPlanV2Owner.PLANNER
            ),
            (
                CharacterPlanV2Source.USER_SUPPLIED
                if naming_design.owner is CharacterNamingOwner.USER_SPECIFIED
                else CharacterPlanV2Source.PLANNER_PROPOSAL
            ),
            note="Explicit user names retain ownership; otherwise the validated Planner selection is frozen.",
        )
    )

    merged = replace(
        shadow,
        status=CharacterDesignPlanV2Status.PROPOSED,
        narrative_role=narrative,
        character_core=core,
        relationship_strategy=relationships,
        gameplay_identity=gameplay,
        visual_identity=visual,
        arc_seed=arc,
        reference_basis=reference,
        risks=risks,
        naming_design=naming_design,
        decisions=tuple(dict.fromkeys(decisions)),
        warnings=tuple(
            dict.fromkeys(
                (
                    *shadow.warnings,
                    *(f"CONTEXT_GAP:{gap.code.value}" for gap in context.gaps),
                )
            )
        ),
    )
    unresolved = []
    for field_name in shadow.unresolved_questions:
        value = getattr(merged, field_name, None)
        if field_name == "future_relationship_opportunities":
            value = merged.relationship_strategy.proposed_relationship_opportunities
        elif field_name == "differentiation_risk_analysis":
            value = merged.risks
        if value is None:
            unresolved.append(field_name)
        elif isinstance(value, tuple):
            if not value:
                unresolved.append(field_name)
        elif not any(getattr(value, name) for name in value.__dataclass_fields__):
            unresolved.append(field_name)
    return replace(merged, unresolved_questions=tuple(unresolved))


def run_character_planner_v1(
    shadow_plan: CharacterDesignPlanV2,
    context: CharacterPlanningContextV2,
    model: AgentModel,
    *,
    selected_concept_seed: CharacterConceptSeedV2 | None = None,
) -> CharacterPlannerV1Result:
    """Run exactly one provider-neutral planning invocation and merge safely."""

    if not isinstance(shadow_plan, CharacterDesignPlanV2):
        raise TypeError("shadow_plan must be a CharacterDesignPlanV2")
    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    if context.plan_v2 != shadow_plan:
        raise ValueError("context.plan_v2 must be the supplied shadow_plan")
    if selected_concept_seed is not None and not isinstance(
        selected_concept_seed, CharacterConceptSeedV2
    ):
        raise TypeError("selected_concept_seed must be a CharacterConceptSeedV2")
    if shadow_plan.status is not CharacterDesignPlanV2Status.SHADOW_PROJECTED:
        raise ValueError("Planner v1 accepts only SHADOW_PROJECTED plans")
    prompt = build_character_planner_prompt(
        context,
        selected_concept_seed=selected_concept_seed,
    )
    turn = model.generate(prompt)
    proposal = _parse_provider_proposal_output(turn)
    raw_naming = proposal.get("character_naming")
    try:
        naming = validate_character_naming_design(
            raw_naming,
            user_texts=(
                context.intent.raw_request,
                *(
                    constraint.value
                    for constraint in context.plan_v2.constraints
                    if constraint.kind.value == "HARD"
                ),
            ),
            canon_names=tuple(
                item.display_name
                for item in context.canon
                if item.display_name and item.entity_type.casefold() == "character"
            )
            + tuple(
                item.display_name
                for item in context.roster
                if item.display_name and item.source_class.value == "CANON_PROJECT_CHARACTER"
            ),
            reference_names=tuple(
                item.display_name for item in context.references if item.display_name
            ),
            occupation_context=(
                selected_concept_seed.one_line_identity
                if selected_concept_seed is not None
                else "",
                context.plan_v2.narrative_role.dramatic_function or "",
                context.plan_v2.character_core.surface_impression or "",
            ),
        )
    except NamingDesignError as error:
        raise CharacterPlannerV1Error(
            "Planner naming proposal failed hard candidate validation: " + str(error)
        ) from error
    proposal["character_naming"] = naming.to_dict()
    plan = _merge_plan(shadow_plan, context, proposal, selected_concept_seed)
    diagnostics = CharacterPlannerV1Diagnostics(
        context_snapshot_id=context.snapshot_id,
        logical_invocation_count=1,
        structured_parse_succeeded=True,
        status=plan.status,
        unresolved_fields=plan.unresolved_questions,
        gap_codes=tuple(gap.code.value for gap in context.gaps),
        model_invocation=turn.invocation,
        selected_concept_id=(
            selected_concept_seed.concept_id
            if selected_concept_seed is not None
            else None
        ),
    )
    return CharacterPlannerV1Result(
        input_shadow_plan=shadow_plan.to_dict(),
        context_snapshot=context.to_dict(),
        proposal=proposal,
        plan=plan,
        diagnostics=diagnostics,
    )


def plan_character_v2(
    shadow_plan: CharacterDesignPlanV2,
    context: CharacterPlanningContextV2,
    model: AgentModel,
    *,
    selected_concept_seed: CharacterConceptSeedV2 | None = None,
) -> CharacterDesignPlanV2:
    """Return one proposed V2 plan; no Generator or persistence integration."""

    return run_character_planner_v1(
        shadow_plan,
        context,
        model,
        selected_concept_seed=selected_concept_seed,
    ).plan


__all__ = [
    "PLANNER_V1_INVOCATION_PURPOSE",
    "PLANNER_V1_RESPONSE_FORMAT",
    "PLANNER_V1_SYSTEM_CONTRACT",
    "CharacterPlannerV1Diagnostics",
    "CharacterPlannerV1Error",
    "CharacterPlannerV1Result",
    "build_character_planner_proposal_schema",
    "build_character_planner_prompt",
    "plan_character_v2",
    "run_character_planner_v1",
    "validate_character_planner_proposal",
]
