#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeConfigurationError, KnowledgeResolver
from story import StoryError, load_story_repository


def main() -> int:
    try:
        repository = load_story_repository()
        resolver = KnowledgeResolver()
    except (StoryError, KnowledgeConfigurationError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "stories": len(repository.canon),
                "definitions": len(repository.definitions),
                "cases": len(resolver.cases),
                "incidents": len(resolver.incidents),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
