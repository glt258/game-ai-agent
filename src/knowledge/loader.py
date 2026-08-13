from pathlib import Path
from typing import Any, Mapping

import yaml


def load_yaml(path: Path) -> Any:
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


def default_data_dir() -> Path:
    # loader.py -> knowledge -> src -> project root
    return Path(__file__).resolve().parents[2] / "data"


def load_canon(data_dir: Path | None = None) -> dict[str, Any]:
    root = Path(data_dir) if data_dir else default_data_dir()
    return {
        "characters": _records(load_yaml(root / "characters" / "characters.yaml"), "characters"),
        "lore": _records(load_yaml(root / "lore" / "lore.yaml"), "lore"),
        # Keep the complete policy document: resolver validation needs its vocabulary.
        "knowledge_rules": load_yaml(root / "knowledge" / "knowledge_rules.yaml"),
        "condition_scopes": load_yaml(root / "knowledge" / "condition_scopes.yaml")
        if (root / "knowledge" / "condition_scopes.yaml").exists()
        else {"bindings": []},
        "projects": load_yaml(root / "projects" / "projects.yaml")
        if (root / "projects" / "projects.yaml").exists()
        else {"version": "0.1", "projects": []},
        "authorizations": load_yaml(root / "knowledge" / "authorizations.yaml")
        if (root / "knowledge" / "authorizations.yaml").exists()
        else {"version": "0.1", "authorizations": []},
        "factions": _records(load_yaml(root / "factions" / "factions.yaml"), "factions"),
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
