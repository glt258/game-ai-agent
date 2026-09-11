from __future__ import annotations

import contextvars
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator
from uuid import uuid4

from .errors import ModelConfigurationError


class OperationDeadline:
    """Monotonic absolute deadline shared by one logical operation."""

    def __init__(
        self,
        budget_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(budget_seconds, bool) or not isinstance(budget_seconds, (int, float)):
            raise ModelConfigurationError("Operation deadline must be a number")
        if budget_seconds <= 0 or not math.isfinite(float(budget_seconds)):
            raise ModelConfigurationError("Operation deadline must be positive and finite")
        self._monotonic = monotonic
        self.started_at = monotonic()
        self.expires_at = self.started_at + float(budget_seconds)

    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - self._monotonic())

    def elapsed_ms(self) -> float:
        return max(0.0, (self._monotonic() - self.started_at) * 1000.0)

    def remaining_ms(self) -> float:
        return self.remaining_seconds() * 1000.0

    def expired(self) -> bool:
        return self.remaining_seconds() <= 0

    def raise_if_expired(self) -> None:
        if self.expired():
            raise DeadlineExceededError()


@dataclass(frozen=True)
class LiveExecutionProgressSnapshot:
    """Content-free progress captured when a live job reaches a terminal timeout."""

    timeout_source: str | None
    execution_phase: str
    action_phase: str | None
    action_round_index: int | None
    semantic_tool_choice: str | None
    wire_tool_choice: str | None
    logical_invocations_completed: int
    provider_attempts_completed: int
    provider_call_in_flight: bool
    last_completed_stage: str
    queue_wait_ms: float = 0.0
    action_loop_ms: float = 0.0
    finalization_context_ms: float = 0.0
    final_provider_ms: float = 0.0
    final_provider_start_offset_ms: float | None = None
    final_provider_remaining_budget_ms: float | None = None
    logical_invocation_index: int | None = None
    logical_invocation_started_offset_ms: float | None = None
    logical_invocation_remaining_budget_ms: float | None = None
    current_provider_attempt_index: int | None = None
    provider_attempts_started: int = 0
    logical_invocations_started: int = 0

    def to_dict(self) -> dict[str, object | None]:
        return {
            "timeout_source": self.timeout_source,
            "execution_phase": self.execution_phase,
            "action_phase": self.action_phase,
            "action_round_index": self.action_round_index,
            "semantic_tool_choice": self.semantic_tool_choice,
            "wire_tool_choice": self.wire_tool_choice,
            "logical_invocations_completed": self.logical_invocations_completed,
            "provider_attempts_completed": self.provider_attempts_completed,
            "provider_call_in_flight": self.provider_call_in_flight,
            "last_completed_stage": self.last_completed_stage,
            "queue_wait_ms": self.queue_wait_ms,
            "action_loop_ms": self.action_loop_ms,
            "finalization_context_ms": self.finalization_context_ms,
            "final_provider_ms": self.final_provider_ms,
            "final_provider_start_offset_ms": self.final_provider_start_offset_ms,
            "final_provider_remaining_budget_ms": self.final_provider_remaining_budget_ms,
            "logical_invocation_index": self.logical_invocation_index,
            "logical_invocation_started_offset_ms": self.logical_invocation_started_offset_ms,
            "logical_invocation_remaining_budget_ms": self.logical_invocation_remaining_budget_ms,
            "current_provider_attempt_index": self.current_provider_attempt_index,
            "provider_attempts_started": self.provider_attempts_started,
            "logical_invocations_started": self.logical_invocations_started,
        }


