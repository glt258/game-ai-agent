from __future__ import annotations

from collections.abc import Iterable

from .errors import ProvenanceValidationError
from .models import CharacterFacts, CharacterProvenance


def resolve_fact_field_path(facts: CharacterFacts, field_path: str) -> object:
    """Resolve a supported, non-indexed field path against CharacterFacts."""
    if not isinstance(field_path, str) or not field_path.strip():
        raise ProvenanceValidationError("field evidence path must be non-empty")
    parts = field_path.split(".")
    if any(not part.strip() for part in parts):
        raise ProvenanceValidationError(f"invalid field evidence path: {field_path!r}")
    if any(part.isdigit() for part in parts):
        raise ProvenanceValidationError(
            f"indexed field evidence paths are unsupported: {field_path}"
        )

    current: object = facts
    for part in parts:
        if isinstance(current, list):
            raise ProvenanceValidationError(
                f"field evidence path enters a list, unsupported: {field_path}"
            )
        if isinstance(current, dict):
            if part not in current:
                raise ProvenanceValidationError(f"unknown fact field path: {field_path}")
            current = current[part]
            continue
        if not hasattr(current, part):
            raise ProvenanceValidationError(f"unknown fact field path: {field_path}")
        current = getattr(current, part)
    return current


def validate_provenance(
    provenance: CharacterProvenance,
    facts: CharacterFacts,
) -> None:
    """Validate source IDs, evidence paths, and cross-file provenance invariants."""
    source_ids = [source.source_id for source in provenance.sources]
    if len(source_ids) != len(set(source_ids)):
        raise ProvenanceValidationError("source_id must be unique within a character")
    known_source_ids = set(source_ids)
    if not provenance.sources:
        raise ProvenanceValidationError("at least one source is required")

    for relation in provenance.source_relations:
        if relation.source_id not in known_source_ids:
            raise ProvenanceValidationError(
                "UNKNOWN_SOURCE_RELATION_SOURCE: "
                f"unknown source relation source_id: {relation.source_id}"
            )
        if relation.target_source_id not in known_source_ids:
            raise ProvenanceValidationError(
                "UNKNOWN_SOURCE_RELATION_TARGET: "
                f"unknown source relation target_source_id: {relation.target_source_id}"
            )
        for field_path in relation.field_paths:
            try:
                resolve_fact_field_path(facts, field_path)
            except ProvenanceValidationError as exc:
                raise ProvenanceValidationError(
                    "UNKNOWN_SOURCE_RELATION_FIELD: "
                    f"{field_path}: {exc}"
                ) from exc

        if relation.relation_type in {"supersedes", "clarifies"}:
            source = next(item for item in provenance.sources if item.source_id == relation.source_id)
            target = next(item for item in provenance.sources if item.source_id == relation.target_source_id)
            if (
                source.published_at is not None
                and target.published_at is not None
                and source.published_at < target.published_at
            ):
                raise ProvenanceValidationError(
                    "INVALID_SOURCE_RELATION_CHRONOLOGY: "
                    f"{relation.source_id} is earlier than {relation.target_source_id}"
                )

    for field_path, evidence_ids in provenance.field_evidence.items():
        if not field_path.strip():
            raise ProvenanceValidationError("field evidence path must be non-empty")
        if not evidence_ids:
            raise ProvenanceValidationError(f"field evidence for {field_path} is empty")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ProvenanceValidationError(f"duplicate source IDs in evidence for {field_path}")
        unknown = set(evidence_ids) - known_source_ids
        if unknown:
            raise ProvenanceValidationError(
                f"unknown evidence source ID(s) for {field_path}: {sorted(unknown)}"
            )
        resolve_fact_field_path(facts, field_path)

    superseded_fields: dict[str, set[str]] = {}
    for relation in provenance.source_relations:
        if relation.relation_type != "supersedes":
            continue
        for field_path in relation.field_paths:
            superseded_fields.setdefault(field_path, set()).add(relation.target_source_id)
    for field_path, superseded_source_ids in superseded_fields.items():
        current_evidence = set(provenance.field_evidence.get(field_path, []))
        invalid = current_evidence & superseded_source_ids
        if invalid:
            raise ProvenanceValidationError(
                "SUPERSEDED_SOURCE_IN_CURRENT_EVIDENCE: "
                f"{sorted(invalid)} remain current evidence for {field_path}"
            )

    for conflict in provenance.verification.conflicts:
        unknown = set(conflict.source_ids) - known_source_ids
        if unknown:
            raise ProvenanceValidationError(
                f"unknown conflict source ID(s) for {conflict.field_path}: {sorted(unknown)}"
            )
        resolve_fact_field_path(facts, conflict.field_path)


def evidence_source_ids(provenance: CharacterProvenance) -> set[str]:
    return {source_id for ids in provenance.field_evidence.values() for source_id in ids}


def validate_field_paths(facts: CharacterFacts, paths: Iterable[str]) -> None:
    for path in paths:
        resolve_fact_field_path(facts, path)
