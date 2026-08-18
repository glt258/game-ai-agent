"""Thin orchestration and presentation for Official Character Authoring Demo v0.1.1.

The module intentionally delegates generation, checking, and repair to the
frozen production components.  Its only domain-specific work is loading a
bounded, read-only view of the existing external reference corpus and
rendering the resulting audit for a planner.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from reference_corpus.loader import load_corpus_manifest, load_game_catalog
from reference_corpus.repository import CharacterReferenceRepository

from .canon_checker import CanonCheckStatus, CanonChecker, CanonFindingCode
from .character_generation import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    CharacterGenerationResult,
    DeterministicCharacterGenerationModel,
)
from .character_repair import (
    CharacterAuthoringResult,
    CharacterAuthoringWorkflow,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
)
from .errors import AgentError, ModelError, ModelMalformedResponseError
from .model_factory import character_model_from_environment


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_ROOT = ROOT / "data" / "reference_corpus" / "characters"


@dataclass(frozen=True)
class ReferenceGrounding:
    corpus_version: str
    total_records: int
    selected: tuple[Mapping[str, Any], ...]

    @property
    def reference_ids(self) -> tuple[str, ...]:
        return tuple(
            item["reference_id"]
            for item in self.selected
            if isinstance(item.get("reference_id"), str)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_version": self.corpus_version,
            "total_records": self.total_records,
            "selected": [dict(item) for item in self.selected],
        }


@dataclass(frozen=True)
class OfficialCharacterAuthoringRun:
    request: CharacterDesignRequest
    generation: CharacterGenerationResult
    authoring: CharacterAuthoringResult
    references: ReferenceGrounding
    source_labels: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        generation_audit = {
            "request_id": self.generation.audit.request_id,
            "tool_rounds": self.generation.audit.tool_rounds,
            "tool_calls": [
                {
                    "round": item.round,
                    "tool": item.tool_name,
                    "result": item.result_status,
                    "source_ids": list(item.allowed_lore_ids),
                }
                for item in self.generation.audit.tool_calls
            ],
            "source_ids": list(self.generation.audit.source_ids),
            "reference_ids": list(self.generation.audit.reference_ids),
            "normalized_fields": list(self.generation.audit.normalized_fields),
            "model_invocations": [asdict(item) for item in self.generation.audit.model_invocations],
        }
        return {
            "request": self.request.to_dict(),
            "references": self.references.to_dict(),
            "source_labels": dict(self.source_labels),
            "generation": {
                "draft": self.generation.draft.to_dict(),
                "sources": list(self.generation.sources),
                "audit": generation_audit,
            },
            "authoring": self.authoring.to_dict(),
        }


class _RecordingGenerationAgent:
    """Keep the production workflow unchanged while exposing its result."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.result: CharacterGenerationResult | None = None

    def generate(self, request: CharacterDesignRequest) -> CharacterGenerationResult:
        self.result = self.delegate.generate(request)
        return self.result


def load_reference_grounding(
    brief: str,
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    limit: int = 3,
) -> ReferenceGrounding:
    """Load and select bounded reference summaries from the real corpus.

    The selection is lexical and deliberately shallow: references provide
    precedent for role/mechanic granularity, while project Canon still comes
    only from the existing authoring tools and CanonChecker.
    """

    if limit < 1:
        raise ValueError("limit must be positive")
    corpus_root = Path(corpus_root)
    catalog = load_game_catalog(corpus_root / "_catalog" / "games.yaml")
    manifest = load_corpus_manifest(corpus_root / "_catalog" / "corpus_manifest.yaml")
    repository = CharacterReferenceRepository(corpus_root, catalog=catalog)
    references = repository.list_all()
    query = _tokens(brief)
    ranked: list[tuple[int, str, Mapping[str, Any]]] = []
    for reference in references:
        summary = _reference_summary(reference)
        haystack = _tokens(json.dumps(summary, ensure_ascii=False))
        score = sum(1 for token in query if token in haystack)
        ranked.append((score, str(summary["reference_id"]), summary))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ReferenceGrounding(
        manifest.corpus_version,
        len(references),
        tuple(item[2] for item in ranked[:limit]),
    )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]*|[\u4e00-\u9fff]{2,}", value.lower())
        if token
    }


