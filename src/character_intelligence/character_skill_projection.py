"""Minimal Character-to-Skill design projection.

The projection is deliberately smaller than ``CharacterDraft``.  It is an
immutable, deterministic input contract for a Character-context Skill design;
it does not know about providers, Web DTOs, Semantic IR, or SkillKit output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from agents.character_generation import CharacterDesignRequest, CharacterDraft
from combat_semantics import CombatRoleProfile

from .planner import CharacterAffiliationContext, CharacterDesignPlan

CHARACTER_SKILL_PROJECTION_VERSION = "character-skill-context/0.2"


def _normalise_strings(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    cleaned = {value.strip() for value in values if isinstance(value, str) and value.strip()}
    return tuple(sorted(cleaned))


def _safe_affiliation_context(
    value: CharacterAffiliationContext | None,
) -> CharacterAffiliationContext | None:
    if value is None:
        return None
    return CharacterAffiliationContext(
        faction_id=value.faction_id.strip(),
        name=value.name.strip(),
        faction_type=value.faction_type.strip(),
        summary=value.summary.strip(),
        typical_roles=_normalise_strings(value.typical_roles),
        semantic_terms=_normalise_strings(value.semantic_terms),
        division_names=_normalise_strings(value.division_names),
    )


@dataclass(frozen=True)
class CharacterSkillDesignContext:
    """The explicit, stable Character input visible to Skill design."""

    character_name: str
    combat_role_profile: CombatRoleProfile
    ability_concept: str
    design_pitch: str
    skill_relevant_hard_constraints: tuple[str, ...] = ()
    skill_relevant_forbidden_elements: tuple[str, ...] = ()
    relevant_desired_connections: tuple[str, ...] = ()
    affiliation_context: CharacterAffiliationContext | None = None
    projection_version: str = CHARACTER_SKILL_PROJECTION_VERSION
    source_draft_id: str | None = None
    source_context_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.combat_role_profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")
        if self.projection_version != CHARACTER_SKILL_PROJECTION_VERSION:
            raise ValueError("unsupported Character Skill projection version")
        object.__setattr__(self, "character_name", self.character_name.strip())
        object.__setattr__(self, "ability_concept", self.ability_concept.strip())
        object.__setattr__(self, "design_pitch", self.design_pitch.strip())
        object.__setattr__(
            self,
            "skill_relevant_hard_constraints",
            _normalise_strings(self.skill_relevant_hard_constraints),
        )
        object.__setattr__(
            self,
            "skill_relevant_forbidden_elements",
            _normalise_strings(self.skill_relevant_forbidden_elements),
        )
        object.__setattr__(
            self,
            "relevant_desired_connections",
            _normalise_strings(self.relevant_desired_connections),
        )
        object.__setattr__(
            self,
            "affiliation_context",
            _safe_affiliation_context(self.affiliation_context),
        )
        object.__setattr__(
            self,
            "source_draft_id",
            self.source_draft_id.strip() if isinstance(self.source_draft_id, str) else None,
        )
        canonical = json.dumps(
            self.to_projection_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(
            self,
            "source_context_fingerprint",
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def to_projection_mapping(self) -> dict[str, Any]:
        """Return only fields that participate in freshness decisions."""

        return {
            "projection_version": self.projection_version,
            "character_name": self.character_name,
            "combat_role_profile": self.combat_role_profile.to_dict(),
            "ability_concept": self.ability_concept,
            "design_pitch": self.design_pitch,
            "skill_relevant_hard_constraints": list(self.skill_relevant_hard_constraints),
            "skill_relevant_forbidden_elements": list(self.skill_relevant_forbidden_elements),
            "relevant_desired_connections": list(self.relevant_desired_connections),
            "affiliation_context": (
                self.affiliation_context.to_dict()
                if self.affiliation_context is not None
                else None
            ),
        }

    def to_safe_mapping(self) -> dict[str, Any]:
        """Return the Web-safe projection plus its backend-owned fingerprint."""

        return {
            **self.to_projection_mapping(),
            "character_name": self.character_name,
            "source_draft_id": self.source_draft_id,
            "source_context_fingerprint": self.source_context_fingerprint,
        }


def build_character_skill_design_context(
    request: CharacterDesignRequest,
    draft: CharacterDraft,
    plan: CharacterDesignPlan | None = None,
) -> CharacterSkillDesignContext:
    """Build a pure projection from the current Character authoring state."""

    if not isinstance(request, CharacterDesignRequest):
        raise TypeError("request must be a CharacterDesignRequest")
    if not isinstance(draft, CharacterDraft):
        raise TypeError("draft must be a CharacterDraft")
    if plan is not None and not isinstance(plan, CharacterDesignPlan):
        raise TypeError("plan must be a CharacterDesignPlan or None")

    affiliation_context = None
    if (
        plan is not None
        and plan.affiliation_context is not None
        and draft.faction_id == plan.affiliation_context.faction_id
    ):
        affiliation_context = plan.affiliation_context

    return CharacterSkillDesignContext(
        character_name=draft.name,
        combat_role_profile=draft.combat_role_profile,
        ability_concept=draft.ability_concept,
        design_pitch=draft.design_pitch,
        skill_relevant_hard_constraints=request.hard_constraints,
        skill_relevant_forbidden_elements=request.forbidden_elements,
        relevant_desired_connections=request.desired_connections,
        affiliation_context=affiliation_context,
        source_draft_id=draft.draft_id,
    )


__all__ = [
    "CHARACTER_SKILL_PROJECTION_VERSION",
    "CharacterSkillDesignContext",
    "build_character_skill_design_context",
]
