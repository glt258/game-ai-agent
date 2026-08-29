"""Deterministic semantic-to-canonical SkillKit compiler seam."""

from .provenance import COMPILER_VERSION, COMPILER_VERSION_V2, CompilerProvenance, CompilerProvenanceEntry
from .skillkit_compiler import (
    DEFAULT_MAPPING_REGISTRY,
    SEMANTIC_EFFECT_OPERATION_MAP,
    CompilerProvenanceResult,
    CompileResult,
    SemanticMappingRegistry,
    SkillKitCompilerError,
    compile_skill_semantic_ir,
    validate_reference_integrity,
)

__all__ = [
    "COMPILER_VERSION",
    "COMPILER_VERSION_V2",
    "DEFAULT_MAPPING_REGISTRY",
    "SEMANTIC_EFFECT_OPERATION_MAP",
    "CompilerProvenance",
    "CompilerProvenanceEntry",
    "CompilerProvenanceResult",
    "CompileResult",
    "SemanticMappingRegistry",
    "SkillKitCompilerError",
    "compile_skill_semantic_ir",
    "validate_reference_integrity",
]
