"""Evaluation inputs kept separate from generation and authoring contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from character_intelligence import CharacterDesignIntent
from character_intelligence.field_authorization import FieldAuthorizationPolicy
from character_intelligence.planner.character_plan import CharacterDesignPlan
from character_skill import ProtocolSkillKitCandidate, SkillValidationContext, SkillValidationReport
from combat_semantics import CombatRoleProfile

from ..character_generation import CharacterDesignRequest, CharacterDraft, CharacterGenerationResult
from ..character_repair import CharacterAuthoringResult


@dataclass(frozen=True)
class EvaluationSubject:
    """Read-only subject presented to one or more evaluation validators.

    ``generation_result`` may be ``None`` when a generation route supplies a
    shared draft and plan directly. The evaluator only observes the supplied
    values. V2 field authority scopes representation checks without granting
    authority from generated content.
    """

    request: CharacterDesignRequest
    generation_result: CharacterGenerationResult | None
    authoring_result: CharacterAuthoringResult | None = None
    generation_error: BaseException | None = None
    case_metadata: Mapping[str, Any] | None = None
    skill_validation_context: SkillValidationContext | Mapping[str, Any] | None = None
    draft: CharacterDraft | None = None
    design_plan: CharacterDesignPlan | None = None
    field_authorization_policy: FieldAuthorizationPolicy | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, CharacterDesignRequest):
            raise TypeError("request must be a CharacterDesignRequest")
        if self.generation_result is not None and not isinstance(
            self.generation_result, CharacterGenerationResult
        ):
            raise TypeError("generation_result must be a CharacterGenerationResult or None")
        if self.draft is not None and not isinstance(self.draft, CharacterDraft):
            raise TypeError("draft must be a CharacterDraft or None")
        if self.design_plan is not None and not isinstance(self.design_plan, CharacterDesignPlan):
            raise TypeError("design_plan must be a CharacterDesignPlan or None")
        if self.field_authorization_policy is not None and not isinstance(
            self.field_authorization_policy, FieldAuthorizationPolicy
        ):
            raise TypeError(
                "field_authorization_policy must be a FieldAuthorizationPolicy or None"
            )
        if self.authoring_result is not None and not isinstance(
            self.authoring_result, CharacterAuthoringResult
        ):
            raise TypeError("authoring_result must be a CharacterAuthoringResult or None")
        if self.generation_error is not None and not isinstance(
            self.generation_error, BaseException
        ):
            raise TypeError("generation_error must be an exception or None")
        if self.case_metadata is not None:
            if not isinstance(self.case_metadata, Mapping):
                raise TypeError("case_metadata must be a mapping or None")
            object.__setattr__(
                self,
                "case_metadata",
                MappingProxyType(dict(self.case_metadata)),
            )
        if self.skill_validation_context is not None:
            context = self.skill_validation_context
            if isinstance(context, Mapping):
                context = SkillValidationContext.from_mapping(context)
            elif not isinstance(context, SkillValidationContext):
                raise TypeError(
                    "skill_validation_context must be a SkillValidationContext, mapping, or None"
                )
            object.__setattr__(self, "skill_validation_context", context)


@dataclass(frozen=True)
class EvaluationContext:
    """Resolved, read-only context supplied to evaluation validators."""

    subject: EvaluationSubject
    intent: CharacterDesignIntent | None
    draft: CharacterDraft | None = None
    skill_validation_context: SkillValidationContext | None = None
    skill_candidate: ProtocolSkillKitCandidate | None = None
    skill_validation_report: SkillValidationReport | None = None
    expected_affiliation_id: str | None = None
    design_plan: CharacterDesignPlan | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, EvaluationSubject):
            raise TypeError("subject must be an EvaluationSubject")
        if self.intent is not None and not isinstance(self.intent, CharacterDesignIntent):
            raise TypeError("intent must be a CharacterDesignIntent")
        if self.draft is not None and not isinstance(self.draft, CharacterDraft):
            raise TypeError("draft must be a CharacterDraft or None")
        if self.design_plan is not None and not isinstance(self.design_plan, CharacterDesignPlan):
            raise TypeError("design_plan must be a CharacterDesignPlan or None")
        if self.draft is None:
            draft = self.subject.draft
            if draft is None and self.subject.generation_result is not None:
                draft = self.subject.generation_result.draft
            object.__setattr__(self, "draft", draft)
        plan = self.design_plan or self.subject.design_plan
        if plan is None and self.subject.generation_result is not None:
            plan = self.subject.generation_result.design_plan
        if self.design_plan is None:
            object.__setattr__(self, "design_plan", plan)
        if self.skill_validation_context is None:
            object.__setattr__(
                self,
                "skill_validation_context",
                self.subject.skill_validation_context,
            )
        if self.skill_validation_context is not None and not isinstance(
            self.skill_validation_context, SkillValidationContext
        ):
            raise TypeError(
                "skill_validation_context must be a SkillValidationContext or None"
            )
        shadow = (
            self.subject.generation_result.skill_shadow
            if self.subject.generation_result is not None
            else None
        )
        if self.skill_candidate is None and shadow is not None:
            candidate = getattr(shadow, "candidate", None)
            if isinstance(candidate, ProtocolSkillKitCandidate):
                object.__setattr__(self, "skill_candidate", candidate)
        if self.skill_validation_report is None and shadow is not None:
            report = getattr(shadow, "validation_report", None)
            if isinstance(report, SkillValidationReport):
                object.__setattr__(self, "skill_validation_report", report)
        if self.intent is not None and not isinstance(
            self.intent.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError("intent.combat_role_profile must be canonical")
        if self.draft is not None and not isinstance(
            self.draft.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError("draft.combat_role_profile must be canonical")
        plan_expected = (
            self.design_plan.expected_affiliation_id if self.design_plan is not None else None
        )
        intent_expected = self.intent.requested_affiliation_id if self.intent is not None else None
        resolved_expected = plan_expected if plan_expected is not None else intent_expected
        if self.expected_affiliation_id is not None and self.expected_affiliation_id != resolved_expected:
            raise ValueError("expected_affiliation_id must match the design plan")
        object.__setattr__(self, "expected_affiliation_id", resolved_expected)

    @classmethod
    def from_subject(cls, subject: EvaluationSubject) -> "EvaluationContext":
        """Resolve only the intent carried by the generation design plan."""

        if not isinstance(subject, EvaluationSubject):
            raise TypeError("subject must be an EvaluationSubject")
        generation_result = subject.generation_result
        design_plan = subject.design_plan or (
            generation_result.design_plan if generation_result is not None else None
        )
        intent = design_plan.parsed_intent if design_plan is not None else None
        draft = subject.draft or (
            generation_result.draft if generation_result is not None else None
        )
        return cls(
            subject=subject,
            intent=intent,
            draft=draft,
            skill_validation_context=subject.skill_validation_context,
            expected_affiliation_id=(
                design_plan.expected_affiliation_id
                if design_plan is not None
                else None
            ),
            design_plan=design_plan,
        )

    @property
    def request(self) -> CharacterDesignRequest:
        return self.subject.request

    @property
    def generation_result(self) -> CharacterGenerationResult | None:
        return self.subject.generation_result

    @property
    def intent_role_profile(self) -> CombatRoleProfile | None:
        """Canonical intent role profile exposed directly to validators."""

        return self.intent.combat_role_profile if self.intent is not None else None

    @property
    def draft_role_profile(self) -> CombatRoleProfile | None:
        """Canonical draft role profile exposed directly to validators."""

        return self.draft.combat_role_profile if self.draft is not None else None


__all__ = ["EvaluationContext", "EvaluationSubject"]
