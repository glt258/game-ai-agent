#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeConfigurationError, KnowledgeResolver


def main() -> int:
    try:
        resolver = KnowledgeResolver()
    except KnowledgeConfigurationError as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    inventory = resolver.scope_registry.inventory(resolver.rules, resolver.vocabulary["condition_types"])
    counts = {"duplicate_bindings": 0, "unknown_rule_refs": 0, "unknown_lore_refs": 0, "evaluator_mismatch": 0, "unknown_vocabulary": 0}
    invalid = [item for item in inventory if item["status"] == "invalid"]
    print(json.dumps({"valid": not invalid, **counts, "invalid": invalid, "condition_inventory": inventory}, ensure_ascii=False, indent=2))
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
