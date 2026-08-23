"""Hermes-style semantic regression runner for Character Repair v0.1.1."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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


FIXTURES = ROOT / "evals" / "fixtures"


def _case(name: str):
    payload = json.loads((FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8"))
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(**payload["request"])


def _checker_case(name: str, draft: CharacterDraft, request: CharacterDesignRequest, expected: CanonCheckStatus):
    report = CanonChecker().check(draft, request=request)
    return {"name": name, "kind": "checker", "expected": report.status == expected, "actual": report.status.value, "failure": report.status != expected}


def _repair_case(name: str, draft: CharacterDraft, request: CharacterDesignRequest, model, expected):
    checker = CanonChecker()
    initial = checker.check(draft, request=request)
    agent = CharacterRepairAgent(model, checker=checker)
    result = agent.repair(agent.prepare_request(request, draft, initial))
    ok = bool(expected(result))
    return {"name": name, "kind": "repair", "expected": ok, "actual": result.status.value, "failure": not ok, "result": result}


def build_cases():
    good, good_request = _case("good")
    shenzhao, shenzhao_request = _case("shenzhao")
    bad, bad_request = _case("bad")
    checker_cases = [
        ("hidden_authority_title_denial", "她没有正式指挥头衔，但任何关键行动都必须经过她确认，警察、消防、急救最终都按她的决定行动。", CanonCheckStatus.FAIL),
        ("hidden_authority_must_pass", "所有关键决定均须经过她确认。", CanonCheckStatus.FAIL),
        ("hidden_authority_departments", "各部门虽然独立，但关键行动必须取得她同意。", CanonCheckStatus.FAIL),
        ("hidden_authority_final_action", "警察、消防、急救最终按她决定行动。", CanonCheckStatus.FAIL),
        ("negated_command", "她不指挥警察、消防或急救，只负责汇总各部门信息。", CanonCheckStatus.PASS),
        ("negated_title_coordination", "她没有正式指挥头衔，但只协调警方、消防和急救的信息交接。", CanonCheckStatus.PASS),
        ("internal_materials", "市里每位能力者的内部资料她都可以调阅", CanonCheckStatus.FAIL),
        ("public_materials", "她可以阅读项目公开资料", CanonCheckStatus.PASS),
        ("unpublished_research_near_neighbor", "研究中心有一个尚未公开发表结果的研究项目。", CanonCheckStatus.PASS),
        ("ordinary_student_quantifier", "她认识实验室里的每位同学。", CanonCheckStatus.PASS),
        ("single_ability_manifestation", "她只能在一次短暂显现中稳定一个小物件。", CanonCheckStatus.PASS),
        ("proposal_hedge", "她可能在未来参与一次南栈复盘。", CanonCheckStatus.PASS),
    ]
    results = []
    for name, text, expected in checker_cases:
        field_name = "knowledge_scope" if name in {"internal_materials", "public_materials"} else "background"
        results.append(_checker_case(name, replace(good, **{field_name: text}), good_request, expected))

    knowledge_request = replace(good_request, hard_constraints=("必须掌握全城能力者档案",), request_id="rt_runner_knowledge")
    knowledge_draft = replace(good, knowledge_scope="可访问全城所有能力者档案")
    results.append(_repair_case("knowledge_hard_constraint_drop", knowledge_draft, knowledge_request, DeterministicCharacterRepairModel(), lambda r: r.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION and r.recommended_draft == knowledge_draft))

    authority_request = replace(good_request, hard_constraints=("必须拥有跨部门统一指挥权",), request_id="rt_runner_authority")
    authority_draft = replace(good, occupation="跨部门统一指挥警察、消防和急救", social_role="拥有统一调度权")
    authority_payload = authority_draft.to_dict()
    authority_payload.update({"occupation": "普通协调员", "social_role": "只负责信息整理"})
    results.append(_repair_case("authority_hard_constraint_drop", authority_draft, authority_request, ScriptedAgentModel([ModelTurn(text=json.dumps(authority_payload, ensure_ascii=False))]), lambda r: r.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION))

    story_request = replace(shenzhao_request, hard_constraints=("必须是南栈事故核心负责人",), request_id="rt_runner_story")
    story_draft = replace(shenzhao, story_hook="她是南栈事故核心负责人，所有关键决定由她拍板。")
    results.append(_repair_case("story_role_hard_constraint_drop", story_draft, story_request, DeterministicCharacterRepairModel(), lambda r: r.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION))

    relationship_draft = CharacterDraft.from_mapping({**shenzhao.to_dict(), "relationships": [{"target_id": "char_launch_001", "description": "拟议协作", "status": "proposed"}]})
    results.append(_repair_case("relationship_roundtrip_repair", relationship_draft, shenzhao_request, DeterministicCharacterRepairModel(), lambda r: json.dumps(r.to_dict(), ensure_ascii=False) is not None and r.final_check.status == CanonCheckStatus.PASS))

    wrapper = {"repaired_draft": shenzhao.to_dict()}
    results.append(_repair_case("wrong_wrapper", shenzhao, shenzhao_request, ScriptedAgentModel([ModelTurn(text=json.dumps(wrapper, ensure_ascii=False))]), lambda r: r.status == RepairResultStatus.REPAIR_MODEL_FAILED))
    results.append(_repair_case("tool_call", shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="tool_call"), lambda r: r.status == RepairResultStatus.REPAIR_MODEL_FAILED))
    results.append(_repair_case("scope_name_change", shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="scope_violation"), lambda r: r.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION))
    results.append(_repair_case("fake_source", shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="fake_source"), lambda r: r.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION))
    results.append(_repair_case("one_attempt_regression", shenzhao, shenzhao_request, DeterministicCharacterRepairModel(mode="regression"), lambda r: r.repair_attempt == 1 and r.recommended_draft == shenzhao))
    return results


def main() -> int:
    results = build_cases()
    correct = sum(not item["failure"] for item in results)
    false_negatives = sum(item["kind"] == "checker" and item["actual"] == "pass" and item["failure"] for item in results)
    false_positives = sum(item["kind"] == "checker" and item["actual"] != "pass" and item["failure"] for item in results)
    scope_failures = sum(item["kind"] == "repair" and item["actual"] in {RepairResultStatus.REPAIR_SCOPE_VIOLATION.value, RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION.value} and item["failure"] for item in results)
    serialization_failures = sum("roundtrip" in item["name"] and item["failure"] for item in results)
    security_failures = sum(item["name"] in {"wrong_wrapper", "tool_call", "fake_source"} and item["failure"] for item in results)
    recommendation_failures = sum(item["name"] == "one_attempt_regression" and item["failure"] for item in results)
    known_limitations = 1
    print(f"Character Repair Red-Team: {correct}/{len(results)} correct")
    print(json.dumps({
        "total": len(results),
        "correct": correct,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "scope_failures": scope_failures,
        "serialization_failures": serialization_failures,
        "security_failures": security_failures,
        "recommendation_failures": recommendation_failures,
        "known_limitations": ["H2 extractive canon_basis support contract"],
    }, ensure_ascii=False, indent=2))
    for item in results:
        if item["failure"]:
            print(f"FAIL {item['name']}: actual={item['actual']}")
    return 0 if correct == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
