from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas.common import ErrorResponseDTO, HealthResponseDTO

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponseDTO,
    responses={500: {"model": ErrorResponseDTO}},
)
def health(request: Request) -> HealthResponseDTO:
    return HealthResponseDTO(
        status="ok",
        service="game-ai-agent-web",
        api_version="v0.1",
        character_generation_available=request.app.state.character_generation is not None,
    )