class LiveExecutionProgress:
    """Thread-safe, ephemeral progress state for one live execution."""

    _SEMANTIC_CHOICES = {"REQUIRED", "OPTIONAL", "DISABLED"}
    _EXECUTION_PHASES = {
        "ACTION_LOOP",
        "TOOL_EXECUTION",
        "FINALIZATION_CONTEXT",
        "FINAL_PROVIDER",
        "NORMALIZATION",
        "EVALUATION",
        "REPAIR",
        "UNKNOWN",
    }
    _STAGES = {
        "NONE",
        "ACTION_RECEIVED",
        "PROVIDER_COMPLETED",
        "TOOLS_EXECUTED",
        "FINALIZATION_CONTEXT_BUILT",
        "FINAL_PROVIDER_COMPLETED",
        "NORMALIZATION_COMPLETED",
        "EVALUATION_COMPLETED",
        "REPAIR_COMPLETED",
    }

    def __init__(self, *, deadline: OperationDeadline | None = None) -> None:
        self._lock = threading.RLock()
        self._deadline = deadline
        self._origin = deadline.started_at if deadline is not None else time.monotonic()
        self._clock = deadline._monotonic if deadline is not None else time.monotonic
        self._timeout_source: str | None = None
        self._execution_phase = "UNKNOWN"
        self._action_phase: str | None = None
        self._action_round_index: int | None = None
        self._semantic_tool_choice: str | None = None
        self._wire_tool_choice: str | None = None
        self._logical_invocations_completed = 0
        self._provider_attempts_completed = 0
        self._provider_call_in_flight = False
        self._provider_attempts_started = 0
        self._logical_invocations_started = 0
        self._logical_invocation_index: int | None = None
        self._logical_invocation_started_offset_ms: float | None = None
        self._logical_invocation_remaining_budget_ms: float | None = None
        self._current_provider_attempt_index: int | None = None
        self._queue_wait_ms = 0.0
        self._phase_started_at: dict[str, float] = {}
        self._phase_durations_ms: dict[str, float] = {}
        self._final_provider_start_offset_ms: float | None = None
        self._final_provider_remaining_budget_ms: float | None = None
        self._last_completed_stage = "NONE"
        self._frozen: LiveExecutionProgressSnapshot | None = None

    def mark_action_round(self, *, round_index: int, tool_invocation: str, tool_count: int) -> None:
        if isinstance(round_index, bool) or round_index < 1:
            raise ValueError("action round index must be positive")
        semantic = tool_invocation.strip().lower()
        semantic_value = semantic.upper()
        if semantic_value not in self._SEMANTIC_CHOICES:
            raise ValueError("tool invocation must be required, optional, or disabled")
        if isinstance(tool_count, bool) or tool_count < 0:
            raise ValueError("tool count must be non-negative")
        with self._lock:
            if self._frozen is not None:
                return
            self._execution_phase = "ACTION_LOOP"
            self._phase_started_at.setdefault("ACTION_LOOP", self._clock())
            self._action_phase = (
                "INITIAL_CANON_REQUIRED" if semantic == "required" else "LATER_ACTION"
            )
            self._action_round_index = round_index
            self._semantic_tool_choice = semantic_value
            self._wire_tool_choice = "required" if semantic == "required" else None
            self._last_completed_stage = "ACTION_RECEIVED"

    def mark_phase(self, phase: str, *, stage: str | None = None) -> None:
        if phase not in self._EXECUTION_PHASES:
            raise ValueError("execution phase must be finite")
        if stage is not None and stage not in self._STAGES:
            raise ValueError("progress stage must be finite")
        with self._lock:
            if self._frozen is None:
                self._close_phase_locked(self._clock())
                self._execution_phase = phase
                self._phase_started_at[phase] = self._clock()
                if stage is not None:
                    self._last_completed_stage = stage

    def provider_call_started(self) -> None:
        self.provider_attempt_started()

    def provider_attempt_started(self, *, effective_attempt_timeout_ms: float | None = None) -> None:
        with self._lock:
            if self._frozen is None:
                self._provider_call_in_flight = True
                self._provider_attempts_started += 1
                self._current_provider_attempt_index = self._provider_attempts_started
                if self._execution_phase == "FINAL_PROVIDER":
                    self._final_provider_start_offset_ms = self._offset_ms(self._clock())
                    self._final_provider_remaining_budget_ms = self._remaining_ms()

    def provider_attempt_completed(self, *, outcome: str = "SUCCESS", retry_reason: str | None = None) -> None:
        with self._lock:
            if self._frozen is None:
                self._provider_attempts_completed += 1
                self._provider_call_in_flight = False
                self._last_completed_stage = "PROVIDER_COMPLETED"

    def logical_invocation_completed(self) -> None:
        with self._lock:
            if self._frozen is None:
                self._logical_invocations_completed += 1

    def logical_invocation_started(self) -> None:
        with self._lock:
            if self._frozen is None:
                self._logical_invocations_started += 1
                self._logical_invocation_index = self._logical_invocations_started
                now = self._clock()
                self._logical_invocation_started_offset_ms = self._offset_ms(now)
                self._logical_invocation_remaining_budget_ms = self._remaining_ms()

    def set_queue_wait_ms(self, value: float) -> None:
        with self._lock:
            if self._frozen is None and math.isfinite(value) and value >= 0:
                self._queue_wait_ms = value

    def _offset_ms(self, now: float) -> float:
        return max(0.0, (now - self._origin) * 1000.0)

    def _remaining_ms(self) -> float | None:
        return self._deadline.remaining_ms() if self._deadline is not None else None

    def _close_phase_locked(self, now: float) -> None:
        phase = self._execution_phase
        started = self._phase_started_at.get(phase)
        if started is not None:
            self._phase_durations_ms[phase] = max(0.0, (now - started) * 1000.0)

    def freeze(self, *, timeout_source: str) -> LiveExecutionProgressSnapshot:
        if not timeout_source or not isinstance(timeout_source, str):
            raise ValueError("timeout source must be a finite value")
        with self._lock:
            if self._frozen is None:
                self._close_phase_locked(self._clock())
                self._timeout_source = timeout_source
                self._frozen = self._snapshot_locked()
            return self._frozen

    def snapshot(self) -> LiveExecutionProgressSnapshot:
        with self._lock:
            return self._frozen or self._snapshot_locked()

    def _snapshot_locked(self) -> LiveExecutionProgressSnapshot:
        return LiveExecutionProgressSnapshot(
            timeout_source=self._timeout_source,
            execution_phase=self._execution_phase,
            action_phase=self._action_phase,
            action_round_index=self._action_round_index,
            semantic_tool_choice=self._semantic_tool_choice,
            wire_tool_choice=self._wire_tool_choice,
            logical_invocations_completed=self._logical_invocations_completed,
            provider_attempts_completed=self._provider_attempts_completed,
            provider_call_in_flight=self._provider_call_in_flight,
            last_completed_stage=self._last_completed_stage,
            queue_wait_ms=self._queue_wait_ms,
            action_loop_ms=self._phase_durations_ms.get("ACTION_LOOP", 0.0),
            finalization_context_ms=self._phase_durations_ms.get("FINALIZATION_CONTEXT", 0.0),
            final_provider_ms=self._phase_durations_ms.get("FINAL_PROVIDER", 0.0),
            final_provider_start_offset_ms=self._final_provider_start_offset_ms,
            final_provider_remaining_budget_ms=self._final_provider_remaining_budget_ms,
            logical_invocation_index=self._logical_invocation_index,
            logical_invocation_started_offset_ms=self._logical_invocation_started_offset_ms,
            logical_invocation_remaining_budget_ms=self._logical_invocation_remaining_budget_ms,
            current_provider_attempt_index=self._current_provider_attempt_index,
            provider_attempts_started=self._provider_attempts_started,
            logical_invocations_started=self._logical_invocations_started,
        )


