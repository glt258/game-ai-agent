from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from knowledge.loader import default_data_dir, load_canon, load_yaml
from knowledge.registries import registry_ids

from .models import StoryDefinition
from .validation import validate_story_canon, validate_story_definitions


@dataclass(frozen=True)
class StoryRepository:
    canon: Mapping[str, Mapping[str, Any]]
    definitions: Mapping[str, StoryDefinition]
    character_ids: frozenset[str]
    case_ids: frozenset[str]
    incident_ids: frozenset[str]


def load_story_repository(data_dir: Path | None = None) -> StoryRepository:
    root = Path(data_dir) if data_dir else default_data_dir()
    raw = load_canon(root)
    city_data = load_yaml(root / "locations" / "cities.yaml")
    cities = city_data.get("cities", []) if isinstance(city_data, Mapping) else []
    character_ids = {record["id"] for record in raw["characters"]}
    faction_ids = {record["id"] for record in raw["factions"]}
    case_ids = registry_ids(raw["cases"], "cases")
    incident_ids = registry_ids(raw["incidents"], "incidents")
    canon = validate_story_canon(
        raw["story_canon"],
        city_ids={record["id"] for record in cities},
        faction_ids=faction_ids,
        character_ids=character_ids,
    )
    definitions = validate_story_definitions(
        raw["story_definitions"],
        story_ids=set(canon),
        case_ids=case_ids,
        incident_ids=incident_ids,
        character_ids=character_ids,
    )
    return StoryRepository(
        canon,
        definitions,
        frozenset(character_ids),
        frozenset(case_ids),
        frozenset(incident_ids),
    )
