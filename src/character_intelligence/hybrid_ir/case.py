"""Authoritative semantic case definitions for Hybrid generation/evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..planner import CharacterDesignPlan, build_character_design_plan
from .projection import HybridGenerationContext


@dataclass(frozen=True)
class HybridSemanticCase:
    """One request-owned case shared by generation facts and evaluation context."""

    case_id: str
    brief: str
    plan: CharacterDesignPlan
    allowed_actors: tuple[str, ...]
    allowed_trigger_events: tuple[str, ...]
    evaluator_requirement_id: str
    evaluator_trigger_subject_kinds: tuple[str, ...]
    evaluator_trigger_events: tuple[str, ...]
    evaluator_effect_subject_kinds: tuple[str, ...]
    evaluator_effect_operations: tuple[str, ...]
    evaluator_feedback_events: tuple[str, ...]
    evaluator_feedback_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.brief.strip():
            raise ValueError("HybridSemanticCase identity and brief must be non-empty")
        if not isinstance(self.plan, CharacterDesignPlan):
            raise TypeError("plan must be a CharacterDesignPlan")

    def generation_context(self) -> HybridGenerationContext:
        """Return only request/plan facts and public structural vocabulary."""

        return HybridGenerationContext(
            self.brief,
            plan=self.plan,
            case_id=self.case_id,
            contract_profile="aligned_v1",
            allowed_actors=self.allowed_actors,
            allowed_trigger_events=self.allowed_trigger_events,
            allowed_feedback_events=self.evaluator_feedback_events,
            allowed_feedback_relations=self.evaluator_feedback_operations,
        )

    def evaluation_context(self) -> Mapping[str, object]:
        """Build the evaluator context from this same authoritative case."""

        return MappingProxyType(
            {
                "intent": MappingProxyType(
                    {
                        "mechanic_requirements": (
                            MappingProxyType(
                                {
                                    "requirement_id": self.evaluator_requirement_id,
                                    "trigger": MappingProxyType(
                                        {
                                            "subject_kinds": self.evaluator_trigger_subject_kinds,
                                            "events": self.evaluator_trigger_events,
                                            "source_kinds": (),
                                        }
                                    ),
                                    "effect": MappingProxyType(
                                        {
                                            "subject_kinds": self.evaluator_effect_subject_kinds,
                                            "operations": self.evaluator_effect_operations,
                                            "object_kinds": (),
                                        }
                                    ),
                                    "feedback": MappingProxyType(
                                        {
                                            "required": True,
                                            "events": self.evaluator_feedback_events,
                                            "operations": self.evaluator_feedback_operations,
                                        }
                                    ),
                                }
                            ),
                        ),
                        "forbidden_mechanic_families": (),
                        "hard_constraint_conflicts": (),
                    }
                ),
                "combat_role_profile": MappingProxyType(
                    {
                        "primary_role": self.plan.combat_role_profile.primary_role,
                        "secondary_roles": self.plan.combat_role_profile.secondary_roles,
                    }
                ),
                "reference_review_context": None,
            }
        )


def build_authoritative_support_case() -> HybridSemanticCase:
    """Create the generic support case used by the aligned configuration."""

    brief = (
        "Design a support ability: when the ability is invoked, it enables an ally; "
        "after the effect is resolved, feedback enables the continuation."
    )
    return HybridSemanticCase(
        case_id="case_13_support_alignment_v1",
        brief=brief,
        plan=build_character_design_plan(brief),
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked",),
        evaluator_requirement_id="req_support_alignment",
        evaluator_trigger_subject_kinds=("self",),
        evaluator_trigger_events=("ability_invoked",),
        evaluator_effect_subject_kinds=("ally",),
        evaluator_effect_operations=("ally_enablement",),
        evaluator_feedback_events=("effect_resolved",),
        evaluator_feedback_operations=("enables",),
    )


__all__ = ["HybridSemanticCase", "build_authoritative_support_case"]
