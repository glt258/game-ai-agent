from __future__ import annotations

from enum import Enum
from typing import Any

from .models import ModelInvocationAudit


class AgentError(Exception):
    """Base error for the deterministic NPC conversation runtime."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # Optional sanitized structural-recovery metadata.  It is attached to
        # failures so live renderers can distinguish recovery from Canon
        # repair without exposing model content.
        self.contract_recovery = None


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


class ModelCapabilityError(ModelConfigurationError):
    """Raised before a request when a profile cannot satisfy an Agent contract."""


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

    def __init__(
        self,
        message: str,
        *,
        finalization_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        # Shape-only metadata populated by the finalization parser.  It never
        # contains response values, raw JSON, or arbitrary model-generated keys.
        self.finalization_diagnostics = finalization_diagnostics


class FinalizationContextFailureReason(str, Enum):
    """Finite, content-free reasons for finalization-context rejection."""

    HISTORY_PAIRING_MISMATCH = "HISTORY_PAIRING_MISMATCH"
    TOOL_AUDIT_MISMATCH = "TOOL_AUDIT_MISMATCH"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"
    CANON_TYPE_MISMATCH = "CANON_TYPE_MISMATCH"
    RESTRICTED_LORE = "RESTRICTED_LORE"
    EMPTY_FACTUAL_PAYLOAD = "EMPTY_FACTUAL_PAYLOAD"
    SOURCE_RECONSTRUCTION_FAILED = "SOURCE_RECONSTRUCTION_FAILED"


class FinalizationContextError(ModelMalformedResponseError):
    """Raised when finalization evidence fails a deterministic invariant."""

    def __init__(
        self,
        reason: FinalizationContextFailureReason,
        message: str,
    ) -> None:
        super().__init__(message)
        self.context_failure_reason = reason


class ModelUnavailableError(ModelError):
    """Raised when a provider is temporarily unavailable."""


class ModelContextLimitError(ModelError):
    """Raised when the provider rejects an over-long request."""


class ModelRefusalError(ModelError):
    """Raised when the provider refuses a request under its contract."""


class ModelCancelledError(ModelError):
    """Raised when cooperative cancellation stops an invocation."""


class ModelDeadlineExceededError(ModelError):
    """Raised when an invocation's absolute deadline is exhausted."""
