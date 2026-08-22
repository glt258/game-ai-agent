"""Canon-aware character authoring agent.

This module deliberately keeps authoring separate from the in-world NPC
conversation consumer.  The model receives a small authoring view and can
only obtain Canon through the read-only tools below; it never receives a
resolver, repository, path or writable object.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from character_intelligence.planner import CharacterDesignPlan
from combat_semantics import CombatRoleProfile, normalize_legacy_combat_role
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
    CharacterDraftRecoveryAudit,
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
    CHARACTER_DRAFT_CORE_FIELDS,
    CHARACTER_DRAFT_JSON_SCHEMA,
    CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL,
    character_draft_prompt_contract,
    has_terminal_authoring_finalize_signal,
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
    combat_role_profile: CombatRoleProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.brief, str) or not self.brief.strip():
            raise ValueError("brief must be a non-empty string")
        if not isinstance(self.request_id, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.-]*", self.request_id
        ):
            raise ValueError("request_id must be a safe identifier")
        if self.combat_role_profile is not None and not isinstance(
            self.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError("combat_role_profile must be a CombatRoleProfile or None")
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
            "combat_role_profile": (
                self.combat_role_profile.to_dict()
                if self.combat_role_profile is not None
                else None
            ),
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
    """Strict, approval-independent candidate character representation.

    ``age`` and ``age_range`` are nullable design facts.  They are not an
    appearance estimator, a legal-status classifier, or a required proxy for
    social position.  Age presentation and life-stage nuance remain authored
    in the existing narrative fields until the project has a demonstrated
    need for a separate structured representation.
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
    # ``combat_role_profile`` is authoritative.  ``combat_role`` is retained
    # as a frozen, derived adapter for older callers and payloads.
    combat_role: str | None = None
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
    _LEGACY_INPUT_FIELDS = frozenset({"combat_role"})
    _ACCEPTED_INPUT_FIELDS = _KNOWN_FIELDS | _LEGACY_INPUT_FIELDS

    _LEGACY_NON_ROLE_VALUES = frozenset({"burst", "sustain", "flex", "hybrid"})

    def __post_init__(self) -> None:
        legacy = self.combat_role
        profile = self.combat_role_profile
        if profile is None:
            if legacy in (None, "", "none", "unspecified"):
                profile = CombatRoleProfile()
            elif legacy in self._LEGACY_NON_ROLE_VALUES:
                # These labels remain readable only for old scalar payloads;
                # they never enter the canonical role profile.
                profile = CombatRoleProfile()
            else:
                try:
                    normalized = normalize_legacy_combat_role(legacy)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"combat_role is invalid: {legacy!r}") from error
                if normalized is None:
                    raise ValueError(f"combat_role is not a supported role: {legacy!r}")
                profile = CombatRoleProfile(primary_role=normalized)
        elif not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")

        if legacy not in (None, "", "none", "unspecified"):
            if legacy in self._LEGACY_NON_ROLE_VALUES:
                if not profile.is_unspecified:
                    raise ValueError(
                        "legacy combat_role is non-canonical and cannot contradict "
                        "combat_role_profile"
                    )
            else:
                try:
                    normalized = normalize_legacy_combat_role(legacy)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"combat_role is invalid: {legacy!r}") from error
                if normalized is None:
                    raise ValueError(f"combat_role is not a supported role: {legacy!r}")
                if profile.primary_role != normalized:
                    raise ValueError(
                        "combat_role is a derived compatibility projection and "
                        "must match combat_role_profile.primary_role"
                    )

        # Draft compatibility uses canonical spellings.  Intent keeps its
        # historical ``dps`` projection separately at its own boundary.
        derived_legacy = profile.primary_role or (
            legacy if legacy in self._LEGACY_NON_ROLE_VALUES else "none"
        )
        object.__setattr__(self, "combat_role_profile", profile)
        object.__setattr__(self, "combat_role", derived_legacy)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        if not isinstance(payload, Mapping):
            raise ModelMalformedResponseError("CharacterDraft must be a JSON object")
        unknown = set(payload) - cls._ACCEPTED_INPUT_FIELDS
        if unknown:
            raise ModelMalformedResponseError(
                f"CharacterDraft has unknown field(s): {sorted(unknown)}"
            )
        required = set(CHARACTER_DRAFT_CORE_FIELDS)
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

        legacy_raw = payload.get("combat_role")
        if legacy_raw is not None and not isinstance(legacy_raw, str):
            raise ModelMalformedResponseError("CharacterDraft.combat_role must be a string")
        combat_role = legacy_raw.strip() if isinstance(legacy_raw, str) else None
        profile_raw = payload.get("combat_role_profile")
        profile = None
        if profile_raw is not None:
            try:
                profile = CombatRoleProfile.from_mapping(profile_raw)
            except (TypeError, ValueError) as error:
                raise ModelMalformedResponseError(
                    f"CharacterDraft.combat_role_profile is invalid: {error}"
                ) from error
        try:
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
        except (TypeError, ValueError) as error:
            raise ModelMalformedResponseError(str(error)) from error

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterDraft":
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        # Do not use dataclasses.asdict here: it deep-copies every field and
        # cannot copy the MappingProxyType used to make relationships
        # immutable.  Build the current JSON contract explicitly instead.
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
            "combat_role_profile": self.combat_role_profile.to_dict(),
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


