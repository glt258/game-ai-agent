from __future__ import annotations

from .models import ModelInvocationAudit


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


class ModelError(AgentError):
    """Base error exposed by provider-neutral model adapters."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # Optional provider-neutral failure audit attached by adapters that
        # recorded a failed model call. Holds sanitized metadata only: never
        # raw model output, prompts, tool results, or player input.
        self.audit: ModelInvocationAudit | None = None


class ModelConfigurationError(ModelError):
    """Raised before a request when live model configuration is invalid."""


class ModelAuthenticationError(ModelError):
    """Raised when the provider rejects configured credentials."""


class ModelTimeoutError(ModelError):
    """Raised after bounded retries for a provider timeout."""


class ModelRateLimitError(ModelError):
    """Raised after bounded retries for provider rate limiting."""


class ModelProviderError(ModelError):
    """Raised for normalized provider or network failures."""


class ModelMalformedResponseError(ModelError):
    """Raised when a provider response cannot become a safe ModelTurn."""
