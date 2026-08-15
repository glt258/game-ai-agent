"""Offline-first Character Repair Loop demo."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from agents import (
    CanonChecker,
    CharacterAuthoringWorkflow,
    CharacterDesignRequest,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    CharacterRepairAgent,
    CharacterDraft,
    DeterministicCharacterRepairModel,
    RepairResultStatus,
    character_model_from_environment,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def _load(case: str):
    filename = {"pass": "good", "subtle": "shenzhao", "bad": "bad", "unrepairable": "bad"}[case]
    payload = json.loads((FIXTURES / f"canon_checker_{filename}.json").read_text(encoding="utf-8"))
    draft = CharacterDraft.from_mapping(payload["draft"])
    request = CharacterDesignRequest(**payload["request"])
    if case == "unrepairable":
        request = replace(
            request,
            request_id="demo_impossible_001",
            hard_constraints=("17岁", "必须担任公共安全联席体系最高负责人", "必须掌握全城能力者档案"),
        )
    return draft, request


class _FixtureGenerationAgent:
    def __init__(self, draft):
        self.draft = draft

    def generate(self, _request):
        return CharacterGenerationResult(self.draft, (), CharacterGenerationAudit(self.draft.draft_id, 0, (), ()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Character Repair Loop v0.1 demo")
    parser.add_argument("--case", choices=("pass", "subtle", "bad", "unrepairable"), default="subtle")
    parser.add_argument("--model", choices=("offline", "live"), default="offline")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    draft, request = _load(args.case)
    checker = CanonChecker()
    if args.model == "live":
        # The same provider-neutral adapter used by generation is reused for
        # repair.  The repair prompt has an empty tool list and the same
        # CharacterDraft structured-output contract.
        repair_model = character_model_from_environment(mode_override="live")
    else:
        repair_model = DeterministicCharacterRepairModel()
    workflow = CharacterAuthoringWorkflow(
        _FixtureGenerationAgent(draft),
        CharacterRepairAgent(repair_model, checker=checker),
        checker=checker,
    )
    result = workflow.run(request)
    if args.as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        return 0

    print("Character Repair")
    print("================")
    print(f"Case: {args.case}")
    print(f"Draft: {result.initial_draft.draft_id} / {result.initial_draft.name}")
    print(f"Initial Check: {result.initial_check.status.value.upper()} ({len(result.initial_check.findings)} findings)")
    for finding in result.initial_check.findings:
        print(f"- {finding.code.value} @ {finding.field_path}")
    print(f"Repair Attempted: {'yes' if result.repair_result.repair_attempted else 'no'}")
    if result.repair_result.changed_fields:
        print("Changed Fields:")
        for field_name in result.repair_result.changed_fields:
            print(f"- {field_name}")
    print(f"Final Check: {result.final_check.status.value.upper()} ({len(result.final_check.findings)} findings)")
    print(f"Resolution: {result.repair_result.status.value}")
    print(f"Recommended Draft: {result.final_draft.draft_id} / {result.final_draft.name}")
    if result.repair_result.error:
        print(f"Repair Error: {result.repair_result.error}")
    if result.final_check.status.value == "fail":
        print("Human review required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
