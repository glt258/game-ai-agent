"""Deterministic evaluation runner and placeholder validator interface."""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .context import EvaluationContext, EvaluationSubject
from .models import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationFinding,
    EvaluationOutcome,
    EvaluationResult,
)
from .validators import (
    IdentityCoherenceValidator,
    RepresentationCompletenessValidator,
    RequestAlignmentValidator,
)


class EvaluationValidator(Protocol):
    """Placeholder interface for future deterministic validators."""

    validator_id: str

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        """Return findings for ``context`` without mutating it."""


class EvaluationRunner:
    """Run a fixed validator collection and produce one stable report."""

    def __init__(self, validators: Sequence[EvaluationValidator] | None = None) -> None:
        configured = (
            (
                RequestAlignmentValidator(),
                IdentityCoherenceValidator(),
                RepresentationCompletenessValidator(),
            )
            if validators is None
            else tuple(validators)
        )
        self.validators = configured
        for validator in self.validators:
            validator_id = getattr(validator, "validator_id", None)
            if not isinstance(validator_id, str) or not validator_id.strip():
                raise ValueError("each evaluation validator needs a non-empty validator_id")

    def run(
        self,
        subject: EvaluationSubject,
        *,
        evaluation_id: str | None = None,
    ) -> EvaluationResult:
        if not isinstance(subject, EvaluationSubject):
            raise TypeError("subject must be an EvaluationSubject")

        context = EvaluationContext.from_subject(subject)
        findings: list[EvaluationFinding] = []
        dimensions: set[str] = set()
        for validator in self.validators:
            produced = validator.validate(context)
            if produced is None:
                raise TypeError(
                    f"evaluation validator {validator.validator_id!r} returned None"
                )
            produced_findings: list[EvaluationFinding] = []
            for finding in produced:
                if not isinstance(finding, EvaluationFinding):
                    raise TypeError(
                        f"evaluation validator {validator.validator_id!r} returned "
                        "a non-EvaluationFinding value"
                    )
                findings.append(finding)
                produced_findings.append(finding)
            if produced_findings and getattr(validator, "dimension", None) is not None:
                dimension = getattr(validator, "dimension")
                if not isinstance(dimension, str) or not dimension.strip():
                    raise ValueError("validator dimension must be a non-empty string or None")
                dimensions.add(dimension)

        if any(finding.blocking or finding.severity.casefold() == "error" for finding in findings):
            outcome = EvaluationOutcome.FAIL
        elif any(finding.severity.casefold() == "warning" for finding in findings):
            outcome = EvaluationOutcome.WARN
        else:
            outcome = EvaluationOutcome.PASS

        stable_id = evaluation_id or f"evaluation:{subject.request.request_id}"
        return EvaluationResult(
            schema_version=EVALUATION_SCHEMA_VERSION,
            evaluation_id=stable_id,
            request_id=subject.request.request_id,
            outcome=outcome,
            blocking=any(finding.blocking for finding in findings),
            dimensions=tuple(dimensions),
            findings=tuple(findings),
        )

    def evaluate(
        self,
        subject: EvaluationSubject,
        *,
        evaluation_id: str | None = None,
    ) -> EvaluationResult:
        """Alias for callers that prefer the domain verb over ``run``."""

        return self.run(subject, evaluation_id=evaluation_id)


__all__ = ["EvaluationRunner", "EvaluationValidator"]
