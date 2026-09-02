from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from reference_corpus.enums import NormalizedRole
from reference_corpus.errors import ReferenceNotFoundError

from ..errors import WebApplicationError
from ..schemas.common import ErrorResponseDTO
from ..schemas.reference_characters import ReferenceCharacterDetailDTO, ReferenceCharacterListDTO
from ..services.reference_characters import ReferenceCharacterReadApplication

router = APIRouter(prefix="/reference-characters", tags=["reference-characters"])


def _service(request: Request) -> ReferenceCharacterReadApplication:
    return request.app.state.reference_characters


@router.get("", response_model=ReferenceCharacterListDTO)
def list_reference_characters(
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    ip: Annotated[str | None, Query(max_length=200)] = None,
    combat_role: NormalizedRole | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReferenceCharacterListDTO:
    return _service(request).list(query=q, ip=ip, combat_role=combat_role, limit=limit)


@router.get(
    "/{reference_id}",
    response_model=ReferenceCharacterDetailDTO,
    responses={404: {"model": ErrorResponseDTO}, 500: {"model": ErrorResponseDTO}},
)
def get_reference_character(
    reference_id: str,
    request: Request,
) -> ReferenceCharacterDetailDTO:
    try:
        return _service(request).get(reference_id)
    except ReferenceNotFoundError as error:
        raise WebApplicationError(
            "REFERENCE_CHARACTER_NOT_FOUND",
            "The requested reference character was not found.",
            status_code=404,
            stage="reference_corpus",
            retryable=False,
        ) from error


__all__ = ["router"]
