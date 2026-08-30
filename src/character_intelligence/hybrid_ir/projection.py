"""Fair, deterministic projection of public generation context into IR enums."""

from __future__ import annotations

import hashlib
import json
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
from character_skill.context import RESPONSE_EFFECT_FAMILIES
from combat_semantics import CANONICAL_COMBAT_ROLES

from ..planner import CharacterDesignPlan

PROJECTION_SOURCES = frozenset(
    {
        "REQUEST_ALLOWED",
        "CASE_REQUIREMENT",
        "PLAN_ALLOWED",
        "GLOBAL_STRUCTURAL",
        "VOCABULARY_REQUIRED",
    }
)
CONTEXT_CONTRACT_PROFILES = frozenset({"frozen_h3", "aligned_v1", "generalization_v1", "generalization_v2"})
CONTEXT_PROJECTION_VERSION_HISTORICAL = "hybrid-semantic-context-projection/0.2.0"
CONTEXT_PROJECTION_VERSION = "hybrid-semantic-context-projection/0.2.1"
CONTEXT_PROJECTION_VERSION_V2_HISTORICAL = "hybrid-semantic-context-projection/0.3.0"
CONTEXT_PROJECTION_VERSION_V2 = "hybrid-semantic-context-projection/0.3.1"
SEMANTIC_ACTORS = tuple(sorted(SUBJECT_KINDS - {"summon"}))
# Keep the structural enum vocabulary compact. Generalization profiles expose
# the small generic vocabulary needed by distinct role families.
SEMANTIC_INTENTS = ("enable_ally",)
GENERALIZATION_SEMANTIC_INTENTS = (
    "control_enemy",
    "deal_damage",
    "enable_ally",
    "mitigate_ally",
)
GENERALIZATION_V2_SEMANTIC_INTENTS = (
    "control_enemy",
    "deal_damage",
    "deal_follow_up_damage",
    "enable_ally",
    "mitigate_ally",
    "protect_ally",
)
GLOBAL_STRUCTURAL_TRIGGER_EVENTS = (
    "ability_invoked",
    "action_completed",
    "damage_received",
    "feedback_received",
    "healing_received",
)
STRUCTURAL_FEEDBACK_TRIGGER_EVENT = "feedback_received"


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
    allowed_trigger_subjects: tuple[str, ...] | None = None
    allowed_effect_subjects: tuple[str, ...] | None = None
    allowed_trigger_events: tuple[str, ...] | None = None
    allowed_feedback_events: tuple[str, ...] | None = None
    allowed_feedback_relations: tuple[str, ...] | None = None
    allowed_modes: tuple[str, ...] | None = None
    allowed_response_effect_families: tuple[str, ...] | None = None
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
            "allowed_trigger_subjects",
            "allowed_effect_subjects",
            "allowed_trigger_events",
            "allowed_feedback_events",
            "allowed_feedback_relations",
            "allowed_modes",
            "allowed_response_effect_families",
            "allowed_roles",
            "allowed_centralities",
        ):
            values = getattr(self, name)
            if values is not None:
                cleaned = _clean_values(values, name)
                if name == "allowed_response_effect_families" and not set(cleaned) <= RESPONSE_EFFECT_FAMILIES:
                    raise ValueError("unsupported response effect family")
                if name in {"allowed_trigger_subjects", "allowed_effect_subjects"} and not set(cleaned) <= set(SEMANTIC_ACTORS):
                    raise ValueError("unsupported semantic subject")
                object.__setattr__(self, name, cleaned)

    @property
    def context_projection_version(self) -> str:
        return (
            CONTEXT_PROJECTION_VERSION_V2
            if self.contract_profile == "generalization_v2"
            else CONTEXT_PROJECTION_VERSION
        )

    @property
    def context_projection_digest(self) -> str:
        return context_projection_digest(self)


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
    source_if_requested: str = "REQUEST_ALLOWED",
    default_values: Iterable[str] | None = None,
) -> EnumDomainProjection:
    legal = frozenset(allowed)
    values = requested if requested is not None else tuple(default_values or sorted(legal))
    cleaned = _clean_values(values, name)
    if not set(cleaned) <= legal:
        raise ProjectionError("PROJECTION_VALUE_INVALID", name, "value is outside the semantic vocabulary")
    return EnumDomainProjection(
        name,
        cleaned,
        source_if_requested if requested is not None else source_if_default,
    )


