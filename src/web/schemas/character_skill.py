from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .characters import (
    CharacterDraftDTO,
    CharacterGenerationRequestDTO,
    CharacterPlanDTO,
    CombatRoleProfileDTO,
)
from .common import PipelineStepDTO, WebModel
from .skills import (
    ArtifactCompatibility,
    SkillArtifactVersionsDTO,
    SkillEvaluationDTO,
    SkillFamily,
    SkillMode,
    SkillPlaygroundRequestDTO,
    SkillProviderDTO,
    SkillSlot,
)


class CharacterSkillSlotDTO(WebModel):
    id: SkillSlot
    order: int
    label: str
    description: str
    max_items: int | None


class CharacterSkillMetaDTO(WebModel):
    schema_version: Literal["web-character-skill-meta/0.1"]
    slots: list[CharacterSkillSlotDTO]


class CharacterKitValidationRequestDTO(WebModel):
    schema_version: Literal["web-character-kit-validation/0.1"]
    kit: dict[str, Any]


class CharacterKitStructuralFindingDTO(WebModel):
    code: str
    field_path: str
    message: str
    blocking: bool


class CharacterKitStructuralValidationDTO(WebModel):
    status: Literal["PASS", "FAIL"]
    blocking: bool
    findings: list[CharacterKitStructuralFindingDTO]


class CharacterKitValidationResponseDTO(WebModel):
    schema_version: Literal["web-character-kit-validation/0.1"]
    contract_version: str
    associations: list[dict[str, Any]]
    structural_validation: CharacterKitStructuralValidationDTO
    kit_digest: str


class CharacterKitRoleCoverageEvidenceDTO(WebModel):
    role: str
    association_id: str
    artifact_digest: str
    operation: str
    artifact_paths: list[str]
    centrality: str | None
    family: str
    mode: str


class CharacterKitRoleCoverageItemDTO(WebModel):
    role: str
    supported: bool
    evidence: list[CharacterKitRoleCoverageEvidenceDTO]


class CharacterKitCoverageDTO(WebModel):
    primary: CharacterKitRoleCoverageItemDTO
    secondary: list[CharacterKitRoleCoverageItemDTO]
    observed_roles: list[str]


class CharacterKitEvaluationFindingDTO(WebModel):
    code: str
    kind: Literal[
        "supporting_evidence",
        "missing_evidence",
        "direct_contradiction",
        "not_evaluated",
    ]
    blocking: bool
    character_role: str | None
    artifact_evidence: list[CharacterKitRoleCoverageEvidenceDTO]
    artifact_digests: list[str]
    field_path: str
    message: str


class CharacterKitRoleCoverageDTO(WebModel):
    status: Literal["PASS", "PARTIAL", "FAIL", "NOT_EVALUATED"]
    kit_digest: str
    evaluation_context_fingerprint: str
    evaluator_version: str
    coverage: CharacterKitCoverageDTO
    findings: list[CharacterKitEvaluationFindingDTO]
    report_digest: str
    blocking: bool
    summary: str


class CharacterKitRoleCoverageResponseDTO(WebModel):
    schema_version: Literal["web-character-kit-role-coverage/0.1"]
    contract_version: str
    kit_digest: str
    structural_validation: CharacterKitStructuralValidationDTO
    role_coverage: CharacterKitRoleCoverageDTO


class CharacterSkillContextRequestDTO(WebModel):
    """Current typed Character input; no generation response metadata crosses this seam."""

    request: CharacterGenerationRequestDTO
    draft: CharacterDraftDTO
    plan: CharacterPlanDTO | None = None


class CharacterSkillContextSummaryDTO(WebModel):
    character_name: str
    combat_role_profile: CombatRoleProfileDTO
    ability_concept: str
    design_pitch: str
    skill_relevant_hard_constraints: list[str] = Field(default_factory=list)
    skill_relevant_forbidden_elements: list[str] = Field(default_factory=list)
    relevant_desired_connections: list[str] = Field(default_factory=list)
    affiliation_context: dict[str, Any] | None = None
    projection_version: str


class CharacterSkillContextResponseDTO(WebModel):
    schema_version: Literal["web-character-skill-context/0.1"]
    source_context_fingerprint: str
    character_context_summary: CharacterSkillContextSummaryDTO


class CharacterSkillDesignRequestDTO(WebModel):
    character: CharacterSkillContextRequestDTO
    skill: SkillPlaygroundRequestDTO


class CharacterSkillEvidenceDTO(WebModel):
    role: str
    operation: str
    family: str
    mode: str
    artifact_paths: list[str]
    centrality: str | None


class CharacterSkillAlignmentFindingDTO(WebModel):
    code: str
    kind: Literal[
        "supporting_evidence", "missing_evidence", "direct_contradiction", "not_evaluated"
    ]
    blocking: bool
    character_role: str | None
    skill_evidence: list[CharacterSkillEvidenceDTO]
    field_path: str
    artifact_path: str | None
    message: str


class CharacterSkillAlignmentResultDTO(WebModel):
    status: Literal["PASS", "FAIL", "PARTIAL", "NOT_EVALUATED"]
    coverage: Literal["primary", "secondary", "none", "not_evaluated"]
    findings: list[CharacterSkillAlignmentFindingDTO]
    blocking: bool
    summary: str
    artifact_digest: str | None
    source_context_fingerprint: str
    skill_roles: list[str]
    evidence: list[CharacterSkillEvidenceDTO]


