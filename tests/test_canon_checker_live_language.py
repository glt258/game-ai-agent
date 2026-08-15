from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agents import (
    CanonChecker,
    CanonFindingCode,
    CharacterDesignRequest,
    CharacterDraft,
)


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _good_draft() -> CharacterDraft:
    payload = json.loads(
        (FIXTURES / "canon_checker_good.json").read_text(encoding="utf-8")
    )
    return CharacterDraft.from_mapping(payload["draft"])


def _good_request() -> CharacterDesignRequest:
    payload = json.loads(
        (FIXTURES / "canon_checker_good.json").read_text(encoding="utf-8")
    )
    return CharacterDesignRequest(**payload["request"])


def _codes(draft: CharacterDraft):
    return {finding.code for finding in CanonChecker().check(draft).findings}


@pytest.mark.parametrize(
    "text",
    [
        "未新增秘密政府组织。",
        "未引入任何秘密政府监管机构。",
        "没有建立秘密监管机构。",
    ],
)
def test_live_negated_forbidden_claims_are_not_forbidden(text: str):
    draft = replace(_good_draft(), background=text)
    assert not {
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    } & _codes(draft)


def test_live_negated_forbidden_claim_is_safe_with_request_constraints():
    payload = json.loads(
        (FIXTURES / "canon_checker_good.json").read_text(encoding="utf-8")
    )
    draft = replace(
        CharacterDraft.from_mapping(payload["draft"]),
        constraint_notes=("未新增秘密政府组织。",),
    )
    request = CharacterDesignRequest(**payload["request"])
    report = CanonChecker().check(draft, request=request)
    assert not {
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    } & {item.code for item in report.findings}


@pytest.mark.parametrize(
    "text",
    [
        "无秘密政府组织元素。",
        "未使用任何秘密政府组织。",
        "不包含秘密监管机构。",
        "未采用秘密行政机关作为角色背景。",
        "不涉及秘密政府监管体系。",
        "没有秘密监管机构相关设定。",
    ],
)
def test_live_absence_and_non_use_denials_are_safe(text: str):
    report = CanonChecker().check(
        replace(_good_draft(), constraint_notes=(text,)),
        request=_good_request(),
    )
    codes = {item.code for item in report.findings}
    assert not {
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    } & codes


@pytest.mark.parametrize(
    "text",
    [
        "包含秘密政府组织元素。",
        "使用秘密监管机构统一管理全城能力者。",
        "采用不公开行政机关作为角色背景。",
        "存在一个秘密政府监管机构。",
        "无公开登记的秘密监管机构。",
    ],
)
def test_live_positive_forbidden_absence_near_neighbors_still_fail(text: str):
    report = CanonChecker().check(
        replace(_good_draft(), constraint_notes=(text,)),
        request=_good_request(),
    )
    codes = {item.code for item in report.findings}
    assert codes & {
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    }


def test_live_mixed_absence_clause_does_not_hide_positive_secret_entity():
    report = CanonChecker().check(
        replace(
            _good_draft(),
            constraint_notes=(
                "角色不使用秘密政府组织设定，但其真实身份隶属于一个不公开的监管机构。",
            ),
        ),
        request=_good_request(),
    )
    codes = {item.code for item in report.findings}
    assert codes & {
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    }


@pytest.mark.parametrize(
    "text",
    [
        "她新增了一个秘密政府组织。",
        "她没有公开身份，实际上新增了秘密政府监管机构。",
        "不对外公开的行政机构统一监管全市能力者。",
        "她任职于一个未向公众披露的行政机构，该机构统一管理全市能力者事务。",
    ],
)
def test_live_forbidden_positive_near_neighbors_still_fail(text: str):
    payload = json.loads(
        (FIXTURES / "canon_checker_good.json").read_text(encoding="utf-8")
    )
    draft = replace(CharacterDraft.from_mapping(payload["draft"]), background=text)
    report = CanonChecker().check(draft, request=CharacterDesignRequest(**payload["request"]))
    codes = {item.code for item in report.findings}
    assert codes & {
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    }


@pytest.mark.parametrize(
    "text",
    [
        "她不了解受限项目数据（lore_011）。",
        "她不能默认读取其他课题组资料（lore_009）。",
        "相关记录见 lore_025，角色对此无访问权。",
        "她无权访问 lore_011。",
    ],
)
def test_live_negated_knowledge_claims_are_not_overreach(text: str):
    draft = replace(_good_draft(), knowledge_scope=text)
    assert CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH not in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "她了解 lore_011 的全部受限数据。",
        "她可以默认读取其他课题组资料（lore_009）。",
        "她对 lore_025 拥有完整访问权。",
    ],
)
def test_live_positive_knowledge_claims_still_fail(text: str):
    draft = replace(_good_draft(), knowledge_scope=text)
    assert CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH in _codes(draft)