def _normalize_character_draft_payload(
    payload: Any,
) -> tuple[Any, tuple[str, ...]]:
    """Apply only the semantically safe CharacterDraft field default.

    ``open_questions`` is an explicit declaration of unresolved design work.
    When a provider omits only that declaration, the completed draft semantics
    are equivalent to an empty list. Canon-bearing and design-content fields
    intentionally remain untouched and continue to fail closed when absent.
    """

    if isinstance(payload, Mapping) and "open_questions" not in payload:
        normalized = dict(payload)
        normalized["open_questions"] = []
        return normalized, ("open_questions",)
    return payload, ()


_AGE_UNSPECIFIED_MARKERS = (
    "不要给出具体年龄",
    "不要提供具体年龄",
    "不明确具体年龄",
    "年龄不公开",
    "年龄保持不明确",
    "年龄保持未知",
    "不指定年龄",
    "不确定年龄",
    "年龄模糊",
    "年龄未知",
    "具体年龄未知",
    "当前年龄未知",
    "年龄信息未知",
    "年龄不明确",
    "年龄不明",
    "年龄未定",
    "具体年龄不详",
    "不说明年龄",
    "不透露年龄",
    "exact age must remain unspecified",
    "do not give a specific age",
    "do not provide an exact age",
    "age must remain unknown",
    "age unspecified",
    "age ambiguous",
    "age unknown",
    "exact age unknown",
)

_SCHOOL_HISTORY_UNSPECIFIED_MARKERS = (
    "不要解释她过去是否上过学",
    "不要解释他过去是否上过学",
    "不要说明她过去是否上过学",
    "不要说明他过去是否上过学",
    "过去是否上过学保持未知",
    "学校经历保持未知",
    "学校历史保持未知",
    "不说明是否上过学",
    "不要设定学校经历",
    "do not explain whether she ever attended school",
    "do not explain whether he ever attended school",
    "school history must remain unknown",
)

_SELF_REFERENT_PATTERN = r"(?:她|他|该角色|角色)"
_AGE_VALUE_PATTERN = r"(?:\d{1,3}|[零〇一二两三四五六七八九十百]+)\s*岁"
_LEGAL_AGE_PATTERN = r"(?:未成年(?:人)?|成年人|成年女性|成年男性)"
_RELATIVE_AGE_PATTERNS = (
    r"十几岁",
    r"少年时期",
    r"少女时期",
    r"童年(?:时|时期)?",
    r"小时候",
    r"幼年(?:时|时期)?",
    r"成年(?:以后|后)",
    r"未成年时期",
    r"年轻时",
)
_SCHOOL_HISTORY_PATTERNS = (
    r"上过学",
    r"读过书",
    r"曾就读",
    r"离开学校后",
    r"毕业后",
    r"读书期间",
    r"上学时",
    r"在校期间",
)


def age_must_remain_unspecified(request: CharacterDesignRequest) -> bool:
    """Return whether the brief explicitly preserves unknown age.

    This is intentionally narrow: it recognizes an explicit authoring
    constraint, not youthful presentation, body description, or a guessed
    legal-age category.  It exists so a model cannot silently violate a
    plainly stated ambiguity requirement during finalization or repair.
    """

    text = " ".join((*request.hard_constraints, request.brief)).casefold()
    return any(marker.casefold() in text for marker in _AGE_UNSPECIFIED_MARKERS)


def school_history_must_remain_unspecified(request: CharacterDesignRequest) -> bool:
    """Return whether the brief separately preserves unknown school history.

    Current non-student status is deliberately not included.  A request can
    exclude school as a present identity while still supplying ordinary past
    school history.
    """

    text = " ".join((*request.hard_constraints, request.brief)).casefold()
    return any(marker.casefold() in text for marker in _SCHOOL_HISTORY_UNSPECIFIED_MARKERS)


def _character_narrative_fields(draft: CharacterDraft) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    for field_name in (
        "occupation",
        "social_role",
        "design_pitch",
        "personality",
        "background",
        "story_hook",
        "ability_concept",
        "knowledge_scope",
        "constraint_notes",
        "new_design_elements",
        "open_questions",
        "proposed_new_content",
    ):
        value = getattr(draft, field_name)
        if isinstance(value, tuple):
            fields.extend((field_name, str(item)) for item in value)
        elif isinstance(value, str) and value:
            fields.append((field_name, value))
    for relationship in draft.relationships:
        description = relationship.get("description")
        if isinstance(description, str) and description:
            fields.append(("relationships.description", description))
    return tuple(fields)


