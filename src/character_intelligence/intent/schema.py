"""Structured input contract for character design intent."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from combat_semantics import (
    CombatRoleProfile,
    resolve_legacy_combat_role_profile,
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


def _gender_value_key(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    compact = normalized.replace(" ", "").replace("-", "").replace("_", "")
    aliases = {
        "女": "female",
        "女性": "female",
        "女人": "female",
        "女生": "female",
        "female": "female",
        "woman": "female",
        "women": "female",
        "girl": "female",
        "girls": "female",
        "男": "male",
        "男性": "male",
        "男人": "male",
        "男生": "male",
        "male": "male",
        "man": "male",
        "men": "male",
        "boy": "male",
        "boys": "male",
        "未指定": "unspecified",
        "未定": "unspecified",
        "未知": "unspecified",
        "不明": "unspecified",
        "不确定": "unspecified",
        "unspecified": "unspecified",
        "undetermined": "unspecified",
        "unknown": "unspecified",
        "nonbinary": "nonbinary",
        "非二元": "nonbinary",
        "非二元性别": "nonbinary",
    }
    return aliases.get(compact, normalized)


@dataclass(frozen=True)
class ExplicitGenderRequirement:
    """One explicit request constraint using CharacterDraft's free-form value contract.

    The object exists only when the user expressed a reliable constraint. A
    missing value therefore remains distinct from an explicit request to keep
    gender unspecified. ``required_value`` and ``forbidden_values`` stay
    strings because CharacterDraft.gender is ``string | null``, not an enum.
    """

    required_value: str | None = None
    forbidden_values: tuple[str, ...] = ()
    remain_unspecified: bool = False

    def __post_init__(self) -> None:
        if self.required_value is not None:
            if not isinstance(self.required_value, str) or not self.required_value.strip():
                raise ValueError("required_value must be a non-empty string or None")
            object.__setattr__(self, "required_value", self.required_value.strip())
        if not isinstance(self.remain_unspecified, bool):
            raise TypeError("remain_unspecified must be a bool")
        forbidden = _normalized_strings(self.forbidden_values, "forbidden_values")
        object.__setattr__(self, "forbidden_values", forbidden)
        if self.remain_unspecified and (self.required_value is not None or forbidden):
            raise ValueError("remain_unspecified cannot be combined with a gender value")
        if self.required_value is None and not forbidden and not self.remain_unspecified:
            raise ValueError("an explicit gender requirement must constrain at least one value")
        if self.required_value is not None and _gender_value_key(self.required_value) in {
            _gender_value_key(item) for item in forbidden
        }:
            raise ValueError("required_value cannot also be forbidden")

    def to_dict(self) -> dict[str, Any]:
        """Return the additive intent representation used by V2 planning."""

        return {
            "required_value": self.required_value,
            "forbidden_values": list(self.forbidden_values),
            "remain_unspecified": self.remain_unspecified,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExplicitGenderRequirement":
        """Restore one explicit requirement without imposing an enum on gender values."""

        if not isinstance(payload, Mapping):
            raise TypeError("ExplicitGenderRequirement must be a mapping")
        return cls(
            required_value=payload.get("required_value"),
            forbidden_values=payload.get("forbidden_values", ()),
            remain_unspecified=payload.get("remain_unspecified", False),
        )

    def satisfied_by(self, value: str | None) -> bool:
        """Check a generated value without inferring from other character fields."""

        candidate_key = _gender_value_key(value)
        if self.remain_unspecified:
            return candidate_key in {None, "unspecified"}
        if self.required_value is not None:
            if candidate_key != _gender_value_key(self.required_value):
                return False
        forbidden_keys = {_gender_value_key(item) for item in self.forbidden_values}
        return candidate_key not in forbidden_keys

    def to_hard_requirement(self) -> str:
        """Project the typed attribute into the existing Spec hard-requirement list."""

        clauses: list[str] = []
        if self.remain_unspecified:
            clauses.append(
                "CharacterDraft.gender must remain null or explicitly unspecified; do not infer a gender."
            )
        if self.required_value is not None:
            clauses.append(
                f"CharacterDraft.gender must match the user-requested value {self.required_value!r}."
            )
        if self.forbidden_values:
            values = ", ".join(repr(item) for item in self.forbidden_values)
            clauses.append(f"CharacterDraft.gender must not use these user-prohibited values: {values}.")
        return "Explicit gender requirement: " + " ".join(clauses)


@dataclass(frozen=True)
class ExplicitAgeRequirement:
    """A user-stated exact age or bounded age range for the generated character."""

    preferred_age: int
    minimum_age: int
    maximum_age: int
    approximate: bool = False

    def __post_init__(self) -> None:
        for field_name in ("preferred_age", "minimum_age", "maximum_age"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 150:
                raise ValueError(f"{field_name} must be an integer from 0 through 150")
        if self.minimum_age > self.maximum_age:
            raise ValueError("minimum_age must not exceed maximum_age")
        if not self.minimum_age <= self.preferred_age <= self.maximum_age:
            raise ValueError("preferred_age must fall within the requested age range")
        if not isinstance(self.approximate, bool):
            raise TypeError("approximate must be a boolean")

    def satisfied_by(self, value: int | None) -> bool:
        """Return whether a generated exact age satisfies the user range."""

        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.minimum_age <= value <= self.maximum_age
        )

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "preferred_age": self.preferred_age,
            "minimum_age": self.minimum_age,
            "maximum_age": self.maximum_age,
            "approximate": self.approximate,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExplicitAgeRequirement":
        if not isinstance(payload, Mapping):
            raise TypeError("ExplicitAgeRequirement must be a mapping")
        expected = {"preferred_age", "minimum_age", "maximum_age", "approximate"}
        if set(payload) != expected:
            raise ValueError("ExplicitAgeRequirement has missing or unsupported fields")
        return cls(
            preferred_age=payload["preferred_age"],
            minimum_age=payload["minimum_age"],
            maximum_age=payload["maximum_age"],
            approximate=payload["approximate"],
        )

    def to_hard_requirement(self) -> str:
        return (
            "Explicit age requirement: CharacterDraft.age must be between "
            f"{self.minimum_age} and {self.maximum_age}; preferred age is {self.preferred_age}."
        )


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
    rarity: int | None = None
    target_audience: str = "general"
    personality_keywords: tuple[str, ...] = ()
    design_goals: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    element: str | None = None
    raw_request: str = ""
    gender_requirement: ExplicitGenderRequirement | None = None
    age_requirement: ExplicitAgeRequirement | None = None
    combat_role_profile: CombatRoleProfile | None = None
    requested_affiliation_id: str | None = None

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
        if self.gender_requirement is not None and not isinstance(
            self.gender_requirement, ExplicitGenderRequirement
        ):
            raise TypeError("gender_requirement must be ExplicitGenderRequirement or None")
        if self.age_requirement is not None and not isinstance(
            self.age_requirement, ExplicitAgeRequirement
        ):
            raise TypeError("age_requirement must be ExplicitAgeRequirement or None")
        if self.requested_affiliation_id is not None:
            if not isinstance(self.requested_affiliation_id, str) or not self.requested_affiliation_id.strip():
                raise ValueError("requested_affiliation_id must be a non-empty string or None")
            if not self.requested_affiliation_id.startswith("faction_"):
                raise ValueError("requested_affiliation_id must be a Canon faction ID")
            object.__setattr__(self, "requested_affiliation_id", self.requested_affiliation_id.strip())
        profile = self.combat_role_profile
        if profile is None:
            profile = CombatRoleProfile()
        elif not isinstance(profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile or None")
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

        profile = self.combat_role_profile
        assert profile is not None  # __post_init__ normalizes an omitted profile.
        result = {
            "role_type": self.role_type,
            "rarity": self.rarity,
            "target_audience": self.target_audience,
            "personality_keywords": list(self.personality_keywords),
            "design_goals": list(self.design_goals),
            "forbidden_patterns": list(self.forbidden_patterns),
            "element": self.element,
            "raw_request": self.raw_request,
            "combat_role_profile": profile.to_dict(),
            "requested_affiliation_id": self.requested_affiliation_id,
        }
        if self.gender_requirement is not None:
            result["gender_requirement"] = self.gender_requirement.to_dict()
        if self.age_requirement is not None:
            result["age_requirement"] = self.age_requirement.to_dict()
        return result

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDesignIntent":
        """Rehydrate an intent from a mapping produced by :meth:`to_dict`."""

        if not isinstance(payload, Mapping):
            raise TypeError("CharacterDesignIntent must be a mapping")
        legacy_value = payload.get("combat_role")
        profile_raw = payload.get("combat_role_profile")
        try:
            profile = resolve_legacy_combat_role_profile(profile_raw, legacy_value)
        except TypeError as error:
            raise TypeError(
                f"CharacterDesignIntent.combat_role compatibility input is invalid: {error}"
            ) from error
        except ValueError as error:
            raise ValueError(
                f"CharacterDesignIntent.combat_role compatibility input is invalid: {error}"
            ) from error
        gender_raw = payload.get("gender_requirement")
        if gender_raw is not None and not isinstance(gender_raw, Mapping):
            raise TypeError("CharacterDesignIntent.gender_requirement must be a mapping or None")
        age_raw = payload.get("age_requirement")
        if age_raw is not None and not isinstance(age_raw, Mapping):
            raise TypeError("CharacterDesignIntent.age_requirement must be a mapping or None")
        return cls(
            role_type=payload.get("role_type", "character"),
            rarity=payload.get("rarity"),
            target_audience=payload.get("target_audience", "general"),
            personality_keywords=payload.get("personality_keywords", ()),
            design_goals=payload.get("design_goals", ()),
            forbidden_patterns=payload.get("forbidden_patterns", ()),
            element=payload.get("element"),
            raw_request=payload.get("raw_request", ""),
            gender_requirement=(
                ExplicitGenderRequirement.from_mapping(gender_raw)
                if gender_raw is not None
                else None
            ),
            age_requirement=(
                ExplicitAgeRequirement.from_mapping(age_raw)
                if age_raw is not None
                else None
            ),
            combat_role_profile=profile,
            requested_affiliation_id=payload.get("requested_affiliation_id"),
        )
