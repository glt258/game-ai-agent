"""Interactive manual entry point for the frozen Skill Design v1 pipeline.

This module is deliberately a presentation/orchestration shell.  It reuses
the existing model-facing contract, runner, compiler, evaluator, and repair
session; it never writes formal benchmark evidence.
"""

# The direct-script sys.path bootstrap intentionally precedes project imports.
# ruff: noqa: I001

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, TextIO

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from character_intelligence.compiler import COMPILER_VERSION_V2  # noqa: E402
from character_intelligence.hybrid_ir.contract import build_model_facing_request  # noqa: E402
from character_intelligence.hybrid_ir.projection import (  # noqa: E402
    SEMANTIC_ACTORS,
    HybridGenerationContext,
)
from character_intelligence.hybrid_ir.repair import (  # noqa: E402
    RepairOutcome,
    SemanticRepairResult,
    SemanticRepairSession,
)
from character_intelligence.hybrid_ir.runner import (  # noqa: E402
    FIRST_FAILURE_LAYERS,
    FakePipelineResult,
    HybridProvider,
    HybridProviderInvocationError,
    _default_hybrid_provider_factory,
    _identity,
    _run_pipeline,
)
from character_intelligence.planner import build_character_design_plan  # noqa: E402
from character_skill.contract import ABILITY_MODES  # noqa: E402
from character_skill.evaluation import _ROLE_ROWS  # noqa: E402
from combat_semantics import CANONICAL_COMBAT_ROLES  # noqa: E402


ROLE_CHOICES = tuple(CANONICAL_COMBAT_ROLES)
MODE_CHOICES = tuple(sorted(ABILITY_MODES))
DEFAULT_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True)
class PlaygroundExecution:
    """In-memory result of one manual generation and optional repair."""

    initial: FakePipelineResult
    final: FakePipelineResult
    repair: SemanticRepairResult | None
    repair_status: str


def _role_row(role: str) -> dict[str, object]:
    if role not in ROLE_CHOICES:
        raise ValueError("unsupported role")
    return _ROLE_ROWS[role]


def build_playground_context(role: str, mode: str, requirement: str) -> HybridGenerationContext:
    """Build a v2 context from user-owned inputs, without case lookup."""

    if role not in ROLE_CHOICES or mode not in MODE_CHOICES:
        raise ValueError("role and mode must use authoritative vocabulary")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("requirement must be non-empty")

    brief = (
        f"Design a {role} {mode} skill.\n"
        f"User requirement:\n{requirement.strip()}"
    )
    plan = build_character_design_plan(brief)
    row = _role_row(role)
    triggers = row["triggers"]
    assert isinstance(triggers, frozenset)
    allowed_events = tuple(sorted(event for _actor, event in triggers))
    return HybridGenerationContext(
        brief,
        plan=plan,
        case_id="manual-playground",
        contract_profile="generalization_v2",
        allowed_actors=SEMANTIC_ACTORS,
        allowed_trigger_events=None if mode == "passive" else allowed_events,
        allowed_modes=(mode,),
        allowed_roles=(role,),
        allowed_centralities=("core",),
    )


