from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from ..errors import WebApplicationError
from ..schemas.canon import CanonEntityDetailDTO, CanonEntityListDTO, CanonEntityType
from ..schemas.common import ErrorResponseDTO
from ..services.canon import CanonEntityNotFoundError, CanonReadApplication

router = APIRouter(prefix="/canon", tags=["canon"])


def _service(request: Request) -> CanonReadApplication:
    return request.app.state.canon


@router.get("/entities", response_model=CanonEntityListDTO)
def list_canon_entities(
    request: Request,
    q: Annotated[str | None, Query(max_length=300)] = None,
    entity_type: Annotated[CanonEntityType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> CanonEntityListDTO:
    return _service(request).list(query=q, entity_type=entity_type, limit=limit)


@router.get(
    "/entities/{entity_id}",
    response_model=CanonEntityDetailDTO,
    responses={404: {"model": ErrorResponseDTO}, 500: {"model": ErrorResponseDTO}},
)
def get_canon_entity(entity_id: str, request: Request) -> CanonEntityDetailDTO:
    try:
        return _service(request).get(entity_id)
    except CanonEntityNotFoundError as error:
        raise WebApplicationError(
            "CANON_ENTITY_NOT_FOUND",
            "The requested Canon entity was not found.",
            status_code=404,
            stage="canon",
            retryable=False,
        ) from error


__all__ = ["router"]
