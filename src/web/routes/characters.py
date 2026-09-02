from __future__ import annotations

from fastapi import APIRouter, Request

from ..mappers.character_generation import to_character_generation_response, to_error_response
from ..schemas.character_skill import (
    CharacterKitRoleCoverageRequestDTO,
    CharacterKitRoleCoverageResponseDTO,
    CharacterKitValidationRequestDTO,
    CharacterKitValidationResponseDTO,
    CharacterSkillContextRequestDTO,
    CharacterSkillContextResponseDTO,
    CharacterSkillDesignRequestDTO,
    CharacterSkillDesignResponseDTO,
    CharacterSkillMetaDTO,
)
from ..schemas.characters import CharacterGenerationRequestDTO, CharacterGenerationResponseDTO
from ..schemas.common import ErrorResponseDTO
from ..schemas.live_jobs import LiveJobAcceptedDTO, LiveJobStatusDTO
from ..services.character_generation import CharacterGenerationApplication
from ..services.character_kit_evaluation import CharacterKitRoleCoverageApplication
from ..services.character_skill_design import CharacterSkillDesignApplication
from ..services.live_jobs import LiveJobRegistry, LiveJobSnapshot

router = APIRouter(prefix="/characters", tags=["characters"])


def _service(request: Request) -> CharacterGenerationApplication:
    return request.app.state.character_generation


def _skill_service(request: Request) -> CharacterSkillDesignApplication:
    return request.app.state.character_skill_design


def _kit_evaluation_service(request: Request) -> CharacterKitRoleCoverageApplication:
    return request.app.state.character_kit_role_coverage


def _jobs(request: Request) -> LiveJobRegistry:
    return request.app.state.live_jobs


def _accepted(snapshot: LiveJobSnapshot) -> LiveJobAcceptedDTO:
    return LiveJobAcceptedDTO(
        schema_version="web-live-skill-job/0.1",
        job_id=snapshot.job_id,
        kind=snapshot.kind,
        status=snapshot.status,
        provider=snapshot.provider,
        model=snapshot.model,
        poll_after_ms=snapshot.poll_after_ms,
    )


def _status(snapshot: LiveJobSnapshot) -> LiveJobStatusDTO:
    result = snapshot.result.model_dump() if snapshot.result is not None else None
    error = None
    if snapshot.error is not None:
        error = to_error_response(snapshot.error).error
    return LiveJobStatusDTO(
        schema_version="web-live-skill-job/0.1",
        job_id=snapshot.job_id,
        kind=snapshot.kind,
        status=snapshot.status,
        provider=snapshot.provider,
        model=snapshot.model,
        elapsed_ms=snapshot.elapsed_ms,
        result=result,
        error=error,
    )


@router.post(
    "/generate",
    response_model=CharacterGenerationResponseDTO,
    responses={
        422: {"model": ErrorResponseDTO},
        500: {"model": ErrorResponseDTO},
        502: {"model": ErrorResponseDTO},
        503: {"model": ErrorResponseDTO},
        504: {"model": ErrorResponseDTO},
    },
)
def generate(
    payload: CharacterGenerationRequestDTO,
    request: Request,
) -> CharacterGenerationResponseDTO:
    result = _service(request).generate(payload)
    return to_character_generation_response(payload, result)


@router.post(
    "/skill-context",
    response_model=CharacterSkillContextResponseDTO,
    responses={422: {"model": ErrorResponseDTO}, 500: {"model": ErrorResponseDTO}},
)
def skill_context(
    payload: CharacterSkillContextRequestDTO,
    request: Request,
) -> CharacterSkillContextResponseDTO:
    return _skill_service(request).context(payload)


@router.get(
    "/skill-meta",
    response_model=CharacterSkillMetaDTO,
)
def skill_meta(request: Request) -> CharacterSkillMetaDTO:
    return _skill_service(request).meta()


@router.post(
    "/skill-kit/validate",
    response_model=CharacterKitValidationResponseDTO,
    responses={422: {"model": ErrorResponseDTO}},
)
def validate_skill_kit(
    payload: CharacterKitValidationRequestDTO,
    request: Request,
) -> CharacterKitValidationResponseDTO:
    return _skill_service(request).validate_kit(payload)


@router.post(
    "/character-kit/evaluate",
    response_model=CharacterKitRoleCoverageResponseDTO,
    responses={422: {"model": ErrorResponseDTO}},
)
def evaluate_character_kit_role_coverage(
    payload: CharacterKitRoleCoverageRequestDTO,
    request: Request,
) -> CharacterKitRoleCoverageResponseDTO:
    return _kit_evaluation_service(request).evaluate(payload)


@router.post(
    "/skill-design",
    response_model=CharacterSkillDesignResponseDTO,
    responses={
        422: {"model": ErrorResponseDTO},
        500: {"model": ErrorResponseDTO},
        502: {"model": ErrorResponseDTO},
        503: {"model": ErrorResponseDTO},
        504: {"model": ErrorResponseDTO},
    },
)
def skill_design(
    payload: CharacterSkillDesignRequestDTO,
    request: Request,
) -> CharacterSkillDesignResponseDTO:
    return _skill_service(request).design(payload)


@router.post(
    "/skill-design/jobs",
    response_model=LiveJobAcceptedDTO,
    status_code=202,
    responses={422: {"model": ErrorResponseDTO}, 429: {"model": ErrorResponseDTO}},
)
def submit_skill_design_job(
    payload: CharacterSkillDesignRequestDTO,
    request: Request,
) -> LiveJobAcceptedDTO:
    return _accepted(_skill_service(request).submit_live_job(payload, _jobs(request)))


@router.get(
    "/skill-design/jobs/{job_id}",
    response_model=LiveJobStatusDTO,
    responses={404: {"model": ErrorResponseDTO}},
)
def get_skill_design_job(job_id: str, request: Request) -> LiveJobStatusDTO:
    return _status(_jobs(request).get(job_id))