def _reference_summary(reference: Any) -> dict[str, Any]:
    facts = reference.facts
    identity = facts.identity
    names = identity.names
    combat = facts.combat
    taxonomy = dict(combat.native_taxonomy.labels) if combat else {}
    roles: list[str] = []
    if reference.analysis is not None:
        roles = [str(role.value) for role in reference.analysis.combat_design.normalized_roles]
    if not roles:
        roles = [str(value) for key, value in taxonomy.items() if "role" in key.lower()]
    categories = []
    if combat:
        categories = [
            str(ability.normalized_category or ability.native_category)
            for ability in combat.abilities
            if ability.normalized_category or ability.native_category
        ][:6]
    return {
        "reference_id": reference.reference_id,
        "display_name": names.canonical,
        "game_id": identity.game_id,
        "roles": roles,
        "occupation": facts.narrative.occupation if facts.narrative else None,
        "ability_categories": categories,
        "taxonomy": taxonomy,
    }


class OfficialCharacterAuthoringDemo:
    """Coordinate the existing production authoring pipeline and render it."""

    def __init__(
        self,
        *,
        generation_model: Any | None = None,
        repair_model: Any | None = None,
        reference_grounding: ReferenceGrounding | None = None,
        generation_agent: Any | None = None,
        repair_agent: CharacterRepairAgent | None = None,
        checker: CanonChecker | None = None,
    ) -> None:
        self.references = reference_grounding or load_reference_grounding("")
        self.checker = checker or CanonChecker()
        self.generation_agent = generation_agent or CharacterGenerationAgent(
            generation_model or DeterministicCharacterGenerationModel(),
            reference_context=self.references.selected,
        )
        self.repair_agent = repair_agent or CharacterRepairAgent(
            repair_model or DeterministicCharacterRepairModel(),
            checker=self.checker,
        )

    def run(self, request: CharacterDesignRequest) -> OfficialCharacterAuthoringRun:
        recorder = _RecordingGenerationAgent(self.generation_agent)
        workflow = CharacterAuthoringWorkflow(
            recorder,
            self.repair_agent,
            checker=self.checker,
        )
        authoring = workflow.run(request)
        if recorder.result is None:
            raise RuntimeError("production generation did not return a result")
        source_ids = set(recorder.result.sources) | set(authoring.final_check.checked_source_ids)
        labels = tuple(
            (source_id, _source_label(self.checker, source_id))
            for source_id in sorted(source_ids)
        )
        return OfficialCharacterAuthoringRun(
            request,
            recorder.result,
            authoring,
            self.references,
            labels,
        )


def make_demo(
    *,
    mode: str,
    scenario: str,
    brief: str,
    provider: str | None = None,
    model_name: str | None = None,
) -> OfficialCharacterAuthoringDemo:
    references = load_reference_grounding(brief)
    if mode == "offline":
        generation_model = DeterministicCharacterGenerationModel(scenario=scenario)
        repair_model = DeterministicCharacterRepairModel()
    else:
        environment = dict(os.environ)
        if provider is not None:
            environment["NPC_LLM_PROVIDER"] = provider
        if model_name is not None:
            environment["NPC_LLM_MODEL"] = model_name
        generation_model = character_model_from_environment(
            environment=environment,
            mode_override="live",
        )
        repair_model = generation_model
    return OfficialCharacterAuthoringDemo(
        generation_model=generation_model,
        repair_model=repair_model,
        reference_grounding=references,
    )


def _source_label(checker: CanonChecker, source_id: str) -> str:
    """Resolve a safe human label from the existing Canon stores."""

    if source_id == "world_rules":
        return f"World Rules ({source_id})"
    record = checker._source_record(source_id)
    if not isinstance(record, Mapping):
        return source_id
    source_type = checker._source_type(source_id)
    candidates: list[Any] = []
    if source_type == "character":
        name = record.get("name")
        if isinstance(name, Mapping):
            candidates.append(name.get("display_name"))
    candidates.extend(
        record.get(key)
        for key in ("title", "name", "short_name")
        if isinstance(record.get(key), str)
    )
    label = next((value.strip() for value in candidates if isinstance(value, str) and value.strip()), None)
    return f"{label} ({source_id})" if label else source_id


