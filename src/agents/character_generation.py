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
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from along_street_resources import data_resource
from character_intelligence.planner import CharacterAffiliationContext, CharacterDesignPlan
from character_skill import (
    ProtocolSkillKitCandidate,
    SkillKitShapeError,
    SkillValidationContext,
    evaluate,
    parse_candidate,
    render_ability_concept,
)
from character_skill.errors import SkillKitShapeDiagnostic, build_shape_diagnostic
from combat_semantics import CombatRoleProfile, resolve_legacy_combat_role_profile
from knowledge import KnowledgeResolver
from story import StoryRepository, load_story_repository

from .character_retrieval import build_character_retrieval_plan
from .errors import (
    AgentError,
    AgentExecutionError,
    AgentToolError,
    ModelAuthenticationError,
    ModelCapabilityError,
    ModelConfigurationError,
    ModelError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from .model_protocol import AgentModel
from .models import (
    AgentPrompt,
    CharacterDraftRecoveryAudit,
    CharacterSkillShadowResult,
    ConversationMessage,
    GroundingEvidence,
    GroundingEvidenceType,
    ModelInvocationAudit,
    ModelTurn,
    SkillShadowAudit,
    SkillShadowConfig,
    ToolAuditEntry,
    ToolCall,
    ToolDefinition,
)
from .response_contracts import (
    CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL,
    CHARACTER_DRAFT_CORE_FIELDS,
    CHARACTER_DRAFT_JSON_SCHEMA,
    character_draft_prompt_contract,
    character_skill_kit_prompt_contract,
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

    def __post_init__(self) -> None:
        profile = self.combat_role_profile
        if profile is None:
            profile = CombatRoleProfile()
        elif not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")
        object.__setattr__(self, "combat_role_profile", profile)

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
        profile_raw = payload.get("combat_role_profile")
        try:
            profile = resolve_legacy_combat_role_profile(profile_raw, legacy_raw)
        except (TypeError, ValueError) as error:
            raise ModelMalformedResponseError(
                f"CharacterDraft.combat_role compatibility input is invalid: {error}"
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


CANON_GROUNDING_TEXT_FIELDS = (
    "occupation",
    "social_role",
    "design_pitch",
    "personality",
    "background",
    "story_hook",
    "ability_concept",
    "knowledge_scope",
)

_CANON_ID_PATTERN = re.compile(
    r"\b(?:lore(?:_secret)?_[A-Za-z0-9_.:-]+|faction_[A-Za-z0-9_.:-]+|"
    r"char_[A-Za-z0-9_.:-]+|(?:story|case|incident|project)_[A-Za-z0-9_.:-]+)\b"
)


def _safe_character_draft_recovery_error_message(error: BaseException) -> str:
    """Return a fixed diagnostic safe for the recovery audit boundary.

    Recovery errors can originate from a provider, a model contract parser, or
    an unexpected implementation boundary.  Their exception text is not a
    safe audit input because it may contain provider payloads, prompts, model
    output, or credentials.  Keep this mapping deliberately fixed and narrow;
    the original exception is still propagated for fail-closed behavior.
    """

    if isinstance(error, ModelTimeoutError):
        return "CharacterDraft contract recovery provider request timed out after bounded retries"
    if isinstance(error, ModelRateLimitError):
        return "CharacterDraft contract recovery provider rate limited the request after bounded retries"
    if isinstance(error, ModelAuthenticationError):
        return "CharacterDraft contract recovery provider authentication failed"
    if isinstance(error, ModelCapabilityError):
        return "CharacterDraft contract recovery provider cannot satisfy the authoring contract"
    if isinstance(error, ModelConfigurationError):
        return "CharacterDraft contract recovery model configuration is invalid"
    if isinstance(error, ModelProviderError):
        return "CharacterDraft contract recovery provider request failed"
    if isinstance(error, ModelMalformedResponseError):
        return "CharacterDraft contract recovery response failed the structural contract"
    if isinstance(error, AgentExecutionError):
        return "CharacterDraft contract recovery execution failed safely"
    if isinstance(error, AgentError):
        return "CharacterDraft contract recovery agent operation failed"
    return "CharacterDraft contract recovery failed safely"
_ORGANIZATION_NAME_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9·]{2,}"
    r"(?:研究中心|研究院|合作社|基金会|管理局|联席体系|保险|传媒|集团|公司|机构|组织|协会|事务所)"
)
_NEW_DESIGN_FIELD_PATTERN = re.compile(
    r"^new_design:(?P<field>[A-Za-z_][A-Za-z0-9_.]*)(?::|$)"
)
_NEGATED_CANON_ID_CLAIM_PATTERN = re.compile(
    r"(?:不了解|不知道|不掌握)"
    r"|(?:不|并不|不能|无法|无权|没有|并未|未)\s*"
    r"(?:默认)?(?:访问|读取|调阅|查阅|调取|查看|检索|掌握|知道|了解)"
    r"|(?:无访问权|没有访问权限|无权访问|不具备(?:对.{0,24})?访问权限)"
)


def declared_new_design_fields(draft: CharacterDraft) -> frozenset[str]:
    """Return fields explicitly classified as new design by the draft.

    The prefix is intentionally machine-readable.  A free-form
    ``new_design_elements`` sentence must not silently authorize every other
    narrative field in a Canon-dependent draft.
    """

    fields: set[str] = set()
    for item in draft.new_design_elements:
        match = _NEW_DESIGN_FIELD_PATTERN.match(item.strip())
        if match:
            fields.add(match.group("field"))
    return frozenset(fields)


def _canon_id_references(
    text: str, source_ids: set[str] | frozenset[str]
) -> tuple[tuple[str, int, int], ...]:
    """Return namespace-shaped and known Canon ID references in text."""

    references = [
        (match.group(0), match.start(), match.end())
        for match in _CANON_ID_PATTERN.finditer(text)
    ]
    for source_id in sorted(set(source_ids), key=lambda item: (-len(item), item)):
        if not source_id:
            continue
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_.:-]){re.escape(source_id)}(?![A-Za-z0-9_.:-])"
        )
        references.extend(
            (source_id, match.start(), match.end())
            for match in pattern.finditer(text)
        )
    return tuple(sorted(set(references), key=lambda item: (item[1], item[2], item[0])))


def _canon_alias_references(
    text: str,
    aliases: Mapping[str, Sequence[str]] | None,
) -> tuple[tuple[str, int, int], ...]:
    """Return registered Canon entity-name references with their source IDs."""

    if not aliases:
        return ()
    references: list[tuple[str, int, int]] = []
    for source_id in sorted(aliases):
        for alias in sorted(
            {item.strip() for item in aliases[source_id] if isinstance(item, str) and item.strip()},
            key=lambda item: (-len(item), item),
        ):
            references.extend(
                (source_id, match.start(), match.end())
                for match in re.finditer(re.escape(alias), text, flags=re.IGNORECASE)
            )
    return tuple(sorted(set(references), key=lambda item: (item[1], item[2], item[0])))


def _is_negated_canon_id_reference(text: str, start: int, end: int) -> bool:
    """Keep explicit negative knowledge references out of positive grounding."""

    sentence_start = max(
        text.rfind(marker, 0, start) for marker in "。！？；!?;\n"
    ) + 1
    sentence_end_candidates = [
        text.find(marker, end)
        for marker in "。！？；!?;\n"
        if text.find(marker, end) >= 0
    ]
    sentence_end = min(sentence_end_candidates, default=len(text))
    before = text[sentence_start:start]
    after = text[end:sentence_end]
    local_before = re.split(r"[，,、]|但|但是|而|不过|同时", before)[-1]
    if _NEGATED_CANON_ID_CLAIM_PATTERN.search(local_before):
        return True
    return bool(_NEGATED_CANON_ID_CLAIM_PATTERN.search(after))


