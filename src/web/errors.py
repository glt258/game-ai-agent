from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agents.errors import (
    AgentError,
    AgentExecutionError,
    AgentToolError,
    FinalizationContextFailureReason,
    ModelAuthenticationError,
    ModelCancelledError,
    ModelCapabilityError,
    ModelConfigurationError,
    ModelContextLimitError,
    ModelDeadlineExceededError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from agents.models import ModelInvocationAudit
from persistence.errors import (
    CharacterRevisionConflictError,
    CharacterSkillPersistenceConflictError,
    PersistenceContractUnsupportedError,
    PersistenceIntegrityError,
    PersistenceRecordNotFoundError,
    PersistenceWriteConflictError,
)


class WebApplicationError(Exception):
    """Safe error crossing the Web application seam."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        stage: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
        model_invocations: Sequence[ModelInvocationAudit] = (),
        context_failure_reason: str | None = None,
    ) -> None:
        super().__init__()
        self.code = code
        self.message = message
        self.status_code = status_code
        self.stage = stage
        self.retryable = retryable
        self.details = dict(details or {})
        self.model_invocations = tuple(model_invocations)
        self.context_failure_reason = context_failure_reason


def model_invocations_from_error(error: BaseException) -> tuple[ModelInvocationAudit, ...]:
    values: list[ModelInvocationAudit] = []
    attached = getattr(error, "model_invocations", ())
    if isinstance(attached, Sequence) and not isinstance(attached, (str, bytes)):
        values.extend(item for item in attached if isinstance(item, ModelInvocationAudit))
    audit = getattr(error, "audit", None)
    if isinstance(audit, ModelInvocationAudit) and audit not in values:
        values.append(audit)
    return tuple(values)


def _provider_details(audits: Sequence[ModelInvocationAudit]) -> dict[str, Any]:
    if not audits:
        return {}
    latest = audits[-1]
    details: dict[str, Any] = {}
    if latest.provider:
        details["provider"] = latest.provider
    if latest.model:
        details["model"] = latest.model
    return details


def _provider_failure_details(
    audits: Sequence[ModelInvocationAudit],
) -> dict[str, Any]:
    details = _provider_details(audits)
    if not audits:
        return details
    latest = audits[-1]
    details.update(
        {
            "upstream_status": latest.upstream_status,
            "upstream_error_type": latest.upstream_error_type,
            "upstream_error_code": latest.upstream_error_code,
            "upstream_error_param": latest.upstream_error_param,
            "provider_request_id": latest.provider_request_id,
            "provider_status_code": latest.provider_status_code,
            "provider_retryable": latest.provider_retryable,
            "attempt_count": len(latest.attempts) if latest.attempts else None,
            "retry_count": latest.retry_count,
        }
    )
    return details


def _finalization_details(error: BaseException) -> dict[str, Any]:
    diagnostic = getattr(error, "finalization_diagnostics", None)
    if not isinstance(diagnostic, dict):
        return {}
    allowed = {
        "content_present",
        "content_length",
        "json_parse_success",
        "top_level_type",
        "key_count",
        "known_keys",
        "missing_required_keys",
        "unknown_key_count",
        "contract_reason",
    }
    result = {key: diagnostic[key] for key in allowed if key in diagnostic}
    for key in ("known_keys", "missing_required_keys"):
        if isinstance(result.get(key), tuple):
            result[key] = list(result[key])
    return result


def _action_termination_details(error: BaseException) -> dict[str, Any]:
    diagnostic = getattr(error, "action_termination_diagnostics", None)
    to_dict = getattr(diagnostic, "to_dict", None)
    if not callable(to_dict):
        return {}
    value = to_dict()
    return value if isinstance(value, dict) else {}


def map_generation_exception(error: BaseException) -> WebApplicationError:
    """Map domain/provider failures without copying exception text."""

    audits = model_invocations_from_error(error)
    details = _provider_details(audits)
    if isinstance(error, ModelAuthenticationError):
        return WebApplicationError(
            "PROVIDER_AUTHENTICATION_FAILED",
            "Configured model provider authentication failed.",
            status_code=502,
            stage="provider",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelTimeoutError):
        return WebApplicationError(
            "PROVIDER_TIMEOUT",
            "The model provider timed out after bounded retries.",
            status_code=504,
            stage="provider",
            retryable=True,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelRateLimitError):
        return WebApplicationError(
            "PROVIDER_RATE_LIMITED",
            "The model provider rate-limited the request.",
            status_code=503,
            stage="provider",
            retryable=True,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelCancelledError):
        return WebApplicationError(
            "PROVIDER_CANCELLED",
            "The live model invocation was cancelled.",
            status_code=499,
            stage="provider",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelDeadlineExceededError):
        return WebApplicationError(
            "PROVIDER_DEADLINE_EXCEEDED",
            "The live model invocation exceeded its operation deadline.",
            status_code=504,
            stage="provider",
            retryable=True,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelUnavailableError):
        return WebApplicationError(
            "PROVIDER_UNAVAILABLE",
            "The configured model provider is temporarily unavailable.",
            status_code=503,
            stage="provider",
            retryable=True,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelContextLimitError):
        return WebApplicationError(
            "MODEL_CONTEXT_LIMIT_EXCEEDED",
            "The model context limit was exceeded.",
            status_code=413,
            stage="provider",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelRefusalError):
        return WebApplicationError(
            "MODEL_REFUSED_REQUEST",
            "The model refused the request under its safety policy.",
            status_code=502,
            stage="provider",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, ModelConfigurationError):
        return WebApplicationError(
            "MODEL_CONFIGURATION_INVALID",
            "The configured model runtime is not available.",
            status_code=503,
            stage="provider",
            retryable=False,
            details={},
            model_invocations=audits,
        )
    if isinstance(error, ModelCapabilityError):
        return WebApplicationError(
            "MODEL_CAPABILITY_UNAVAILABLE",
            "The configured model runtime cannot satisfy this request.",
            status_code=503,
            stage="provider",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if (
        isinstance(error, ModelMalformedResponseError)
        and getattr(error, "reason", None) == "context_construction_failed"
    ):
        failure_details = dict(details)
        failure_details["reason_code"] = "context_construction_failed"
        failure_details["model_invocation_count"] = len(audits)
        return WebApplicationError(
            "GENERATION_CONTEXT_FAILED",
            "Character generation context could not be constructed safely.",
            status_code=502,
            stage=getattr(error, "phase", "finalization_context"),
            retryable=False,
            details=failure_details,
            model_invocations=audits,
            context_failure_reason=(
                error.context_failure_reason.value
                if isinstance(
                    getattr(error, "context_failure_reason", None),
                    FinalizationContextFailureReason,
                )
                else None
            ),
        )
    if isinstance(error, ModelMalformedResponseError):
        failure_details = dict(details)
        finalization = _finalization_details(error)
        if finalization:
            failure_details["finalization"] = finalization
        if getattr(error, "phase", None) == "action_termination":
            action_termination = _action_termination_details(error)
            if action_termination:
                failure_details["action_termination"] = action_termination
        return WebApplicationError(
            "MODEL_RESPONSE_INVALID",
            "The model returned a response that did not satisfy the runtime contract.",
            status_code=502,
            stage=getattr(error, "phase", "generation"),
            retryable=False,
            details=failure_details,
            model_invocations=audits,
        )
    if isinstance(error, ModelProviderError):
        provider_retryable = audits[-1].provider_retryable if audits else None
        # `retryable` is the Web/UI automatic-action policy. The nullable
        # `provider_retryable` detail remains the upstream fact and must not
        # turn UNKNOWN into a claimed provider-side false.
        return WebApplicationError(
            "PROVIDER_FAILURE",
            "模型服务调用失败，请稍后重试。",
            status_code=502,
            stage="generation_provider_invocation",
            retryable=provider_retryable if isinstance(provider_retryable, bool) else False,
            details=_provider_failure_details(audits),
            model_invocations=audits,
        )
    if isinstance(error, AgentToolError):
        return WebApplicationError(
            "AUTHORING_TOOL_REJECTED",
            "The authoring tool contract rejected the generation request.",
            status_code=502,
            stage="retrieval",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    if isinstance(error, AgentExecutionError):
        reason = getattr(error, "reason", None)
        code = {
            "tool_round_limit_exhausted": "GENERATION_EXHAUSTED",
            "invalid_termination_signal": "MODEL_TERMINATION_INVALID",
            "context_construction_failed": "GENERATION_CONTEXT_FAILED",
        }.get(reason, "GENERATION_NOT_COMPLETED")
        failure_details = dict(details)
        failure_details["reason_code"] = reason or "generation_execution_failed"
        failure_details["model_invocation_count"] = len(audits)
        if getattr(error, "phase", None) == "action_termination":
            action_termination = _action_termination_details(error)
            if action_termination:
                failure_details["action_termination"] = action_termination
        recovery = getattr(error, "contract_recovery", None)
        recovery_status = getattr(recovery, "status", None)
        if isinstance(recovery_status, str):
            failure_details["contract_recovery_status"] = recovery_status
        return WebApplicationError(
            code,
            "Character generation did not complete safely.",
            status_code=502,
            stage=getattr(error, "phase", "generation"),
            retryable=False,
            details=failure_details,
            model_invocations=audits,
        )
    if isinstance(error, AgentError):
        return WebApplicationError(
            "AGENT_FAILURE",
            "The character authoring agent failed safely.",
            status_code=502,
            stage="generation",
            retryable=False,
            details=details,
            model_invocations=audits,
        )
    return WebApplicationError(
        "INTERNAL_ERROR",
        "The Web application could not complete the request.",
        status_code=500,
        stage="web",
        retryable=False,
        details={},
        model_invocations=audits,
    )


def map_validation_exception(error: BaseException) -> WebApplicationError:
    """Map edited-draft parsing/context failures without copying exception text."""

    if isinstance(error, ModelMalformedResponseError):
        return WebApplicationError(
            "DRAFT_CONTRACT_INVALID",
            "The edited draft does not satisfy the CharacterDraft contract.",
            status_code=422,
            stage="validation",
            retryable=False,
        )
    if isinstance(error, (TypeError, ValueError)):
        return WebApplicationError(
            "VALIDATION_CONTEXT_INVALID",
            "The validation context could not be constructed.",
            status_code=422,
            stage="validation",
            retryable=False,
        )
    return WebApplicationError(
        "VALIDATION_RUNTIME_ERROR",
        "Character validation could not complete safely.",
        status_code=500,
        stage="validation",
        retryable=False,
    )


def map_persistence_exception(error: BaseException) -> WebApplicationError:
    """Map persistence failures to safe Saved Character HTTP errors."""

    if isinstance(error, PersistenceRecordNotFoundError):
        return WebApplicationError(
            "SAVED_CHARACTER_NOT_FOUND",
            "Saved character not found.",
            status_code=404,
            stage="persistence",
            retryable=False,
        )
    if isinstance(error, CharacterRevisionConflictError):
        return WebApplicationError(
            "SAVED_CHARACTER_CONFLICT",
            "This saved character changed since it was opened. Reload the latest saved revision before saving again.",
            status_code=409,
            stage="persistence",
            retryable=False,
            details={
                "resource": "character_revision",
                "expected_current_revision_id": error.expected_revision_id,
                "current_revision_id": error.current_revision_id,
            },
        )
    if isinstance(error, CharacterSkillPersistenceConflictError):
        return WebApplicationError(
            "SAVED_CHARACTER_CONFLICT",
            "This saved character changed since it was opened. Reload the latest saved workspace before saving again.",
            status_code=409,
            stage="persistence",
            retryable=False,
            details={
                "resource": error.resource,
                "expected": error.expected,
                "current": error.current,
            },
        )
    if isinstance(error, PersistenceWriteConflictError):
        return WebApplicationError(
            "SAVED_CHARACTER_CONFLICT",
            "The saved workspace changed before this save completed.",
            status_code=409,
            stage="persistence",
            retryable=False,
        )
    if isinstance(error, PersistenceContractUnsupportedError):
        return WebApplicationError(
            "PERSISTED_CONTRACT_UNSUPPORTED",
            "The saved character uses a persistence contract this runtime does not support.",
            status_code=500,
            stage="persistence",
            retryable=False,
        )
    if isinstance(error, PersistenceIntegrityError):
        return WebApplicationError(
            "PERSISTED_CHARACTER_INTEGRITY_ERROR",
            "The saved character could not be opened because persisted data failed integrity validation.",
            status_code=500,
            stage="persistence",
            retryable=False,
        )
    return WebApplicationError(
        "SAVED_CHARACTER_ERROR",
        "The saved Character workspace could not be completed safely.",
        status_code=500,
        stage="persistence",
        retryable=False,
    )


__all__ = [
    "WebApplicationError",
    "map_generation_exception",
    "map_validation_exception",
    "map_persistence_exception",
    "model_invocations_from_error",
]