class SkillArtifactIdentityDTO(WebModel):
    artifact_digest: str
    canonical_schema_version: str
    artifact_kind: Literal["skill_design"]


class CompilerProvenanceEntryDTO(WebModel):
    canonical_path: str
    source_kind: str
    source_path: str | None = None
    rule_id: str | None = None


class CompilerProvenanceDTO(WebModel):
    compiler_version: str
    entries: list[CompilerProvenanceEntryDTO]


class SkillArtifactProvenanceDTO(WebModel):
    compiler_provenance: CompilerProvenanceDTO
    run_id: str | None = None
    provider: str | None = None
    model: str | None = None


class SkillArtifactFindingDTO(WebModel):
    code: str
    field_path: str
    blocking: bool
    repairable: bool
    evidence_refs: list[str]
    authorized_paths: list[str]
    priority: int


class SkillArtifactEvaluationDTO(WebModel):
    outcome: Literal["PASS", "REPAIR", "FAIL"]
    blocking: bool
    repair_allowed: bool
    findings: list[SkillArtifactFindingDTO]
    candidate_digest: str
    context_digest: str
    report_digest: str
    base_digest: str
    finding_codes: list[str]


class SkillDesignArtifactDTO(WebModel):
    artifact_contract_version: str
    identity: SkillArtifactIdentityDTO
    versions: SkillArtifactVersionsDTO
    semantic_source: dict[str, Any]
    semantic_source_digest: str
    canonical_artifact: dict[str, Any]
    original_evaluation: SkillArtifactEvaluationDTO
    provenance: SkillArtifactProvenanceDTO


class CharacterSkillArtifactBindingDTO(WebModel):
    binding_contract_version: str
    artifact_digest: str
    source_context_fingerprint: str
    alignment: CharacterSkillAlignmentResultDTO
    alignment_version: str
    character_context_projection_version: str


class CharacterSkillAssociationDTO(WebModel):
    association_id: str
    artifact: SkillDesignArtifactDTO
    binding: CharacterSkillArtifactBindingDTO
    slot: SkillSlot
    order: int
    family: SkillFamily
    mode: SkillMode
    display_summary: str


class CharacterKitEvaluationKitDTO(WebModel):
    """Transport-only Kit input; the backend owns canonical ordering/digest."""

    contract_version: Literal["character-kit/0.1.0"]
    placement_schema_version: Literal["character-kit-placement/0.1.0"]
    associations: list[CharacterSkillAssociationDTO]
    kit_digest: str | None = None


class CharacterKitRoleCoverageRequestDTO(WebModel):
    schema_version: Literal["web-character-kit-role-coverage/0.1"]
    kit: CharacterKitEvaluationKitDTO
    combat_role_profile: CombatRoleProfileDTO
    current_skill_context_fingerprint: str | None = None


class CharacterSkillDesignResponseDTO(WebModel):
    schema_version: Literal["web-character-skill-design/0.1"]
    status: Literal["completed", "failed"]
    source_context_fingerprint: str
    character_context_summary: CharacterSkillContextSummaryDTO
    skill_input: SkillPlaygroundRequestDTO
    semantic_ir: dict[str, Any] | None
    skillkit: dict[str, Any] | None
    evaluation: SkillEvaluationDTO
    alignment: CharacterSkillAlignmentResultDTO
    pipeline: list[PipelineStepDTO]
    artifact_digest: str | None
    freshness: Literal["current", "stale"]
    provider: SkillProviderDTO
    evidence: dict[str, Any]
    artifact_versions: SkillArtifactVersionsDTO | None = None
    artifact_compatibility: ArtifactCompatibility | None = None
    artifact: SkillDesignArtifactDTO | None = None
    binding: CharacterSkillArtifactBindingDTO | None = None


__all__ = [
    "CharacterSkillContextRequestDTO",
    "CharacterSkillMetaDTO",
    "CharacterSkillSlotDTO",
    "CharacterKitValidationRequestDTO",
    "CharacterKitStructuralFindingDTO",
    "CharacterKitStructuralValidationDTO",
    "CharacterKitValidationResponseDTO",
    "CharacterKitRoleCoverageRequestDTO",
    "CharacterKitRoleCoverageEvidenceDTO",
    "CharacterKitRoleCoverageItemDTO",
    "CharacterKitCoverageDTO",
    "CharacterKitEvaluationFindingDTO",
    "CharacterKitRoleCoverageDTO",
    "CharacterKitRoleCoverageResponseDTO",
    "CharacterKitEvaluationKitDTO",
    "CharacterSkillArtifactBindingDTO",
    "CharacterSkillAssociationDTO",
    "CharacterSkillContextResponseDTO",
    "CharacterSkillContextSummaryDTO",
    "CharacterSkillAlignmentFindingDTO",
    "CharacterSkillAlignmentResultDTO",
    "CharacterSkillEvidenceDTO",
    "CharacterSkillDesignRequestDTO",
    "CharacterSkillDesignResponseDTO",
    "CompilerProvenanceDTO",
    "CompilerProvenanceEntryDTO",
    "SkillArtifactIdentityDTO",
    "SkillArtifactEvaluationDTO",
    "SkillArtifactFindingDTO",
    "SkillArtifactProvenanceDTO",
    "SkillDesignArtifactDTO",
]
