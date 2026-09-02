from __future__ import annotations

from fastapi import APIRouter, Request

from ..mappers.character_generation import to_character_validation_response
from ..schemas.common import ErrorResponseDTO
from ..schemas.validation import (
    CharacterValidationRequestDTO,
    CharacterValidationResponseDTO,
)
from ..services.character_validation import CharacterValidationApplication

router = APIRouter(prefix="/characters", tags=["characters"])


def _service(request: Request) -> CharacterValidationApplication:
    return request.app.state.character_validation


@router.post(
    "/validate",
    response_model=CharacterValidationResponseDTO,
    responses={
        422: {"model": ErrorResponseDTO},
        500: {"model": ErrorResponseDTO},
    },
)
def validate(
    payload: CharacterValidationRequestDTO,
    request: Request,
) -> CharacterValidationResponseDTO:
    result = _service(request).validate(payload)
    return to_character_validation_response(result)


__all__ = ["router"]