def project_semantic_enums(context: HybridGenerationContext) -> SemanticEnumProjection:
    """Project only public request/plan facts plus legal structural vocabulary."""

    if not isinstance(context, HybridGenerationContext):
        raise TypeError("context must be HybridGenerationContext")
    role_values = context.allowed_roles
    role_source = "GLOBAL_STRUCTURAL"
    requested_source = "CASE_REQUIREMENT" if context.contract_profile == "aligned_v1" else "REQUEST_ALLOWED"
    if role_values is None and context.plan is not None:
        primary = context.plan.combat_role_profile.primary_role
        role_values = (primary,)
        role_source = "PLAN_ALLOWED"
    trigger_values = context.allowed_trigger_events
    if trigger_values is not None:
        # The response trigger is a required structural part of every
        # SemanticFeedback object.  Keep its canonical event visible even
        # when the case narrows the primary mechanic trigger events.
        trigger_values = tuple((*trigger_values, STRUCTURAL_FEEDBACK_TRIGGER_EVENT))
    domains = [
        _domain(
            "actor",
            context.allowed_actors,
            SEMANTIC_ACTORS,
            source_if_requested=requested_source,
        ),
        _domain(
            "trigger_event",
            trigger_values,
            TRIGGER_EVENTS,
            source_if_requested=requested_source,
            default_values=GLOBAL_STRUCTURAL_TRIGGER_EVENTS,
        ),
        _domain(
            "feedback_event",
            context.allowed_feedback_events,
            FEEDBACK_EVENTS,
            source_if_requested=requested_source,
        ),
        _domain(
            "feedback_relation",
            context.allowed_feedback_relations,
            FEEDBACK_OPERATIONS,
            source_if_requested=requested_source,
        ),
        _domain(
            "mode",
            context.allowed_modes,
            ABILITY_MODES,
            source_if_requested=requested_source,
        ),
        EnumDomainProjection(
            "role",
            _clean_values(role_values or tuple(sorted(CANONICAL_COMBAT_ROLES)), "role"),
            requested_source if context.allowed_roles is not None else role_source,
        ),
        _domain(
            "centrality",
            context.allowed_centralities,
            CENTRALITIES,
            source_if_requested=requested_source,
        ),
        EnumDomainProjection(
            "intent",
            (
                 GENERALIZATION_V2_SEMANTIC_INTENTS
                 if context.contract_profile == "generalization_v2"
                 else (
                     GENERALIZATION_SEMANTIC_INTENTS
                     if context.contract_profile == "generalization_v1"
                     else SEMANTIC_INTENTS
                 )
            ),
            "VOCABULARY_REQUIRED",
        ),
    ]
    if context.contract_profile == "generalization_v2":
        domains.extend(
            (
                EnumDomainProjection("mechanic_kind", ("passive", "triggered"), "VOCABULARY_REQUIRED"),
                EnumDomainProjection("persistence", ("always_on",), "VOCABULARY_REQUIRED"),
            )
        )
    return SemanticEnumProjection(tuple(domains))


def _context_plan_payload(plan: CharacterDesignPlan | None) -> dict[str, object] | None:
    if plan is None:
        return None
    payload = plan.to_dict()
    payload["generation_constraints"] = sorted(plan.generation_constraints)
    payload["recommended_traits"] = sorted(plan.recommended_traits)
    return payload


def context_projection_payload(context: HybridGenerationContext) -> dict[str, object]:
    """Return the canonical, provider-facing context identity payload."""

    payload = {
        "version": context.context_projection_version,
        "case_id": context.case_id,
        "contract_profile": context.contract_profile,
        "brief": context.brief,
        "plan": _context_plan_payload(context.plan),
        "allowed_actors": list(context.allowed_actors or ()),
        "allowed_trigger_subjects": list(context.allowed_trigger_subjects or ()),
        "allowed_effect_subjects": list(context.allowed_effect_subjects or ()),
        "allowed_trigger_events": list(context.allowed_trigger_events or ()),
        "allowed_feedback_events": list(context.allowed_feedback_events or ()),
        "allowed_feedback_relations": list(context.allowed_feedback_relations or ()),
        "allowed_modes": list(context.allowed_modes or ()),
        "allowed_roles": list(context.allowed_roles or ()),
        "allowed_centralities": list(context.allowed_centralities or ()),
        "semantic_projection": project_semantic_enums(context).to_mapping(),
    }
    if context.allowed_response_effect_families is not None:
        payload["allowed_response_effect_families"] = list(
            context.allowed_response_effect_families
        )
    if context.contract_profile == "generalization_v2":
        payload["semantic_ir_version"] = "semantic-skill-plan-ir/0.2.0"
    return payload


def context_projection_digest(context: HybridGenerationContext) -> str:
    """Hash the canonical context projection deterministically."""

    canonical = json.dumps(
        context_projection_payload(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "EnumDomainProjection",
    "CONTEXT_CONTRACT_PROFILES",
    "CONTEXT_PROJECTION_VERSION",
    "CONTEXT_PROJECTION_VERSION_HISTORICAL",
    "CONTEXT_PROJECTION_VERSION_V2",
    "CONTEXT_PROJECTION_VERSION_V2_HISTORICAL",
    "HybridGenerationContext",
    "PROJECTION_SOURCES",
    "ProjectionError",
    "SEMANTIC_ACTORS",
    "SEMANTIC_INTENTS",
    "GENERALIZATION_SEMANTIC_INTENTS",
    "GENERALIZATION_V2_SEMANTIC_INTENTS",
    "GLOBAL_STRUCTURAL_TRIGGER_EVENTS",
    "STRUCTURAL_FEEDBACK_TRIGGER_EVENT",
    "SemanticEnumProjection",
    "project_semantic_enums",
    "context_projection_payload",
    "context_projection_digest",
]