def test_live_mixed_knowledge_polarity_is_clause_local():
    draft = replace(
        _good_draft(),
        knowledge_scope="她不了解 lore_011，但可以读取 lore_025 的内部样本。",
    )
    assert CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "拟议关系：与余弦存在一次访谈往来。",
        "拟议关系：与纪衡进行一次工作交接。",
        "拟议：在一次公开活动中与唐栖见过面。",
        "拟议：在临洲大学行为与能力研究中心承担一项新的资料整理工作。",
    ],
)
def test_live_existing_canon_targets_can_be_relation_or_assignment(text: str):
    draft = replace(_good_draft(), proposed_new_content=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL not in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "新增角色：余弦。",
        "新增组织：临洲大学行为与能力研究中心。",
        "新事件：南栈演出散场事故后续协调委托。",
    ],
)
def test_live_existing_canon_entities_still_cannot_be_proposed_as_new(text: str):
    draft = replace(_good_draft(), new_design_elements=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "未新增任何不对外公开的秘密监管机构。",
        "并未建立新的秘密行政机关。",
        "没有创建任何统一管理全市能力者的秘密行政部门。",
        "从未设立过一个负责全城能力事务的秘密机构。",
        "她曾考虑创建秘密监管机构，但最终并未建立任何此类组织。",
    ],
)
def test_live_complex_forbidden_denial_is_action_local(text: str):
    report = CanonChecker().check(
        replace(_good_draft(), background=text),
        request=_good_request(),
    )
    codes = {item.code for item in report.findings}
    assert not {
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
    } & codes


@pytest.mark.parametrize(
    "text",
    [
        "新增了一个不对外公开的秘密监管机构。",
        "创建未向公众披露的监管机构统一管理全城能力者。",
        "设立一个秘密管理局统一负责全市能力事务。",
        "她没有公开头衔，但创建了秘密监管机构。",
        "她所在的机构不对外公开，并统一监管全市能力者。",
    ],
)
def test_live_complex_forbidden_creation_still_fails(text: str):
    report = CanonChecker().check(
        replace(_good_draft(), background=text),
        request=_good_request(),
    )
    codes = {item.code for item in report.findings}
    assert codes & {
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.WORLD_RULE_VIOLATION,
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
    }


def test_live_mixed_forbidden_clauses_do_not_share_negation():
    report = CanonChecker().check(
        replace(
            _good_draft(),
            background="她没有新增普通行政部门，但创建了一个秘密监管机构。",
        ),
        request=_good_request(),
    )
    assert report.status == "fail"


@pytest.mark.parametrize(
    "text",
    [
        "拟议：与余弦形成一次资料层面的工作往来。",
        "拟议：和纪衡进行一次工作交接。",
        "拟议：未来可能与唐栖在公开活动中产生一次短暂接触。",
        "拟议：负责向余弦提交一次去标识化记录。",
        "拟议：在回写与社会认知组承担一项新的资料校对工作。",
        "拟议：在临洲大学行为与能力研究中心参与新的非受限材料整理工作。",
        "未来可能采访余弦。",
    ],
)
def test_live_natural_existing_target_interactions_are_not_new_entities(text: str):
    draft = replace(_good_draft(), proposed_new_content=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL not in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "与余弦的关系为新增设计。",
        "与纪衡的一次工作交接为新增设计。",
        "与唐栖的短暂接触为拟议设计。",
        "与余弦的纵向随访关系为新增角色内容。",
        "在回写与社会认知组中的资料整理任务为新增设计。",
        "在临洲大学行为与能力研究中心中的个人工作安排为拟议内容。",
    ],
)
def test_live_proposal_head_ordering_allows_relations_and_assignments(text: str):
    draft = replace(_good_draft(), proposed_new_content=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL not in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "余弦为新增角色设计。",
        "回写与社会认知组为新增部门设计。",
        "南栈演出散场事故为新事件设计。",
    ],
)
def test_live_proposal_head_ordering_blocks_existing_entity_itself(text: str):
    draft = replace(_good_draft(), proposed_new_content=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL in _codes(draft)


@pytest.mark.parametrize(
    "text",
    [
        "新增角色：余弦。",
        "新设计：余弦。",
        "新增组织：临洲大学行为与能力研究中心。",
        "新部门：回写与社会认知组。",
        "新事件：南栈演出散场事故后续协调委托。",
    ],
)
def test_live_introduction_marker_keeps_existing_entity_blocked(text: str):
    draft = replace(_good_draft(), proposed_new_content=(text,))
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL in _codes(draft)


def test_live_relation_proposal_still_checks_proposal_presented_as_canon():
    draft = replace(
        _good_draft(),
        proposed_new_content=("拟议：未来可能与余弦产生一次工作接触。",),
        background="她长期与余弦共同工作多年。",
    )
    report = CanonChecker().check(draft)
    assert CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL not in {
        item.code for item in report.findings
    }
    assert CanonFindingCode.PROPOSAL_PRESENTED_AS_CANON in {
        item.code for item in report.findings
    }
