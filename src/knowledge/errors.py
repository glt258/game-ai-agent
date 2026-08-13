class KnowledgeResolverError(Exception):
    """Base class for domain errors raised by the resolver."""


class UnknownCharacterError(KnowledgeResolverError):
    def __init__(self, character_id: str):
        super().__init__(f"Unknown character: {character_id}")
        self.character_id = character_id


class UnknownLoreError(KnowledgeResolverError):
    def __init__(self, lore_id: str):
        super().__init__(f"Unknown lore: {lore_id}")
        self.lore_id = lore_id


class KnowledgeConfigurationError(KnowledgeResolverError):
    """Raised when the knowledge policy cannot be safely interpreted."""


class KnowledgeContextValidationError(KnowledgeResolverError):
    """Raised when runtime context contains an unknown canonical ID."""

    def __init__(self, field: str, values: set[str]):
        self.field = field
        self.values = frozenset(values)
        super().__init__(f"Unknown runtime {field} ID(s): {sorted(values)}")


class KnowledgeAccessDenied(KnowledgeResolverError):
    """Raised by require_access when a valid query is denied."""

    def __init__(self, decision):
        super().__init__(decision.reason)
        self.decision = decision