def _self_age_claim_kind(text: str, character_name: str) -> str | None:
    self_ref = rf"(?:{_SELF_REFERENT_PATTERN}|{re.escape(character_name)})"
    age_value = _AGE_VALUE_PATTERN
    # These patterns intentionally require a self reference close to the age
    # phrase.  They do not classify age mentions belonging to another person.
    if re.search(rf"(?:当前)?年龄\s*(?:是|为|：|:)\s*{age_value}", text):
        return "exact_age"
    if re.search(rf"{self_ref}\s*(?:目前|现在|如今)?\s*(?:是|为)?\s*{age_value}(?!的)", text):
        return "exact_age"
    if re.search(rf"{self_ref}\s*(?:从|在|于)\s*{age_value}\s*(?:时|起|以后|后)?", text):
        return "exact_age"
    if re.search(rf"{age_value}\s*(?:时|起|以后|后)\s*{self_ref}", text):
        return "exact_age"
    if re.search(rf"{self_ref}\s*(?:目前|现在|如今)?\s*(?:是|为|属于)?\s*{_LEGAL_AGE_PATTERN}(?!人?的)", text):
        return "legal_age_status"
    for relative in _RELATIVE_AGE_PATTERNS:
        if re.search(rf"{self_ref}\s*(?:曾经|过去|从|在|于)?\s*{relative}", text):
            return "relative_life_stage"
        if re.search(rf"{relative}(?:时|起|以后|后)?\s*[，,、]?\s*{self_ref}", text):
            return "relative_life_stage"
    return None


def _self_school_history_claim(text: str, character_name: str) -> bool:
    self_ref = rf"(?:{_SELF_REFERENT_PATTERN}|{re.escape(character_name)})"
    for school_pattern in _SCHOOL_HISTORY_PATTERNS:
        if re.search(rf"{self_ref}\s*(?:曾经|过去|后来|在|从)?\s*{school_pattern}", text):
            return True
        if re.search(rf"{school_pattern}\s*[，,、]?\s*{self_ref}", text):
            return True
    return False


def age_information_preservation_violations(
    request: CharacterDesignRequest,
    draft: CharacterDraft,
    *,
    canon_age_supported: bool = False,
) -> tuple[str, ...]:
    """Find unsupported age or school-history claims about the drafted character.

    This is a preservation check, not an age classifier.  It only activates
    for an explicit ambiguity requirement and only recognizes self-referential
    claims in authored text.  A validated Canon source may support the
    structured exact/legal age fields; it does not authorize inventing a
    relative life-stage history.
    """

    violations: list[str] = []
    if age_must_remain_unspecified(request):
        if not canon_age_supported and (draft.age is not None or draft.age_range is not None):
            violations.append("exact_age")
        for _field_name, text in _character_narrative_fields(draft):
            kind = _self_age_claim_kind(text, draft.name)
            if kind is not None and not (canon_age_supported and kind in {"exact_age", "legal_age_status"}):
                violations.append(kind)
    if school_history_must_remain_unspecified(request):
        for _field_name, text in _character_narrative_fields(draft):
            if _self_school_history_claim(text, draft.name):
                violations.append("school_history")
    return tuple(dict.fromkeys(violations))


