from __future__ import annotations

import threading
import time

import pytest

from agents import (
    CancellationToken,
    LiveLLMAdapter,
    ModelAuthenticationError,
    ModelCancelledError,
    ModelDeadlineExceededError,
    ModelRateLimitError,
    ModelUnavailableError,
    OperationDeadline,
    ProviderClientError,
    ProviderCompletion,
    InvocationPolicy,
    LiveExecutionProgress,
    current_invocation_context,
    default_invocation_context,
    invocation_context,
)
from web.errors import WebApplicationError
from web.services.live_jobs import LiveJobRegistry


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def complete(self, **request: object) -> ProviderCompletion:
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


def _adapter(client: _Client, **kwargs: object) -> LiveLLMAdapter:
    return LiveLLMAdapter(
        client,
        provider="openai",
        model="test-model",
        sleep=lambda _seconds: None,
        **kwargs,
    )


def test_operation_deadline_uses_monotonic_remaining_budget() -> None:
    now = [10.0]
    deadline = OperationDeadline(2.0, monotonic=lambda: now[0])
    now[0] = 11.25
    assert deadline.remaining_seconds() == pytest.approx(0.75)
    assert not deadline.expired()
    now[0] = 12.0
    assert deadline.expired()


def test_parent_invocation_context_owns_one_session_affinity_id():
    with default_invocation_context(budget_seconds=2.0):
        first = current_invocation_context().provider_session_id
        with default_invocation_context(budget_seconds=2.0):
            assert current_invocation_context().provider_session_id == first
    with default_invocation_context(budget_seconds=2.0):
        second = current_invocation_context().provider_session_id
    assert first != second


def test_adapter_retries_transient_failure_with_bounded_attempts() -> None:
    client = _Client(
        [
            ProviderClientError("rate_limit", retryable=True, status_code=429),
            ProviderCompletion(text='{"segments":[{"segment_id":"1","kind":"non_factual","text":"这件事值得继续核实。","evidence_ids":[]}]}'),
        ]
    )
    _adapter(client, max_retries=1).generate(_prompt())
    assert len(client.calls) == 2
    assert client.calls[0]["timeout_seconds"] == 30.0


def test_adapter_maps_non_retryable_provider_categories() -> None:
    for kind, expected in (
        ("authentication", ModelAuthenticationError),
        ("rate_limit", ModelRateLimitError),
        ("unavailable", ModelUnavailableError),
    ):
        client = _Client([ProviderClientError(kind, retryable=False)])
        with pytest.raises(expected):
            _adapter(client, max_retries=3).generate(_prompt())
        assert len(client.calls) == 1


def test_adapter_does_not_call_provider_after_cancellation() -> None:
    token = CancellationToken()
    token.cancel()
    client = _Client([ProviderCompletion(text="unused")])
    with pytest.raises(ModelCancelledError):
        _adapter(client, cancellation=token).generate(_prompt())
    assert client.calls == []


def test_adapter_does_not_retry_after_expired_deadline() -> None:
    client = _Client([ProviderCompletion(text="unused")])
    deadline = OperationDeadline(0.05)
    time.sleep(0.1)
    with pytest.raises(ModelDeadlineExceededError):
        with invocation_context(
            deadline=deadline,
            cancellation=CancellationToken(),
            policy=InvocationPolicy(max_attempts=3, attempt_timeout_cap=1),
        ):
            _adapter(client).generate(_prompt())
    assert client.calls == []


def test_job_timeout_keeps_physical_capacity_until_worker_settles() -> None:
    registry = LiveJobRegistry(max_workers=1, max_in_flight=1, timeout_seconds=0.02, ttl_seconds=1)
    started = threading.Event()
    release = threading.Event()

    def work() -> str:
        started.set()
        release.wait(1)
        return "late-success"

    first = registry.submit(kind="skill_playground", provider="openai", model="m", work=work)
    assert started.wait(1)
    time.sleep(0.05)
    assert registry.get(first.job_id).error is not None
    with pytest.raises(WebApplicationError) as busy:
        registry.submit(kind="skill_playground", provider="openai", model="m", work=lambda: "second")
    assert busy.value.code == "LIVE_EXECUTION_BUSY"
    release.set()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        try:
            second = registry.submit(kind="skill_playground", provider="openai", model="m", work=lambda: "second")
            assert second.status in {"PENDING", "RUNNING", "SUCCEEDED"}
            break
        except WebApplicationError:
            time.sleep(0.01)
    else:
        raise AssertionError("physical worker capacity did not recover")
    registry.shutdown()


