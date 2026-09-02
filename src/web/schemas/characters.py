from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from combat_semantics import CANONICAL_COMBAT_ROLES

from .common import (
    ModelInvocationDTO,
    PipelineStepDTO,
    ValidatorResultDTO,
    WebModel,
)

CombatRoleLiteral = Literal["main_dps", "sub_dps", "support", "healer", "control", "defense"]


class CombatRoleProfileDTO(WebModel):
    primary_role: CombatRoleLiteral | None = None
    secondary_roles: list[CombatRoleLiteral] = Field(default_factory=list)

    @field_validator("secondary_roles")
    @classmethod
    def unique_secondary_roles(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("secondary_roles must not contain duplicates")
        return value

    @model_validator(mode="after")
    def primary_not_secondary(self) -> "CombatRoleProfileDTO":
        if self.primary_role is not None and self.primary_role in self.secondary_roles:
            raise ValueError("primary_role must not also occur in secondary_roles")
        return self


class CharacterGenerationRequestDTO(WebModel):
    brief: str = Field(min_length=1, max_length=12000)
    hard_constraints: list[str] = Field(default_factory=list, max_length=32)
    soft_preferences: list[str] = Field(default_factory=list, max_length=32)
    forbidden_elements: list[str] = Field(default_factory=list, max_length=32)
    desired_connections: list[str] = Field(default_factory=list, max_length=32)
    request_id: str | None = Field(
        default=None,
        pattern=r"[A-Za-z][A-Za-z0-9_.-]*",
        max_length=128,
    )
    combat_role_profile: CombatRoleProfileDTO | None = None

    @field_validator("brief")
    @classmethod
    def non_blank_brief(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("brief must be a non-empty string")
        return value

    @field_validator(
        "hard_constraints",
        "soft_preferences",
        "forbidden_elements",
        "desired_connections",
    )
    @classmethod
    def clean_string_lists(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            item = item.strip()
            if not item:
                raise ValueError("list items must be non-empty strings")
            if len(item) > 2000:
                raise ValueError("list items are too long")
            cleaned.append(item)
        return cleaned


class CanonBasisDTO(WebModel):
    source_id: str
    supports: list[str] = Field(default_factory=list)
    source_type: str | None = None


class StoryLinkDTO(WebModel):
    target_id: str
    relation: str
    status: str


class RelationshipDTO(WebModel):
    target_id: str | None = None
    description: str | None = None
    status: str | None = None
    type: str | None = None


class CharacterDraftDTO(WebModel):
    draft_id: str
    status: str
    name: str
    canonical_character_id: str | None = None
    age: int | None = None
    age_range: str | None = None
    gender: str | None = None
    faction_id: str | None = None
    occupation: str
    social_role: str
    combat_role_profile: CombatRoleProfileDTO
    design_pitch: str
    personality: list[str]
    background: str
    story_hook: str
    relationships: list[RelationshipDTO]
    ability_concept: str
    knowledge_scope: str
    canon_basis: list[CanonBasisDTO]
    new_design_elements: list[str]
    open_questions: list[str]
    constraint_notes: list[str]
    story_link: StoryLinkDTO | None = None
    proposed_new_content: list[str]


class CharacterIntentDTO(WebModel):
    role_type: str
    rarity: int | None = None
    target_audience: str
    personality_keywords: list[str]
    design_goals: list[str]
    forbidden_patterns: list[str]
    element: str | None = None
    raw_request: str
    combat_role_profile: CombatRoleProfileDTO
    requested_affiliation_id: str | None = None


class CharacterAffiliationContextDTO(WebModel):
    faction_id: str
    name: str
    faction_type: str
    summary: str
    typical_roles: list[str]
    semantic_terms: list[str]
    division_names: list[str]


class CharacterPlanDTO(WebModel):
    parsed_intent: CharacterIntentDTO
    combat_role_profile: CombatRoleProfileDTO
    generation_constraints: list[str]
    recommended_traits: list[str]
    expected_affiliation_id: str | None = None
    affiliation_context: CharacterAffiliationContextDTO | None = None


class ToolAuditDTO(WebModel):
    round: int
    tool_name: str
    result_status: str
    source_ids: list[str]
    denied_requested_ids: list[str]
    resolver_reason_code: str | None = None


class ContractRecoveryDTO(WebModel):
    status: str
    attempted: bool
    missing_required: list[str]
    unknown_fields: list[str]
    invalid_fields: list[str]
    recovered_fields: list[str]
    discarded_unknown_fields: list[str]


class GenerationAuditDTO(WebModel):
    request_id: str
    tool_rounds: int
    tool_calls: list[ToolAuditDTO]
    source_ids: list[str]
    reference_ids: list[str]
    normalized_fields: list[str]
    contract_recovery: ContractRecoveryDTO


class RepairDTO(WebModel):
    repair_performed: bool
    repair_attempts: int
    status: str
    repair_succeeded: bool
    changed_fields: list[str]
    initial_status: str
    final_status: str
    failure_code: str | None = None


class CombatDTO(WebModel):
    combat_role_profile: CombatRoleProfileDTO
    skill_shadow_available: bool
    skill_shadow_status: str
    skill_summary: str | None = None
    skill_evaluation: dict[str, Any] | None = None


class RawCharacterResultDTO(WebModel):
    draft: dict[str, Any]
    plan: dict[str, Any] | None
    generation_audit: dict[str, Any]
    authoring_audit: dict[str, Any]


class CharacterGenerationResponseDTO(WebModel):
    schema_version: Literal["web-character-generation/0.1"]
    status: Literal["completed"]
    request: CharacterGenerationRequestDTO
    draft: CharacterDraftDTO
    plan: CharacterPlanDTO | None
    combat: CombatDTO
    canon_basis: list[CanonBasisDTO]
    validators: list[ValidatorResultDTO]
    repair: RepairDTO
    model_invocations: list[ModelInvocationDTO]
    pipeline: list[PipelineStepDTO]
    audit: GenerationAuditDTO
    raw_data: RawCharacterResultDTO


__all__ = [
    "CANONICAL_COMBAT_ROLES",
    "CanonBasisDTO",
    "CharacterGenerationRequestDTO",
    "CharacterGenerationResponseDTO",
    "CharacterPlanDTO",
    "CombatDTO",
]
