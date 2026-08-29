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
    generation_mode: str = "active"
    contract_profile: str = "aligned_v1"

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
            contract_profile=self.contract_profile,
            allowed_actors=self.allowed_actors,
            allowed_trigger_events=self.allowed_trigger_events,
            allowed_feedback_events=self.evaluator_feedback_events,
            allowed_feedback_relations=self.evaluator_feedback_operations,
            allowed_modes=(self.generation_mode,) if self.contract_profile == "generalization_v1" else None,
            allowed_roles=(self.plan.combat_role_profile.primary_role,)
            if self.contract_profile == "generalization_v1"
            else None,
            allowed_centralities=("core",) if self.contract_profile == "generalization_v1" else None,
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


def build_authoritative_generalization_cases() -> tuple[HybridSemanticCase, ...]:
    """Return the four offline pilot cases from one authoritative registry."""

    return (
        HybridSemanticCase(
            case_id="generalization_support_alternate_v1",
            brief=(
                "Design an alternate support ability that reacts when an ally completes an action, "
                "enables the team, and modifies the continuation after the effect resolves."
            ),
            plan=build_character_design_plan(
                "Design an alternate support ability for a support character."
            ),
            allowed_actors=("ally", "team"),
            allowed_trigger_events=("action_completed",),
            evaluator_requirement_id="req_generalization_support_alternate",
            evaluator_trigger_subject_kinds=("ally",),
            evaluator_trigger_events=("action_completed",),
            evaluator_effect_subject_kinds=("team",),
            evaluator_effect_operations=("ally_enablement",),
            evaluator_feedback_events=("effect_resolved",),
            evaluator_feedback_operations=("modifies",),
            generation_mode="active",
            contract_profile="generalization_v1",
        ),
        HybridSemanticCase(
            case_id="generalization_dps_v1",
            brief=(
                "Design a main DPS ability that starts when the caster acts, deals primary damage to an enemy, "
                "and enables a follow-up damage continuation after resolution."
            ),
            plan=build_character_design_plan("Design a main DPS character ability."),
            allowed_actors=("self", "enemy"),
            allowed_trigger_events=("ability_invoked",),
            evaluator_requirement_id="req_generalization_dps",
            evaluator_trigger_subject_kinds=("self",),
            evaluator_trigger_events=("ability_invoked",),
            evaluator_effect_subject_kinds=("enemy",),
            evaluator_effect_operations=("direct_output",),
            evaluator_feedback_events=("effect_resolved",),
            evaluator_feedback_operations=("enables",),
            generation_mode="active",
            contract_profile="generalization_v1",
        ),
        HybridSemanticCase(
            case_id="generalization_control_v1",
            brief=(
                "Design a control ability that starts when the scene is entered, applies enemy action control "
                "without making damage the primary effect, and modifies the control continuation."
            ),
            plan=build_character_design_plan("Design a control character ability."),
            allowed_actors=("scene", "enemy"),
            allowed_trigger_events=("scene_entered",),
            evaluator_requirement_id="req_generalization_control",
            evaluator_trigger_subject_kinds=("scene",),
            evaluator_trigger_events=("scene_entered",),
            evaluator_effect_subject_kinds=("enemy",),
            evaluator_effect_operations=("enemy_action_control",),
            evaluator_feedback_events=("effect_resolved",),
            evaluator_feedback_operations=("modifies",),
            generation_mode="active",
            contract_profile="generalization_v1",
        ),
        HybridSemanticCase(
            case_id="generalization_reaction_heal_v1",
            brief=(
                "Design a reaction healer ability that activates when an ally receives damage, mitigates the ally, "
                "and enables a recovery continuation after the effect resolves."
            ),
            plan=build_character_design_plan("Design a healer character reaction ability."),
            allowed_actors=("ally",),
            allowed_trigger_events=("damage_received",),
            evaluator_requirement_id="req_generalization_reaction_heal",
            evaluator_trigger_subject_kinds=("ally",),
            evaluator_trigger_events=("damage_received",),
            evaluator_effect_subject_kinds=("ally",),
            evaluator_effect_operations=("recover_or_mitigate",),
            evaluator_feedback_events=("effect_resolved",),
            evaluator_feedback_operations=("enables",),
            generation_mode="reaction",
            contract_profile="generalization_v1",
        ),
    )


def build_authoritative_case_registry() -> Mapping[str, HybridSemanticCase]:
    """Return stable semantic IDs for all generalization pilot cases."""

    cases = (build_authoritative_support_case(), *build_authoritative_generalization_cases())
    return MappingProxyType({case.case_id: case for case in cases})


__all__ = [
    "HybridSemanticCase",
    "build_authoritative_case_registry",
    "build_authoritative_generalization_cases",
    "build_authoritative_support_case",
]
