"""Character design planning contracts."""

from .character_plan import (
    CharacterAffiliationContext,
    CharacterDesignPlan,
    build_character_design_plan,
)

__all__ = [
    "CharacterAffiliationContext",
    "CharacterDesignPlan",
    "build_character_design_plan",
]


_PLANNER_V1_EXPORTS = {
    "PLANNER_V1_INVOCATION_PURPOSE",
    "PLANNER_V1_RESPONSE_FORMAT",
    "PLANNER_V1_SYSTEM_CONTRACT",
    "CharacterPlannerV1Diagnostics",
    "CharacterPlannerV1Error",
    "CharacterPlannerV1Result",
    "build_character_planner_proposal_schema",
    "build_character_planner_prompt",
    "plan_character_v2",
    "run_character_planner_v1",
    "validate_character_planner_proposal",
}

_CONCEPT_V2_EXPORTS = {
    "CharacterConceptSeedStatus",
    "CharacterConceptV2Error",
    "CharacterConceptSeedV2",
    "CharacterConceptSelectionV2",
    "build_character_concept_seed_schema",
    "build_character_concept_search_schema",
    "build_character_concept_selection_schema",
    "validate_character_concept_search_response",
    "validate_character_concept_selection",
    "validate_concept_seed_set",
}

_CONCEPT_SEARCH_V2_EXPORTS = {
    "CONCEPT_SEARCH_INVOCATION_PURPOSE",
    "CONCEPT_SEARCH_RESPONSE_FORMAT",
    "CONCEPT_SEARCH_SYSTEM_CONTRACT",
    "CONCEPT_SELECTION_INVOCATION_PURPOSE",
    "CONCEPT_SELECTION_RESPONSE_FORMAT",
    "CONCEPT_SELECTION_SYSTEM_CONTRACT",
    "ConceptSearchDiagnostics",
    "ConceptSearchResult",
    "ConceptSelectionDiagnostics",
    "ConceptSelectionResult",
    "CharacterPlanningV2Phase4Result",
    "build_concept_search_prompt",
    "build_concept_selector_prompt",
    "run_concept_search_v2",
    "run_concept_selector_v2",
    "run_character_planning_v2_phase4",
}

_GENERATION_SPEC_V1_EXPORTS = {
    "CHARACTER_GENERATION_V2_ROUTE",
    "RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA",
    "GenerationSpecAuditMetadataV1",
    "GenerationSpecFreezeError",
    "GenerationSpecValidationReason",
    "GenerationSpecValidationResult",
    "GenerationSpecValidator",
    "ResolvedCharacterDirectionV1",
    "ResolvedCharacterGenerationSpecV1",
    "freeze_resolved_character_generation_spec",
}


def __getattr__(name: str):
    if name in _PLANNER_V1_EXPORTS:
        from . import character_planner_v2

        value = getattr(character_planner_v2, name)
        globals()[name] = value
        return value
    if name in _CONCEPT_V2_EXPORTS:
        from . import character_concept_v2

        value = getattr(character_concept_v2, name)
        globals()[name] = value
        return value
    if name in _CONCEPT_SEARCH_V2_EXPORTS:
        from . import concept_search_v2

        value = getattr(concept_search_v2, name)
        globals()[name] = value
        return value
    if name in _GENERATION_SPEC_V1_EXPORTS:
        from . import character_generation_spec

        value = getattr(character_generation_spec, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__.extend(sorted(_PLANNER_V1_EXPORTS))
__all__.extend(sorted(_CONCEPT_V2_EXPORTS))
__all__.extend(sorted(_CONCEPT_SEARCH_V2_EXPORTS))
__all__.extend(sorted(_GENERATION_SPEC_V1_EXPORTS))
