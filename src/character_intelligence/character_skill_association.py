"""Session-only Character ↔ Skill association and slot semantics.

This module is the narrow application seam for associating immutable Skill
artifacts with one Character session.  It intentionally does not define a
Character Kit, persistence identity, or cross-Skill evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .character_skill_alignment import CharacterSkillAlignmentResult
from .character_skill_projection import CharacterSkillDesignContext
from .skill_artifact import (
    ArtifactDriftInspection,
    CharacterSkillArtifactBinding,
    SkillArtifactVersionMetadata,
    SkillDesignArtifact,
    build_character_skill_artifact_binding,
    inspect_skill_artifact_compatibility,
)


class CharacterSkillAssociationError(ValueError):
    """Stable fail-closed error for invalid session association operations."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class SkillSlot(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    PASSIVE = "passive"
    UTILITY = "utility"


@dataclass(frozen=True)
class SkillSlotMetadata:
    slot: SkillSlot
    order: int
    label: str
    description: str
    max_items: int | None = 1

    def to_mapping(self) -> dict[str, object]:
        return {
            "id": self.slot.value,
            "order": self.order,
            "label": self.label,
            "description": self.description,
            "max_items": self.max_items,
        }


SKILL_SLOT_METADATA: tuple[SkillSlotMetadata, ...] = (
    SkillSlotMetadata(SkillSlot.PRIMARY, 0, "Primary", "Primary Character Skill association.", 1),
    SkillSlotMetadata(SkillSlot.SECONDARY, 1, "Secondary", "Secondary Character Skill association.", 1),
    SkillSlotMetadata(SkillSlot.PASSIVE, 2, "Passive", "Passive Character Skill association.", None),
    SkillSlotMetadata(SkillSlot.UTILITY, 3, "Utility", "Utility Character Skill association.", None),
)
SLOT_ORDER: dict[SkillSlot, int] = {item.slot: item.order for item in SKILL_SLOT_METADATA}


