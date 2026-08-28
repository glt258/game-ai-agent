"""Fair, deterministic projection of public generation context into IR enums."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from character_skill.contract import (
    ABILITY_MODES,
    CENTRALITIES,
    FEEDBACK_EVENTS,
    FEEDBACK_OPERATIONS,
    SUBJECT_KINDS,
    TRIGGER_EVENTS,
)
from combat_semantics import CANONICAL_COMBAT_ROLES

from ..planner import CharacterDesignPlan

PROJECTION_SOURCES = frozenset(
    {"REQUEST_ALLOWED", "PLAN_ALLOWED", "GLOBAL_STRUCTURAL", "VOCABULARY_REQUIRED"}
)
CONTEXT_CONTRACT_PROFILES = frozenset({"frozen_h3", "aligned_v1"})
SEMANTIC_ACTORS = tuple(sorted(SUBJECT_KINDS - {"summon"}))
SEMANTIC_INTENTS = ("enable_ally",)
GLOBAL_STRUCTURAL_TRIGGER_EVENTS = (
    "ability_invoked",
    "action_completed",
    "damage_received",
    "feedback_received",
    "healing_received",
)


class ProjectionError(ValueError):
    """A safe, bounded projection failure."""

    def __init__(self, code: str, domain: str, detail: str) -> None:
        self.code = code
        self.domain = domain
        self.detail = detail
        super().__init__(f"{code} at {domain}: {detail}")


def _clean_values(values: Iterable[str], domain: str) -> tuple[str, ...]:
    result = tuple(sorted({value.strip() for value in values if isinstance(value, str) and value.strip()}))
    if not result:
        raise ProjectionError("PROJECTION_EMPTY_DOMAIN", domain, "projection must contain a value")
    return result


@dataclass(frozen=True)
class HybridGenerationContext:
    """Public request and plan facts available to a future model-facing call."""

    brief: str
    plan: CharacterDesignPlan | None = None
    case_id: str = "case_13"
    contract_profile: str = "frozen_h3"
    allowed_actors: tuple[str, ...] | None = None
    allowed_trigger_events: tuple[str, ...] | None = None
    allowed_feedback_events: tuple[str, ...] | None = None
    allowed_feedback_relations: tuple[str, ...] | None = None
    allowed_modes: tuple[str, ...] | None = None
    allowed_roles: tuple[str, ...] | None = None
    allowed_centralities: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.brief, str) or not self.brief.strip():
            raise ValueError("brief must be a non-empty string")
        object.__setattr__(self, "brief", self.brief.strip())
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        object.__setattr__(self, "case_id", self.case_id.strip())
        if self.contract_profile not in CONTEXT_CONTRACT_PROFILES:
            raise ValueError("unsupported contract profile")
        if self.plan is not None and not isinstance(self.plan, CharacterDesignPlan):
            raise TypeError("plan must be CharacterDesignPlan or None")
        for name in (
            "allowed_actors",
            "allowed_trigger_events",
            "allowed_feedback_events",
            "allowed_feedback_relations",
            "allowed_modes",
            "allowed_roles",
            "allowed_centralities",
        ):
            values = getattr(self, name)
            if values is not None:
                object.__setattr__(self, name, _clean_values(values, name))


@dataclass(frozen=True)
class EnumDomainProjection:
    """One projected semantic enum domain and its public source category."""

    domain: str
    values: tuple[str, ...]
    source: str

    def __post_init__(self) -> None:
        if self.source not in PROJECTION_SOURCES:
            raise ValueError("unsupported projection source")
        if not self.values:
            raise ValueError("projection values must not be empty")
        if tuple(sorted(set(self.values))) != self.values:
            raise ValueError("projection values must be sorted and unique")

    def to_mapping(self) -> dict[str, object]:
        return {"domain": self.domain, "values": list(self.values), "source": self.source}


@dataclass(frozen=True)
class SemanticEnumProjection:
    """All semantic domains visible to the model-facing contract."""

    domains: tuple[EnumDomainProjection, ...]

    def __post_init__(self) -> None:
        names = tuple(item.domain for item in self.domains)
        if len(names) != len(set(names)):
            raise ValueError("projection domains must be unique")

    def domain(self, name: str) -> EnumDomainProjection:
        for item in self.domains:
            if item.domain == name:
                return item
        raise KeyError(name)

    def to_mapping(self) -> dict[str, object]:
        return {item.domain: item.to_mapping() for item in self.domains}


def _domain(
    name: str,
    requested: tuple[str, ...] | None,
    allowed: Iterable[str],
    *,
    source_if_default: str = "GLOBAL_STRUCTURAL",
    default_values: Iterable[str] | None = None,
) -> EnumDomainProjection:
    legal = frozenset(allowed)
    values = requested if requested is not None else tuple(default_values or sorted(legal))
    cleaned = _clean_values(values, name)
    if not set(cleaned) <= legal:
        raise ProjectionError("PROJECTION_VALUE_INVALID", name, "value is outside the semantic vocabulary")
    return EnumDomainProjection(name, cleaned, "REQUEST_ALLOWED" if requested is not None else source_if_default)


def project_semantic_enums(context: HybridGenerationContext) -> SemanticEnumProjection:
    """Project only public request/plan facts plus legal structural vocabulary."""

    if not isinstance(context, HybridGenerationContext):
        raise TypeError("context must be HybridGenerationContext")
    role_values = context.allowed_roles
    role_source = "GLOBAL_STRUCTURAL"
    if role_values is None and context.plan is not None:
        primary = context.plan.combat_role_profile.primary_role
        role_values = (primary,)
        role_source = "PLAN_ALLOWED"
    domains = (
        _domain("actor", context.allowed_actors, SEMANTIC_ACTORS),
        _domain(
            "trigger_event",
            context.allowed_trigger_events,
            TRIGGER_EVENTS,
            default_values=GLOBAL_STRUCTURAL_TRIGGER_EVENTS,
        ),
        _domain("feedback_event", context.allowed_feedback_events, FEEDBACK_EVENTS),
        _domain("feedback_relation", context.allowed_feedback_relations, FEEDBACK_OPERATIONS),
        _domain("mode", context.allowed_modes, ABILITY_MODES),
        EnumDomainProjection(
            "role",
            _clean_values(role_values or tuple(sorted(CANONICAL_COMBAT_ROLES)), "role"),
            "REQUEST_ALLOWED" if context.allowed_roles is not None else role_source,
        ),
        _domain("centrality", context.allowed_centralities, CENTRALITIES),
        EnumDomainProjection("intent", SEMANTIC_INTENTS, "VOCABULARY_REQUIRED"),
    )
    return SemanticEnumProjection(domains)


__all__ = [
    "EnumDomainProjection",
    "CONTEXT_CONTRACT_PROFILES",
    "HybridGenerationContext",
    "PROJECTION_SOURCES",
    "ProjectionError",
    "SEMANTIC_ACTORS",
    "SEMANTIC_INTENTS",
    "GLOBAL_STRUCTURAL_TRIGGER_EVENTS",
    "SemanticEnumProjection",
    "project_semantic_enums",
]
