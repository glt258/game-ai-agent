#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge.loader import load_canon
from knowledge.registries import validate_authorizations, validate_projects


def main() -> int:
    raw = load_canon()
    projects = validate_projects(
        raw["projects"],
        faction_ids={record["id"] for record in raw["factions"]},
        lore_ids={record["id"] for record in raw["lore"]},
        assignment_ids=set(raw["knowledge_rules"].get("vocabulary", {}).get("assignment_types", {})),
    )
    authorizations = validate_authorizations(
        raw["authorizations"],
        faction_ids={record["id"] for record in raw["factions"]},
        target_registries={"project": set(projects)},
    )
    print(f"Authorization registry validation passed: {len(authorizations)} records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
