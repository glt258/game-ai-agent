"""Shared application seam for the Skill Design v1 playground.

The CLI and Web adapters provide presentation and transport concerns only;
this module owns the user-input projection and one-shot pipeline execution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from character_skill.contract import ABILITY_MODES
from character_skill.evaluation import _ROLE_ROWS
from combat_semantics import CANONICAL_COMBAT_ROLES

from ..compiler import COMPILER_VERSION_V2
from ..planner import build_character_design_plan
from ..semantic_ir.schema import SEMANTIC_IR_V2_VERSION
from .contract import build_model_facing_request
from .language import resolve_output_language
from .projection import SEMANTIC_ACTORS, HybridGenerationContext
from .repair import SemanticRepairResult
from .runner import (
    FakePipelineResult,
    HybridProvider,
    HybridProviderInvocationError,
    _identity,
    _run_pipeline,
)

ROLE_CHOICES = tuple(CANONICAL_COMBAT_ROLES)
MODE_CHOICES = tuple(sorted(ABILITY_MODES))
BASIC_PASSIVE_FAMILY = "basic_passive"
FAMILY_CHOICES = ROLE_CHOICES + (BASIC_PASSIVE_FAMILY,)


@dataclass(frozen=True)
class PlaygroundExecution:
    initial: FakePipelineResult
    final: FakePipelineResult
    repair: SemanticRepairResult | None = None
    repair_status: str = "NOT_ATTEMPTED"


def resolve_family(family: str, mode: str) -> tuple[str, str]:
    if family not in FAMILY_CHOICES:
        raise ValueError("unsupported family")
    if mode not in MODE_CHOICES:
        raise ValueError("unsupported mode")
    if family == BASIC_PASSIVE_FAMILY:
        if mode != "passive":
            raise ValueError("basic passive requires passive mode")
        return "support", "passive"
    return family, mode


def _role_row(role: str) -> dict[str, object]:
    if role not in ROLE_CHOICES:
        raise ValueError("unsupported role")
    return _ROLE_ROWS[role]


def build_playground_context(role: str, mode: str, requirement: str) -> HybridGenerationContext:
    role, mode = resolve_family(role, mode)
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("requirement must be non-empty")
    brief = f"Design a {role} {mode} skill.\nUser requirement:\n{requirement.strip()}"
    plan = build_character_design_plan(brief)
    row = _role_row(role)
    triggers = row["triggers"]
    subjects = row["subjects"]
    assert isinstance(triggers, frozenset)
    assert isinstance(subjects, frozenset)
    # Some legacy role rows mention summon actors, while the current Semantic
    # IR contract deliberately excludes summon as a direct trigger subject.
    # Project only the supported structured vocabulary into this context.
    supported_triggers = frozenset(
        (actor, event) for actor, event in triggers if actor in SEMANTIC_ACTORS
    )
    return HybridGenerationContext(
        brief,
        plan=plan,
        case_id="manual-playground",
        contract_profile="generalization_v2",
        allowed_actors=SEMANTIC_ACTORS,
        allowed_trigger_subjects=(
            tuple(sorted({actor for actor, _event in supported_triggers}))
            if mode != "passive" else None
        ),
        allowed_effect_subjects=tuple(sorted(subjects)),
        allowed_trigger_events=(
            None if mode == "passive" else tuple(sorted(event for _actor, event in supported_triggers))
        ),
        allowed_modes=(mode,),
        allowed_roles=(role,),
        allowed_centralities=("core",),
    )


def build_playground_evaluation_context(role: str, mode: str) -> dict[str, object]:
    role, mode = resolve_family(role, mode)
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


def run_playground_pipeline(
    provider: HybridProvider,
    role: str,
    mode: str,
    requirement: str,
    *,
    model: str,
    language: str,
    repo_root: Path | str,
    invocation_id: str | None = None,
) -> FakePipelineResult:
    role, mode = resolve_family(role, mode)
    context = build_playground_context(role, mode, requirement)
    evaluation_context = build_playground_evaluation_context(role, mode)
    selected_language = resolve_output_language(language, requirement)
    request = build_model_facing_request(context, language=selected_language)
    identity = replace(
        _identity(
            Path(repo_root),
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
        language=selected_language,
    )
    return replace(
        result,
        evidence=replace(
            result.evidence,
            run_id=invocation_id or f"manual-playground-{uuid.uuid4().hex}",
        ),
    )


def run_playground_context_pipeline(
    provider: HybridProvider,
    context: HybridGenerationContext,
    evaluation_context: dict[str, object],
    *,
    model: str,
    language: str,
    repo_root: Path | str,
    invocation_id: str | None = None,
) -> FakePipelineResult:
    """Run the shared seam for adapters that already built an authoritative context."""

    selected_language = resolve_output_language(language, context.brief)
    request = build_model_facing_request(context, language=selected_language)
    identity = replace(
        _identity(
            Path(repo_root),
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
        language=selected_language,
    )
    return replace(result, evidence=replace(result.evidence, run_id=invocation_id or f"manual-playground-{uuid.uuid4().hex}"))


def execute_playground(
    provider: HybridProvider,
    role: str,
    mode: str,
    requirement: str,
    *,
    model: str,
    language: str = "auto",
    repo_root: Path | str,
) -> PlaygroundExecution:
    """Execute exactly one pipeline pass; repair is intentionally not automatic."""

    result = run_playground_pipeline(
        provider,
        role,
        mode,
        requirement,
        model=model,
        language=language,
        repo_root=repo_root,
    )
    if result.evidence.first_failure_layer == "PROVIDER":
        raise HybridProviderInvocationError(
            "TIMEOUT" if result.evidence.failure_code == "PROVIDER_TIMEOUT" else "TRANSPORT_FAILURE"
        )
    status = "NOT_NEEDED" if result.evidence.evaluator_outcome == "PASS" else "NOT_ATTEMPTED"
    return PlaygroundExecution(result, result, None, status)


__all__ = [
    "BASIC_PASSIVE_FAMILY",
    "FAMILY_CHOICES",
    "MODE_CHOICES",
    "ROLE_CHOICES",
    "PlaygroundExecution",
    "build_playground_context",
    "build_playground_evaluation_context",
    "execute_playground",
    "resolve_family",
    "run_playground_pipeline",
    "run_playground_context_pipeline",
]
