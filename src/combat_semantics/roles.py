"""Canonical combat-role value objects and bounded legacy normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Literal, cast


CombatRole = Literal[
    "main_dps",
    "sub_dps",
    "support",
    "healer",
    "control",
    "defense",
]

CANONICAL_COMBAT_ROLES: tuple[CombatRole, ...] = (
    "main_dps",
    "sub_dps",
    "support",
    "healer",
    "control",
    "defense",
)

_CANONICAL_ROLE_SET = frozenset(CANONICAL_COMBAT_ROLES)
_LOOKUP_SEPARATOR_RE = re.compile(r"[\s-]+")


def _lookup_key(value: str) -> str:
    return _LOOKUP_SEPARATOR_RE.sub("_", value.strip().casefold())


# This is intentionally limited to role aliases.  Behavior and composition
# labels such as burst, sustain, and hybrid are not assigned a role here.
_LEGACY_ROLE_CROSSWALK: dict[str, CombatRole] = {
    "dps": "main_dps",
    "main_dps": "main_dps",
    "primary_dps": "main_dps",
    "main_damage_dealer": "main_dps",
    "sub_dps": "sub_dps",
    "secondary_dps": "sub_dps",
    "sub_damage_dealer": "sub_dps",
    "off_field_dps": "sub_dps",
    "support": "support",
    "team_support": "support",
    "healer": "healer",
    "healing_support": "healer",
    "control": "control",
    "defense": "defense",
    "tank": "defense",
    "defender": "defense",
    "frontline_defender": "defense",
}


@dataclass(frozen=True)
class CombatRoleProfile:
    """Immutable canonical primary/secondary combat-role contract."""

    primary_role: CombatRole | None = None
    secondary_roles: tuple[CombatRole, ...] = ()

    def __post_init__(self) -> None:
        if self.primary_role is not None:
            self._validate_role(self.primary_role, "primary_role")

        if isinstance(self.secondary_roles, (str, bytes)):
            raise TypeError("secondary_roles must be a sequence of canonical roles")
        secondary = tuple(self.secondary_roles)
        for role in secondary:
            self._validate_role(role, "secondary_roles")
        if len(secondary) != len(set(secondary)):
            raise ValueError("secondary_roles must not contain duplicates")
        if self.primary_role is not None and self.primary_role in secondary:
            raise ValueError("primary_role must not also occur in secondary_roles")
        object.__setattr__(self, "secondary_roles", secondary)

    @staticmethod
    def _validate_role(value: object, field_name: str) -> None:
        if value not in _CANONICAL_ROLE_SET:
            raise ValueError(
                f"{field_name} must contain a canonical combat role; got {value!r}"
            )

    @property
    def is_unspecified(self) -> bool:
        return self.primary_role is None and not self.secondary_roles

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_role": self.primary_role,
            "secondary_roles": list(self.secondary_roles),
        }

    @classmethod
    def from_mapping(cls, payload: object) -> "CombatRoleProfile":
        if not isinstance(payload, Mapping):
            raise TypeError("CombatRoleProfile must be a mapping")
        unknown = set(payload) - {"primary_role", "secondary_roles"}
        if unknown:
            raise ValueError(f"CombatRoleProfile has unknown field(s): {sorted(unknown)}")
        secondary = payload.get("secondary_roles", ())
        if not isinstance(secondary, Sequence) or isinstance(secondary, (str, bytes)):
            raise TypeError("secondary_roles must be a sequence of canonical roles")
        return cls(
            primary_role=cast(CombatRole | None, payload.get("primary_role")),
            secondary_roles=tuple(cast(CombatRole, item) for item in secondary),
        )


def legacy_combat_role_projection(profile: CombatRoleProfile) -> str:
    """Return the old scalar spelling only at the legacy boundary."""

    if profile.primary_role is None:
        return "unspecified"
    if profile.primary_role == "main_dps":
        return "dps"
    return profile.primary_role


@dataclass(frozen=True)
class CombatRoleNormalization:
    """Result of resolving one role-domain token."""

    raw_value: str
    canonical_role: CombatRole
    lossy: bool = False
    note: str | None = None


def normalize_legacy_combat_role(value: str) -> CombatRole | None:
    """Normalize only bounded role aliases; return None for non-role labels."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("combat role must be a non-empty string")
    return _LEGACY_ROLE_CROSSWALK.get(_lookup_key(value))


__all__ = [
    "CANONICAL_COMBAT_ROLES",
    "CombatRole",
    "CombatRoleNormalization",
    "CombatRoleProfile",
    "legacy_combat_role_projection",
    "normalize_legacy_combat_role",
]
