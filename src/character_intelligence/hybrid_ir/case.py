"""Authoritative semantic case definitions for Hybrid generation/evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from character_skill.context import RESPONSE_EFFECT_FAMILIES

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
    continuation_family: str = ""
    mechanic_kind: str = "triggered"
    requires_feedback: bool = True

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.brief.strip():
            raise ValueError("HybridSemanticCase identity and brief must be non-empty")
        if not isinstance(self.plan, CharacterDesignPlan):
            raise TypeError("plan must be a CharacterDesignPlan")
        if self.contract_profile in {"generalization_v1", "generalization_v2"}:
            if self.generation_mode not in {"active", "passive", "reaction"}:
                raise ValueError("generalization generation mode must be canonical")
            if self.mechanic_kind not in {"triggered", "passive"}:
                raise ValueError("generalization mechanic kind must be canonical")
            if self.mechanic_kind == "triggered" and self.continuation_family and self.continuation_family not in RESPONSE_EFFECT_FAMILIES:
                raise ValueError("generalization continuation family must be canonical")
            if self.mechanic_kind == "passive" and (self.generation_mode != "passive" or self.requires_feedback):
                raise ValueError("passive generalization cases must be passive and feedback-free")

    def generation_context(self) -> HybridGenerationContext:
        """Return only request/plan facts and public structural vocabulary."""

        return HybridGenerationContext(
            self.brief,
            plan=self.plan,
            case_id=self.case_id,
            contract_profile=self.contract_profile,
            allowed_actors=self.allowed_actors,
            allowed_trigger_subjects=(
                self.evaluator_trigger_subject_kinds
                if self.mechanic_kind == "triggered"
                else None
            ),
            allowed_effect_subjects=self.evaluator_effect_subject_kinds,
            allowed_trigger_events=self.allowed_trigger_events if self.mechanic_kind == "triggered" else None,
            allowed_feedback_events=self.evaluator_feedback_events if self.requires_feedback else None,
            allowed_feedback_relations=self.evaluator_feedback_operations if self.requires_feedback else None,
            allowed_modes=(self.generation_mode,) if self.contract_profile in {"generalization_v1", "generalization_v2"} else None,
            allowed_response_effect_families=(self.continuation_family,)
            if self.contract_profile in {"generalization_v1", "generalization_v2"} and self.continuation_family
            else None,
            allowed_roles=(self.plan.combat_role_profile.primary_role,)
            if self.contract_profile in {"generalization_v1", "generalization_v2"}
            else None,
            allowed_centralities=("core",) if self.contract_profile in {"generalization_v1", "generalization_v2"} else None,
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
                                    **(
                                        {"mechanic_kind": self.mechanic_kind}
                                        if self.contract_profile == "generalization_v2"
                                        else {}
                                    ),
                                    **(
                                        {
                                            "trigger": MappingProxyType(
                                                {
                                                    "subject_kinds": self.evaluator_trigger_subject_kinds,
                                                    "events": self.evaluator_trigger_events,
                                                    "source_kinds": (),
                                                }
                                            )
                                        }
                                        if self.mechanic_kind == "triggered"
                                        else {}
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
                                            "required": self.requires_feedback,
                                            "events": self.evaluator_feedback_events,
                                            "operations": self.evaluator_feedback_operations,
                                        }
                                    ),
                                    **(
                                        {
                                            "allowed_modes": (self.generation_mode,),
                                        "allowed_response_effect_families": (
                                            (self.continuation_family,)
                                            if self.continuation_family
                                            else ()
                                        ),
                                        }
                                         if self.contract_profile in {"generalization_v1", "generalization_v2"}
                                        else {}
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
    """Return the four original offline pilot cases unchanged."""

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
            continuation_family="support",
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
            continuation_family="damage",
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
            continuation_family="control",
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
            continuation_family="recovery",
        ),
    )


def build_authoritative_final_coverage_cases() -> tuple[HybridSemanticCase, ...]:
    """Return the v2 Sub-DPS, Defense, and Basic Passive coverage cases."""

    return (
        HybridSemanticCase(
            case_id="generalization_sub_dps_v1",
            brief=(
                "Design a sub-DPS ability that reacts after an ally or team action completes, "
                "deals follow-up damage to an enemy, and is not the caster's primary direct strike."
            ),
            plan=build_character_design_plan("Design a sub-DPS character ability."),
            allowed_actors=("ally", "team", "enemy"),
            allowed_trigger_events=("action_completed",),
            evaluator_requirement_id="req_generalization_sub_dps",
            evaluator_trigger_subject_kinds=("ally", "team"),
            evaluator_trigger_events=("action_completed",),
            evaluator_effect_subject_kinds=("enemy",),
            evaluator_effect_operations=("follow_up_output",),
            evaluator_feedback_events=(),
            evaluator_feedback_operations=(),
            generation_mode="active",
            contract_profile="generalization_v2",
            mechanic_kind="triggered",
            requires_feedback=False,
        ),
        HybridSemanticCase(
            case_id="generalization_defense_v1",
            brief=(
                "Design a defense ability that reacts when an ally receives damage and provides "
                "threat protection for an ally or the team, without healing or ordinary ally enablement."
            ),
            plan=build_character_design_plan("Design a defense character reaction ability."),
            allowed_actors=("ally", "team"),
            allowed_trigger_events=("damage_received",),
            evaluator_requirement_id="req_generalization_defense",
            evaluator_trigger_subject_kinds=("ally",),
            evaluator_trigger_events=("damage_received",),
            evaluator_effect_subject_kinds=("ally", "team"),
            evaluator_effect_operations=("threat_protection",),
            evaluator_feedback_events=(),
            evaluator_feedback_operations=(),
            generation_mode="reaction",
            contract_profile="generalization_v2",
            mechanic_kind="triggered",
            requires_feedback=False,
        ),
        HybridSemanticCase(
            case_id="generalization_basic_passive_v1",
            brief=(
                "Design a basic passive support trait that is always on and enables the team. "
                "It has no activation trigger, feedback, continuation, duration, stack, resource, state, or summon."
            ),
            plan=build_character_design_plan("Design a support character basic passive."),
            allowed_actors=("team",),
            allowed_trigger_events=(),
            evaluator_requirement_id="req_generalization_basic_passive",
            evaluator_trigger_subject_kinds=(),
            evaluator_trigger_events=(),
            evaluator_effect_subject_kinds=("team",),
            evaluator_effect_operations=("ally_enablement",),
            evaluator_feedback_events=(),
            evaluator_feedback_operations=(),
            generation_mode="passive",
            contract_profile="generalization_v2",
            mechanic_kind="passive",
            requires_feedback=False,
        ),
    )


def build_authoritative_case_registry() -> Mapping[str, HybridSemanticCase]:
    """Return stable semantic IDs for all generalization pilot cases."""

    cases = (
        build_authoritative_support_case(),
        *build_authoritative_generalization_cases(),
        *build_authoritative_final_coverage_cases(),
    )
    return MappingProxyType({case.case_id: case for case in cases})


__all__ = [
    "HybridSemanticCase",
    "build_authoritative_case_registry",
    "build_authoritative_final_coverage_cases",
    "build_authoritative_generalization_cases",
    "build_authoritative_support_case",
]
