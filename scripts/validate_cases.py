#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge.loader import load_canon
from knowledge.registries import (
    registry_ids,
    validate_case_incident_relationships,
    validate_cases,
    validate_incidents,
    validate_projects,
)


def main() -> int:
    raw = load_canon()
    faction_ids = {record["id"] for record in raw["factions"]}
    lore_ids = {record["id"] for record in raw["lore"]}
    projects = validate_projects(
        raw["projects"],
        faction_ids=faction_ids,
        lore_ids=lore_ids,
        assignment_ids=set(raw["knowledge_rules"].get("vocabulary", {}).get("assignment_types", {})),
    )
    story_ids = registry_ids(raw["story_canon"], "stories")
    cases = validate_cases(
        raw["cases"],
        faction_ids=faction_ids,
        lore_ids=lore_ids,
        incident_ids=registry_ids(raw["incidents"], "incidents"),
        project_ids=set(projects),
        story_ids=story_ids,
    )
    incidents = validate_incidents(
        raw["incidents"],
        faction_ids=faction_ids,
        lore_ids=lore_ids,
        case_ids=set(cases),
        story_ids=story_ids,
    )
    validate_case_incident_relationships(cases, incidents)
    print(f"Case registry validation passed: {len(cases)} records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
