from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .common import PipelineStepDTO, WebModel

SkillFamily = Literal[
    "main_dps", "sub_dps", "support", "healer", "control", "defense", "basic_passive"
]
SkillMode = Literal["active", "passive", "reaction"]
SkillSlot = Literal["primary", "secondary", "passive", "utility"]
OutputLanguage = Literal["auto", "en", "zh-CN"]
SkillExecutionMode = Literal["offline", "live"]
SkillProviderName = Literal["deepseek", "opencode_go"]
ArtifactCompatibility = Literal[
    "CURRENT_COMPATIBLE",
    "REEVALUATION_RECOMMENDED",
    "REALIGNMENT_RECOMMENDED",
    "RECOMPILE_REQUIRED",
    "UNSUPPORTED_VERSION",
    "CONTEXT_PROJECTION_DRIFT",
]


class SkillPlaygroundRequestDTO(WebModel):
    family: SkillFamily
    mode: SkillMode
    brief: str = Field(min_length=1, max_length=2000)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    language: OutputLanguage = "auto"
    model: str = Field(default="web-offline-fixture", min_length=1, max_length=100)
    preset_id: str | None = Field(default=None, max_length=100)
    execution_mode: SkillExecutionMode = "offline"
    provider: SkillProviderName = "opencode_go"

    @field_validator("brief")
    @classmethod
    def non_blank_brief(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("brief must not be blank")
        return value

    @field_validator("model")
    @classmethod
    def allowlisted_model(cls, value: str) -> str:
        if value not in {
            "web-offline-fixture",
            "deepseek-v4-pro",
            "deepseek-chat",
            "mimo-v2.5",
            "mimo-v2.5-pro",
        }:
            raise ValueError("model is not allowlisted")
        return value

    @field_validator("constraints")
    @classmethod
    def bounded_constraints(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("constraints must be non-empty and bounded")
        return values

    @model_validator(mode="after")
    def validate_family_mode(self) -> "SkillPlaygroundRequestDTO":
        if self.family == "basic_passive" and self.mode != "passive":
            raise ValueError("basic_passive requires passive mode")
        return self


class SkillFamilyOptionDTO(WebModel):
    id: SkillFamily
    label: str
    description: str
    role: str
    default_mode: SkillMode


class SkillPlaygroundMetaDTO(WebModel):
    schema_version: Literal["web-skill-playground-meta/0.1"]
    families: list[SkillFamilyOptionDTO]
    modes: list[SkillMode]
    examples: list[str]
    provider_mode: Literal["offline_fixture", "injected", "unavailable"]


class SkillFindingDTO(WebModel):
    code: str
    field_path: str
    blocking: bool
    repairable: bool
    evidence_refs: list[str] = Field(default_factory=list)
    priority: int


class SkillEvaluationDTO(WebModel):
    outcome: Literal["PASS", "REPAIR", "FAIL", "NOT_RUN"]
    blocking: bool
    repair_allowed: bool
    findings: list[SkillFindingDTO]
    candidate_digest: str | None
    report_digest: str | None
    diagnostics: dict[str, Any] | None


class SkillProviderDTO(WebModel):
    mode: Literal["offline_fixture", "injected", "live", "unavailable"]
    called: bool
    outcome: str
    transport_attempts: int
    latency_ms: float | None


class SkillArtifactVersionsDTO(WebModel):
    semantic_ir_schema_version: str
    compiler_version: str
    canonical_skillkit_schema_version: str
    skill_evaluator_version: str
    character_alignment_version: str | None = None
    character_context_projection_version: str | None = None


class SkillPlaygroundResponseDTO(WebModel):
    schema_version: Literal["web-skill-playground/0.1"]
    status: Literal["completed", "failed"]
    input: SkillPlaygroundRequestDTO
    semantic_ir: dict[str, Any] | None
    skillkit: dict[str, Any] | None
    evaluation: SkillEvaluationDTO
    pipeline: list[PipelineStepDTO]
    provider: SkillProviderDTO
    evidence: dict[str, Any]
    artifact_versions: SkillArtifactVersionsDTO | None = None
    artifact_compatibility: ArtifactCompatibility | None = None


__all__ = [
    "SkillFamily",
    "SkillFamilyOptionDTO",
    "SkillArtifactVersionsDTO",
    "SkillMode",
    "SkillExecutionMode",
    "SkillProviderName",
    "SkillSlot",
    "SkillPlaygroundMetaDTO",
    "SkillPlaygroundRequestDTO",
    "SkillPlaygroundResponseDTO",
]
