"""Canon-aware character authoring agent.

This module deliberately keeps authoring separate from the in-world NPC
conversation consumer.  The model receives a small authoring view and can
only obtain Canon through the read-only tools below; it never receives a
resolver, repository, path or writable object.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from knowledge import KnowledgeResolver
from knowledge.loader import default_data_dir
from story import StoryRepository, load_story_repository

from .errors import (
    AgentExecutionError,
    AgentToolError,
    ModelError,
    ModelMalformedResponseError,
)
from .model_protocol import AgentModel
from .models import (
    AgentPrompt,
    ConversationMessage,
    GroundingEvidence,
    GroundingEvidenceType,
    ModelInvocationAudit,
    ModelTurn,
    ToolAuditEntry,
    ToolCall,
    ToolDefinition,
)
from .response_contracts import (
    CHARACTER_DRAFT_JSON_SCHEMA,
    character_draft_prompt_contract,
)


@dataclass(frozen=True)
class CharacterDesignRequest:
    """A planner brief split into machine-auditable intent categories."""

    brief: str
    hard_constraints: tuple[str, ...] = ()
    soft_preferences: tuple[str, ...] = ()
    forbidden_elements: tuple[str, ...] = ()
    desired_connections: tuple[str, ...] = ()
    request_id: str = "request_001"

    def __post_init__(self) -> None:
        if not isinstance(self.brief, str) or not self.brief.strip():
            raise ValueError("brief must be a non-empty string")
        if not isinstance(self.request_id, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.-]*", self.request_id
        ):
            raise ValueError("request_id must be a safe identifier")
        for name in (
            "hard_constraints",
            "soft_preferences",
            "forbidden_elements",
            "desired_connections",
        ):
            value = getattr(self, name)
            if isinstance(value, (str, bytes)) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(item.strip() for item in value))

    @property
    def freeform_brief(self) -> str:
        return self.brief

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief": self.brief.strip(),
            "hard_constraints": list(self.hard_constraints),
            "soft_preferences": list(self.soft_preferences),
            "forbidden_elements": list(self.forbidden_elements),
            "desired_connections": list(self.desired_connections),
            "request_id": self.request_id,
        }


@dataclass(frozen=True)
class CanonBasisEntry:
    source_id: str
    supports: tuple[str, ...] = ()
    source_type: str | None = None

    def __getitem__(self, key: str) -> Any:
        if key == "source_id":
            return self.source_id
        if key == "supports":
            return self.supports
        if key == "source_type":
            return self.source_type
        raise KeyError(key)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_id": self.source_id,
            "supports": list(self.supports),
        }
        if self.source_type is not None:
            result["source_type"] = self.source_type
        return result


@dataclass(frozen=True)
class StoryLink:
    target_id: str
    relation: str = "related_context"
    status: str = "canon_backed"

    def __getitem__(self, key: str) -> str:
        if key == "target_id":
            return self.target_id
        if key == "relation":
            return self.relation
        if key == "status":
            return self.status
        raise KeyError(key)

    def to_dict(self) -> dict[str, str]:
        return {
            "target_id": self.target_id,
            "relation": self.relation,
            "status": self.status,
        }


@dataclass(frozen=True)
class CharacterDraft:
    """Strict, approval-independent candidate character representation."""

    draft_id: str
    status: str
    name: str
    canonical_character_id: str | None = None
    age: int | None = None
    age_range: str | None = None
    gender: str | None = None
    faction_id: str | None = None
    occupation: str = ""
    social_role: str = ""
    combat_role: str = "none"
    design_pitch: str = ""
    personality: tuple[str, ...] = ()
    background: str = ""
    story_hook: str = ""
    relationships: tuple[Mapping[str, Any], ...] = ()
    ability_concept: str = ""
    knowledge_scope: str = ""
    canon_basis: tuple[CanonBasisEntry, ...] = ()
    new_design_elements: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    constraint_notes: tuple[str, ...] = ()
    story_link: StoryLink | None = None
    proposed_new_content: tuple[str, ...] = ()

    _KNOWN_FIELDS = frozenset(CHARACTER_DRAFT_JSON_SCHEMA["properties"])

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        if not isinstance(payload, Mapping):
            raise ModelMalformedResponseError("CharacterDraft must be a JSON object")
        unknown = set(payload) - cls._KNOWN_FIELDS
        if unknown:
            raise ModelMalformedResponseError(
                f"CharacterDraft has unknown field(s): {sorted(unknown)}"
            )
        required = {"draft_id", "status", "name", "canon_basis", "new_design_elements", "open_questions"}
        missing = required - set(payload)
        if missing:
            raise ModelMalformedResponseError(
                f"CharacterDraft is missing field(s): {sorted(missing)}"
            )

        def string(name: str, *, optional: bool = False) -> str | None:
            value = payload.get(name)
            if value is None and optional:
                return None
            if not isinstance(value, str) or not value.strip():
                raise ModelMalformedResponseError(f"CharacterDraft.{name} must be a non-empty string")
            return value.strip()

        draft_id = string("draft_id")
        status = string("status")
        name = string("name")
        assert draft_id is not None and status is not None and name is not None
        if status != "draft":
            raise ModelMalformedResponseError("CharacterDraft.status must be 'draft'")
        if not re.fullmatch(r"draft_[A-Za-z0-9][A-Za-z0-9_.-]*", draft_id):
            raise ModelMalformedResponseError("draft_id must use the draft_ namespace")

        age = payload.get("age")
        if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
            raise ModelMalformedResponseError("CharacterDraft.age must be a non-negative integer or null")
        age_range = string("age_range", optional=True) if "age_range" in payload else None
        gender = string("gender", optional=True) if "gender" in payload else None
        faction_id = string("faction_id", optional=True) if "faction_id" in payload else None
        canonical_id = payload.get("canonical_character_id")
        if canonical_id is not None:
            if not isinstance(canonical_id, str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.:-]*", canonical_id
            ):
                raise ModelMalformedResponseError(
                    "canonical_character_id must be a strict string ID or null"
                )
            raise ModelMalformedResponseError(
                "v0.1 drafts must not claim a canonical character ID"
            )

        def strings(name: str) -> tuple[str, ...]:
            value = payload.get(name, [])
            if isinstance(value, (str, bytes)) or not isinstance(value, list):
                raise ModelMalformedResponseError(f"CharacterDraft.{name} must be an array of strings")
            if not all(isinstance(item, str) and item.strip() for item in value):
                raise ModelMalformedResponseError(f"CharacterDraft.{name} contains an invalid string")
            return tuple(item.strip() for item in value)

        def text(name: str) -> str:
            value = payload.get(name, "")
            if not isinstance(value, str):
                raise ModelMalformedResponseError(f"CharacterDraft.{name} must be a string")
            return value.strip()

        canon_raw = payload.get("canon_basis")
        if not isinstance(canon_raw, list):
            raise ModelMalformedResponseError("CharacterDraft.canon_basis must be an array")
        basis: list[CanonBasisEntry] = []
        seen_sources: set[str] = set()
        for item in canon_raw:
            if isinstance(item, str):
                item = {"source_id": item, "supports": []}
            if not isinstance(item, Mapping):
                raise ModelMalformedResponseError("canon_basis entries must be objects")
            if set(item) - {"source_id", "supports", "source_type"}:
                raise ModelMalformedResponseError("canon_basis entry has unknown fields")
            source_id = item.get("source_id")
            supports = item.get("supports", [])
            source_type = item.get("source_type")
            if not isinstance(source_id, str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.:-]*", source_id
            ):
                raise ModelMalformedResponseError("canon_basis source_id must be a strict string ID")
            if isinstance(supports, (str, bytes)) or not isinstance(supports, list) or not all(
                isinstance(value, str) and value.strip() for value in supports
            ):
                raise ModelMalformedResponseError("canon_basis supports must be an array of strings")
            if source_type is not None and (not isinstance(source_type, str) or not source_type.strip()):
                raise ModelMalformedResponseError("canon_basis source_type must be a string")
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            basis.append(CanonBasisEntry(source_id, tuple(s.strip() for s in supports), source_type))

        relationships_raw = payload.get("relationships", [])
        if not isinstance(relationships_raw, list):
            raise ModelMalformedResponseError("CharacterDraft.relationships must be an array")
        relationships: list[Mapping[str, Any]] = []
        for item in relationships_raw:
            if not isinstance(item, Mapping):
                raise ModelMalformedResponseError("relationship entries must be objects")
            if set(item) - {"target_id", "description", "status", "type"}:
                raise ModelMalformedResponseError("relationship entry has unknown fields")
            target_id = item.get("target_id")
            if target_id is not None and (
                not isinstance(target_id, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", target_id)
            ):
                raise ModelMalformedResponseError("relationship target_id must be a strict string ID")
            clean = {key: value for key, value in item.items()}
            relationships.append(MappingProxyType(clean))

        story_raw = payload.get("story_link")
        story_link = None
        if story_raw is not None:
            if not isinstance(story_raw, Mapping) or set(story_raw) - {"target_id", "relation", "status"}:
                raise ModelMalformedResponseError("story_link has an invalid shape")
            target = story_raw.get("target_id")
            if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", target):
                raise ModelMalformedResponseError("story_link.target_id must be a strict string ID")
            relation = story_raw.get("relation", "related_context")
            link_status = story_raw.get("status", "canon_backed")
            if not isinstance(relation, str) or not relation.strip() or not isinstance(link_status, str):
                raise ModelMalformedResponseError("story_link fields are malformed")
            story_link = StoryLink(target, relation.strip(), link_status.strip())

        combat_role = text("combat_role") or "none"
        if combat_role not in {"support", "control", "defense", "burst", "sustain", "flex", "none"}:
            raise ModelMalformedResponseError("combat_role is unsupported")
        return cls(
            draft_id=draft_id,
            status=status,
            name=name,
            canonical_character_id=None,
            age=age,
            age_range=age_range,
            gender=gender,
            faction_id=faction_id,
            occupation=text("occupation"),
            social_role=text("social_role"),
            combat_role=combat_role,
            design_pitch=text("design_pitch"),
            personality=strings("personality"),
            background=text("background"),
            story_hook=text("story_hook"),
            relationships=tuple(relationships),
            ability_concept=text("ability_concept"),
            knowledge_scope=text("knowledge_scope"),
            canon_basis=tuple(basis),
            new_design_elements=strings("new_design_elements"),
            open_questions=strings("open_questions"),
            constraint_notes=strings("constraint_notes"),
            story_link=story_link,
            proposed_new_content=strings("proposed_new_content"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["canon_basis"] = [entry.to_dict() for entry in self.canon_basis]
        result["relationships"] = [dict(item) for item in self.relationships]
        result["story_link"] = self.story_link.to_dict() if self.story_link else None
        return result


@dataclass(frozen=True)
class CharacterAuthoringKnowledgeContext:
    principal: str = "character_authoring"
    allowed_scopes: frozenset[str] = frozenset(
        {"world_rules", "factions", "lore", "characters", "story_context"}
    )
    allow_restricted_lore: bool = True


@dataclass(frozen=True)
class AuthoringToolExecution:
    observation: Mapping[str, Any]
    audit: ToolAuditEntry
    allowed_source_ids: frozenset[str] = frozenset()
    source_types: Mapping[str, str] = field(default_factory=dict)

    @property
    def allowed_lore_ids(self) -> frozenset[str]:
        """Compatibility alias for generic audit consumers."""
        return self.allowed_source_ids


class CharacterAuthoringToolbox:
    """Fixed-schema, read-only Canon tools for the authoring principal."""

    tool_definitions = (
        ToolDefinition(
            "search_lore",
            "Search authoring-visible Lore summaries; never write Canon.",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            "get_lore",
            "Retrieve one authoring-visible Lore fact by its stable ID.",
            {"type": "object", "properties": {"lore_id": {"type": "string", "pattern": r"^lore(?:_secret)?_[A-Za-z0-9]+$"}}, "required": ["lore_id"], "additionalProperties": False},
        ),
        ToolDefinition(
            "search_factions",
            "Search safe summaries of existing Canon factions.",
            {"type": "object", "properties": {"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"], "additionalProperties": False},
        ),
        ToolDefinition(
            "get_faction",
            "Retrieve one authoring-safe existing faction view.",
            {"type": "object", "properties": {"faction_id": {"type": "string", "pattern": r"^faction_[A-Za-z0-9]+$"}}, "required": ["faction_id"], "additionalProperties": False},
        ),
        ToolDefinition(
            "search_characters",
            "Search summaries of existing Canon characters to avoid obvious duplication.",
            {"type": "object", "properties": {"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"], "additionalProperties": False},
        ),
        ToolDefinition(
            "get_character",
            "Retrieve one authoring-safe existing character view.",
            {"type": "object", "properties": {"character_id": {"type": "string", "pattern": r"^char_[A-Za-z0-9_]+$"}}, "required": ["character_id"], "additionalProperties": False},
        ),
        ToolDefinition(
            "get_world_rules",
            "Retrieve deterministic World Rules and Forbidden Patterns summary.",
            {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        ),
        ToolDefinition(
            "search_story_context",
            "Search safe metadata for established stories, cases and incidents.",
            {"type": "object", "properties": {"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"], "additionalProperties": False},
        ),
        ToolDefinition(
            "get_story_context",
            "Retrieve one established story, case or incident metadata view.",
            {"type": "object", "properties": {"context_id": {"type": "string", "pattern": r"^(story|case|incident)_[-A-Za-z0-9_.]+$"}}, "required": ["context_id"], "additionalProperties": False},
        ),
    )
    allowed_tools = frozenset(item.name for item in tool_definitions)

    def __init__(self, resolver: KnowledgeResolver | None = None, story_repository: StoryRepository | None = None) -> None:
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()

    def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        context: CharacterAuthoringKnowledgeContext | None = None,
        round_number: int = 1,
        character_id: str | None = None,
    ) -> AuthoringToolExecution:
        # ``character_id`` is accepted only for call-site compatibility with
        # the NPC toolbox.  Authoring permissions come from the explicit
        # context and are never inferred from an in-world character identity.
        if character_id is not None and not isinstance(character_id, str):
            raise AgentToolError("authoring character_id must be a string when supplied")
        context = context or CharacterAuthoringKnowledgeContext()
        if tool_name not in self.allowed_tools:
            raise AgentToolError(f"Unknown or forbidden tool: {tool_name}")
        if not isinstance(arguments, Mapping):
            raise AgentToolError("tool arguments must be an object")
        if tool_name == "get_world_rules":
            if arguments:
                raise AgentToolError("get_world_rules accepts no arguments")
            if "world_rules" not in context.allowed_scopes:
                raise AgentToolError("authoring scope does not allow world rules")
            payload = self._world_rules()
            return self._execution(tool_name, arguments, round_number, payload, {"world_rules": "world_rules"})
        if tool_name in {"search_lore", "search_factions", "search_characters", "search_story_context"}:
            query, limit = self._search_args(arguments)
            scope = {
                "search_lore": "lore",
                "search_factions": "factions",
                "search_characters": "characters",
                "search_story_context": "story_context",
            }[tool_name]
            if scope not in context.allowed_scopes:
                raise AgentToolError(f"authoring scope does not allow {scope}")
            handlers = {
                "search_lore": self._search_lore,
                "search_factions": self._search_factions,
                "search_characters": self._search_characters,
                "search_story_context": self._search_story_context,
            }
            payload, types = handlers[tool_name](query, limit, context)
            return self._execution(tool_name, {"query": query, "limit": limit}, round_number, payload, types)
        expected = {
            "get_lore": ("lore_id", "lore"),
            "get_faction": ("faction_id", "factions"),
            "get_character": ("character_id", "characters"),
            "get_story_context": ("context_id", "story_context"),
        }[tool_name]
        key, scope = expected
        if set(arguments) != {key}:
            raise AgentToolError(f"{tool_name} accepts only {key}")
        value = arguments.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", value):
            raise AgentToolError(f"{tool_name} requires a valid stable ID")
        if scope not in context.allowed_scopes:
            raise AgentToolError(f"authoring scope does not allow {scope}")
        payload, types = self._get(tool_name, value, context)
        return self._execution(tool_name, {key: value}, round_number, payload, types)

    @staticmethod
    def _search_args(arguments: Mapping[str, Any]) -> tuple[str, int]:
        if set(arguments) - {"query", "limit"} or "query" not in arguments:
            raise AgentToolError("search tools accept query and optional limit")
        query, limit = arguments.get("query"), arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip():
            raise AgentToolError("search query must be a non-empty string")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise AgentToolError("search limit must be an integer from 1 to 10")
        return query.strip(), limit

    def _execution(self, name: str, arguments: Mapping[str, Any], round_number: int, payload: Mapping[str, Any], types: Mapping[str, str]) -> AuthoringToolExecution:
        ids = frozenset(types)
        observation = dict(payload)
        audit = ToolAuditEntry(round_number, name, arguments, "allowed", allowed_lore_ids=tuple(sorted(ids)))
        return AuthoringToolExecution(observation, audit, ids, MappingProxyType(dict(types)))

    def _get(self, name: str, value: str, context: CharacterAuthoringKnowledgeContext) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        if name == "get_lore":
            record = self.resolver.lore.get(value)
            if record is None:
                raise AgentToolError(f"Unknown lore ID: {value}")
            if not context.allow_restricted_lore and record.get("sensitivity") != "public":
                raise AgentToolError("authoring scope does not allow restricted lore")
            result = self._lore_view(record)
            return {"status": "ok", "result": result}, {value: "lore"}
        if name == "get_faction":
            record = self.resolver.factions.get(value)
            if record is None:
                raise AgentToolError(f"Unknown faction ID: {value}")
            return {"status": "ok", "result": self._faction_view(record)}, {value: "faction"}
        if name == "get_character":
            record = self.resolver.characters.get(value)
            if record is None:
                raise AgentToolError(f"Unknown character ID: {value}")
            return {"status": "ok", "result": self._character_view(record)}, {value: "character"}
        result = self._context_by_id(value)
        if result is None:
            raise AgentToolError(f"Unknown story context ID: {value}")
        return {"status": "ok", "result": result}, {value: result["source_type"]}

    def _search_lore(self, query: str, limit: int, context: CharacterAuthoringKnowledgeContext) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        records = [record for record in self.resolver.lore.values() if context.allow_restricted_lore or record.get("sensitivity") == "public"]
        ranked = self._rank(query, records, lambda item: f"{item.get('title', '')} {item.get('statement', '')}")
        selected = ranked[:limit]
        return {"status": "ok", "results": [self._lore_summary(item) for item in selected]}, {item["id"]: "lore" for item in selected}

    def _search_factions(self, query: str, limit: int, context: CharacterAuthoringKnowledgeContext) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        records = list(self.resolver.factions.values())
        ranked = self._rank(query, records, lambda item: f"{item.get('name', '')} {item.get('short_name', '')} {item.get('type', '')} {item.get('core_function', {}).get('description', '')} {' '.join(item.get('tags', []))}")[:limit]
        return {"status": "ok", "results": [self._faction_summary(item) for item in ranked]}, {item["id"]: "faction" for item in ranked}

    def _search_characters(self, query: str, limit: int, context: CharacterAuthoringKnowledgeContext) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        records = list(self.resolver.characters.values())
        ranked = self._rank(query, records, lambda item: f"{item.get('name', {}).get('display_name', '')} {item.get('basic_profile', {}).get('occupation', '')} {item.get('character_hook', {}).get('first_impression', '')} {' '.join(item.get('tags', []))}")[:limit]
        return {"status": "ok", "results": [self._character_summary(item) for item in ranked]}, {item["id"]: "character" for item in ranked}

    def _search_story_context(self, query: str, limit: int, context: CharacterAuthoringKnowledgeContext) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        records: list[dict[str, Any]] = []
        for story_id, story in self.story_repository.canon.items():
            records.append({"id": story_id, "source_type": "story", "name": story.get("title", story_id), "summary": story.get("premise", ""), "faction_ids": story.get("involved_faction_ids", [])})
        for case_id, case in self.resolver.cases.items():
            records.append({"id": case_id, "source_type": "case", "name": case.get("name", case_id), "summary": "Established case context", "story_refs": case.get("story_refs", []), "related_incident_ids": case.get("related_incident_ids", [])})
        for incident_id, incident in self.resolver.incidents.items():
            records.append({"id": incident_id, "source_type": "incident", "name": incident.get("name", incident_id), "summary": "Established incident context", "story_refs": incident.get("story_refs", []), "related_case_ids": incident.get("related_case_ids", [])})
        ranked = self._rank(query, records, lambda item: f"{item.get('name', '')} {item.get('summary', '')} {' '.join(item.get('faction_ids', []))}")[:limit]
        return {"status": "ok", "results": ranked}, {item["id"]: item["source_type"] for item in ranked}

    def _context_by_id(self, value: str) -> dict[str, Any] | None:
        if value.startswith("story_") and value in self.story_repository.canon:
            story = self.story_repository.canon[value]
            return {"id": value, "source_id": value, "source_type": "story", "name": story.get("title", value), "summary": story.get("premise", ""), "faction_ids": story.get("involved_faction_ids", [])}
        if value.startswith("case_") and value in self.resolver.cases:
            record = self.resolver.cases[value]
            return {"id": value, "source_id": value, "source_type": "case", "name": record.get("name", value), "summary": "Established case context", "story_refs": record.get("story_refs", []), "related_incident_ids": record.get("related_incident_ids", [])}
        if value.startswith("incident_") and value in self.resolver.incidents:
            record = self.resolver.incidents[value]
            return {"id": value, "source_id": value, "source_type": "incident", "name": record.get("name", value), "summary": "Established incident context", "story_refs": record.get("story_refs", []), "related_case_ids": record.get("related_case_ids", [])}
        return None

    @staticmethod
    def _rank(query: str, records: Sequence[Mapping[str, Any]], text_fn: Any) -> list[dict[str, Any]]:
        query_norm = CharacterAuthoringToolbox._normalize(query)
        scored = []
        for record in records:
            text = CharacterAuthoringToolbox._normalize(str(text_fn(record)))
            score = (20 if query_norm and query_norm in text else 0) + sum(1 for unit in CharacterAuthoringToolbox._units(query_norm) & CharacterAuthoringToolbox._units(text))
            if score > 0:
                scored.append((score, str(record.get("id", "")), dict(record)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored]

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(character.lower() for character in value if character.isalnum())

    @staticmethod
    def _units(value: str) -> set[str]:
        chinese = [char for char in value if "\u4e00" <= char <= "\u9fff"]
        units = set(re.findall(r"[a-z0-9]+", value))
        units.update(chinese)
        units.update("".join(chinese[index : index + 2]) for index in range(len(chinese) - 1))
        return units

    @staticmethod
    def _lore_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        return {"id": record.get("id"), "source_id": record.get("id"), "source_type": "lore", "title": record.get("title", ""), "summary": record.get("statement", ""), "category": record.get("category")}

    @staticmethod
    def _lore_view(record: Mapping[str, Any]) -> dict[str, Any]:
        return {"id": record.get("id"), "lore_id": record.get("id"), "source_id": record.get("id"), "source_type": "lore", "title": record.get("title", ""), "statement": record.get("statement", ""), "category": record.get("category"), "sensitivity": record.get("sensitivity", "public")}

    @classmethod
    def _faction_summary(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        function = record.get("core_function", {})
        return {"id": record.get("id"), "source_id": record.get("id"), "source_type": "faction", "name": record.get("name", ""), "type": record.get("type", ""), "summary": function.get("description", "") if isinstance(function, Mapping) else "", "tags": record.get("tags", [])}

    @classmethod
    def _faction_view(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        result = cls._faction_summary(record)
        result.update({"status": record.get("status"), "public_identity": record.get("public_identity", {}), "core_function": record.get("core_function", {}), "canon_constraints": record.get("canon_constraints", []), "internal_structure": record.get("internal_structure", {})})
        return result

    @staticmethod
    def _character_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        name = record.get("name", {})
        basic = record.get("basic_profile", {})
        identity = record.get("identity", {})
        return {"id": record.get("id"), "source_id": record.get("id"), "source_type": "character", "name": name.get("display_name", record.get("id", "")), "age": basic.get("age"), "occupation": basic.get("occupation", ""), "faction_id": identity.get("faction_id"), "tags": record.get("tags", [])}

    @classmethod
    def _character_view(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        result = cls._character_summary(record)
        result.update({"character_hook": record.get("character_hook", {}), "personality": record.get("personality", {}), "ability": record.get("ability", {}), "narrative": record.get("narrative", {})})
        return result

    @staticmethod
    def _world_rules() -> dict[str, Any]:
        path = default_data_dir() / "canon" / "world_bible.md"
        text = path.read_text(encoding="utf-8")
        rules = re.findall(r"- \*\*(RULE-\d+)：\*\*\s*(.+)", text)
        forbidden_section = text.split("## 13. Forbidden Patterns", 1)
        forbidden: list[str] = []
        if len(forbidden_section) == 2:
            forbidden_body = forbidden_section[1].split("\n## ", 1)[0]
            forbidden = [line[2:].strip() for line in forbidden_body.splitlines() if line.startswith("- ")]
        return {"status": "ok", "result": {"source_id": "world_rules", "source_type": "world_rules", "rules": [{"id": item[0], "statement": item[1].strip()} for item in rules], "forbidden_patterns": forbidden, "scope_summary": "World rules and forbidden patterns are read-only Canon constraints."}}

    @staticmethod
    def world_rules_view() -> dict[str, Any]:
        """Return the same read-only rules view exposed to authoring tools."""
        return CharacterAuthoringToolbox._world_rules()


CHARACTER_SYSTEM_CONTRACT = """You are a read-only game character authoring agent. Generate a candidate CharacterDraft for a planner, not an in-world NPC and not approved Canon. Use only facts returned by the listed authoring tools. Existing faction, lore, character, story, case, incident and world-rule assertions require canon_basis source IDs from successful tool observations. New personal details must be placed in new_design_elements or proposed_new_content and must never be presented as existing Canon. Never create organizations, IDs, files or Canon records. Respect hard constraints; if a requirement cannot be established, use open_questions and constraint_notes. Keep combat_role high-level and do not invent numeric balance values.""" + "\n\n" + character_draft_prompt_contract()


@dataclass(frozen=True)
class CharacterAuthoringView:
    principal: str
    purpose: str
    allowed_scopes: tuple[str, ...]


@dataclass(frozen=True)
class CharacterGenerationRuntimeView:
    request_id: str
    brief: str
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]
    forbidden_elements: tuple[str, ...]
    desired_connections: tuple[str, ...]


@dataclass(frozen=True)
class CharacterGenerationAudit:
    request_id: str
    tool_rounds: int
    tool_calls: tuple[ToolAuditEntry, ...]
    source_ids: tuple[str, ...]
    model_invocations: tuple[ModelInvocationAudit, ...] = ()


@dataclass(frozen=True)
class CharacterGenerationResult:
    draft: CharacterDraft
    sources: tuple[str, ...]
    audit: CharacterGenerationAudit


class CharacterGenerationAgent:
    """Sibling consumer to NpcConversationAgent for one-shot draft generation."""

    def __init__(self, model: AgentModel, *, resolver: KnowledgeResolver | None = None, story_repository: StoryRepository | None = None, max_tool_rounds: int = 6, authoring_context: CharacterAuthoringKnowledgeContext | None = None) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()
        self.tools = CharacterAuthoringToolbox(self.resolver, self.story_repository)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.authoring_context = authoring_context or CharacterAuthoringKnowledgeContext()

    def generate(self, request: CharacterDesignRequest | str) -> CharacterGenerationResult:
        if isinstance(request, str):
            request = CharacterDesignRequest(request)
        if not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be CharacterDesignRequest or string")
        authoring = CharacterAuthoringView("character_authoring", "create a reviewable CharacterDraft", tuple(sorted(self.authoring_context.allowed_scopes)))
        runtime = CharacterGenerationRuntimeView(request.request_id, request.brief, request.hard_constraints, request.soft_preferences, request.forbidden_elements, request.desired_connections)
        messages: list[ConversationMessage] = [ConversationMessage("user", json.dumps(request.to_dict(), ensure_ascii=False, separators=(",", ":")))]
        source_ids: set[str] = set()
        source_types: dict[str, str] = {}
        audits: list[ToolAuditEntry] = []
        invocations: list[ModelInvocationAudit] = []
        try:
            for round_number in range(1, self.max_tool_rounds + 2):
                evidence = tuple(
                    GroundingEvidence(f"canon:{source_id}", GroundingEvidenceType.TOOL_LORE, source_id, source_id if source_type == "lore" else None)
                    for source_id, source_type in sorted(source_types.items())
                )
                prompt = AgentPrompt(
                    CHARACTER_SYSTEM_CONTRACT,
                    authoring,
                    runtime,
                    tuple(messages),
                    self.tools.tool_definitions,
                    f"character_generation:{request.request_id}",
                    round_number,
                    evidence,
                    response_format="character_draft",
                )
                turn = self.model.generate(prompt)
                if turn.invocation is not None:
                    invocations.append(turn.invocation)
                if turn.tool_calls:
                    if round_number > self.max_tool_rounds:
                        raise AgentExecutionError(f"Tool loop exceeded {self.max_tool_rounds} rounds")
                    messages.append(ConversationMessage("assistant", {"tool_calls": [{"id": call.id, "name": call.name, "arguments": dict(call.arguments)} for call in turn.tool_calls]}))
                    for call in turn.tool_calls:
                        try:
                            execution = self.tools.execute(tool_name=call.name, arguments=call.arguments, context=self.authoring_context, round_number=round_number)
                        except AgentToolError:
                            audits.append(ToolAuditEntry(round_number, call.name, call.arguments, "rejected", resolver_reason_code="tool_not_allowed" if call.name not in self.tools.allowed_tools else "invalid_tool_arguments"))
                            raise
                        audits.append(execution.audit)
                        source_ids.update(execution.allowed_source_ids)
                        source_types.update(execution.source_types)
                        messages.append(ConversationMessage("tool", {"tool_call_id": call.id, **dict(execution.observation)}))
                    continue
                payload = turn.structured_output
                if payload is None:
                    if not isinstance(turn.text, str):
                        raise AgentExecutionError("Model returned no CharacterDraft")
                    try:
                        payload = json.loads(turn.text)
                    except json.JSONDecodeError:
                        raise ModelMalformedResponseError("CharacterDraft response is not valid JSON") from None
                draft = CharacterDraft.from_mapping(payload)
                self._validate_draft(draft, request, source_ids, source_types)
                audit = CharacterGenerationAudit(request.request_id, len(audits), tuple(audits), tuple(sorted(source_ids)), tuple(invocations))
                return CharacterGenerationResult(draft, tuple(sorted(source_ids)), audit)
        except Exception as error:
            # CharacterGenerationAudit only exists on success, so the
            # propagating exception is the failure-path audit carrier. Keep the
            # invocation trail (including the adapter-attached failure audit)
            # observable on any abort: a failed call stays distinguishable
            # from a call that never happened. Metadata only, never raw output.
            if isinstance(error, ModelError) and error.audit is not None:
                invocations.append(error.audit)
            error.model_invocations = tuple(invocations)
            raise
        raise AgentExecutionError("Character generation ended without a draft")

    @staticmethod
    def _validate_draft(draft: CharacterDraft, request: CharacterDesignRequest, source_ids: set[str], source_types: Mapping[str, str]) -> None:
        age_bounds = CharacterGenerationAgent._age_bounds(request)
        if draft.age is not None and age_bounds is not None and not age_bounds[0] <= draft.age <= age_bounds[1]:
            raise AgentExecutionError(f"Draft age {draft.age} violates hard constraint {age_bounds[0]}-{age_bounds[1]}")
        if draft.faction_id is not None:
            if draft.faction_id not in source_ids or source_types.get(draft.faction_id) != "faction":
                raise AgentExecutionError(f"Draft faction_id is not grounded: {draft.faction_id}")
        for entry in draft.canon_basis:
            if entry.source_id not in source_ids:
                raise AgentExecutionError(f"Draft cites Canon source not returned this turn: {entry.source_id}")
        if draft.story_link is not None and (
            draft.story_link.status == "canon_backed"
            and (draft.story_link.target_id not in source_ids or source_types.get(draft.story_link.target_id) not in {"story", "case", "incident"})
        ):
            raise AgentExecutionError(f"Draft story_link is not grounded: {draft.story_link.target_id}")
        for relationship in draft.relationships:
            target_id = relationship.get("target_id")
            if target_id is not None and target_id.startswith(("char_", "faction_")) and target_id not in source_ids:
                raise AgentExecutionError(f"Draft relationship is not grounded: {target_id}")
        brief_forbidden = tuple(
            marker
            for marker in ("秘密政府组织", "秘密行政机构", "秘密监察处")
            if marker in request.brief
        )
        forbidden_terms = tuple(dict.fromkeys((*request.forbidden_elements, *brief_forbidden)))
        forbidden = [item for item in forbidden_terms if item and item in " ".join((*draft.new_design_elements, *draft.proposed_new_content))]
        if forbidden:
            raise AgentExecutionError(f"Draft proposes forbidden content: {', '.join(forbidden)}")

    @staticmethod
    def _age_bounds(request: CharacterDesignRequest) -> tuple[int, int] | None:
        text = " ".join((*request.hard_constraints, request.brief))
        match = re.search(r"(\d+)\s*[～至到\-]\s*(\d+)\s*岁?", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r"(\d+)\s*岁左右", text)
        if match:
            value = int(match.group(1))
            return value - 2, value + 2
        return None


class DeterministicCharacterGenerationModel:
    """Offline model used by tests, evals and the demo; no network required."""

    def __init__(self) -> None:
        self.prompts: list[AgentPrompt] = []

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        self.prompts.append(prompt)
        if prompt.response_format != "character_draft":
            raise RuntimeError("DeterministicCharacterGenerationModel requires character_draft prompts")
        called = {
            message.content.get("tool_calls", [{}])[0].get("name")
            for message in prompt.messages
            if message.role == "assistant" and isinstance(message.content, Mapping)
        }
        brief = prompt.runtime.brief
        if "get_world_rules" not in called:
            return ModelTurn(tool_calls=(ToolCall("world", "get_world_rules", {}),))
        if "search_factions" not in called:
            return ModelTurn(tool_calls=(ToolCall("faction", "search_factions", {"query": brief, "limit": 5}),))
        if "search_lore" not in called:
            return ModelTurn(tool_calls=(ToolCall("lore", "search_lore", {"query": brief, "limit": 5}),))
        if ("事件" in brief or "事故" in brief or "南站" in brief or "南栈" in brief) and "search_story_context" not in called:
            return ModelTurn(tool_calls=(ToolCall("story", "search_story_context", {"query": brief, "limit": 5}),))
        selected_faction = None
        selected_story = None
        lore_sources: list[str] = []
        faction_candidates: list[tuple[str, str]] = []
        for message in prompt.messages:
            if message.role != "tool" or not isinstance(message.content, Mapping):
                continue
            for key in ("result",):
                item = message.content.get(key)
                if isinstance(item, Mapping):
                    if item.get("source_type") == "faction" and item.get("id"):
                        faction_candidates.append((str(item.get("id")), str(item.get("name", "")) + str(item.get("summary", ""))))
                    if item.get("source_type") in {"story", "case", "incident"} and selected_story is None:
                        selected_story = item.get("id")
                    if item.get("source_type") == "lore" and item.get("id"):
                        lore_sources.append(item["id"])
            for item in message.content.get("results", []):
                if isinstance(item, Mapping):
                    if item.get("source_type") == "faction" and item.get("id"):
                        faction_candidates.append((str(item.get("id")), str(item.get("name", "")) + str(item.get("summary", ""))))
                    if item.get("source_type") in {"story", "case", "incident"} and selected_story is None:
                        selected_story = item.get("id")
                    if item.get("source_type") == "lore" and item.get("id"):
                        lore_sources.append(item["id"])
        for marker, preferred in (("大学", "faction_002"), ("南栈", "faction_006"), ("公共安全", "faction_005")):
            if marker in brief and any(candidate[0] == preferred for candidate in faction_candidates):
                selected_faction = preferred
                break
        if selected_faction is None and faction_candidates:
            selected_faction = faction_candidates[0][0]
        age = 23 if "23" in brief else 22
        if "20" in brief and "25" in brief:
            age = 23
        basis = [{"source_id": "world_rules", "supports": ["world_rules"]}]
        if selected_faction:
            basis.append({"source_id": selected_faction, "supports": ["faction_id", "occupation"]})
        for lore_id in dict.fromkeys(lore_sources[:2]):
            basis.append({"source_id": lore_id, "supports": ["world_context"]})
        if selected_story:
            basis.append({"source_id": selected_story, "supports": ["story_hook"]})
        payload = {
            "draft_id": f"draft_{prompt.runtime.request_id}",
            "status": "draft",
            "name": "顾澄",
            "canonical_character_id": None,
            "age": age,
            "age_range": "20-25",
            "gender": "女性",
            "faction_id": selected_faction,
            "occupation": "临洲大学学生助理",
            "social_role": "校园活动与社区安全志愿协调者",
            "combat_role": "support",
            "design_pitch": "一名把现场秩序与他人安全放在首位的年轻辅助型角色。",
            "personality": ["冷静", "克制", "先观察后行动"],
            "background": "她在校园与社区活动中逐渐形成了谨慎处理复杂关系的习惯。",
            "story_hook": "在既有事件的后续协调中提供非核心的现场协助，并面对个人选择与公共责任的拉扯。",
            "relationships": [],
            "ability_concept": "能够在自己明确标记过的安全范围内短暂稳定注意与行动节奏；作用有限，不能替代训练或专业处置。",
            "knowledge_scope": "仅凭学生与志愿协作者身份接触公开信息和被明确交付的现场事项。",
            "canon_basis": basis,
            "new_design_elements": ["姓名、性格、个人习惯与高层能力表现均为新角色设计。"],
            "open_questions": ["是否将她与后续校园活动支线建立更长期的个人关系？"],
            "constraint_notes": ["与既有事件保持间接联系，不承担事件核心负责人身份。"],
            "story_link": {"target_id": selected_story, "relation": "indirect_connection", "status": "canon_backed"} if selected_story else None,
            "proposed_new_content": [],
        }
        return ModelTurn(text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")), structured_output=payload)


# Friendly aliases for callers that use the agent-oriented vocabulary.
CharacterGenerationToolbox = CharacterAuthoringToolbox
CharacterGenerationContext = CharacterAuthoringKnowledgeContext
CharacterDesignBrief = CharacterDesignRequest
CharacterGenerationResponse = CharacterGenerationResult


__all__ = [
    "CanonBasisEntry",
    "CharacterAuthoringKnowledgeContext",
    "CharacterAuthoringToolbox",
    "CharacterGenerationToolbox",
    "CharacterGenerationContext",
    "CharacterDesignBrief",
    "CharacterDesignRequest",
    "CharacterDraft",
    "CharacterGenerationAgent",
    "CharacterGenerationAudit",
    "CharacterGenerationResult",
    "CharacterGenerationResponse",
    "CharacterGenerationRuntimeView",
    "CharacterAuthoringView",
    "DeterministicCharacterGenerationModel",
    "StoryLink",
]
