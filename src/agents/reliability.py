from __future__ import annotations

import contextvars
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

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

    def expired(self) -> bool:
        return self.remaining_seconds() <= 0

    def raise_if_expired(self) -> None:
        if self.expired():
            raise DeadlineExceededError()


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


_CURRENT_CONTEXT: contextvars.ContextVar[InvocationContext | None] = contextvars.ContextVar(
    "live_invocation_context", default=None
)


def current_invocation_context() -> InvocationContext | None:
    return _CURRENT_CONTEXT.get()


@contextmanager
def invocation_context(
    *,
    deadline: OperationDeadline,
    cancellation: CancellationToken,
    policy: InvocationPolicy,
) -> Iterator[InvocationContext]:
    context = InvocationContext(deadline, cancellation, policy)
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
    "OperationDeadline",
    "current_invocation_context",
    "default_invocation_context",
    "invocation_context",
]
