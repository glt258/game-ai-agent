from __future__ import annotations

import json

import pytest

from agents import (
    AgentExecutionError,
    CanonCheckStatus,
    CanonChecker,
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAgent,
    ModelTurn,
    ScriptedAgentModel,
    ToolCall,
    age_must_remain_unspecified,
)
from agents.character_generation import CHARACTER_SYSTEM_CONTRACT
from agents.character_benchmark import compute_metrics, run_benchmark


def _payload(
    draft_id: str,
    *,
    name: str = "林岑",
    age: int | None = None,
    age_range: str | None = None,
    faction_id: str | None = None,
    occupation: str = "独立社区工作者",
    social_role: str = "在本地生活网络中承担有限、可复核的实际事务",
    combat_role_profile: dict[str, object] | None = None,
    design_pitch: str = "以具体生活选择和有限能力边界建立可操作的角色身份。",
    background: str = "经历、训练和支持网络均为新设计，不宣称既有 Canon 身份。",
    story_hook: str = "先处理手边的具体问题，再决定是否把自己卷入更大的冲突。",
    ability_concept: str = "通过有限的现场判断和实际行动提供可理解的辅助作用，不能替代专业知识或正式权限。",
    knowledge_scope: str = "仅接触公开信息、本人亲历事项和被明确交付的工作内容。",
) -> dict:
    basis = []
    if faction_id:
        basis.append(
            {
                "source_id": faction_id,
                "supports": ["faction_id", "occupation"],
                "source_type": "faction",
            }
        )
    return {
        "draft_id": draft_id,
        "status": "draft",
        "name": name,
        "canonical_character_id": None,
        "age": age,
        "age_range": age_range,
        "gender": None,
        "faction_id": faction_id,
        "occupation": occupation,
        "social_role": social_role,
        "combat_role_profile": combat_role_profile or {"primary_role": "support", "secondary_roles": []},
        "design_pitch": design_pitch,
        "personality": ["有行动力", "观察细致"],
        "background": background,
        "story_hook": story_hook,
        "relationships": [],
        "ability_concept": ability_concept,
        "knowledge_scope": knowledge_scope,
        "canon_basis": basis,
        "new_design_elements": [
            "new_design:occupation: 职业表达为新设计。",
            "new_design:social_role: 社会角色表达为新设计。",
            "new_design:design_pitch: 角色概念为新设计。",
            "new_design:personality: 性格为新设计。",
            "new_design:background: 个人经历为新设计。",
            "new_design:story_hook: 叙事钩子为新设计。",
            "new_design:ability_concept: 能力表现为新设计。",
            "new_design:knowledge_scope: 知识边界表达为新设计。",
            "姓名、性格、日常习惯和个人经历均为新设计。",
        ],
        "open_questions": [],
        "constraint_notes": ["年龄呈现、社会位置与正式权限保持分离。"],
        "story_link": None,
        "proposed_new_content": [],
    }


def _generate(
    request: CharacterDesignRequest,
    payload: dict,
    *,
    faction_lookup: bool = False,
) -> CharacterDraft:
    turns = []
    if faction_lookup:
        turns.append(
            ModelTurn(
                tool_calls=(
                    ToolCall(
                        "faction-005",
                        "get_faction",
                        {"faction_id": "faction_005"},
                    ),
                )
            )
        )
    turns.extend(
        [
            ModelTurn(text="FINALIZE"),
            ModelTurn(
                text=json.dumps(payload, ensure_ascii=False),
                structured_output=payload,
            ),
        ]
    )
    return CharacterGenerationAgent(ScriptedAgentModel(turns)).generate(request).draft


def test_matrix_covers_the_six_required_social_positions():
    matrix = {
        "A": "年轻呈现、年龄不公开、独立从事大型活动安全现场协作",
        "B": "年轻呈现、年龄不公开、普通都市生活身份、不指定学校",
        "C": "成熟呈现、不以正式职业作为身份核心",
        "D": "成熟呈现、当前仍活跃、五星可操作、不是导师模板",
        "E": "不要给出具体年龄，年龄保持未知",
        "F": "年轻呈现、加入公共安全联席体系但权限有限",
    }
    assert tuple(matrix) == ("A", "B", "C", "D", "E", "F")


def test_exact_age_is_optional_and_explicit_ambiguity_survives_serialization():
    request = CharacterDesignRequest(
        "年轻呈现，年龄不公开；不要根据外表推断具体年龄。",
        request_id="diversity_age_ambiguous",
    )
    assert age_must_remain_unspecified(request)
    draft = _generate(request, _payload("draft_age_ambiguous"))
    assert draft.age is None and draft.age_range is None
    assert CharacterDraft.from_mapping(draft.to_dict()).to_dict()["age"] is None


def test_explicit_unspecified_age_rejects_model_invention():
    request = CharacterDesignRequest(
        "不要给出具体年龄，也不要给出年龄范围。",
        request_id="diversity_age_rejected",
    )
    with pytest.raises(AgentExecutionError, match="unspecified-age"):
        _generate(request, _payload("draft_age_invented", age=17, age_range="16-18"))


