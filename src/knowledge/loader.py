from pathlib import Path
from typing import Any, Mapping
from importlib.resources.abc import Traversable

import yaml

from along_street_resources import data_root


Resource = Path | Traversable


def normalize_resource(value: Resource | str) -> Resource:
    """Keep packaged resources traversable while accepting filesystem paths."""

    if isinstance(value, (Path, Traversable)):
        return value
    return Path(value)


def join_resource(root: Resource, *parts: str) -> Resource:
    return root.joinpath(*parts)


def load_yaml(path: Resource | str) -> Any:
    path = normalize_resource(path)
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def _records(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        value = data.get(key, [])
        if isinstance(value, list):
            return value
    raise ValueError(f"Expected a list of {key} records")


def default_data_dir() -> Traversable:
    """Compatibility alias for the packaged data root."""

    return data_root()


def load_canon(data_dir: Resource | str | None = None) -> dict[str, Any]:
    root = data_root() if data_dir is None else normalize_resource(data_dir)
    return {
        "characters": _records(
            load_yaml(join_resource(root, "characters", "characters.yaml")), "characters"
        ),
        "lore": _records(load_yaml(join_resource(root, "lore", "lore.yaml")), "lore"),
        # Keep the complete policy document: resolver validation needs its vocabulary.
        "knowledge_rules": load_yaml(
            join_resource(root, "knowledge", "knowledge_rules.yaml")
        ),
        "condition_scopes": load_yaml(join_resource(root, "knowledge", "condition_scopes.yaml"))
        if join_resource(root, "knowledge", "condition_scopes.yaml").is_file()
        else {"bindings": []},
        "projects": load_yaml(join_resource(root, "projects", "projects.yaml"))
        if join_resource(root, "projects", "projects.yaml").is_file()
        else {"version": "0.1", "projects": []},
        "cases": load_yaml(join_resource(root, "cases", "cases.yaml"))
        if join_resource(root, "cases", "cases.yaml").is_file()
        else {"version": "0.1", "cases": []},
        "incidents": load_yaml(join_resource(root, "incidents", "incidents.yaml"))
        if join_resource(root, "incidents", "incidents.yaml").is_file()
        else {"version": "0.1", "incidents": []},
        "authorizations": load_yaml(join_resource(root, "knowledge", "authorizations.yaml"))
        if join_resource(root, "knowledge", "authorizations.yaml").is_file()
        else {"version": "0.1", "authorizations": []},
        "story_canon": load_yaml(join_resource(root, "stories", "story_canon.yaml"))
        if join_resource(root, "stories", "story_canon.yaml").is_file()
        else {"version": "0.1", "stories": []},
        "story_definitions": load_yaml(
            join_resource(root, "stories", "story_definitions.yaml")
        )
        if join_resource(root, "stories", "story_definitions.yaml").is_file()
        else {"version": "0.1", "story_definitions": []},
        "factions": _records(
            load_yaml(join_resource(root, "factions", "factions.yaml")), "factions"
        ),
    }


def index_by_id(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"Every {label} record must have a non-empty id")
        if record_id in result:
            raise ValueError(f"Duplicate {label} id: {record_id}")
        result[record_id] = record
    return result
