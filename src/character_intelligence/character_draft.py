"""Shared, provider-neutral CharacterDraft domain contract.

This module owns the proposal value, its strict JSON schema, and the parser
needed by both legacy generation and future output pipelines. It deliberately
does not import Agent, Provider, CanonChecker, Repair, Web, or persistence code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from combat_semantics import (
    CANONICAL_COMBAT_ROLES,
    CombatRoleProfile,
    resolve_legacy_combat_role_profile,
)

from .draft_errors import CharacterDraftMappingError, CharacterDraftMappingReason

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
            "draft_id",
            "status",
            "name",
            "canonical_character_id",
            "age",
            "age_range",
            "gender",
            "faction_id",
            "occupation",
            "social_role",
            "combat_role_profile",
            "design_pitch",
            "personality",
            "background",
            "story_hook",
            "relationships",
            "ability_concept",
            "knowledge_scope",
            "canon_basis",
            "new_design_elements",
            "open_questions",
            "constraint_notes",
            "story_link",
            "proposed_new_content",
        ],
    }
)

# These fields are required by the domain parser even though the provider
# schema declares every property required for strict transport. The Agent's
# bounded recovery path also consumes this same vocabulary.
CHARACTER_DRAFT_CORE_FIELDS = frozenset(
    {"draft_id", "status", "name", "canon_basis", "new_design_elements", "open_questions"}
)

# The structured provider schema stays strict. This input vocabulary additionally
# admits the one legacy alias already handled by CharacterDraft.from_mapping.
_CHARACTER_DRAFT_LEGACY_INPUT_FIELDS = frozenset({"combat_role"})
CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS = frozenset(
    CHARACTER_DRAFT_JSON_SCHEMA["properties"]
) | _CHARACTER_DRAFT_LEGACY_INPUT_FIELDS

_SAFE_UNKNOWN_FIELD_LABELS = frozenset(
    {"character_draft", "draft", "result", "data", "response", "payload"}
)


@dataclass(frozen=True)
class CanonBasisEntry:
    """One proposed source-to-field support entry carried by a draft."""

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
    """A bounded reference from a draft to a story-context entity."""

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
    """Strict, approval-independent candidate character representation.

    Age and age range are nullable design facts, not appearance estimators,
    legal-status classifiers, or required proxies for social position. Age
    presentation and life-stage nuance remain in the narrative fields until
    the project demonstrates a need for a separate structured representation.
    """

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
    combat_role_profile: CombatRoleProfile | None = None
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
    # Accepted only at the deserialization boundary; never part of the
    # canonical provider schema or serialized Draft representation.
    _LEGACY_INPUT_FIELDS = _CHARACTER_DRAFT_LEGACY_INPUT_FIELDS
    _ACCEPTED_INPUT_FIELDS = CHARACTER_DRAFT_ACCEPTED_INPUT_FIELDS

    def __post_init__(self) -> None:
        profile = self.combat_role_profile
        if profile is None:
            profile = CombatRoleProfile()
        elif not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")
        object.__setattr__(self, "combat_role_profile", profile)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        """Parse the existing strict mapping contract without Agent state."""

        def mapping_error(
            reason: CharacterDraftMappingReason,
            detail: str,
            *,
            field_path: str | None = None,
        ) -> CharacterDraftMappingError:
            return CharacterDraftMappingError(reason, detail, field_path=field_path)

        if not isinstance(payload, Mapping):
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_MAPPING,
                "CharacterDraft must be a JSON object",
                field_path="$",
            )
        unknown = set(payload) - cls._ACCEPTED_INPUT_FIELDS
        if unknown:
            safe_unknown = sorted(
                field
                for field in unknown
                if isinstance(field, str) and field in _SAFE_UNKNOWN_FIELD_LABELS
            )
            raise mapping_error(
                CharacterDraftMappingReason.UNKNOWN_FIELD,
                f"CharacterDraft has unknown field(s): {safe_unknown}",
            )
        required = set(CHARACTER_DRAFT_CORE_FIELDS)
        missing = required - set(payload)
        if missing:
            raise mapping_error(
                CharacterDraftMappingReason.MISSING_REQUIRED_FIELD,
                f"CharacterDraft is missing field(s): {sorted(missing)}",
                field_path=sorted(missing)[0],
            )

        def string(name: str, *, optional: bool = False) -> str | None:
            value = payload.get(name)
            if value is None and optional:
                return None
            if not isinstance(value, str):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                    f"CharacterDraft.{name} must be a non-empty string",
                    field_path=name,
                )
            if not value.strip():
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                    f"CharacterDraft.{name} must be a non-empty string",
                    field_path=name,
                )
            return value.strip()

        draft_id = string("draft_id")
        status = string("status")
        name = string("name")
        assert draft_id is not None and status is not None and name is not None
        if status != "draft":
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                "CharacterDraft.status must be 'draft'",
                field_path="status",
            )
        if not re.fullmatch(r"draft_[A-Za-z0-9][A-Za-z0-9_.-]*", draft_id):
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                "draft_id must use the draft_ namespace",
                field_path="draft_id",
            )

        age = payload.get("age")
        if age is not None and (isinstance(age, bool) or not isinstance(age, int)):
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                "CharacterDraft.age must be a non-negative integer or null",
                field_path="age",
            )
        if age is not None and age < 0:
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                "CharacterDraft.age must be a non-negative integer or null",
                field_path="age",
            )
        age_range = string("age_range", optional=True) if "age_range" in payload else None
        gender = string("gender", optional=True) if "gender" in payload else None
        faction_id = string("faction_id", optional=True) if "faction_id" in payload else None
        canonical_id = payload.get("canonical_character_id")
        if canonical_id is not None:
            if not isinstance(canonical_id, str):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                    "canonical_character_id must be a strict string ID or null",
                    field_path="canonical_character_id",
                )
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", canonical_id):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                    "canonical_character_id must be a strict string ID or null",
                    field_path="canonical_character_id",
                )
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                "v0.1 drafts must not claim a canonical character ID",
                field_path="canonical_character_id",
            )

        def strings(name: str) -> tuple[str, ...]:
            value = payload.get(name, [])
            if isinstance(value, (str, bytes)) or not isinstance(value, list):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                    f"CharacterDraft.{name} must be an array of strings",
                    field_path=name,
                )
            if not all(isinstance(item, str) for item in value):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                    f"CharacterDraft.{name} contains an invalid string",
                    field_path=name,
                )
            if not all(item.strip() for item in value):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_VALUE,
                    f"CharacterDraft.{name} contains an invalid string",
                    field_path=name,
                )
            return tuple(item.strip() for item in value)

        def text(name: str) -> str:
            value = payload.get(name, "")
            if not isinstance(value, str):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_FIELD_TYPE,
                    f"CharacterDraft.{name} must be a string",
                    field_path=name,
                )
            return value.strip()

        canon_raw = payload.get("canon_basis")
        if not isinstance(canon_raw, list):
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_CANON_BASIS,
                "CharacterDraft.canon_basis must be an array",
                field_path="canon_basis",
            )
        basis: list[CanonBasisEntry] = []
        seen_sources: set[str] = set()
        for item in canon_raw:
            if isinstance(item, str):
                item = {"source_id": item, "supports": []}
            if not isinstance(item, Mapping):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_CANON_BASIS,
                    "canon_basis entries must be objects",
                    field_path="canon_basis",
                )
            if set(item) - {"source_id", "supports", "source_type"}:
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_CANON_BASIS,
                    "canon_basis entry has unknown fields",
                    field_path="canon_basis",
                )
            source_id = item.get("source_id")
            supports = item.get("supports", [])
            source_type = item.get("source_type")
            if not isinstance(source_id, str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.:-]*", source_id
            ):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_CANON_BASIS,
                    "canon_basis source_id must be a strict string ID",
                    field_path="canon_basis.source_id",
                )
            if isinstance(supports, (str, bytes)) or not isinstance(supports, list) or not all(
                isinstance(value, str) and value.strip() for value in supports
            ):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_CANON_BASIS,
                    "canon_basis supports must be an array of strings",
                    field_path="canon_basis.supports",
                )
            if source_type is not None and (not isinstance(source_type, str) or not source_type.strip()):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_CANON_BASIS,
                    "canon_basis source_type must be a string",
                    field_path="canon_basis.source_type",
                )
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            basis.append(CanonBasisEntry(source_id, tuple(s.strip() for s in supports), source_type))

        relationships_raw = payload.get("relationships", [])
        if not isinstance(relationships_raw, list):
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_RELATIONSHIP,
                "CharacterDraft.relationships must be an array",
                field_path="relationships",
            )
        relationships: list[Mapping[str, Any]] = []
        for item in relationships_raw:
            if not isinstance(item, Mapping):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_RELATIONSHIP,
                    "relationship entries must be objects",
                    field_path="relationships",
                )
            if set(item) - {"target_id", "description", "status", "type"}:
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_RELATIONSHIP,
                    "relationship entry has unknown fields",
                    field_path="relationships",
                )
            target_id = item.get("target_id")
            if target_id is not None and (
                not isinstance(target_id, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", target_id)
            ):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_RELATIONSHIP,
                    "relationship target_id must be a strict string ID",
                    field_path="relationships.target_id",
                )
            clean = {key: value for key, value in item.items()}
            relationships.append(MappingProxyType(clean))

        story_raw = payload.get("story_link")
        story_link = None
        if story_raw is not None:
            if not isinstance(story_raw, Mapping) or set(story_raw) - {"target_id", "relation", "status"}:
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_NESTED_STRUCTURE,
                    "story_link has an invalid shape",
                    field_path="story_link",
                )
            target = story_raw.get("target_id")
            if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", target):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_NESTED_STRUCTURE,
                    "story_link.target_id must be a strict string ID",
                    field_path="story_link.target_id",
                )
            relation = story_raw.get("relation", "related_context")
            link_status = story_raw.get("status", "canon_backed")
            if not isinstance(relation, str) or not relation.strip() or not isinstance(link_status, str):
                raise mapping_error(
                    CharacterDraftMappingReason.INVALID_NESTED_STRUCTURE,
                    "story_link fields are malformed",
                    field_path="story_link",
                )
            story_link = StoryLink(target, relation.strip(), link_status.strip())

        legacy_raw = payload.get("combat_role")
        profile_raw = payload.get("combat_role_profile")
        try:
            profile = resolve_legacy_combat_role_profile(profile_raw, legacy_raw)
        except (TypeError, ValueError):
            # The shared resolver may quote an untrusted role value in its
            # exception; retain only this bounded domain-level diagnosis.
            profile = None
        if profile is None:
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_COMBAT_ROLE,
                "CharacterDraft.combat_role compatibility input is invalid",
                field_path="combat_role_profile",
            )
        draft: CharacterDraft | None
        try:
            draft = cls(
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
                combat_role_profile=profile,
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
        except CharacterDraftMappingError:
            raise
        except (TypeError, ValueError):
            # Do not retain arbitrary constructor exception text or chaining.
            draft = None
        if draft is None:
            raise mapping_error(
                CharacterDraftMappingReason.INVALID_DOMAIN_CONSTRUCTION,
                "CharacterDraft could not be materialized",
            )
        return draft

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        # dataclasses.asdict deep-copies fields and cannot copy relationship
        # MappingProxyType values; explicitly build the current JSON contract.
        # INVARIANT: __post_init__ replaces None with an unspecified profile.
        profile = self.combat_role_profile
        assert profile is not None
        return {
            "draft_id": self.draft_id,
            "status": self.status,
            "name": self.name,
            "canonical_character_id": self.canonical_character_id,
            "age": self.age,
            "age_range": self.age_range,
            "gender": self.gender,
            "faction_id": self.faction_id,
            "occupation": self.occupation,
            "social_role": self.social_role,
            "combat_role_profile": profile.to_dict(),
            "design_pitch": self.design_pitch,
            "personality": list(self.personality),
            "background": self.background,
            "story_hook": self.story_hook,
            "relationships": [
                {key: _json_safe_relationship_value(value) for key, value in relationship.items()}
                for relationship in self.relationships
            ],
            "ability_concept": self.ability_concept,
            "knowledge_scope": self.knowledge_scope,
            "canon_basis": [entry.to_dict() for entry in self.canon_basis],
            "new_design_elements": list(self.new_design_elements),
            "open_questions": list(self.open_questions),
            "constraint_notes": list(self.constraint_notes),
            "story_link": self.story_link.to_dict() if self.story_link else None,
            "proposed_new_content": list(self.proposed_new_content),
        }


def _json_safe_relationship_value(value: Any) -> Any:
    """Serialize relationship values without mutating the in-memory mapping."""

    if isinstance(value, Mapping):
        return {str(key): _json_safe_relationship_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe_relationship_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported relationship value for JSON serialization: {type(value).__name__}")
