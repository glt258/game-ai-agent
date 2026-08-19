from __future__ import annotations

import re
from datetime import date as date_type, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AnalysisStatus,
    AttackRange,
    NormalizedRole,
    OrdinalBand,
    SourceReliability,
    SourceType,
    VerificationStatus,
)


REFERENCE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?$")
RELATION_TYPE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
SUPPORTED_SCHEMA_VERSIONS = {
    "character-facts/0.3",
    "character-analysis/0.1",
    "character-sources/0.2",
    "game-catalog/0.1",
    "character-reference-corpus/0.1",
}


class ReferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _text(value: str, field_name: str = "value") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None) -> str | None:
    return None if value is None else _text(value)


def _string_list(value: list[str], field_name: str = "list") -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = [_text(item, field_name) for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


class LocalizedNames(ReferenceModel):
    canonical: str
    localized: dict[str, str] = Field(default_factory=dict)

    _canonical = field_validator("canonical")(lambda value: _text(value, "canonical"))

    @field_validator("localized")
    @classmethod
    def validate_localized(cls, value: dict[str, str]) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("localized must be a mapping")
        result: dict[str, str] = {}
        for key, item in value.items():
            result[_text(key, "localized key")] = _text(item, "localized value")
        return result


class CharacterRelease(ReferenceModel):
    version: str | None = None
    date: date_type | None = None

    _version = field_validator("version")(lambda value: _optional_text(value))


class CharacterRarity(ReferenceModel):
    native_value: str | int | None = None
    normalized_tier: str | None = None

    @field_validator("native_value")
    @classmethod
    def validate_native_value(cls, value: str | int | None) -> str | int | None:
        if isinstance(value, bool):
            raise ValueError("native_value must not be boolean")
        return _optional_text(value) if isinstance(value, str) else value

    _normalized_tier = field_validator("normalized_tier")(lambda value: _optional_text(value))


class CharacterIdentity(ReferenceModel):
    game_id: str
    native_character_id: str | None = None
    names: LocalizedNames
    release: CharacterRelease | None = None
    rarity: CharacterRarity | None = None

    _game_id = field_validator("game_id")(lambda value: _text(value, "game_id"))
    _native_character_id = field_validator("native_character_id")(
        lambda value: _optional_text(value)
    )


class NativeTaxonomy(ReferenceModel):
    labels: dict[str, str | list[str]] = Field(default_factory=dict)

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: dict[str, str | list[str]]) -> dict[str, str | list[str]]:
        if not isinstance(value, dict):
            raise ValueError("labels must be a mapping")
        result: dict[str, str | list[str]] = {}
        for key, item in value.items():
            clean_key = _text(key, "taxonomy key")
            if isinstance(item, str):
                result[clean_key] = _text(item, "taxonomy value")
            elif isinstance(item, list):
                result[clean_key] = _string_list(item, "taxonomy value")
            else:
                raise ValueError("taxonomy values must be strings or string lists")
        return result


class AbilityFact(ReferenceModel):
    ability_id: str
    native_name: str | None = None
    native_category: str
    normalized_category: str | None = None
    description_summary: str | None = None

    _ability_id = field_validator("ability_id")(lambda value: _text(value, "ability_id"))
    _native_name = field_validator("native_name")(lambda value: _optional_text(value))
    _native_category = field_validator("native_category")(
        lambda value: _text(value, "native_category")
    )
    _normalized_category = field_validator("normalized_category")(
        lambda value: _optional_text(value)
    )
    _description_summary = field_validator("description_summary")(
        lambda value: _optional_text(value)
    )


class ResourceFact(ReferenceModel):
    resource_id: str
    native_name: str | None = None
    description_summary: str | None = None
    cap: int | float | None = None

    _resource_id = field_validator("resource_id")(lambda value: _text(value, "resource_id"))
    _native_name = field_validator("native_name")(lambda value: _optional_text(value))
    _description_summary = field_validator("description_summary")(
        lambda value: _optional_text(value)
    )

    @field_validator("cap")
    @classmethod
    def valid_cap(cls, value: int | float | None) -> int | float | None:
        if isinstance(value, bool):
            raise ValueError("cap must be numeric or null")
        return value


