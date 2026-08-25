"""Fail-closed latency audit for the official Live Character Authoring flow.

This module is intentionally an integration seam around the existing
provider-neutral model boundary.  It records only bounded metadata while the
official generation, tool, checker, and repair implementations remain the
source of ordering and behavior.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents import (  # noqa: E402
    AgentExecutionError,
    AgentToolError,
    CanonChecker,
    CanonCheckStatus,
    CharacterDesignRequest,
    CharacterGenerationAgent,
    CharacterRepairAgent,
    ModelAuthenticationError,
    ModelCapabilityError,
    ModelError,
    ModelInvocationAudit,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    character_model_from_environment,
)
from agents.character_repair import CharacterAuthoringResult  # noqa: E402
from agents.models import AgentPrompt, ModelTurn  # noqa: E402
from agents.official_character_authoring import ReferenceGrounding  # noqa: E402

SCHEMA_VERSION = "character-authoring-live-latency-audit/v0"
_RETRIEVAL_STRATEGIES = frozenset({"model_loop", "deterministic"})
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SECRET_MARKERS = (
    "api_key",
    "api-key",
    "apikey",
    "secret",
    "token",
    "password",
    "cookie",
    "private",
    "bearer",
    "sk-",
)
_SAFE_OUTCOMES = frozenset(
    {
        "success",
        "timeout",
        "provider",
        "rate_limit",
        "authentication",
        "malformed_response",
        "capability",
        "failed",
        "unknown",
    }
)
_SAFE_RESPONSE_CONTRACTS = frozenset({"text", "json_object", "json_schema"})
_SAFE_TOOL_NAMES = frozenset(
    {
        "search_lore",
        "get_lore",
        "search_factions",
        "get_faction",
        "search_characters",
        "get_character",
        "get_world_rules",
        "search_story_context",
        "get_story_context",
    }
)


def _safe_retrieval_strategy(value: Any) -> str | None:
    if isinstance(value, str) and value in _RETRIEVAL_STRATEGIES:
        return value
    return None


def _safe_label(value: Any) -> str | None:
    """Keep only existing metadata-shaped labels, never arbitrary text."""

    if value is None:
        return None
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        return "redacted"
    normalized = raw.strip().lower()
    if (
        not normalized
        or not _SAFE_LABEL.fullmatch(normalized)
        or any(marker in normalized for marker in _SECRET_MARKERS)
    ):
        return "redacted"
    return normalized


def _safe_outcome(value: Any, *, fallback: str = "unknown") -> str:
    normalized = _safe_label(value)
    return normalized if normalized in _SAFE_OUTCOMES else fallback


def _safe_response_contract(value: Any) -> str | None:
    normalized = _safe_label(value)
    return normalized if normalized in _SAFE_RESPONSE_CONTRACTS else None


def _safe_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_provider_status_code(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        return None
    return value


def _safe_provider_retryable(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _safe_nonnegative_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0:
        return None
    return round(result, 3)


def _elapsed_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    if not math.isfinite(start) or not math.isfinite(end):
        return None
    return round(max(0.0, (end - start) * 1000.0), 3)


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Enum):
        return value.value
    return None


def _serialized_metrics(value: Any) -> tuple[int, int] | None:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
    except (TypeError, ValueError, OverflowError):
        return None
    return len(serialized), len(serialized.encode("utf-8"))


def _serialized_length(value: Any) -> int | None:
    metrics = _serialized_metrics(value)
    return metrics[0] if metrics is not None else None


def _prompt_shape(prompt: AgentPrompt) -> dict[str, Any]:
    """Return count-only prompt-shape metrics.

    ``utf8_bytes_div_4_estimated_tokens`` is a deterministic sizing heuristic,
    not provider-reported usage.  No prompt component is returned.
    """

    messages = getattr(prompt, "messages", ())
    message_characters = 0
    message_utf8_bytes = 0
    message_count = 0
    for message in messages if isinstance(messages, Sequence) else ():
        message_count += 1
        metrics = _serialized_metrics(getattr(message, "content", None))
        if metrics is not None:
            message_characters += metrics[0]
            message_utf8_bytes += metrics[1]
    evidence = getattr(prompt, "evidence", ())
    payload = getattr(prompt, "authoring_payload", None)
    available_tools = getattr(prompt, "available_tools", ()) or ()
    system_metrics = _serialized_metrics(getattr(prompt, "system_contract", None))
    runtime_metrics = _serialized_metrics(getattr(prompt, "runtime", None))
    history_metrics = _serialized_metrics(messages)
    evidence_metrics = _serialized_metrics(evidence)
    tool_metrics = _serialized_metrics(available_tools)
    payload_metrics = _serialized_metrics(payload) if payload is not None else (0, 0)
    components = (
        system_metrics,
        runtime_metrics,
        history_metrics,
        evidence_metrics,
        tool_metrics,
        payload_metrics,
    )
    aggregate_characters = sum(item[0] for item in components if item is not None)
    aggregate_utf8_bytes = sum(item[1] for item in components if item is not None)
    return {
        "system_contract_characters": system_metrics[0] if system_metrics else 0,
        "system_contract_utf8_bytes": system_metrics[1] if system_metrics else 0,
        "runtime_characters": runtime_metrics[0] if runtime_metrics else 0,
        "runtime_utf8_bytes": runtime_metrics[1] if runtime_metrics else 0,
        "message_count": message_count,
        "message_characters": message_characters,
        "message_utf8_bytes": message_utf8_bytes,
        "history_messages_characters": history_metrics[0] if history_metrics else 0,
        "history_messages_utf8_bytes": history_metrics[1] if history_metrics else 0,
        "available_tool_count": len(available_tools),
        "available_tools_characters": tool_metrics[0] if tool_metrics else 0,
        "available_tools_utf8_bytes": tool_metrics[1] if tool_metrics else 0,
        "evidence_count": len(evidence or ()),
        "source_count": len(evidence or ()),
        "evidence_characters": evidence_metrics[0] if evidence_metrics else 0,
        "evidence_utf8_bytes": evidence_metrics[1] if evidence_metrics else 0,
        "authoring_payload_present": payload is not None,
        "authoring_payload_characters": payload_metrics[0],
        "authoring_payload_utf8_bytes": payload_metrics[1],
        "aggregate_serialized_characters": aggregate_characters,
        "aggregate_serialized_utf8_bytes": aggregate_utf8_bytes,
        "utf8_bytes_div_4_estimated_tokens": round(aggregate_utf8_bytes / 4.0, 3),
    }


def classify_invocation(prompt: AgentPrompt) -> str:
    """Classify using only the existing prompt context and response contract."""

    purpose = getattr(prompt, "invocation_purpose", "")
    response_format = getattr(prompt, "response_format", "")
    character = getattr(prompt, "character", None)
    principal = getattr(character, "principal", None)
    session_id = getattr(prompt, "session_id", "")

    if purpose == "character_draft_recovery":
        return "contract_recovery"
    if principal == "character_repair" or (
        isinstance(session_id, str) and session_id.startswith("character_repair:")
    ):
        return "repair"
    if response_format == "character_authoring_action" and principal == "character_authoring":
        return "retrieval_action"
    if (
        response_format == "character_draft"
        and principal == "character_authoring"
        and isinstance(session_id, str)
        and session_id.startswith("character_generation:")
    ):
        return "finalization"
    raise ValueError("unsupported authoring invocation context")


def _failure_category(error: BaseException) -> str:
    if isinstance(error, ModelAuthenticationError):
        return "authentication_failure"
    if isinstance(error, ModelTimeoutError):
        return "timeout_failure"
    if isinstance(error, ModelRateLimitError):
        return "rate_limit_failure"
    if isinstance(error, ModelProviderError):
        return "provider_failure"
    if isinstance(error, ModelCapabilityError):
        return "capability_failure"
    if isinstance(error, ModelMalformedResponseError):
        return "malformed_response"
    if isinstance(error, AgentToolError):
        return "tool_failure"
    if isinstance(error, AgentExecutionError):
        return "agent_failure"
    if isinstance(error, ModelError):
        return "model_failure"
    if isinstance(error, OSError):
        return "input_or_reference_failure"
    return "orchestration_failure"


def _status_value(value: Any, *, fallback: str = "unknown") -> str:
    normalized = _safe_label(value)
    return normalized or fallback


def _audit_usage(audit: ModelInvocationAudit | None) -> dict[str, int] | None:
    usage = getattr(audit, "usage", None)
    if usage is None:
        return None
    result: dict[str, int] = {}
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        value = _safe_nonnegative_int(getattr(usage, name, None))
        if value is not None:
            result[name] = value
    return result or None


class _AuditState:
    def __init__(self, clock: Callable[[], float], retrieval_strategy: str | None) -> None:
        self.clock = clock
        self.retrieval_strategy = retrieval_strategy
        self.pipeline_start = self._now()
        self.pipeline_end: float | None = None
        self.reference_start: float | None = None
        self.reference_end: float | None = None
        self.reference_selected_count: int | None = None
        self.reference_total_count: int | None = None
        self.generation_start: float | None = None
        self.generation_end: float | None = None
        self.repair_start: float | None = None
        self.repair_end: float | None = None
        self.invocations: list[dict[str, Any]] = []
        self._invocation_timeline: list[tuple[str, float, float]] = []
        self.tools: list[dict[str, Any]] = []
        self._tool_timeline: list[tuple[int, float, float]] = []
        self.checks: dict[str, dict[str, Any]] = {
            "initial": {"executed": False, "elapsed_ms": None, "status": "not_run"},
            "final": {"executed": False, "elapsed_ms": None, "status": "not_run"},
        }

    def _now(self) -> float:
        value = float(self.clock())
        if not math.isfinite(value):
            raise ValueError("clock returned a non-finite value")
        return value

    def start_generation(self) -> float:
        self.generation_start = self._now()
        return self.generation_start

    def end_generation(self) -> float:
        self.generation_end = self._now()
        return self.generation_end

    def start_repair(self) -> float:
        if self.repair_start is None:
            self.repair_start = self._now()
        return self.repair_start

    def end_repair(self) -> float:
        self.repair_end = self._now()
        return self.repair_end

    def record_reference(self, grounding: ReferenceGrounding) -> None:
        self.reference_selected_count = len(getattr(grounding, "selected", ()) or ())
        total = getattr(grounding, "total_records", None)
        self.reference_total_count = _safe_nonnegative_int(total)

    def record_invocation(
        self,
        prompt: AgentPrompt,
        classification: str,
        start: float,
        end: float,
        audit: ModelInvocationAudit | None,
        *,
        failed: bool = False,
    ) -> None:
        provider_latency = _safe_nonnegative_float(getattr(audit, "latency_ms", None))
        retry_count = _safe_nonnegative_int(getattr(audit, "retry_count", None))
        network_attempts = 1 + retry_count if retry_count is not None else None
        event = {
            "sequence": len(self.invocations) + 1,
            "classification": classification,
            "turn": _safe_nonnegative_int(getattr(prompt, "turn_number", None)),
            "outcome": _safe_outcome(
                getattr(audit, "outcome", None),
                fallback="failed" if failed else "unknown",
            ),
            "provider_status_code": _safe_provider_status_code(
                getattr(audit, "provider_status_code", None)
            ),
            "provider_retryable": _safe_provider_retryable(
                getattr(audit, "provider_retryable", None)
            ),
            "provider": _safe_label(getattr(audit, "provider", None)),
            "model": _safe_label(getattr(audit, "model", None)),
            "transport": _safe_label(getattr(audit, "transport", None)),
            "response_contract": _safe_response_contract(
                getattr(audit, "response_contract", None)
            ),
            "elapsed_ms": _elapsed_ms(start, end),
            "wall_elapsed_ms": _elapsed_ms(start, end),
            "provider_latency_ms": provider_latency,
            "retry_count": retry_count,
            "network_attempts": network_attempts,
            "usage": _audit_usage(audit),
            "shape": _prompt_shape(prompt),
        }
        self.invocations.append(event)
        self._invocation_timeline.append((classification, start, end))

    def record_tool(
        self,
        tool_name: Any,
        round_number: Any,
        start: float,
        end: float,
        status: str,
        source_count: int,
    ) -> None:
        safe_name = (
            tool_name
            if isinstance(tool_name, str) and tool_name in _SAFE_TOOL_NAMES
            else "unknown_tool"
        )
        safe_round = _safe_nonnegative_int(round_number)
        safe_sources = _safe_nonnegative_int(source_count) or 0
        self.tools.append(
            {
                "tool_name": safe_name,
                "round": safe_round,
                "elapsed_ms": _elapsed_ms(start, end),
                "status": status if status in {"allowed", "rejected", "failed"} else "failed",
                "source_count": safe_sources,
            }
        )
        self._tool_timeline.append((safe_round or 0, start, end))

    def record_check(
        self,
        label: str,
        start: float,
        end: float,
        status: str,
    ) -> None:
        if label not in self.checks:
            return
        self.checks[label] = {
            "executed": True,
            "elapsed_ms": _elapsed_ms(start, end),
            "status": status,
        }

    def finish(self) -> None:
        self.pipeline_end = self._now()

    def _stage_elapsed(
        self,
        classification: str,
        *,
        end: float | None,
        subtract: tuple[float, float] | None = None,
    ) -> float | None:
        spans = [
            (start, finish)
            for item_class, start, finish in self._invocation_timeline
            if item_class == classification
        ]
        if not spans:
            return None
        start = spans[0][0]
        finish = end if end is not None else spans[-1][1]
        total = _elapsed_ms(start, finish)
        if total is None or subtract is None:
            return total
        excluded = _elapsed_ms(subtract[0], subtract[1]) or 0.0
        return round(max(0.0, total - excluded), 3)

    def build(
        self,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        failure: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        pipeline_total = _elapsed_ms(self.pipeline_start, self.pipeline_end)
        provider_values = [
            item["provider_latency_ms"]
            for item in self.invocations
            if item["provider_latency_ms"] is not None
        ]
        provider_latency = round(sum(provider_values), 3)
        attempts = [
            item["network_attempts"]
            for item in self.invocations
            if item["network_attempts"] is not None
        ]
        network_attempts = sum(attempts) if len(attempts) == len(self.invocations) else None
        finalization_spans = [
            (start, end)
            for classification, start, end in self._invocation_timeline
            if classification == "finalization"
        ]
        recovery_spans = [
            (start, end)
            for classification, start, end in self._invocation_timeline
            if classification == "contract_recovery"
        ]
        recovery_span = (
            (recovery_spans[0][0], recovery_spans[-1][1]) if recovery_spans else None
        )
        action_spans = [
            (start, end)
            for classification, start, end in self._invocation_timeline
            if classification == "retrieval_action"
        ]
        finalization_start = finalization_spans[0][0] if finalization_spans else None
        action_end = finalization_start or self.generation_end
        action_elapsed = (
            _elapsed_ms(action_spans[0][0], action_end)
            if action_spans and action_end is not None
            else None
        )
        finalization_elapsed = (
            self._stage_elapsed(
                "finalization",
                end=self.generation_end,
                subtract=recovery_span,
            )
            if finalization_spans
            else None
        )
        recovery_elapsed = (
            _elapsed_ms(recovery_span[0], recovery_span[1]) if recovery_span else None
        )
        provider_latency_known = len(provider_values) == len(self.invocations)
        local_remainder = (
            round(max(0.0, (pipeline_total or 0.0) - provider_latency), 3)
            if provider_latency_known
            else None
        )
        selected = self.reference_selected_count
        tool_rounds = len({round_number for round_number, _, _ in self._tool_timeline})
        classification_counts = {
            name: sum(1 for item in self.invocations if item["classification"] == name)
            for name in (
                "retrieval_action",
                "finalization",
                "contract_recovery",
                "repair",
            )
        }
        repair_status = "not_run"
        repair_executed = self.repair_start is not None
        if repair_executed:
            repair_status = "executed"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "retrieval_strategy": self.retrieval_strategy,
            "failure": failure,
            "pipeline": {
                "total_ms": pipeline_total,
                "provider_latency_ms": provider_latency if provider_latency_known else None,
                "known_provider_latency_ms": provider_latency,
                "provider_latency_known": provider_latency_known,
                "local_orchestration_remainder_ms": local_remainder,
            },
            "timing_definition": {
                "provider_latency_ms": (
                    "Sum of ModelInvocationAudit.latency_ms; the live adapter latency "
                    "includes provider retries and backoff."
                ),
                "network_attempts": (
                    "Each logical model call reports 1 + retry_count when the existing "
                    "invocation metadata supplies retry_count."
                ),
                "local_orchestration_remainder_ms": (
                    "null when provider latency metadata is incomplete; otherwise "
                    "max(0, pipeline.total_ms - provider_latency_ms), covering reference "
                    "selection, prompt/orchestration work, deterministic tools and checks, "
                    "repair orchestration, and local timing overhead."
                ),
                "generation_action_loop_ms": (
                    "Wall time from the first retrieval/action invocation to the start of "
                    "finalization, including action calls and deterministic tool execution."
                ),
                "finalization_ms": (
                    "Wall time from finalization invocation start through generation "
                    "completion, excluding the contract-recovery invocation span."
                ),
                "utf8_bytes_div_4_estimated_tokens": (
                    "Deterministic count-only prompt-size heuristic; this is not "
                    "provider-reported token usage."
                ),
            },
            "stages": {
                "reference_selection": {
                    "elapsed_ms": _elapsed_ms(self.reference_start, self.reference_end),
                    "selected_count": selected,
                    "total_reference_count": self.reference_total_count,
                },
                "generation_action_loop": {
                    "elapsed_ms": action_elapsed,
                    "invocation_count": len(action_spans),
                    "tool_event_count": len(self.tools),
                    "tool_round_count": tool_rounds,
                },
                "finalization": {
                    "elapsed_ms": finalization_elapsed,
                    "invocation_count": len(finalization_spans),
                },
                "contract_recovery": {
                    "elapsed_ms": recovery_elapsed,
                    "invocation_count": len(recovery_spans),
                },
                "canon_checker": self.checks,
                "repair": {
                    "executed": repair_executed,
                    "elapsed_ms": _elapsed_ms(self.repair_start, self.repair_end),
                    "invocation_count": classification_counts["repair"],
                    "status": repair_status,
                },
            },
            "counts": {
                "logical_llm_calls": len(self.invocations),
                "network_attempts": network_attempts,
                "tool_events": len(self.tools),
                "tool_rounds": tool_rounds,
                "selected_references": selected,
                **{f"{name}_calls": count for name, count in classification_counts.items()},
            },
            "invocations": self.invocations,
            "tools": self.tools,
            "result": result,
        }


def _error_audit(error: BaseException) -> ModelInvocationAudit | None:
    candidate = getattr(error, "audit", None)
    return candidate if isinstance(candidate, ModelInvocationAudit) else None


class _InstrumentedModel:
    def __init__(self, delegate: Any, state: _AuditState) -> None:
        self.delegate = delegate
        self.state = state

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        classification = classify_invocation(prompt)
        start = self.state._now()
        try:
            turn = self.delegate.generate(prompt)
        except BaseException as error:
            end = self.state._now()
            self.state.record_invocation(
                prompt,
                classification,
                start,
                end,
                _error_audit(error),
                failed=True,
            )
            raise
        end = self.state._now()
        self.state.record_invocation(
            prompt,
            classification,
            start,
            end,
            getattr(turn, "invocation", None),
        )
        return turn


class _InstrumentedToolbox:
    def __init__(self, delegate: Any, state: _AuditState) -> None:
        self.delegate = delegate
        self.state = state
        self.tool_definitions = delegate.tool_definitions
        self.allowed_tools = delegate.allowed_tools

    def execute(self, **kwargs: Any) -> Any:
        tool_name = kwargs.get("tool_name")
        round_number = kwargs.get("round_number")
        start = self.state._now()
        try:
            execution = self.delegate.execute(**kwargs)
        except BaseException as error:
            end = self.state._now()
            self.state.record_tool(
                tool_name,
                round_number,
                start,
                end,
                "rejected" if isinstance(error, AgentToolError) else "failed",
                0,
            )
            raise
        end = self.state._now()
        sources = getattr(execution, "allowed_source_ids", ())
        self.state.record_tool(
            tool_name,
            round_number,
            start,
            end,
            "allowed",
            len(sources) if isinstance(sources, (set, frozenset, tuple, list)) else 0,
        )
        return execution


class _InstrumentedGenerationAgent:
    def __init__(self, delegate: Any, state: _AuditState) -> None:
        self.delegate = delegate
        self.state = state

    def generate(self, request: CharacterDesignRequest) -> Any:
        self.state.start_generation()
        try:
            return self.delegate.generate(request)
        finally:
            self.state.end_generation()


class _InstrumentedRepairAgent:
    def __init__(self, delegate: CharacterRepairAgent, state: _AuditState) -> None:
        self.delegate = delegate
        self.state = state

    def prepare_request(self, *args: Any, **kwargs: Any) -> Any:
        self.state.start_repair()
        try:
            return self.delegate.prepare_request(*args, **kwargs)
        except BaseException:
            self.state.end_repair()
            raise

    def repair(self, *args: Any, **kwargs: Any) -> Any:
        self.state.start_repair()
        try:
            return self.delegate.repair(*args, **kwargs)
        finally:
            self.state.end_repair()


class _InstrumentedChecker:
    def __init__(self, delegate: CanonChecker, state: _AuditState) -> None:
        self.delegate = delegate
        self.state = state
        self._check_count = 0

    def check(self, *args: Any, **kwargs: Any) -> Any:
        label = "initial" if self._check_count == 0 else "final"
        self._check_count += 1
        start = self.state._now()
        try:
            report = self.delegate.check(*args, **kwargs)
        except BaseException:
            end = self.state._now()
            self.state.record_check(label, start, end, "failed")
            raise
        end = self.state._now()
        self.state.record_check(label, start, end, _status_value(report.status.value))
        return report

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def _result_summary(authoring: CharacterAuthoringResult) -> dict[str, Any]:
    repair = authoring.repair_result
    return {
        "initial_canon_status": _status_value(authoring.initial_check.status.value),
        "final_canon_status": _status_value(authoring.final_check.status.value),
        "final_status": _status_value(authoring.final_status.value),
        "repair_attempted": bool(repair.repair_attempted),
        "repair_succeeded": bool(repair.repair_succeeded),
        "repair_status": _status_value(repair.status.value),
    }


def audit_live_character_authoring(
    request: CharacterDesignRequest,
    *,
    model: Any | None = None,
    reference_grounding: ReferenceGrounding | None = None,
    reference_loader: Callable[[str], ReferenceGrounding] | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
    retrieval_strategy: str = "model_loop",
) -> dict[str, Any]:
    """Run the official pipeline and return a sanitized JSON-compatible audit."""

    state = _AuditState(clock, _safe_retrieval_strategy(retrieval_strategy))
    try:
        if state.retrieval_strategy is None:
            raise ValueError("retrieval_strategy must be 'model_loop' or 'deterministic'")
        if not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be CharacterDesignRequest")

        if reference_grounding is None:
            state.reference_start = state._now()
            loader = reference_loader or _load_reference_grounding
            grounding = loader(request.brief)
            state.reference_end = state._now()
        else:
            grounding = reference_grounding
            state.reference_start = state._now()
            state.reference_end = state.reference_start
        state.record_reference(grounding)

        live_model = model
        if live_model is None:
            environment = dict(os.environ)
            if provider is not None:
                environment["NPC_LLM_PROVIDER"] = provider
            if model_name is not None:
                environment["NPC_LLM_MODEL"] = model_name
            live_model = character_model_from_environment(
                environment=environment,
                mode_override="live",
            )

        instrumented_model = _InstrumentedModel(live_model, state)
        generation_agent = CharacterGenerationAgent(
            instrumented_model,
            reference_context=grounding.selected,
            retrieval_strategy=state.retrieval_strategy,
        )
        generation_agent.tools = _InstrumentedToolbox(generation_agent.tools, state)

        checker = _InstrumentedChecker(CanonChecker(), state)
        repair_agent = CharacterRepairAgent(instrumented_model, checker=checker)
        instrumented_repair = _InstrumentedRepairAgent(repair_agent, state)
        instrumented_generation = _InstrumentedGenerationAgent(generation_agent, state)

        workflow = _AuthoringWorkflowAdapter(
            instrumented_generation,
            instrumented_repair,
            checker,
        )
        authoring = workflow.run(request)
        result = _result_summary(authoring)
        state.finish()
        if result["final_status"] != CanonCheckStatus.PASS.value:
            return state.build(
                status="failed",
                result=result,
                failure={"category": "canon_check_failed"},
            )
        return state.build(status="passed", result=result)
    except BaseException as error:
        try:
            state.finish()
        except BaseException:
            state.pipeline_end = state.pipeline_start
        return state.build(
            status="failed",
            failure={"category": _failure_category(error)},
        )


class _AuthoringWorkflowAdapter:
    """Keep the official CharacterAuthoringWorkflow ordering in one call."""

    def __init__(self, generation: Any, repair: Any, checker: Any) -> None:
        from agents.character_repair import CharacterAuthoringWorkflow

        self._workflow = CharacterAuthoringWorkflow(
            generation,
            repair,
            checker=checker,
        )

    def run(self, request: CharacterDesignRequest) -> CharacterAuthoringResult:
        return self._workflow.run(request)


def _load_reference_grounding(brief: str) -> ReferenceGrounding:
    from agents.official_character_authoring import load_reference_grounding

    return load_reference_grounding(brief)


def _failure_json(category: str, *, retrieval_strategy: Any = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "retrieval_strategy": _safe_retrieval_strategy(retrieval_strategy),
        "failure": {"category": category},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Live Character Authoring latency; emits sanitized JSON."
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--brief")
    inputs.add_argument("--brief-file")
    parser.add_argument("--provider")
    parser.add_argument("--model-name")
    parser.add_argument(
        "--retrieval-strategy",
        choices=tuple(sorted(_RETRIEVAL_STRATEGIES)),
        default="model_loop",
    )
    args = parser.parse_args(argv)

    try:
        if args.brief is None and args.brief_file is None:
            raise ValueError("one brief input is required")
        brief = args.brief
        if brief is None:
            brief = Path(args.brief_file).read_text(encoding="utf-8")
        if not brief or not brief.strip():
            raise ValueError("brief must not be empty")
        request = CharacterDesignRequest(brief, request_id="live_latency_audit_001")
        report = audit_live_character_authoring(
            request,
            provider=args.provider,
            model_name=args.model_name,
            retrieval_strategy=args.retrieval_strategy,
        )
    except BaseException:
        report = _failure_json(
            "input_orchestration_failure",
            retrieval_strategy=args.retrieval_strategy,
        )

    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "audit_live_character_authoring",
    "classify_invocation",
    "main",
]
