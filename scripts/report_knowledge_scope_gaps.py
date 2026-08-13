#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeResolver


def main() -> int:
    resolver = KnowledgeResolver()
    inventory = resolver.scope_registry.inventory(resolver.rules, resolver.vocabulary["condition_types"])
    lines = ["# Knowledge Scope Gaps", "", "This report records Canon modeling gaps; it does not manufacture IDs or permissions.", ""]
    gaps = [item for item in inventory if item["status"] != "resolved"]
    if not gaps:
        lines.append("No unresolved or missing scope bindings.")
    else:
        lines.extend(["| rule_id | lore_id | condition | evaluator | status | gap_type | reason |", "|---|---|---|---|---|---|---|"])
        for item in gaps:
            reason = item.get("reason") or "invalid scope binding"
            lines.append(f"| {item['rule_id']} | {item['lore_id']} | {item['condition']} | {item['evaluator']} | {item['status']} | {item.get('gap_type') or 'other'} | {reason} |")
    output = ROOT / "docs" / "knowledge_scope_gaps.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
