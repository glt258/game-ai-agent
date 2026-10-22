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
    fail_codes = frozenset({CanonFindingCode.FORBIDDEN_PATTERN})
    hard_fail = frozenset({CanonFindingCode.HARD_CONSTRAINT_VIOLATION})
    knowledge_fail = frozenset({CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH})
    proposal_fail = frozenset({CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL})
    literal_request = replace(request, forbidden_elements=("秘密行政机构",))
    generic_request = replace(request, forbidden_elements=("秘密政府组织",))

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
        ("complex_denial_secret_property", "background", "未新增任何不对外公开的秘密监管机构。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("complex_denial_admin", "background", "并未建立新的秘密行政机关。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("complex_denial_city_scope", "background", "没有创建任何统一管理全市能力者的秘密行政部门。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("complex_denial_ever", "background", "从未设立过一个负责全城能力事务的秘密机构。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("complex_denial_mixed", "background", "她曾考虑创建秘密监管机构，但最终并未建立任何此类组织。", CanonCheckStatus.PASS, frozenset(), fail_codes),
        ("complex_creation_secret_property", "background", "新增了一个不对外公开的秘密监管机构。", CanonCheckStatus.FAIL, fail_codes, frozenset()),
        ("complex_creation_disclosed", "background", "创建未向公众披露的监管机构统一管理全城能力者。", CanonCheckStatus.FAIL, fail_codes, frozenset()),
        ("complex_creation_management", "background", "设立一个秘密管理局统一负责全市能力事务。", CanonCheckStatus.FAIL, fail_codes, frozenset()),
        ("complex_creation_after_negation", "background", "她没有公开头衔，但创建了秘密监管机构。", CanonCheckStatus.FAIL, fail_codes, frozenset()),
        ("complex_property_without_action", "background", "她所在的机构不对外公开，并统一监管全市能力者。", CanonCheckStatus.FAIL, frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}), frozenset()),
        ("natural_interaction_interview", "proposed_new_content", "拟议：与余弦形成一次资料层面的工作往来。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_interaction_handoff", "proposed_new_content", "拟议：和纪衡进行一次工作交接。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_interaction_contact", "proposed_new_content", "拟议：未来可能与唐栖在公开活动中产生一次短暂接触。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_interaction_submission", "proposed_new_content", "拟议：负责向余弦提交一次去标识化记录。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_division_assignment", "proposed_new_content", "拟议：在回写与社会认知组承担一项新的资料校对工作。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_faction_assignment", "proposed_new_content", "拟议：在临洲大学行为与能力研究中心参与新的非受限材料整理工作。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("natural_interview_without_preposition", "proposed_new_content", "未来可能采访余弦。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("marker_existing_character", "proposed_new_content", "新设计：余弦。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("marker_existing_division", "proposed_new_content", "新部门：回写与社会认知组。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("absence_element", "constraint_notes", "无秘密政府组织元素。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("absence_non_use", "constraint_notes", "未使用任何秘密政府组织。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("absence_contains", "constraint_notes", "不包含秘密监管机构。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("absence_adoption", "constraint_notes", "未采用秘密行政机关作为角色背景。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("absence_scope", "constraint_notes", "不涉及秘密政府监管体系。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("absence_related_setting", "constraint_notes", "没有秘密监管机构相关设定。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("positive_absence_neighbor", "background", "包含秘密政府组织元素。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("positive_usage_neighbor", "background", "使用秘密监管机构统一管理全城能力者。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("positive_publicity_neighbor", "background", "采用不公开行政机关作为角色背景。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("positive_existing_secret_entity", "background", "存在一个秘密政府监管机构。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("positive_negative_property", "background", "无公开登记的秘密监管机构。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("mixed_absence_positive_entity", "background", "角色不使用秘密政府组织设定，但其真实身份隶属于一个不公开的监管机构。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("ordered_relation_design", "proposed_new_content", "与余弦的关系为新增设计。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_handoff_design", "proposed_new_content", "与纪衡的一次工作交接为新增设计。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_contact_proposal", "proposed_new_content", "与唐栖的短暂接触为拟议设计。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_followup_content", "proposed_new_content", "与余弦的纵向随访关系为新增角色内容。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_division_assignment", "proposed_new_content", "在回写与社会认知组中的资料整理任务为新增设计。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_faction_assignment", "proposed_new_content", "在临洲大学行为与能力研究中心中的个人工作安排为拟议内容。", CanonCheckStatus.PASS, frozenset(), proposal_fail),
        ("ordered_existing_character_block", "proposed_new_content", "余弦为新增角色设计。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("ordered_existing_division_block", "proposed_new_content", "回写与社会认知组为新增部门设计。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("ordered_existing_event_block", "proposed_new_content", "南栈演出散场事故为新事件设计。", CanonCheckStatus.FAIL, proposal_fail, frozenset()),
        ("compound_absence_live_case", "constraint_notes", "无秘密政府机构或秘密行政机构要素。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_absence_three_items", "constraint_notes", "无秘密政府组织、秘密监管机构或隐藏行政机关相关设定。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_non_inclusion", "constraint_notes", "不包含秘密政府组织或秘密监管体系。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_non_use", "constraint_notes", "未使用秘密行政机关与隐藏监管部门设定。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_adoption", "constraint_notes", "未采用秘密监管机构、秘密行政组织以及全城统一监管机关作为角色背景。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_or_else", "constraint_notes", "不涉及秘密政府机构或秘密能力监管组织。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_deng", "constraint_notes", "没有秘密政府组织、秘密行政机关等元素。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_any", "constraint_notes", "无任何秘密政府组织或秘密监管部门内容。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_connector_or", "constraint_notes", "无秘密政府组织或者秘密行政机关要素。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_connector_and", "constraint_notes", "无秘密政府组织和秘密监管部门内容。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_connector_jian", "constraint_notes", "无秘密政府组织及秘密行政机关设定。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_connector_slash", "constraint_notes", "无秘密政府组织/秘密行政机构要素。", CanonCheckStatus.PASS, frozenset(), hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION})),
        ("compound_positive_or", "background", "包含秘密政府机构或秘密行政机构要素。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_positive_and", "background", "使用秘密政府组织和秘密监管部门作为角色背景。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_positive_assignment", "background", "采用秘密行政机关与全城监管机构设定。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_positive_membership", "background", "角色隶属于秘密政府机构或秘密行政机关。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_positive_existing", "background", "存在秘密政府组织与隐藏监管部门。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_positive_disclosed", "background", "存在不对外公开的秘密政府机构或秘密行政机关。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_negative_property", "background", "无公开登记的秘密监管机构或秘密行政机关统一负责全城能力事务。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_mixed_identity", "background", "无秘密政府组织或秘密行政机构元素，但角色真实身份隶属于一个不公开的监管机构。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_mixed_creation", "background", "不包含秘密监管机构设定，但设立一个未公开行政办公室统一管理全城能力者。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
        ("compound_mixed_positive", "background", "无秘密政府机构或秘密行政机构，但存在秘密监管机构。", CanonCheckStatus.FAIL, hard_fail, frozenset()),
    ]
    base_cases = tuple(
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
    path_consistency_cases = (
        LiveLanguageCase(
            "hermes_exact_absence_1",
            replace(base, constraint_notes=("无秘密政府机构或秘密行政机构要素",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "hermes_exact_absence_2",
            replace(base, constraint_notes=("未使用秘密政府组织或秘密行政机构",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "hermes_exact_absence_3",
            replace(base, constraint_notes=("未采用秘密监管机构与秘密政府组织作为背景",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "hermes_exact_absence_4",
            replace(base, constraint_notes=("不涉及秘密政府机构或秘密行政机构",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "literal_path_negative",
            replace(base, constraint_notes=("无秘密政府机构或秘密行政机构要素",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "generic_path_negative",
            replace(base, constraint_notes=("无秘密政府机构或秘密行政机构要素",)),
            generic_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "literal_path_positive",
            replace(base, background="存在秘密政府机构或秘密行政机构"),
            literal_request,
            CanonCheckStatus.FAIL,
            expected_codes=hard_fail,
        ),
        LiveLanguageCase(
            "generic_path_positive",
            replace(base, background="存在秘密政府机构或秘密行政机构"),
            generic_request,
            CanonCheckStatus.FAIL,
            expected_codes=hard_fail,
        ),
        LiveLanguageCase(
            "three_target_negative_shared_scope",
            replace(base, constraint_notes=("无秘密政府组织、秘密行政机构或隐藏监管部门相关设定",)),
            literal_request,
            CanonCheckStatus.PASS,
            forbidden_codes=hard_fail | fail_codes | frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}),
        ),
        LiveLanguageCase(
            "mixed_clause_shared_scope_boundary",
            replace(base, background="无秘密政府机构或秘密行政机构，但存在秘密监管机构"),
            literal_request,
            CanonCheckStatus.FAIL,
            expected_codes=hard_fail,
        ),
    )
    return base_cases + path_consistency_cases
