"""Evaluation inputs kept separate from generation and authoring contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from character_intelligence import CharacterDesignIntent
from combat_semantics import CombatRoleProfile

from ..character_generation import CharacterDesignRequest, CharacterDraft, CharacterGenerationResult
from ..character_repair import CharacterAuthoringResult


@dataclass(frozen=True)
class EvaluationSubject:
    """Read-only subject presented to one or more evaluation validators.

    ``generation_result`` is required as a field but may be ``None`` when a
    caller is preserving a failed generation attempt through ``generation_error``.
    The evaluator does not invoke generation, Canon checking, repair, or a
    model; it only observes the supplied subject.
    """

    request: CharacterDesignRequest
    generation_result: CharacterGenerationResult | None
    authoring_result: CharacterAuthoringResult | None = None
    generation_error: BaseException | None = None
    case_metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, CharacterDesignRequest):
            raise TypeError("request must be a CharacterDesignRequest")
        if self.generation_result is not None and not isinstance(
            self.generation_result, CharacterGenerationResult
        ):
            raise TypeError("generation_result must be a CharacterGenerationResult or None")
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


@dataclass(frozen=True)
class EvaluationContext:
    """Resolved, read-only context supplied to evaluation validators."""

    subject: EvaluationSubject
    intent: CharacterDesignIntent | None
    draft: CharacterDraft | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, EvaluationSubject):
            raise TypeError("subject must be an EvaluationSubject")
        if self.intent is not None and not isinstance(self.intent, CharacterDesignIntent):
            raise TypeError("intent must be a CharacterDesignIntent")
        if self.draft is not None and not isinstance(self.draft, CharacterDraft):
            raise TypeError("draft must be a CharacterDraft or None")
        if self.draft is None and self.subject.generation_result is not None:
            object.__setattr__(self, "draft", self.subject.generation_result.draft)
        if self.intent is not None and not isinstance(
            self.intent.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError("intent.combat_role_profile must be canonical")
        if self.draft is not None and not isinstance(
            self.draft.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError("draft.combat_role_profile must be canonical")

    @classmethod
    def from_subject(cls, subject: EvaluationSubject) -> "EvaluationContext":
        """Resolve only the intent carried by the generation design plan."""

        if not isinstance(subject, EvaluationSubject):
            raise TypeError("subject must be an EvaluationSubject")
        generation_result = subject.generation_result
        if generation_result is not None and generation_result.design_plan is not None:
            intent = generation_result.design_plan.parsed_intent
        else:
            intent = None
        draft = generation_result.draft if generation_result is not None else None
        return cls(subject=subject, intent=intent, draft=draft)

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