@dataclass(frozen=True)
class CharacterSkillAssociation:
    """One session-scoped relationship; the Skill artifact remains immutable."""

    association_id: str
    artifact: SkillDesignArtifact
    binding: CharacterSkillArtifactBinding
    slot: SkillSlot
    order: int
    family: str
    mode: str
    display_summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, SkillDesignArtifact):
            raise TypeError("artifact must be a SkillDesignArtifact")
        if not isinstance(self.binding, CharacterSkillArtifactBinding):
            raise TypeError("binding must be a CharacterSkillArtifactBinding")
        if not isinstance(self.slot, SkillSlot):
            raise TypeError("slot must be a SkillSlot")
        if self.binding.artifact_digest != self.artifact.artifact_digest:
            raise CharacterSkillAssociationError(
                "ASSOCIATION_ARTIFACT_DIGEST_MISMATCH",
                "binding is not bound to artifact",
            )
        if self.order != SLOT_ORDER[self.slot]:
            raise CharacterSkillAssociationError(
                "ASSOCIATION_ORDER_MISMATCH",
                "association order must match authoritative slot order",
            )
        if self.association_id != _association_id(self.slot, self.artifact.artifact_digest):
            raise CharacterSkillAssociationError(
                "ASSOCIATION_ID_INVALID",
                "association_id must be the session-scoped slot/artifact key",
            )
        for name in ("family", "mode", "display_summary"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise CharacterSkillAssociationError(
                    "ASSOCIATION_METADATA_INVALID",
                    f"{name} must be non-empty",
                )

    @classmethod
    def from_artifact(
        cls,
        artifact: SkillDesignArtifact,
        binding: CharacterSkillArtifactBinding,
        *,
        slot: SkillSlot | str,
        family: str,
        mode: str,
        display_summary: str,
    ) -> "CharacterSkillAssociation":
        resolved_slot = _resolve_slot(slot)
        return cls(
            association_id=_association_id(resolved_slot, artifact.artifact_digest),
            artifact=artifact,
            binding=binding,
            slot=resolved_slot,
            order=SLOT_ORDER[resolved_slot],
            family=family,
            mode=mode,
            display_summary=display_summary,
        )

    @property
    def artifact_digest(self) -> str:
        return self.artifact.artifact_digest

    @property
    def source_context_fingerprint(self) -> str:
        return self.binding.source_context_fingerprint

    def freshness_for(self, current_context: CharacterSkillDesignContext) -> Literal["current", "stale"]:
        return self.binding.freshness_for(current_context.source_context_fingerprint)

    def compatibility_for(
        self,
        current_versions: SkillArtifactVersionMetadata,
    ) -> ArtifactDriftInspection:
        return inspect_skill_artifact_compatibility(self.artifact.versions, current_versions)

    def to_mapping(self) -> dict[str, object]:
        return {
            "association_id": self.association_id,
            "artifact": self.artifact.to_mapping(),
            "binding": self.binding.to_mapping(),
            "slot": self.slot.value,
            "order": self.order,
            "family": self.family,
            "mode": self.mode,
            "display_summary": self.display_summary,
        }


@dataclass(frozen=True)
class CharacterSkillCollection:
    """Immutable ordered 0..N association collection for one Character session."""

    associations: tuple[CharacterSkillAssociation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        values = tuple(self.associations)
        if not all(isinstance(item, CharacterSkillAssociation) for item in values):
            raise TypeError("associations must contain CharacterSkillAssociation values")
        if len({item.association_id for item in values}) != len(values):
            raise CharacterSkillAssociationError("DUPLICATE_ASSOCIATION", "association id already exists")
        if len({item.artifact_digest for item in values}) != len(values):
            raise CharacterSkillAssociationError("DUPLICATE_ARTIFACT", "one artifact may be attached once per session")
        if len({item.slot for item in values}) != len(values):
            raise CharacterSkillAssociationError("DUPLICATE_SLOT", "one artifact may occupy each slot")
        object.__setattr__(self, "associations", self._ordered(values))

    @property
    def ordered(self) -> tuple[CharacterSkillAssociation, ...]:
        return self.associations

    def attach(
        self,
        association: CharacterSkillAssociation,
        *,
        replace: bool = False,
    ) -> "CharacterSkillCollection":
        if not isinstance(association, CharacterSkillAssociation):
            raise TypeError("association must be a CharacterSkillAssociation")
        if any(item.artifact_digest == association.artifact_digest for item in self.associations):
            raise CharacterSkillAssociationError(
                "DUPLICATE_ARTIFACT",
                "the same Skill artifact cannot be attached twice in one session",
            )
        occupied = next((item for item in self.associations if item.slot == association.slot), None)
        if occupied is not None and not replace:
            raise CharacterSkillAssociationError(
                "SLOT_OCCUPIED",
                "slot is occupied; explicit replace is required",
            )
        remaining = tuple(item for item in self.associations if item.slot != association.slot)
        return CharacterSkillCollection(remaining + (association,))

    def replace(self, association: CharacterSkillAssociation) -> "CharacterSkillCollection":
        return self.attach(association, replace=True)

    def detach(self, association_id: str) -> "CharacterSkillCollection":
        if not isinstance(association_id, str) or not association_id.strip():
            raise CharacterSkillAssociationError("ASSOCIATION_ID_INVALID", "association id must be non-empty")
        if not any(item.association_id == association_id for item in self.associations):
            raise CharacterSkillAssociationError("ASSOCIATION_NOT_FOUND", "association does not exist")
        return CharacterSkillCollection(
            tuple(item for item in self.associations if item.association_id != association_id)
        )

    def compatibility_for(
        self,
        current_versions: SkillArtifactVersionMetadata,
    ) -> dict[str, ArtifactDriftInspection]:
        return {
            item.association_id: item.compatibility_for(current_versions)
            for item in self.associations
        }

    def to_mapping(self) -> dict[str, object]:
        return {"associations": [item.to_mapping() for item in self.associations]}

    @staticmethod
    def _ordered(values: tuple[CharacterSkillAssociation, ...]) -> tuple[CharacterSkillAssociation, ...]:
        return tuple(sorted(values, key=lambda item: (item.order, item.association_id)))


def build_character_skill_association(
    artifact: SkillDesignArtifact,
    character_context: CharacterSkillDesignContext,
    alignment: CharacterSkillAlignmentResult,
    *,
    slot: SkillSlot | str,
    family: str,
    mode: str,
    display_summary: str,
) -> CharacterSkillAssociation:
    """Create a checked session association from an artifact and Character context."""

    binding = build_character_skill_artifact_binding(artifact, character_context, alignment)
    return CharacterSkillAssociation.from_artifact(
        artifact,
        binding,
        slot=slot,
        family=family,
        mode=mode,
        display_summary=display_summary,
    )


def slot_metadata() -> tuple[SkillSlotMetadata, ...]:
    """Return backend-authoritative ordered slot metadata."""

    return SKILL_SLOT_METADATA


def _resolve_slot(value: SkillSlot | str) -> SkillSlot:
    if isinstance(value, SkillSlot):
        return value
    if not isinstance(value, str):
        raise CharacterSkillAssociationError("UNKNOWN_SLOT", "slot must be a known string")
    try:
        return SkillSlot(value)
    except ValueError as error:
        raise CharacterSkillAssociationError("UNKNOWN_SLOT", "slot is not supported") from error


def _association_id(slot: SkillSlot, artifact_digest: str) -> str:
    return f"session-skill:{slot.value}:{artifact_digest}"


__all__ = [
    "CharacterSkillAssociation",
    "CharacterSkillAssociationError",
    "CharacterSkillCollection",
    "SKILL_SLOT_METADATA",
    "SLOT_ORDER",
    "SkillSlot",
    "SkillSlotMetadata",
    "build_character_skill_association",
    "slot_metadata",
]
