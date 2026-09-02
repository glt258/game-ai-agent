from __future__ import annotations

from dataclasses import dataclass, replace

from agents.canon_checker import CanonChecker, CanonCheckReport
from agents.character_generation import (
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
)
from agents.evaluation.context import EvaluationSubject
from agents.evaluation.models import EvaluationResult
from agents.evaluation.runner import EvaluationRunner
from character_intelligence import CharacterDesignIntent, CharacterDesignPlan

from ..errors import WebApplicationError, map_validation_exception
from ..schemas.characters import CharacterGenerationRequestDTO
from ..schemas.validation import CharacterValidationRequestDTO
from .character_generation import CharacterGenerationApplication


@dataclass(frozen=True)
class CharacterValidationApplicationResult:
    request: CharacterDesignRequest
    draft: CharacterDraft
    canon: CanonCheckReport
    evaluation: EvaluationResult


def _plan_for_request(request: CharacterDesignRequest, *, factions=None) -> CharacterDesignPlan:
    plan = CharacterDesignPlan.from_text(request.brief, factions=factions)
    if request.combat_role_profile is None:
        return plan
    intent: CharacterDesignIntent = replace(
        plan.parsed_intent,
        combat_role_profile=request.combat_role_profile,
    )
    return CharacterDesignPlan.from_intent(intent, factions=factions)


class CharacterValidationApplication:
    """Deep validation seam for one edited draft, with no provider or repair."""

    def __init__(
        self,
        *,
        checker: CanonChecker | None = None,
        evaluation_runner: EvaluationRunner | None = None,
    ) -> None:
        self.checker = checker or CanonChecker()
        self.evaluation_runner = evaluation_runner or EvaluationRunner()

    @staticmethod
    def to_domain_request(payload: CharacterGenerationRequestDTO) -> CharacterDesignRequest:
        return CharacterGenerationApplication.to_domain_request(payload)

    def validate(
        self,
        payload: CharacterValidationRequestDTO,
    ) -> CharacterValidationApplicationResult:
        try:
            request = self.to_domain_request(payload.request)
            draft = CharacterDraft.from_mapping(payload.draft.model_dump(mode="json"))
            plan = _plan_for_request(request, factions=self.checker.context.resolver.factions)
        except WebApplicationError:
            raise
        except Exception as error:
            raise map_validation_exception(error) from None

        try:
            generation = CharacterGenerationResult(
                draft=draft,
                sources=(),
                audit=CharacterGenerationAudit(
                    request_id=request.request_id,
                    tool_rounds=0,
                    tool_calls=(),
                    source_ids=(),
                ),
                design_plan=plan,
            )
            subject = EvaluationSubject(
                request=request,
                generation_result=generation,
            )
            canon = self.checker.check(draft, request=request)
            evaluation = self.evaluation_runner.run(
                subject,
                evaluation_id=f"validation:{request.request_id}:{draft.draft_id}",
            )
            return CharacterValidationApplicationResult(
                request=request,
                draft=draft,
                canon=canon,
                evaluation=evaluation,
            )
        except WebApplicationError:
            raise
        except Exception:
            raise WebApplicationError(
                "VALIDATION_RUNTIME_ERROR",
                "Character validation could not complete safely.",
                status_code=500,
                stage="validation",
                retryable=False,
            ) from None


__all__ = [
    "CharacterValidationApplication",
    "CharacterValidationApplicationResult",
]
