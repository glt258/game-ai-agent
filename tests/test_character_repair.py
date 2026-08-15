from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from agents import (
    CanonCheckStatus,
    CanonChecker,
    CharacterAuthoringResult,
    CharacterAuthoringWorkflow,
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
    ModelTurn,
    RepairResultStatus,
    ScriptedAgentModel,
    ToolCall,
)


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _case(name: str) -> tuple[CharacterDraft, CharacterDesignRequest]:
    payload = json.loads((FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8"))
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(**payload["request"])


def _repair(name: str, *, mode: str = "auto"):
    draft, request = _case(name)
    checker = CanonChecker()
    model = DeterministicCharacterRepairModel(mode=mode)
    agent = CharacterRepairAgent(model, checker=checker)
    report = checker.check(draft, request=request)
    result = agent.repair(agent.prepare_request(request, draft, report))
    return draft, request, model, result


def test_pass_draft_skips_repair_model():
    draft, request = _case("good")
    checker = CanonChecker()
    model = DeterministicCharacterRepairModel()
    result = CharacterRepairAgent(model, checker=checker).repair(
        CharacterRepairAgent(model, checker=checker).prepare_request(
            request, draft, checker.check(draft, request=request)
        )
    )
    assert result.status == RepairResultStatus.NO_REPAIR_NEEDED
    assert not result.repair_attempted
    assert model.call_count == 0


def test_shenzhao_repair_is_minimal_and_reaches_pass():
    draft, request, model, result = _repair("shenzhao")
    assert result.initial_check.status == CanonCheckStatus.WARN
    assert result.final_check.status == CanonCheckStatus.PASS
    assert result.status == RepairResultStatus.REPAIRED_PASS
    assert model.call_count == 1
    assert result.changed_fields == ("background", "story_hook")
    assert result.repaired_draft is not None
    assert result.repaired_draft.name == draft.name
    assert result.repaired_draft.age == draft.age
    assert result.repaired_draft.faction_id == draft.faction_id
    assert result.repaired_draft.personality == draft.personality
    assert "南栈" in result.repaired_draft.background


def test_bad_draft_can_improve_without_being_called_success():
    _draft, _request, model, result = _repair("bad")
    assert model.call_count == 1
    assert result.status == RepairResultStatus.IMPROVED_BUT_FAILED
    assert result.final_check.status == CanonCheckStatus.FAIL
    assert result.final_check.summary.errors < result.initial_check.summary.errors
    assert result.recommended_draft == result.repaired_draft
    assert any(item.field_path == "age" for item in result.final_check.findings)


def test_repair_is_one_attempt_and_regression_keeps_original():
    draft, _request, model, result = _repair("shenzhao", mode="regression")
    assert model.call_count == 1
    assert result.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION
    assert result.recommended_draft == draft
    assert result.repaired_draft is not None
    assert "age" in result.changed_fields


def test_scope_violation_rejects_identity_change():
    draft, _request, model, result = _repair("shenzhao", mode="scope_violation")
    assert model.call_count == 1
    assert result.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION
    assert result.recommended_draft.name == draft.name


def test_fake_source_is_rejected_at_repair_boundary():
    _draft, _request, _model, result = _repair("shenzhao", mode="fake_source")
    assert result.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION
    assert "allowlist" in (result.error or "")


def test_repair_prompt_has_no_tools_and_is_bounded():
    _draft, _request, model, result = _repair("shenzhao")
    assert result.repair_attempted
    prompt = model.prompts[0]
    assert prompt.available_tools == ()
    assert prompt.authoring_payload is not None
    assert "current_draft" in prompt.authoring_payload
    assert "canon_check_report" in prompt.authoring_payload
    assert "allowed_evidence" in prompt.authoring_payload
    assert "messages" not in prompt.authoring_payload


def test_tool_call_is_rejected_without_execution():
    draft, request = _case("shenzhao")
    checker = CanonChecker()
    model = DeterministicCharacterRepairModel(mode="tool_call")
    agent = CharacterRepairAgent(model, checker=checker)
    report = checker.check(draft, request=request)
    result = agent.repair(agent.prepare_request(request, draft, report))
    assert result.status == RepairResultStatus.REPAIR_MODEL_FAILED
    assert "tool call" in (result.error or "")
    assert model.call_count == 1


@pytest.mark.parametrize(
    "payload_mode",
    ["wrapper", "malformed"],
)
def test_wrong_wrapper_or_malformed_json_is_rejected(payload_mode):
    draft, request = _case("shenzhao")
    checker = CanonChecker()
    payload = draft.to_dict()
    if payload_mode == "wrapper":
        turn = ModelTurn(text=json.dumps({"repaired_draft": payload}, ensure_ascii=False))
    else:
        turn = ModelTurn(text="{not-json")
    model = ScriptedAgentModel([turn])
    result = CharacterRepairAgent(model, checker=checker).repair(
        CharacterRepairAgent(model, checker=checker).prepare_request(
            request, draft, checker.check(draft, request=request)
        )
    )
    assert result.status == RepairResultStatus.REPAIR_MODEL_FAILED
    assert result.recommended_draft == draft


def test_request_draft_and_checker_are_not_mutated():
    draft, request = _case("shenzhao")
    before_draft = copy.deepcopy(draft.to_dict())
    before_request = copy.deepcopy(request.to_dict())
    checker = CanonChecker()
    report = checker.check(draft, request=request)
    before_report = copy.deepcopy(report.to_dict())
    CharacterRepairAgent(DeterministicCharacterRepairModel(), checker=checker).repair(
        CharacterRepairAgent(DeterministicCharacterRepairModel(), checker=checker).prepare_request(request, draft, report)
    )
    assert draft.to_dict() == before_draft
    assert request.to_dict() == before_request
    assert report.to_dict() == before_report


class _StaticGenerationAgent:
    def __init__(self, draft: CharacterDraft):
        self.draft = draft

    def generate(self, _request):
        return CharacterGenerationResult(
            self.draft,
            (),
            CharacterGenerationAudit(self.draft.draft_id, 0, (), ()),
        )


def test_authoring_workflow_rechecks_and_selects_repaired_draft():
    draft, request = _case("shenzhao")
    checker = CanonChecker()
    repair_model = DeterministicCharacterRepairModel()
    result = CharacterAuthoringWorkflow(
        _StaticGenerationAgent(draft),
        CharacterRepairAgent(repair_model, checker=checker),
        checker=checker,
    ).run(request)
    assert isinstance(result, CharacterAuthoringResult)
    assert result.initial_check.status == CanonCheckStatus.WARN
    assert result.final_check.status == CanonCheckStatus.PASS
    assert result.final_draft == result.repair_result.repaired_draft
    assert result.repair_result.repair_attempt == 1


def test_impossible_brief_stays_fail_and_does_not_change_age():
    draft, _request = _case("bad")
    request = replace(
        _request,
        request_id="impossible_repair_001",
        hard_constraints=("17岁", "必须担任公共安全联席体系最高负责人", "必须掌握全城能力者档案"),
    )
    checker = CanonChecker()
    initial = checker.check(draft, request=request)
    model = DeterministicCharacterRepairModel()
    result = CharacterRepairAgent(model, checker=checker).repair(
        CharacterRepairAgent(model, checker=checker).prepare_request(request, draft, initial)
    )
    assert result.final_check.status == CanonCheckStatus.FAIL
    assert result.recommended_draft == draft
    assert result.repaired_draft is not None
    assert result.repaired_draft.age == 17
    assert result.repair_attempted
