"""Offline evals for the one-attempt Character Repair Loop."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from agents import (
    CanonChecker,
    CanonCheckStatus,
    CharacterDesignRequest,
    CharacterDraft,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
    ModelTurn,
    RepairResultStatus,
    ScriptedAgentModel,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def _case(name: str):
    payload = json.loads((FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8"))
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(**payload["request"])


def _run(draft, request, model):
    checker = CanonChecker()
    initial = checker.check(draft, request=request)
    agent = CharacterRepairAgent(model, checker=checker)
    result = agent.repair(agent.prepare_request(request, draft, initial))
    return result


def build_cases():
    good, good_request = _case("good")
    shenzhao, shenzhao_request = _case("shenzhao")
    bad, bad_request = _case("bad")
    cases = {
        "pass_draft_skips_repair": (good, good_request, DeterministicCharacterRepairModel(), lambda r: r.status == RepairResultStatus.NO_REPAIR_NEEDED),
        "shenzhao_warn_repairs_to_pass": (shenzhao, shenzhao_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "authority_overreach_repaired": (replace(good, occupation="公共安全联席体系最高负责人"), good_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "knowledge_overreach_repaired": (replace(good, knowledge_scope="可查看全城每位能力者内部档案"), good_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "story_role_overreach_repaired": (replace(shenzhao, story_hook="所有关键决定由她拍板"), shenzhao_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "proposal_smuggling_repaired": (replace(shenzhao, background="她已经建立南栈观察项目并决定后续方向。"), shenzhao_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status != CanonCheckStatus.WARN or r.final_check.summary.warnings < 2),
        "canon_presented_as_proposal_repaired": (replace(shenzhao, new_design_elements=("南栈演出散场事故",)), shenzhao_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "forbidden_secret_authority_repaired": (bad, bad_request, DeterministicCharacterRepairModel(), lambda r: r.final_check.summary.errors < 11),
        "minor_frontline_repaired_when_brief_allows": (replace(good, age=16, age_range="16", occupation="消防员"), replace(good_request, request_id="minor_frontline", hard_constraints=("16岁",)), DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.PASS),
        "unrepairable_hard_constraint_stays_fail": (bad, replace(bad_request, request_id="impossible", hard_constraints=("17岁", "必须担任公共安全联席体系最高负责人", "必须掌握全城能力者档案")), DeterministicCharacterRepairModel(), lambda r: r.final_check.status == CanonCheckStatus.FAIL),
        "scope_violation_rejected": (shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="scope_violation"), lambda r: r.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION),
        "repair_model_failure_preserves_original": (shenzhao, shenzhao_request, ScriptedAgentModel([ModelTurn(text="{not-json")]), lambda r: r.status == RepairResultStatus.REPAIR_MODEL_FAILED and r.recommended_draft == shenzhao),
        "repair_regression_preserves_original": (shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="regression"), lambda r: r.recommended_draft == shenzhao),
        "fake_source_not_allowed": (shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="fake_source"), lambda r: r.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION),
        "tool_call_not_allowed": (shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="tool_call"), lambda r: r.status == RepairResultStatus.REPAIR_MODEL_FAILED),
        "wrong_wrapper_rejected": (shenzhao, shenzhao_request, ScriptedAgentModel([ModelTurn(text=json.dumps({"repaired_draft": shenzhao.to_dict()}, ensure_ascii=False))]), lambda r: r.status == RepairResultStatus.REPAIR_MODEL_FAILED),
    }
    return cases


def main() -> int:
    results = []
    counters = {"repair_attempted": 0, "repaired_pass": 0, "repaired_warn": 0, "unresolved_fail": 0}
    for name, (draft, request, model, predicate) in build_cases().items():
        result = _run(draft, request, model)
        if result.repair_attempted:
            counters["repair_attempted"] += 1
        if result.status == RepairResultStatus.REPAIRED_PASS:
            counters["repaired_pass"] += 1
        if result.status == RepairResultStatus.REPAIRED_WARN:
            counters["repaired_warn"] += 1
        if result.final_check.status == CanonCheckStatus.FAIL:
            counters["unresolved_fail"] += 1
        ok = bool(predicate(result))
        results.append((name, ok, result.status.value, result.final_check.status.value, result.error))
    passed = sum(item[1] for item in results)
    failed = len(results) - passed
    print(f"Character Repair evals: {passed} passed, {failed} failed")
    print(json.dumps({"total": len(results), "passed": passed, "failed": failed, **counters}, ensure_ascii=False, indent=2))
    for name, ok, status, final_status, error in results:
        if not ok:
            print(f"FAIL {name}: status={status} final={final_status} error={error}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