class CancellationToken:
    """Cooperative cancellation; it never force-kills a running Python thread."""

    def __init__(self, event: threading.Event | None = None) -> None:
        self._event = event or threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise InvocationCancelledError()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(max(0.0, timeout))


@dataclass(frozen=True)
class InvocationPolicy:
    max_attempts: int = 3
    attempt_timeout_cap: float = 30.0
    retry_backoff_seconds: float = 0.5
    operation_deadline_seconds: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 4:
            raise ModelConfigurationError("Invocation max_attempts must be from 1 to 4")
        if self.attempt_timeout_cap <= 0 or not math.isfinite(float(self.attempt_timeout_cap)):
            raise ModelConfigurationError("Invocation attempt timeout must be positive")
        if self.retry_backoff_seconds < 0 or not math.isfinite(float(self.retry_backoff_seconds)):
            raise ModelConfigurationError("Invocation backoff must not be negative")
        if self.operation_deadline_seconds is not None and (
            self.operation_deadline_seconds <= 0
            or not math.isfinite(float(self.operation_deadline_seconds))
        ):
            raise ModelConfigurationError("Invocation operation deadline must be positive")

    @classmethod
    def from_legacy(
        cls,
        *,
        timeout_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        operation_deadline_seconds: float | None = None,
    ) -> "InvocationPolicy":
        return cls(
            max_attempts=max_retries + 1,
            attempt_timeout_cap=float(timeout_seconds),
            retry_backoff_seconds=float(backoff_seconds),
            operation_deadline_seconds=operation_deadline_seconds,
        )


