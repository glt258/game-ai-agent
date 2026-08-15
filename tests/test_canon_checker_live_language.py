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
