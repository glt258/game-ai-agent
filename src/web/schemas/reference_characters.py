from __future__ import annotations

from typing import Literal

from .common import WebModel


class ReferenceCoverageDTO(WebModel):
    identity: float
    combat: float
    narrative: float
    presentation: float
    analysis: float


class ReferenceAvailabilityDTO(WebModel):
    facts: bool
    abilities: bool
    analysis: bool
    sources: bool


class ReferenceCharacterSummaryDTO(WebModel):
    schema_version: Literal["web-reference-character-summary/0.1"]
    reference_id: str
    display_name: str
    localized_names: dict[str, str]
    game_id: str
    game_name: str
    native_character_id: str | None
    faction: str | None
    occupation: str | None
    combat_roles: list[str]
    ability_categories: list[str]
    verification_status: str
    analysis_status: str
    availability: ReferenceAvailabilityDTO
    completeness: ReferenceCoverageDTO


class ReferenceCharacterListDTO(WebModel):
    schema_version: Literal["web-reference-character-list/0.1"]
    characters: list[ReferenceCharacterSummaryDTO]
    total: int


class ReferenceReleaseDTO(WebModel):
    version: str | None
    date: str | None


class ReferenceRarityDTO(WebModel):
    native_value: str | int | None
    normalized_tier: str | None


class ReferenceIdentityDTO(WebModel):
    game_id: str
    game_name: str
    native_character_id: str | None
    canonical_name: str
    localized_names: dict[str, str]
    release: ReferenceReleaseDTO | None
    rarity: ReferenceRarityDTO | None


class ReferenceNarrativeFactsDTO(WebModel):
    faction: str | None
    occupation: str | None
    affiliations: list[str]
    public_identity: str | None


class ReferencePresentationFactsDTO(WebModel):
    official_visual_tags: list[str]
    official_character_keywords: list[str]


class ReferenceAbilityDTO(WebModel):
    ability_id: str
    native_name: str | None
    native_category: str
    normalized_category: str | None
    description_summary: str | None


class ReferenceResourceDTO(WebModel):
    resource_id: str
    native_name: str | None
    description_summary: str | None
    cap: int | float | None


class ReferenceStateDTO(WebModel):
    state_id: str
    native_name: str | None
    subject_scope: str
    description_summary: str | None


class ReferenceTeamInteractionDTO(WebModel):
    interaction_id: str
    native_name: str | None
    description_summary: str


class ReferenceMechanicsDTO(WebModel):
    resources: list[ReferenceResourceDTO]
    states: list[ReferenceStateDTO]
    transformations: list[str]
    summons: list[str]
    mobility_mechanics: list[str]
    targeting_mechanics: list[str]


class ReferenceTeamMechanicsDTO(WebModel):
    buffs: list[str]
    debuffs: list[str]
    healing: list[str]
    shielding: list[str]
    grouping: list[str]
    off_field_effects: list[str]
    interactions: list[ReferenceTeamInteractionDTO]


class ReferenceMechanicRefDTO(WebModel):
    kind: str
    id: str


class ReferenceMechanicRelationDTO(WebModel):
    relation_id: str
    source: ReferenceMechanicRefDTO
    relation_type: str
    target: ReferenceMechanicRefDTO
    description_summary: str | None


class ReferenceCombatFactsDTO(WebModel):
    native_taxonomy: dict[str, str | list[str]]
    mechanics: ReferenceMechanicsDTO
    team_mechanics: ReferenceTeamMechanicsDTO
    relations: list[ReferenceMechanicRelationDTO]


class ReferenceFactsDTO(WebModel):
    narrative: ReferenceNarrativeFactsDTO
    presentation: ReferencePresentationFactsDTO
    combat: ReferenceCombatFactsDTO


class ReferencePrimaryLoopDTO(WebModel):
    summary: str | None
    steps: list[str]


class ReferenceEvidenceDTO(WebModel):
    dimension: str
    token: str | None
    ability_ids: list[str]
    mechanic_refs: list[ReferenceMechanicRefDTO]
    note: str


class ReferenceAnalysisMetadataDTO(WebModel):
    analyzer: str
    prompt_version: str | None
    analyzed_at: str | None


class ReferenceCombatAnalysisDTO(WebModel):
    normalized_roles: list[str]
    combat_roles: list[str]
    damage_patterns: list[str]
    mechanics: list[str]
    team_position: list[str]
    attack_range: str
    field_time: str
    mechanical_complexity: str
    execution_difficulty: str
    mobility: str
    survivability: str
    team_dependency: str
    primary_loop: ReferencePrimaryLoopDTO
    resource_loop: str | None
    burst_pattern: str | None
    archetypes: list[str]
    core_mechanics: list[str]
    role_rationale: dict[str, str]
    evidence: list[ReferenceEvidenceDTO]


class ReferenceCharacterAnalysisDTO(WebModel):
    metadata: ReferenceAnalysisMetadataDTO
    combat: ReferenceCombatAnalysisDTO
    character_fantasy: str | None
    personality_archetypes: list[str]
    identity_hooks: list[str]
    narrative_hooks: list[str]
    visual_motifs: list[str]
    primary_selling_points: list[str]
    gameplay_hooks: list[str]
    visual_hooks: list[str]
    narrative_design_hooks: list[str]
    novelty_dimensions: list[str]
    strongest_differentiators: list[str]
    common_patterns: list[str]
    unusual_patterns: list[str]
    extracted_patterns: list[str]
    combat_signature: list[str]
    narrative_signature: list[str]
    presentation_signature: list[str]


class ReferenceSourceDTO(WebModel):
    source_id: str
    source_type: str
    publisher: str | None
    title: str | None
    url: str
    language: str | None
    published_at: str | None
    version_context: str | None
    reliability: str


class ReferenceMetadataDTO(WebModel):
    baseline_id: str | None
    facts_schema_version: str
    analysis_schema_version: str | None
    sources_schema_version: str
    verification_status: str
    analysis_status: str
    completeness: ReferenceCoverageDTO
    warnings: list[str]


class ReferenceCharacterDetailDTO(WebModel):
    schema_version: Literal["web-reference-character/0.1"]
    reference_id: str
    identity: ReferenceIdentityDTO
    facts: ReferenceFactsDTO
    abilities: list[ReferenceAbilityDTO]
    combat_analysis: ReferenceCharacterAnalysisDTO | None
    sources: list[ReferenceSourceDTO]
    metadata: ReferenceMetadataDTO


__all__ = [
    "ReferenceCharacterDetailDTO",
    "ReferenceCharacterListDTO",
    "ReferenceCharacterSummaryDTO",
]
