class AgentError(Exception):
    """Base error for the deterministic NPC conversation runtime."""


class AgentExecutionError(AgentError):
    """Raised when the model/tool loop cannot safely finish."""


class AgentToolError(AgentError):
    """Raised for unknown tools or invalid tool arguments."""


class GroundingError(AgentError):
    """Raised when a model cites Lore not returned in the current turn."""


class SessionValidationError(AgentError):
    """Raised when a session is used with the wrong character or Story."""