@dataclass(frozen=True)
class InvocationContext:
    deadline: OperationDeadline
    cancellation: CancellationToken
    policy: InvocationPolicy
    provider_session_id: str
    progress: LiveExecutionProgress


_CURRENT_CONTEXT: contextvars.ContextVar[InvocationContext | None] = contextvars.ContextVar(
    "live_invocation_context", default=None
)


def current_invocation_context() -> InvocationContext | None:
    return _CURRENT_CONTEXT.get()


def current_live_execution_progress() -> LiveExecutionProgress | None:
    context = current_invocation_context()
    return context.progress if context is not None else None


@contextmanager
def invocation_context(
    *,
    deadline: OperationDeadline,
    cancellation: CancellationToken,
    policy: InvocationPolicy,
    progress: LiveExecutionProgress | None = None,
) -> Iterator[InvocationContext]:
    context = InvocationContext(deadline, cancellation, policy, uuid4().hex, progress or LiveExecutionProgress(deadline=deadline))
    token = _CURRENT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_CONTEXT.reset(token)


@contextmanager
def default_invocation_context(
    *,
    budget_seconds: float,
    max_attempts: int = 3,
    attempt_timeout_cap: float = 30.0,
    retry_backoff_seconds: float = 0.5,
) -> Iterator[InvocationContext]:
    existing = current_invocation_context()
    if existing is not None:
        yield existing
        return
    with invocation_context(
        deadline=OperationDeadline(budget_seconds),
        cancellation=CancellationToken(),
        policy=InvocationPolicy(
            max_attempts=max_attempts,
            attempt_timeout_cap=attempt_timeout_cap,
            retry_backoff_seconds=retry_backoff_seconds,
            operation_deadline_seconds=budget_seconds,
        ),
    ) as context:
        yield context


class InvocationCancelledError(Exception):
    def __init__(self) -> None:
        super().__init__("LIVE_INVOCATION_CANCELLED")


class DeadlineExceededError(Exception):
    def __init__(self) -> None:
        super().__init__("LIVE_INVOCATION_DEADLINE_EXCEEDED")


__all__ = [
    "CancellationToken",
    "DeadlineExceededError",
    "InvocationCancelledError",
    "InvocationContext",
    "InvocationPolicy",
    "LiveExecutionProgress",
    "LiveExecutionProgressSnapshot",
    "OperationDeadline",
    "current_invocation_context",
    "current_live_execution_progress",
    "default_invocation_context",
    "invocation_context",
]
