from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from .errors import DuplicateReferenceError
from .models import (
    CharacterReference,
    CorpusValidationReport,
    GameCatalog,
    ValidationIssue,
)
from .provenance import validate_provenance


def _issue(
    severity: str,
    code: str,
    message: str,
    reference_id: str | None = None,
    field_path: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        reference_id=reference_id,
        field_path=field_path,
    )


def _sort_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return sorted(
        issues,
        key=lambda item: (
            item.severity,
            item.reference_id or "",
            item.field_path or "",
            item.code,
            item.message,
        ),
    )


def validate_character_reference(
    reference: CharacterReference,
    catalog: GameCatalog | None = None,
) -> CorpusValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    reference_id = reference.reference_id
    if catalog is not None and reference.facts.identity.game_id not in catalog.games:
        errors.append(
            _issue(
                "error",
                "unknown_game",
                f"unknown game_id: {reference.facts.identity.game_id}",
                reference_id,
                "identity.game_id",
            )
        )
    try:
        validate_provenance(reference.provenance, reference.facts)
    except Exception as exc:
        errors.append(_issue("error", "provenance_invalid", str(exc), reference_id))
    if reference.analysis is None:
        warnings.append(
            _issue(
                "warning",
                "analysis_missing",
                "analysis.yaml is optional and was not supplied",
                reference_id,
            )
        )
    if reference.quality.verification_status.value == "conflicted":
        warnings.append(
            _issue(
                "warning",
                "verification_conflicted",
                "reference contains source conflicts",
                reference_id,
            )
        )
    return CorpusValidationReport(
        valid=not errors,
        errors=_sort_issues(errors),
        warnings=_sort_issues(warnings),
    )


def validate_corpus(
    references: Iterable[CharacterReference],
    catalog: GameCatalog | None = None,
) -> CorpusValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    ordered = sorted(list(references), key=lambda item: item.reference_id)
    seen: set[str] = set()
    for reference in ordered:
        if reference.reference_id in seen:
            errors.append(
                _issue(
                    "error",
                    "duplicate_reference_id",
                    f"duplicate reference_id: {reference.reference_id}",
                    reference.reference_id,
                )
            )
        seen.add(reference.reference_id)
        report = validate_character_reference(reference, catalog)
        errors.extend(report.errors)
        warnings.extend(report.warnings)
    errors = _sort_issues(errors)
    warnings = _sort_issues(warnings)
    return CorpusValidationReport(valid=not errors, errors=errors, warnings=warnings)
