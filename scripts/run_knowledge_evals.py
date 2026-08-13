#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import KnowledgeResolverError


def _context(payload: dict) -> KnowledgeContext:
    return KnowledgeContext(
        active_responsibilities=frozenset(payload.get("active_responsibilities", [])),
        active_assignments=frozenset(payload.get("active_assignments", [])),
        active_projects=frozenset(payload.get("active_projects", [])),
        active_cases=frozenset(payload.get("active_cases", [])),
        active_incidents=frozenset(payload.get("active_incidents", [])),
        authorizations=frozenset(payload.get("authorizations", [])),
        active_roles=frozenset(payload.get("active_roles", [])),
        artist_teams=frozenset(payload.get("artist_teams", [])),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Knowledge Resolver evaluation cases")
    parser.add_argument("--file", type=Path, default=ROOT / "evals" / "knowledge_resolver_v0.1.yaml")
    args = parser.parse_args()
    with args.file.open("r", encoding="utf-8-sig") as stream:
        document = yaml.safe_load(stream) or {}
    resolver = KnowledgeResolver()
    failures = []
    for case in document.get("cases", []):
        try:
            result = resolver.resolve(case["character_id"], case["lore_id"], _context(case.get("context", {})))
            passed = result.decision == case["expected_decision"] and (
                "expected_reason_code" not in case or result.reason_code == case["expected_reason_code"]
            )
            if not passed:
                failures.append({
                    "case_id": case["id"],
                    "expected": {"decision": case["expected_decision"], "reason_code": case.get("expected_reason_code")},
                    "actual": {"decision": result.decision, "reason_code": result.reason_code},
                    "reason": result.reason,
                    "trace_summary": [item.get("reason_code") for item in result.trace],
                })
        except KnowledgeResolverError as error:
            expected_error = case.get("expected_error")
            if expected_error and error.__class__.__name__ == expected_error:
                continue
            failures.append({"case_id": case["id"], "error": str(error)})
    total = len(document.get("cases", []))
    print(json.dumps({"total": total, "passed": total - len(failures), "failed": len(failures), "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
