#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeResolver
from story import KnowledgeContextProvider, StoryRuntime


def main() -> int:
    with (ROOT / "evals" / "story_state_v0.1.yaml").open("r", encoding="utf-8-sig") as stream:
        document = yaml.safe_load(stream) or {}
    runtime = StoryRuntime()
    provider = KnowledgeContextProvider(runtime.repository)
    resolver = KnowledgeResolver()
    initial = runtime.initial_state("story_after_the_show_001")
    final = initial
    for transition_id in document.get("transition_sequence", []):
        final = runtime.transition(final, transition_id)
    failures = []
    for case in document.get("cases", []):
        try:
            kind = case["type"]
            if kind == "final_state":
                passed = (
                    final.current_node_id == case["expected_current_node_id"]
                    and sorted(final.active_case_ids) == sorted(case["expected_active_cases"])
                    and sorted(final.active_incident_ids) == sorted(case["expected_active_incidents"])
                    and dict(final.story_flags) == case["expected_flags"]
                )
            elif kind == "context":
                context = provider.for_character(case["character_id"], final)
                passed = (
                    sorted(context.active_cases) == sorted(case["expected_active_cases"])
                    and sorted(context.active_incidents) == sorted(case["expected_active_incidents"])
                )
            elif kind == "knowledge":
                context = provider.for_character(case["character_id"], final)
                passed = (
                    resolver.resolve(case["character_id"], case["lore_id"], context).decision
                    == case["expected_decision"]
                )
            elif kind == "illegal_transition":
                try:
                    runtime.transition(initial, case["transition_id"])
                except Exception as error:
                    passed = error.__class__.__name__ == case["expected_error"]
                else:
                    passed = False
            else:
                passed = False
            if not passed:
                failures.append({"case_id": case["id"], "reason": "expectation mismatch"})
        except Exception as error:
            failures.append({"case_id": case["id"], "error": str(error)})
    total = len(document.get("cases", []))
    print(
        json.dumps(
            {
                "total": total,
                "passed": total - len(failures),
                "failed": len(failures),
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