class StateFact(ReferenceModel):
    state_id: str
    native_name: str | None = None
    subject_scope: str
    description_summary: str | None = None

    _state_id = field_validator("state_id")(lambda value: _text(value, "state_id"))
    _native_name = field_validator("native_name")(lambda value: _optional_text(value))
    @field_validator("subject_scope")
    @classmethod
    def valid_subject_scope(cls, value: str) -> str:
        value = _text(value, "subject_scope")
        if value not in {"self", "target", "unknown"}:
            raise ValueError(
                "subject_scope must be one of: self, target, unknown"
            )
        return value

    _description_summary = field_validator("description_summary")(
        lambda value: _optional_text(value)
    )


class TeamInteractionFact(ReferenceModel):
    interaction_id: str
    native_name: str | None = None
    description_summary: str

    _interaction_id = field_validator("interaction_id")(
        lambda value: _text(value, "interaction_id")
    )
    _native_name = field_validator("native_name")(lambda value: _optional_text(value))
    _description_summary = field_validator("description_summary")(
        lambda value: _text(value, "description_summary")
    )


class MechanicRef(ReferenceModel):
    kind: Literal["ability", "state", "resource", "team_interaction"]
    id: str

    _id = field_validator("id")(lambda value: _text(value, "mechanic reference id"))


class MechanicRelation(ReferenceModel):
    relation_id: str
    source: MechanicRef
    relation_type: str
    target: MechanicRef
    description_summary: str | None = None

    _relation_id = field_validator("relation_id")(
        lambda value: _text(value, "relation_id")
    )
    _description_summary = field_validator("description_summary")(
        lambda value: _optional_text(value)
    )

    @field_validator("relation_type")
    @classmethod
    def valid_relation_type(cls, value: str) -> str:
        value = _text(value, "relation_type")
        if not RELATION_TYPE_RE.fullmatch(value):
            raise ValueError("relation_type must be non-empty snake_case")
        return value


def _ensure_unique_node_ids(items: list[object], field_name: str, id_attribute: str) -> None:
    ids = [getattr(item, id_attribute) for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"DUPLICATE_{field_name.upper()}_ID: {id_attribute} must be unique")


class CombatMechanics(ReferenceModel):
    resources: list[ResourceFact] = Field(default_factory=list)
    states: list[StateFact] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    summons: list[str] = Field(default_factory=list)
    mobility_mechanics: list[str] = Field(default_factory=list)
    targeting_mechanics: list[str] = Field(default_factory=list)

    _mechanic_lists = field_validator(
        "transformations", "summons", "mobility_mechanics", "targeting_mechanics"
    )(_string_list)

    @model_validator(mode="after")
    def unique_mechanic_nodes(self) -> "CombatMechanics":
        _ensure_unique_node_ids(self.resources, "resource", "resource_id")
        _ensure_unique_node_ids(self.states, "state", "state_id")
        return self


class TeamMechanics(ReferenceModel):
    buffs: list[str] = Field(default_factory=list)
    debuffs: list[str] = Field(default_factory=list)
    healing: list[str] = Field(default_factory=list)
    shielding: list[str] = Field(default_factory=list)
    grouping: list[str] = Field(default_factory=list)
    off_field_effects: list[str] = Field(default_factory=list)
    interactions: list[TeamInteractionFact] = Field(default_factory=list)

    _team_lists = field_validator(
        "buffs", "debuffs", "healing", "shielding", "grouping", "off_field_effects"
    )(_string_list)

    @model_validator(mode="after")
    def unique_interactions(self) -> "TeamMechanics":
        _ensure_unique_node_ids(self.interactions, "team_interaction", "interaction_id")
        return self


