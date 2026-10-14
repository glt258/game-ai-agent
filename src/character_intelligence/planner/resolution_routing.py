"""Explicit Phase 7 SELECT routing around the existing planning contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from agents import AgentModel, ModelInvocationAudit

from ..context.schema import CharacterPlanningContextV2
from . import concept_search_v2
from .character_concept_v2 import CharacterConceptSeedStatus
from .decision_metadata import (
    CharacterResolutionInput,
    CharacterResolutionResult,
    DecisionMetadataError,
    DecisionMetadataSet,
    DecisionResolutionMode,
    ResolvedCharacterDirection,
    UserResolutionCommand,
    build_resolution_input_from_search_and_selection,
    resolve_character_direction,
)
from .resolution_planner_bridge import plan_resolved_character_direction


@dataclass(frozen=True)
class CharacterPlanningV2Phase7Result(
    concept_search_v2.CharacterPlanningV2Phase4Result
):
    """Phase 7 SELECT result retained by the existing Phase 5 seam.

    ``selection`` is the effective SELECT used by Phase 5.  For legacy mode
    it is the original Selector result; for ``USER_DECIDE`` it reflects the
    explicit user choice.  ``selector_selection`` retains the recommendation
    separately, so audit consumers can distinguish recommendation from
    authority without changing the public seed or plan contracts.
    """

    selector_selection: concept_search_v2.ConceptSelectionResult
    resolution_input: CharacterResolutionInput
    resolution_result: CharacterResolutionResult
    resolved_direction: ResolvedCharacterDirection

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload.update(
            {
                "selector_selection": self.selector_selection.to_dict(),
                "resolution_input": self.resolution_input.to_dict(),
                "resolution_result": self.resolution_result.to_dict(),
                "resolved_direction": self.resolved_direction.to_dict(),
            }
        )
        return payload


def run_character_planning_v2_phase7(
    context: CharacterPlanningContextV2,
    model: AgentModel,
    *,
    resolution_mode: DecisionResolutionMode | str = DecisionResolutionMode.LEGACY_AI_SELECT,
    user_command: UserResolutionCommand | None = None,
    planner_model: AgentModel | None = None,
) -> CharacterPlanningV2Phase7Result:
    """Run Search → Selector → SELECT resolution → the existing Planner once.

    WHY: Phase 7 introduces decision ownership at the orchestration seam.  It
    does not alter seed, plan, or Planner contracts, and it deliberately
    rejects ``AI_DECIDE`` because P7.5 has no production AI resolver runtime.
    Resolution is local and adds zero provider calls; the only provider stages
    remain Concept Search, Selector, and Planner.
    """

    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    try:
        selected_mode = (
            resolution_mode
            if isinstance(resolution_mode, DecisionResolutionMode)
            else DecisionResolutionMode(resolution_mode)
        )
    except (TypeError, ValueError) as error:
        raise DecisionMetadataError("unsupported resolution mode") from error
    if selected_mode is DecisionResolutionMode.AI_DECIDE:
        raise DecisionMetadataError("AI_RESOLVER_RUNTIME_NOT_AVAILABLE")
    if selected_mode is DecisionResolutionMode.USER_DECIDE and not isinstance(
        user_command, UserResolutionCommand
    ):
        raise DecisionMetadataError("USER_DECIDE requires a structured user command")

    search = concept_search_v2.run_concept_search_v2(context, model)
    selector = concept_search_v2.run_concept_selector_v2(context, search.seeds, model)
    metadata = DecisionMetadataSet.from_selector(
        search.seeds,
        selector.selection,
        source_invocation_id=_invocation_id(search.diagnostics.model_invocation),
        selector_invocation_id=_invocation_id(selector.diagnostics.model_invocation),
    )
    resolution_input = build_resolution_input_from_search_and_selection(
        search,
        selector,
        metadata,
    )
    resolution = resolve_character_direction(
        selected_mode,
        resolution_input,
        user_command=user_command,
    )
    resolved_direction = ResolvedCharacterDirection.from_result(
        resolution,
        resolution_input.candidate_set,
    )
    planner = plan_resolved_character_direction(
        resolution,
        resolution_input.candidate_set,
        context.plan_v2,
        context,
        planner_model or model,
    )
    effective_selection = _effective_selection_result(
        selector,
        resolution,
        resolution_input,
    )
    return CharacterPlanningV2Phase7Result(
        search=search,
        selection=effective_selection,
        planner=planner,
        selector_selection=selector,
        resolution_input=resolution_input,
        resolution_result=resolution,
        resolved_direction=resolved_direction,
    )


def _effective_selection_result(
    selector: concept_search_v2.ConceptSelectionResult,
    resolution: CharacterResolutionResult,
    resolution_input: CharacterResolutionInput,
) -> concept_search_v2.ConceptSelectionResult:
    """Project a resolved SELECT into the existing Phase 5 selection seam."""

    selected_id = resolution.source_candidate_ids[0]
    if selected_id == selector.selection.selected_concept_id:
        return selector
    selected_seed = resolution_input.candidate_set.get(selected_id)
    return replace(
        selector,
        selection=replace(
            selector.selection,
            selected_concept_id=selected_id,
            selection_reasons=resolution.rationale.selection_reasons,
            tradeoffs=resolution.rationale.tradeoffs,
            preserve_elements=resolution.rationale.preserve_elements,
            rejected_reasons=resolution.rationale.rejected_reasons,
        ),
        selected_seed=selected_seed.with_status(CharacterConceptSeedStatus.SELECTED),
    )


def _invocation_id(audit: ModelInvocationAudit | None) -> str | None:
    if audit is None:
        return None
    return f"{audit.session_id}:{audit.turn_number}"


__all__ = [
    "CharacterPlanningV2Phase7Result",
    "run_character_planning_v2_phase7",
]