@pytest.mark.parametrize(
    "unsupported_claim",
    (
        "她17岁。",
        "她是未成年人。",
        "她从十几岁起就在店里帮忙。",
        "少年时期她曾经在店里帮忙。",
        "小时候她就会修理旧收音机。",
    ),
)
def test_unknown_age_rejects_unsupported_self_age_claims(unsupported_claim: str):
    request = CharacterDesignRequest(
        "年轻呈现，具体年龄未知；不要推断她的法律年龄或过去的年龄阶段。",
        request_id="diversity_age_history_rejected",
    )
    with pytest.raises(AgentExecutionError, match="age-preservation"):
        _generate(
            request,
            _payload("draft_age_history_invented", background=unsupported_claim),
        )


def test_unknown_age_allows_age_claim_about_another_person():
    request = CharacterDesignRequest(
        "年轻呈现，具体年龄未知；不要推断她的法律年龄或过去的年龄阶段。",
        request_id="diversity_age_other_person",
    )
    draft = _generate(
        request,
        _payload(
            "draft_age_other_person",
            background="她帮助一个十几岁的顾客修好旧收音机。",
        ),
    )
    assert "十几岁的顾客" in draft.background


def test_unknown_age_ignores_attributive_age_of_other_people():
    request = CharacterDesignRequest(
        "年轻呈现，具体年龄未知；不要推断她的法律年龄或过去的年龄阶段。",
        request_id="diversity_age_attributive_other_person",
    )
    draft = _generate(
        request,
        _payload(
            "draft_age_attributive_other_person",
            background="她是未成年人的监护人，也会照顾自己17岁的孩子。",
        ),
    )
    assert "监护人" in draft.background


def test_current_non_student_constraint_does_not_ban_past_school_history():
    request = CharacterDesignRequest(
        "年龄未知；她现在不在学校，也不是学生。过去是否上过学不需要特别解释。",
        request_id="diversity_current_non_student",
    )
    draft = _generate(
        request,
        _payload(
            "draft_current_non_student",
            background="她过去上过学，后来离开学校，现按项目接街区维护工作。",
        ),
    )
    assert "离开学校" in draft.background


def test_explicit_school_history_ambiguity_rejects_self_school_history():
    request = CharacterDesignRequest(
        "年龄未知；不要解释她过去是否上过学。",
        request_id="diversity_school_history_unknown",
    )
    with pytest.raises(AgentExecutionError, match="school_history"):
        _generate(
            request,
            _payload(
                "draft_school_history_invented",
                background="离开学校后，她开始接街区维护工作。",
            ),
        )


def test_unknown_age_preserves_youthful_presentation_without_age_claim():
    request = CharacterDesignRequest(
        "整体印象偏年轻，具体年龄未知。",
        request_id="diversity_youthful_presentation_only",
    )
    draft = _generate(
        request,
        _payload(
            "draft_youthful_presentation_only",
            design_pitch="她的轻快表达和敏锐观察让人觉得偏年轻，但年龄信息保持空缺。",
        ),
    )
    assert "偏年轻" in draft.design_pitch


def test_unknown_age_does_not_infer_age_from_duration_or_family():
    request = CharacterDesignRequest(
        "年龄保持未知，不推断法律年龄或历史年龄阶段。",
        request_id="diversity_age_duration_family",
    )
    draft = _generate(
        request,
        _payload(
            "draft_age_duration_family",
            background="她已经做这份工作很多年，也和家人一起照料孩子。",
        ),
    )
    assert draft.age is None and "很多年" in draft.background


def test_explicit_mature_adult_request_is_not_rejected():
    request = CharacterDesignRequest(
        "明显成熟的成年人，当前仍活跃，不要写成导师或退休高手。",
        request_id="diversity_explicit_mature_adult",
    )
    draft = _generate(
        request,
        _payload(
            "draft_explicit_mature_adult",
            social_role="明显成熟的成年人，当前仍主动接案并承担有限的现场工作。",
        ),
    )
    assert "成年人" in draft.social_role


def test_canon_supported_age_is_not_erased_by_ambiguity_guard():
    request = CharacterDesignRequest(
        "年龄通常保持未知，但以有效 Canon 明确记载的年龄为准。",
        request_id="diversity_canon_age",
    )
    payload = _payload(
        "draft_canon_age",
        age=27,
        age_range="27",
        faction_id="faction_005",
    )
    payload["canon_basis"] = [
        {
            "source_id": "faction_005",
            "supports": ["age", "age_range"],
            "source_type": "faction",
        }
    ]
    draft = _generate(request, payload, faction_lookup=True)
    assert draft.age == 27 and draft.age_range == "27"