class CombatFacts(ReferenceModel):
    native_taxonomy: NativeTaxonomy
    abilities: list[AbilityFact] = Field(default_factory=list)
    mechanics: CombatMechanics = Field(default_factory=CombatMechanics)
    team_mechanics: TeamMechanics = Field(default_factory=TeamMechanics)
    relations: list[MechanicRelation] = Field(default_factory=list)

    @field_validator("abilities")
    @classmethod
    def unique_abilities(cls, value: list[AbilityFact]) -> list[AbilityFact]:
        ids = [item.ability_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("ability_id must be unique within a character")
        return value

    @model_validator(mode="after")
    def validate_relations(self) -> "CombatFacts":
        _ensure_unique_node_ids(self.relations, "relation", "relation_id")

        nodes = {
            "ability": {item.ability_id for item in self.abilities},
            "state": {item.state_id for item in self.mechanics.states},
            "resource": {item.resource_id for item in self.mechanics.resources},
            "team_interaction": {
                item.interaction_id for item in self.team_mechanics.interactions
            },
        }
        seen_edges: set[tuple[str, str, str, str, str]] = set()
        for relation in self.relations:
            for endpoint_name, endpoint in (("source", relation.source), ("target", relation.target)):
                if endpoint.id not in nodes[endpoint.kind]:
                    raise ValueError(
                        f"UNKNOWN_MECHANIC_REFERENCE: {endpoint_name} {endpoint.kind} {endpoint.id!r}"
                    )
            edge = (
                relation.source.kind,
                relation.source.id,
                relation.relation_type,
                relation.target.kind,
                relation.target.id,
            )
            if edge in seen_edges:
                raise ValueError("DUPLICATE_MECHANIC_RELATION: source/relation_type/target must be unique")
            seen_edges.add(edge)
        return self


class NarrativeFacts(ReferenceModel):
    faction: str | None = None
    occupation: str | None = None
    affiliations: list[str] = Field(default_factory=list)
    public_identity: str | None = None

    _optional_fields = field_validator("faction", "occupation", "public_identity")(
        lambda value: _optional_text(value)
    )
    _affiliations = field_validator("affiliations")(_string_list)


class PresentationFacts(ReferenceModel):
    official_visual_tags: list[str] = Field(default_factory=list)
    official_character_keywords: list[str] = Field(default_factory=list)

    _presentation_lists = field_validator(
        "official_visual_tags", "official_character_keywords"
    )(_string_list)


class CharacterFacts(ReferenceModel):
    schema_version: str
    reference_id: str
    identity: CharacterIdentity
    combat: CombatFacts
    narrative: NarrativeFacts = Field(default_factory=NarrativeFacts)
    presentation: PresentationFacts = Field(default_factory=PresentationFacts)

    _schema_version = field_validator("schema_version")(lambda value: _text(value, "schema_version"))

    @field_validator("reference_id")
    @classmethod
    def valid_reference_id(cls, value: str) -> str:
        value = _text(value, "reference_id")
        if not REFERENCE_ID_RE.fullmatch(value):
            raise ValueError("reference_id must use lowercase kebab-case, optionally game:character")
        return value


class AnalysisMetadata(ReferenceModel):
    analyzer: str
    model: str | None = None
    prompt_version: str | None = None
    analyzed_at: datetime | None = None

    _analyzer = field_validator("analyzer")(lambda value: _text(value, "analyzer"))
    _optional_fields = field_validator("model", "prompt_version")(
        lambda value: _optional_text(value)
    )


class PrimaryLoop(ReferenceModel):
    summary: str | None = None
    steps: list[str] = Field(default_factory=list)

    _summary = field_validator("summary")(lambda value: _optional_text(value))
    _steps = field_validator("steps")(_string_list)


class CombatDesignAnalysis(ReferenceModel):
    normalized_roles: list[NormalizedRole] = Field(default_factory=list)
    attack_range: AttackRange = AttackRange.UNKNOWN
    field_time: OrdinalBand = OrdinalBand.UNKNOWN
    mechanical_complexity: OrdinalBand = OrdinalBand.UNKNOWN
    execution_difficulty: OrdinalBand = OrdinalBand.UNKNOWN
    mobility: OrdinalBand = OrdinalBand.UNKNOWN
    survivability: OrdinalBand = OrdinalBand.UNKNOWN
    team_dependency: OrdinalBand = OrdinalBand.UNKNOWN
    primary_loop: PrimaryLoop
    resource_loop: str | None = None
    burst_pattern: str | None = None
    archetypes: list[str] = Field(default_factory=list)
    core_mechanics: list[str] = Field(default_factory=list)

    @field_validator("normalized_roles")
    @classmethod
    def unique_roles(cls, value: list[NormalizedRole]) -> list[NormalizedRole]:
        if len(value) != len(set(value)):
            raise ValueError("normalized_roles must not contain duplicates")
        return value
    _analysis_lists = field_validator("archetypes", "core_mechanics")(_string_list)
    _optional_fields = field_validator("resource_loop", "burst_pattern")(
        lambda value: _optional_text(value)
    )


class AlignmentAssessment(ReferenceModel):
    score: float
    reasoning: str

    score = Field(ge=0.0, le=1.0)
    _reasoning = field_validator("reasoning")(lambda value: _text(value, "reasoning"))


class AuthoringFeatureEvidence(ReferenceModel):
    """Small provenance entries for normalized analysis features."""

    kind: Literal["source_fact", "brief", "analyst_derivation"]
    source_id: str | None = None
    fact_path: str | None = None
    note: str | None = None

    _source_id = field_validator("source_id")(lambda value: _optional_text(value))
    _fact_path = field_validator("fact_path")(lambda value: _optional_text(value))
    _note = field_validator("note")(lambda value: _optional_text(value))

    @model_validator(mode="after")
    def validate_kind_shape(self) -> "AuthoringFeatureEvidence":
        if self.kind == "source_fact":
            if self.source_id is None:
                raise ValueError("source_fact evidence requires source_id")
            if self.fact_path is not None and self.fact_path.startswith("facts."):
                raise ValueError("fact_path must be relative to CharacterFacts")
        elif self.kind == "brief":
            if self.source_id is not None or self.fact_path is not None:
                raise ValueError("brief evidence cannot reference a corpus source fact")
        elif self.kind == "analyst_derivation":
            if self.source_id is not None or self.fact_path is not None:
                raise ValueError("analyst_derivation cannot masquerade as source_fact")
            if self.note is None:
                raise ValueError("analyst_derivation evidence requires note")
        return self


class StructuredHookFeatures(ReferenceModel):
    surface_traits: list[str] = Field(default_factory=list)
    contrast_traits: list[str] = Field(default_factory=list)
    behavioral_patterns: list[str] = Field(default_factory=list)

    _lists = field_validator(
        "surface_traits", "contrast_traits", "behavioral_patterns"
    )(_string_list)


def _canonical_authoring_list(
    value: list[str],
    domain: str,
) -> list[str]:
    values = _string_list(value, f"authoring_features.{domain}")
    # Import lazily to keep the validated model layer independent from the
    # diagnostic extractor's provenance helpers during package import.
    from .features import canonical_tokens

    allowed = set(canonical_tokens(domain))
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(
            f"authoring_features.{domain} contains unsupported canonical token(s): {unknown}"
        )
    return values


def _canonical_authoring_optional(
    value: str | None,
    domain: str,
) -> str | None:
    if value is None:
        return None
    clean_value = _text(value, f"authoring_features.{domain}")
    # Import lazily to keep the validated model layer independent from the
    # diagnostic extractor's provenance helpers during package import.
    from .features import canonical_tokens

    if clean_value not in set(canonical_tokens(domain)):
        raise ValueError(
            f"authoring_features.{domain} contains unsupported canonical token(s): "
            f"[{clean_value!r}]"
        )
    return clean_value


class AuthoringFeatureBlock(ReferenceModel):
    """Optional normalized authoring interpretation for a reference."""

    personality: list[str] = Field(default_factory=list)
    gameplay_fantasy: list[str] = Field(default_factory=list)
    life_social_identity: list[str] = Field(default_factory=list)
    life_stage: list[str] = Field(default_factory=list)
    authority: list[str] = Field(default_factory=list)
    authority_scope: str | None = None
    hook: StructuredHookFeatures | None = None
    visual_behavioral_motifs: list[str] = Field(default_factory=list)
    evidence: dict[str, list[AuthoringFeatureEvidence]] = Field(default_factory=dict)

    _personality = field_validator("personality")(
        lambda value: _canonical_authoring_list(value, "personality")
    )
    _gameplay_fantasy = field_validator("gameplay_fantasy")(
        lambda value: _canonical_authoring_list(value, "gameplay_fantasy")
    )
    _life_social_identity = field_validator("life_social_identity")(
        lambda value: _canonical_authoring_list(value, "life_social_identity")
    )
    _life_stage = field_validator("life_stage")(
        lambda value: _canonical_authoring_list(value, "life_stage")
    )
    _authority = field_validator("authority")(
        lambda value: _canonical_authoring_list(value, "authority")
    )
    _authority_scope = field_validator("authority_scope")(
        lambda value: _canonical_authoring_optional(value, "authority_scope")
    )
    _visual_behavioral_motifs = field_validator("visual_behavioral_motifs")(
        lambda value: _canonical_authoring_list(value, "visual_behavioral_motif")
    )

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: dict[str, list[AuthoringFeatureEvidence]]) -> dict[str, list[AuthoringFeatureEvidence]]:
        allowed = {
            "personality",
            "gameplay_fantasy",
            "life_social_identity",
            "life_stage",
            "authority",
            "authority_scope",
            "hook.surface_traits",
            "hook.contrast_traits",
            "hook.behavioral_patterns",
            "visual_behavioral_motifs",
        }
        result: dict[str, list[AuthoringFeatureEvidence]] = {}
        for path, entries in value.items():
            clean_path = _text(path, "authoring feature evidence path")
            if clean_path not in allowed:
                raise ValueError(
                    f"unsupported authoring feature evidence path: {clean_path}"
                )
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"authoring feature evidence for {clean_path} must not be empty")
            result[clean_path] = entries
        return result


