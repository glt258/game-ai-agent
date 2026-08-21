"""Character Intelligence Layer public package."""

from combat_semantics import (
    CANONICAL_COMBAT_ROLES,
    CombatRole,
    CombatRoleNormalization,
    CombatRoleProfile,
    legacy_combat_role_projection,
)

from .intent import (
    CharacterDesignIntent,
    CharacterDesignIntentParser,
    DeterministicCharacterDesignIntentParser,
)
from .planner import CharacterDesignPlan

__all__ = [
    "CharacterDesignIntent",
    "CharacterDesignIntentParser",
    "CharacterDesignPlan",
    "DeterministicCharacterDesignIntentParser",
    "CANONICAL_COMBAT_ROLES",
    "CombatRole",
    "CombatRoleNormalization",
    "CombatRoleProfile",
    "legacy_combat_role_projection",
]
