from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .character_skill import (
    CharacterKitStructuralValidationDTO,
    CharacterSkillAssociationDTO,
)
from .characters import CharacterDraftDTO, CharacterGenerationRequestDTO, CharacterPlanDTO
from .common import WebModel
from .skills import ArtifactCompatibility


class SavedCharacterAssociationDTO(CharacterSkillAssociationDTO):
    artifact_compatibility: ArtifactCompatibility


class SavedCharacterRevisionDTO(WebModel):
    revision_id: str
    kind: Literal["GENERATED", "EDITED"]
    parent_revision_id: str | None
    created_at: str
    is_current: bool


class SavedCharacterSummaryDTO(WebModel):
    character_id: str
    display_name: str
    current_revision_id: str
    revision_kind: Literal["GENERATED", "EDITED"]
    created_at: str
    updated_at: str
    has_kit: bool
    skill_count: int


class SavedCharacterHistorySummaryDTO(WebModel):
    report_family: Literal["skill_evaluation", "alignment", "role_coverage"]
    report_id: str
    created_at: str
    target: str
    version: str
    status: str


class SavedCharacterDerivedStateDTO(WebModel):
    freshness_by_association_id: dict[str, Literal["current", "stale"]] = Field(
        default_factory=dict
    )
    compatibility_by_association_id: dict[str, str] = Field(default_factory=dict)
    structural_validation: CharacterKitStructuralValidationDTO | None = None


class SavedCharacterDTO(WebModel):
    character_id: str
    current_revision_id: str
    current_kit_assignment_id: str | None
    created_at: str
    updated_at: str
    revision: SavedCharacterRevisionDTO
    draft: CharacterDraftDTO
    request: CharacterGenerationRequestDTO
    plan: CharacterPlanDTO | None
    associations: list[SavedCharacterAssociationDTO]
    kit: dict[str, Any] | None
    derived: SavedCharacterDerivedStateDTO
    history: list[SavedCharacterHistorySummaryDTO]


class SavedCharacterListResponseDTO(WebModel):
    schema_version: Literal["web-saved-character-list/0.1"]
    characters: list[SavedCharacterSummaryDTO]
    total: int


class SavedCharacterSaveRequestDTO(WebModel):
    schema_version: Literal["web-saved-character-save/0.1"]
    request: CharacterGenerationRequestDTO
    draft: CharacterDraftDTO
    plan: CharacterPlanDTO | None = None
    associations: list[SavedCharacterAssociationDTO] = Field(default_factory=list, max_length=16)
    expected_current_revision_id: str | None = None
    expected_current_kit_assignment_id: str | None = None


class SavedCharacterSaveResponseDTO(WebModel):
    schema_version: Literal["web-saved-character-save/0.1"]
    saved: SavedCharacterDTO


__all__ = [
    "SavedCharacterDTO",
    "SavedCharacterAssociationDTO",
    "SavedCharacterDerivedStateDTO",
    "SavedCharacterHistorySummaryDTO",
    "SavedCharacterListResponseDTO",
    "SavedCharacterRevisionDTO",
    "SavedCharacterSaveRequestDTO",
    "SavedCharacterSaveResponseDTO",
    "SavedCharacterSummaryDTO",
]
