from __future__ import annotations

from enum import Enum
from typing import Any

from reference_corpus.models import CharacterAnalysis, CharacterReference, GameCatalog

from ..schemas.reference_characters import (
    ReferenceAbilityDTO,
    ReferenceAnalysisMetadataDTO,
    ReferenceAvailabilityDTO,
    ReferenceCharacterAnalysisDTO,
    ReferenceCharacterDetailDTO,
    ReferenceCharacterListDTO,
    ReferenceCharacterSummaryDTO,
    ReferenceCombatAnalysisDTO,
    ReferenceCombatFactsDTO,
    ReferenceCoverageDTO,
    ReferenceEvidenceDTO,
    ReferenceFactsDTO,
    ReferenceIdentityDTO,
    ReferenceMechanicRefDTO,
    ReferenceMechanicRelationDTO,
    ReferenceMechanicsDTO,
    ReferenceMetadataDTO,
    ReferenceNarrativeFactsDTO,
    ReferencePresentationFactsDTO,
    ReferencePrimaryLoopDTO,
    ReferenceRarityDTO,
    ReferenceReleaseDTO,
    ReferenceResourceDTO,
    ReferenceSourceDTO,
    ReferenceStateDTO,
    ReferenceTeamInteractionDTO,
    ReferenceTeamMechanicsDTO,
)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _date(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _game_name(reference: CharacterReference, catalog: GameCatalog | None) -> str:
    game_id = reference.facts.identity.game_id
    if catalog is None or game_id not in catalog.games:
        return game_id
    return catalog.games[game_id].display_name


def _coverage(reference: CharacterReference) -> ReferenceCoverageDTO:
    return ReferenceCoverageDTO(
        identity=reference.quality.completeness.identity,
        combat=reference.quality.completeness.combat,
        narrative=reference.quality.completeness.narrative,
        presentation=reference.quality.completeness.presentation,
        analysis=reference.quality.completeness.analysis,
    )


def _roles(reference: CharacterReference) -> list[str]:
    if reference.analysis is None:
        return []
    return [_value(role) for role in reference.analysis.combat_design.normalized_roles]


def _ability_categories(reference: CharacterReference) -> list[str]:
    categories = [
        ability.normalized_category or ability.native_category
        for ability in reference.facts.combat.abilities
    ]
    return list(dict.fromkeys(categories))


def to_reference_summary(
    reference: CharacterReference, catalog: GameCatalog | None
) -> ReferenceCharacterSummaryDTO:
    identity = reference.facts.identity
    narrative = reference.facts.narrative
    return ReferenceCharacterSummaryDTO(
        schema_version="web-reference-character-summary/0.1",
        reference_id=reference.reference_id,
        display_name=identity.names.canonical,
        localized_names=dict(identity.names.localized),
        game_id=identity.game_id,
        game_name=_game_name(reference, catalog),
        native_character_id=identity.native_character_id,
        faction=narrative.faction,
        occupation=narrative.occupation,
        combat_roles=_roles(reference),
        ability_categories=_ability_categories(reference),
        verification_status=_value(reference.quality.verification_status),
        analysis_status=_value(reference.quality.analysis_status),
        availability=ReferenceAvailabilityDTO(
            facts=True,
            abilities=bool(reference.facts.combat.abilities),
            analysis=reference.analysis is not None,
            sources=bool(reference.provenance.sources),
        ),
        completeness=_coverage(reference),
    )


def to_reference_list(
    references: list[CharacterReference],
    catalog: GameCatalog | None,
) -> ReferenceCharacterListDTO:
    items = [to_reference_summary(item, catalog) for item in references]
    return ReferenceCharacterListDTO(
        schema_version="web-reference-character-list/0.1",
        characters=items,
        total=len(items),
    )


def _identity(reference: CharacterReference, catalog: GameCatalog | None) -> ReferenceIdentityDTO:
    identity = reference.facts.identity
    release = identity.release
    rarity = identity.rarity
    return ReferenceIdentityDTO(
        game_id=identity.game_id,
        game_name=_game_name(reference, catalog),
        native_character_id=identity.native_character_id,
        canonical_name=identity.names.canonical,
        localized_names=dict(identity.names.localized),
        release=(
            ReferenceReleaseDTO(version=release.version, date=_date(release.date))
            if release is not None
            else None
        ),
        rarity=(
            ReferenceRarityDTO(
                native_value=rarity.native_value,
                normalized_tier=rarity.normalized_tier,
            )
            if rarity is not None
            else None
        ),
    )


def _mechanics(reference: CharacterReference) -> ReferenceMechanicsDTO:
    mechanics = reference.facts.combat.mechanics
    return ReferenceMechanicsDTO(
        resources=[
            ReferenceResourceDTO(
                resource_id=item.resource_id,
                native_name=item.native_name,
                description_summary=item.description_summary,
                cap=item.cap,
            )
            for item in mechanics.resources
        ],
        states=[
            ReferenceStateDTO(
                state_id=item.state_id,
                native_name=item.native_name,
                subject_scope=item.subject_scope,
                description_summary=item.description_summary,
            )
            for item in mechanics.states
        ],
        transformations=list(mechanics.transformations),
        summons=list(mechanics.summons),
        mobility_mechanics=list(mechanics.mobility_mechanics),
        targeting_mechanics=list(mechanics.targeting_mechanics),
    )


def _team_mechanics(reference: CharacterReference) -> ReferenceTeamMechanicsDTO:
    mechanics = reference.facts.combat.team_mechanics
    return ReferenceTeamMechanicsDTO(
        buffs=list(mechanics.buffs),
        debuffs=list(mechanics.debuffs),
        healing=list(mechanics.healing),
        shielding=list(mechanics.shielding),
        grouping=list(mechanics.grouping),
        off_field_effects=list(mechanics.off_field_effects),
        interactions=[
            ReferenceTeamInteractionDTO(
                interaction_id=item.interaction_id,
                native_name=item.native_name,
                description_summary=item.description_summary,
            )
            for item in mechanics.interactions
        ],
    )


def _facts(reference: CharacterReference) -> ReferenceFactsDTO:
    facts = reference.facts
    return ReferenceFactsDTO(
        narrative=ReferenceNarrativeFactsDTO(
            faction=facts.narrative.faction,
            occupation=facts.narrative.occupation,
            affiliations=list(facts.narrative.affiliations),
            public_identity=facts.narrative.public_identity,
        ),
        presentation=ReferencePresentationFactsDTO(
            official_visual_tags=list(facts.presentation.official_visual_tags),
            official_character_keywords=list(facts.presentation.official_character_keywords),
        ),
        combat=ReferenceCombatFactsDTO(
            native_taxonomy=dict(facts.combat.native_taxonomy.labels),
            mechanics=_mechanics(reference),
            team_mechanics=_team_mechanics(reference),
            relations=[
                ReferenceMechanicRelationDTO(
                    relation_id=item.relation_id,
                    source=ReferenceMechanicRefDTO(kind=item.source.kind, id=item.source.id),
                    relation_type=item.relation_type,
                    target=ReferenceMechanicRefDTO(kind=item.target.kind, id=item.target.id),
                    description_summary=item.description_summary,
                )
                for item in facts.combat.relations
            ],
        ),
    )


def _analysis(reference: CharacterAnalysis) -> ReferenceCharacterAnalysisDTO:
    combat = reference.combat_design
    return ReferenceCharacterAnalysisDTO(
        metadata=ReferenceAnalysisMetadataDTO(
            analyzer=reference.analysis_metadata.analyzer,
            prompt_version=reference.analysis_metadata.prompt_version,
            analyzed_at=_date(reference.analysis_metadata.analyzed_at),
        ),
        combat=ReferenceCombatAnalysisDTO(
            normalized_roles=[_value(item) for item in combat.normalized_roles],
            combat_roles=list(combat.combat_roles),
            damage_patterns=list(combat.damage_patterns),
            mechanics=list(combat.mechanics),
            team_position=list(combat.team_position),
            attack_range=_value(combat.attack_range),
            field_time=_value(combat.field_time),
            mechanical_complexity=_value(combat.mechanical_complexity),
            execution_difficulty=_value(combat.execution_difficulty),
            mobility=_value(combat.mobility),
            survivability=_value(combat.survivability),
            team_dependency=_value(combat.team_dependency),
            primary_loop=ReferencePrimaryLoopDTO(
                summary=combat.primary_loop.summary,
                steps=list(combat.primary_loop.steps),
            ),
            resource_loop=combat.resource_loop,
            burst_pattern=combat.burst_pattern,
            archetypes=list(combat.archetypes),
            core_mechanics=list(combat.core_mechanics),
            role_rationale=dict(combat.role_rationale),
            evidence=[
                ReferenceEvidenceDTO(
                    dimension=item.dimension,
                    token=item.token,
                    ability_ids=list(item.ability_ids),
                    mechanic_refs=[
                        ReferenceMechanicRefDTO(kind=ref.kind, id=ref.id)
                        for ref in item.mechanic_refs
                    ],
                    note=item.note,
                )
                for item in combat.evidence
            ],
        ),
        character_fantasy=reference.character_design.character_fantasy,
        personality_archetypes=list(reference.character_design.personality_archetypes),
        identity_hooks=list(reference.character_design.identity_hooks),
        narrative_hooks=list(reference.character_design.narrative_hooks),
        visual_motifs=list(reference.character_design.visual_motifs),
        primary_selling_points=list(reference.product_design.primary_selling_points),
        gameplay_hooks=list(reference.product_design.gameplay_hooks),
        visual_hooks=list(reference.product_design.visual_hooks),
        narrative_design_hooks=list(reference.product_design.narrative_hooks),
        novelty_dimensions=list(reference.product_design.novelty_dimensions),
        strongest_differentiators=list(reference.differentiation.strongest_differentiators),
        common_patterns=list(reference.differentiation.common_patterns),
        unusual_patterns=list(reference.differentiation.unusual_patterns),
        extracted_patterns=list(reference.design_patterns.extracted_patterns),
        combat_signature=list(reference.similarity_features.combat_signature),
        narrative_signature=list(reference.similarity_features.narrative_signature),
        presentation_signature=list(reference.similarity_features.presentation_signature),
    )


def to_reference_detail(
    reference: CharacterReference,
    catalog: GameCatalog | None,
    baseline_id: str | None,
) -> ReferenceCharacterDetailDTO:
    facts = reference.facts
    return ReferenceCharacterDetailDTO(
        schema_version="web-reference-character/0.1",
        reference_id=reference.reference_id,
        identity=_identity(reference, catalog),
        facts=_facts(reference),
        abilities=[
            ReferenceAbilityDTO(
                ability_id=item.ability_id,
                native_name=item.native_name,
                native_category=item.native_category,
                normalized_category=item.normalized_category,
                description_summary=item.description_summary,
            )
            for item in facts.combat.abilities
        ],
        combat_analysis=_analysis(reference.analysis) if reference.analysis is not None else None,
        sources=[
            ReferenceSourceDTO(
                source_id=item.source_id,
                source_type=_value(item.source_type),
                publisher=item.publisher,
                title=item.title,
                url=item.url,
                language=item.language,
                published_at=_date(item.published_at),
                version_context=item.version_context,
                reliability=_value(item.reliability),
            )
            for item in reference.provenance.sources
        ],
        metadata=ReferenceMetadataDTO(
            baseline_id=baseline_id,
            facts_schema_version=facts.schema_version,
            analysis_schema_version=(
                reference.analysis.schema_version if reference.analysis is not None else None
            ),
            sources_schema_version=reference.provenance.schema_version,
            verification_status=_value(reference.quality.verification_status),
            analysis_status=_value(reference.quality.analysis_status),
            completeness=_coverage(reference),
            warnings=list(reference.quality.warnings),
        ),
    )


__all__ = ["to_reference_detail", "to_reference_list", "to_reference_summary"]