def _compliance_summary(run: OfficialCharacterAuthoringRun) -> tuple[str, ...]:
    """Describe only dimensions represented by the actual checker result."""

    report = run.authoring.final_check
    draft = run.authoring.final_draft
    codes = {finding.code for finding in report.findings}
    summary: list[str] = []
    if report.status == CanonCheckStatus.PASS:
        if "world_rules" in report.checked_source_ids and CanonFindingCode.FORBIDDEN_PATTERN not in codes:
            summary.append("No forbidden world-pattern violations detected.")
        if draft.faction_id and draft.faction_id in report.checked_source_ids:
            summary.append("Referenced faction resolved successfully.")
        if draft.canon_basis:
            summary.append("Canon-supported claims passed validation.")
        if not summary:
            summary.append("No Canon Checker findings.")
    return tuple(summary)


def render(run: OfficialCharacterAuthoringRun, *, scenario: str, model_mode: str) -> str:
    draft = run.authoring.final_draft
    initial = run.authoring.initial_check
    final = run.authoring.final_check
    repair = run.authoring.repair_result
    reference_names = [
        f"- {item['display_name']} ({item['reference_id']}) — selected for bounded character-authoring context"
        for item in run.references.selected
    ]
    model_audits = len(run.generation.audit.model_invocations) + len(repair.model_audit)
    generation_turns = len({item.round for item in run.generation.audit.tool_calls}) + 1
    model_invocations = model_audits or generation_turns + repair.repair_attempt
    all_model_audits = tuple(run.generation.audit.model_invocations) + tuple(repair.model_audit)
    provider = all_model_audits[0].provider if all_model_audits else "offline-deterministic"
    model = all_model_audits[0].model if all_model_audits else "fixture"
    final_status = "ACCEPTED" if final.status == CanonCheckStatus.PASS else "NEEDS_REVIEW"
    source_labels = dict(run.source_labels)
    evidence = [source_labels.get(source_id, source_id) for source_id in final.checked_source_ids]
    findings = [f"{item.code.value}: {item.message}" for item in initial.findings]
    if not findings:
        findings = ["No findings."]
    compliance = _compliance_summary(run)
    repair_applied = (
        repair.repair_attempted
        and repair.repair_succeeded
        and repair.repaired_draft is not None
        and repair.recommended_draft == repair.repaired_draft
        and run.authoring.final_draft == repair.repaired_draft
    )
    repair_trigger = [
        f"{item.code.value} — {item.message}" for item in initial.findings
    ] or ["No Canon finding triggered repair."]

    lines = [
        "=" * 58,
        " OFFICIAL CHARACTER AUTHORING — LIVE MODE" if model_mode == "live" else " Official Character Authoring Demo v0.2",
        "=" * 58,
        f"Provider: {provider}",
        f"Model: {model}",
        f"Input: {'Custom Brief' if scenario == 'custom' else 'Scenario ' + scenario}",
        "",
        "[AUTHOR BRIEF]",
        run.request.request_id + " / " + scenario,
        run.request.brief,
        "",
        "----------------------------------------------------------",
        "CHARACTER PROPOSAL",
        "----------------------------------------------------------",
        f"Name: {draft.name}",
        f"Faction: {draft.faction_id or '未固化'}",
        f"Role: {draft.combat_role} / {draft.occupation}",
        f"Concept: {draft.design_pitch}",
        f"Personality: {'、'.join(draft.personality) or '—'}",
        f"Background: {draft.background}",
        f"Abilities: {draft.ability_concept}",
        f"Relationships / Canon basis: {len(draft.relationships)} / {len(draft.canon_basis)}",
        f"Constraints: {'；'.join(draft.constraint_notes) or '—'}",
        "",
        "----------------------------------------------------------",
        "REFERENCE GROUNDING",
        "----------------------------------------------------------",
        f"Corpus: {run.references.corpus_version} / {run.references.total_records} records",
        "Selected references:",
        *reference_names,
        "Grounding scope: bounded role/detail granularity, ability categories, and taxonomy context.",
        "The current audit records selection-level grounding, not field-level causal attribution.",
        "",
        "----------------------------------------------------------",
        "CANON VALIDATION",
        "----------------------------------------------------------",
        f"Initial: {initial.status.value.upper()}",
        f"Final: {final.status.value.upper()}",
        f"Evidence checked: {', '.join(evidence) or 'none'}",
        "Findings: " + " | ".join(findings),
        "Compliance summary:",
        *(f"- {item}" for item in compliance),
        "",
        "----------------------------------------------------------",
        "REPAIR",
        "----------------------------------------------------------",
        f"Status: {'APPLIED' if repair_applied else 'NOT NEEDED' if not repair.repair_attempted else 'NOT APPLIED'}",
        "Trigger:",
        *(f"- {item}" for item in repair_trigger),
        f"Changed fields: {', '.join(repair.changed_fields) or '—'}",
        f"Resolution: {repair.status.value}",
        f"Final Canon Check: {final.status.value.upper()}",
        "Next action: Manual review required." if repair.repair_attempted and not repair_applied else "",
        "",
        "----------------------------------------------------------",
        "AUTHORING AUDIT",
        "----------------------------------------------------------",
        f"References: {', '.join(run.generation.audit.reference_ids) or 'none'}",
        f"Normalized fields: {', '.join(run.generation.audit.normalized_fields) or 'none'}",
        f"Canon evidence used: {', '.join(source_labels.get(source_id, source_id) for source_id in run.generation.sources) or 'none'}",
        f"Generation turns: {generation_turns}",
        f"Model invocations: {model_invocations} [{model_mode}; provider audit entries: {model_audits}]",
        f"Repair attempts: {repair.repair_attempt}",
        "Offline model note: deterministic fixture for pipeline/regression; use --model live for open-ended generation."
        if model_mode == "offline"
        else "",
        f"Final status: {final_status}",
        "",
        "=" * 58,
        f" FINAL: {final_status}",
        "=" * 58,
    ]
    return "\n".join(lines)


