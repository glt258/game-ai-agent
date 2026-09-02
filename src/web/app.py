from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from .errors import WebApplicationError
from .mappers.character_generation import to_error_response
from .routes.canon import router as canon_router
from .routes.characters import router as characters_router
from .routes.reference_characters import router as reference_characters_router
from .routes.saved_characters import router as saved_characters_router
from .routes.skills import router as skills_router
from .routes.system import router as system_router
from .routes.validation import router as validation_router
from .schemas.common import ErrorBodyDTO, ErrorResponseDTO
from .services.canon import CanonReadApplication
from .services.character_generation import CharacterGenerationApplication
from .services.character_kit_evaluation import CharacterKitRoleCoverageApplication
from .services.character_skill_design import CharacterSkillDesignApplication
from .services.character_validation import CharacterValidationApplication
from .services.live_jobs import LiveJobRegistry
from .services.reference_characters import ReferenceCharacterReadApplication
from .services.saved_characters import StudioSaveService
from .services.skill_playground import SkillPlaygroundApplication


def _database_path(value: str | Path | None) -> Path:
    if value is not None:
        return Path(value)
    configured = os.environ.get("GAME_AI_AGENT_DB_PATH")
    if configured:
        return Path(configured)
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    return (
        Path(root) / "game-ai-agent" / "studio.db"
        if root
        else Path.home() / ".game-ai-agent" / "studio.db"
    )


def _validation_error_response(error: RequestValidationError) -> JSONResponse:
    fields: list[dict[str, str]] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg")
        fields.append(
            {
                "field": location,
                "message": message if isinstance(message, str) else "invalid request field",
            }
        )
    body = ErrorResponseDTO(
        error=ErrorBodyDTO(
            code="REQUEST_VALIDATION_ERROR",
            message="Request validation failed.",
            stage="request",
            retryable=False,
            details={"fields": fields},
        )
    )
    return JSONResponse(status_code=422, content=body.model_dump())


def create_app(
    generation_service: CharacterGenerationApplication | None = None,
    *,
    validation_service: CharacterValidationApplication | None = None,
    reference_service: ReferenceCharacterReadApplication | None = None,
    canon_service: CanonReadApplication | None = None,
    skill_playground_service: SkillPlaygroundApplication | None = None,
    character_skill_design_service: CharacterSkillDesignApplication | None = None,
    character_kit_role_coverage_service: CharacterKitRoleCoverageApplication | None = None,
    live_job_registry: LiveJobRegistry | None = None,
    generation_mode: str = "offline",
    cors_origins: Sequence[str] = (),
    database_path: str | Path | None = None,
) -> FastAPI:
    """Build an isolated Web app without import-time provider calls."""

    service = generation_service or CharacterGenerationApplication(
        generation_mode=generation_mode,
    )
    validation = validation_service or CharacterValidationApplication(
        checker=service.checker,
        evaluation_runner=service.evaluation_runner,
    )
    references = reference_service or ReferenceCharacterReadApplication()
    canon = canon_service or CanonReadApplication()
    skills = skill_playground_service or SkillPlaygroundApplication()
    character_skills = character_skill_design_service or CharacterSkillDesignApplication(
        skill_playground=skills,
    )
    kit_role_coverage = character_kit_role_coverage_service or CharacterKitRoleCoverageApplication()
    live_jobs = live_job_registry or LiveJobRegistry.from_environment()
    saved_characters = StudioSaveService(_database_path(database_path))
    app = FastAPI(
        title="Game AI Agent Studio Web API",
        version="0.1.0",
        description="Thin HTTP adapter over the existing character authoring runtime.",
    )
    app.state.character_generation = service
    app.state.character_validation = validation
    app.state.reference_characters = references
    app.state.canon = canon
    app.state.skill_playground = skills
    app.state.character_skill_design = character_skills
    app.state.character_kit_role_coverage = kit_role_coverage
    app.state.live_jobs = live_jobs
    app.state.saved_characters = saved_characters
    app.include_router(system_router, prefix="/api")
    app.include_router(characters_router, prefix="/api")
    app.include_router(validation_router, prefix="/api")
    app.include_router(reference_characters_router, prefix="/api")
    app.include_router(canon_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")
    app.include_router(saved_characters_router, prefix="/api")

    # Opening a UoW here applies schema creation/migration before serving requests.
    from persistence import PersistenceUnitOfWork

    with PersistenceUnitOfWork(saved_characters.database_path):
        pass
    app.router.add_event_handler("shutdown", live_jobs.shutdown)

    origins = tuple(origin for origin in cors_origins if origin)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(WebApplicationError)
    async def web_error_handler(_request: Request, error: WebApplicationError) -> JSONResponse:
        payload = to_error_response(error)
        return JSONResponse(status_code=error.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return _validation_error_response(error)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _error: Exception) -> JSONResponse:
        payload = ErrorResponseDTO(
            error=ErrorBodyDTO(
                code="INTERNAL_ERROR",
                message="The Web application could not complete the request.",
                stage="web",
                retryable=False,
                details={},
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    return app


__all__ = ["create_app"]
