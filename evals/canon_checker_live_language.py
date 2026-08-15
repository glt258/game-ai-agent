"""Minimal offline regressions derived from the Hermes Live acceptance report."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from agents import (
    CanonCheckStatus,
    CanonFindingCode,
    CharacterDesignRequest,
    CharacterDraft,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "canon_checker_good.json"


@dataclass(frozen=True)
class LiveLanguageCase:
    case_id: str
    draft: CharacterDraft
    request: CharacterDesignRequest
    expected_status: CanonCheckStatus
    expected_codes: frozenset[CanonFindingCode] = frozenset()
    forbidden_codes: frozenset[CanonFindingCode] = frozenset()


def live_language_cases() -> tuple[LiveLanguageCase, ...]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base = CharacterDraft.from_mapping(payload["draft"])
    request = CharacterDesignRequest(**payload["request"])
    fail_codes = frozenset(
        {
            CanonFindingCode.FORBIDDEN_PATTERN,
            CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
            CanonFindingCode.WORLD_RULE_VIOLATION,
        }
    )
    knowledge_fail = frozenset({CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH})
    proposal_fail = frozenset({CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL})

    cases = [
        ("negated_forbidden_added", "background", "未新增秘密政府组织。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("negated_forbidden_introduced", "background", "未引入任何秘密政府监管机构。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("negated_forbidden_established", "background", "没有建立秘密监管机构。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("positive_forbidden_added", "background", "她新增了一个秘密政府组织。", CanonCheckStatus.FAIL, fail_codes, frozenset()),
        ("positive_secret_authority", "background", "不对外公开的行政机构统一监管全市能力者。", CanonCheckStatus.FAIL, frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}), frozenset()),
        ("positive_secret_authority_posted", "background", "她任职于一个未向公众披露的行政机构，该机构统一管理全市能力者事务。", CanonCheckStatus.FAIL, frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}), frozenset()),
        ("knowledge_negated_preposed", "knowledge_scope", "她不了解受限项目数据（lore_011）。", CanonCheckStatus.PASS, frozenset(), knowledge_fail),
        ("knowledge_negated_default_read", "knowledge_scope", "她不能默认读取其他课题组资料（lore_009）。", CanonCheckStatus.PASS, frozenset(), knowledge_fail),
        ("knowledge_negated_postposed", "knowledge_scope", "相关记录见 lore_025，角色对此无访问权。", CanonCheckStatus.PASS, frozenset(), knowledge_fail),
        ("knowledge_positive_read", "knowledge_scope", "她可以默认读取其他课题组资料（lore_009）。", CanonCheckStatus.FAIL, knowledge_fail, frozenset()),
        ("knowledge_positive_access", "knowledge_scope", "她对 lore_025 拥有完整访问权。", CanonCheckStatus.FAIL, knowledge_fail, frozenset()),
        ("knowledge_mixed_polarity", "knowledge_scope", "她不了解 lore_011，但可以读取 lore_025 的内部样本。", CanonCheckStatus.FAIL, knowledge_fail, frozenset()),
        ("relation_interview", "proposed_new_content", "拟议关系：与余弦存在一次访谈往来。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("relation_handoff", "proposed_new_content", "拟议关系：与纪衡进行一次工作交接。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("relation_meeting", "proposed_new_content", "拟议：在一次公开活动中与唐栖见过面。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("existing_membership", "proposed_new_content", "拟议：在临洲大学行为与能力研究中心承担一项新的资料整理工作。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("existing_character_as_new", "new_design_elements", "新增角色：余弦。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("existing_group_as_new", "new_design_elements", "新增组织：临洲大学行为与能力研究中心。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("existing_case_as_new", "new_design_elements", "新事件：南栈演出散场事故后续协调委托。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
    ]
    return tuple(
        LiveLanguageCase(
            case_id,
            replace(
                base,
                **{
                    field: (text,)
                    if field in {"constraint_notes", "new_design_elements", "proposed_new_content"}
                    else text
                },
            ),
            request,
            expected_status,
            expected_codes,
            forbidden_codes,
        )
        for case_id, field, text, expected_status, expected_codes, forbidden_codes in cases
    )