def test_late_failure_cannot_replace_timeout_and_shutdown_rejects_new_work() -> None:
    registry = LiveJobRegistry(max_workers=1, max_in_flight=1, timeout_seconds=0.02, ttl_seconds=1)
    release = threading.Event()

    def work() -> None:
        release.wait(1)
        raise RuntimeError("late provider detail")

    first = registry.submit(kind="skill_playground", provider="openai", model="m", work=work)
    time.sleep(0.05)
    timed_out = registry.get(first.job_id)
    assert timed_out.status == "FAILED"
    assert timed_out.error is not None and timed_out.error.code == "BACKEND_REQUEST_TIMEOUT"
    release.set()
    time.sleep(0.05)
    final = registry.get(first.job_id)
    assert final.error is not None and final.error.code == "BACKEND_REQUEST_TIMEOUT"
    registry.shutdown()
    with pytest.raises(WebApplicationError) as closed:
        registry.submit(kind="skill_playground", provider="openai", model="m", work=lambda: None)
    assert closed.value.code == "LIVE_EXECUTION_SHUTDOWN"


def test_timeout_progress_snapshot_freezes_and_suppresses_late_updates() -> None:
    progress = LiveExecutionProgress()
    progress.mark_action_round(round_index=6, tool_invocation="optional", tool_count=9)
    progress.provider_call_started()

    frozen = progress.freeze(timeout_source="LIVE_EXECUTION_BUDGET")
    progress.provider_attempt_completed()
    progress.logical_invocation_completed()

    assert frozen.to_dict() == {
        "timeout_source": "LIVE_EXECUTION_BUDGET",
        "execution_phase": "ACTION_LOOP",
        "action_phase": "LATER_ACTION",
        "action_round_index": 6,
        "semantic_tool_choice": "OPTIONAL",
        "wire_tool_choice": None,
        "logical_invocations_completed": 0,
        "provider_attempts_completed": 0,
        "provider_call_in_flight": True,
        "last_completed_stage": "ACTION_RECEIVED",
    }
    assert progress.snapshot() == frozen


def test_registry_timeout_exposes_safe_progress_and_keeps_terminal_state() -> None:
    registry = LiveJobRegistry(max_workers=1, max_in_flight=1, timeout_seconds=10, ttl_seconds=1)
    started = threading.Event()
    release = threading.Event()
    settled = threading.Event()

    def work() -> str:
        progress = current_invocation_context().progress
        progress.mark_action_round(round_index=1, tool_invocation="required", tool_count=9)
        progress.provider_call_started()
        started.set()
        release.wait(1)
        progress.provider_attempt_completed()
        settled.set()
        return "late-success"

    first = registry.submit(kind="character_generation", provider="openai", model="m", work=work)
    assert started.wait(1)
    registry._mark_timeout(first.job_id)  # noqa: SLF001 - deterministic timer seam
    timed_out = registry.get(first.job_id)
    assert timed_out.error is not None
    assert timed_out.error.code == "BACKEND_REQUEST_TIMEOUT"
    assert timed_out.error.details["timeout_source"] == "LIVE_EXECUTION_BUDGET"
    assert timed_out.error.details["execution_phase"] == "ACTION_LOOP"
    assert timed_out.error.details["action_phase"] == "INITIAL_CANON_REQUIRED"
    assert timed_out.error.details["action_round_index"] == 1
    assert timed_out.error.details["provider_call_in_flight"] is True
    release.set()
    assert settled.wait(1)
    final = registry.get(first.job_id)
    assert final.error is not None and final.error.code == "BACKEND_REQUEST_TIMEOUT"
    assert final.error.details["provider_call_in_flight"] is True
    registry.shutdown()


def _prompt():
    from agents.models import AgentPrompt, NpcCharacterView, NpcRuntimeView

    return AgentPrompt(
        system_contract="test",
        character=NpcCharacterView(
            "c", "C", "", (), (), "", "", (), "", ""
        ),
        runtime=NpcRuntimeView("s", "", None, (), ()),
        messages=(),
        available_tools=(),
        session_id="test",
        turn_number=1,
    )
