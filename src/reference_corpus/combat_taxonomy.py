"""Ownership and compatibility rules for combat taxonomy fields.

The structured v0.6 combat profile is the canonical interpretation surface.
``normalized_roles`` remains a legacy compatibility field and is never treated
as a second canonical vocabulary.  A legacy label may project into more than
one structured domain, or into none when its meaning is too broad to preserve
without context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .combat_vocabulary import CombatVocabulary
from .enums import NormalizedRole


CrosswalkStatus = Literal["exact", "contextual", "ambiguous", "deprecated"]


@dataclass(frozen=True)
class LegacyCombatCrosswalkEntry:
    """One non-lossless mapping from a legacy role label."""

    legacy_role: str
    status: CrosswalkStatus
    combat_roles: tuple[str, ...] = ()
    damage_patterns: tuple[str, ...] = ()
    team_positions: tuple[str, ...] = ()
    note: str = ""


LEGACY_COMBAT_CROSSWALK: tuple[LegacyCombatCrosswalkEntry, ...] = (
    LegacyCombatCrosswalkEntry(
        "on_field_dps",
        "contextual",
        combat_roles=("main_dps",),
        note="Projects to the primary damage role; field-time ownership is not itself a role.",
    ),
    LegacyCombatCrosswalkEntry(
        "off_field_dps",
        "contextual",
        combat_roles=("sub_dps",),
        note="Projects to secondary damage contribution; off-field behavior is not a damage pattern.",
    ),
    LegacyCombatCrosswalkEntry(
        "burst_dps",
        "ambiguous",
        damage_patterns=("burst",),
        note="Burst describes damage timing; the primary or secondary role requires evidence.",
    ),
    LegacyCombatCrosswalkEntry(
        "support",
        "exact",
        combat_roles=("support",),
        note="Support remains a combat job; buffer and enabler are team positions.",
    ),
    LegacyCombatCrosswalkEntry(
        "sustain",
        "ambiguous",
        note="Sustain may be healing, shielding, mitigation, or another survivability pattern.",
    ),
    LegacyCombatCrosswalkEntry(
        "control",
        "exact",
        combat_roles=("control",),
        note="Control is a combat job; its implementation belongs in mechanics.",
    ),
    LegacyCombatCrosswalkEntry(
        "hybrid",
        "ambiguous",
        note="Hybrid is a composition claim and must be decomposed from evidence.",
    ),
    LegacyCombatCrosswalkEntry(
        "unknown",
        "deprecated",
        note="Unknown carries no structured claim.",
    ),
)

_CROSSWALK_BY_LEGACY_ROLE = {
    entry.legacy_role: entry for entry in LEGACY_COMBAT_CROSSWALK
}


def _legacy_id(value: str | NormalizedRole) -> str:
    return value.value if isinstance(value, NormalizedRole) else value


def validate_legacy_crosswalk(vocabulary: CombatVocabulary) -> None:
    """Ensure every non-empty crosswalk target is a canonical vocabulary ID."""

    for entry in LEGACY_COMBAT_CROSSWALK:
        for domain, values in (
            ("combat_role", entry.combat_roles),
            ("damage_pattern", entry.damage_patterns),
            ("team_position", entry.team_positions),
        ):
            for value in values:
                if vocabulary.canonical_id(domain, value) != value:
                    raise ValueError(
                        f"legacy crosswalk target {value!r} is not canonical in {domain}"
                    )


def validate_legacy_compatibility(
    normalized_roles: Sequence[str | NormalizedRole],
    combat_roles: Sequence[str],
    damage_patterns: Sequence[str],
) -> None:
    """Reject contradictions while allowing partial structured profiles.

    Empty structured domains are treated as incomplete, not contradictory.
    Ambiguous legacy labels intentionally impose no automatic structured role.
    """

    structured_roles = set(combat_roles)
    structured_patterns = set(damage_patterns)
    for legacy_value in normalized_roles:
        legacy_role = _legacy_id(legacy_value)
        entry = _CROSSWALK_BY_LEGACY_ROLE.get(legacy_role)
        if entry is None:
            raise ValueError(f"unknown legacy normalized role: {legacy_role!r}")
        if entry.combat_roles and structured_roles:
            if not structured_roles.intersection(entry.combat_roles):
                raise ValueError(
                    f"legacy normalized role {legacy_role!r} contradicts "
                    f"combat_roles {sorted(structured_roles)!r}"
                )
        if entry.damage_patterns and structured_patterns:
            if not structured_patterns.intersection(entry.damage_patterns):
                raise ValueError(
                    f"legacy normalized role {legacy_role!r} contradicts "
                    f"damage_patterns {sorted(structured_patterns)!r}"
                )


__all__ = [
    "CrosswalkStatus",
    "LEGACY_COMBAT_CROSSWALK",
    "LegacyCombatCrosswalkEntry",
    "validate_legacy_compatibility",
    "validate_legacy_crosswalk",
]
