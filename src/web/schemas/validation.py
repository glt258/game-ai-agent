from __future__ import annotations

from typing import Literal

from pydantic import Field

from .characters import CharacterDraftDTO, CharacterGenerationRequestDTO, CombatRoleProfileDTO
from .common import PipelineStepDTO, ValidatorResultDTO, WebModel


class CharacterValidationRequestDTO(WebModel):
    """Only the request context and edited draft cross the validation seam."""

    request: CharacterGenerationRequestDTO
    draft: CharacterDraftDTO


class CanonValidationSummaryDTO(WebModel):
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)
    infos: int = Field(ge=0)


class CanonValidationDTO(WebModel):
    status: Literal["passed", "warning", "failed"]
    checked_source_ids: list[str]
    summary: CanonValidationSummaryDTO
    findings: list[ValidatorResultDTO]


class ValidationSummaryDTO(WebModel):
    status: Literal["passed", "failed"]
    blocking: bool
    validator_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class CharacterValidationResponseDTO(WebModel):
    schema_version: Literal["web-character-validation/0.1"]
    status: Literal["passed", "failed"]
    request_id: str
    draft_id: str
    validators: list[ValidatorResultDTO]
    canon: CanonValidationDTO
    combat: CombatRoleProfileDTO
    pipeline: list[PipelineStepDTO]
    summary: ValidationSummaryDTO


__all__ = [
    "CanonValidationDTO",
    "CanonValidationSummaryDTO",
    "CharacterValidationRequestDTO",
    "CharacterValidationResponseDTO",
    "ValidationSummaryDTO",
]