def _json_safe_relationship_value(value: Any) -> Any:
    """Serialize the small relationship value schema without mutating it."""

    if isinstance(value, Mapping):
        return {str(key): _json_safe_relationship_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe_relationship_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported relationship value for JSON serialization: {type(value).__name__}")


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


CHARACTER_SYSTEM_CONTRACT = """You are a read-only game character authoring agent. Generate a candidate CharacterDraft for a planner, not an in-world NPC and not approved Canon.

Canon grounding is conditional on Canon dependency, not a requirement to call a tool for every brief. New proposed mechanics, personality, appearance, background and other explicitly original design content may be produced without authoring-tool calls when the brief does not depend on existing Canon.

If the brief uses or depends on an existing Canon entity, identifier, fact, rule or context—including an existing faction, lore fact, character, world rule, story, case or incident—you must first search for or retrieve it with the appropriate listed read-only authoring tool before producing the final CharacterDraft. Do not treat a name or ID in the brief as verified evidence. For an existing faction, search/retrieve the faction, use the returned stable ID and evidence, and only then set faction_id or cite that faction in canon_basis. The same rule applies to every other existing Canon claim. Use only facts returned by successful authoring-tool observations.

Every existing Canon claim must be represented by a canon_basis source ID returned by a successful tool observation. canon_basis.supports is a machine-validated contract: prefer defined generic support keys, field paths, or short extractive phrases copied from the cited Canon source; do not freely paraphrase Canon claims in supports. New personal details must be placed in new_design_elements or proposed_new_content and must never be presented as existing Canon. Never create organizations, IDs, files or Canon records. If required Canon cannot be found or verified, do not invent or guess it; leave the Canon-dependent field unresolved and surface the uncertainty through open_questions and constraint_notes. Respect hard constraints. Keep combat_role_profile canonical and high-level; combat_role is accepted only as a deprecated legacy input and must not be emitted. Do not invent numeric balance values.""" + "\n\n" + character_draft_prompt_contract()


CHARACTER_SYSTEM_CONTRACT += """

Generation quality requirements for playable briefs:
- Treat an explicit request for a playable, roster, gacha, five-star, or combat-role character as a request for playable agency. Keep the ordinary occupation and social identity ordinary; do not turn the person into a secret fighter, elite operative, or hidden-organization member merely to justify playability.
- When playability is requested, use `background` or `story_hook` to explain why this ordinary person can plausibly enter dangerous scenes. Do not make them important solely because they are playable.
- When playability is requested, `ability_concept` must answer at a conceptual level: what the player imagines doing during combat, what support/control/burst contribution occurs, how the ability translates the person's identity into action, what visible or spatial feedback the player can understand, and what the play rhythm is. Non-damage support and control are valid, but “only talks” or “does nothing in combat” is insufficient.
- Do not invent elemental classes, weapon taxonomies, damage types, damage multipliers, critical-rate systems, cooldown or energy systems, numeric balance, or other unestablished combat systems. Describe combat fantasy, not a complete game kit.
- If the brief is NPC-only or does not request playability, do not force combat fantasy or a combat role; preserve the ordinary-character principle.

Character hook requirements:
- Use the existing `story_hook` field to make three dimensions explicit when possible: `first impression` (what the player understands immediately), `visual_or_behavioral_motif` (one repeatable phrase, gesture, ordinary object, or routine), and `memorable_contrast` (an observable “appears X, but repeatedly does Y” tension).
- Derive the hook from the brief's identity, personality, routine, ability, or conflict. Ordinary hooks are valid; the hook is not a marketing gimmick and must not be a generic hidden past.

Age, life-stage, and social-position requirements:
- Treat exact Canon age, age presentation, life/social position, and authority as separate concepts. `age: null` and `age_range: null` are valid and preferred when the brief and Canon do not establish an exact age or supported range.
- Never infer an exact age, age range, or legal-age label from height, face, voice, body proportions, clothing, behavior, or youthful/mature presentation. Do not turn age presentation into biological or legal speculation.
- When the brief explicitly keeps age unknown, do not invent self-referential historical age claims such as `十几岁时`, `少年时期`, `小时候`, or `成年后`. Unknown age includes unsupported past life-stage facts; do not add them merely to make the biography feel complete.
- Do not map life stage mechanically to occupation or story importance: youthful presentation does not imply student, adulthood does not imply formal employment, and mature presentation does not imply mentor, parent, retired master, or veteran.
- Do not infer school attendance from youthful presentation alone. A current non-student constraint does not automatically ban ordinary past school history; if the brief explicitly keeps past school history unknown, do not invent `离开学校后` or equivalent self-history. If school is not supported by the brief or Canon, choose among several plausible everyday, occupational, community, family, itinerant, freelance, or independent positions.
- A younger-presenting or age-ambiguous character may hold a dangerous-world occupation when the world and brief support it. Explain how practical experience, apprenticeship, family trade, survival experience, local knowledge, or bounded training makes the work plausible; state limits, support, and missing authority. Do not reject the role solely because presentation is young.
- Playability is not evidence of prodigy, secret training, elite operative status, hidden bloodline, experiment status, command authority, or world-truth knowledge. Preserve high practical competence with limited formal authority when that is the more plausible design.
- Keep competence, formal authority, knowledge access, and narrative importance distinct. Faction membership is not leadership or blanket information access. `faction_id` means formal organization identity; if the prose says the character is not a member, leave `faction_id` null rather than creating a contradiction.
- Do not add sexualized, adultized, or otherwise inappropriate appeal to younger-presenting characters. Build appeal from identity, personality, relationships, motifs, story tension, agency, and gameplay fantasy.

Reference context requirements:
- The supplied reference context is bounded external design precedent, not Canon evidence and not a template. Extract a high-level design principle, transform it into this brief, and do not copy a reference character's personality, combat kit, or visual identity. Field-level causal attribution is not available.
"""


CHARACTER_DRAFT_RECOVERY_SYSTEM_CONTRACT = """You are a bounded provider-neutral CharacterDraft contract recovery step. The original provider response is a partially valid draft. Complete only the explicitly listed missing core fields. Return one JSON object only. Do not rewrite, improve, summarize, or reinterpret any existing field. Do not add fields outside the CharacterDraft schema. Do not call tools. `canon_basis` is a proposal for later Canon Checker validation, not proof of Canon truth. `new_design_elements` must classify only new design material already evidenced by the original draft; do not invent lore, organizations, identities, or major concepts. If the missing field cannot be completed from the original draft and available context, return the field in a schema-valid unresolved form only when the original contract semantics permit it; otherwise return the best structurally valid proposal and let normal validation decide."""

CHARACTER_AUTHORING_ACTION_SYSTEM_CONTRACT = (
    """You are a read-only game character authoring retrieval agent. Inspect the design brief and gather only the existing Canon evidence needed to create a reviewable CharacterDraft. This is a retrieval/action phase, not the final draft response.

If the brief depends on an existing Canon faction, lore fact, character, world rule, story, case or incident, use the appropriate listed read-only authoring tool before finalization. Do not treat names or IDs in the brief as verified evidence. Use only facts returned by successful tool observations, never invent Canon, and never create organizations, IDs, files or Canon records. Perform as many retrieval steps as needed within the tool-round limit. If no Canon retrieval is needed, you may finalize immediately.

When enough evidence has been gathered, or when no Canon retrieval is needed, return exactly """
    + CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL
    + """ and nothing else. Do not return a CharacterDraft, JSON schema, wrapper object, prose, or a substitute signal."""
)


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
    # Optional, bounded external design-reference context.  It is deliberately
    # separate from Canon evidence and defaults empty for all existing callers.
    reference_context: tuple[Mapping[str, Any], ...] = ()
    combat_role_profile: CombatRoleProfile | None = None


@dataclass(frozen=True)
class CharacterGenerationAudit:
    request_id: str
    tool_rounds: int
    tool_calls: tuple[ToolAuditEntry, ...]
    source_ids: tuple[str, ...]
    model_invocations: tuple[ModelInvocationAudit, ...] = ()
    reference_ids: tuple[str, ...] = ()
    normalized_fields: tuple[str, ...] = ()
    contract_recovery: CharacterDraftRecoveryAudit = field(default_factory=CharacterDraftRecoveryAudit)


@dataclass(frozen=True)
class CharacterGenerationResult:
    draft: CharacterDraft
    sources: tuple[str, ...]
    audit: CharacterGenerationAudit
    design_plan: CharacterDesignPlan | None = None


class CharacterGenerationAgent:
    """Sibling consumer to NpcConversationAgent for one-shot draft generation."""

    def __init__(self, model: AgentModel, *, resolver: KnowledgeResolver | None = None, story_repository: StoryRepository | None = None, max_tool_rounds: int = 6, authoring_context: CharacterAuthoringKnowledgeContext | None = None, reference_context: Sequence[Mapping[str, Any]] = ()) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()
        self.tools = CharacterAuthoringToolbox(self.resolver, self.story_repository)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.authoring_context = authoring_context or CharacterAuthoringKnowledgeContext()
        self.reference_context = tuple(dict(item) for item in reference_context)

    def generate(
        self,
        request: CharacterDesignRequest | str,
        *,
        use_intent_layer: bool = False,
    ) -> CharacterGenerationResult:
        if isinstance(request, str):
            request = CharacterDesignRequest(request)
        if not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be CharacterDesignRequest or string")
        design_plan = None
        if use_intent_layer:
            design_plan = CharacterDesignPlan.from_text(request.brief)
            request = self._request_with_design_plan(request, design_plan)
        authoring = CharacterAuthoringView("character_authoring", "create a reviewable CharacterDraft", tuple(sorted(self.authoring_context.allowed_scopes)))
        runtime = CharacterGenerationRuntimeView(
            request.request_id,
            request.brief,
            request.hard_constraints,
            request.soft_preferences,
            request.forbidden_elements,
            request.desired_connections,
            self.reference_context,
            request.combat_role_profile,
        )
        messages: list[ConversationMessage] = [ConversationMessage("user", json.dumps(request.to_dict(), ensure_ascii=False, separators=(",", ":")))]
        source_ids: set[str] = set()
        source_types: dict[str, str] = {}
        audits: list[ToolAuditEntry] = []
        invocations: list[ModelInvocationAudit] = []
        recovery_audit = CharacterDraftRecoveryAudit()
        try:
            finalization_round: int | None = None
            for round_number in range(1, self.max_tool_rounds + 1):
                evidence = tuple(
                    GroundingEvidence(f"canon:{source_id}", GroundingEvidenceType.TOOL_LORE, source_id, source_id if source_type == "lore" else None)
                    for source_id, source_type in sorted(source_types.items())
                )
                prompt = AgentPrompt(
                    CHARACTER_AUTHORING_ACTION_SYSTEM_CONTRACT,
                    authoring,
                    runtime,
                    tuple(messages),
                    self.tools.tool_definitions,
                    f"character_generation:{request.request_id}",
                    round_number,
                    evidence,
                    response_format="character_authoring_action",
                )
                turn = self.model.generate(prompt)
                if turn.invocation is not None:
                    invocations.append(turn.invocation)
                if turn.tool_calls:
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
                if not has_terminal_authoring_finalize_signal(turn.text or ""):
                    raise ModelMalformedResponseError(
                        "Authoring action must be a real tool call or end with the exact FINALIZE signal"
                    )
                finalization_round = round_number + 1
                break
            if finalization_round is None:
                finalization_round = self.max_tool_rounds + 1

            evidence = tuple(
                GroundingEvidence(f"canon:{source_id}", GroundingEvidenceType.TOOL_LORE, source_id, source_id if source_type == "lore" else None)
                for source_id, source_type in sorted(source_types.items())
            )
            final_prompt = AgentPrompt(
                CHARACTER_SYSTEM_CONTRACT,
                authoring,
                runtime,
                tuple(messages),
                (),
                f"character_generation:{request.request_id}",
                finalization_round,
                evidence,
                response_format="character_draft",
            )
            final_turn = self.model.generate(final_prompt)
            if final_turn.invocation is not None:
                invocations.append(final_turn.invocation)
            if final_turn.tool_calls:
                raise AgentExecutionError(
                    "Character finalization model attempted a tool call"
                )
            payload = final_turn.structured_output
            if payload is None:
                if not isinstance(final_turn.text, str):
                    raise AgentExecutionError("Model returned no CharacterDraft")
                try:
                    payload = json.loads(final_turn.text)
                except json.JSONDecodeError:
                    raise ModelMalformedResponseError("CharacterDraft response is not valid JSON") from None
            payload, normalized_fields = _normalize_character_draft_payload(payload)
            payload, recovery_audit = self._recover_character_draft_payload(
                payload,
                request=request,
                authoring=authoring,
                runtime=runtime,
                messages=messages,
                evidence=evidence,
                turn_number=finalization_round,
                invocations=invocations,
                source_ids=source_ids,
                source_types=source_types,
            )
            draft = CharacterDraft.from_mapping(payload)
            self._validate_draft(draft, request, source_ids, source_types)
            audit = CharacterGenerationAudit(
                request.request_id,
                len(audits),
                tuple(audits),
                tuple(sorted(source_ids)),
                tuple(invocations),
                tuple(item["reference_id"] for item in self.reference_context if isinstance(item.get("reference_id"), str)),
                normalized_fields,
                recovery_audit,
            )
            return CharacterGenerationResult(
                draft,
                tuple(sorted(source_ids)),
                audit,
                design_plan,
            )
        except Exception as error:
            # CharacterGenerationAudit only exists on success, so the
            # propagating exception is the failure-path audit carrier. Keep the
            # invocation trail (including the adapter-attached failure audit)
            # observable on any abort: a failed call stays distinguishable
            # from a call that never happened. Metadata only, never raw output.
            if isinstance(error, ModelError) and error.audit is not None:
                invocations.append(error.audit)
            error.model_invocations = tuple(invocations)
            recovery_audit = getattr(error, "contract_recovery", recovery_audit)
            error.contract_recovery = recovery_audit
            raise
        raise AgentExecutionError("Character generation ended without a draft")

    def generate_with_intent(
        self,
        request: CharacterDesignRequest | str,
    ) -> CharacterGenerationResult:
        """Generate through the optional deterministic Character Intelligence Layer."""

        return self.generate(request, use_intent_layer=True)

    @staticmethod
    def _request_with_design_plan(
        request: CharacterDesignRequest,
        plan: CharacterDesignPlan,
    ) -> CharacterDesignRequest:
        """Project plan signals into the existing request contract.

        The existing CharacterDesignRequest remains the only input contract
        seen by the generation pipeline.  This keeps the new layer additive
        while allowing the current agent and its validators to remain intact.
        """

        intent = plan.parsed_intent
        forbidden = tuple(
            dict.fromkeys((*request.forbidden_elements, *intent.forbidden_patterns))
        )
        return CharacterDesignRequest(
            brief=request.brief,
            hard_constraints=tuple(
                dict.fromkeys((*request.hard_constraints, *plan.generation_constraints))
            ),
            soft_preferences=tuple(
                dict.fromkeys((*request.soft_preferences, *plan.recommended_traits))
            ),
            forbidden_elements=forbidden,
            desired_connections=request.desired_connections,
            request_id=request.request_id,
            combat_role_profile=plan.combat_role_profile,
        )

    def _recover_character_draft_payload(
        self,
        payload: Any,
        *,
        request: CharacterDesignRequest,
        authoring: CharacterAuthoringView,
        runtime: CharacterGenerationRuntimeView,
        messages: Sequence[ConversationMessage],
        evidence: tuple[GroundingEvidence, ...],
        turn_number: int,
        invocations: list[ModelInvocationAudit],
        source_ids: set[str],
        source_types: Mapping[str, str],
    ) -> tuple[Mapping[str, Any], CharacterDraftRecoveryAudit]:
        inspection = inspect_character_draft_payload(payload)
        if inspection.invalid_fields:
            raise ModelMalformedResponseError(
                self._contract_diagnosis("CharacterDraft validation failed", inspection)
            )

        # Unknown keys are safe to discard only after all known core fields
        # are present and the known payload itself parses successfully.
        if inspection.unknown_fields and not inspection.missing_required:
            cleaned = {
                key: value
                for key, value in payload.items()
                if key in CharacterDraft._ACCEPTED_INPUT_FIELDS
            }
            return cleaned, CharacterDraftRecoveryAudit(
                status="applied",
                discarded_unknown_fields=inspection.unknown_fields,
                unknown_fields=inspection.unknown_fields,
            )

        if not inspection.missing_required:
            return payload, CharacterDraftRecoveryAudit()

        # Missing core fields and unknown/invalid known fields together are
        # ambiguous.  Do not discard or rewrite anything in that case.
        if inspection.unknown_fields or inspection.invalid_fields:
            raise ModelMalformedResponseError(
                self._contract_diagnosis("CharacterDraft contract is not safely recoverable", inspection)
            )

        recovery_audit = CharacterDraftRecoveryAudit(
            status="attempted",
            attempted=True,
            missing_required=inspection.missing_required,
        )
        recovery_prompt = AgentPrompt(
            CHARACTER_DRAFT_RECOVERY_SYSTEM_CONTRACT,
            authoring,
            runtime,
            tuple(messages),
            (),
            f"character_generation:{request.request_id}",
            turn_number + 1,
            evidence,
            response_format="character_draft",
            authoring_payload={
                "task": "complete_missing_character_draft_fields",
                "missing_required": list(inspection.missing_required),
                "original_draft": dict(payload),
                "request": request.to_dict(),
                "available_canon_source_ids": sorted(source_ids),
                "available_canon_source_types": dict(sorted(source_types.items())),
                "reference_context": [dict(item) for item in self.reference_context],
            },
            invocation_purpose="character_draft_recovery",
        )
        try:
            recovery_turn = self.model.generate(recovery_prompt)
            if recovery_turn.invocation is not None:
                invocations.append(recovery_turn.invocation)
            if recovery_turn.tool_calls:
                raise AgentExecutionError(
                    "CharacterDraft contract recovery does not permit tool calls"
                )
            recovered = recovery_turn.structured_output
            if recovered is None:
                if not isinstance(recovery_turn.text, str):
                    raise ModelMalformedResponseError(
                        "CharacterDraft contract recovery returned no JSON object"
                    )
                try:
                    recovered = json.loads(recovery_turn.text)
                except json.JSONDecodeError:
                    raise ModelMalformedResponseError(
                        "CharacterDraft contract recovery returned invalid JSON"
                    ) from None
            if not isinstance(recovered, Mapping):
                raise ModelMalformedResponseError(
                    "CharacterDraft contract recovery must return a JSON object"
                )
            recovered_inspection = inspect_character_draft_payload(recovered)
            if recovered_inspection.unknown_fields or recovered_inspection.invalid_fields:
                raise ModelMalformedResponseError(
                    self._contract_diagnosis(
                        "CharacterDraft contract recovery returned invalid fields",
                        recovered_inspection,
                    )
                )
            missing = set(inspection.missing_required)
            if not missing <= set(recovered):
                remaining = tuple(sorted(missing - set(recovered)))
                raise ModelMalformedResponseError(
                    "CharacterDraft contract recovery remained incomplete: "
                    + ", ".join(remaining)
                )
            for key, value in recovered.items():
                if key in missing:
                    continue
                if key not in payload or payload[key] != value:
                    raise ModelMalformedResponseError(
                        f"CharacterDraft contract recovery attempted to overwrite valid field: {key}"
                    )
            merged = dict(payload)
            merged.update({key: recovered[key] for key in inspection.missing_required})
            merged_inspection = inspect_character_draft_payload(merged)
            if merged_inspection.missing_required or merged_inspection.unknown_fields or merged_inspection.invalid_fields:
                raise ModelMalformedResponseError(
                    self._contract_diagnosis(
                        "CharacterDraft contract recovery produced an invalid draft",
                        merged_inspection,
                    )
                )
            CharacterDraft.from_mapping(merged)
            return merged, CharacterDraftRecoveryAudit(
                status="applied",
                attempted=True,
                missing_required=inspection.missing_required,
                recovered_fields=inspection.missing_required,
            )
        except Exception as error:
            failed = CharacterDraftRecoveryAudit(
                status="failed",
                attempted=True,
                missing_required=inspection.missing_required,
                error_message=str(error),
            )
            error.contract_recovery = failed
            raise

    @staticmethod
    def _contract_diagnosis(
        prefix: str,
        inspection: CharacterDraftContractInspection,
    ) -> str:
        return (
            f"{prefix}: missing_required={list(inspection.missing_required)}, "
            f"unknown fields={list(inspection.unknown_fields)}, "
            f"invalid fields={list(inspection.invalid_fields)}"
        )

    @staticmethod
    def _validate_draft(draft: CharacterDraft, request: CharacterDesignRequest, source_ids: set[str], source_types: Mapping[str, str]) -> None:
        age_bounds = CharacterGenerationAgent._age_bounds(request)
        canon_age_supported = any(
            entry.source_id in source_ids
            and any(
                support.casefold() in {"age", "age_range", "legal_age_status", "age_status"}
                for support in entry.supports
            )
            for entry in draft.canon_basis
        )
        age_violations = age_information_preservation_violations(
            request,
            draft,
            canon_age_supported=canon_age_supported,
        )
        if age_violations:
            raise AgentExecutionError(
                "Draft age-preservation violation despite an explicit unspecified-age constraint: "
                + ", ".join(age_violations)
            )
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

    def __init__(self, *, scenario: str = "valid") -> None:
        if scenario not in {"valid", "canon_conflict"}:
            raise ValueError("scenario must be 'valid' or 'canon_conflict'")
        self.scenario = scenario
        self.prompts: list[AgentPrompt] = []

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        self.prompts.append(prompt)
        if prompt.response_format not in {
            "character_authoring_action",
            "character_draft",
        }:
            raise RuntimeError(
                "DeterministicCharacterGenerationModel requires character authoring prompts"
            )
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
        if prompt.response_format == "character_authoring_action":
            return ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL)
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
        requested_profile = prompt.runtime.combat_role_profile
        profile = requested_profile if requested_profile is not None else CombatRoleProfile(primary_role="support")
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
            "combat_role_profile": profile.to_dict(),
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

        if self.scenario == "canon_conflict":
            # This is a deterministic model fixture, not a checker shortcut:
            # the real CanonChecker must detect RULE-008 and the real repair
            # model must handle the resulting finding.
            payload["background"] = "她隶属于秘密政府能力管理局，负责统一处理所有能力相关事务。"
        return ModelTurn(text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")), structured_output=payload)


@dataclass(frozen=True)
class CharacterDraftContractInspection:
    """Provider-neutral diagnosis before CharacterDraft parsing."""

    missing_required: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "missing_required": list(self.missing_required),
            "unknown_fields": list(self.unknown_fields),
            "invalid_fields": list(self.invalid_fields),
        }