class CharacterDesignAnalysis(ReferenceModel):
    character_fantasy: str | None = None
    personality_archetypes: list[str] = Field(default_factory=list)
    identity_hooks: list[str] = Field(default_factory=list)
    narrative_hooks: list[str] = Field(default_factory=list)
    visual_motifs: list[str] = Field(default_factory=list)
    gameplay_identity_alignment: AlignmentAssessment | None = None
    authoring_features: AuthoringFeatureBlock | None = None

    _fantasy = field_validator("character_fantasy")(lambda value: _optional_text(value))
    _lists = field_validator(
        "personality_archetypes", "identity_hooks", "narrative_hooks", "visual_motifs"
    )(_string_list)


class ProductDesignAnalysis(ReferenceModel):
    primary_selling_points: list[str] = Field(default_factory=list)
    gameplay_hooks: list[str] = Field(default_factory=list)
    visual_hooks: list[str] = Field(default_factory=list)
    narrative_hooks: list[str] = Field(default_factory=list)
    novelty_dimensions: list[str] = Field(default_factory=list)

    _lists = field_validator(
        "primary_selling_points", "gameplay_hooks", "visual_hooks", "narrative_hooks", "novelty_dimensions"
    )(_string_list)


class DifferentiationAnalysis(ReferenceModel):
    strongest_differentiators: list[str] = Field(default_factory=list)
    common_patterns: list[str] = Field(default_factory=list)
    unusual_patterns: list[str] = Field(default_factory=list)

    _lists = field_validator(
        "strongest_differentiators", "common_patterns", "unusual_patterns"
    )(_string_list)


