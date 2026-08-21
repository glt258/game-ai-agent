"""Shared canonical combat semantics used by upstream design layers."""

from .roles import (
    CANONICAL_COMBAT_ROLES,
    CombatRole,
    CombatRoleNormalization,
    CombatRoleProfile,
    legacy_combat_role_projection,
    normalize_legacy_combat_role,
)

__all__ = [
    "CANONICAL_COMBAT_ROLES",
    "CombatRole",
    "CombatRoleNormalization",
    "CombatRoleProfile",
    "legacy_combat_role_projection",
    "normalize_legacy_combat_role",
]