def inspect_character_draft_payload(payload: Any) -> CharacterDraftContractInspection:
    """Inspect shape without inventing any missing CharacterDraft content."""

    if not isinstance(payload, Mapping):
        return CharacterDraftContractInspection(invalid_fields=("<root>",))
    missing = tuple(sorted(set(CHARACTER_DRAFT_CORE_FIELDS) - set(payload)))
    unknown = tuple(sorted(set(payload) - CharacterDraft._ACCEPTED_INPUT_FIELDS))
    known_payload = {
        key: value
        for key, value in payload.items()
        if key in CharacterDraft._ACCEPTED_INPUT_FIELDS
    }
    if missing:
        # Fill only for diagnostic probing so a malformed known field is not
        # mistaken for a recoverable omission.  These values never reach the
        # final draft and are not deterministic defaults.
        probe = dict(known_payload)
        probe.setdefault("draft_id", "draft_contract_probe")
        probe.setdefault("status", "draft")
        probe.setdefault("name", "contract probe")
        probe.setdefault("canon_basis", [])
        probe.setdefault("new_design_elements", [])
        probe.setdefault("open_questions", [])
        try:
            CharacterDraft.from_mapping(probe)
        except ModelMalformedResponseError as error:
            fields = tuple(sorted(set(re.findall(r"CharacterDraft\.([A-Za-z_][A-Za-z0-9_]*)", str(error)))))
            if fields:
                return CharacterDraftContractInspection(
                    missing_required=missing,
                    unknown_fields=unknown,
                    invalid_fields=fields,
                )
        return CharacterDraftContractInspection(missing_required=missing, unknown_fields=unknown)
    try:
        CharacterDraft.from_mapping(known_payload)
    except ModelMalformedResponseError as error:
        fields = tuple(sorted(set(re.findall(r"CharacterDraft\.([A-Za-z_][A-Za-z0-9_]*)", str(error)))))
        return CharacterDraftContractInspection(
            unknown_fields=unknown,
            invalid_fields=fields or ("<root>",),
        )
    return CharacterDraftContractInspection(unknown_fields=unknown)


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
    "CharacterDraftContractInspection",
    "DeterministicCharacterGenerationModel",
    "StoryLink",
    "age_information_preservation_violations",
    "age_must_remain_unspecified",
    "school_history_must_remain_unspecified",
    "inspect_character_draft_payload",
]
