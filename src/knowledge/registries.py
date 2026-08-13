from __future__ import annotations

from typing import Any, Mapping

from .errors import KnowledgeConfigurationError


AUTHORIZATION_SCOPE_TYPES = frozenset({"project", "dataset", "review", "case", "incident"})


def records_document(data: Any, key: str) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(data, Mapping):
        raise KnowledgeConfigurationError(f"{key} registry must be a mapping")
    version = data.get("version")
    records = data.get(key)
    if not isinstance(version, str) or not version.strip():
        raise KnowledgeConfigurationError(f"{key} registry requires a non-empty version")
    if not isinstance(records, list):
        raise KnowledgeConfigurationError(f"{key} registry requires a list of {key}")
    return version, records


def validate_projects(
    data: Any,
    *,
    faction_ids: set[str],
    lore_ids: set[str],
    assignment_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _, records = records_document(data, "projects")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise KnowledgeConfigurationError("every project record must be a mapping")
        project_id = record.get("id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise KnowledgeConfigurationError("every project needs a non-empty id")
        if project_id in result:
            raise KnowledgeConfigurationError(f"duplicate project id: {project_id}")
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            raise KnowledgeConfigurationError(f"{project_id}: project name must be non-empty")
        faction_id = record.get("faction_id")
        if faction_id not in faction_ids:
            raise KnowledgeConfigurationError(f"{project_id}: unknown faction {faction_id}")
        _validate_refs(project_id, "lore_refs", record.get("lore_refs", []), lore_ids, "lore")
        _validate_refs(
            project_id,
            "assignment_refs",
            record.get("assignment_refs", []),
            assignment_ids,
            "assignment",
        )
        result[project_id] = dict(record)
    return result


def validate_authorizations(
    data: Any,
    *,
    faction_ids: set[str],
    target_registries: Mapping[str, set[str]],
) -> dict[str, dict[str, Any]]:
    _, records = records_document(data, "authorizations")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise KnowledgeConfigurationError("every authorization record must be a mapping")
        authorization_id = record.get("id")
        if not isinstance(authorization_id, str) or not authorization_id.strip():
            raise KnowledgeConfigurationError("every authorization needs a non-empty id")
        if authorization_id in result:
            raise KnowledgeConfigurationError(f"duplicate authorization id: {authorization_id}")
        faction_id = record.get("faction_id")
        if faction_id not in faction_ids:
            raise KnowledgeConfigurationError(f"{authorization_id}: unknown faction {faction_id}")
        if not isinstance(record.get("purpose"), str) or not record["purpose"].strip():
            raise KnowledgeConfigurationError(f"{authorization_id}: purpose must be non-empty")
        scope_type = record.get("scope_type")
        if scope_type not in AUTHORIZATION_SCOPE_TYPES:
            raise KnowledgeConfigurationError(f"{authorization_id}: unsupported scope_type {scope_type}")
        target_refs = record.get("target_refs")
        if not isinstance(target_refs, list) or not target_refs or any(
            not isinstance(value, str) or not value.strip() for value in target_refs
        ):
            raise KnowledgeConfigurationError(f"{authorization_id}: target_refs must contain concrete IDs")
        if len(target_refs) != len(set(target_refs)):
            raise KnowledgeConfigurationError(f"{authorization_id}: duplicate target_refs")
        known_targets = target_registries.get(scope_type)
        if known_targets is None:
            raise KnowledgeConfigurationError(
                f"{authorization_id}: target registry is unavailable for scope_type {scope_type}"
            )
        unknown = set(target_refs) - known_targets
        if unknown:
            raise KnowledgeConfigurationError(
                f"{authorization_id}: unknown {scope_type} target(s): {sorted(unknown)}"
            )
        result[authorization_id] = dict(record)
    return result


def _validate_refs(
    record_id: str,
    field_name: str,
    refs: Any,
    known: set[str],
    label: str,
) -> None:
    if not isinstance(refs, list) or any(not isinstance(value, str) or not value.strip() for value in refs):
        raise KnowledgeConfigurationError(f"{record_id}: {field_name} must contain string IDs")
    if len(refs) != len(set(refs)):
        raise KnowledgeConfigurationError(f"{record_id}: duplicate {field_name}")
    unknown = set(refs) - known
    if unknown:
        raise KnowledgeConfigurationError(f"{record_id}: unknown {label} reference(s): {sorted(unknown)}")
