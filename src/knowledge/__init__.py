"""Knowledge boundary resolution for Along the Street."""

from .context import KnowledgeContext
from .errors import (
    KnowledgeAccessDenied,
    KnowledgeConfigurationError,
    KnowledgeContextValidationError,
    UnknownCharacterError,
    UnknownLoreError,
)
from .models import KnowledgeDecision
from .resolver import KnowledgeResolver
from .scope_registry import ConditionScopeRegistry, ScopeBinding

__all__ = [
    "KnowledgeAccessDenied",
    "KnowledgeConfigurationError",
    "KnowledgeContextValidationError",
    "KnowledgeContext",
    "KnowledgeDecision",
    "KnowledgeResolver",
    "ConditionScopeRegistry",
    "ScopeBinding",
    "UnknownCharacterError",
    "UnknownLoreError",
]
