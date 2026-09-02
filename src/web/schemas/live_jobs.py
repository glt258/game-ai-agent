from __future__ import annotations

from typing import Any, Literal

from .common import ErrorBodyDTO, WebModel

LiveJobStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
LiveJobKind = Literal["skill_playground", "character_skill_design"]


class LiveJobAcceptedDTO(WebModel):
    schema_version: Literal["web-live-skill-job/0.1"]
    job_id: str
    kind: LiveJobKind
    status: LiveJobStatus
    provider: str
    model: str
    poll_after_ms: int


class LiveJobStatusDTO(WebModel):
    schema_version: Literal["web-live-skill-job/0.1"]
    job_id: str
    kind: LiveJobKind
    status: LiveJobStatus
    provider: str
    model: str
    elapsed_ms: float
    result: dict[str, Any] | None = None
    error: ErrorBodyDTO | None = None


__all__ = ["LiveJobAcceptedDTO", "LiveJobKind", "LiveJobStatus", "LiveJobStatusDTO"]
