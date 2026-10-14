"""Typed, immutable, provider-independent planning context v2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any

from combat_semantics import CombatRoleProfile

from ..intent import CharacterDesignIntent
from ..planner.character_plan import CharacterDesignPlan
from ..planner.character_plan_v2 import CharacterDesignPlanV2

CHARACTER_PLANNING_CONTEXT_V2_SCHEMA = "character-planning-context/v2"


class ContextAuthority(str, Enum):
    USER_REQUIREMENT = "USER_REQUIREMENT"
    PROJECT_CANON = "PROJECT_CANON"
    PROJECT_ROSTER = "PROJECT_ROSTER"
    DETERMINISTIC_SEMANTICS = "DETERMINISTIC_SEMANTICS"
    REFERENCE_PRECEDENT = "REFERENCE_PRECEDENT"
    GENERATED_DRAFT = "GENERATED_DRAFT"
    EXPERIMENTAL = "EXPERIMENTAL"


class ContextGapCode(str, Enum):
    CANON_CONTEXT_UNAVAILABLE = "CANON_CONTEXT_UNAVAILABLE"
    ROSTER_CONTEXT_UNAVAILABLE = "ROSTER_CONTEXT_UNAVAILABLE"
    HUMAN_ACCEPTANCE_STATE_UNAVAILABLE = "HUMAN_ACCEPTANCE_STATE_UNAVAILABLE"
    # Compatibility alias for the Phase 2 diagnostic name.
    ROSTER_GENERATED_ACCEPTANCE_UNAVAILABLE = "HUMAN_ACCEPTANCE_STATE_UNAVAILABLE"
    ROSTER_MEMBERSHIP_PARTIALLY_KNOWN = "ROSTER_MEMBERSHIP_PARTIALLY_KNOWN"
    RELATIONSHIP_CONTEXT_UNAVAILABLE = "RELATIONSHIP_CONTEXT_UNAVAILABLE"
    RELATIONSHIP_COVERAGE_INCOMPLETE = "RELATIONSHIP_COVERAGE_INCOMPLETE"
    RELATIONSHIP_VOCABULARY_UNAVAILABLE = "RELATIONSHIP_VOCABULARY_UNAVAILABLE"
    STORY_CONTEXT_UNAVAILABLE = "STORY_CONTEXT_UNAVAILABLE"
    REFERENCE_CONTEXT_UNAVAILABLE = "REFERENCE_CONTEXT_UNAVAILABLE"
    ROSTER_METADATA_SPARSE = "ROSTER_METADATA_SPARSE"
    PRODUCT_POSITIONING_UNAVAILABLE = "PRODUCT_POSITIONING_UNAVAILABLE"
    ROSTER_COMBAT_COVERAGE_INCOMPLETE = "ROSTER_COMBAT_COVERAGE_INCOMPLETE"
    ROSTER_STORY_STATUS_UNAVAILABLE = "ROSTER_STORY_STATUS_UNAVAILABLE"


class CoverageLevel(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    SPARSE = "SPARSE"
    ABSENT = "ABSENT"


class RosterSourceClass(str, Enum):
    CANON_PROJECT_CHARACTER = "CANON_PROJECT_CHARACTER"
    ACCEPTED_PROJECT_CHARACTER = "ACCEPTED_PROJECT_CHARACTER"
    GENERATED_DRAFT = "GENERATED_DRAFT"
    REFERENCE_CHARACTER = "REFERENCE_CHARACTER"
    TEST_FIXTURE = "TEST_FIXTURE"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"
    UNKNOWN = "UNKNOWN"


class RosterMembershipStatus(str, Enum):
    IN_PROJECT_ROSTER = "IN_PROJECT_ROSTER"
    NOT_PROJECT_ROSTER = "NOT_PROJECT_ROSTER"
    UNKNOWN = "UNKNOWN"


class WorldCharacterStatus(str, Enum):
    PROJECT_WORLD_CHARACTER = "PROJECT_WORLD_CHARACTER"
    PROJECT_ROSTER_CHARACTER = "PROJECT_ROSTER_CHARACTER"
    UNKNOWN = "UNKNOWN"


class AcceptanceState(str, Enum):
    ACCEPTED = "ACCEPTED"
    NOT_ACCEPTED = "NOT_ACCEPTED"
    ACCEPTANCE_STATE_UNKNOWN = "ACCEPTANCE_STATE_UNKNOWN"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(value: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        item = _text(item, name)
        if item not in result:
            result.append(item)
    return tuple(result)


def _enum(enum_type: type[Enum], value: object, name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} has an invalid value: {value!r}") from exc


def _serialize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serialize(value[key]) for key in sorted(value, key=str)}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize(value.to_dict())
    return value


@dataclass(frozen=True)
class ContextSource:
    source_id: str
    source_type: str
    authority: ContextAuthority
    retrieval_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        object.__setattr__(self, "source_type", _text(self.source_type, "source_type"))
        object.__setattr__(self, "authority", _enum(ContextAuthority, self.authority, "authority"))
        object.__setattr__(self, "retrieval_reason", _text(self.retrieval_reason, "retrieval_reason"))


@dataclass(frozen=True)
class CanonContextItem:
    entity_id: str
    entity_type: str
    display_name: str | None
    summary: str | None
    source: ContextSource


@dataclass(frozen=True)
class RosterCharacterContext:
    character_id: str
    display_name: str | None
    origin: str
    source: ContextSource
    source_class: RosterSourceClass = RosterSourceClass.UNKNOWN
    membership_status: RosterMembershipStatus = RosterMembershipStatus.UNKNOWN
    world_status: WorldCharacterStatus = WorldCharacterStatus.UNKNOWN
    acceptance_state: AcceptanceState = AcceptanceState.ACCEPTANCE_STATE_UNKNOWN
    faction_id: str | None = None
    combat_role_profile: CombatRoleProfile | None = None
    combat_source: ContextSource | None = None
    personality: tuple[str, ...] = ()
    narrative: tuple[str, ...] = ()
    visual: tuple[str, ...] = ()
    product: tuple[str, ...] = ()
    release: tuple[str, ...] = ()
    story_status: tuple[str, ...] = ()
    signature: "RosterDesignSignatureV2 | None" = None


@dataclass(frozen=True)
class RosterDesignSignatureV2:
    character_id: str
    source_class: RosterSourceClass
    membership_status: RosterMembershipStatus
    faction_id: str | None = None
    combat_roles: tuple[str, ...] = ()
    personality: tuple[str, ...] = ()
    narrative: tuple[str, ...] = ()
    visual: tuple[str, ...] = ()
    relationship_positions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RosterOverlapEvidence:
    left_character_id: str
    right_character_id: str
    overlap_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class RelationshipVocabularyEntry:
    relation_id: str
    directionality: str
    inverse_relation_id: str | None
    symmetric: bool | None
    applicable_entity_types: tuple[tuple[str, str], ...]
    production_status: str
    source: ContextSource


@dataclass(frozen=True)
class RelationshipContextItem:
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    authority: ContextAuthority
    description: str | None = None


@dataclass(frozen=True)
class CombatPlanningContext:
    requested_role_profile: CombatRoleProfile | None = None
    occupied_role_profiles: tuple[CombatRoleProfile, ...] = ()
    semantic_metadata: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferencePrecedentContext:
    reference_id: str
    display_name: str | None
    game_id: str | None
    roles: tuple[str, ...]
    narrative: tuple[str, ...]
    visual: tuple[str, ...]
    source: ContextSource
    source_ids: tuple[str, ...] = ()
    selector_metadata: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryContextItem:
    story_id: str
    title: str | None
    facts: tuple[str, ...]
    source: ContextSource


@dataclass(frozen=True)
class DraftContextItem:
    draft_id: str
    display_name: str | None
    source: ContextSource


@dataclass(frozen=True)
class ContextGap:
    code: ContextGapCode
    domain: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _enum(ContextGapCode, self.code, "code"))
        object.__setattr__(self, "domain", _text(self.domain, "domain"))
        object.__setattr__(self, "detail", _text(self.detail, "detail"))


@dataclass(frozen=True)
class ContextAssemblyLimits:
    max_canon_items: int = 16
    max_roster_items: int = 32
    max_relationships: int = 64
    max_references: int = 16
    max_story_items: int = 16
    max_drafts: int = 16

    def __post_init__(self) -> None:
        for name in ("max_canon_items", "max_roster_items", "max_relationships", "max_references", "max_story_items", "max_drafts"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class RosterMetadataCoverage:
    identity: CoverageLevel = CoverageLevel.ABSENT
    membership: CoverageLevel = CoverageLevel.ABSENT
    faction: CoverageLevel = CoverageLevel.ABSENT
    combat: CoverageLevel = CoverageLevel.ABSENT
    relationships: CoverageLevel = CoverageLevel.ABSENT
    personality: CoverageLevel = CoverageLevel.ABSENT
    narrative: CoverageLevel = CoverageLevel.ABSENT
    visual: CoverageLevel = CoverageLevel.ABSENT
    product: CoverageLevel = CoverageLevel.ABSENT
    release: CoverageLevel = CoverageLevel.ABSENT
    story_status: CoverageLevel = CoverageLevel.ABSENT


@dataclass(frozen=True)
class CharacterPlanningContextV2:
    """Read-only assembly input for a future planner; never a generation result."""

    schema_version: str
    snapshot_id: str
    intent: CharacterDesignIntent
    plan_v1: CharacterDesignPlan
    plan_v2: CharacterDesignPlanV2
    canon: tuple[CanonContextItem, ...] = ()
    roster: tuple[RosterCharacterContext, ...] = ()
    drafts: tuple[DraftContextItem, ...] = ()
    canon_relationships: tuple[RelationshipContextItem, ...] = ()
    reference_relationships: tuple[RelationshipContextItem, ...] = ()
    draft_relationships: tuple[RelationshipContextItem, ...] = ()
    evaluation_relationships: tuple[RelationshipContextItem, ...] = ()
    requested_relationships: tuple[str, ...] = ()
    unresolved_relationships: tuple[str, ...] = ()
    relationship_vocabulary: tuple[RelationshipVocabularyEntry, ...] = ()
    combat: CombatPlanningContext = field(default_factory=CombatPlanningContext)
    references: tuple[ReferencePrecedentContext, ...] = ()
    story: tuple[StoryContextItem, ...] = ()
    gaps: tuple[ContextGap, ...] = ()
    roster_coverage: RosterMetadataCoverage = field(default_factory=RosterMetadataCoverage)
    roster_signatures: tuple[RosterDesignSignatureV2, ...] = ()
    overlap_evidence: tuple[RosterOverlapEvidence, ...] = ()
    limits: ContextAssemblyLimits = field(default_factory=ContextAssemblyLimits)

    def __post_init__(self) -> None:
        if self.schema_version != CHARACTER_PLANNING_CONTEXT_V2_SCHEMA:
            raise ValueError(f"unsupported schema_version: {self.schema_version!r}")
        object.__setattr__(self, "snapshot_id", _text(self.snapshot_id, "snapshot_id"))
        if not isinstance(self.intent, CharacterDesignIntent):
            raise TypeError("intent must be a CharacterDesignIntent")
        if not isinstance(self.plan_v1, CharacterDesignPlan):
            raise TypeError("plan_v1 must be a CharacterDesignPlan")
        if not isinstance(self.plan_v2, CharacterDesignPlanV2):
            raise TypeError("plan_v2 must be a CharacterDesignPlanV2")
        for name in (
            "canon", "roster", "drafts", "canon_relationships", "reference_relationships",
            "draft_relationships", "evaluation_relationships", "references", "story", "gaps",
            "roster_signatures", "overlap_evidence",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "requested_relationships", _strings(self.requested_relationships, "requested_relationships"))
        object.__setattr__(self, "unresolved_relationships", _strings(self.unresolved_relationships, "unresolved_relationships"))
        object.__setattr__(self, "relationship_vocabulary", tuple(self.relationship_vocabulary))
        if not isinstance(self.combat, CombatPlanningContext):
            raise TypeError("combat must be a CombatPlanningContext")
        if not isinstance(self.roster_coverage, RosterMetadataCoverage):
            raise TypeError("roster_coverage must be a RosterMetadataCoverage")
        if not isinstance(self.limits, ContextAssemblyLimits):
            raise TypeError("limits must be a ContextAssemblyLimits")

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)  # type: ignore[return-value]
