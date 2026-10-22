"""Hermes red-team regression matrix for Canon Checker v0.1.1.

The matrix intentionally keeps the expected semantic outcome independent from
the checker implementation.  H2 remains an explicit known limitation: the
current fail-closed support contract cannot prove a non-extractive paraphrase.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from enum import Enum
from pathlib import Path
import json

from agents import CanonFindingCode, CanonCheckStatus, CharacterDesignRequest, CharacterDraft


class RedTeamExpectation(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True)
class RedTeamCase:
    case_id: str
    expected_status: CanonCheckStatus
    expected_codes: frozenset[CanonFindingCode] = frozenset()
    forbidden_codes: frozenset[CanonFindingCode] = frozenset()
    known_limitation: bool = False
    severity: dict[CanonFindingCode, str] | None = None
    description: str = ""


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def _base() -> tuple[CharacterDraft, CharacterDesignRequest]:
    payload = json.loads((FIXTURES / "canon_checker_good.json").read_text(encoding="utf-8"))
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(**payload["request"])


def redteam_cases() -> list[tuple[RedTeamCase, CharacterDraft, CharacterDesignRequest | None]]:
    base, request = _base()
    fail = CanonCheckStatus.FAIL
    passed = CanonCheckStatus.PASS

    cases: list[tuple[RedTeamCase, CharacterDraft, CharacterDesignRequest | None]] = [
        (RedTeamCase("A", passed, description="conservative valid draft"), base, request),
        (RedTeamCase("B", passed, description="ordinary cross-department coordination"), replace(base, background="她协调警方、消防与急救交换信息，但各机构独立作出专业决定。"), None),
        (RedTeamCase("C", passed, description="new personal proposal"), replace(base, proposed_new_content=("拟议一段个人经历",), background="她可能在未来参与社区项目。"), None),
        (RedTeamCase("D", passed, description="ordinary observation role"), replace(base, background="她记录现场信息，但不参与关键决定。"), None),
        (RedTeamCase("E", passed, description="minor student"), replace(base, age=16, occupation="高中生"), None),
        (RedTeamCase("F", passed, description="single bounded physical effect"), replace(base, ability_concept="她能短暂提高某物表面温度。"), None),
        (RedTeamCase("G1", fail, frozenset({CanonFindingCode.AUTHORITY_OVERREACH}), description="cross-domain command"), replace(base, background="警察、消防、急救的现场处置都由她统一调度，各部门行动听她安排。"), None),
        (RedTeamCase("G2", fail, frozenset({CanonFindingCode.WORLD_RULE_VIOLATION, CanonFindingCode.FORBIDDEN_PATTERN}), description="secret centralized institution"), replace(base, background="她在一家从不对外公开的行政机构任职，该机构统一管理全市能力者事务，所有事件记录都归口到这里。"), None),
        (RedTeamCase("G3", fail, frozenset({CanonFindingCode.AUTHORITY_OVERREACH}), description="claimed temporary authorization does not legalize command"), replace(base, background="她获得上级临时授权，在事故期间统一指挥警察、消防与急救的现场行动。"), None),
        (RedTeamCase("G4", passed, description="existing story target without relationship claim"), replace(base, story_hook="她在南栈事故中负责现场观察和信息记录。", story_link=None), None),
        (RedTeamCase("G5", passed, description="proposed story participation"), replace(base, story_hook="她拟议参与南栈事故复盘。", story_link=None), None),
        (RedTeamCase("G6", passed, description="authorized personal data scope"), replace(base, knowledge_scope="她整理自己负责课题的已授权数据。"), None),
        (RedTeamCase("G7", fail, frozenset({CanonFindingCode.STORY_ROLE_OVERREACH}), description="factual decision dominance without story_link"), replace(base, background="她没有指挥头衔，但南栈演出散场与撤场动线冲突事故中所有关键决定都由她拍板，最终处置方案全部出自她的手。", story_link=None), None),
        (RedTeamCase("G8", passed, description="new personal proposal does not become Canon"), replace(base, proposed_new_content=("拟议一段个人经历",), story_hook="她会在未来参与一项新的校园志愿活动。"), None),
        (RedTeamCase("G9", passed, description="clause-level hedged proposal"), replace(base, proposed_new_content=("拟议：参与南栈事故复盘",), story_hook="她可能会参与南栈事故复盘，也可能只是旁听。"), None),
        (RedTeamCase("G10", fail, frozenset({CanonFindingCode.WORLD_RULE_VIOLATION}), description="minor professional frontline occupation"), replace(base, age=16, occupation="消防员"), None),
        (RedTeamCase("G11", fail, frozenset({CanonFindingCode.FORBIDDEN_PATTERN}), description="elemental classification system"), replace(base, ability_concept="她能操纵烈焰、翻涌水流、引动雷霆，是典型的元素使。"), None),
        (RedTeamCase("G12", fail, frozenset({CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH}), description="universal sensitive knowledge access"), replace(base, knowledge_scope="市里每位能力者的内部档案她都能调阅，相关结论她也都清楚。"), None),
        (RedTeamCase("G13", passed, description="negative polarity remains safe"), replace(base, background="她不负责统一管理全市能力者，也不拥有任何部门的指挥权。"), None),
        (RedTeamCase("G14", passed, description="bounded ability is not elemental system"), replace(base, ability_concept="她能短暂提高物体表面温度，但不存在元素属性分类。"), None),
        (RedTeamCase("G15", passed, description="proposed weak relationship"), replace(base, relationships=({"target_id": "char_launch_001", "description": "拟议合作", "status": "proposed"},)), None),
        (RedTeamCase("H1", fail, frozenset({CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL}), severity={CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL: "error"}, description="existing Canon entity mislabeled as new design"), replace(base, new_design_elements=("南栈演出散场事故", "南栈生活合作社"), design_pitch="新设计事件：南栈演出散场事故"), None),
        (RedTeamCase("H2", passed, known_limitation=True, description="non-extractive Canon paraphrase; fail-closed known limitation"), replace(base, canon_basis=(replace(base.canon_basis[0], source_id="lore_001", supports=("临洲这座城市里有合法的协理职业",)),)), None),
    ]
    assert len(cases) == 23
    return cases
