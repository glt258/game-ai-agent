"""Deterministic bridge from a resolved direction to the existing Planner.

This module is intentionally outside ``character_planner_v2``.  Resolution
chooses the direction; the existing Planner still elaborates that direction
into ``CharacterDesignPlanV2``.  The bridge carries audit metadata without
putting resolver semantics, rejected candidates, or locks into the Planner
prompt.  Phase 7 may call this bridge from an explicit opt-in orchestration
route; the default Phase 4 path remains separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents import AgentModel

from ..context.schema import CharacterPlanningContextV2
from .character_concept_v2 import CharacterConceptSeedV2
from .character_plan_v2 import CharacterDesignPlanV2
from .character_planner_v2 import CharacterPlannerV1Result, run_character_planner_v1
from .decision_metadata import (
    CandidateLineage,
    CharacterCandidateSet,
    CharacterResolutionResult,
    DecisionMetadataError,
    DecisionMetadataSet,
    DecisionResolutionMode,
    DecisionResolutionStatus,
    ResolutionAction,
    ResolvedCharacterDirection,
)


def _text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence")
    try:
        values = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{field_name} must be a sequence") from exc
    normalized = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        normalized.append(item.strip())
    return tuple(normalized)


@dataclass(frozen=True)
class ResolvedPlanningInput:
    """Planner-facing snapshot for one already-resolved SELECT direction.

    ``selected_seed`` is the exact object held by ``candidate_set``.  The
    bridge stores resolution identity and lineage for audit/continuation, but
    deliberately exposes only that seed to the existing Planner call.
    """

    selected_seed: CharacterConceptSeedV2
    resolved_direction: ResolvedCharacterDirection
    resolution_id: str
    resolution_mode: DecisionResolutionMode
    resolution_action: ResolutionAction
    source_candidate_id: str
    preserve_guidance: tuple[str, ...] = ()

    @classmethod
    def from_result(
        cls,
        resolution_result: CharacterResolutionResult,
        candidate_set: CharacterCandidateSet,
    ) -> "ResolvedPlanningInput":
        """Validate a resolution result and bind its exact selected seed.

        P7.4 already validates the result, but this boundary repeats the
        planner-readiness checks so a future caller cannot accidentally route
        ``REQUEST_MORE``, ``REVISE``, or another unresolved action to Planner.
        """

        if not isinstance(resolution_result, CharacterResolutionResult):
            raise TypeError("resolution_result must be CharacterResolutionResult")
        if not isinstance(candidate_set, CharacterCandidateSet):
            raise TypeError("candidate_set must be CharacterCandidateSet")
        if (
            resolution_result.action is not ResolutionAction.SELECT
            or resolution_result.resolution_status is not DecisionResolutionStatus.RESOLVED
        ):
            raise DecisionMetadataError(
                "RESOLUTION_ACTION_NOT_PLANNER_READY: only resolved SELECT is supported"
            )

        direction = ResolvedCharacterDirection.from_result(
            resolution_result,
            candidate_set,
        )
        decisions = direction.resolved_decisions
        if len(decisions) != 1:
            raise DecisionMetadataError(
                "RESOLUTION_ACTION_NOT_PLANNER_READY: SELECT requires one decision"
            )
        decision = decisions[0]
        if decision.decision_path != "selected_concept_seed":
            raise DecisionMetadataError(
                "RESOLUTION_ACTION_NOT_PLANNER_READY: SELECT path is not selected_concept_seed"
            )
        if decision.action is not ResolutionAction.SELECT:
            raise DecisionMetadataError(
                "RESOLUTION_ACTION_NOT_PLANNER_READY: decision action is not SELECT"
            )
        if tuple(resolution_result.source_candidate_ids) != decision.source_candidate_ids:
            raise DecisionMetadataError(
                "resolution source candidates do not match the resolved decision"
            )

        selected_id = decision.source_candidate_ids[0]
        selected_seed = candidate_set.get(selected_id)
        if not isinstance(selected_seed, CharacterConceptSeedV2):
            raise TypeError("resolved selected candidate is not CharacterConceptSeedV2")
        if selected_seed is not candidate_set.get(selected_id):
            raise DecisionMetadataError("selected seed identity was not preserved")

        return cls(
            selected_seed=selected_seed,
            resolved_direction=direction,
            resolution_id=resolution_result.resolution_id,
            resolution_mode=resolution_result.mode,
            resolution_action=resolution_result.action,
            source_candidate_id=selected_id,
            preserve_guidance=_text_tuple(
                resolution_result.rationale.preserve_elements,
                "preserve_guidance",
            ),
        )

    @property
    def candidate_set(self) -> CharacterCandidateSet:
        """Expose the immutable candidate snapshot for audit consumers."""

        return self.resolved_direction.candidate_set

    @property
    def decision_metadata(self) -> DecisionMetadataSet:
        """Retain USER/CANON locks and other metadata without prompt expansion."""

        return self.resolved_direction.decision_metadata

    @property
    def lineage(self) -> tuple[CandidateLineage, ...]:
        """Keep all three candidate lineage entries request-local."""

        return self.candidate_set.lineage

    def to_dict(self) -> dict[str, Any]:
        """Serialize identity and audit metadata without duplicating seed values."""

        return {
            "resolution_id": self.resolution_id,
            "resolution_mode": self.resolution_mode.value,
            "resolution_action": self.resolution_action.value,
            "source_candidate_id": self.source_candidate_id,
            "preserve_guidance": list(self.preserve_guidance),
            "lineage": [item.to_dict() for item in self.lineage],
            "decision_metadata": self.decision_metadata.to_dict(),
        }


def build_resolved_planning_input(
    resolution_result: CharacterResolutionResult,
    candidate_set: CharacterCandidateSet,
) -> ResolvedPlanningInput:
    """Create the isolated Planner bridge from one validated resolution."""

    return ResolvedPlanningInput.from_result(resolution_result, candidate_set)


def plan_resolved_character_direction(
    resolution_result: CharacterResolutionResult,
    candidate_set: CharacterCandidateSet,
    shadow_plan: CharacterDesignPlanV2,
    context: CharacterPlanningContextV2,
    model: AgentModel,
) -> CharacterPlannerV1Result:
    """Run the unchanged Planner with the resolver-selected seed only.

    The helper proves that every supported SELECT result reaches the same
    existing ``run_character_planner_v1`` entrypoint without reselecting a
    candidate.  Production callers must still opt in at their orchestration
    seam; this function does not enable the route by itself.
    """

    bridge = build_resolved_planning_input(resolution_result, candidate_set)
    return run_character_planner_v1(
        shadow_plan,
        context,
        model,
        selected_concept_seed=bridge.selected_seed,
    )


__all__ = [
    "ResolvedPlanningInput",
    "build_resolved_planning_input",
    "plan_resolved_character_direction",
]