class DesignPatternAnalysis(ReferenceModel):
    extracted_patterns: list[str] = Field(default_factory=list)

    _patterns = field_validator("extracted_patterns")(_string_list)


class SimilarityFeatures(ReferenceModel):
    combat_signature: list[str] = Field(default_factory=list)
    narrative_signature: list[str] = Field(default_factory=list)
    presentation_signature: list[str] = Field(default_factory=list)

    _lists = field_validator(
        "combat_signature", "narrative_signature", "presentation_signature"
    )(_string_list)


class AnalysisConfidence(ReferenceModel):
    overall: float | None = Field(default=None, ge=0.0, le=1.0)
    combat_design: float | None = Field(default=None, ge=0.0, le=1.0)
    character_design: float | None = Field(default=None, ge=0.0, le=1.0)
    product_design: float | None = Field(default=None, ge=0.0, le=1.0)


class CharacterAnalysis(ReferenceModel):
    schema_version: str
    reference_id: str
    analysis_metadata: AnalysisMetadata
    combat_design: CombatDesignAnalysis
    character_design: CharacterDesignAnalysis
    product_design: ProductDesignAnalysis
    differentiation: DifferentiationAnalysis
    design_patterns: DesignPatternAnalysis
    similarity_features: SimilarityFeatures
    confidence: AnalysisConfidence

    _schema_version = field_validator("schema_version")(lambda value: _text(value, "schema_version"))

    @field_validator("reference_id")
    @classmethod
    def valid_reference_id(cls, value: str) -> str:
        value = _text(value, "reference_id")
        if not REFERENCE_ID_RE.fullmatch(value):
            raise ValueError("reference_id must use lowercase kebab-case, optionally game:character")
        return value


class SourceRecord(ReferenceModel):
    source_id: str
    source_type: SourceType
    publisher: str | None = None
    title: str | None = None
    url: str
    language: str | None = None
    retrieved_at: datetime | None = None
    published_at: date_type | None = None
    version_context: str | None = None
    content_hash: str | None = None
    reliability: SourceReliability

    _source_id = field_validator("source_id")(lambda value: _text(value, "source_id"))
    _optional_fields = field_validator(
        "publisher", "title", "language", "version_context", "content_hash"
    )(
        lambda value: _optional_text(value)
    )

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        value = _text(value, "url")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute http:// or https:// URL")
        return value