def build_playground_evaluation_context(role: str, mode: str) -> dict[str, object]:
    """Build generic role/mode requirements from the authoritative evaluator row."""

    row = _role_row(role)
    duty = row["duty"]
    subjects = row["subjects"]
    triggers = row["triggers"]
    assert isinstance(duty, str)
    assert isinstance(subjects, frozenset)
    assert isinstance(triggers, frozenset)

    requirement: dict[str, object] = {
        "requirement_id": f"manual_{role}",
        "mechanic_kind": "passive" if mode == "passive" else "triggered",
        "effect": {
            "subject_kinds": sorted(subjects),
            "operations": [duty],
            "object_kinds": [],
        },
        "feedback": {"required": False, "events": [], "operations": []},
        "allowed_modes": [mode],
    }
    if mode != "passive":
        requirement["trigger"] = {
            "subject_kinds": sorted({actor for actor, _event in triggers}),
            "events": sorted({event for _actor, event in triggers}),
            "source_kinds": [],
        }
    return {
        "intent": {
            "mechanic_requirements": [requirement],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": {"primary_role": role, "secondary_roles": []},
        "reference_review_context": None,
    }


def run_manual_pipeline(
    provider: HybridProvider,
    context: HybridGenerationContext,
    evaluation_context: dict[str, object],
    *,
    model: str = DEFAULT_MODEL,
    repo_root: Path = ROOT,
    invocation_id: str | None = None,
) -> FakePipelineResult:
    """Run the existing pipeline in memory under an independent manual identity."""

    from character_intelligence.semantic_ir.schema import SEMANTIC_IR_V2_VERSION

    request = build_model_facing_request(context)
    identity = replace(
        _identity(
            repo_root,
            request.contract.digest,
            context.case_id,
            request.contract.version,
            context.context_projection_version,
            context.context_projection_digest,
            target_sample_count=1,
            experiment="manual-playground",
            ir_schema_version=SEMANTIC_IR_V2_VERSION,
            compiler_version=COMPILER_VERSION_V2,
        ),
        model=model,
    )
    result = _run_pipeline(
        provider,
        context,
        evaluation_context,
        repo_root=repo_root,
        sample_index=1,
        target_sample_count=1,
        experiment="manual-playground",
        identity=identity,
    )
    manual_id = invocation_id or f"manual-playground-{uuid.uuid4().hex}"
    return replace(result, evidence=replace(result.evidence, run_id=manual_id))


def _manualize_result(result: FakePipelineResult, *, model: str) -> FakePipelineResult:
    """Keep any in-memory revalidation identity independent of formal runs."""

    return replace(
        result,
        evidence=replace(
            result.evidence,
            identity=replace(result.evidence.identity, model=model),
            run_id=f"manual-playground-{uuid.uuid4().hex}",
        ),
    )


def execute_playground(
    provider: HybridProvider,
    role: str,
    mode: str,
    requirement: str,
    *,
    model: str = DEFAULT_MODEL,
    repair_decider: Callable[[], bool] | None = None,
    repo_root: Path = ROOT,
) -> PlaygroundExecution:
    """Generate once and, only after confirmation, repair at most once."""

    context = build_playground_context(role, mode, requirement)
    evaluation_context = build_playground_evaluation_context(role, mode)
    initial = run_manual_pipeline(
        provider,
        context,
        evaluation_context,
        model=model,
        repo_root=repo_root,
    )
    evidence = initial.evidence
    if evidence.evaluator_outcome == "PASS":
        return PlaygroundExecution(initial, initial, None, "NOT_NEEDED")
    if evidence.first_failure_layer != "EVALUATOR" or evidence.evaluator_outcome != "FAIL":
        return PlaygroundExecution(initial, initial, None, "UNAVAILABLE")
    if repair_decider is None or not repair_decider():
        return PlaygroundExecution(initial, initial, None, "NOT_ATTEMPTED")

    session = SemanticRepairSession(
        initial,
        context,
        evaluation_context,
        repo_root=str(repo_root),
    )
    repair = session.run(lambda request: provider.complete(request.to_prompt()))
    if repair.revalidation is not None:
        repair = replace(repair, revalidation=_manualize_result(repair.revalidation, model=model))
    final = repair.revalidation if repair.outcome is RepairOutcome.REPAIR_SUCCESS else initial
    if repair.outcome is RepairOutcome.REPAIR_SUCCESS:
        status = "SUCCESS"
    elif repair.outcome is RepairOutcome.REPAIR_UNAVAILABLE:
        status = "UNAVAILABLE"
    else:
        status = "FAILED"
    return PlaygroundExecution(initial, final, repair, status)


def _candidate_summary(result: FakePipelineResult) -> tuple[str, str, str, str]:
    candidate = result.candidate
    if candidate is None or not candidate.entries:
        return (
            "<not generated by current pipeline>",
            "<not reached>",
            "<not reached>",
            "<not reached>",
        )
    entry = candidate.entries[0]
    trigger_parts: list[str] = []
    effect_parts: list[str] = []
    for protocol in entry.protocols:
        if protocol.when is not None:
            when = protocol.when
            subject = when.subject.kind if when.subject is not None else "<unspecified>"
            trigger_parts.append(f"{subject} / {when.event or '<unspecified>'}")
        for effect in protocol.causes:
            subject = effect.subject.kind if effect.subject is not None else "<unspecified>"
            detail = effect.description.strip() or effect.operation or "<unspecified>"
            effect_parts.append(f"{subject} / {effect.operation or '<unspecified>'}: {detail}")
    feedback = (
        "; ".join(f"{item.event} / {item.operation}" for item in candidate.feedback_relations)
        or "None declared by canonical result"
    )
    return (
        entry.name.strip() or "<not generated by current pipeline>",
        "; ".join(dict.fromkeys(trigger_parts)) or "<none>",
        "; ".join(dict.fromkeys(effect_parts)) or entry.display_text.strip() or "<none>",
        feedback,
    )


def _evaluator_label(result: FakePipelineResult) -> str:
    evidence = result.evidence
    if evidence.first_failure_layer is None and evidence.evaluator_outcome == "PASS":
        return "PASS"
    if evidence.first_failure_layer == "EVALUATOR":
        return "FAIL"
    return "NOT_REACHED"


def _stage_status(result: FakePipelineResult, stage: str) -> str:
    failure_layer = result.evidence.first_failure_layer
    if failure_layer is None:
        return "PASS"
    stage_index = FIRST_FAILURE_LAYERS.index(stage)
    failure_index = FIRST_FAILURE_LAYERS.index(failure_layer)
    if stage_index < failure_index:
        return "PASS"
    if stage_index == failure_index:
        return "FAIL"
    return "NOT_REACHED"


def render_result(
    execution: PlaygroundExecution,
    role: str,
    mode: str,
    *,
    show_safe_debug: bool = False,
    provider: HybridProvider | None = None,
    output: TextIO = sys.stdout,
) -> None:
    """Print only selected canonical fields and bounded diagnostics."""

    result = execution.final
    name, trigger, effect, feedback = _candidate_summary(result)
    print("=== Skill Design Result ===", file=output)
    print(f"Role: {role}", file=output)
    print(f"Mode: {mode}", file=output)
    print(f"Skill Name: {name}", file=output)
    print("Trigger:", file=output)
    print(f"  {trigger}", file=output)
    print("Core Effect:", file=output)
    print(f"  {effect}", file=output)
    print("Feedback / Continuation:", file=output)
    print(f"  {feedback}", file=output)
    print(f"Evaluator: {_evaluator_label(result)}", file=output)
    print(f"Repair: {execution.repair_status}", file=output)
    print("Pipeline:", file=output)
    for stage in FIRST_FAILURE_LAYERS:
        print(f"  {stage}: {_stage_status(result, stage)}", file=output)

    if show_safe_debug:
        evidence = execution.initial.evidence
        diagnostics = evidence.evaluator_diagnostics
        print("Safe debug:", file=output)
        print(f"  Provider: {evidence.identity.provider} / {evidence.identity.model}", file=output)
        print(f"  First failure layer: {evidence.first_failure_layer or 'none'}", file=output)
        if evidence.first_failure_layer == "IR_PARSE":
            print(
                f"  Parse classification: {evidence.failure_code or 'OTHER_IR_PARSE'}",
                file=output,
            )
        print(f"  Request characters: {evidence.request_metrics.get('total_chars', 0)}", file=output)
        print(f"  Provider calls: {provider.calls if provider is not None else 'not exposed'}", file=output)
        if diagnostics is not None:
            print(
                "  Diagnostics: "
                f"dimensions={','.join(diagnostics.dimensions) or 'none'}; "
                f"categories={','.join(diagnostics.categories) or 'none'}; "
                f"findings={diagnostics.finding_count}",
                file=output,
            )


def _credential_status(output: TextIO) -> bool:
    configured = bool(os.environ.get("NPC_LLM_API_KEY", "").strip())
    print(f"NPC_LLM_API_KEY={'SET' if configured else 'MISSING'}", file=output)
    if not configured:
        print(
            "Set NPC_LLM_API_KEY before running the live playground. "
            "The key value is never displayed.",
            file=output,
        )
    return configured


def _prompt_choice(label: str, choices: tuple[str, ...], input_fn: Callable[[str], str], output: TextIO) -> str:
    print(f"{label} choices: {', '.join(choices)}", file=output)
    while True:
        value = input_fn(f"{label}: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        if value in choices:
            return value
        print("Please choose one of the listed values.", file=output)


def _prompt_requirement(input_fn: Callable[[str], str], output: TextIO) -> str:
    print("Requirement (multi-line; submit an empty line to finish):", file=output)
    lines: list[str] = []
    while True:
        line = input_fn("")
        if not line:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main(
    argv: list[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output: TextIO | None = None,
    provider_factory: Callable[[str], HybridProvider] | None = None,
) -> int:
    if output is None:
        output = sys.stdout
    parser = argparse.ArgumentParser(description="Manual Skill Design v1 interactive playground")
    parser.add_argument("--role", choices=ROLE_CHOICES)
    parser.add_argument("--mode", choices=MODE_CHOICES)
    parser.add_argument("--prompt", help="single-line requirement; omit for multi-line input")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model used by the configured provider. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument("--show-safe-debug", action="store_true")
    args = parser.parse_args(argv)

    try:
        role = args.role or _prompt_choice("Role", ROLE_CHOICES, input_fn, output)
        mode = args.mode or _prompt_choice("Mode", MODE_CHOICES, input_fn, output)
        requirement = args.prompt.strip() if args.prompt else _prompt_requirement(input_fn, output)
        if not requirement:
            print("Requirement must not be empty.", file=output)
            return 2
        if provider_factory is None and not _credential_status(output):
            return 2
        factory = provider_factory or (
            lambda selected_model: _default_hybrid_provider_factory(model=selected_model)
        )
        provider = factory(args.model)

        def decide() -> bool:
            answer = input_fn("Evaluator FAIL. Repair adds one model call. Continue? [Y/n] ").strip().lower()
            return answer not in {"n", "no"}

        execution = execute_playground(
            provider,
            role,
            mode,
            requirement,
            model=args.model,
            repair_decider=decide,
        )
        render_result(
            execution,
            role,
            mode,
            show_safe_debug=args.show_safe_debug,
            provider=provider,
            output=output,
        )
        return 0 if _evaluator_label(execution.final) == "PASS" else 1
    except (KeyboardInterrupt, EOFError):
        print("\nPlayground cancelled.", file=output)
        return 130
    except HybridProviderInvocationError:
        print("Playground failed: provider unavailable (timeout or transport failure).", file=output)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"Playground failed: {type(error).__name__}.", file=output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