def _live_failure_audits(error: BaseException) -> tuple[Any, ...]:
    """Return only sanitized invocation metadata attached by live components."""

    invocations = getattr(error, "model_invocations", ())
    if invocations:
        return tuple(invocations)
    audit = getattr(error, "audit", None)
    return (audit,) if audit is not None else ()


def render_live_failure(
    error: BaseException,
    *,
    provider: str | None = None,
    model_name: str | None = None,
) -> str:
    """Render a fail-closed live result without printing secrets or raw output."""

    audits = _live_failure_audits(error)
    audit_provider = audits[-1].provider if audits else None
    audit_model = audits[-1].model if audits else None
    display_provider = audit_provider or provider or os.environ.get("NPC_LLM_PROVIDER", "openai")
    display_model = audit_model or model_name or os.environ.get("NPC_LLM_MODEL") or "<not configured>"
    if isinstance(error, ModelError):
        detail = str(error)
    elif isinstance(error, AgentError):
        detail = f"{type(error).__name__}: the live authoring pipeline could not complete safely"
    else:
        detail = "Unexpected live authoring failure; the pipeline was not completed"
    outcome = audits[-1].outcome if audits else "not_started"
    provider_invocation = (
        "SUCCESS" if outcome == "success" else "FAILED" if audits else "NOT_STARTED"
    )
    draft_validation = (
        "FAILED"
        if isinstance(error, ModelMalformedResponseError)
        and "CharacterDraft" in str(error)
        else "NOT_RUN"
    )
    lines = [
        "OFFICIAL CHARACTER AUTHORING — LIVE MODE",
        "",
        "LIVE MODEL INVOCATION FAILURE",
        "",
        f"Provider: {display_provider}",
        f"Model: {display_model}",
        f"Invocation count: {len(audits)}",
        f"Outcome: {outcome}",
        f"Provider invocation: {provider_invocation}",
        f"CharacterDraft validation: {draft_validation}",
        f"Error: {detail}",
        "",
        "Requested model mode: LIVE",
        f"Invocation: {provider_invocation}",
        "Pipeline status: NOT_COMPLETED",
        "No Character draft or Canon result was fabricated.",
    ]
    if audits:
        lines.append("Audit retained: provider/model and sanitized failure metadata.")
    else:
        lines.append("The authoring pipeline was not started.")
    return "\n".join(lines)


