"""Stable, serializable value objects for character evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


EVALUATION_SCHEMA_VERSION = "evaluation/v0.6.1-A"


class EvaluationOutcome(str, Enum):
    """Outcome of the deterministic evaluation pass."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
    NOT_COMPLETED = "not_completed"


@dataclass(frozen=True)
class EvaluationFinding:
    """One deterministic observation emitted by an evaluation validator."""

    validator_id: str
    code: str
    severity: str
    blocking: bool
    stage: str
    field_path: str | None
    message: str

    def __post_init__(self) -> None:
        for name in ("validator_id", "code", "severity", "stage", "message"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.field_path is not None and not isinstance(self.field_path, str):
            raise TypeError("field_path must be a string or None")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_id": self.validator_id,
            "code": self.code,
            "severity": self.severity,
            "blocking": self.blocking,
            "stage": self.stage,
            "field_path": self.field_path,
            "message": self.message,
        }


def _finding_sort_key(finding: EvaluationFinding) -> tuple[object, ...]:
    return (
        finding.validator_id,
        finding.code,
        finding.severity,
        finding.stage,
        finding.field_path or "",
        finding.message,
        finding.blocking,
    )


@dataclass(frozen=True)
class EvaluationResult:
    """Complete result of one deterministic evaluation run."""

    schema_version: str
    evaluation_id: str
    request_id: str
    outcome: EvaluationOutcome
    blocking: bool
    dimensions: tuple[str, ...]
    findings: tuple[EvaluationFinding, ...]

    def __post_init__(self) -> None:
        for name in ("schema_version", "evaluation_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking must be a bool")

        dimensions = tuple(self.dimensions)
        if not all(isinstance(item, str) and item.strip() for item in dimensions):
            raise ValueError("dimensions must contain non-empty strings")
        object.__setattr__(self, "dimensions", tuple(sorted(set(dimensions))))

        findings = tuple(self.findings)
        if not all(isinstance(item, EvaluationFinding) for item in findings):
            raise TypeError("findings must contain EvaluationFinding values")
        object.__setattr__(self, "findings", tuple(sorted(findings, key=_finding_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "request_id": self.request_id,
            "outcome": self.outcome.value,
            "blocking": self.blocking,
            "dimensions": list(self.dimensions),
            "findings": [finding.to_dict() for finding in self.findings],
        }


__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "EvaluationFinding",
    "EvaluationOutcome",
    "EvaluationResult",
]
