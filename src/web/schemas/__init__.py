"""Stable Web DTOs for the Game AI Agent Studio backend."""

from .characters import (
    CharacterGenerationRequestDTO,
    CharacterGenerationResponseDTO,
)
from .common import ErrorResponseDTO, HealthResponseDTO
from .validation import (
    CharacterValidationRequestDTO,
    CharacterValidationResponseDTO,
)

__all__ = [
    "CharacterGenerationRequestDTO",
    "CharacterGenerationResponseDTO",
    "CharacterValidationRequestDTO",
    "CharacterValidationResponseDTO",
    "ErrorResponseDTO",
    "HealthResponseDTO",
]
