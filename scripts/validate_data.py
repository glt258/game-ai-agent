#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeResolver
from knowledge.loader import load_canon
from knowledge.responsibility_validation import validate_knowledge_responsibilities
from story import load_story_repository


def main() -> int:
    KnowledgeResolver()
    data = load_canon()
    validate_knowledge_responsibilities(
        knowledge_rules_data=data["knowledge_rules"],
        condition_scopes_data=data["condition_scopes"],
        factions_data=data["factions"],
        characters_data=data["characters"],
    )
    load_story_repository()
    print("Knowledge data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
