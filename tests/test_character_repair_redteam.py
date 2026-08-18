from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from agents import (
    CanonCheckStatus,
    CanonChecker,
    CharacterAuthoringWorkflow,
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
    HardConstraintDomain,
    ModelTurn,
    RepairResultStatus,
    ScriptedAgentModel,
)


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _case(name: str):
    payload = json.loads((FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8"))
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(**payload["request"])


def _candidate_model(draft: CharacterDraft, **changes: object) -> ScriptedAgentModel:
    payload = draft.to_dict()
    payload.update(changes)
    return ScriptedAgentModel([ModelTurn(text=json.dumps(payload, ensure_ascii=False))])


def _repair(draft: CharacterDraft, request: CharacterDesignRequest, model) :
    checker = CanonChecker()
    initial = checker.check(draft, request=request)
    agent = CharacterRepairAgent(model, checker=checker)
    return initial, agent.repair(agent.prepare_request(request, draft, initial))


def test_knowledge_hard_constraint_is_classified_and_preserved():
    draft, base_request = _case("good")
    request = replace(base_request, hard_constraints=("必须掌握全城能力者档案",), request_id="rt_knowledge_hard")
    draft = replace(draft, knowledge_scope="可访问全城所有能力者档案")
    requirements = CharacterRepairAgent(DeterministicCharacterRepairModel()).prepare_request(
        request, draft, CanonChecker().check(draft, request=request)
    ).scope
    assert requirements is not None
    assert HardConstraintDomain.KNOWLEDGE_SCOPE.value == "knowledge_scope"
    assert "knowledge_scope" not in requirements.frozen_fields

    initial, result = _repair(draft, request, DeterministicCharacterRepairModel())
    assert initial.status == CanonCheckStatus.FAIL
    assert result.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION
    assert "knowledge_scope" in (result.error or "")
    assert result.recommended_draft == draft


def test_repair_rejects_candidate_that_keeps_unsupported_age_history():
    draft, base_request = _case("bad")
    request = replace(
        base_request,
        brief="设计一个年龄保持未知、且不新增秘密政府组织的辅助角色。",
        hard_constraints=("年龄保持未知", "不得成为事件核心负责人"),
    )
    draft = replace(
        draft,
        age=None,
        age_range=None,
        background="她从十几岁起参与社区活动，并秘密领导未公开能力监管部门。",
    )
    initial, result = _repair(
        draft,
        request,
        _candidate_model(draft, background="她从十几岁起参与普通社区活动。"),
    )
    assert initial.status == CanonCheckStatus.FAIL
    assert result.status == RepairResultStatus.REPAIR_SCOPE_VIOLATION
    assert "age-information" in (result.error or "")
    assert result.recommended_draft == draft


def test_authority_hard_constraint_cannot_be_removed():
    draft, base_request = _case("good")
    request = replace(base_request, hard_constraints=("必须拥有跨部门统一指挥权",), request_id="rt_authority_hard")
    draft = replace(draft, occupation="跨部门统一指挥警察、消防和急救", social_role="拥有统一调度权")
    candidate = _candidate_model(draft, occupation="普通协调员", social_role="只负责信息整理")
    _initial, result = _repair(draft, request, candidate)
    assert result.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION
    assert result.recommended_draft == draft


def test_story_role_hard_constraint_cannot_be_removed():
    draft, base_request = _case("shenzhao")
    request = replace(base_request, hard_constraints=("必须是南栈事故核心负责人",), request_id="rt_story_role_hard")
    draft = replace(draft, story_hook="她是南栈事故核心负责人，所有关键决定由她拍板。")
    _initial, result = _repair(draft, request, DeterministicCharacterRepairModel())
    assert result.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION
    assert result.recommended_draft == draft


def test_relationship_hard_constraint_cannot_be_deleted():
    draft, base_request = _case("shenzhao")
    request = replace(base_request, hard_constraints=("必须与唐栖为师徒关系",), request_id="rt_relationship_hard")
    draft = CharacterDraft.from_mapping(
        {**draft.to_dict(), "relationships": [{"target_id": "char_launch_001", "description": "唐栖是她的导师，二人为师徒关系", "status": "proposed"}]}
    )
    _initial, result = _repair(draft, request, _candidate_model(draft, relationships=[]))
    assert result.status == RepairResultStatus.REPAIR_HARD_CONSTRAINT_VIOLATION
    assert result.recommended_draft == draft
    assert "relationships" in result.changed_fields


def test_relationships_serialize_to_json_and_roundtrip_without_mutation():
    draft, _request = _case("good")
    draft = CharacterDraft.from_mapping(
        {**draft.to_dict(), "relationships": [{"target_id": "char_launch_001", "description": "拟议协作", "status": "proposed"}]}
    )
    before = copy.deepcopy(draft.to_dict())
    serialized = draft.to_dict()
    encoded = json.dumps(serialized, ensure_ascii=False)
    roundtrip = CharacterDraft.from_mapping(json.loads(encoded))
    assert roundtrip == draft
    assert draft.to_dict() == before
    with pytest.raises(TypeError):
        draft.relationships[0]["status"] = "canon_backed"


def test_repair_with_relationships_and_json_result_does_not_crash():
    draft, request = _case("shenzhao")
    draft = replace(
        draft,
        relationships=({"target_id": "char_launch_001", "description": "拟议协作", "status": "proposed"},),
    )
    checker = CanonChecker()
    result = CharacterRepairAgent(DeterministicCharacterRepairModel(), checker=checker).repair(
        CharacterRepairAgent(DeterministicCharacterRepairModel(), checker=checker).prepare_request(
            request, draft, checker.check(draft, request=request)
        )
    )
    json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.final_check.status == CanonCheckStatus.PASS


@pytest.mark.parametrize(
    "text",
    [
        "她没有正式指挥头衔，但任何关键行动都必须经过她确认，警察、消防、急救最终都按她的决定行动。",
        "所有关键决定均须经过她确认。",
        "警察、消防、急救最终按她决定行动。",
        "各部门虽然独立，但关键行动必须取得她同意。",
    ],
)
def test_hidden_supreme_authority_is_detected(text):
    draft, request = _case("shenzhao")
    report = CanonChecker().check(replace(draft, background=text), request=request)
    codes = {finding.code.value for finding in report.findings}
    assert report.status == CanonCheckStatus.FAIL
    assert {"AUTHORITY_OVERREACH", "STORY_ROLE_OVERREACH"} & codes


@pytest.mark.parametrize(
    "text",
    [
        "她不指挥警察、消防或急救，只负责汇总各部门信息。",
        "她没有正式指挥头衔，但只协调警方、消防和急救的信息交接。",
    ],
)
def test_coordination_without_command_remains_valid(text):
    draft, request = _case("good")
    report = CanonChecker().check(replace(draft, background=text), request=request)
    assert not any(item.code.value == "AUTHORITY_OVERREACH" for item in report.findings)


def test_internal_materials_are_sensitive_but_public_materials_are_not():
    draft, request = _case("good")
    checker = CanonChecker()
    restricted = checker.check(replace(draft, knowledge_scope="市里每位能力者的内部资料她都可以调阅"), request=request)
    public = checker.check(replace(draft, knowledge_scope="她可以阅读项目公开资料"), request=request)
    assert any(item.code.value == "KNOWLEDGE_SCOPE_OVERREACH" for item in restricted.findings)
    assert not any(item.code.value == "KNOWLEDGE_SCOPE_OVERREACH" for item in public.findings)


def test_hidden_authority_triggers_repair_workflow():
    draft, request = _case("good")
    draft = replace(draft, background="所有关键决定均须经过她确认。")

    class StaticGenerator:
        def generate(self, _request):
            return CharacterGenerationResult(draft, (), CharacterGenerationAudit(draft.draft_id, 0, (), ()))

    model = DeterministicCharacterRepairModel()
    checker = CanonChecker()
    result = CharacterAuthoringWorkflow(
        StaticGenerator(), CharacterRepairAgent(model, checker=checker), checker=checker
    ).run(request)
    assert result.initial_check.status == CanonCheckStatus.FAIL
    assert model.call_count == 1
    assert result.repair_result.repair_attempt == 1
