from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from agents.canon_checker import CanonChecker
from agents.character_generation import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    CharacterGenerationResult,
)
from agents.character_repair import (
    CharacterAuthoringResult,
    CharacterAuthoringWorkflow,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
)
from agents.evaluation.context import EvaluationSubject
from agents.evaluation.models import EvaluationResult
from agents.evaluation.runner import EvaluationRunner
from agents.model_factory import character_model_from_environment
from agents.model_protocol import AgentModel
from combat_semantics import CombatRoleProfile

from ..errors import WebApplicationError, map_generation_exception
from ..schemas.characters import CharacterGenerationRequestDTO


@dataclass(frozen=True)
class CharacterGenerationApplicationResult:
    request: CharacterDesignRequest
    generation: CharacterGenerationResult
    authoring: CharacterAuthoringResult
    evaluation: EvaluationResult


class _RecordingGenerationAgent:
    """Adapter that preserves the existing workflow while exposing its result."""

    def __init__(self, delegate: CharacterGenerationAgent, *, use_intent_layer: bool) -> None:
        self.delegate = delegate
        self.use_intent_layer = use_intent_layer
        self.result: CharacterGenerationResult | None = None

    def generate(self, request: CharacterDesignRequest) -> CharacterGenerationResult:
        self.result = self.delegate.generate(
            request,
            use_intent_layer=self.use_intent_layer,
        )
        return self.result


class CharacterGenerationApplication:
    """Deep application seam for one synchronous Web character generation."""

    def __init__(
        self,
        generation_agent: CharacterGenerationAgent | None = None,
        *,
        repair_agent: CharacterRepairAgent | None = None,
        checker: CanonChecker | None = None,
        evaluation_runner: EvaluationRunner | None = None,
        generation_mode: str = "offline",
        use_intent_layer: bool = True,
    ) -> None:
        if generation_mode not in {"offline", "live"}:
            raise ValueError("generation_mode must be 'offline' or 'live'")
        self.generation_mode = generation_mode
        self.checker = checker or CanonChecker()
        self.evaluation_runner = evaluation_runner or EvaluationRunner()
        if generation_agent is None:
            model = character_model_from_environment(mode_override=generation_mode)
            generation_agent = CharacterGenerationAgent(model)
            if repair_agent is None:
                repair_model: AgentModel = (
                    DeterministicCharacterRepairModel() if generation_mode == "offline" else model
                )
                repair_agent = CharacterRepairAgent(repair_model, checker=self.checker)
        elif repair_agent is None:
            repair_agent = CharacterRepairAgent(
                DeterministicCharacterRepairModel(),
                checker=self.checker,
            )
        self.generation_agent = generation_agent
        self.repair_agent = repair_agent
        self.use_intent_layer = use_intent_layer

    @staticmethod
    def to_domain_request(payload: CharacterGenerationRequestDTO) -> CharacterDesignRequest:
        request_id = payload.request_id or f"web_request_{uuid4().hex}"
        return CharacterDesignRequest(
            brief=payload.brief,
            hard_constraints=tuple(payload.hard_constraints),
            soft_preferences=tuple(payload.soft_preferences),
            forbidden_elements=tuple(payload.forbidden_elements),
            desired_connections=tuple(payload.desired_connections),
            request_id=request_id,
            combat_role_profile=(
                CombatRoleProfile(
                    primary_role=payload.combat_role_profile.primary_role,
                    secondary_roles=tuple(payload.combat_role_profile.secondary_roles),
                )
                if payload.combat_role_profile is not None
                else None
            ),
        )

    def generate(
        self,
        payload: CharacterGenerationRequestDTO,
    ) -> CharacterGenerationApplicationResult:
        request = self.to_domain_request(payload)
        recorder = _RecordingGenerationAgent(
            self.generation_agent,
            use_intent_layer=self.use_intent_layer,
        )
        workflow = CharacterAuthoringWorkflow(
            recorder,
            self.repair_agent,
            checker=self.checker,
        )
        try:
            authoring = workflow.run(request)
            generation = recorder.result
            if generation is None:
                raise RuntimeError("generation workflow returned no result")
            evaluation = self.evaluation_runner.run(
                EvaluationSubject(
                    request=request,
                    generation_result=generation,
                    authoring_result=authoring,
                ),
                evaluation_id=f"evaluation:{request.request_id}",
            )
            return CharacterGenerationApplicationResult(
                request,
                generation,
                authoring,
                evaluation,
            )
        except WebApplicationError:
            raise
        except Exception as error:
            raise map_generation_exception(error) from None


__all__ = ["CharacterGenerationApplication", "CharacterGenerationApplicationResult"]
