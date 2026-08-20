"""Build a generation-facing plan from parsed character design intent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..intent import CharacterDesignIntent, parse_character_design_intent


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


@dataclass(frozen=True)
class CharacterDesignPlan:
    """Intermediate contract between intent understanding and generation."""

    parsed_intent: CharacterDesignIntent
    generation_constraints: tuple[str, ...] = ()
    recommended_traits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.parsed_intent, CharacterDesignIntent):
            raise TypeError("parsed_intent must be CharacterDesignIntent")
        for field_name in ("generation_constraints", "recommended_traits"):
            value = getattr(self, field_name)
            if isinstance(value, (str, bytes)):
                raise TypeError(f"{field_name} must be a sequence of strings")
            if not all(isinstance(item, str) and item.strip() for item in value):
                raise ValueError(f"{field_name} must contain non-empty strings")
            object.__setattr__(self, field_name, _unique(tuple(item.strip() for item in value)))

    @classmethod
    def from_intent(cls, intent: CharacterDesignIntent) -> "CharacterDesignPlan":
        constraints: list[str] = []
        if intent.role_type != "character":
            constraints.append(f"role_type={intent.role_type}")
        if intent.combat_role != "unspecified":
            constraints.append(f"combat_role={intent.combat_role}")
        if intent.rarity is not None:
            constraints.append(f"rarity={intent.rarity}")
        if intent.element is not None:
            constraints.append(f"element={intent.element}")
        if intent.target_audience != "general":
            constraints.append(f"target_audience={intent.target_audience}")
        constraints.extend(f"forbidden_pattern={item}" for item in intent.forbidden_patterns)

        traits = list(intent.personality_keywords)
        traits.extend(item for item in intent.design_goals if item not in {intent.element})
        return cls(intent, tuple(constraints), _unique(tuple(traits)))

    @classmethod
    def from_text(cls, request: str) -> "CharacterDesignPlan":
        return cls.from_intent(parse_character_design_intent(request))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the plan."""

        return {
            "parsed_intent": self.parsed_intent.to_dict(),
            "generation_constraints": list(self.generation_constraints),
            "recommended_traits": list(self.recommended_traits),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDesignPlan":
        if not isinstance(payload, Mapping):
            raise TypeError("CharacterDesignPlan must be a mapping")
        return cls(
            parsed_intent=CharacterDesignIntent.from_mapping(payload["parsed_intent"]),
            generation_constraints=payload.get("generation_constraints", ()),
            recommended_traits=payload.get("recommended_traits", ()),
        )


def build_character_design_plan(request: str) -> CharacterDesignPlan:
    """Parse a natural-language brief and build its generation plan."""

    return CharacterDesignPlan.from_text(request)