def test_younger_presentation_does_not_force_school_identity():
    request = CharacterDesignRequest(
        "年轻呈现、年龄不公开；普通都市生活身份，不指定学校。",
        request_id="diversity_non_school",
    )
    draft = _generate(
        request,
        _payload(
            "draft_non_school",
            occupation="独立接单的街区设备维护员",
            social_role="与小店和居民按项目合作，生活安排围绕工作现场和邻里往来展开",
            design_pitch="吸引力来自记工具位置、临时修补和熟悉每家店的开门时间。",
        ),
    )
    social_text = " ".join((draft.occupation, draft.social_role, draft.background))
    assert not any(marker in social_text for marker in ("在校", "课堂", "老师", "作业", "社团"))
    assert "街区设备维护员" in draft.occupation


def test_dangerous_world_role_is_plausible_without_exact_age_or_elite_authority():
    request = CharacterDesignRequest(
        "年轻呈现但不明确具体年龄，已有大型活动安全现场协作经验；可操作但不是秘密天才或组织高层。",
        request_id="diversity_field_worker",
    )
    draft = _generate(
        request,
        _payload(
            "draft_field_worker",
            faction_id="faction_005",
            occupation="大型活动安全协作员",
            social_role="在受训成年人和专业部门的现场体系中负责信息传递、路线确认与撤离协作，不拥有指挥权",
            background="能力来自反复参加社区活动安全演练和现场观察；遇到超出训练范围的情况必须交给相应专业人员。",
            knowledge_scope="只接触公开安全规范和被明确交付的现场事项，不能读取内部案件档案。",
        ),
        faction_lookup=True,
    )
    report = CanonChecker().check(draft, request=request)
    assert report.status != CanonCheckStatus.FAIL
    assert draft.age is None
    assert "学生" not in draft.occupation
    assert "指挥" in draft.social_role and "不拥有" in draft.social_role
    assert "秘密" not in draft.background


def test_adult_without_career_identity_and_mature_playable_identity_are_valid():
    adult_request = CharacterDesignRequest(
        "成年呈现，但身份不建立在正式职业上；保留家庭、兴趣和临时生活安排。",
        request_id="diversity_non_career_adult",
    )
    adult = _generate(
        adult_request,
        _payload(
            "draft_non_career_adult",
            age_range=None,
            occupation="照料家人、接零散委托并维护个人兴趣的人",
            social_role="家庭成员、邻里熟人和临时项目合作者，不以正式职业定义自己",
        ),
    )
    assert "公司" not in adult.occupation
    assert "正式职业" in adult.social_role

    mature_request = CharacterDesignRequest(
        "成熟年龄呈现，当前仍活跃，五星可操作；不是导师、退休高手或家长型角色。",
        request_id="diversity_mature_playable",
    )
    mature = _generate(
        mature_request,
        _payload(
            "draft_mature_playable",
            age_range=None,
            occupation="城市夜间路线规划顾问",
            social_role="主动接案、亲自勘路并在危险现场保持行动能力的独立工作者",
            combat_role_profile={"primary_role": "control", "secondary_roles": []},
            design_pitch="成熟不等于退场；她把多年路线判断转化为可操作的空间控制节奏。",
            ability_concept="在亲自确认过的路线节点上短暂改变人群与障碍的可通行优先级，玩家通过封路、引导和重新开路控制现场。",
            story_hook="她一边标记出口，一边拒绝别人把她当成只负责给年轻人建议的导师。",
        ),
    )
    assert mature.combat_role_profile.primary_role == "control"
    assert "导师" in mature.story_hook and "拒绝" in mature.story_hook
    assert "退休" not in mature.social_role


def test_faction_membership_does_not_imply_leadership_or_blanket_knowledge():
    request = CharacterDesignRequest(
        "年轻呈现的公共安全联席体系成员，能力可靠但权限有限，不是领导或最高研究者。",
        request_id="diversity_limited_member",
    )
    draft = _generate(
        request,
        _payload(
            "draft_limited_member",
            faction_id="faction_005",
            occupation="大型活动安全组现场协作员",
            social_role="组织成员，负责被交付的现场记录和接口沟通，不拥有跨部门指挥权",
            knowledge_scope="只接触完成现场协作所必需的信息；原始案件数据和其他部门内部记录仍受各自权限限制。",
        ),
        faction_lookup=True,
    )
    report = CanonChecker().check(draft, request=request)
    assert report.status != CanonCheckStatus.FAIL
    assert draft.faction_id == "faction_005"
    assert "最高" not in " ".join((draft.occupation, draft.social_role, draft.knowledge_scope))
    assert "不拥有" in draft.social_role
    assert "限制" in draft.knowledge_scope


def test_v02_playable_and_canon_repair_boundaries_remain_covered():
    assert "playable agency" in CHARACTER_SYSTEM_CONTRACT
    assert "combat fantasy" in CHARACTER_SYSTEM_CONTRACT
    assert "competence, formal authority, knowledge access" in CHARACTER_SYSTEM_CONTRACT
    metrics = compute_metrics(run_benchmark())
    assert metrics.final_end_to_end_passes == metrics.evaluable_core_cases