def canon_field_grounding_violations(
    draft: CharacterDraft,
    source_ids: set[str] | frozenset[str],
    *,
    available_source_ids: set[str] | frozenset[str] | None = None,
    known_source_aliases: Mapping[str, Sequence[str]] | None = None,
    reject_unknown_organizations: bool = False,
) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    """Find narrative fields lacking an explicit Canon/design classification.

    ``canon_basis.supports`` is the field-level edge in the evidence graph.
    A field may instead be explicitly marked with ``new_design:<field>``.  An
    existing Canon ID in prose always requires the Canon edge, even when the
    field also has a new-design declaration.
    """

    available = set(source_ids if available_source_ids is None else available_source_ids)
    basis_by_field: dict[str, set[str]] = {}
    for entry in draft.canon_basis:
        for support in entry.supports:
            if support in CANON_GROUNDING_TEXT_FIELDS:
                basis_by_field.setdefault(support, set()).add(entry.source_id)

    declared = declared_new_design_fields(draft)
    violations: list[tuple[str, tuple[str, ...], str]] = []
    for field in CANON_GROUNDING_TEXT_FIELDS:  # noqa: F402 - domain field vocabulary
        value = getattr(draft, field)
        text = " ".join(value) if isinstance(value, tuple) else str(value)
        if not text.strip():
            continue

        referenced_ids = tuple(
            dict.fromkeys(
                source_id
                for source_id, start, end in (
                    *_canon_id_references(text, source_ids),
                    *_canon_alias_references(text, known_source_aliases),
                )
                if not _is_negated_canon_id_reference(text, start, end)
            )
        )
        if referenced_ids:
            unsupported: list[str] = []
            for source_id in referenced_ids:
                entries = [
                    entry
                    for entry in draft.canon_basis
                    if entry.source_id == source_id and field in entry.supports
                ]
                if source_id not in available or not entries:
                    unsupported.append(source_id)
            if unsupported:
                violations.append(
                    (
                        field,
                        tuple(unsupported),
                        "Narrative field references Canon IDs without a field-level canon_basis edge.",
                    )
                )
            continue

        if (
            field == "occupation"
            and reject_unknown_organizations
            and known_source_aliases
            and _ORGANIZATION_NAME_PATTERN.search(text)
        ):
            violations.append(
                (
                    field,
                    (),
                    "Occupation names an unverified organization; retrieve an existing Canon entity or use an ordinary role without creating an organization.",
                )
            )
            continue

        if field not in basis_by_field and field not in declared:
            violations.append(
                (
                    field,
                    (),
                    "Narrative field must be backed by canon_basis or an explicit new_design field declaration.",
                )
            )
    return tuple(violations)


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
        ranked = self._rank(query, records, lambda item: f"{item.get('name', '')} {item.get('short_name', '')} {item.get('aliases', '')} {item.get('type', '')} {item.get('core_function', {}).get('description', '')} {' '.join(item.get('tags', []))}")[:limit]
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
        query_units = CharacterAuthoringToolbox._units(query.casefold())
        scored = []
        for record in records:
            raw_text = str(text_fn(record))
            text = CharacterAuthoringToolbox._normalize(raw_text)
            text_units = CharacterAuthoringToolbox._units(raw_text.casefold())
            score = (20 if query_norm and query_norm in text else 0) + sum(1 for unit in query_units & text_units)
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
        return {"id": record.get("id"), "source_id": record.get("id"), "source_type": "lore", "title": record.get("title", ""), "summary": record.get("statement", ""), "category": record.get("category"), "sensitivity": record.get("sensitivity", "public")}

    @staticmethod
    def _lore_view(record: Mapping[str, Any]) -> dict[str, Any]:
        return {"id": record.get("id"), "lore_id": record.get("id"), "source_id": record.get("id"), "source_type": "lore", "title": record.get("title", ""), "statement": record.get("statement", ""), "category": record.get("category"), "sensitivity": record.get("sensitivity", "public")}

    @classmethod
    def _faction_summary(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        function = record.get("core_function", {})
        return {
            "id": record.get("id"),
            "source_id": record.get("id"),
            "source_type": "faction",
            "name": record.get("name", ""),
            "type": record.get("type", ""),
            "summary": function.get("description", "") if isinstance(function, Mapping) else "",
            "tags": record.get("tags", []),
            "public_identity": record.get("public_identity", {}),
            "public_reputation": record.get("public_reputation", {}),
            "core_function": record.get("core_function", {}),
            "member_profile": record.get("member_profile", {}),
            "internal_structure": record.get("internal_structure", {}),
            "character_archetypes": record.get("character_archetypes", []),
            "story_functions": record.get("story_functions", []),
        }

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
        path = data_resource("canon", "world_bible.md")
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

Occupation contract: an ordinary role such as a freelancer, photographer, coordinator or consultant may be new design and must be marked `new_design:occupation:` when it does not depend on an existing entity. If occupation text names or includes a registered Canon entity, retrieve that entity and add a field-level `canon_basis` edge for `occupation`; do not classify the Canon entity relationship as new design. Never invent an organization, company, group, institution or named employer. A mixed occupation may keep its ordinary role tail as new design, but its Canon organization reference still requires the retrieved source edge.

Every existing Canon claim must be represented by a canon_basis source ID returned by a successful tool observation. canon_basis.supports is a machine-validated contract: prefer defined generic support keys, field paths, or short extractive phrases copied from the cited Canon source; do not freely paraphrase Canon claims in supports. Every non-empty Canon-bearing text field must either include its exact field path in a canon_basis.supports entry or have an explicit new_design:<field> declaration in new_design_elements. A free-form new_design_elements sentence does not authorize unrelated fields. If a narrative field names an existing Canon ID, it must have a field-level basis edge even when the surrounding idea is new design. New personal details must be placed in new_design_elements or proposed_new_content and must never be presented as existing Canon. Never create organizations, IDs, files or Canon records. If required Canon cannot be found or verified, do not invent or guess it; leave the Canon-dependent field unresolved and surface the uncertainty through open_questions and constraint_notes. Respect hard constraints. Keep combat_role_profile canonical and high-level; do not emit a flat combat-role field. Do not invent numeric balance values.""" + "\n\n" + character_draft_prompt_contract()


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


CHARACTER_FINALIZATION_SYSTEM_CONTRACT = CHARACTER_SYSTEM_CONTRACT + """

Finalization seam: retrieval is complete. Do not call tools, reconstruct retrieval
history, or treat an absent Canon source as verified. The user payload contains a
deterministic Evidence Bundle built from successful read-only retrieval. Treat
only the bundle's source IDs and factual payloads as available Canon evidence;
do not ask the provider to summarize Canon as an authority. Use the request and
bundle as the complete finalization context.
"""


CHARACTER_DRAFT_RECOVERY_SYSTEM_CONTRACT = """You are a bounded provider-neutral CharacterDraft contract recovery step. The original provider response is a partially valid draft. Complete only the explicitly listed missing core fields. Return one JSON object only. Do not rewrite, improve, summarize, or reinterpret any existing field. Do not add fields outside the CharacterDraft schema. Do not call tools. `canon_basis` is a proposal for later Canon Checker validation, not proof of Canon truth. Every non-empty Canon-bearing text field must retain an exact field-level `canon_basis.supports` edge or an explicit `new_design:<field>:` declaration; a free-form design sentence is not a substitute. `new_design_elements` must classify only new design material already evidenced by the original draft; do not invent lore, organizations, identities, or major concepts. If the missing field cannot be completed from the original draft and available context, return the field in a schema-valid unresolved form only when the original contract semantics permit it; otherwise return the best structurally valid proposal and let normal validation decide."""

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
    affiliation_context: Mapping[str, Any] | None = None


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
class GroundingFailureDiagnostic:
    """Sanitized metadata for one fail-closed draft grounding rejection."""

    check: str
    canon_id: str | None = None


_SAFE_GROUNDING_CANON_ID = re.compile(
    r"(?:world_rules|(?:faction|lore|char|story|case|incident|project)_[A-Za-z0-9][A-Za-z0-9_.:-]*)"
)
_ACTION_TERMINATION_PHASE = "action_termination"
_FINALIZATION_CONTEXT_PHASE = "finalization_context"


def _classify_generation_failure(
    error: Exception,
    *,
    phase: str,
    reason: str,
) -> None:
    """Attach fixed, sanitized stage metadata to a generation failure."""

    error.phase = phase
    error.reason = reason


def _safe_grounding_canon_id(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_GROUNDING_CANON_ID.fullmatch(value):
        return value
    return None


def _grounding_failure(
    message: str,
    *,
    check: str,
    canon_id: Any = None,
) -> AgentExecutionError:
    error = AgentExecutionError(message)
    error.grounding_failure = GroundingFailureDiagnostic(
        check=check,
        canon_id=_safe_grounding_canon_id(canon_id),
    )
    return error


_FINALIZATION_SEARCH_TO_SOURCE_TYPE = {
    "search_lore": frozenset({"lore"}),
    "search_factions": frozenset({"faction"}),
    "search_characters": frozenset({"character"}),
    "search_story_context": frozenset({"story", "case", "incident"}),
}
_FINALIZATION_SEARCH_BOUND_PER_SOURCE_TYPE = 5


@dataclass(frozen=True)
class CharacterFinalizationContext:
    """Clean, provider-facing evidence context for the draft turn.

    Retrieval history is intentionally not part of this context.  The full
    history remains on the generation audit, while the finalizer receives a
    deterministic evidence bundle and the single original request message.
    Search-only discovery is bounded to five sources per source type, matching
    the toolbox's default search limit.  Explicit ``get_*`` observations and
    request-matched sources are retained outside that discovery bound.
    """

    messages: tuple[ConversationMessage, ...]
    evidence: tuple[GroundingEvidence, ...]
    source_ids: tuple[str, ...]
    source_types: Mapping[str, str]
    evidence_bundle: tuple[Mapping[str, Any], ...] = ()
    selected_search_counts: Mapping[str, int] = field(default_factory=dict)
    pruned_source_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        object.__setattr__(
            self,
            "source_types",
            MappingProxyType(dict(self.source_types)),
        )
        object.__setattr__(
            self,
            "evidence_bundle",
            tuple(dict(item) for item in self.evidence_bundle),
        )
        object.__setattr__(
            self,
            "selected_search_counts",
            MappingProxyType(dict(self.selected_search_counts)),
        )


@dataclass(frozen=True)
class _FinalizationCallRecord:
    group_index: int
    call_index: int
    call: Mapping[str, Any]
    tool_message: ConversationMessage
    audit: ToolAuditEntry
    source_ids: frozenset[str]
    observation: Mapping[str, Any]


@dataclass(frozen=True)
class _FinalizationSearchCandidate:
    source_id: str
    source_type: str
    group_index: int
    call_index: int
    result_index: int
    score: int
    result: Mapping[str, Any]


_FINALIZATION_SAFE_PAYLOAD_KEYS = {
    "world_rules": (
        "rules",
        "forbidden_patterns",
        "scope_summary",
    ),
    "lore": (
        "title",
        "statement",
        "summary",
        "category",
        "sensitivity",
    ),
    "faction": (
        "name",
        "type",
        "summary",
        "tags",
        "status",
        "public_identity",
        "public_reputation",
        "core_function",
        "member_profile",
        "canon_constraints",
        "internal_structure",
        "character_archetypes",
        "story_functions",
    ),
    "character": (
        "name",
        "age",
        "occupation",
        "faction_id",
        "tags",
        "character_hook",
        "personality",
        "ability",
        "narrative",
    ),
    "story": (
        "name",
        "summary",
        "faction_ids",
    ),
    "case": (
        "name",
        "summary",
        "story_refs",
        "related_incident_ids",
    ),
    "incident": (
        "name",
        "summary",
        "story_refs",
        "related_case_ids",
    ),
}
_FINALIZATION_ALLOWED_SOURCE_TYPES = frozenset(_FINALIZATION_SAFE_PAYLOAD_KEYS)


def _finalization_json_safe(value: Any) -> Any:
    """Copy only JSON-shaped deterministic Canon data into the bundle."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _finalization_json_safe(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            if isinstance(key, (str, int, float, bool))
        }
    if isinstance(value, (tuple, list)):
        return [_finalization_json_safe(item) for item in value]
    return None


