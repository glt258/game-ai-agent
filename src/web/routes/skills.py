from __future__ import annotations

from fastapi import APIRouter, Request

from ..mappers.character_generation import to_error_response
from ..schemas.common import ErrorResponseDTO
from ..schemas.live_jobs import LiveJobAcceptedDTO, LiveJobStatusDTO
from ..schemas.skills import (
    SkillPlaygroundMetaDTO,
    SkillPlaygroundRequestDTO,
    SkillPlaygroundResponseDTO,
)
from ..services.live_jobs import LiveJobRegistry, LiveJobSnapshot
from ..services.skill_playground import SkillPlaygroundApplication

router = APIRouter(prefix="/skills/playground", tags=["skills"])


def _service(request: Request) -> SkillPlaygroundApplication:
    return request.app.state.skill_playground


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


@router.get("/meta", response_model=SkillPlaygroundMetaDTO)
def get_meta(request: Request) -> SkillPlaygroundMetaDTO:
    return _service(request).meta()


@router.post("/run", response_model=SkillPlaygroundResponseDTO)
def run_playground(
    payload: SkillPlaygroundRequestDTO,
    request: Request,
) -> SkillPlaygroundResponseDTO:
    return _service(request).run(payload)


@router.post(
    "/jobs",
    response_model=LiveJobAcceptedDTO,
    status_code=202,
    responses={422: {"model": ErrorResponseDTO}, 429: {"model": ErrorResponseDTO}},
)
def submit_live_job(
    payload: SkillPlaygroundRequestDTO,
    request: Request,
) -> LiveJobAcceptedDTO:
    return _accepted(_service(request).submit_live_job(payload, _jobs(request)))


@router.get(
    "/jobs/{job_id}",
    response_model=LiveJobStatusDTO,
    responses={404: {"model": ErrorResponseDTO}},
)
def get_live_job(job_id: str, request: Request) -> LiveJobStatusDTO:
    return _status(_jobs(request).get(job_id))


__all__ = ["router"]
