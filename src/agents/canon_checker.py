"""Deterministic, read-only validation for generated character drafts.

The generator is allowed to be creative.  This checker is intentionally not:
it reads structured Canon, applies stable rules, and returns machine-readable
findings.  It never calls a model and never mutates the draft or repositories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from knowledge import KnowledgeResolver
from story import StoryRepository, load_story_repository

from .character_generation import (
    CharacterAuthoringToolbox,
    CharacterDesignRequest,
    CharacterDraft,
    canon_field_grounding_violations,
)
from .grounding import GroundingValidator


class CanonCheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CanonFindingCode(str, Enum):
    INVALID_CANON_REFERENCE = "INVALID_CANON_REFERENCE"
    UNSUPPORTED_CANON_CLAIM = "UNSUPPORTED_CANON_CLAIM"
    PROPOSAL_PRESENTED_AS_CANON = "PROPOSAL_PRESENTED_AS_CANON"
    CANON_PRESENTED_AS_PROPOSAL = "CANON_PRESENTED_AS_PROPOSAL"
    WORLD_RULE_VIOLATION = "WORLD_RULE_VIOLATION"
    FORBIDDEN_PATTERN = "FORBIDDEN_PATTERN"
    AUTHORITY_OVERREACH = "AUTHORITY_OVERREACH"
    KNOWLEDGE_SCOPE_OVERREACH = "KNOWLEDGE_SCOPE_OVERREACH"
    STORY_ROLE_OVERREACH = "STORY_ROLE_OVERREACH"
    EXISTING_CHARACTER_CONFLICT = "EXISTING_CHARACTER_CONFLICT"
    DUPLICATE_CHARACTER_CONCEPT = "DUPLICATE_CHARACTER_CONCEPT"
    HARD_CONSTRAINT_VIOLATION = "HARD_CONSTRAINT_VIOLATION"
    AMBIGUOUS_NEW_CANON = "AMBIGUOUS_NEW_CANON"
    INVALID_STORY_LINK = "INVALID_STORY_LINK"
    INVALID_FACTION_ROLE = "INVALID_FACTION_ROLE"
    INVALID_DRAFT_STATUS = "INVALID_DRAFT_STATUS"


@dataclass(frozen=True)
class CanonFinding:
    code: CanonFindingCode
    severity: FindingSeverity
    field_path: str
    message: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "field_path": self.field_path,
            "message": self.message,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class CanonCheckSummary:
    errors: int
    warnings: int
    infos: int

    def to_dict(self) -> dict[str, int]:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
        }


@dataclass(frozen=True)
class CanonCheckReport:
    draft_id: str
    status: CanonCheckStatus
    findings: tuple[CanonFinding, ...]
    checked_source_ids: tuple[str, ...]
    summary: CanonCheckSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "status": self.status.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "checked_source_ids": list(self.checked_source_ids),
            "summary": self.summary.to_dict(),
        }


@dataclass(frozen=True)
class CanonCheckContext:
    """Small read-only dependency bundle used by Canon check rules."""

    resolver: KnowledgeResolver
    story_repository: StoryRepository
    world_rules: Mapping[str, Any]


@dataclass(frozen=True)
class _ForbiddenTargetSpan:
    """A deterministic, clause-local forbidden target occurrence."""

    start: int
    end: int
    normalized_text: str


_GENERIC_SUPPORTS: Mapping[str, frozenset[str]] = {
    "world_rules": frozenset(
        {"world_rules", "world_context", "ability_concept", "setting"}
    ),
    "faction": frozenset(
        {"faction_id", "faction_context", "occupation", "social_role"}
    ),
    "lore": frozenset(
        {"world_context", "background", "ability_concept", "knowledge_scope"}
    ),
    "character": frozenset(
        {"character_context", "relationship", "existing_character_awareness"}
    ),
    "story": frozenset({"story_context", "story_hook", "story_link"}),
    "case": frozenset({"story_context", "story_hook", "story_link", "case_context"}),
    "incident": frozenset(
        {"story_context", "story_hook", "story_link", "incident_context"}
    ),
    "project": frozenset({"project_context", "background", "knowledge_scope"}),
}

_SEVERITY_ORDER = {
    FindingSeverity.ERROR: 0,
    FindingSeverity.WARNING: 1,
    FindingSeverity.INFO: 2,
}

_NEGATION_PREFIXES = (
    "不得",
    "不能",
    "不会",
    "并非",
    "不是",
    "没有",
    "不可",
    "不承担",
    "非核心",
    "不",
    "未",
    "无",
)

_TEXT_FIELDS = (
    "occupation",
    "social_role",
    "design_pitch",
    "background",
    "story_hook",
    "ability_concept",
    "knowledge_scope",
)

# These small lexicons describe invariants, rather than individual red-team
# sentences.  They intentionally stay local to the deterministic checker.
_COMMAND_ACTIONS = (
    "指挥",
    "统一指挥",
    "统一调度",
    "统一安排",
    "统一决定",
    "统一裁定",
    "统一部署",
    "直接指挥",
    "全权调度",
    "听其安排",
    "听她安排",
    "听他安排",
    "行动由其决定",
    "全部由其决定",
    "全部听她安排",
    "全部听他安排",
    "最终决定",
    "按她的决定行动",
    "按其决定行动",
    "行动听她安排",
    "行动听其安排",
    "必须经过她确认",
    "必须经过其确认",
    "均须经过",
    "都要经过",
    "都必须经过",
    "最终由她确认",
    "最终由其确认",
)
_PUBLIC_SAFETY_DOMAINS = (
    "警察",
    "警方",
    "公安",
    "消防",
    "急救",
    "医疗",
    "医院",
    "保险",
    "行政",
    "司法",
)
_SECRECY_MARKERS = (
    "秘密",
    "未公开",
    "不公开",
    "从不公开",
    "从不对外公开",
    "不对外公开",
    "未对外披露",
    "未向公众披露",
    "隐藏",
    "隐蔽",
    "不为公众所知",
)
_ABSENCE_DENIAL_PATTERNS = (
    r"(?:无|没有)(?:任何|一个|此类|相关)?$",
    r"(?:不|未)(?:使用|包含|采用|涉及)(?:任何|一个|一项|此类|相关)?$",
    # Some formal patterns begin with the denied action itself, e.g.
    # ``不把能力简单拆成……``.  In that shape the regex match starts after
    # the negator, so the relation-specific forms below cannot see it.
    r"(?:不|未|没有|并非|禁止|避免)$",
    # These predicates deny the relationship/action represented by the
    # forbidden target.  Keep them explicit instead of treating every
    # preceding "不" or "未" as a negation; otherwise a positive claim in a
    # sentence such as "不属于旧机构，但隶属于秘密管理局" could be hidden.
    r"(?:不是|并非|不属于|不隶属于|未加入|未曾加入|从未加入|没有加入|不加入"
    r"|未建立|未曾建立|从未建立|没有建立|不建立|未设立|未曾设立|从未设立|没有设立|不设立"
    r"|未创建|未曾创建|从未创建|没有创建|不创建|未组建|未曾组建|从未组建|没有组建|不组建)"
    r"(?:任何|一个|一项|此类|相关)?(?:新的|新)?$",
)
_ABSENCE_PREDICATE_PATTERN = (
    r"(?:不(?:使用|包含|采用|涉及)(?:任何|一个|一项|此类|相关)?"
    r"|未(?:使用|包含|采用|涉及)(?:任何|一个|一项|此类|相关)?"
    r"|无(?:任何|一个|此类|相关)?|没有(?:任何|一个|此类|相关)?)"
)
_ABSENCE_COORDINATOR_PATTERN = r"(?:或|或者|与|和|及|以及|、|/)"
_NON_COORDINATE_TEXT = r"[^或与和及、/，,。！？；而]"
_SECRET_ADMINISTRATIVE_ENTITY_PATTERNS = (
    r"(?:秘密|未公开|不公开|从不公开|从不对外公开|不对外公开|未对外披露|未向公众披露|隐藏|隐蔽|不为公众所知)"
    rf"{_NON_COORDINATE_TEXT}{{0,8}}(?:政府|行政|监管|管理局|机构|部门|机关|组织)",
    r"(?:政府|行政|监管|管理局|机构|部门|机关|组织)"
    rf"{_NON_COORDINATE_TEXT}{{0,8}}(?:秘密|未公开|不公开|从不公开|从不对外公开|不对外公开|未对外披露|未向公众披露|隐藏|隐蔽|不为公众所知)",
)
_ADMINISTRATIVE_ENTITIES = (
    "政府机构",
    "行政机构",
    "行政机关",
    "机构",
    "监管机构",
    "管理局",
    "监管部门",
    "官方机构",
    "跨部门办公室",
    "委员会",
    "协调办公室",
)
_CENTRALIZED_AUTHORITY = (
    "统一管理全市",
    "统一监管全市",
    "所有事件归口",
    "全部事件归口",
    "掌管全城",
    "掌管全市",
    "统一能力监管",
    "全城能力者",
    "全市能力者",
    "全市能力者事务",
)
_STORY_DECISION_DOMINANCE = (
    "所有关键决定由她",
    "全部关键决定由她",
    "由她拍板",
    "最终由她拍板",
    "最终决定由她",
    "处置方案由她决定",
    "方案全部出自她",
    "最终方案由她制定",
    "任何关键行动都要经过她确认",
    "所有行动都需她确认",
    "所有关键行动由她安排",
    "所有部门按她方案行动",
    "现场处置围绕她的决定展开",
    "最终解决方案由她给出",
    "所有决定必须经她同意",
    "所有关键决定均须经过她确认",
    "所有关键决定都必须经过她确认",
    "任何关键行动都必须经过她确认",
    "任何关键行动均须经过她确认",
    "关键行动必须取得她同意",
    "各部门关键行动必须取得她同意",
    "警察消防急救最终按她决定行动",
    "警察、消防、急救最终按她决定行动",
    "各部门按她的决定行动",
    "各部门按其决定行动",
)
_UNIVERSAL_SCOPE = (
    "所有",
    "全部",
    "全城",
    "全市",
    "每位",
    "每个",
    "任一",
    "任何",
    "无一例外",
)
_SENSITIVE_OBJECTS = (
    "能力者档案",
    "能力档案",
    "内部资料",
    "内部数据",
    "受限资料",
    "内部档案",
    "个人档案",
    "受限数据",
    "内部结论",
    "事故内部结论",
    "历史记录",
    "长期样本",
    "档案",
    "内部记录",
)
_KNOWLEDGE_ACCESS = (
    "访问",
    "调取",
    "调阅",
    "查阅",
    "读取",
    "掌握",
    "知道",
    "了解",
    "清楚",
    "查看",
    "检索",
)
_KNOWLEDGE_NEGATION_PATTERNS = (
    r"(?:不|并不|不了解|不知道|不掌握)",
    r"(?:不能|无法|无权|没有|并未|未)\s*(?:默认)?(?:访问|读取|调阅|查阅|调取|查看|检索|掌握|知道|了解)",
    r"(?:无访问权|没有访问权限|无权访问|不具备(?:对.{0,24})?访问权限)",
)
_PROPOSAL_ENTITY_INTRODUCTION = (
    "新增",
    "新建",
    "新设",
    "新设计",
    "新角色",
    "新组织",
    "新事件",
    "新机构",
    "新部门",
    "新项目",
    "设立",
    "成立",
    "创建",
    "添加",
    "组建",
    "搭建",
    "设置",
    "设计一个",
)
_INTRODUCTION_ACTIONS = (
    "新增",
    "引入",
    "建立",
    "设立",
    "成立",
    "创建",
    "组建",
    "搭建",
    "设置",
    "新设",
)
_HEDGE_MARKERS = (
    "可能",
    "也许",
    "或许",
    "是否",
    "考虑",
    "可以考虑",
    "尚未确定",
    "未确定",
    "拟议",
    "计划",
    "如果",
    "若",
    "假如",
    "或只是",
)
_ELEMENT_CATEGORIES = {
    "fire": ("火", "火焰", "烈焰"),
    "water": ("水", "水流", "冰"),
    "thunder": ("雷", "雷霆"),
    "wind": ("风",),
    "light": ("光",),
    "dark": ("暗",),
}
_ELEMENT_SYSTEM_MARKERS = (
    "元素使",
    "元素体系",
    "元素属性",
    "属性体系",
    "火系",
    "水系",
    "雷系",
    "属性克制",
    "元素分类",
)
_ELEMENTAL_NEGATION_PATTERN = (
    r"(?:不|未|没有|并非|禁止|避免)[^，,。！？；!?\n]{0,16}"
    r"(?:拆成|分成|划分为|归类为|归为|视为)"
)
_FRONTLINE_OCCUPATIONS = (
    "消防员",
    "消防救援",
    "警察",
    "警务人员",
    "警员",
    "军人",
    "士兵",
    "特警",
    "一线急救",
    "急救员",
    "急救医生",
)


class CanonChecker:
    """Run deterministic Canon checks over a ``CharacterDraft``."""

    def __init__(
        self,
        *,
        resolver: KnowledgeResolver | None = None,
        story_repository: StoryRepository | None = None,
    ) -> None:
        actual_resolver = resolver or KnowledgeResolver()
        actual_story_repository = story_repository or load_story_repository()
        toolbox = CharacterAuthoringToolbox(
            actual_resolver, actual_story_repository
        )
        world_rules = toolbox.world_rules_view()["result"]
        self.context = CanonCheckContext(
            actual_resolver,
            actual_story_repository,
            world_rules,
        )
        self._toolbox = toolbox
        self._rules = (
            self._check_references,
            self._check_field_grounding,
            self._check_canon_support,
            self._check_proposal_separation,
            self._check_world_rules,
            self._check_authority,
            self._check_knowledge_scope,
            self._check_story_and_relationships,
            self._check_hard_constraints,
            self._check_existing_character_collision,
        )

    def _check_field_grounding(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        source_ids = {
            "world_rules",
            *self.context.resolver.factions,
            *self.context.resolver.lore,
            *self.context.resolver.characters,
            *self.context.resolver.projects,
            *self.context.resolver.cases,
            *self.context.resolver.incidents,
            *self.context.story_repository.canon,
        }
        for field_path, evidence_ids, reason in canon_field_grounding_violations(
            draft, source_ids
        ):
            yield self._finding(
                CanonFindingCode.UNSUPPORTED_CANON_CLAIM,
                FindingSeverity.ERROR,
                field_path,
                reason,
                evidence_ids,
            )

    def check(
        self,
        draft: CharacterDraft,
        *,
        request: CharacterDesignRequest | None = None,
    ) -> CanonCheckReport:
        if not isinstance(draft, CharacterDraft):
            raise TypeError("draft must be a CharacterDraft")
        if request is not None and not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be a CharacterDesignRequest or None")

        findings: list[CanonFinding] = []
        for rule in self._rules:
            findings.extend(rule(draft, request))
        ordered = self._deduplicate_and_sort(findings)
        summary = CanonCheckSummary(
            errors=sum(item.severity == FindingSeverity.ERROR for item in ordered),
            warnings=sum(
                item.severity == FindingSeverity.WARNING for item in ordered
            ),
            infos=sum(item.severity == FindingSeverity.INFO for item in ordered),
        )
        status = (
            CanonCheckStatus.FAIL
            if summary.errors
            else CanonCheckStatus.WARN
            if summary.warnings
            else CanonCheckStatus.PASS
        )
        return CanonCheckReport(
            draft.draft_id,
            status,
            ordered,
            self._checked_source_ids(draft),
            summary,
        )

    def _check_references(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        if draft.status != "draft":
            yield self._finding(
                CanonFindingCode.INVALID_DRAFT_STATUS,
                FindingSeverity.ERROR,
                "status",
                f"CharacterDraft status must be 'draft', not {draft.status!r}.",
            )
        if draft.canonical_character_id is not None:
            yield self._finding(
                CanonFindingCode.INVALID_DRAFT_STATUS,
                FindingSeverity.ERROR,
                "canonical_character_id",
                "A draft must not claim a canonical character ID.",
                (draft.canonical_character_id,)
                if draft.canonical_character_id in self.context.resolver.characters
                else (),
            )
        if draft.faction_id and self._source_type(draft.faction_id) != "faction":
            yield self._invalid_reference("faction_id", draft.faction_id)
        for index, entry in enumerate(draft.canon_basis):
            actual_type = self._source_type(entry.source_id)
            if actual_type is None:
                yield self._invalid_reference(
                    f"canon_basis[{index}].source_id", entry.source_id
                )
            elif entry.source_type and entry.source_type != actual_type:
                yield self._finding(
                    CanonFindingCode.INVALID_CANON_REFERENCE,
                    FindingSeverity.ERROR,
                    f"canon_basis[{index}].source_type",
                    f"Canon source {entry.source_id!r} is {actual_type!r}, not {entry.source_type!r}.",
                    (entry.source_id,),
                )
        if draft.story_link and self._source_type(
            draft.story_link.target_id
        ) not in {"story", "case", "incident"}:
            yield self._invalid_reference(
                "story_link.target_id", draft.story_link.target_id
            )
        for index, relationship in enumerate(draft.relationships):
            target_id = relationship.get("target_id")
            if target_id and self._source_type(str(target_id)) not in {
                "character",
                "faction",
            }:
                yield self._invalid_reference(
                    f"relationships[{index}].target_id", str(target_id)
                )

    def _check_canon_support(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        for index, entry in enumerate(draft.canon_basis):
            source_type = self._source_type(entry.source_id)
            if source_type is None:
                continue
            evidence_text = self._source_text(entry.source_id)
            generic = _GENERIC_SUPPORTS.get(source_type, frozenset())
            for support_index, support in enumerate(entry.supports):
                if support in generic:
                    continue
                if GroundingValidator.extractively_supported(support, evidence_text):
                    continue
                yield self._finding(
                    CanonFindingCode.UNSUPPORTED_CANON_CLAIM,
                    FindingSeverity.ERROR,
                    f"canon_basis[{index}].supports[{support_index}]",
                    f"Canon source {entry.source_id!r} does not support claim {support!r}.",
                    (entry.source_id,),
                )

            if (
                source_type == "faction"
                and entry.source_id == draft.faction_id
                and any(
                    support in {"occupation", "social_role", "faction_id"}
                    for support in entry.supports
                )
                and self._faction_role_conflict(draft, entry.source_id)
            ):
                yield self._finding(
                    CanonFindingCode.UNSUPPORTED_CANON_CLAIM,
                    FindingSeverity.ERROR,
                    f"canon_basis[{index}].supports",
                    f"Faction {entry.source_id!r} does not support the draft's claimed role or authority.",
                    (entry.source_id,),
                )

    def _check_proposal_separation(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        proposals: list[str] = []
        for index, item in enumerate(
            (*draft.new_design_elements, *draft.proposed_new_content)
        ):
            existing_entities = self._existing_canon_entities(item)
            usage = self._classify_proposal_entity_usage(item, existing_entities)
            if existing_entities and usage in {"ENTITY_ITSELF_AS_NEW", "AMBIGUOUS"}:
                yield self._finding(
                    CanonFindingCode.CANON_PRESENTED_AS_PROPOSAL,
                    FindingSeverity.ERROR,
                    (
                        f"new_design_elements[{index}]"
                        if index < len(draft.new_design_elements)
                        else f"proposed_new_content[{index - len(draft.new_design_elements)}]"
                    ),
                    "A new-design claim names an entity already registered in Canon.",
                    tuple(entity_id for entity_id, _ in existing_entities),
                )
                continue
            if self._proposal_fragments(item):
                proposals.append(item)
        if not proposals:
            return
        evidence = (
            (draft.story_link.target_id,)
            if draft.story_link
            and self._source_type(draft.story_link.target_id) is not None
            else ()
        )
        for field_path in ("background", "story_hook", "design_pitch"):
            narrative = getattr(draft, field_path)
            matching = [
                proposal
                for proposal in proposals
                if self._proposal_asserted_in_narrative(proposal, narrative)
            ]
            if not matching:
                continue
            yield self._finding(
                CanonFindingCode.PROPOSAL_PRESENTED_AS_CANON,
                FindingSeverity.WARNING,
                field_path,
                f"Narrative presents proposed element {matching[0]!r} as an established event.",
                evidence,
            )

    def _check_world_rules(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        rules = {
            str(item.get("id")): str(item.get("statement", ""))
            for item in self.context.world_rules.get("rules", [])
            if isinstance(item, Mapping)
        }
        ability = draft.ability_concept
        if "RULE-006" in rules and self._ability_replaces_expertise(ability):
            yield self._finding(
                CanonFindingCode.WORLD_RULE_VIOLATION,
                FindingSeverity.ERROR,
                "ability_concept",
                "Ability claims to replace professional knowledge, training, or real resources.",
                ("world_rules",),
            )
        if (
            ("RULE-003" in rules or "RULE-004" in rules)
            and self._unbounded_control_ability(ability)
        ):
            yield self._finding(
                CanonFindingCode.WORLD_RULE_VIOLATION,
                FindingSeverity.ERROR,
                "ability_concept",
                "Ability is unbounded control rather than a limited personal bias rule.",
                ("world_rules",),
            )

        secret_field = self._first_secret_institution_field(draft)
        if "RULE-008" in rules and secret_field:
            yield self._finding(
                CanonFindingCode.WORLD_RULE_VIOLATION,
                FindingSeverity.ERROR,
                secret_field,
                "Draft creates a secret centralized ability-governance institution forbidden by RULE-008.",
                ("world_rules",),
            )

        if "RULE-024" in rules and self._minor_frontline_occupation(draft):
            yield self._finding(
                CanonFindingCode.WORLD_RULE_VIOLATION,
                FindingSeverity.ERROR,
                "occupation",
                "A minor draft claims a professional high-risk frontline occupation without a Canon-established exception.",
                ("world_rules",),
            )

        for pattern in self.context.world_rules.get("forbidden_patterns", []):
            if not isinstance(pattern, str):
                continue
            field_path = self._forbidden_pattern_field(pattern, draft)
            if field_path:
                yield self._finding(
                    CanonFindingCode.FORBIDDEN_PATTERN,
                    FindingSeverity.ERROR,
                    field_path,
                    f"Draft matches formal Forbidden Pattern: {pattern}",
                    ("world_rules",),
                )

    def _check_authority(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        if draft.faction_id and self._source_type(draft.faction_id) != "faction":
            return
        text = " ".join(
            (draft.occupation, draft.social_role, draft.background, draft.story_hook)
        )
        evidence = (draft.faction_id,) if draft.faction_id else ("world_rules",)
        if self._positive_match(
            text,
            r"最高负责人|最高领导|全权负责人|统领全市|全权指挥|行政执法权|(?:全市|城市)警务总指挥|消防总指挥",
        ):
            yield self._finding(
                CanonFindingCode.AUTHORITY_OVERREACH,
                FindingSeverity.ERROR,
                "occupation",
                "Draft claims organization-wide or city-wide authority not established by Canon.",
                evidence,
            )
        if self._positive_forbidden_match(
            text,
            r"独立行政机关|独立监管机关|秘密监管(?:部门|机构)|秘密行政机构|神秘管理局",
        ):
            yield self._finding(
                CanonFindingCode.AUTHORITY_OVERREACH,
                FindingSeverity.ERROR,
                "background",
                "Draft turns a role or faction into an independent authority that Canon does not define.",
                evidence,
            )
        if self._has_cross_domain_command_claim(text):
            yield self._finding(
                CanonFindingCode.AUTHORITY_OVERREACH,
                FindingSeverity.ERROR,
                "background",
                "Draft claims unified command authority over independent public-safety domains.",
                evidence,
            )
        if self._has_story_decision_dominance(text):
            yield self._finding(
                CanonFindingCode.AUTHORITY_OVERREACH,
                FindingSeverity.ERROR,
                "background",
                "Draft claims hidden authority over consequential decisions.",
                evidence,
            )
        if draft.faction_id and self._faction_role_conflict(draft, draft.faction_id):
            yield self._finding(
                CanonFindingCode.INVALID_FACTION_ROLE,
                FindingSeverity.ERROR,
                "occupation",
                f"Occupation is outside the deterministic function boundary of faction {draft.faction_id!r}.",
                (draft.faction_id,),
            )

    def _check_knowledge_scope(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        scope = draft.knowledge_scope
        broad_access = self._has_universal_sensitive_access(scope)
        evidence = (draft.faction_id,) if draft.faction_id else ("world_rules",)
        if broad_access:
            yield self._finding(
                CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH,
                FindingSeverity.ERROR,
                "knowledge_scope",
                "Draft claims blanket access to city-wide, internal, or complete records without a Canon authorization.",
                evidence,
            )
        for lore_id in sorted(set(re.findall(r"lore(?:_secret)?_[A-Za-z0-9]+", scope))):
            lore = self.context.resolver.lore.get(lore_id)
            if lore is None:
                continue
            if lore.get("sensitivity") == "public":
                continue
            claim = self._knowledge_claim_clause(scope, lore_id)
            if not self._contains_any(claim, _KNOWLEDGE_ACCESS):
                continue
            if self._has_local_negation(claim):
                continue
            yield self._finding(
                CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH,
                FindingSeverity.ERROR,
                "knowledge_scope",
                f"Draft claims non-public Lore {lore_id!r} without a Canon authorization.",
                (lore_id,),
            )

    def _check_story_and_relationships(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        linked_story_target = (
            draft.story_link
            and self._source_type(draft.story_link.target_id)
            in {"story", "case", "incident"}
        )
        story_targets = self._resolve_story_targets_from_text(draft, request)
        if linked_story_target:
            if draft.story_link.status == "canon_backed":
                yield self._finding(
                    CanonFindingCode.INVALID_STORY_LINK,
                    FindingSeverity.ERROR,
                    "story_link.status",
                    "The target exists, but Canon does not establish this new draft's relationship to it; use a proposed status.",
                    (draft.story_link.target_id,),
                )
        role_field = self._story_overreach_field(draft)
        if role_field and story_targets:
            yield self._finding(
                CanonFindingCode.STORY_ROLE_OVERREACH,
                FindingSeverity.ERROR,
                role_field,
                "Draft takes a core, sole, or resolving role in an existing story position not assigned by Canon.",
                tuple(sorted(story_targets)),
            )
        for index, relationship in enumerate(draft.relationships):
            target_id = relationship.get("target_id")
            if not target_id or self._source_type(str(target_id)) not in {
                "character",
                "faction",
            }:
                continue
            status = str(relationship.get("status", "proposed"))
            if status == "canon_backed":
                yield self._finding(
                    CanonFindingCode.UNSUPPORTED_CANON_CLAIM,
                    FindingSeverity.ERROR,
                    f"relationships[{index}].status",
                    "Existing target does not make a relationship with a new draft established Canon.",
                    (str(target_id),),
                )

    def _check_hard_constraints(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        if request is None:
            return
        hard_text = " ".join((*request.hard_constraints, request.brief))
        bounds = self._age_bounds(hard_text)
        if bounds and draft.age is not None and not bounds[0] <= draft.age <= bounds[1]:
            yield self._finding(
                CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                FindingSeverity.ERROR,
                "age",
                f"Draft age {draft.age} violates required range {bounds[0]}-{bounds[1]}.",
                (request.request_id,),
            )

        role_field = self._story_overreach_field(draft)
        if role_field and self._positive_match(
            hard_text,
            r"不得.{0,8}(?:核心负责人|主要负责人|主导者)|非核心(?:联系|角色)|不能.{0,8}(?:负责|主导|解决)",
        ):
            yield self._finding(
                CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                FindingSeverity.ERROR,
                role_field,
                "Draft violates the request's non-core story-role constraint.",
                (request.request_id,),
            )

        draft_text = self._all_draft_text(draft)
        for forbidden in request.forbidden_elements:
            if self._forbidden_request_matches(forbidden, draft_text):
                yield self._finding(
                    CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                    FindingSeverity.ERROR,
                    "forbidden_elements",
                    f"Draft includes request-forbidden element {forbidden!r}.",
                    (request.request_id,),
                )

        required_factions = re.findall(
            r"(?:必须|需要|应当).{0,8}(faction_[A-Za-z0-9_]+)", hard_text
        )
        forbidden_factions = re.findall(
            r"(?:不得|禁止|不能).{0,8}(faction_[A-Za-z0-9_]+)", hard_text
        )
        if required_factions and draft.faction_id not in required_factions:
            yield self._finding(
                CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                FindingSeverity.ERROR,
                "faction_id",
                f"Draft faction {draft.faction_id!r} does not satisfy required faction {required_factions[0]!r}.",
                (request.request_id,),
            )
        if draft.faction_id in forbidden_factions:
            yield self._finding(
                CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                FindingSeverity.ERROR,
                "faction_id",
                f"Draft uses forbidden faction {draft.faction_id!r}.",
                (request.request_id,),
            )

        combat_requirements = {
            "main_dps": ("主C", "主输出", "main_dps"),
            "sub_dps": ("副C", "副输出", "sub_dps"),
            "support": ("辅助", "支援", "support"),
            "healer": ("治疗", "奶", "healer"),
            "control": ("控制", "control"),
            "defense": ("防御", "defense"),
        }
        canonical_roles = {
            draft.combat_role_profile.primary_role,
            *draft.combat_role_profile.secondary_roles,
        }
        for role, markers in combat_requirements.items():
            if any(f"必须{marker}" in hard_text or f"要求{marker}" in hard_text for marker in markers):
                if role not in canonical_roles:
                    yield self._finding(
                        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
                        FindingSeverity.ERROR,
                        "combat_role_profile",
                        f"Draft combat role profile does not satisfy required role {role!r}.",
                        (request.request_id,),
                    )
                break

    def _check_existing_character_collision(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> Iterable[CanonFinding]:
        del request
        if draft.canonical_character_id in self.context.resolver.characters:
            yield self._finding(
                CanonFindingCode.EXISTING_CHARACTER_CONFLICT,
                FindingSeverity.ERROR,
                "canonical_character_id",
                f"New draft reuses existing character ID {draft.canonical_character_id!r}.",
                (str(draft.canonical_character_id),),
            )
        draft_name = self._normalize(draft.name)
        draft_occupation = self._normalize(draft.occupation)
        for character_id, character in self.context.resolver.characters.items():
            name = character.get("name", {})
            display_name = name.get("display_name", "") if isinstance(name, Mapping) else ""
            profile = character.get("basic_profile", {})
            occupation = profile.get("occupation", "") if isinstance(profile, Mapping) else ""
            if (
                draft_name
                and draft_name == self._normalize(str(display_name))
                and draft_occupation
                and draft_occupation == self._normalize(str(occupation))
            ):
                yield self._finding(
                    CanonFindingCode.DUPLICATE_CHARACTER_CONCEPT,
                    FindingSeverity.ERROR,
                    "name",
                    "Draft duplicates both the exact name and occupation of an existing character.",
                    (character_id,),
                )

    def _source_type(self, source_id: str) -> str | None:
        if source_id == "world_rules":
            return "world_rules"
        resolver = self.context.resolver
        for source_type, registry in (
            ("faction", resolver.factions),
            ("lore", resolver.lore),
            ("character", resolver.characters),
            ("project", resolver.projects),
            ("case", resolver.cases),
            ("incident", resolver.incidents),
            ("story", self.context.story_repository.canon),
        ):
            if source_id in registry:
                return source_type
        return None

    def _source_record(self, source_id: str) -> Mapping[str, Any] | None:
        source_type = self._source_type(source_id)
        resolver = self.context.resolver
        if source_type == "world_rules":
            return self.context.world_rules
        if source_type == "faction":
            return self._toolbox._faction_view(resolver.factions[source_id])
        if source_type == "lore":
            return self._toolbox._lore_view(resolver.lore[source_id])
        if source_type == "character":
            return self._toolbox._character_view(resolver.characters[source_id])
        if source_type == "story":
            return self.context.story_repository.canon[source_id]
        if source_type == "case":
            return resolver.cases[source_id]
        if source_type == "incident":
            return resolver.incidents[source_id]
        if source_type == "project":
            return resolver.projects[source_id]
        return None

    def _source_text(self, source_id: str) -> str:
        record = self._source_record(source_id)
        return " ".join(self._string_values(record)) if record else ""

    @classmethod
    def _string_values(cls, value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            for key in sorted(value):
                if key in {"rumors", "misconceptions"}:
                    continue
                yield from cls._string_values(value[key])
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                yield from cls._string_values(item)

    def _checked_source_ids(self, draft: CharacterDraft) -> tuple[str, ...]:
        candidates = {"world_rules"}
        if draft.faction_id:
            candidates.add(draft.faction_id)
        candidates.update(item.source_id for item in draft.canon_basis)
        if draft.story_link:
            candidates.add(draft.story_link.target_id)
        candidates.update(
            str(item.get("target_id"))
            for item in draft.relationships
            if item.get("target_id")
        )
        return tuple(sorted(item for item in candidates if self._source_type(item)))

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text)).lower()

    @classmethod
    def _proposal_fragments(cls, proposal: str) -> tuple[str, ...]:
        clean = re.sub(
            r"拟议|提案|待确认|建议|新增|新设计|新角色设计|proposed|proposal",
            "",
            proposal,
            flags=re.IGNORECASE,
        )
        return tuple(
            part.strip(" ：:()（）[]【】.-")
            for part in re.split(r"[；;。！？!?\n]|(?:：|:)", clean)
            if len(cls._normalize(part)) >= 5
        )

    def _proposal_asserted_in_narrative(self, proposal: str, narrative: str) -> bool:
        cls = type(self)
        fragments = tuple(cls._normalize(item) for item in cls._proposal_fragments(proposal))
        if not fragments:
            return False
        existing_target_names = tuple(
            cls._normalize(name)
            for _source_id, name in self._existing_canon_entities(proposal)
        )
        proposal_has_interaction = bool(
            re.search(
                r"(?:与|和|向|采访|接触|往来|交接|工作|提交|参与|旁听|会面|拜访|合作|协作)",
                proposal,
            )
        )
        # Modality is local to the clause containing the proposal phrase.  A
        # hedge in a later clause must not erase an earlier accomplished fact.
        clauses = re.split(r"[。！？；，,;!?\n]", narrative)
        for clause in clauses:
            normalized_clause = cls._normalize(clause)
            if not normalized_clause:
                continue
            if any(fragment in normalized_clause for fragment in fragments):
                if any(marker in clause for marker in _HEDGE_MARKERS):
                    continue
                return True
            if proposal_has_interaction and any(
                target in normalized_clause for target in existing_target_names
            ) and any(
                marker in clause
                for marker in ("已经", "已", "曾经", "曾", "长期", "多年", "共同", "持续", "有过")
            ):
                return True
        return False

    @staticmethod
    def _contains_any(text: str, terms: Sequence[str]) -> bool:
        return any(term in text for term in terms)

    @classmethod
    def _has_cross_domain_command_claim(cls, text: str) -> bool:
        # Evaluate each clause independently.  A negated title in one clause
        # must not suppress a positive command claim in the next clause.
        for clause in cls._authority_clauses(text):
            if not clause.strip():
                continue
            if not any(cls._positive_command_match(clause, re.escape(action)) for action in _COMMAND_ACTIONS):
                continue
            domains = {domain for domain in _PUBLIC_SAFETY_DOMAINS if domain in clause}
            if len(domains) >= 2:
                return True
        return False

    @staticmethod
    def _clauses(text: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in re.split(r"[。！？；，,;!?\n]+", text) if item.strip())

    @staticmethod
    def _authority_clauses(text: str) -> tuple[str, ...]:
        # Keep comma-separated domain lists in one command clause.  A comma
        # after a negated title still remains local to this sentence, so a
        # later positive command is not cancelled by the title disclaimer.
        return tuple(item.strip() for item in re.split(r"[。！？；!?\n]+", text) if item.strip())

    @staticmethod
    def _sentence_clauses(text: str) -> tuple[str, ...]:
        return tuple(
            item.strip()
            for item in re.split(r"[。！？；!?\n]+", text)
            if item.strip()
        )

    @classmethod
    def _knowledge_claim_clause(cls, text: str, lore_id: str) -> str:
        """Return the smallest useful claim context for one Lore reference.

        A comma-separated positive and negative claim must remain independent,
        while a postposed clause such as ``lore_025 ... 无访问权`` needs the
        surrounding sentence to connect the target and its access predicate.
        """

        for sentence in cls._sentence_clauses(text):
            if lore_id not in sentence:
                continue
            candidates = tuple(
                item.strip()
                for item in re.split(r"[，,、]|但|但是|而|不过|同时", sentence)
                if item.strip()
            )
            for candidate in candidates:
                if lore_id in candidate and cls._contains_any(
                    candidate, _KNOWLEDGE_ACCESS
                ):
                    return candidate
            return sentence
        return text

    @classmethod
    def _has_local_negation(cls, text: str) -> bool:
        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in _KNOWLEDGE_NEGATION_PATTERNS
        )

    @classmethod
    def _positive_command_match(cls, text: str, pattern: str) -> bool:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            prefix = text[max(0, match.start() - 10) : match.start()]
            # Keep this negation local to the command phrase.  This catches
            # “没有正式指挥头衔” but does not let that title disclaimer cancel
            # “但随后统一调度警察、消防和急救” later in the sentence.
            if re.search(r"(?:不|没有|并非|未|无)(?:正式|实际|明确)?$", prefix):
                continue
            return True
        return False

    @classmethod
    def _has_story_decision_dominance(cls, text: str) -> bool:
        patterns = (
            r"(?:所有|任何|各|每个|关键).{0,8}(?:决定|行动|方案).{0,8}(?:必须|均须|都要|都必须|需要|需).{0,8}(?:经过|取得|获得).{0,8}(?:她|其)",
            r"(?:警察|消防|急救|各部门).{0,12}(?:按|听).{0,5}(?:她|其).{0,5}(?:决定|安排|方案)",
            r"(?:最终|全部).{0,8}(?:由她|由其).{0,8}(?:确认|决定|安排|拍板)",
        )
        for clause in cls._clauses(text):
            if any(cls._positive_match(clause, pattern) for pattern in patterns):
                return True
            if any(cls._positive_match(clause, re.escape(marker)) for marker in _STORY_DECISION_DOMINANCE):
                return True
        return False

    @classmethod
    def _has_secret_central_authority_claim(cls, text: str) -> bool:
        if not (
            cls._contains_any(text, _SECRECY_MARKERS)
            and cls._contains_any(text, _ADMINISTRATIVE_ENTITIES)
            and cls._contains_any(text, _CENTRALIZED_AUTHORITY)
        ):
            return False
        for sentence in cls._sentence_clauses(text):
            if not (
                cls._contains_any(sentence, _SECRECY_MARKERS)
                and cls._contains_any(sentence, _ADMINISTRATIVE_ENTITIES)
                and cls._contains_any(sentence, _CENTRALIZED_AUTHORITY)
            ):
                continue
            for secrecy in _SECRECY_MARKERS:
                for entity in _ADMINISTRATIVE_ENTITIES:
                    for pattern in (
                        re.escape(secrecy) + r".{0,8}" + re.escape(entity),
                        re.escape(entity) + r".{0,8}" + re.escape(secrecy),
                    ):
                        if cls._positive_forbidden_match(sentence, pattern):
                            return True
        return False

    @classmethod
    def _has_universal_sensitive_access(cls, text: str) -> bool:
        for clause in re.split(r"[。！？；，,;!?\n]", text):
            if (
                cls._contains_any(clause, _UNIVERSAL_SCOPE)
                and cls._contains_any(clause, _SENSITIVE_OBJECTS)
                and cls._contains_any(clause, _KNOWLEDGE_ACCESS)
                and not cls._has_local_negation(clause)
            ):
                return True
        return False

    @classmethod
    def _has_elemental_system_claim(cls, text: str) -> bool:
        for clause in cls._sentence_clauses(text):
            categories = {
                category
                for category, markers in _ELEMENT_CATEGORIES.items()
                if cls._contains_any(clause, markers)
            }
            if len(categories) < 2:
                continue
            system_match = next(
                (
                    match
                    for marker in _ELEMENT_SYSTEM_MARKERS
                    for match in re.finditer(re.escape(marker), clause)
                ),
                None,
            )
            if system_match is None:
                continue
            if re.search(_ELEMENTAL_NEGATION_PATTERN, clause[: system_match.start()]):
                continue
            return True
        return False

    @classmethod
    def _minor_frontline_occupation(cls, draft: CharacterDraft) -> bool:
        return draft.age is not None and draft.age < 18 and cls._contains_any(
            draft.occupation, _FRONTLINE_OCCUPATIONS
        )

    @classmethod
    def _is_negated_claim(cls, text: str) -> bool:
        return cls._has_local_negation(text)

    def _iter_canon_entities(self) -> Iterable[tuple[str, str, str]]:
        resolver = self.context.resolver
        for source_type, registry in (
            ("character", resolver.characters),
            ("faction", resolver.factions),
            ("case", resolver.cases),
            ("incident", resolver.incidents),
            ("project", resolver.projects),
        ):
            for source_id, record in registry.items():
                if source_type == "character":
                    name = record.get("name", {})
                    value = name.get("display_name", "") if isinstance(name, Mapping) else ""
                else:
                    value = record.get("name", record.get("title", "")) if isinstance(record, Mapping) else ""
                if isinstance(value, str) and value.strip():
                    yield source_id, source_type, value.strip()
                if source_type == "faction" and isinstance(record, Mapping):
                    internal_structure = record.get("internal_structure")
                    divisions = (
                        internal_structure.get("divisions", [])
                        if isinstance(internal_structure, Mapping)
                        else []
                    )
                    for division in divisions:
                        if not isinstance(division, Mapping):
                            continue
                        division_name = division.get("name")
                        division_id = division.get("id", division_name)
                        if isinstance(division_name, str) and division_name.strip():
                            yield (
                                f"{source_id}:{division_id}",
                                "faction_division",
                                division_name.strip(),
                            )
        for source_id, record in self.context.story_repository.canon.items():
            value = record.get("title", record.get("name", ""))
            if isinstance(value, str) and value.strip():
                yield source_id, "story", value.strip()

    def _existing_canon_entities(self, text: str) -> tuple[tuple[str, str], ...]:
        normalized = self._normalize(text)
        matches: list[tuple[str, str]] = []
        for source_id, _source_type, name in self._iter_canon_entities():
            name_normalized = self._normalize(name)
            # IDs are exact references.  Names are exact, with a conservative
            # long-name containment fallback for registered compound titles.
            if source_id in text or name_normalized in normalized or (
                len(normalized) >= 6 and normalized in name_normalized
            ):
                matches.append((source_id, name))
                continue
            common_prefix = 0
            for left, right in zip(normalized, name_normalized):
                if left != right:
                    break
                common_prefix += 1
            if (
                common_prefix >= 6
                and normalized[common_prefix : common_prefix + 1] in {"为", "是", "的", "与", "和"}
            ):
                matches.append((source_id, name))
        return tuple(sorted(set(matches)))

    @classmethod
    def _local_claim_prefix(cls, text: str, start: int) -> str:
        sentence_start = max(
            (text.rfind(marker, 0, start) for marker in "。！？；!?\n"),
            default=-1,
        ) + 1
        local_start = sentence_start
        for match in re.finditer(r"[，,、]|但|但是|而|不过|同时", text[sentence_start:start]):
            local_start = sentence_start + match.end()
        return text[local_start:start]

    @classmethod
    def _forbidden_introduction_action_polarity(
        cls, text: str, entity_start: int
    ) -> str:
        prefix = cls._local_claim_prefix(text, entity_start)
        action_pattern = "|".join(
            sorted((re.escape(action) for action in _INTRODUCTION_ACTIONS), key=len, reverse=True)
        )
        actions = tuple(re.finditer(action_pattern, prefix))
        if not actions:
            return "UNKNOWN"
        action_prefix = prefix[: actions[-1].start()]
        if re.search(
            r"(?:最终|但|却|只是|不过|同时)?\s*"
            r"(?:从未|未曾|不曾|并未|没有|未|不得|不能|不)\s*"
            r"(?:任何|一个|一项|新的|再)?$",
            action_prefix,
        ):
            return "NEGATIVE"
        if re.search(r"(?:考虑|可能|计划|打算|拟议|准备)\s*$", action_prefix):
            return "HEDGED"
        return "POSITIVE"

    @classmethod
    def _forbidden_claim_is_negated(
        cls,
        text: str,
        start: int,
        end: int | None = None,
        pattern: str | None = None,
    ) -> bool:
        del end
        prefix = cls._local_claim_prefix(text, start)
        if any(
            re.search(denial_pattern, prefix)
            for denial_pattern in _ABSENCE_DENIAL_PATTERNS
        ):
            return True
        if cls._absence_scope_for_forbidden_match(text, start, pattern):
            return True
        return cls._forbidden_introduction_action_polarity(text, start) in {
            "NEGATIVE",
            "HEDGED",
        }

    @classmethod
    def _absence_scope_for_forbidden_match(
        cls, text: str, start: int, pattern: str | None
    ) -> bool:
        if not pattern:
            return False
        polarities = cls._resolve_forbidden_target_polarities(text, start, pattern)
        return polarities.get(start) == "NEGATIVE"

    @classmethod
    def _forbidden_clause_bounds(cls, text: str, position: int) -> tuple[int, int]:
        sentence_start = max(
            (text.rfind(marker, 0, position) for marker in "。！？；，,!?\n"),
            default=-1,
        ) + 1
        clause_start = sentence_start
        for match in re.finditer(
            r"但|但是|然而|不过|而|实际(?:上)?",
            text[sentence_start:position],
        ):
            clause_start = sentence_start + match.end()

        clause_end = len(text)
        for match in re.finditer(r"[。！？；，,!?\n]", text[position:]):
            clause_end = min(clause_end, position + match.start())
        for match in re.finditer(
            r"但|但是|然而|不过|而|实际(?:上)?",
            text[position:],
        ):
            clause_end = min(clause_end, position + match.start())
        return clause_start, clause_end

    @classmethod
    def _forbidden_target_patterns(cls, pattern: str) -> tuple[str, ...]:
        """Return the existing detector patterns relevant to one match path."""

        return tuple(dict.fromkeys((
            pattern,
            *_SECRET_ADMINISTRATIVE_ENTITY_PATTERNS,
            r"秘密.{0,8}(?:政府|行政|监管|管理局|机构|部门|机关)",
        )))

    @classmethod
    def _collect_forbidden_target_spans(
        cls,
        text: str,
        clause_start: int,
        clause_end: int,
        pattern: str,
    ) -> tuple[_ForbiddenTargetSpan, ...]:
        candidates: list[_ForbiddenTargetSpan] = []
        clause = text[clause_start:clause_end]
        for target_pattern in cls._forbidden_target_patterns(pattern):
            for match in re.finditer(target_pattern, clause, re.IGNORECASE):
                matched_text = match.group(0)
                if re.search(
                    rf"(?:{_ABSENCE_COORDINATOR_PATTERN})|[，,。！？；!?\n]",
                    matched_text,
                ):
                    continue
                candidates.append(
                    _ForbiddenTargetSpan(
                        clause_start + match.start(),
                        clause_start + match.end(),
                        cls._normalize(matched_text),
                    )
                )

        # Deterministically collapse exact and overlapping detector hits.  A
        # longer occurrence wins so a generic and literal hit cannot create two
        # coordinate items for the same target.
        normalized: list[_ForbiddenTargetSpan] = []
        for candidate in sorted(
            candidates,
            key=lambda item: (item.start, -(item.end - item.start), item.end),
        ):
            overlaps = [
                index
                for index, existing in enumerate(normalized)
                if candidate.start < existing.end and existing.start < candidate.end
            ]
            if not overlaps:
                normalized.append(candidate)
                continue
            longest = max(
                (normalized[index] for index in overlaps),
                key=lambda item: (item.end - item.start, -item.start),
            )
            if candidate.end - candidate.start > longest.end - longest.start:
                normalized = [
                    existing
                    for existing in normalized
                    if existing not in {normalized[index] for index in overlaps}
                ]
                normalized.append(candidate)
        return tuple(sorted(normalized, key=lambda item: (item.start, item.end)))

    @classmethod
    def _resolve_forbidden_target_polarities(
        cls, text: str, start: int, pattern: str
    ) -> dict[int, str]:
        """Resolve all forbidden targets in the containing clause together."""

        clause_start, clause_end = cls._forbidden_clause_bounds(text, start)
        targets = cls._collect_forbidden_target_spans(
            text, clause_start, clause_end, pattern
        )
        current = next(
            (target for target in targets if target.start <= start < target.end),
            None,
        )
        if current is None:
            return {}

        clause = text[clause_start:clause_end]
        relative_targets = tuple(
            (target.start - clause_start, target.end - clause_start)
            for target in targets
        )
        predicate_matches = tuple(re.finditer(_ABSENCE_PREDICATE_PATTERN, clause))
        absence_scope = False
        if predicate_matches and relative_targets:
            predicate = predicate_matches[-1]
            first_start, _first_end = relative_targets[0]
            initial_gap = clause[predicate.end() : first_start]
            if not initial_gap or re.fullmatch(
                r"\s*(?:任何|一个|一项|此类|相关|新的)?\s*", initial_gap
            ):
                absence_scope = all(
                    re.fullmatch(
                        rf"\s*(?:{_ABSENCE_COORDINATOR_PATTERN})\s*",
                        clause[previous_end:current_start],
                    )
                    for (_previous_start, previous_end), (current_start, _current_end)
                    in zip(relative_targets, relative_targets[1:])
                )
                if first_start < predicate.end():
                    absence_scope = False

        polarities = {
            target.start: "NEGATIVE" if absence_scope else "UNKNOWN"
            for target in targets
        }
        for target in targets:
            action_polarity = cls._forbidden_introduction_action_polarity(
                text, target.start
            )
            if action_polarity in {"NEGATIVE", "HEDGED"}:
                polarities[target.start] = "NEGATIVE"
        return polarities

    @classmethod
    def _positive_forbidden_match(cls, text: str, pattern: str) -> bool:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if not cls._forbidden_claim_is_negated(
                text, match.start(), match.end(), pattern
            ):
                return True
        return False

    @classmethod
    def _classify_proposal_entity_usage(
        cls,
        text: str,
        existing_entities: Sequence[tuple[str, str]],
    ) -> str:
        if not existing_entities:
            return "AMBIGUOUS"

        for _source_id, name in existing_entities:
            target = re.escape(name)
            if re.search(rf"(?:与|和|向).{{0,30}}{target}", text):
                return "RELATION_TO_EXISTING"
            if re.search(rf"(?:在|进入|加入|作为).{{0,30}}{target}", text):
                return "MEMBERSHIP_OR_ASSIGNMENT_TO_EXISTING"

        if any(marker in text for marker in _PROPOSAL_ENTITY_INTRODUCTION):
            return "ENTITY_ITSELF_AS_NEW"

        normalized = cls._normalize(text)
        for _source_id, name in existing_entities:
            normalized = normalized.replace(cls._normalize(name), "")
        context = re.sub(r"拟议|提案|待确认|建议|proposed|proposal", "", normalized, flags=re.IGNORECASE)
        if len(context) >= 4:
            return "RELATION_TO_EXISTING"
        return "AMBIGUOUS"

    def _resolve_story_targets_from_text(
        self,
        draft: CharacterDraft,
        request: CharacterDesignRequest | None,
    ) -> frozenset[str]:
        targets: set[str] = set()
        if draft.story_link and self._source_type(draft.story_link.target_id) in {"story", "case", "incident"}:
            targets.add(draft.story_link.target_id)
        context_text = " ".join(
            (
                draft.background,
                draft.story_hook,
                draft.design_pitch,
                *(request.desired_connections if request else ()),
                *(request.hard_constraints if request else ()),
                request.brief if request else "",
            )
        )
        for source_id, source_type, name in self._iter_canon_entities():
            if source_type not in {"story", "case", "incident"}:
                continue
            if source_id in context_text or self._normalize(name) in self._normalize(context_text):
                targets.add(source_id)
        return frozenset(targets)

    @classmethod
    def _match_is_negated(cls, text: str, start: int) -> bool:
        prefix = text[max(0, start - 8) : start]
        return any(prefix.endswith(marker) for marker in _NEGATION_PREFIXES)

    @classmethod
    def _positive_match(cls, text: str, pattern: str) -> bool:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if not cls._match_is_negated(text, match.start()):
                return True
        return False

    @classmethod
    def _ability_replaces_expertise(cls, text: str) -> bool:
        profession = r"急救|医疗|诊断|犯罪调查|侦查|专业知识|专业训练|身体训练|现实资源"
        replacement = r"无需|不需要|直接完成|完全替代|取代|自动完成"
        return bool(
            re.search(rf"(?:{replacement}).{{0,12}}(?:{profession})", text)
            or re.search(rf"(?:{profession}).{{0,12}}(?:{replacement})", text)
        )

    @staticmethod
    def _unbounded_control_ability(text: str) -> bool:
        return bool(
            re.search(
                r"(?:永久|无条件|随时|一眼).{0,8}(?:控制|支配|改写).{0,8}(?:任何人|所有人|思想|意志)",
                text,
            )
        )

    @classmethod
    def _first_secret_institution_field(cls, draft: CharacterDraft) -> str | None:
        legacy_pattern = r"秘密.{0,8}(?:政府|行政|监管|管理局|机构|部门|机关)"
        for field in (*_TEXT_FIELDS, "proposed_new_content", "new_design_elements"):
            value = getattr(draft, field)
            text = " ".join(value) if isinstance(value, tuple) else value
            if (
                any(
                    cls._positive_forbidden_match(text, pattern)
                    for pattern in _SECRET_ADMINISTRATIVE_ENTITY_PATTERNS
                )
                or cls._positive_forbidden_match(text, legacy_pattern)
                or cls._has_secret_central_authority_claim(text)
            ):
                return field
        return None

    @classmethod
    def _forbidden_pattern_field(
        cls, pattern: str, draft: CharacterDraft
    ) -> str | None:
        normalized_pattern = cls._normalize(pattern)
        secret_government_detector = "政府" in pattern and "管理局" in pattern
        secret_facility_detector = "秘密机构" in pattern and "实验室" in pattern
        conspiracy_detector = "幕后" in pattern and "组织" in pattern
        elemental_detector = all(marker in pattern for marker in ("火", "水", "雷"))
        for field in (*_TEXT_FIELDS, "proposed_new_content", "new_design_elements"):
            value = getattr(draft, field)
            text = " ".join(value) if isinstance(value, tuple) else value
            normalized = cls._normalize(text)
            if len(normalized_pattern) >= 6 and normalized_pattern in normalized:
                direct_match = re.search(re.escape(pattern), text, re.IGNORECASE)
                if direct_match is None or not cls._forbidden_claim_is_negated(
                    text,
                    direct_match.start(),
                    direct_match.end(),
                    re.escape(pattern),
                ):
                    return field
            if secret_government_detector and (
                any(
                    cls._positive_forbidden_match(text, pattern)
                    for pattern in _SECRET_ADMINISTRATIVE_ENTITY_PATTERNS
                )
                or cls._has_secret_central_authority_claim(text)
            ):
                return field
            if secret_facility_detector and cls._positive_forbidden_match(
                text, r"(?:互不相干|不断增加|新增).{0,12}(?:秘密机构|实验室|收容设施)|秘密(?:实验室|收容设施)"
            ):
                return field
            if conspiracy_detector and cls._positive_forbidden_match(
                text, r"(?:所有|一切|每个).{0,12}(?:事件|事故).{0,12}(?:幕后|邪恶).{0,8}组织"
            ):
                return field
            if elemental_detector and cls._has_elemental_system_claim(text):
                return field
        return None

    @classmethod
    def _all_draft_text(cls, draft: CharacterDraft) -> str:
        # constraint_notes records how the draft satisfies or interprets the
        # request.  It is evidence about the proposal, not proposal content;
        # including it here makes merely echoing a forbidden term look like a
        # forbidden design element.
        values = [str(getattr(draft, field)) for field in _TEXT_FIELDS]
        values.extend(draft.personality)
        values.extend(draft.new_design_elements)
        values.extend(draft.proposed_new_content)
        return " ".join(values)

    @classmethod
    def _forbidden_request_matches(cls, forbidden: str, draft_text: str) -> bool:
        if cls._normalize(forbidden) in cls._normalize(draft_text):
            direct_match = re.search(re.escape(forbidden), draft_text, re.IGNORECASE)
            if direct_match is None or not cls._forbidden_claim_is_negated(
                draft_text,
                direct_match.start(),
                direct_match.end(),
                re.escape(forbidden),
            ):
                return True
        if "秘密" in forbidden and any(
            marker in forbidden for marker in ("政府", "行政", "监管", "机构", "组织")
        ):
            return any(
                cls._positive_forbidden_match(draft_text, pattern)
                for pattern in _SECRET_ADMINISTRATIVE_ENTITY_PATTERNS
            )
        return False

    def _faction_role_conflict(self, draft: CharacterDraft, faction_id: str) -> bool:
        faction = self.context.resolver.factions.get(faction_id)
        if faction is None:
            return False
        faction_type = str(faction.get("type", ""))
        role_text = " ".join((draft.occupation, draft.social_role))
        if self._positive_match(
            role_text,
            r"独立行政机关|行政执法权|秘密监管|全市警务总指挥|城市警务总指挥",
        ):
            return True
        domain_patterns = {
            "academic": r"警务总指挥|消防总指挥|行政执法|城市监管负责人",
            "community": r"警务总指挥|消防总指挥|行政执法|城市监管负责人",
            "professional_association": r"警务总指挥|消防总指挥|行政执法",
            "corporation": r"警务总指挥|消防总指挥|行政执法",
            "media": r"警务总指挥|消防总指挥|行政执法",
            "public_service": r"全城能力监管最高负责人|公共安全联席体系最高负责人|统领全市",
        }
        pattern = domain_patterns.get(faction_type)
        return bool(pattern and self._positive_match(role_text, pattern))

    @classmethod
    def _story_overreach_field(cls, draft: CharacterDraft) -> str | None:
        pattern = r"领导.{0,10}(?:事故|事件|应急处置)|全权指挥|最终解决|真正的?(?:负责人|幕后真凶)|唯一关键证人|核心负责人|主导.{0,8}(?:事故|事件)"
        for field in ("background", "story_hook", "design_pitch"):
            text = getattr(draft, field)
            if cls._positive_match(text, pattern) or cls._has_story_decision_dominance(text):
                return field
        return None

    @staticmethod
    def _age_bounds(text: str) -> tuple[int, int] | None:
        match = re.search(r"(\d+)\s*[～至到\-]\s*(\d+)\s*岁?", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r"(\d+)\s*岁左右", text)
        if match:
            value = int(match.group(1))
            return value - 2, value + 2
        return None

    @staticmethod
    def _finding(
        code: CanonFindingCode,
        severity: FindingSeverity,
        field_path: str,
        message: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> CanonFinding:
        return CanonFinding(
            code,
            severity,
            field_path,
            message,
            tuple(sorted(set(evidence_ids))),
        )

    def _invalid_reference(self, field_path: str, source_id: str) -> CanonFinding:
        return self._finding(
            CanonFindingCode.INVALID_CANON_REFERENCE,
            FindingSeverity.ERROR,
            field_path,
            f"Canon reference {source_id!r} does not exist or has the wrong source type.",
        )

    @staticmethod
    def _deduplicate_and_sort(
        findings: Iterable[CanonFinding],
    ) -> tuple[CanonFinding, ...]:
        unique: dict[
            tuple[CanonFindingCode, str, tuple[str, ...]], CanonFinding
        ] = {}
        for finding in findings:
            key = (finding.code, finding.field_path, finding.evidence_ids)
            unique.setdefault(key, finding)
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (
                    _SEVERITY_ORDER[item.severity],
                    item.field_path,
                    item.code.value,
                    item.evidence_ids,
                    item.message,
                ),
            )
        )


__all__ = [
    "CanonCheckContext",
    "CanonCheckReport",
    "CanonCheckStatus",
    "CanonCheckSummary",
    "CanonChecker",
    "CanonFinding",
    "CanonFindingCode",
    "FindingSeverity",
]