VALID_BRIEF = """设计一个新的五星角色。
所属组织：临洲大学行为与能力研究中心
定位：偏辅助
性格：表面懒散但观察力很强
希望有明显都市生活感
不要设计成秘密实验体
不要改变现有世界观重大设定"""

CONFLICT_BRIEF = """设计一个新的五星角色。
角色概念：她是秘密政府能力管理局的一名普通辅助成员。
定位：偏辅助；保持现代都市生活感。"""


def _request_for_scenario(scenario: str) -> CharacterDesignRequest:
    if scenario == "valid":
        return CharacterDesignRequest(
            VALID_BRIEF,
            hard_constraints=("五星角色", "不得改变现有世界观重大设定"),
            soft_preferences=("偏辅助", "表面懒散但观察力很强", "都市生活感"),
            forbidden_elements=("秘密实验体", "秘密政府机构"),
            desired_connections=("临洲大学行为与能力研究中心",),
            request_id="official_valid_001",
        )
    return CharacterDesignRequest(
        CONFLICT_BRIEF,
        hard_constraints=("偏辅助",),
        soft_preferences=("都市生活感",),
        forbidden_elements=(),
        request_id="official_conflict_001",
    )


def request_from_inputs(
    *,
    scenario: str | None = None,
    brief: str | None = None,
    brief_file: str | None = None,
) -> tuple[CharacterDesignRequest, str, str]:
    """Build a request and presentation/model profile from one CLI input."""

    supplied = sum(value is not None for value in (scenario, brief, brief_file))
    if supplied != 1:
        raise ValueError("exactly one of --scenario, --brief, or --brief-file is required")
    if scenario is not None:
        request = _request_for_scenario(scenario)
        return request, scenario, "canon_conflict" if scenario == "conflict" else "valid"
    if brief is None and brief_file is not None:
        try:
            brief = Path(brief_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"could not read --brief-file: {exc}") from exc
    if brief is None or not brief.strip():
        raise ValueError("custom brief must not be empty")
    return CharacterDesignRequest(brief, request_id="official_custom_001"), "custom", "valid"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official Character Authoring Demo v0.2")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--scenario", choices=("valid", "conflict"))
    inputs.add_argument("--brief", help="planner brief text to send through the real pipeline")
    inputs.add_argument("--brief-file", help="UTF-8 file containing the planner brief")
    parser.add_argument("--model", choices=("offline", "live"), default="offline")
    parser.add_argument(
        "--provider",
        help="live provider override; otherwise NPC_LLM_PROVIDER (default: openai)",
    )
    parser.add_argument(
        "--model-name",
        help="live model override; otherwise NPC_LLM_MODEL",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    if args.scenario is None and args.brief is None and args.brief_file is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        request, presentation_scenario, generation_scenario = request_from_inputs(
            scenario=args.scenario,
            brief=args.brief,
            brief_file=args.brief_file,
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        demo = make_demo(
            mode=args.model,
            scenario=generation_scenario,
            brief=request.brief,
            provider=args.provider,
            model_name=args.model_name,
        )
        run = demo.run(request)
    except Exception as exc:
        if args.model == "live":
            print(
                render_live_failure(
                    exc,
                    provider=args.provider,
                    model_name=args.model_name,
                ),
                file=sys.stderr,
            )
            return 2
        raise
    if args.as_json:
        payload = run.to_dict()
        payload["demo"] = {
            "scenario": presentation_scenario,
            "model_mode": args.model,
            "offline_notice": (
                "Deterministic pipeline fixture; use --model live for open-ended generation."
                if args.model == "offline"
                else None
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(run, scenario=presentation_scenario, model_mode=args.model))
    return 0 if run.authoring.final_status != CanonCheckStatus.FAIL else 2


if __name__ == "__main__":
    sys.exit(main())
