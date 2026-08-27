"""Character Intelligence Layer public package."""

from combat_semantics import (
    CANONICAL_COMBAT_ROLES,
    CombatRole,
    CombatRoleNormalization,
    CombatRoleProfile,
)

from .compiler import (
    CompileResult,
    CompilerProvenance,
    CompilerProvenanceEntry,
    SemanticMappingRegistry,
    SkillKitCompilerError,
    compile_skill_semantic_ir,
    validate_reference_integrity,
)
from .hybrid_ir import (
    FakeProvider,
    HybridGenerationContext,
    HybridSemanticIRRunner,
    build_model_facing_contract,
    build_model_facing_request,
    run_fake_pipeline,
)
from .intent import (
    CharacterDesignIntent,
    CharacterDesignIntentParser,
    DeterministicCharacterDesignIntentParser,
)
from .planner import CharacterDesignPlan
from .semantic_ir import (
    SemanticEffect,
    SemanticFeedback,
    SemanticIRValidator,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SkillSemanticIR,
    ValidatedSkillSemanticIR,
    parse_semantic_ir,
    validate_skill_semantic_ir,
)

__all__ = [
    "CharacterDesignIntent",
    "CharacterDesignIntentParser",
    "CharacterDesignPlan",
    "DeterministicCharacterDesignIntentParser",
    "CANONICAL_COMBAT_ROLES",
    "CombatRole",
    "CombatRoleNormalization",
    "CombatRoleProfile",
    "CompileResult",
    "CompilerProvenance",
    "CompilerProvenanceEntry",
    "FakeProvider",
    "HybridGenerationContext",
    "HybridSemanticIRRunner",
    "SemanticMappingRegistry",
    "SkillKitCompilerError",
    "SemanticEffect",
    "SemanticFeedback",
    "SemanticMechanic",
    "SemanticRolePath",
    "SemanticTrigger",
    "SkillSemanticIR",
    "SemanticIRValidator",
    "ValidatedSkillSemanticIR",
    "compile_skill_semantic_ir",
    "build_model_facing_contract",
    "build_model_facing_request",
    "parse_semantic_ir",
    "run_fake_pipeline",
    "validate_reference_integrity",
    "validate_skill_semantic_ir",
]
