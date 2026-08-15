from __future__ import annotations

from .enums import AnalysisStatus
from .models import (
    CharacterAnalysis,
    CharacterFacts,
    CharacterReferenceQuality,
    CompletenessScore,
    SourceConflict,
)


def _ratio(populated: int, total: int) -> float:
    return round(populated / total, 4) if total else 0.0


def calculate_completeness(
    facts: CharacterFacts,
    analysis: CharacterAnalysis | None,
) -> CompletenessScore:
    """Calculate deterministic v0.1 section scores from populated structured fields.

    Required identity fields count toward identity. Combat scores taxonomy and abilities.
    Narrative and presentation score their explicitly populated lists/fields. Analysis
    scores the eight top-level analysis sections when an analysis document exists.
    """
    identity = _ratio(
        sum(bool(value) for value in (facts.identity.game_id, facts.identity.names.canonical)),
        2,
    )
    combat = _ratio(
        int(bool(facts.combat.native_taxonomy.labels))
        + int(bool(facts.combat.abilities)),
        2,
    )
    narrative_values = (
        facts.narrative.faction,
        facts.narrative.occupation,
        facts.narrative.affiliations,
        facts.narrative.public_identity,
    )
    narrative = _ratio(sum(bool(value) for value in narrative_values), 4)
    presentation = _ratio(
        int(bool(facts.presentation.official_visual_tags))
        + int(bool(facts.presentation.official_character_keywords)),
        2,
    )
    if analysis is None:
        analysis_score = 0.0
    else:
        analysis_score = _ratio(
            sum(
                bool(value)
                for value in (
                    analysis.combat_design,
                    analysis.character_design,
                    analysis.product_design,
                    analysis.differentiation,
                    analysis.design_patterns,
                    analysis.similarity_features,
                    analysis.confidence,
                    analysis.analysis_metadata,
                )
            ),
            8,
        )
    return CompletenessScore(
        identity=identity,
        combat=combat,
        narrative=narrative,
        presentation=presentation,
        analysis=analysis_score,
    )


def build_quality(
    facts: CharacterFacts,
    analysis: CharacterAnalysis | None,
    verification_status,
    conflicts: list[SourceConflict],
) -> CharacterReferenceQuality:
    warnings: list[str] = []
    if analysis is None:
        warnings.append("analysis.yaml is absent; analysis status is missing")
    elif analysis.confidence.overall is None:
        warnings.append("analysis confidence.overall is unknown")
    if not facts.presentation.official_visual_tags and not facts.presentation.official_character_keywords:
        warnings.append("no official presentation tags or keywords were supplied")
    if analysis is None:
        analysis_status = AnalysisStatus.MISSING
    elif (
        analysis.confidence.overall is not None
        and bool(analysis.combat_design.normalized_roles)
        and bool(analysis.combat_design.primary_loop.steps)
        and bool(analysis.character_design.character_fantasy)
        and bool(analysis.product_design.primary_selling_points)
        and bool(analysis.differentiation.strongest_differentiators)
        and bool(analysis.similarity_features.combat_signature)
    ):
        analysis_status = AnalysisStatus.COMPLETED
    else:
        analysis_status = AnalysisStatus.PARTIAL
    return CharacterReferenceQuality(
        completeness=calculate_completeness(facts, analysis),
        verification_status=verification_status,
        analysis_status=analysis_status,
        warnings=warnings,
        conflicts=conflicts,
    )
