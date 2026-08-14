#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge.loader import load_canon
from knowledge.responsibility_validation import validate_knowledge_responsibilities


def main() -> int:
    data = load_canon()
    result = validate_knowledge_responsibilities(
        knowledge_rules_data=data["knowledge_rules"],
        condition_scopes_data=data["condition_scopes"],
        factions_data=data["factions"],
        characters_data=data["characters"],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
