#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeResolver


def main() -> int:
    resolver = KnowledgeResolver()
    inventory = resolver.scope_registry.inventory(resolver.rules, resolver.vocabulary["condition_types"])
    total = len(inventory)
    resolved = sum(item["status"] == "resolved" for item in inventory)
    resolved_valid = resolved
    unresolved = sum(item["status"] == "unresolved" for item in inventory)
    missing = sum(item["status"] == "missing" for item in inventory)
    by_evaluator = defaultdict(lambda: {"resolved": 0, "unresolved": 0, "missing": 0, "invalid": 0})
    by_scope_type = defaultdict(lambda: {"resolved": 0, "unresolved": 0, "missing": 0, "invalid": 0})
    for item in inventory:
        by_evaluator[item["evaluator"]][item["status"]] += 1
        binding = resolver.scope_registry.get(item["rule_id"], item["condition"])
        scope_type = binding.scope_type if binding else "missing"
        by_scope_type[scope_type][item["status"]] += 1
    print(json.dumps({
        "total_condition_bindings_required": total,
        "resolved": resolved,
        "resolved_valid": resolved_valid,
        "unresolved": unresolved,
        "missing": missing,
        "invalid": sum(item["status"] == "invalid" for item in inventory),
        "coverage_percent": round((resolved_valid / total) * 100, 2) if total else 100.0,
        "by_evaluator": dict(by_evaluator),
        "by_scope_type": dict(by_scope_type),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
