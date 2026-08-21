"""Structured input contract for character design intent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from combat_semantics import (
    CombatRoleProfile,
    legacy_combat_role_projection,
    normalize_legacy_combat_role,
)


def _normalized_strings(value: Sequence[str] | None, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        cleaned = item.strip()
        if cleaned not in result:
            result.append(cleaned)
    return tuple(result)


@dataclass(frozen=True)
class CharacterDesignIntent:
    """A stable, serializable, advisory interpretation of a natural-language brief.

    The values are intentionally small and descriptive rather than tied to the
    existing reference-corpus vocabulary.  ``element`` is an optional
    normalized design signal (for example, ``"fire"``); it is not a Canon
    fact, a ``CharacterDraft`` field, or an enforceable generation constraint.
    Intent is derived from the request and remains advisory unless the
    generation-facing plan can represent a value in the draft contract.
    """

    role_type: str = "character"
    combat_role: str | None = None
    rarity: int | None = None
    target_audience: str = "general"
    personality_keywords: tuple[str, ...] = ()
    design_goals: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    element: str | None = None
    raw_request: str = ""
    combat_role_profile: CombatRoleProfile | None = None

    def __post_init__(self) -> None:
        for field_name in ("role_type", "target_audience"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        if self.rarity is not None and (
            isinstance(self.rarity, bool) or not isinstance(self.rarity, int) or self.rarity < 1
        ):
            raise ValueError("rarity must be a positive integer or None")
        if self.element is not None:
            if not isinstance(self.element, str) or not self.element.strip():
                raise ValueError("element must be a non-empty string or None")
            object.__setattr__(self, "element", self.element.strip())
        if not isinstance(self.raw_request, str):
            raise TypeError("raw_request must be a string")
        object.__setattr__(self, "raw_request", self.raw_request.strip())
        profile = self.combat_role_profile
        if profile is None:
            role = (
                normalize_legacy_combat_role(self.combat_role)
                if self.combat_role not in (None, "unspecified")
                else None
            )
            profile = CombatRoleProfile(primary_role=role)
        elif not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile or None")
        legacy_role = self.combat_role
        if profile.is_unspecified and legacy_role in {
            "burst",
            "sustain",
            "hybrid",
            "buffer",
            "enabler",
            "flex",
            "none",
        }:
            pass
        else:
            expected_legacy_role = legacy_combat_role_projection(profile)
            normalized_legacy = None
            if legacy_role not in (None, "unspecified"):
                normalized_legacy = normalize_legacy_combat_role(legacy_role)
            if legacy_role not in (None, "unspecified", expected_legacy_role) and normalized_legacy != profile.primary_role:
                raise ValueError(
                    "combat_role is a derived compatibility projection and "
                    "must match combat_role_profile"
                )
            legacy_role = expected_legacy_role
        object.__setattr__(self, "combat_role", legacy_role or "unspecified")
        object.__setattr__(self, "combat_role_profile", profile)
        for field_name in (
            "personality_keywords",
            "design_goals",
            "forbidden_patterns",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalized_strings(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the intent."""

        return {
            "role_type": self.role_type,
            "combat_role": self.combat_role,
            "rarity": self.rarity,
            "target_audience": self.target_audience,
            "personality_keywords": list(self.personality_keywords),
            "design_goals": list(self.design_goals),
            "forbidden_patterns": list(self.forbidden_patterns),
            "element": self.element,
            "raw_request": self.raw_request,
            "combat_role_profile": self.combat_role_profile.to_dict(),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDesignIntent":
        """Rehydrate an intent from a mapping produced by :meth:`to_dict`."""

        if not isinstance(payload, Mapping):
            raise TypeError("CharacterDesignIntent must be a mapping")
        return cls(
            role_type=payload.get("role_type", "character"),
            combat_role=payload.get("combat_role", "unspecified"),
            rarity=payload.get("rarity"),
            target_audience=payload.get("target_audience", "general"),
            personality_keywords=payload.get("personality_keywords", ()),
            design_goals=payload.get("design_goals", ()),
            forbidden_patterns=payload.get("forbidden_patterns", ()),
            element=payload.get("element"),
            raw_request=payload.get("raw_request", ""),
            combat_role_profile=(
                CombatRoleProfile.from_mapping(payload["combat_role_profile"])
                if payload.get("combat_role_profile") is not None
                else None
            ),
        )
