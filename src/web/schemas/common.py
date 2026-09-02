from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WebModel(BaseModel):
    """Base model that rejects accidental additions to the public contract."""

    model_config = ConfigDict(extra="forbid")


class HealthResponseDTO(WebModel):
    status: Literal["ok"]
    service: str
    api_version: str
    character_generation_available: bool


class PipelineStepDTO(WebModel):
    id: str
    label: str
    status: Literal["passed", "failed", "repaired", "skipped"]
    detail: str | None = None


class ValidatorResultDTO(WebModel):
    name: str
    status: Literal["passed", "warning", "failed", "not_available"]
    code: str | None = None
    severity: str | None = None
    blocking: bool | None = None
    field_path: str | None = None
    message: str
    evidence_ids: list[str] = Field(default_factory=list)


class ModelUsageDTO(WebModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ModelInvocationDTO(WebModel):
    provider: str
    model: str
    turn_number: int
    outcome: str
    latency_ms: float | None = None
    retry_count: int
    finish_reason: str | None = None
    tool_call_count: int
    usage: ModelUsageDTO | None = None
    purpose: str
    provider_status_code: int | None = None
    provider_retryable: bool | None = None


class ErrorAuditDTO(WebModel):
    stage: str | None = None
    model_invocations: list[ModelInvocationDTO] = Field(default_factory=list)


class ErrorBodyDTO(WebModel):
    code: str
    message: str
    stage: str | None = None
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
    audit: ErrorAuditDTO | None = None


class ErrorResponseDTO(WebModel):
    error: ErrorBodyDTO
