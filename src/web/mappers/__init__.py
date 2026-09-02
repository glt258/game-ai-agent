"""Explicit domain to Web DTO projections."""

from .canon import to_canon_detail, to_canon_list
from .character_generation import (
    to_character_generation_response,
    to_character_validation_response,
    to_error_response,
)
from .reference_characters import to_reference_detail, to_reference_list, to_reference_summary

__all__ = [
    "to_character_generation_response",
    "to_character_validation_response",
    "to_error_response",
    "to_reference_detail",
    "to_reference_list",
    "to_reference_summary",
    "to_canon_detail",
    "to_canon_list",
]
