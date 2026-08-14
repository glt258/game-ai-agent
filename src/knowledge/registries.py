from __future__ import annotations

from typing import Any, Mapping

from .errors import KnowledgeConfigurationError


AUTHORIZATION_SCOPE_TYPES = frozenset({"project", "dataset", "review", "case", "incident"})
CASE_INCIDENT_STATUSES = frozenset({"open", "closed", "ongoing", "historical"})


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


def registry_ids(data: Any, key: str) -> set[str]:
    """Read unique concrete IDs before validating cross-registry references."""
    _, records = records_document(data, key)
    result: set[str] = set()
    singular = key[:-1] if key.endswith("s") else key
    for record in records:
        if not isinstance(record, Mapping):
            raise KnowledgeConfigurationError(f"every {singular} record must be a mapping")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise KnowledgeConfigurationError(f"every {singular} needs a non-empty id")
        if record_id in result:
            raise KnowledgeConfigurationError(f"duplicate {singular} id: {record_id}")
        result.add(record_id)
    return result


def validate_cases(
    data: Any,
    *,
    faction_ids: set[str],
    lore_ids: set[str],
    incident_ids: set[str],
    project_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _, records = records_document(data, "cases")
    known_ids = registry_ids(data, "cases")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        case_id = record["id"]
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            raise KnowledgeConfigurationError(f"{case_id}: case name must be non-empty")
        faction_id = record.get("faction_id")
        if faction_id not in faction_ids:
            raise KnowledgeConfigurationError(f"{case_id}: unknown faction {faction_id}")
        lore_refs = record.get("lore_refs", [])
        _require_refs(case_id, "lore_refs", lore_refs)
        _validate_refs(case_id, "lore_refs", lore_refs, lore_ids, "lore")
        _validate_refs(
            case_id,
            "related_incident_ids",
            record.get("related_incident_ids", []),
            incident_ids,
            "incident",
        )
        _validate_refs(
            case_id,
            "related_project_ids",
            record.get("related_project_ids", []),
            project_ids,
            "project",
        )
        _validate_status(case_id, record.get("status"), "case")
        result[case_id] = dict(record)
    if set(result) != known_ids:  # Defensive: both passes must describe the same document.
        raise KnowledgeConfigurationError("case registry changed during validation")
    return result


def validate_incidents(
    data: Any,
    *,
    faction_ids: set[str],
    lore_ids: set[str],
    case_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _, records = records_document(data, "incidents")
    known_ids = registry_ids(data, "incidents")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        incident_id = record["id"]
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            raise KnowledgeConfigurationError(f"{incident_id}: incident name must be non-empty")
        incident_factions = record.get("faction_ids", [])
        _require_refs(incident_id, "faction_ids", incident_factions)
        _validate_refs(
            incident_id,
            "faction_ids",
            incident_factions,
            faction_ids,
            "faction",
        )
        lore_refs = record.get("lore_refs", [])
        _require_refs(incident_id, "lore_refs", lore_refs)
        _validate_refs(incident_id, "lore_refs", lore_refs, lore_ids, "lore")
        _validate_refs(
            incident_id,
            "related_case_ids",
            record.get("related_case_ids", []),
            case_ids,
            "case",
        )
        _validate_status(incident_id, record.get("status"), "incident")
        result[incident_id] = dict(record)
    if set(result) != known_ids:
        raise KnowledgeConfigurationError("incident registry changed during validation")
    return result


def validate_case_incident_relationships(
    cases: Mapping[str, Mapping[str, Any]],
    incidents: Mapping[str, Mapping[str, Any]],
) -> None:
    """Keep optional bidirectional Case/Incident links from drifting."""
    shared_ids = set(cases) & set(incidents)
    if shared_ids:
        raise KnowledgeConfigurationError(
            f"case and incident IDs must be distinct: {sorted(shared_ids)}"
        )
    for case_id, case in cases.items():
        for incident_id in case.get("related_incident_ids", []):
            if case_id not in incidents[incident_id].get("related_case_ids", []):
                raise KnowledgeConfigurationError(
                    f"{case_id}: relationship to {incident_id} is not bidirectional"
                )
    for incident_id, incident in incidents.items():
        for case_id in incident.get("related_case_ids", []):
            if incident_id not in cases[case_id].get("related_incident_ids", []):
                raise KnowledgeConfigurationError(
                    f"{incident_id}: relationship to {case_id} is not bidirectional"
                )


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


def _require_refs(record_id: str, field_name: str, refs: Any) -> None:
    if not isinstance(refs, list) or not refs:
        raise KnowledgeConfigurationError(f"{record_id}: {field_name} must contain at least one ID")


def _validate_status(record_id: str, status: Any, label: str) -> None:
    if status is not None and status not in CASE_INCIDENT_STATUSES:
        raise KnowledgeConfigurationError(f"{record_id}: unsupported {label} status {status!r}")
