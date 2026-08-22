"""Shared canonical combat semantics used by upstream design layers."""

from .roles import (
    CANONICAL_COMBAT_ROLES,
    CombatRole,
    CombatRoleNormalization,
    CombatRoleProfile,
    normalize_legacy_combat_role,
    resolve_legacy_combat_role_profile,
)

__all__ = [
    "CANONICAL_COMBAT_ROLES",
    "CombatRole",
    "CombatRoleNormalization",
    "CombatRoleProfile",
    "normalize_legacy_combat_role",
    "resolve_legacy_combat_role_profile",
]
