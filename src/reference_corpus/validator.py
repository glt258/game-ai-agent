from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from .errors import DuplicateReferenceError
from .models import (
    CharacterReference,
    CorpusValidationReport,
    GameCatalog,
    RELATION_TYPE_RE,
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


def _mechanic_integrity_issues(reference: CharacterReference) -> list[ValidationIssue]:
    """Return explicit report issues for graph mutations after model construction."""
    facts = reference.facts.combat
    issues: list[ValidationIssue] = []

    def duplicate_ids(items, attribute: str, code: str, path: str) -> None:
        ids = [getattr(item, attribute, None) for item in items]
        seen: set[object] = set()
        for item_id in ids:
            if item_id in seen:
                issues.append(
                    _issue("error", code, f"duplicate {attribute}: {item_id}", reference.reference_id, path)
                )
            seen.add(item_id)

    duplicate_ids(facts.mechanics.resources, "resource_id", "DUPLICATE_RESOURCE_ID", "combat.mechanics.resources")
    duplicate_ids(facts.mechanics.states, "state_id", "DUPLICATE_STATE_ID", "combat.mechanics.states")
    duplicate_ids(
        facts.team_mechanics.interactions,
        "interaction_id",
        "DUPLICATE_TEAM_INTERACTION_ID",
        "combat.team_mechanics.interactions",
    )
    duplicate_ids(facts.relations, "relation_id", "DUPLICATE_RELATION_ID", "combat.relations")

    nodes = {
        "ability": {item.ability_id for item in facts.abilities},
        "state": {item.state_id for item in facts.mechanics.states},
        "resource": {item.resource_id for item in facts.mechanics.resources},
        "team_interaction": {item.interaction_id for item in facts.team_mechanics.interactions},
    }
    seen_edges: set[tuple[str, str, str, str, str]] = set()
    for relation in facts.relations:
        relation_path = f"combat.relations.{relation.relation_id}"
        if not RELATION_TYPE_RE.fullmatch(relation.relation_type):
            issues.append(
                _issue(
                    "error",
                    "INVALID_RELATION_TYPE",
                    f"relation_type must be non-empty snake_case: {relation.relation_type!r}",
                    reference.reference_id,
                    relation_path,
                )
            )
        for endpoint_name, endpoint in (("source", relation.source), ("target", relation.target)):
            if endpoint.id not in nodes[endpoint.kind]:
                issues.append(
                    _issue(
                        "error",
                        "UNKNOWN_MECHANIC_REFERENCE",
                        f"unknown {endpoint_name} {endpoint.kind} reference: {endpoint.id}",
                        reference.reference_id,
                        relation_path,
                    )
                )
        edge = (
            relation.source.kind,
            relation.source.id,
            relation.relation_type,
            relation.target.kind,
            relation.target.id,
        )
        if edge in seen_edges:
            issues.append(
                _issue(
                    "error",
                    "DUPLICATE_MECHANIC_RELATION",
                    "source/relation_type/target must be unique",
                    reference.reference_id,
                    relation_path,
                )
            )
        seen_edges.add(edge)
    return issues


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
    errors.extend(_mechanic_integrity_issues(reference))
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
