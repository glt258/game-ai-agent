from agents.models import (
    ModelAttemptAudit,
    ModelInvocationAudit,
    ModelUsage,
    summarize_model_usage,
)
from web.mappers.character_generation import to_model_invocation


def _audit(usage=None, attempts=()):
    return ModelInvocationAudit(
        session_id="session",
        turn_number=1,
        provider="opencode_go",
        model="deepseek-v4-pro",
        outcome="success",
        latency_ms=12.0,
        retry_count=1,
        usage=usage,
        provider_request_id="req-safe",
        purpose="generation",
        attempts=attempts,
    )


def test_usage_summary_preserves_unknown_and_partial_values() -> None:
    full = _audit(ModelUsage(10, 5, 15))
    partial = _audit(ModelUsage(None, 2, None))

    summary = summarize_model_usage((full, partial))

    assert summary.invocation_count == 2
    assert summary.reported_usage_count == 2
    assert summary.known_input_tokens == 10
    assert summary.known_output_tokens == 7
    assert summary.known_total_tokens == 15
    assert summary.complete is False
    assert summarize_model_usage(()).known_total_tokens is None


def test_invalid_usage_is_unknown_and_web_projection_is_allowlisted() -> None:
    audit = _audit(
        ModelUsage(-1, True, "15"),
        (ModelAttemptAudit(1, "rate_limit", 3.0, error_code="rate_limit"),),
    )

    assert audit.usage == ModelUsage(None, None, None)
    projected = to_model_invocation(audit).model_dump()
    assert projected["provider_request_id"] == "req-safe"
    assert projected["attempts"][0]["error_code"] == "rate_limit"
    assert "session_id" not in projected
    assert "error_message" not in projected
