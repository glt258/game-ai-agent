"""Character Intelligence Layer public package."""

from combat_semantics import (
    CANONICAL_COMBAT_ROLES,
    CombatRole,
    CombatRoleNormalization,
    CombatRoleProfile,
)

from .intent import (
    CharacterDesignIntent,
    CharacterDesignIntentParser,
    DeterministicCharacterDesignIntentParser,
)
from .planner import CharacterDesignPlan
from .compiler import (
    CompileResult,
    CompilerProvenance,
    CompilerProvenanceEntry,
    SemanticMappingRegistry,
    SkillKitCompilerError,
    compile_skill_semantic_ir,
    validate_reference_integrity,
)
from .semantic_ir import (
    SemanticEffect,
    SemanticFeedback,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SkillSemanticIR,
    SemanticIRValidator,
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
    "parse_semantic_ir",
    "validate_reference_integrity",
    "validate_skill_semantic_ir",
]