def _finalization_has_factual_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value) and any(_finalization_has_factual_value(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return bool(value) and any(_finalization_has_factual_value(item) for item in value)
    return True


def _finalization_safe_payload(
    source_id: str,
    source_type: str,
    observation_payload: Mapping[str, Any] | None,
    *,
    allow_restricted_lore: bool = True,
) -> dict[str, Any]:
    if source_type not in _FINALIZATION_ALLOWED_SOURCE_TYPES:
        raise ModelMalformedResponseError(
            "Finalization context contains an unknown Canon source type"
        )
    if not isinstance(observation_payload, Mapping):
        raise ModelMalformedResponseError(
            "Finalization source has no verifiable observation payload"
        )
    if (
        source_type == "lore"
        and not allow_restricted_lore
        and observation_payload.get("sensitivity") != "public"
    ):
        raise ModelMalformedResponseError(
            "Finalization context cannot verify restricted lore access"
        )
    payload: dict[str, Any] = {
        "source_id": source_id,
        "source_type": source_type,
    }
    factual_value_found = False
    for key in _FINALIZATION_SAFE_PAYLOAD_KEYS[source_type]:
        if key not in observation_payload:
            continue
        safe_value = _finalization_json_safe(observation_payload[key])
        payload[key] = safe_value
        factual_value_found = factual_value_found or _finalization_has_factual_value(safe_value)
    if not factual_value_found:
        raise ModelMalformedResponseError(
            "Finalization source has no verifiable observation payload"
        )
    return payload


def _finalization_summary(payload: Mapping[str, Any], source_id: str, source_type: str) -> str:
    for key in ("summary", "statement", "scope_summary", "title", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    core_function = payload.get("core_function")
    if isinstance(core_function, Mapping):
        description = core_function.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    for key in (
        "rules",
        "forbidden_patterns",
        "tags",
        "public_identity",
        "canon_constraints",
        "internal_structure",
        "character_hook",
        "personality",
        "ability",
        "narrative",
        "faction_ids",
        "story_refs",
        "related_incident_ids",
        "related_case_ids",
    ):
        value = payload.get(key)
        if _finalization_has_factual_value(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raise ModelMalformedResponseError(
        "Finalization source has no factual summary derived from its observation"
    )


def _finalization_value_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(
            f"{_finalization_value_text(key)} {_finalization_value_text(item)}"
            for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return " ".join(_finalization_value_text(item) for item in value)
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""


def _finalization_normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _finalization_units(value: str) -> set[str]:
    chinese = [char for char in value if "\u4e00" <= char <= "\u9fff"]
    units = set(re.findall(r"[a-z0-9]+", value))
    units.update(chinese)
    units.update("".join(chinese[index : index + 2]) for index in range(len(chinese) - 1))
    return units


def _finalization_search_score(query: Any, result: Mapping[str, Any]) -> int:
    if not isinstance(query, str):
        query = ""
    query_norm = _finalization_normalize(query)
    result_norm = _finalization_normalize(_finalization_value_text(result))
    return (20 if query_norm and query_norm in result_norm else 0) + len(
        _finalization_units(query_norm) & _finalization_units(result_norm)
    )


def _finalization_candidate_key(
    candidate: _FinalizationSearchCandidate,
) -> tuple[int, str, int, int]:
    return (
        -candidate.score,
        candidate.source_id,
        candidate.group_index,
        candidate.result_index,
    )


def _request_canon_source_ids(
    request: CharacterDesignRequest,
    available_source_ids: set[str],
    known_source_ids: set[str] | frozenset[str],
    known_source_aliases: Mapping[str, Sequence[str]] | None,
) -> frozenset[str]:
    request_text = " ".join(
        (
            request.brief,
            *request.hard_constraints,
            *request.soft_preferences,
            *request.forbidden_elements,
            *request.desired_connections,
        )
    )
    reference_ids: set[str] = set()
    reference_pool = set(known_source_ids) | set(available_source_ids)
    for source_id, start, end in _canon_id_references(request_text, reference_pool):
        if not _is_negated_canon_id_reference(request_text, start, end):
            reference_ids.add(source_id)
    for source_id, start, end in _canon_alias_references(request_text, known_source_aliases):
        if not _is_negated_canon_id_reference(request_text, start, end):
            reference_ids.add(source_id)
    return frozenset(reference_ids & available_source_ids)


def _build_finalization_context(
    request: CharacterDesignRequest,
    *,
    messages: Sequence[ConversationMessage],
    source_ids: set[str] | frozenset[str],
    source_types: Mapping[str, str],
    audits: Sequence[ToolAuditEntry],
    known_source_ids: set[str] | frozenset[str] | None = None,
    known_source_aliases: Mapping[str, Sequence[str]] | None = None,
    known_source_types: Mapping[str, str] | None = None,
    allow_restricted_lore: bool = True,
) -> CharacterFinalizationContext:
    """Build a clean finalization context from the full retrieval trail.

    The caller supplies the full successful retrieval trail and receives only
    the original user message plus a deterministic Evidence Bundle.  This
    implementation owns protocol pairing, direct-get retention,
    search ranking/deduplication, and source-set construction.  Retrieval
    action messages and observations never cross the finalization seam.
    """

    retrieved_ids = set(source_ids)
    typed_retrieved_ids = retrieved_ids & set(source_types)
    if typed_retrieved_ids != retrieved_ids:
        raise ModelMalformedResponseError(
            "Finalization context has a source without a source type"
        )
    if known_source_ids is not None:
        unknown_source_ids = retrieved_ids - set(known_source_ids)
        if unknown_source_ids:
            raise ModelMalformedResponseError(
                "Finalization context contains a source outside known Canon IDs"
            )
    for source_id in retrieved_ids:
        source_type = source_types.get(source_id)
        if not isinstance(source_type, str) or source_type not in _FINALIZATION_ALLOWED_SOURCE_TYPES:
            raise ModelMalformedResponseError(
                "Finalization context contains an unknown Canon source type"
            )
        if known_source_types is not None and known_source_types.get(source_id) != source_type:
            raise ModelMalformedResponseError(
                "Finalization context source type does not match known Canon type"
            )
    if not messages or messages[0].role != "user":
        raise ModelMalformedResponseError(
            "Finalization context must begin with the original user message"
        )

    successful_audits = tuple(
        item for item in audits if item.result_status == "allowed"
    )
    audit_index = 0
    groups: list[tuple[ConversationMessage, tuple[_FinalizationCallRecord, ...]]] = []
    message_index = 1
    while message_index < len(messages):
        assistant = messages[message_index]
        if assistant.role != "assistant" or not isinstance(assistant.content, Mapping):
            raise ModelMalformedResponseError(
                "Finalization context contains an invalid assistant tool-call message"
            )
        raw_calls = assistant.content.get("tool_calls")
        if isinstance(raw_calls, (str, bytes)) or not isinstance(raw_calls, Sequence) or not raw_calls:
            raise ModelMalformedResponseError(
                "Finalization context contains an invalid tool-call group"
            )
        message_index += 1
        records: list[_FinalizationCallRecord] = []
        for call_index, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, Mapping):
                raise ModelMalformedResponseError(
                    "Finalization context contains an invalid tool call"
                )
            call_id = raw_call.get("id")
            tool_name = raw_call.get("name")
            arguments = raw_call.get("arguments", {})
            if (
                not isinstance(call_id, str)
                or not call_id
                or not isinstance(tool_name, str)
                or not tool_name
                or not isinstance(arguments, Mapping)
            ):
                raise ModelMalformedResponseError(
                    "Finalization context contains malformed tool-call metadata"
                )
            if message_index >= len(messages) or messages[message_index].role != "tool":
                raise ModelMalformedResponseError(
                    "Finalization context contains an orphan assistant tool call"
                )
            tool_message = messages[message_index]
            if not isinstance(tool_message.content, Mapping):
                raise ModelMalformedResponseError(
                    "Finalization context contains an invalid tool observation"
                )
            if tool_message.content.get("tool_call_id") != call_id:
                raise ModelMalformedResponseError(
                    "Finalization context contains an orphan tool observation"
                )
            if audit_index >= len(successful_audits):
                raise ModelMalformedResponseError(
                    "Finalization context is missing a successful tool audit"
                )
            audit = successful_audits[audit_index]
            audit_index += 1
            if audit.tool_name != tool_name or dict(audit.arguments) != dict(arguments):
                raise ModelMalformedResponseError(
                    "Finalization context tool audit does not match the history"
                )
            call_source_ids = frozenset(audit.allowed_lore_ids)
            if not call_source_ids <= retrieved_ids:
                raise ModelMalformedResponseError(
                    "Finalization context audit references an unretrieved source"
                )
            if any(item not in source_types for item in call_source_ids):
                raise ModelMalformedResponseError(
                    "Finalization context has an untyped tool observation"
                )
            if tool_name.startswith("get_") and not call_source_ids:
                raise ModelMalformedResponseError(
                    "Successful direct retrieval has no grounded source"
                )
            records.append(
                _FinalizationCallRecord(
                    len(groups),
                    call_index,
                    dict(raw_call),
                    tool_message,
                    audit,
                    call_source_ids,
                    tool_message.content,
                )
            )
            message_index += 1
        groups.append((assistant, tuple(records)))
    if audit_index != len(successful_audits):
        raise ModelMalformedResponseError(
            "Finalization context has a successful tool audit without a history pair"
        )

    direct_source_ids = {
        source_id
        for _assistant, records in groups
        for record in records
        if record.call["name"].startswith("get_")
        for source_id in record.source_ids
    }
    observation_payload_by_source: dict[str, Mapping[str, Any]] = {}
    for _assistant, records in groups:
        for record in records:
            if not record.call["name"].startswith("get_"):
                continue
            raw_result = record.observation.get("result")
            if not isinstance(raw_result, Mapping) or len(record.source_ids) != 1:
                raise ModelMalformedResponseError(
                    "Finalization direct retrieval has no verifiable observation payload"
                )
            direct_source_id = next(iter(record.source_ids))
            observed_source_id = raw_result.get("source_id") or raw_result.get("id")
            if observed_source_id != direct_source_id:
                raise ModelMalformedResponseError(
                    "Finalization direct retrieval observation does not identify its source"
                )
            observed_source_type = raw_result.get("source_type")
            if observed_source_type is not None and observed_source_type != source_types[direct_source_id]:
                raise ModelMalformedResponseError(
                    "Finalization direct retrieval observation has an invalid source type"
                )
            observation_payload_by_source[direct_source_id] = raw_result
    explicit_source_ids = _request_canon_source_ids(
        request,
        retrieved_ids,
        set(known_source_ids or ()) | retrieved_ids,
        known_source_aliases,
    )

    candidates_by_source_id: dict[str, _FinalizationSearchCandidate] = {}
    candidates_by_record: dict[tuple[int, int], list[_FinalizationSearchCandidate]] = {}
    for _assistant, records in groups:
        for record in records:
            tool_name = record.call["name"]
            source_type_options = _FINALIZATION_SEARCH_TO_SOURCE_TYPE.get(tool_name)
            if source_type_options is None:
                continue
            results = record.observation.get("results")
            if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
                raise ModelMalformedResponseError(
                    "Search observation does not contain a valid results array"
                )
            for result_index, result in enumerate(results):
                if not isinstance(result, Mapping):
                    raise ModelMalformedResponseError(
                        "Search observation contains an invalid result"
                    )
                candidate_id = result.get("source_id") or result.get("id")
                if not isinstance(candidate_id, str) or candidate_id not in record.source_ids:
                    continue
                source_type = source_types.get(candidate_id)
                if source_type not in source_type_options:
                    continue
                observed_source_type = result.get("source_type")
                if observed_source_type is not None and observed_source_type != source_type:
                    raise ModelMalformedResponseError(
                        "Finalization search observation has an invalid source type"
                    )
                candidate = _FinalizationSearchCandidate(
                    candidate_id,
                    source_type,
                    record.group_index,
                    record.call_index,
                    result_index,
                    _finalization_search_score(record.call["arguments"].get("query"), result),
                    result,
                )
                candidates_by_record.setdefault(
                    (record.group_index, record.call_index), []
                ).append(candidate)
                previous = candidates_by_source_id.get(candidate_id)
                if previous is None or _finalization_candidate_key(candidate) < _finalization_candidate_key(previous):
                    candidates_by_source_id[candidate_id] = candidate

    missing_explicit_sources = explicit_source_ids - direct_source_ids - set(
        candidates_by_source_id
    )
    if missing_explicit_sources:
        raise ModelMalformedResponseError(
            "An explicitly requested Canon source cannot be reconstructed from its observation"
        )

    selected_search: dict[str, _FinalizationSearchCandidate] = {}
    source_types_seen = sorted(
        {candidate.source_type for candidate in candidates_by_source_id.values()}
    )
    for source_type in source_types_seen:
        candidates = sorted(
            (
                candidate
                for candidate in candidates_by_source_id.values()
                if candidate.source_type == source_type and candidate.source_id not in direct_source_ids
            ),
            key=_finalization_candidate_key,
        )
        forced = [candidate for candidate in candidates if candidate.source_id in explicit_source_ids]
        bounded = [candidate for candidate in candidates if candidate.source_id not in explicit_source_ids][
            :_FINALIZATION_SEARCH_BOUND_PER_SOURCE_TYPE
        ]
        for candidate in (*forced, *bounded):
            selected_search[candidate.source_id] = candidate

    selected_source_ids = direct_source_ids | set(selected_search)
    selected_types = {
        source_id: source_types[source_id]
        for source_id in selected_source_ids
    }
    selected_search_counts: dict[str, int] = {}
    for source_id in selected_search:
        selected_search_counts[selected_search[source_id].source_type] = (
            selected_search_counts.get(selected_search[source_id].source_type, 0) + 1
        )

    for _assistant, records in groups:
        for record in records:
            tool_name = record.call["name"]
            if not tool_name.startswith("get_") and tool_name not in _FINALIZATION_SEARCH_TO_SOURCE_TYPE:
                raise ModelMalformedResponseError(
                    "Finalization context contains an unknown retrieval tool"
                )

    final_source_ids = tuple(sorted(selected_source_ids))
    final_source_types = {
        source_id: selected_types[source_id] for source_id in final_source_ids
    }
    for source_id, candidate in selected_search.items():
        observation_payload_by_source[source_id] = candidate.result
    records_by_key = {
        (record.group_index, record.call_index): record
        for _assistant, records in groups
        for record in records
    }
    provenance_by_source: dict[str, list[dict[str, Any]]] = {
        source_id: [] for source_id in final_source_ids
    }
    for _assistant, records in groups:
        for record in records:
            if not record.call["name"].startswith("get_"):
                continue
            for source_id in sorted(record.source_ids & set(final_source_ids)):
                provenance_by_source[source_id].append(
                    {
                        "kind": "explicit_get",
                        "tool_name": record.call["name"],
                        "round": record.audit.round,
                    }
                )
    for source_id, candidate in selected_search.items():
        record = records_by_key[(candidate.group_index, candidate.call_index)]
        provenance_by_source[source_id].append(
            {
                "kind": "request_explicit"
                if source_id in explicit_source_ids
                else "discovery_search",
                "tool_name": record.call["name"],
                "round": record.audit.round,
                "result_index": candidate.result_index,
            }
        )
    bundle_items: list[Mapping[str, Any]] = []
    for source_id in final_source_ids:
        source_type = final_source_types[source_id]
        payload = _finalization_safe_payload(
            source_id,
            source_type,
            observation_payload_by_source.get(source_id),
            allow_restricted_lore=allow_restricted_lore,
        )
        bundle_items.append(
            {
                "source_id": source_id,
                "source_type": source_type,
                "payload": payload,
                "summary": _finalization_summary(payload, source_id, source_type),
                "provenance": tuple(provenance_by_source[source_id]),
            }
        )
    evidence_bundle = tuple(bundle_items)
    evidence = tuple(
        GroundingEvidence(
            f"canon:{source_id}",
            GroundingEvidenceType.TOOL_LORE,
            item["summary"],
            source_id,
        )
        for source_id, item in zip(final_source_ids, evidence_bundle)
    )
    return CharacterFinalizationContext(
        (messages[0],),
        evidence,
        final_source_ids,
        final_source_types,
        evidence_bundle,
        selected_search_counts,
        len(retrieved_ids - set(final_source_ids)),
    )


@dataclass(frozen=True)
class CharacterGenerationResult:
    draft: CharacterDraft
    sources: tuple[str, ...]
    audit: CharacterGenerationAudit
    design_plan: CharacterDesignPlan | None = None
    skill_shadow: CharacterSkillShadowResult | None = None


class CharacterGenerationAgent:
    """Sibling consumer to NpcConversationAgent for one-shot draft generation."""

    def __init__(self, model: AgentModel, *, resolver: KnowledgeResolver | None = None, story_repository: StoryRepository | None = None, max_tool_rounds: int = 6, authoring_context: CharacterAuthoringKnowledgeContext | None = None, reference_context: Sequence[Mapping[str, Any]] = (), shadow_config: SkillShadowConfig | None = None, retrieval_strategy: str = "model_loop") -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        if shadow_config is not None and not isinstance(shadow_config, SkillShadowConfig):
            raise TypeError("shadow_config must be a SkillShadowConfig or None")
        if retrieval_strategy not in ("model_loop", "deterministic"):
            raise ValueError("retrieval_strategy must be 'model_loop' or 'deterministic'")
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()
        self.tools = CharacterAuthoringToolbox(self.resolver, self.story_repository)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.authoring_context = authoring_context or CharacterAuthoringKnowledgeContext()
        self.reference_context = tuple(dict(item) for item in reference_context)
        self.shadow_config = shadow_config or SkillShadowConfig()
        self.retrieval_strategy = retrieval_strategy

    def generate(
        self,
        request: CharacterDesignRequest | str,
        *,
        use_intent_layer: bool = False,
        skill_shadow_context: SkillValidationContext | None = None,
    ) -> CharacterGenerationResult:
        if isinstance(request, str):
            request = CharacterDesignRequest(request)
        if not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be CharacterDesignRequest or string")
        design_plan = None
        if use_intent_layer:
            design_plan = CharacterDesignPlan.from_text(
                request.brief,
                factions=self.resolver.factions,
            )
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
            (
                design_plan.affiliation_context.to_dict()
                if design_plan is not None and design_plan.affiliation_context is not None
                else None
            ),
        )
        messages: list[ConversationMessage] = [ConversationMessage("user", json.dumps(request.to_dict(), ensure_ascii=False, separators=(",", ":")))]
        source_ids: set[str] = set()
        source_types: dict[str, str] = {}
        audits: list[ToolAuditEntry] = []
        invocations: list[ModelInvocationAudit] = []
        recovery_audit = CharacterDraftRecoveryAudit()
        try:
            finalization_round: int | None = None
            if self.retrieval_strategy == "deterministic":
                finalization_round = self._run_deterministic_retrieval(
                    request=request,
                    authoring=authoring,
                    runtime=runtime,
                    messages=messages,
                    source_ids=source_ids,
                    source_types=source_types,
                    audits=audits,
                    invocations=invocations,
                )
                action_rounds: Sequence[int] = ()
            else:
                action_rounds = range(1, self.max_tool_rounds + 1)
            for round_number in action_rounds:
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
                try:
                    turn = self.model.generate(prompt)
                except ModelMalformedResponseError as error:
                    _classify_generation_failure(
                        error,
                        phase=_ACTION_TERMINATION_PHASE,
                        reason="invalid_termination_signal",
                    )
                    raise
                if turn.invocation is not None:
                    invocations.append(turn.invocation)
                if turn.tool_calls:
                    self._execute_tool_calls(
                        turn.tool_calls,
                        round_number=round_number,
                        messages=messages,
                        source_ids=source_ids,
                        source_types=source_types,
                        audits=audits,
                    )
                    continue
                if not has_terminal_authoring_finalize_signal(turn.text or ""):
                    error = ModelMalformedResponseError(
                        "Authoring action must be a real tool call or end with the exact FINALIZE signal"
                    )
                    _classify_generation_failure(
                        error,
                        phase=_ACTION_TERMINATION_PHASE,
                        reason="invalid_termination_signal",
                    )
                    raise error
                finalization_round = round_number + 1
                break
            if finalization_round is None:
                error = ModelMalformedResponseError(
                    "Authoring action round limit exhausted before exact FINALIZE"
                )
                _classify_generation_failure(
                    error,
                    phase=_ACTION_TERMINATION_PHASE,
                    reason="tool_round_limit_exhausted",
                )
                raise error

            try:
                finalization_context = _build_finalization_context(
                    request,
                    messages=messages,
                    source_ids=source_ids,
                    source_types=source_types,
                    audits=audits,
                    known_source_ids=self._known_canon_source_ids(),
                    known_source_aliases=self._known_canon_source_aliases(),
                    known_source_types=self._known_canon_source_types(),
                    allow_restricted_lore=self.authoring_context.allow_restricted_lore,
                )
            except ModelMalformedResponseError as error:
                _classify_generation_failure(
                    error,
                    phase=_FINALIZATION_CONTEXT_PHASE,
                    reason="context_construction_failed",
                )
                raise
            final_source_ids = set(finalization_context.source_ids)
            final_source_types = dict(finalization_context.source_types)
            finalization_payload = {
                "task": "finalize_character_draft_from_evidence_bundle",
                "request": request.to_dict(),
                "evidence_bundle": [
                    dict(item) for item in finalization_context.evidence_bundle
                ],
                "available_canon_source_ids": list(finalization_context.source_ids),
                "available_canon_source_types": dict(
                    sorted(finalization_context.source_types.items())
                ),
                "reference_context": [dict(item) for item in self.reference_context],
            }
            final_prompt = AgentPrompt(
                CHARACTER_FINALIZATION_SYSTEM_CONTRACT,
                authoring,
                runtime,
                finalization_context.messages,
                (),
                f"character_generation:{request.request_id}",
                finalization_round,
                finalization_context.evidence,
                response_format="character_draft",
                authoring_payload=finalization_payload,
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
                messages=finalization_context.messages,
                evidence=finalization_context.evidence,
                evidence_bundle=finalization_context.evidence_bundle,
                turn_number=finalization_round,
                invocations=invocations,
                source_ids=final_source_ids,
                source_types=final_source_types,
            )
            draft = CharacterDraft.from_mapping(payload)
            self._validate_draft(
                draft,
                request,
                final_source_ids,
                final_source_types,
                known_source_ids=self._known_canon_source_ids(),
                known_source_aliases=self._known_canon_source_aliases(),
            )
            audit = CharacterGenerationAudit(
                request.request_id,
                len(audits),
                tuple(audits),
                finalization_context.source_ids,
                tuple(invocations),
                tuple(item["reference_id"] for item in self.reference_context if isinstance(item.get("reference_id"), str)),
                normalized_fields,
                recovery_audit,
            )
            skill_shadow = self._generate_skill_shadow(
                request=request,
                draft=draft,
                authoring=authoring,
                runtime=runtime,
                skill_shadow_context=skill_shadow_context,
            )
            return CharacterGenerationResult(
                draft,
                finalization_context.source_ids,
                audit,
                design_plan,
                skill_shadow,
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
            recovery_audit = getattr(error, "contract_recovery", None) or recovery_audit
            error.contract_recovery = recovery_audit
            raise
        raise AgentExecutionError("Character generation ended without a draft")

    def _run_deterministic_retrieval(
        self,
        *,
        request: CharacterDesignRequest,
        authoring: CharacterAuthoringView,
        runtime: CharacterGenerationRuntimeView,
        messages: list[ConversationMessage],
        source_ids: set[str],
        source_types: dict[str, str],
        audits: list[ToolAuditEntry],
        invocations: list[ModelInvocationAudit],
    ) -> int:
        plan = build_character_retrieval_plan(
            request,
            known_source_ids=self._known_canon_source_ids(),
            known_source_aliases=self._known_canon_source_aliases(),
            source_types=self._known_canon_source_types(),
        )
        self._execute_tool_calls(
            plan.tool_calls,
            round_number=1,
            messages=messages,
            source_ids=source_ids,
            source_types=source_types,
            audits=audits,
        )
        if not plan.requires_model_planning:
            return 1

        evidence = tuple(
            GroundingEvidence(
                f"canon:{source_id}",
                GroundingEvidenceType.TOOL_LORE,
                source_id,
                source_id if source_type == "lore" else None,
            )
            for source_id, source_type in sorted(source_types.items())
        )
        prompt = AgentPrompt(
            CHARACTER_AUTHORING_ACTION_SYSTEM_CONTRACT,
            authoring,
            runtime,
            tuple(messages),
            self.tools.tool_definitions,
            f"character_generation:{request.request_id}",
            1,
            evidence,
            response_format="character_authoring_action",
        )
        try:
            turn = self.model.generate(prompt)
        except ModelMalformedResponseError as error:
            _classify_generation_failure(
                error,
                phase=_ACTION_TERMINATION_PHASE,
                reason="invalid_termination_signal",
            )
            raise
        if turn.invocation is not None:
            invocations.append(turn.invocation)
        if turn.tool_calls:
            self._execute_tool_calls(
                turn.tool_calls,
                round_number=1,
                messages=messages,
                source_ids=source_ids,
                source_types=source_types,
                audits=audits,
            )
        elif not has_terminal_authoring_finalize_signal(turn.text or ""):
            error = ModelMalformedResponseError(
                "Authoring action must be a real tool call or end with the exact FINALIZE signal"
            )
            _classify_generation_failure(
                error,
                phase=_ACTION_TERMINATION_PHASE,
                reason="invalid_termination_signal",
            )
            raise error
        return 2

    def _execute_tool_calls(
        self,
        calls: Sequence[ToolCall],
        *,
        round_number: int,
        messages: list[ConversationMessage],
        source_ids: set[str],
        source_types: dict[str, str],
        audits: list[ToolAuditEntry],
    ) -> None:
        messages.append(
            ConversationMessage(
                "assistant",
                {
                    "tool_calls": [
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": dict(call.arguments),
                        }
                        for call in calls
                    ]
                },
            )
        )
        for call in calls:
            try:
                execution = self.tools.execute(
                    tool_name=call.name,
                    arguments=call.arguments,
                    context=self.authoring_context,
                    round_number=round_number,
                )
            except AgentToolError:
                audits.append(
                    ToolAuditEntry(
                        round_number,
                        call.name,
                        call.arguments,
                        "rejected",
                        resolver_reason_code=(
                            "tool_not_allowed"
                            if call.name not in self.tools.allowed_tools
                            else "invalid_tool_arguments"
                        ),
                    )
                )
                raise
            audits.append(execution.audit)
            source_ids.update(execution.allowed_source_ids)
            source_types.update(execution.source_types)
            messages.append(
                ConversationMessage(
                    "tool",
                    {"tool_call_id": call.id, **dict(execution.observation)},
                )
            )

    def _generate_skill_shadow(
        self,
        *,
        request: CharacterDesignRequest,
        draft: CharacterDraft,
        authoring: CharacterAuthoringView,
        runtime: CharacterGenerationRuntimeView,
        skill_shadow_context: SkillValidationContext | None,
    ) -> CharacterSkillShadowResult | None:
        """Run the opt-in SkillKit call without entering the legacy pipeline.

        This is deliberately invoked only after a legacy draft has parsed and
        passed its existing validation.  All shadow failures are contained so
        the legacy result remains the authoritative generation outcome.
        """

        if not self.shadow_config.enabled:
            return None

        legacy_ability_concept = draft.ability_concept
        stage = "context"
        candidate: ProtocolSkillKitCandidate | None = None
        report = None
        rendered: str | None = None
        response_compliant = False
        shape_diagnostic: SkillKitShapeDiagnostic | None = None
        audit = SkillShadowAudit(request_id=request.request_id)
        context: SkillValidationContext | None = None
        context_digest: str | None = None
        request_alignment_measured = False
        reference_review_measured = False
        diff: dict[str, Any] = {
            "legacy_ability_concept": legacy_ability_concept,
            "rendered_ability_concept": None,
            "matches": None,
        }
        try:
            if skill_shadow_context is None:
                role_profile = (
                    request.combat_role_profile.to_dict()
                    if request.combat_role_profile is not None
                    else None
                )
                context = SkillValidationContext.from_mapping(
                    {
                        "intent": {
                            "mechanic_requirements": [],
                            "forbidden_mechanic_families": [],
                            "hard_constraint_conflicts": [],
                        },
                        "combat_role_profile": role_profile,
                        "reference_review_context": None,
                    }
                )
            else:
                if not isinstance(skill_shadow_context, SkillValidationContext):
                    raise TypeError(
                        "skill_shadow_context must be a SkillValidationContext or None"
                    )
                context = skill_shadow_context
                request_alignment_measured = True

            context_digest = context.digest
            reference_review_measured = context.reference_review_context is not None
            audit = SkillShadowAudit(
                request_id=request.request_id,
                context_digest=context_digest,
                request_alignment_measured=request_alignment_measured,
                reference_review_measured=reference_review_measured,
            )
            stage = "provider"
            # Keep the shadow request independent of the legacy prose field.
            # The request is the source of truth for this sidecar invocation;
            # no CharacterDraft data is interpolated into its prompt/payload.
            shadow_payload = {
                "draft_id": draft.draft_id,
                "request": request.to_dict(),
                "task": "produce_a_protocol_skill_kit_candidate",
            }
            shadow_prompt = AgentPrompt(
                character_skill_kit_prompt_contract(),
                authoring,
                runtime,
                (
                    ConversationMessage(
                        "user",
                        json.dumps(
                            shadow_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                ),
                (),
                f"character_generation:{request.request_id}:skill_shadow",
                1,
                response_format="character_skill_kit",
                authoring_payload=shadow_payload,
                invocation_purpose="character_skill_shadow",
            )
            shadow_turn = self.model.generate(shadow_prompt)
            audit = self._skill_shadow_audit(
                shadow_turn.invocation,
                request_id=request.request_id,
                context_digest=context_digest,
                request_alignment_measured=request_alignment_measured,
                reference_review_measured=reference_review_measured,
            )

            stage = "json"
            payload = shadow_turn.structured_output
            if payload is None:
                if not isinstance(shadow_turn.text, str):
                    raise ValueError("no structured shadow response")
                try:
                    payload = json.loads(shadow_turn.text)
                except json.JSONDecodeError:
                    raise ValueError("invalid shadow JSON") from None
            if not isinstance(payload, Mapping):
                stage = "shape"
                shape_error = SkillKitShapeError(
                    "TYPE_MISMATCH", "/", "shadow response must be a JSON object"
                )
                shape_error.attach_diagnostic(
                    build_shape_diagnostic(payload, shape_error, extraction_stage="shadow_root_check")
                )
                raise shape_error

            stage = "shape"
            # The provider contract is stricter than the general parser seam:
            # only a direct candidate root is accepted for this invocation.
            if "skill_kit" in payload or "ability_concept" in payload:
                shape_error = SkillKitShapeError(
                    "UNSUPPORTED_VALUE",
                    "/",
                    "shadow response must be a direct ProtocolSkillKitCandidate root",
                )
                shape_error.attach_diagnostic(
                    build_shape_diagnostic(
                        payload,
                        shape_error,
                        extraction_stage="shadow_root_check",
                        wrapper_detected=True,
                    )
                )
                raise shape_error
            parsed = parse_candidate(payload)
            if not isinstance(parsed, ProtocolSkillKitCandidate):
                raise SkillKitShapeError(
                    "UNSUPPORTED_VALUE",
                    "/",
                    "shadow response must be a ProtocolSkillKitCandidate",
                )
            candidate = parsed
            response_compliant = True
            rendered = render_ability_concept(candidate)
            diff = {
                "legacy_ability_concept": legacy_ability_concept,
                "rendered_ability_concept": rendered,
                "matches": legacy_ability_concept == rendered,
            }

            stage = "validation"
            assert context is not None
            report = evaluate(candidate, context)
            return CharacterSkillShadowResult(
                draft_id=draft.draft_id,
                response_compliant=response_compliant,
                candidate=candidate,
                validation_report=report,
                audit=audit,
                shape_diagnostic=shape_diagnostic,
                rendered_ability_concept=rendered,
                legacy_ability_concept=legacy_ability_concept,
                ability_concept_diff=diff,
            )
        except Exception as error:
            # Shadow failures must never alter the successful legacy result or
            # its model invocation audit.  Store only a fixed, sanitized stage
            # marker; provider payloads and exception text stay private.
            error_audit = getattr(error, "audit", None)
            if isinstance(error_audit, ModelInvocationAudit):
                audit = self._skill_shadow_audit(
                    error_audit,
                    request_id=request.request_id,
                    context_digest=context_digest,
                    request_alignment_measured=request_alignment_measured,
                    reference_review_measured=reference_review_measured,
                )
            if isinstance(error, SkillKitShapeError):
                shape_diagnostic = error.diagnostic
            return CharacterSkillShadowResult(
                draft_id=draft.draft_id,
                response_compliant=response_compliant,
                candidate=candidate,
                validation_report=report,
                audit=audit,
                failure_stage=stage,
                shape_diagnostic=shape_diagnostic,
                error_message=self._skill_shadow_error_message(stage),
                rendered_ability_concept=rendered,
                legacy_ability_concept=legacy_ability_concept,
                ability_concept_diff=diff,
            )

    @staticmethod
    def _skill_shadow_audit(
        invocation: ModelInvocationAudit | None,
        *,
        request_id: str | None = None,
        context_digest: str | None = None,
        request_alignment_measured: bool = False,
        reference_review_measured: bool = False,
    ) -> SkillShadowAudit:
        if invocation is None:
            return SkillShadowAudit(
                request_id=request_id,
                context_digest=context_digest,
                request_alignment_measured=request_alignment_measured,
                reference_review_measured=reference_review_measured,
            )
        return SkillShadowAudit(
            provider=invocation.provider,
            model=invocation.model,
            request_id=request_id,
            provider_request_id=invocation.provider_request_id,
            response_contract=invocation.response_contract or "character_skill_kit",
            invocation_purpose="character_skill_shadow",
            session_id=invocation.session_id,
            turn_number=invocation.turn_number,
            outcome=invocation.outcome,
            transport=invocation.transport,
            context_digest=context_digest,
            request_alignment_measured=request_alignment_measured,
            reference_review_measured=reference_review_measured,
        )

    @staticmethod
    def _skill_shadow_error_message(stage: str) -> str:
        return {
            "context": "SkillKit shadow validation context is invalid",
            "provider": "SkillKit shadow provider invocation failed",
            "json": "SkillKit shadow response was not valid JSON",
            "shape": "SkillKit shadow candidate failed the strict shape contract",
            "validation": "SkillKit shadow structural validation failed",
        }.get(stage, "SkillKit shadow invocation failed")

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
            # An explicit API profile is authoritative. The intent layer may infer a
            # narrower profile from prose, but must not erase a typed request contract.
            combat_role_profile=(
                request.combat_role_profile
                if request.combat_role_profile is not None
                else plan.combat_role_profile
            ),
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
        evidence_bundle: Sequence[Mapping[str, Any]],
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

        _recovery_audit = CharacterDraftRecoveryAudit(
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
                "evidence_bundle": [dict(item) for item in evidence_bundle],
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
                error_message=_safe_character_draft_recovery_error_message(error),
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

    def _known_canon_source_ids(self) -> set[str]:
        return {
            "world_rules",
            *self.resolver.factions,
            *self.resolver.lore,
            *self.resolver.characters,
            *self.resolver.projects,
            *self.resolver.cases,
            *self.resolver.incidents,
            *self.story_repository.canon,
        }

    def _known_canon_source_types(self) -> Mapping[str, str]:
        source_types: dict[str, str] = {"world_rules": "world_rules"}
        source_types.update({source_id: "faction" for source_id in self.resolver.factions})
        source_types.update({source_id: "lore" for source_id in self.resolver.lore})
        source_types.update({source_id: "character" for source_id in self.resolver.characters})
        source_types.update({source_id: "story" for source_id in self.story_repository.canon})
        source_types.update({source_id: "case" for source_id in self.resolver.cases})
        source_types.update({source_id: "incident" for source_id in self.resolver.incidents})
        return source_types

    def _known_canon_source_aliases(self) -> Mapping[str, tuple[str, ...]]:
        aliases: dict[str, set[str]] = {}

        def add(source_id: str, *values: Any) -> None:
            bucket = aliases.setdefault(source_id, set())
            for value in values:
                if isinstance(value, str) and len(value.strip()) >= 2:
                    bucket.add(value.strip())

        for source_id, record in self.resolver.factions.items():
            record_aliases = record.get("aliases", ())
            add(
                source_id,
                record.get("name"),
                record.get("short_name"),
                *(record_aliases if isinstance(record_aliases, (list, tuple)) else ()),
            )
        for source_id, record in self.resolver.characters.items():
            name = record.get("name", {})
            add(source_id, name.get("display_name") if isinstance(name, Mapping) else None)
        for source_id, record in self.resolver.lore.items():
            add(source_id, record.get("title"))
        for source_id, record in self.resolver.projects.items():
            add(source_id, record.get("name"), record.get("title"))
        for source_id, record in self.resolver.cases.items():
            add(source_id, record.get("name"))
        for source_id, record in self.resolver.incidents.items():
            add(source_id, record.get("name"))
        for source_id, record in self.story_repository.canon.items():
            add(source_id, record.get("title"), record.get("name"))
        return {source_id: tuple(sorted(values)) for source_id, values in aliases.items()}

    @staticmethod
    def _validate_draft(
        draft: CharacterDraft,
        request: CharacterDesignRequest,
        source_ids: set[str],
        source_types: Mapping[str, str],
        *,
        known_source_ids: set[str] | frozenset[str] | None = None,
        known_source_aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
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
                raise _grounding_failure(
                    f"Draft faction_id is not grounded: {draft.faction_id}",
                    check="faction_id",
                    canon_id=draft.faction_id,
                )
        for entry in draft.canon_basis:
            if entry.source_id not in source_ids:
                raise _grounding_failure(
                    f"Draft cites Canon source not returned this turn: {entry.source_id}",
                    check="canon_basis",
                    canon_id=entry.source_id,
                )
        field_violations = canon_field_grounding_violations(
            draft,
            source_ids if known_source_ids is None else known_source_ids,
            available_source_ids=source_ids,
            known_source_aliases=known_source_aliases,
            reject_unknown_organizations=True,
        )
        if field_violations:
            field, evidence_ids, reason = field_violations[0]
            evidence = f" ({', '.join(evidence_ids)})" if evidence_ids else ""
            raise _grounding_failure(
                f"Draft field {field!r} is not canon-grounded{evidence}: {reason}",
                check=f"field:{field}",
                canon_id=next(
                    (
                        safe_id
                        for safe_id in (_safe_grounding_canon_id(item) for item in evidence_ids)
                        if safe_id is not None
                    ),
                    None,
                ),
            )
        if draft.story_link is not None and (
            draft.story_link.status == "canon_backed"
            and (draft.story_link.target_id not in source_ids or source_types.get(draft.story_link.target_id) not in {"story", "case", "incident"})
        ):
            raise _grounding_failure(
                f"Draft story_link is not grounded: {draft.story_link.target_id}",
                check="story_link",
                canon_id=draft.story_link.target_id,
            )
        for relationship in draft.relationships:
            target_id = relationship.get("target_id")
            if target_id is not None and target_id.startswith(("char_", "faction_")) and target_id not in source_ids:
                raise _grounding_failure(
                    f"Draft relationship is not grounded: {target_id}",
                    check="relationships",
                    canon_id=target_id,
                )
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
        return _age_bounds_from_text(text)


def _age_bounds_from_text(text: str) -> tuple[int, int] | None:
    """Extract an explicit numeric age range from the authoring request."""

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

    @staticmethod
    def _grounded_identity_fields(
        context: Mapping[str, Any] | None,
        profile: CombatRoleProfile,
    ) -> dict[str, str] | None:
        if not isinstance(context, Mapping):
            return None
        roles = tuple(
            item.strip()
            for item in context.get("typical_roles", ())
            if isinstance(item, str) and item.strip()
        )
        terms = tuple(
            item.strip()
            for item in context.get("semantic_terms", ())
            if isinstance(item, str) and item.strip()
        )
        if not roles or not terms:
            return None
        name = str(context.get("name", "相关协作体系"))
        anchor = terms[0]
        divisions = tuple(
            item.strip()
            for item in context.get("division_names", ())
            if isinstance(item, str) and item.strip()
        )
        division = divisions[0] if divisions else anchor
        summary = str(context.get("summary", "相关公共事务"))
        combat_role = profile.primary_role or "support"
        return {
            "occupation": roles[0],
            "social_role": f"参与{name}的{division}相关现场协调与信息联络",
            "design_pitch": f"把{anchor}相关职责转化为{combat_role}型行动表达。",
            "background": f"她在{summary}相关工作中逐渐形成了谨慎处理复杂关系的习惯。",
            "story_hook": f"在{anchor}相关事件中，她需要在专业分工与现场协作之间作出选择。",
            "knowledge_scope": "仅接触与所属组织职责直接相关的公开流程和被明确交付的现场事项。",
            "open_question": f"是否让她参与{division}后续的联合演练或复盘？",
        }

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
        if prompt.response_format == "character_authoring_action" and "get_world_rules" not in called:
            return ModelTurn(tool_calls=(ToolCall("world", "get_world_rules", {}),))
        if prompt.response_format == "character_authoring_action" and "search_factions" not in called:
            return ModelTurn(tool_calls=(ToolCall("faction", "search_factions", {"query": brief, "limit": 5}),))
        if prompt.response_format == "character_authoring_action" and "search_lore" not in called:
            return ModelTurn(tool_calls=(ToolCall("lore", "search_lore", {"query": brief, "limit": 5}),))
        if (
            prompt.response_format == "character_authoring_action"
            and ("事件" in brief or "事故" in brief or "南站" in brief or "南栈" in brief)
            and "search_story_context" not in called
        ):
            return ModelTurn(tool_calls=(ToolCall("story", "search_story_context", {"query": brief, "limit": 5}),))
        if prompt.response_format == "character_authoring_action":
            return ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL)
        selected_faction = None
        selected_story = None
        lore_sources: list[str] = []
        faction_candidates: list[tuple[str, str]] = []
        faction_contexts: dict[str, Mapping[str, Any]] = {}
        if isinstance(prompt.authoring_payload, Mapping):
            bundle = prompt.authoring_payload.get("evidence_bundle", ())
            if isinstance(bundle, Sequence) and not isinstance(bundle, (str, bytes)):
                for evidence in bundle:
                    if not isinstance(evidence, Mapping):
                        continue
                    source_id = evidence.get("source_id")
                    source_type = evidence.get("source_type")
                    payload = evidence.get("payload")
                    if not isinstance(source_id, str) or not isinstance(source_type, str):
                        continue
                    if not isinstance(payload, Mapping):
                        payload = {}
                    if source_type == "faction":
                        faction_contexts[source_id] = CharacterAffiliationContext.from_record(
                            source_id,
                            payload,
                        ).to_dict()
                        faction_candidates.append(
                            (
                                source_id,
                                str(payload.get("name", ""))
                                + str(payload.get("summary", "")),
                            )
                        )
                    if source_type in {"story", "case", "incident"} and selected_story is None:
                        selected_story = source_id
                    if source_type == "lore":
                        lore_sources.append(source_id)
        for message in prompt.messages:
            if message.role != "tool" or not isinstance(message.content, Mapping):
                continue
            for key in ("result",):
                item = message.content.get(key)
                if isinstance(item, Mapping):
                    if item.get("source_type") == "faction" and item.get("id"):
                        source_id = str(item["id"])
                        faction_contexts[source_id] = CharacterAffiliationContext.from_record(
                            source_id,
                            item,
                        ).to_dict()
                        faction_candidates.append((str(item.get("id")), str(item.get("name", "")) + str(item.get("summary", ""))))
                    if item.get("source_type") in {"story", "case", "incident"} and selected_story is None:
                        selected_story = item.get("id")
                    if item.get("source_type") == "lore" and item.get("id"):
                        lore_sources.append(item["id"])
            for item in message.content.get("results", []):
                if isinstance(item, Mapping):
                    if item.get("source_type") == "faction" and item.get("id"):
                        source_id = str(item["id"])
                        faction_contexts[source_id] = CharacterAffiliationContext.from_record(
                            source_id,
                            item,
                        ).to_dict()
                        faction_candidates.append((str(item.get("id")), str(item.get("name", "")) + str(item.get("summary", ""))))
                    if item.get("source_type") in {"story", "case", "incident"} and selected_story is None:
                        selected_story = item.get("id")
                    if item.get("source_type") == "lore" and item.get("id"):
                        lore_sources.append(item["id"])
        requested_faction = (
            prompt.runtime.affiliation_context.get("faction_id")
            if isinstance(prompt.runtime.affiliation_context, Mapping)
            else None
        )
        if isinstance(requested_faction, str) and any(
            candidate[0] == requested_faction for candidate in faction_candidates
        ):
            selected_faction = requested_faction
        if selected_faction is None and faction_candidates:
            selected_faction = faction_candidates[0][0]
        requested_profile = prompt.runtime.combat_role_profile
        profile = requested_profile if requested_profile is not None else CombatRoleProfile(primary_role="support")
        grounded_identity = self._grounded_identity_fields(
            faction_contexts.get(selected_faction or "", prompt.runtime.affiliation_context),
            profile,
        )
        age = 23 if "23" in brief else 22
        age_range = "20-25"
        age_bounds = _age_bounds_from_text(brief)
        if age_bounds is not None:
            age = (age_bounds[0] + age_bounds[1]) // 2
            age_range = f"{age_bounds[0]}-{age_bounds[1]}"
        basis = [{"source_id": "world_rules", "supports": ["world_rules"]}]
        if selected_faction:
            basis.append({"source_id": selected_faction, "supports": ["faction_id", "occupation", "social_role"]})
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
            "age_range": age_range,
            "gender": "女性",
            "faction_id": selected_faction,
            "occupation": grounded_identity["occupation"] if grounded_identity else "临洲大学学生助理",
            "social_role": grounded_identity["social_role"] if grounded_identity else "校园活动与社区安全志愿协调者",
            "combat_role_profile": profile.to_dict(),
            "design_pitch": grounded_identity["design_pitch"] if grounded_identity else "一名把现场秩序与他人安全放在首位的年轻辅助型角色。",
            "personality": ["冷静", "克制", "先观察后行动"],
            "background": grounded_identity["background"] if grounded_identity else "她在校园与社区活动中逐渐形成了谨慎处理复杂关系的习惯。",
            "story_hook": grounded_identity["story_hook"] if grounded_identity else "在既有事件的后续协调中提供非核心的现场协助，并面对个人选择与公共责任的拉扯。",
            "relationships": [],
            "ability_concept": "能够在自己明确标记过的安全范围内短暂稳定注意与行动节奏；作用有限，不能替代训练或专业处置。",
            "knowledge_scope": grounded_identity["knowledge_scope"] if grounded_identity else "仅凭学生与志愿协作者身份接触公开信息和被明确交付的现场事项。",
            "canon_basis": basis,
            "new_design_elements": [
                "new_design:occupation: 具体职业表达为新设计。",
                "new_design:social_role: 具体社会角色表达为新设计。",
                "new_design:design_pitch: 高层角色概念为新设计。",
                "new_design:personality: 性格表达为新设计。",
                "new_design:background: 个人经历为新设计。",
                "new_design:story_hook: 个人叙事钩子为新设计。",
                "new_design:ability_concept: 能力表现为新设计。",
                "new_design:knowledge_scope: 具体知识边界表达为新设计。",
                "姓名、性格、个人习惯与高层能力表现均为新角色设计。",
            ],
            "open_questions": [grounded_identity["open_question"] if grounded_identity else "是否将她与后续校园活动支线建立更长期的个人关系？"],
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
    "CharacterSkillShadowResult",
    "CharacterGenerationRuntimeView",
    "CharacterAuthoringView",
    "CharacterDraftContractInspection",
    "DeterministicCharacterGenerationModel",
    "SkillShadowConfig",
    "SkillShadowAudit",
    "StoryLink",
    "age_information_preservation_violations",
    "age_must_remain_unspecified",
    "school_history_must_remain_unspecified",
    "inspect_character_draft_payload",
]
