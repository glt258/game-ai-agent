from __future__ import annotations

from fastapi import APIRouter, Request

from ..errors import WebApplicationError, map_persistence_exception
from ..schemas.common import ErrorResponseDTO
from ..schemas.saved_characters import (
    SavedCharacterDTO,
    SavedCharacterListResponseDTO,
    SavedCharacterSaveRequestDTO,
    SavedCharacterSaveResponseDTO,
)
from ..services.saved_characters import StudioSaveService

router = APIRouter(prefix="/saved-characters", tags=["saved-characters"])


def _service(request: Request) -> StudioSaveService:
    return request.app.state.saved_characters


def _run(operation):
    try:
        return operation()
    except WebApplicationError:
        raise
    except Exception as error:
        raise map_persistence_exception(error) from error


@router.get("", response_model=SavedCharacterListResponseDTO)
def list_saved_characters(request: Request) -> SavedCharacterListResponseDTO:
    return _run(lambda: _service(request).list())


@router.get(
    "/{character_id}",
    response_model=SavedCharacterDTO,
    responses={404: {"model": ErrorResponseDTO}, 500: {"model": ErrorResponseDTO}},
)
def open_saved_character(character_id: str, request: Request) -> SavedCharacterDTO:
    return _run(lambda: _service(request).open(character_id))


@router.post(
    "",
    response_model=SavedCharacterSaveResponseDTO,
    status_code=201,
    responses={
        409: {"model": ErrorResponseDTO},
        422: {"model": ErrorResponseDTO},
        500: {"model": ErrorResponseDTO},
    },
)
def create_saved_character(
    payload: SavedCharacterSaveRequestDTO,
    request: Request,
) -> SavedCharacterSaveResponseDTO:
    return _run(lambda: _service(request).create(payload))


@router.put(
    "/{character_id}",
    response_model=SavedCharacterSaveResponseDTO,
    responses={
        409: {"model": ErrorResponseDTO},
        422: {"model": ErrorResponseDTO},
        500: {"model": ErrorResponseDTO},
    },
)
def save_saved_character(
    character_id: str,
    payload: SavedCharacterSaveRequestDTO,
    request: Request,
) -> SavedCharacterSaveResponseDTO:
    return _run(lambda: _service(request).update(character_id, payload))


__all__ = ["router"]