class SourceRelation(ReferenceModel):
    relation_id: str
    source_id: str
    relation_type: str
    target_source_id: str
    field_paths: list[str]
    description_summary: str | None = None

    _relation_id = field_validator("relation_id")(lambda value: _text(value, "relation_id"))
    _source_id = field_validator("source_id")(lambda value: _text(value, "source_id"))
    _target_source_id = field_validator("target_source_id")(
        lambda value: _text(value, "target_source_id")
    )
    _description_summary = field_validator("description_summary")(
        lambda value: _optional_text(value)
    )

    @field_validator("relation_type")
    @classmethod
    def valid_relation_type(cls, value: str) -> str:
        value = _text(value, "relation_type")
        if not RELATION_TYPE_RE.fullmatch(value):
            raise ValueError("INVALID_SOURCE_RELATION_TYPE: relation_type must be non-empty snake_case")
        return value

    @field_validator("field_paths")
    @classmethod
    def valid_field_paths(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("EMPTY_SOURCE_RELATION_FIELDS: field_paths must not be empty")
        return _string_list(value, "source relation field paths")

    @model_validator(mode="after")
    def reject_self_relation(self) -> "SourceRelation":
        if self.source_id == self.target_source_id:
            raise ValueError("SELF_SOURCE_RELATION: source relation cannot target itself")
        return self


class SourceConflict(ReferenceModel):
    field_path: str
    source_ids: list[str]
    description: str

    _field_path = field_validator("field_path")(lambda value: _text(value, "field_path"))
    _source_ids = field_validator("source_ids")(_string_list)
    _description = field_validator("description")(lambda value: _text(value, "description"))


class VerificationRecord(ReferenceModel):
    status: VerificationStatus
    conflicts: list[SourceConflict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    _notes = field_validator("notes")(_string_list)

    @model_validator(mode="after")
    def validate_conflicts(self) -> "VerificationRecord":
        if self.status == VerificationStatus.CONFLICTED and not self.conflicts:
            raise ValueError("conflicted verification requires conflicts")
        if self.status == VerificationStatus.VERIFIED and self.conflicts:
            raise ValueError("verified verification must not contain conflicts")
        return self


class CharacterProvenance(ReferenceModel):
    schema_version: str
    reference_id: str
    sources: list[SourceRecord]
    source_relations: list[SourceRelation] = Field(default_factory=list)
    field_evidence: dict[str, list[str]] = Field(default_factory=dict)
    verification: VerificationRecord

    _schema_version = field_validator("schema_version")(lambda value: _text(value, "schema_version"))

    @field_validator("reference_id")
    @classmethod
    def valid_reference_id(cls, value: str) -> str:
        value = _text(value, "reference_id")
        if not REFERENCE_ID_RE.fullmatch(value):
            raise ValueError("reference_id must use lowercase kebab-case, optionally game:character")
        return value

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, value: list[SourceRecord]) -> list[SourceRecord]:
        ids = [item.source_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("source_id must be unique within a character")
        return value

    @field_validator("source_relations")
    @classmethod
    def unique_source_relations(cls, value: list[SourceRelation]) -> list[SourceRelation]:
        ids = [item.relation_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_SOURCE_RELATION_ID: relation_id must be unique within a character")
        return value

    @field_validator("field_evidence")
    @classmethod
    def validate_evidence_shape(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for path, source_ids in value.items():
            clean_path = _text(path, "field evidence path")
            clean_sources = _string_list(source_ids, "field evidence sources")
            if not clean_sources:
                raise ValueError(f"field evidence for {clean_path} must not be empty")
            result[clean_path] = clean_sources
        return result


class CompletenessScore(ReferenceModel):
    identity: float = Field(ge=0.0, le=1.0)
    combat: float = Field(ge=0.0, le=1.0)
    narrative: float = Field(ge=0.0, le=1.0)
    presentation: float = Field(ge=0.0, le=1.0)
    analysis: float = Field(ge=0.0, le=1.0)


class CharacterReferenceQuality(ReferenceModel):
    completeness: CompletenessScore
    verification_status: VerificationStatus
    analysis_status: AnalysisStatus
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[SourceConflict] = Field(default_factory=list)

    _warnings = field_validator("warnings")(_string_list)


class CharacterReference(ReferenceModel):
    reference_id: str
    facts: CharacterFacts
    analysis: CharacterAnalysis | None = None
    provenance: CharacterProvenance
    quality: CharacterReferenceQuality

    @model_validator(mode="after")
    def ids_match(self) -> "CharacterReference":
        ids = {self.reference_id, self.facts.reference_id, self.provenance.reference_id}
        if self.analysis is not None:
            ids.add(self.analysis.reference_id)
        if len(ids) != 1:
            raise ValueError("all reference_id fields must match")
        return self


class GameDefinition(ReferenceModel):
    display_name: str
    developer: str | None = None
    aliases: list[str] = Field(default_factory=list)
    taxonomy: dict[str, bool] = Field(default_factory=dict)

    _display_name = field_validator("display_name")(lambda value: _text(value, "display_name"))
    _developer = field_validator("developer")(lambda value: _optional_text(value))
    _aliases = field_validator("aliases")(_string_list)

    @field_validator("taxonomy")
    @classmethod
    def valid_taxonomy(cls, value: dict[str, bool]) -> dict[str, bool]:
        if any(not isinstance(key, str) or not key.strip() for key in value):
            raise ValueError("taxonomy keys must be non-empty")
        if any(not isinstance(item, bool) for item in value.values()):
            raise ValueError("taxonomy values must be boolean")
        return {key.strip(): item for key, item in value.items()}


class GameCatalog(ReferenceModel):
    schema_version: str
    games: dict[str, GameDefinition]

    _schema_version = field_validator("schema_version")(lambda value: _text(value, "schema_version"))

    @field_validator("games")
    @classmethod
    def valid_games(cls, value: dict[str, GameDefinition]) -> dict[str, GameDefinition]:
        if not value:
            raise ValueError("games must not be empty")
        result: dict[str, GameDefinition] = {}
        for game_id, definition in value.items():
            clean_id = _text(game_id, "game_id")
            if clean_id in result:
                raise ValueError(f"duplicate game_id after trimming: {clean_id}")
            result[clean_id] = definition
        return result

    def require(self, game_id: str) -> GameDefinition:
        try:
            return self.games[game_id]
        except KeyError as exc:
            raise KeyError(f"unknown game_id: {game_id}") from exc


class CorpusManifest(ReferenceModel):
    corpus_version: str
    schema_versions: dict[str, str]
    games: list[str]
    status: str

    _corpus_version = field_validator("corpus_version")(lambda value: _text(value, "corpus_version"))
    @field_validator("schema_versions")
    @classmethod
    def valid_schema_versions(cls, value: dict[str, str]) -> dict[str, str]:
        return {_text(key, "schema version key"): _text(item, "schema version") for key, item in value.items()}

    _games = field_validator("games")(_string_list)
    _status = field_validator("status")(lambda value: _text(value, "status"))


class FixturePlan(ReferenceModel):
    corpus_version: str
    target_count: int = Field(ge=0)
    games: dict[str, list[str]]
    notes: list[str] = Field(default_factory=list)

    _corpus_version = field_validator("corpus_version")(lambda value: _text(value, "corpus_version"))
    _notes = field_validator("notes")(_string_list)

    @field_validator("games")
    @classmethod
    def valid_plan_games(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for game_id, slots in value.items():
            clean_id = _text(game_id, "game_id")
            if clean_id in result:
                raise ValueError(f"duplicate game_id after trimming: {clean_id}")
            result[clean_id] = _string_list(slots, "fixture slots")
        return result


class ValidationIssue(ReferenceModel):
    severity: Literal["error", "warning"]
    code: str
    reference_id: str | None = None
    field_path: str | None = None
    message: str

    _code = field_validator("code")(lambda value: _text(value, "code"))
    _reference_id = field_validator("reference_id")(lambda value: _optional_text(value))
    _field_path = field_validator("field_path")(lambda value: _optional_text(value))
    _message = field_validator("message")(lambda value: _text(value, "message"))


class CorpusValidationReport(ReferenceModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validity_matches_errors(self) -> "CorpusValidationReport":
        if self.valid != (not self.errors):
            raise ValueError("valid must be true exactly when errors is empty")
        return self
