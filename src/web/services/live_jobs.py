from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from ..errors import WebApplicationError

LiveJobStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
LiveJobKind = Literal["skill_playground", "character_skill_design"]


@dataclass(frozen=True)
class LiveJobSnapshot:
    job_id: str
    kind: LiveJobKind
    status: LiveJobStatus
    provider: str
    model: str
    poll_after_ms: int
    elapsed_ms: float
    result: Any = None
    error: WebApplicationError | None = None


@dataclass
class _LiveJob:
    job_id: str
    kind: LiveJobKind
    provider: str
    model: str
    created_at: float
    status: LiveJobStatus = "PENDING"
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: WebApplicationError | None = None
    timer: threading.Timer | None = None


class LiveJobRegistry:
    """Small process-local registry for long-running live Web executions."""

    def __init__(
        self,
        *,
        max_workers: int = 2,
        max_in_flight: int = 2,
        timeout_seconds: float = 90.0,
        ttl_seconds: float = 900.0,
        poll_after_ms: int = 1500,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_workers < 1 or max_in_flight < 1 or max_in_flight < max_workers:
            raise ValueError("live job concurrency must be positive and bounded")
        if timeout_seconds <= 0 or ttl_seconds <= 0 or poll_after_ms < 250:
            raise ValueError("live job timing must be positive and bounded")
        self.max_in_flight = max_in_flight
        self.timeout_seconds = float(timeout_seconds)
        self.ttl_seconds = float(ttl_seconds)
        self.poll_after_ms = poll_after_ms
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, _LiveJob] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="live-web",
        )

    @classmethod
    def from_environment(cls) -> "LiveJobRegistry":
        max_workers = _bounded_int("NPC_WEB_LIVE_MAX_WORKERS", 2, 1, 4)
        max_in_flight = _bounded_int("NPC_WEB_LIVE_MAX_IN_FLIGHT", 2, 1, 8)
        if max_in_flight < max_workers:
            raise ValueError("NPC_WEB_LIVE_MAX_IN_FLIGHT must cover max workers")
        return cls(
            max_workers=max_workers,
            max_in_flight=max_in_flight,
            timeout_seconds=_bounded_float("NPC_WEB_LIVE_JOB_TIMEOUT_SECONDS", 90.0, 1.0, 300.0),
            ttl_seconds=_bounded_float("NPC_WEB_LIVE_JOB_TTL_SECONDS", 900.0, 1.0, 86400.0),
            poll_after_ms=_bounded_int("NPC_WEB_LIVE_POLL_AFTER_MS", 1500, 250, 10000),
        )

    def submit(
        self,
        *,
        kind: LiveJobKind,
        provider: str,
        model: str,
        work: Callable[[], Any],
    ) -> LiveJobSnapshot:
        with self._lock:
            self._cleanup_locked()
            in_flight = sum(item.status in {"PENDING", "RUNNING"} for item in self._jobs.values())
            if in_flight >= self.max_in_flight:
                raise WebApplicationError(
                    "LIVE_EXECUTION_BUSY",
                    "Another live execution is already using the available Web capacity.",
                    status_code=429,
                    stage="live_execution",
                    retryable=True,
                )
            job = _LiveJob(
                job_id=uuid.uuid4().hex,
                kind=kind,
                provider=provider,
                model=model,
                created_at=self._clock(),
            )
            self._jobs[job.job_id] = job
            self._executor.submit(self._execute, job.job_id, work)
            timer = threading.Timer(
                self.timeout_seconds,
                self._mark_timeout,
                args=(job.job_id,),
            )
            timer.daemon = True
            job.timer = timer
            timer.start()
            return self._snapshot_locked(job)

    def get(self, job_id: str) -> LiveJobSnapshot:
        with self._lock:
            self._cleanup_locked()
            job = self._jobs.get(job_id)
            if job is None:
                raise WebApplicationError(
                    "LIVE_JOB_NOT_FOUND",
                    "The live execution job was not found or has expired.",
                    status_code=404,
                    stage="live_execution",
                    retryable=False,
                )
            return self._snapshot_locked(job)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, job_id: str, work: Callable[[], Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "PENDING":
                return
            job.status = "RUNNING"
            job.started_at = self._clock()
        try:
            result = work()
        except WebApplicationError as error:
            self._finish(job_id, error=error)
        except Exception:
            self._finish(
                job_id,
                error=WebApplicationError(
                    "LIVE_EXECUTION_FAILED",
                    "The live execution could not complete safely.",
                    status_code=503,
                    stage="live_execution",
                    retryable=True,
                ),
            )
        else:
            self._finish(job_id, result=result)

    def _finish(
        self,
        job_id: str,
        *,
        result: Any = None,
        error: WebApplicationError | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "RUNNING":
                return
            job.status = "FAILED" if error is not None else "SUCCEEDED"
            job.result = result
            job.error = error
            job.finished_at = self._clock()
            if job.timer is not None:
                job.timer.cancel()

    def _mark_timeout(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"SUCCEEDED", "FAILED"}:
                return
            job.status = "FAILED"
            job.error = WebApplicationError(
                "BACKEND_REQUEST_TIMEOUT",
                "The live execution exceeded its bounded Web execution budget.",
                status_code=504,
                stage="live_execution",
                retryable=True,
                details={"timeout_seconds": self.timeout_seconds},
            )
            job.finished_at = self._clock()

    def _cleanup_locked(self) -> None:
        now = self._clock()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"SUCCEEDED", "FAILED"}
            and job.finished_at is not None
            and now - job.finished_at >= self.ttl_seconds
        ]
        for job_id in expired:
            job = self._jobs.pop(job_id)
            if job.timer is not None:
                job.timer.cancel()

    def _snapshot_locked(self, job: _LiveJob) -> LiveJobSnapshot:
        now = self._clock()
        elapsed_start = job.started_at or job.created_at
        elapsed_end = job.finished_at or now
        return LiveJobSnapshot(
            job_id=job.job_id,
            kind=job.kind,
            status=job.status,
            provider=job.provider,
            model=job.model,
            poll_after_ms=self.poll_after_ms,
            elapsed_ms=max(0.0, (elapsed_end - elapsed_start) * 1000),
            result=job.result,
            error=job.error,
        )


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside its bounded range")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside its bounded range")
    return value


__all__ = ["LiveJobKind", "LiveJobRegistry", "LiveJobSnapshot", "LiveJobStatus"]
