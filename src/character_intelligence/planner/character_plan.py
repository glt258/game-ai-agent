"""Build a generation-facing plan from parsed character design intent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from combat_semantics import CombatRoleProfile

from ..intent import CharacterDesignIntent, parse_character_design_intent


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _string_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return _unique(tuple(item.strip() for item in value if isinstance(item, str) and item.strip()))


@dataclass(frozen=True)
class CharacterAffiliationContext:
    """Safe design context projected from one resolved Canon faction."""

    faction_id: str
    name: str
    faction_type: str
    summary: str
    typical_roles: tuple[str, ...] = ()
    semantic_terms: tuple[str, ...] = ()
    division_names: tuple[str, ...] = ()

    @classmethod
    def from_record(cls, faction_id: str, record: Mapping[str, Any]) -> "CharacterAffiliationContext":
        public_identity = record.get("public_identity", {})
        core_function = record.get("core_function", {})
        reputation = record.get("public_reputation", {})
        member_profile = record.get("member_profile", {})
        divisions = record.get("internal_structure", {}).get("divisions", [])
        division_names = _unique(
            tuple(
                item.get("name", "").strip()
                for item in divisions
                if isinstance(item, Mapping) and isinstance(item.get("name"), str) and item.get("name", "").strip()
            )
        )
        typical_roles = _string_values(member_profile.get("typical_roles"))
        keywords = _string_values(reputation.get("keywords"))
        tags = _string_values(record.get("tags"))
        semantic_terms = _unique((*keywords, *tags, *division_names, *typical_roles))
        summary = (
            core_function.get("description")
            if isinstance(core_function, Mapping)
            else None
        ) or (
            public_identity.get("description")
            if isinstance(public_identity, Mapping)
            else ""
        )
        return cls(
            faction_id=faction_id,
            name=str(record.get("name", faction_id)),
            faction_type=str(record.get("type", "")),
            summary=str(summary),
            typical_roles=typical_roles,
            semantic_terms=semantic_terms,
            division_names=division_names,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "faction_id": self.faction_id,
            "name": self.name,
            "faction_type": self.faction_type,
            "summary": self.summary,
            "typical_roles": list(self.typical_roles),
            "semantic_terms": list(self.semantic_terms),
            "division_names": list(self.division_names),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterAffiliationContext":
        if not isinstance(payload, Mapping):
            raise TypeError("CharacterAffiliationContext must be a mapping")
        return cls(
            faction_id=payload["faction_id"],
            name=payload["name"],
            faction_type=payload.get("faction_type", ""),
            summary=payload.get("summary", ""),
            typical_roles=payload.get("typical_roles", ()),
            semantic_terms=payload.get("semantic_terms", ()),
            division_names=payload.get("division_names", ()),
        )


@dataclass(frozen=True)
class CharacterDesignPlan:
    """Intermediate contract between intent understanding and generation."""

    parsed_intent: CharacterDesignIntent
    generation_constraints: tuple[str, ...] = ()
    recommended_traits: tuple[str, ...] = ()
    combat_role_profile: CombatRoleProfile | None = None
    expected_affiliation_id: str | None = None
    affiliation_context: CharacterAffiliationContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parsed_intent, CharacterDesignIntent):
            raise TypeError("parsed_intent must be CharacterDesignIntent")
        profile = self.combat_role_profile or self.parsed_intent.combat_role_profile
        if not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")
        if profile != self.parsed_intent.combat_role_profile:
            raise ValueError("combat_role_profile must match parsed_intent")
        object.__setattr__(self, "combat_role_profile", profile)
        expected = self.parsed_intent.requested_affiliation_id
        if self.expected_affiliation_id is not None and self.expected_affiliation_id != expected:
            raise ValueError("expected_affiliation_id must match parsed_intent")
        object.__setattr__(self, "expected_affiliation_id", expected)
        if self.affiliation_context is not None:
            if not isinstance(self.affiliation_context, CharacterAffiliationContext):
                raise TypeError("affiliation_context must be a CharacterAffiliationContext or None")
            if self.affiliation_context.faction_id != expected:
                raise ValueError("affiliation_context must match expected_affiliation_id")
        for field_name in ("generation_constraints", "recommended_traits"):
            value = getattr(self, field_name)
            if isinstance(value, (str, bytes)):
                raise TypeError(f"{field_name} must be a sequence of strings")
            if not all(isinstance(item, str) and item.strip() for item in value):
                raise ValueError(f"{field_name} must contain non-empty strings")
            object.__setattr__(self, field_name, _unique(tuple(item.strip() for item in value)))

    @classmethod
    def from_intent(
        cls,
        intent: CharacterDesignIntent,
        factions: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> "CharacterDesignPlan":
        constraints: list[str] = []
        constraints.extend(f"forbidden_pattern={item}" for item in intent.forbidden_patterns)

        traits = list(intent.personality_keywords)
        if intent.element is not None:
            traits.append(f"element:{intent.element}")
        if intent.target_audience != "general":
            traits.append(f"target_audience:{intent.target_audience}")
        traits.extend(item for item in intent.design_goals if item not in {intent.element})
        context = None
        if intent.requested_affiliation_id is not None and factions is not None:
            record = factions.get(intent.requested_affiliation_id)
            if isinstance(record, Mapping):
                context = CharacterAffiliationContext.from_record(
                    intent.requested_affiliation_id,
                    record,
                )
        return cls(
            intent,
            tuple(constraints),
            _unique(tuple(traits)),
            expected_affiliation_id=intent.requested_affiliation_id,
            affiliation_context=context,
        )

    @classmethod
    def from_text(cls, request: str, factions=None) -> "CharacterDesignPlan":
        intent = parse_character_design_intent(request, factions=factions)
        return cls.from_intent(intent, factions=factions)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the plan."""

        return {
            "parsed_intent": self.parsed_intent.to_dict(),
            "combat_role_profile": self.combat_role_profile.to_dict(),
            "generation_constraints": list(self.generation_constraints),
            "recommended_traits": list(self.recommended_traits),
            "expected_affiliation_id": self.expected_affiliation_id,
            "affiliation_context": (
                self.affiliation_context.to_dict()
                if self.affiliation_context is not None
                else None
            ),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDesignPlan":
        if not isinstance(payload, Mapping):
            raise TypeError("CharacterDesignPlan must be a mapping")
        return cls(
            parsed_intent=CharacterDesignIntent.from_mapping(payload["parsed_intent"]),
            generation_constraints=payload.get("generation_constraints", ()),
            recommended_traits=payload.get("recommended_traits", ()),
            combat_role_profile=(
                CombatRoleProfile.from_mapping(payload["combat_role_profile"])
                if payload.get("combat_role_profile") is not None
                else None
            ),
            expected_affiliation_id=payload.get("expected_affiliation_id"),
            affiliation_context=(
                CharacterAffiliationContext.from_mapping(payload["affiliation_context"])
                if payload.get("affiliation_context") is not None
                else None
            ),
        )


def build_character_design_plan(request: str) -> CharacterDesignPlan:
    """Parse a natural-language brief and build its generation plan."""

    return CharacterDesignPlan.from_text(request)
