"""Small, deterministic Character Generation Benchmark v0.1.

This module is deliberately a fixture runner, not a second character schema or
mechanic system.  It drives the existing CharacterGenerationAgent,
CanonChecker, CharacterAuthoringWorkflow, and repair boundary with small
auditable drafts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from knowledge import KnowledgeResolver
from story import StoryRepository, load_story_repository

from .canon_checker import CanonCheckReport, CanonCheckStatus, CanonFindingCode, CanonChecker
from .character_generation import CharacterDesignRequest, CharacterDraft, CharacterGenerationAgent
from .character_repair import (
    CharacterAuthoringResult,
    CharacterAuthoringWorkflow,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
    build_repair_scope,
    changed_fields,
)
from .model_protocol import ScriptedAgentModel
from .models import ModelTurn, ToolCall
from .response_contracts import CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL


CORE_CASE_IDS = ("A", "B", "C", "D")
WATCH_CASE_IDS = ("E", "F")
ALL_CASE_IDS = CORE_CASE_IDS + WATCH_CASE_IDS


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    request: CharacterDesignRequest
    initial_payload: Mapping[str, Any]
    repaired_payload: Mapping[str, Any] | None = None
    watch: bool = False
    watch_observation: str = ""
    representation_pressure: bool = False


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    blocking: bool
    initial_report: CanonCheckReport
    final_report: CanonCheckReport
    initial_draft: CharacterDraft
    final_draft: CharacterDraft
    authoring_result: CharacterAuthoringResult
    repair_triggered: bool
    repair_succeeded: bool
    minimal_repair: bool
    accepted: bool
    failure_reason: str | None = None
    watch_observation: str = ""
    representation_pressure: bool = False


@dataclass(frozen=True)
class BenchmarkMetrics:
    evaluable_core_cases: int
    first_pass_passes: int
    repair_attempts: int
    repair_successes: int
    minimal_repairs: int
    final_end_to_end_passes: int

    @property
    def first_pass_pass_rate(self) -> float:
        return _rate(self.first_pass_passes, self.evaluable_core_cases)

    @property
    def repair_success_rate(self) -> float:
        return _rate(self.repair_successes, self.repair_attempts)

    @property
    def minimal_repair_rate(self) -> float:
        return _rate(self.minimal_repairs, self.repair_successes)

    @property
    def final_end_to_end_pass_rate(self) -> float:
        return _rate(self.final_end_to_end_passes, self.evaluable_core_cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluable_core_cases": self.evaluable_core_cases,
            "first_pass_pass_rate": self.first_pass_pass_rate,
            "repair_success_rate": self.repair_success_rate,
            "minimal_repair_rate": self.minimal_repair_rate,
            "final_end_to_end_pass_rate": self.final_end_to_end_pass_rate,
            "first_pass_passes": self.first_pass_passes,
            "repair_attempts": self.repair_attempts,
            "repair_successes": self.repair_successes,
            "minimal_repairs": self.minimal_repairs,
            "final_end_to_end_passes": self.final_end_to_end_passes,
        }


def benchmark_cases() -> tuple[BenchmarkCase, ...]:
    """Return fresh immutable benchmark definitions with no Canon corpus data."""

    return (
        BenchmarkCase(
            "A",
            CharacterDesignRequest(
                "设计一个攻击会积累个人战斗充能，充能满后可使用强化能力并在使用后重置的角色。",
                request_id="benchmark_a_normal_loop",
            ),
            _draft_payload(
                "draft_benchmark_a",
                name="岑遥",
                combat_role_profile={"primary_role": None, "secondary_roles": []},
                design_pitch="以命中积累个人战斗充能，满值后开放一次强化能力。",
                ability_concept="攻击命中会积累战斗充能；充能达到满值后获得强化能力，使用该能力会消耗并重置充能。",
            ),
        ),
        BenchmarkCase(
            "B",
            CharacterDesignRequest(
                "设计一个主要依靠普通能力使用和冷却节奏作战的直接攻击者，不要加入个人积累条或角色专属资源。",
                forbidden_elements=("个人积累条", "角色专属资源", "充能循环"),
                request_id="benchmark_b_no_special_resource",
            ),
            _draft_payload(
                "draft_benchmark_b",
                name="陆衡",
                combat_role_profile={"primary_role": None, "secondary_roles": []},
                design_pitch="通过普通攻击、技能使用和冷却节奏造成稳定伤害。",
                ability_concept="普通攻击与技能按照各自冷却时间循环使用，直接形成稳定的攻击节奏。",
            ),
        ),
        BenchmarkCase(
            "C",
            CharacterDesignRequest(
                "设计一个保持个人经历为原创的辅助角色。",
                request_id="benchmark_c_minimal_repair",
            ),
            _draft_payload(
                "draft_benchmark_c",
                name="闻溪",
                relationships=(
                    {
                        "target_id": "char_launch_001",
                        "description": "已建立的直属合作关系",
                        "status": "canon_backed",
                    },
                ),
            ),
            repaired_payload=_draft_payload(
                "draft_benchmark_c",
                name="闻溪",
                relationships=(
                    {
                        "target_id": "char_launch_001",
                        "description": "拟议中的合作关系，仍待审核",
                        "status": "proposed",
                    },
                ),
            ),
        ),
        BenchmarkCase(
            "D",
            CharacterDesignRequest(
                "设计一个不提供团队协同的专职全队治疗者；如果要求冲突，必须如实保留冲突。",
                hard_constraints=("不得提供团队协同", "必须是全队治疗者"),
                forbidden_elements=("全队治疗",),
                request_id="benchmark_d_impossible_brief",
            ),
            _draft_payload(
                "draft_benchmark_d",
                name="顾临",
                combat_role_profile={"primary_role": None, "secondary_roles": []},
                design_pitch="这是一个无法同时满足的要求组合，保留原问题供人工决定。",
                ability_concept="核心能力明确要求为全队治疗，但这与不得提供团队协同相冲突。",
                open_questions=("不提供团队协同与专职全队治疗发生冲突，不能同时成立，必须先澄清硬约束。",),
                constraint_notes=("保留两个互相冲突的硬要求，不用假折中掩盖冲突。",),
            ),
        ),
        BenchmarkCase(
            "E",
            CharacterDesignRequest(
                "设计一个离场角色，在当前队友完成指定动作后自动响应。",
                request_id="benchmark_e_external_teammate_event",
            ),
            _draft_payload(
                "draft_benchmark_e",
                name="苏弦",
                design_pitch="离场时等待当前队友的指定动作。",
                ability_concept="当前队友命中特定目标后，角色自动响应一次；触发主体和队友事件目前只能用文字表达。",
            ),
            watch=True,
            watch_observation="外部队友触发被保留在 ability_concept 文字中，但 CharacterDraft 没有独立的队友事件主体字段。",
            representation_pressure=True,
        ),
        BenchmarkCase(
            "F",
            CharacterDesignRequest(
                "设计一个能创建临时自主召唤物、持续一段时间并独立攻击的角色。",
                request_id="benchmark_f_independent_summon",
            ),
            _draft_payload(
                "draft_benchmark_f",
                name="唐栖",
                combat_role_profile={"primary_role": "control", "secondary_roles": []},
                design_pitch="创建临时自主召唤物，召唤物会独立攻击一段时间。",
                ability_concept="角色创建一个持续一段时间的自主召唤物；召唤物独立寻找目标并攻击。当前表示仍是单段能力文字。",
            ),
            watch=True,
            watch_observation="独立召唤物和持续时间被保留在 ability_concept 文字中，但没有独立 summon 实体或生命周期字段。",
            representation_pressure=True,
        ),
    )


def run_benchmark(cases: tuple[BenchmarkCase, ...] | None = None) -> tuple[BenchmarkCaseResult, ...]:
    """Run all six cases offline through the existing authoring workflow."""

    selected = cases or benchmark_cases()
    if len(selected) != len(ALL_CASE_IDS) or {case.case_id for case in selected} != set(ALL_CASE_IDS):
        raise ValueError(f"benchmark must contain exactly cases {ALL_CASE_IDS}")
    resolver = KnowledgeResolver()
    story_repository = load_story_repository()
    checker = CanonChecker(resolver=resolver, story_repository=story_repository)
    results = tuple(_run_case(case, resolver, story_repository, checker) for case in selected)
    return tuple(sorted(results, key=lambda result: ALL_CASE_IDS.index(result.case_id)))


def compute_metrics(results: tuple[BenchmarkCaseResult, ...]) -> BenchmarkMetrics:
    """Compute only the four v0.1 metrics; watch cases never enter a denominator."""

    core = tuple(result for result in results if result.blocking)
    repair_attempts = sum(result.repair_triggered for result in core)
    repair_successes = sum(result.repair_succeeded for result in core)
    return BenchmarkMetrics(
        evaluable_core_cases=len(core),
        first_pass_passes=sum(result.initial_report.status == CanonCheckStatus.PASS for result in core),
        repair_attempts=repair_attempts,
        repair_successes=repair_successes,
        minimal_repairs=sum(result.minimal_repair for result in core),
        final_end_to_end_passes=sum(result.accepted for result in core),
    )


def case_a_alignment_failures(draft: CharacterDraft) -> tuple[str, ...]:
    """Narrow fixture-specific checks for the requested charge/payoff loop."""

    text = _draft_mechanic_text(draft)
    failures: list[str] = []
    for label, markers in (
        ("accumulation", ("命中", "积累", "充能")),
        ("threshold", ("满",)),
        ("empowered_payoff", ("强化能力",)),
        ("consumption_or_reset", ("消耗", "重置")),
    ):
        if not all(marker in text for marker in markers):
            failures.append(f"missing {label}")
    if any(marker in text for marker in ("召唤物", "独立召唤", "全队治疗")):
        failures.append("unrelated major mechanic present")
    return tuple(failures)


def case_b_over_invention_findings(draft: CharacterDraft) -> tuple[str, ...]:
    """Detect only obvious personal-resource vocabulary for this fixture."""

    text = _draft_mechanic_text(draft)
    prohibited = (
        "个人积累条",
        "角色专属资源",
        "专属资源",
        "个人资源",
        "角色资源",
        "资源循环",
        "资源条",
        "充能循环",
        "能量条",
        "层数",
    )
    return tuple(f"prohibited personal resource marker: {marker}" for marker in prohibited if marker in text)


def repaired_draft_is_minimal(
    request: CharacterDesignRequest,
    initial: CharacterDraft,
    repaired: CharacterDraft,
    initial_report: CanonCheckReport,
) -> bool:
    """Compare top-level JSON fields against the real repair scope."""

    changed = set(changed_fields(initial, repaired))
    scope = build_repair_scope(request, initial_report)
    finding_roots = set(scope.finding_fields)
    return bool(changed) and changed <= set(scope.editable_fields) and changed <= finding_roots


def _run_case(
    case: BenchmarkCase,
    resolver: KnowledgeResolver,
    story_repository: StoryRepository,
    checker: CanonChecker,
) -> BenchmarkCaseResult:
    generated_turns = []
    if case.case_id == "C":
        generated_turns.append(ModelTurn(tool_calls=(ToolCall("character", "get_character", {"character_id": "char_launch_001"}),)))
    generated_turns.append(ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL))
    generated_turns.append(_draft_turn(case.initial_payload))
    generation = CharacterGenerationAgent(
        ScriptedAgentModel(generated_turns),
        resolver=resolver,
        story_repository=story_repository,
    )
    if case.repaired_payload is not None:
        repair_model = ScriptedAgentModel([_draft_turn(case.repaired_payload)])
    elif case.case_id == "D":
        repair_model = ScriptedAgentModel([_draft_turn(case.initial_payload)])
    else:
        repair_model = DeterministicCharacterRepairModel()
    workflow = CharacterAuthoringWorkflow(
        generation,
        CharacterRepairAgent(repair_model, checker=checker),
        checker=checker,
    )
    authored = workflow.run(case.request)
    initial = authored.initial_draft
    final = authored.final_draft
    initial_report = authored.initial_check
    final_report = authored.final_check
    repair = authored.repair_result
    minimal = (
        repair.repair_succeeded
        and repair.repaired_draft is not None
        and repaired_draft_is_minimal(case.request, initial, repair.repaired_draft, initial_report)
    )
    accepted, reason = _accepted(case, authored)
    return BenchmarkCaseResult(
        case.case_id,
        not case.watch,
        initial_report,
        final_report,
        initial,
        final,
        authored,
        repair.repair_attempted,
        repair.repair_succeeded,
        minimal,
        accepted,
        reason,
        case.watch_observation,
        case.representation_pressure,
    )


def _accepted(case: BenchmarkCase, authored: CharacterAuthoringResult) -> tuple[bool, str | None]:
    if case.watch:
        return True, None
    if case.case_id == "A":
        failures = case_a_alignment_failures(authored.final_draft)
        if authored.final_check.status != CanonCheckStatus.PASS:
            failures += ("final Canon validation did not pass",)
        return (not failures, "; ".join(failures) if failures else None)
    if case.case_id == "B":
        failures = case_b_over_invention_findings(authored.final_draft)
        if authored.final_check.status != CanonCheckStatus.PASS:
            failures += ("final Canon validation did not pass",)
        return (not failures, "; ".join(failures) if failures else None)
    if case.case_id == "C":
        findings = {(finding.code, finding.field_path) for finding in authored.initial_check.findings}
        repair = authored.repair_result
        changed = set(repair.changed_fields)
        initial_findings = {(finding.code, finding.field_path) for finding in authored.initial_check.findings}
        final_findings = {(finding.code, finding.field_path) for finding in authored.final_check.findings}
        failures: list[str] = []
        if (CanonFindingCode.UNSUPPORTED_CANON_CLAIM, "relationships[0].status") not in findings:
            failures.append("unsupported Canon relationship finding was not detected")
        if not repair.repair_attempted:
            failures.append("repair was not triggered")
        if not repair.repair_succeeded:
            failures.append("repair did not succeed")
        if final_findings & initial_findings:
            failures.append("offending finding remained after repair")
        if changed != {"relationships"}:
            failures.append(f"unexpected changed fields: {sorted(changed)}")
        if authored.final_check.status != CanonCheckStatus.PASS:
            failures.append("final Canon validation did not pass")
        return (not failures, "; ".join(failures) if failures else None)
    if case.case_id == "D":
        unchanged = authored.final_draft.to_dict() == authored.initial_draft.to_dict()
        truthful = (
            authored.final_check.status == CanonCheckStatus.FAIL
            and any("冲突" in item for item in authored.final_draft.open_questions)
            and any("冲突" in item for item in authored.final_draft.constraint_notes)
            and unchanged
        )
        return truthful, None if truthful else "workflow discarded or concealed the contradictory hard requirements"
    raise ValueError(f"unknown core case: {case.case_id}")


def _draft_turn(payload: Mapping[str, Any]) -> ModelTurn:
    data = json.loads(json.dumps(payload, ensure_ascii=False))
    return ModelTurn(text=json.dumps(data, ensure_ascii=False, separators=(",", ":")), structured_output=data)


def _draft_payload(
    draft_id: str,
    *,
    name: str,
    combat_role_profile: Mapping[str, Any] | None = None,
    design_pitch: str = "原创角色设计，保持有限且清晰的个人能力边界。",
    ability_concept: str = "通过普通能力使用与有限个人技巧提供战斗作用。",
    relationships: tuple[Mapping[str, Any], ...] = (),
    open_questions: tuple[str, ...] = ("具体表现仍待后续创作确认。",),
    constraint_notes: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "status": "draft",
        "name": name,
        "canonical_character_id": None,
        "age": 24,
        "age_range": "20-25",
        "gender": "未指定",
        "faction_id": None,
        "occupation": "独立行动者",
        "social_role": "新角色设计中的行动者",
        "combat_role_profile": dict(
            combat_role_profile
            if combat_role_profile is not None
            else {"primary_role": "support", "secondary_roles": []}
        ),
        "design_pitch": design_pitch,
        "personality": ["清醒", "克制"],
        "background": "个人经历保持原创，不宣称既有 Canon 事件中的官方身份。",
        "story_hook": "后续可围绕个人选择展开新的原创支线。",
        "relationships": [dict(item) for item in relationships],
        "ability_concept": ability_concept,
        "knowledge_scope": "仅接触公开信息和本人亲历的事项。",
        "canon_basis": [],
        "new_design_elements": ["姓名、性格与个人经历均为新角色设计。"],
        "open_questions": list(open_questions),
        "constraint_notes": list(constraint_notes),
        "story_link": None,
        "proposed_new_content": [],
    }


def _draft_mechanic_text(draft: CharacterDraft) -> str:
    return " ".join((draft.design_pitch, draft.ability_concept, *draft.new_design_elements))


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


__all__ = [
    "ALL_CASE_IDS",
    "BenchmarkCase",
    "BenchmarkCaseResult",
    "BenchmarkMetrics",
    "CORE_CASE_IDS",
    "WATCH_CASE_IDS",
    "benchmark_cases",
    "case_a_alignment_failures",
    "case_b_over_invention_findings",
    "compute_metrics",
    "repaired_draft_is_minimal",
    "run_benchmark",
]
