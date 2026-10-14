from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4

from agents.canon_checker import CanonChecker
from agents.character_generation import (
    CharacterDesignRequest,
)
from agents.character_generation_v2_workflow import (
    CharacterGenerationCallAccounting,
    CharacterGenerationV2SpecInputs,
    CharacterGenerationV2Workflow,
    CharacterGenerationV2WorkflowAudit,
    build_character_generation_v2_spec_inputs,
)
from agents.character_repair import (
    CharacterAuthoringResult,
    CharacterAuthoringWorkflow,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
)
from agents.errors import ModelConfigurationError
from agents.evaluation.context import EvaluationSubject
from agents.evaluation.models import EvaluationResult
from agents.evaluation.runner import EvaluationRunner
from agents.model_factory import LiveLLMSettings, character_model_from_environment
from agents.model_protocol import AgentModel
from agents.models import AgentPrompt, ModelInvocationAudit, ModelTurn
from agents.reliability import (
    OperationDeadline,
    current_invocation_context,
    current_live_execution_progress,
    default_invocation_context,
    invocation_context,
)
from character_intelligence.character_draft import CharacterDraft
from character_intelligence.context import (
    CharacterPlanningContextV2,
    assemble_character_planning_context_v2,
)
from character_intelligence.field_authorization import (
    CharacterGenerationField,
    FieldAuthorizationPolicy,
    FieldAuthorizationState,
)
from character_intelligence.field_authorization_canon_adapter import (
    CanonFieldEvidenceAudit,
    adapt_request_scoped_canon_field_evidence,
    build_request_scoped_canon_source_snapshot,
)
from character_intelligence.field_authorization_resolver import (
    CharacterFieldAuthorizationRequest,
    resolve_character_field_authorization,
)
from character_intelligence.generator_v2 import (
    CharacterGenerationV2Result,
    CharacterGenerationV2Status,
)
from character_intelligence.intent import (
    ExplicitAgeRequirement,
    parse_character_design_intent,
    parse_explicit_age_requirement,
    parse_explicit_gender_requirement,
)
from character_intelligence.naming_design import CharacterNamingDesignV1
from character_intelligence.planner import CharacterDesignPlan
from character_intelligence.planner.character_generation_spec import (
    CHARACTER_GENERATION_V2_ROUTE,
)
from combat_semantics import CombatRoleProfile
from knowledge.resolver import KnowledgeResolver

from ..errors import WebApplicationError, map_generation_exception
from ..schemas.characters import CharacterGenerationRequestDTO
from .live_jobs import LiveJobRegistry, LiveJobSnapshot


class CharacterGenerationRoute(str, Enum):
    """The only supported production character-generation route."""

    CHARACTER_GENERATION_V2 = CHARACTER_GENERATION_V2_ROUTE


DEFAULT_NEW_DESIGN_FIELDS = (
    CharacterGenerationField.OCCUPATION,
    CharacterGenerationField.PERSONALITY,
    CharacterGenerationField.DESIGN_PITCH,
    CharacterGenerationField.BACKGROUND,
    CharacterGenerationField.STORY_HOOK,
)


class OfflineCharacterGenerationV2Model:
    """Deterministic provider fixture that exercises each production V2 stage."""

    _CONCEPTS = (
        {
            "concept_id": "concept_1",
            "one_line_identity": "A careful route steward who keeps a strained team moving.",
            "dramatic_axis": "Choose between personal certainty and shared trust.",
            "character_contradiction": "Seeks control while fearing dependence.",
            "player_hook": "Help a guarded ally decide when to trust the team.",
            "relationship_axis": "Build trust through shared responsibility.",
            "gameplay_fantasy": "Protect allies during a short response window.",
            "visual_anchor": "An asymmetrical field coat with a clear signal motif.",
            "differentiation_basis": ["A protection role shaped by coordination, not command."],
            "major_risk": "The support role could read as a generic coordinator.",
        },
        {
            "concept_id": "concept_2",
            "one_line_identity": "A mobile responder who turns setbacks into team openings.",
            "dramatic_axis": "Choose whether a public failure becomes a shared lesson.",
            "character_contradiction": "Acts quickly but hesitates to accept help.",
            "player_hook": "Coordinate a rescue whose success depends on delegation.",
            "relationship_axis": "Let another person carry part of the risk.",
            "gameplay_fantasy": "Redirect pressure and create a safe handoff.",
            "visual_anchor": "A compact silhouette with a bright crossing-line motif.",
            "differentiation_basis": ["A response loop centered on safe handoffs."],
            "major_risk": "The rescue theme could overtake the character's own motive.",
        },
        {
            "concept_id": "concept_3",
            "one_line_identity": "A quiet investigator who makes hidden choices visible.",
            "dramatic_axis": "Choose between preserving a secret and naming its cost.",
            "character_contradiction": "Values transparency but avoids personal disclosure.",
            "player_hook": "Uncover why a useful record was deliberately left incomplete.",
            "relationship_axis": "Trade guarded observation for honest disclosure.",
            "gameplay_fantasy": "Expose a threat and open a precise counter window.",
            "visual_anchor": "Layered sleeves and a narrow lens-shaped accessory.",
            "differentiation_basis": ["Information is expressed through timing and exposure."],
            "major_risk": "The investigator premise could become exposition-heavy.",
        },
    )

    _NAME_CANDIDATES = (
        {
            "candidate_id": "c1",
            "name": "Qavren",
            "identity_kind": "PERSONAL_NAME",
            "identity_rationale": "这是独立人名形式，能识别她本人而不依赖任何岗位。",
            "naming_style": "原创幻想式",
            "cultural_inspiration": "原创构词，无具体出处主张",
            "phonetic_rationale": "辅音起音清楚，短尾音利落。",
            "character_alignment": "适合克制但可靠的角色气质。",
            "tradeoffs": "陌生语感需要剧情帮助记忆。",
        },
        {
            "candidate_id": "c2",
            "name": "Iscalen",
            "identity_kind": "PERSONAL_NAME",
            "identity_rationale": "这是人物自己的名字；即使离开当前工作也仍然称呼她。",
            "naming_style": "跨文化幻想式",
            "cultural_inspiration": "原创构词，借鉴开放音节节奏",
            "phonetic_rationale": "三拍节奏从轻到重，读音有延展感。",
            "character_alignment": "与温和、独立的角色方向相容。",
            "tradeoffs": "比短代号更长。",
        },
        {
            "candidate_id": "c3",
            "name": "Nymora",
            "identity_kind": "PERSONAL_NAME",
            "identity_rationale": "这是个人身份名，不是在陈述她承担的职责。",
            "naming_style": "简洁幻想式",
            "cultural_inspiration": "原创构词，没有文化出处主张",
            "phonetic_rationale": "辅音与开口元音交替，发音连贯。",
            "character_alignment": "有较强记忆点，适合情感支点。",
            "tradeoffs": "意象较抽象。",
        },
    )

    _NEW_DESIGN_VALUES = {
        "occupation": "field coordinator",
        "social_role": "supports safe movement through the city",
        "design_pitch": "A measured responder who creates room for others to act.",
        "personality": ["measured", "observant", "reluctant to delegate"],
        "background": "She learned to plan routes after a rescue failed for lack of coordination.",
        "story_hook": "A new emergency forces her to trust a teammate with the final decision.",
        "ability_concept": "Redirects pressure to create a brief team handoff window.",
        "knowledge_scope": "Local routes and the limits of her own field experience.",
    }

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        if prompt.response_format == "character_concept_search":
            output: object = {"concepts": [dict(item) for item in self._CONCEPTS]}
        elif prompt.response_format == "character_concept_selection":
            output = {
                "selected_concept_id": "concept_2",
                "selection_reasons": [
                    "It offers a clear team handoff and a distinct pressure response."
                ],
                "preserve_elements": ["dramatic_axis", "player_hook"],
            }
        elif prompt.response_format == "character_planner_proposal":
            output = {
                "character_core": {
                    "core_desire": "Protect people without deciding everything for them.",
                    "core_fear": "A delayed choice will leave someone unsupported.",
                },
                "gameplay_identity": {
                    "gameplay_fantasy": "Redirect pressure and make a safe team handoff.",
                    "mechanic_identity_direction": "A short response window rewards deliberate timing.",
                },
                "character_naming": {
                    "candidates": [dict(item) for item in self._NAME_CANDIDATES],
                    "selected_candidate_id": "c1",
                    "selection_reasons": ["The compact sound fits the restrained character direction."],
                    "rejected_candidates": [],
                },
            }
        elif prompt.response_format in {"character_draft", "character_draft_recovery"}:
            output = self._draft_output(prompt)
        else:
            raise ValueError(
                f"offline V2 model does not support response format {prompt.response_format!r}"
            )
        audit = ModelInvocationAudit(
            session_id=prompt.session_id,
            turn_number=prompt.turn_number,
            provider="offline",
            model="deterministic-character-generation-v2",
            outcome="success",
            latency_ms=0.0,
            retry_count=0,
            response_contract=prompt.response_format,
            purpose=prompt.invocation_purpose,
        )
        return ModelTurn(structured_output=output, invocation=audit)

    def _draft_output(self, prompt: AgentPrompt) -> Mapping[str, object]:
        payload = prompt.authoring_payload
        if not isinstance(payload, Mapping):
            raise ValueError("V2 offline prompt is missing its bounded payload")
        model_input = payload.get("finalization_input", payload)
        if not isinstance(model_input, Mapping):
            raise ValueError("V2 offline finalization input is invalid")
        spec = model_input.get("spec")
        if not isinstance(spec, Mapping):
            raise ValueError("V2 offline finalization input has no frozen spec")
        naming = spec.get("naming_design")
        if not isinstance(naming, Mapping) or not isinstance(naming.get("selected_name"), str):
            raise ValueError("V2 offline spec has no frozen name")
        age_requirement_data = spec.get("age_requirement")
        age_requirement = None
        if age_requirement_data is not None:
            if not isinstance(age_requirement_data, Mapping):
                raise ValueError("V2 offline spec has an invalid age requirement")
            age_requirement = ExplicitAgeRequirement.from_mapping(
                age_requirement_data
            )
        requested_affiliation_id = spec.get("requested_affiliation_id")
        if requested_affiliation_id is not None and not isinstance(
            requested_affiliation_id, str
        ):
            raise ValueError("V2 offline spec has an invalid requested affiliation")
        policy = spec.get("field_authorization_policy")
        if not isinstance(policy, Mapping) or not isinstance(policy.get("field_authorizations"), Mapping):
            raise ValueError("V2 offline spec has no field authorization matrix")

        draft_id_suffix = re.sub(r"[^A-Za-z0-9_.-]", "_", prompt.session_id)
        draft: dict[str, object] = {
            "draft_id": f"draft_{draft_id_suffix}",
            "status": "draft",
            "name": naming["selected_name"],
            "canonical_character_id": None,
            "age": age_requirement.preferred_age if age_requirement else None,
            "age_range": (
                f"{age_requirement.minimum_age}-{age_requirement.maximum_age}"
                if age_requirement and age_requirement.approximate
                else None
            ),
            "gender": self._gender_value(spec.get("gender_requirement")),
            "faction_id": requested_affiliation_id,
            "occupation": "",
            "social_role": "",
            "combat_role_profile": spec.get("combat_semantics")
            or {"primary_role": None, "secondary_roles": []},
            "design_pitch": "",
            "personality": [],
            "background": "",
            "story_hook": "",
            "relationships": [],
            "ability_concept": "",
            "knowledge_scope": "",
            "canon_basis": [],
            "new_design_elements": [],
            "open_questions": [],
            "constraint_notes": [],
            "story_link": None,
            "proposed_new_content": [],
        }
        declarations: list[str] = []
        for field_value in CharacterGenerationField:
            entry = policy["field_authorizations"].get(field_value.value)
            if not isinstance(entry, Mapping):
                raise ValueError(f"V2 offline policy has no {field_value.value!r} entry")
            state = entry.get("state")
            if state == FieldAuthorizationState.NEW_DESIGN_AUTHORIZED.value:
                value = self._NEW_DESIGN_VALUES[field_value.value]
                draft[field_value.value] = value
                declarations.append(f"new_design:{field_value.value}:")
            elif state == FieldAuthorizationState.CANON_GROUNDED_ONLY.value:
                exact_values = entry.get("allowed_exact_values")
                if not isinstance(exact_values, (tuple, list)) or not exact_values:
                    raise ValueError(
                        f"V2 offline policy has no exact value for {field_value.value!r}"
                    )
                draft[field_value.value] = exact_values[0]
        draft["new_design_elements"] = declarations

        if prompt.response_format == "character_draft_recovery":
            missing_fields = payload.get("missing_fields")
            if not isinstance(missing_fields, (tuple, list)):
                raise ValueError("V2 offline recovery payload has no missing_fields list")
            return {field: draft[field] for field in missing_fields if field in draft}
        return draft

    @staticmethod
    def _gender_value(value: object) -> str | None:
        if not isinstance(value, Mapping):
            return None
        if value.get("remain_unspecified") is True:
            return None
        required = value.get("required_value")
        return required if isinstance(required, str) else None


@dataclass(frozen=True)
class CharacterGenerationApplicationResult:
    request: CharacterDesignRequest
    generator_result: CharacterGenerationV2Result
    authoring: CharacterAuthoringResult
    evaluation: EvaluationResult
    design_plan: CharacterDesignPlan
    route: CharacterGenerationRoute = CharacterGenerationRoute.CHARACTER_GENERATION_V2
    workflow_audit: CharacterGenerationV2WorkflowAudit | None = None
    call_accounting: CharacterGenerationCallAccounting | None = None
    canon_field_evidence_audit: tuple[CanonFieldEvidenceAudit, ...] = ()
    naming_design: CharacterNamingDesignV1 | None = None

    @property
    def model_invocations(self) -> tuple[ModelInvocationAudit, ...]:
        planning = self.workflow_audit.planning_model_invocations if self.workflow_audit else ()
        generation = self.generator_result.audit.model_invocations
        repair = self.authoring.repair_result.model_audit
        return tuple((*planning, *generation, *repair))


class _CompletedDraftSource:
    """Adapt only a completed shared draft to the existing authoring workflow."""

    def __init__(self, draft: CharacterDraft) -> None:
        self.draft = draft

    def generate(self, request: CharacterDesignRequest) -> "_CompletedDraftSource":
        del request
        return self


class CharacterGenerationApplication:
    """Application seam for the sole production V2 character workflow."""

    def __init__(
        self,
        *,
        repair_agent: CharacterRepairAgent | None = None,
        checker: CanonChecker | None = None,
        evaluation_runner: EvaluationRunner | None = None,
        generation_mode: str = "offline",
        environment: Mapping[str, str] | None = None,
        default_new_design_fields: tuple[CharacterGenerationField, ...] = DEFAULT_NEW_DESIGN_FIELDS,
        operation_deadline_seconds: float = 90.0,
        v2_workflow: CharacterGenerationV2Workflow,
    ) -> None:
        if generation_mode not in {"offline", "live"}:
            raise ValueError("generation_mode must be 'offline' or 'live'")
        self.generation_mode = generation_mode
        self.environment = dict(environment) if environment is not None else None
        self.default_new_design_fields = tuple(default_new_design_fields)
        self.checker = checker or CanonChecker()
        self.evaluation_runner = evaluation_runner or EvaluationRunner()
        if not isinstance(v2_workflow, CharacterGenerationV2Workflow):
            raise TypeError("v2_workflow must be CharacterGenerationV2Workflow")
        if repair_agent is None:
            if generation_mode == "offline":
                repair_model: AgentModel = DeterministicCharacterRepairModel()
            else:
                repair_model = character_model_from_environment(
                    environment=self.environment,
                    mode_override="live",
                )
            repair_agent = CharacterRepairAgent(repair_model, checker=self.checker)
        self.repair_agent = repair_agent
        self.operation_deadline_seconds = operation_deadline_seconds
        self.v2_workflow = v2_workflow

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
        *,
        route: CharacterGenerationRoute = CharacterGenerationRoute.CHARACTER_GENERATION_V2,
        field_authorization_request: CharacterFieldAuthorizationRequest | None = None,
    ) -> CharacterGenerationApplicationResult:
        try:
            if route is not CharacterGenerationRoute.CHARACTER_GENERATION_V2:
                raise ValueError("only Character Generation V2 is available in production")
            request = self.to_domain_request(payload)
            with default_invocation_context(
                budget_seconds=self.operation_deadline_seconds,
            ) if self.generation_mode == "live" else nullcontext():
                return self._generate_v2(request, field_authorization_request)
        except WebApplicationError:
            raise
        except Exception as error:
            raise map_generation_exception(error) from error

    def _generate_v2(
        self,
        request: CharacterDesignRequest,
        field_authorization_request: CharacterFieldAuthorizationRequest | None,
    ) -> CharacterGenerationApplicationResult:
        if self.v2_workflow is None:
            raise ValueError("the explicit V2 route is not configured")

        authorization_request = (
            field_authorization_request
            if field_authorization_request is not None
            else CharacterFieldAuthorizationRequest(
                new_design_fields=self.default_new_design_fields
            )
        )
        requested_source_ids = tuple(
            sorted(
                {
                    source_id
                    for source_ids in authorization_request.canon_source_ids.values()
                    for source_id in source_ids
                }
            )
        )
        project_canon_records: Mapping[str, object] = {}
        if requested_source_ids:
            resolver = getattr(getattr(self.checker, "context", None), "resolver", None)
            records = getattr(resolver, "characters", None)
            if not isinstance(records, Mapping):
                raise ValueError(
                    "request-scoped Canon authority requires the loaded Project Canon character registry"
                )
            project_canon_records = records

        canon_snapshot = build_request_scoped_canon_source_snapshot(
            project_canon_records,
            requested_source_ids,
        )
        canon_evidence = adapt_request_scoped_canon_field_evidence(
            canon_snapshot,
            authorization_request.canon_source_ids,
        )

        # Route selection and free-form request prose never grant field
        # authority; only the structured request plus adapter output reaches B1A.
        field_authorization_policy = resolve_character_field_authorization(
            authorization_request,
            canon_evidence=canon_evidence.authority_by_field,
        )
        workflow_result = self.v2_workflow.generate(
            request,
            field_authorization_policy=field_authorization_policy,
            bounded_canon_evidence=canon_evidence.bounded_generation_evidence,
        )
        generated = workflow_result.generator_result
        if generated.status is not CharacterGenerationV2Status.COMPLETED:
            failure = generated.failure_reason
            raise WebApplicationError(
                "CHARACTER_GENERATION_V2_FAILED",
                "Character Generation V2 could not produce a valid draft.",
                status_code=502,
                stage="generation",
                retryable=False,
                details={
                    "reason_code": failure.value if failure is not None else "unknown_failure",
                },
                model_invocations=(
                    *workflow_result.audit.planning_model_invocations,
                    *generated.audit.model_invocations,
                ),
            )
        if generated.draft is None:
            raise RuntimeError("completed V2 generation returned no CharacterDraft")

        parent_invocation = current_invocation_context()
        repair_context = nullcontext()
        if self.generation_mode == "live" and parent_invocation is not None:
            # INVARIANT: the 180s V2 Generator child can outlive the enclosing
            # application deadline. Repair remains bounded by the existing
            # application operation budget, with caller cancellation and retry
            # caps preserved in a fresh phase context.
            repair_context = invocation_context(
                deadline=OperationDeadline(self.operation_deadline_seconds),
                cancellation=parent_invocation.cancellation,
                policy=replace(
                    parent_invocation.policy,
                    operation_deadline_seconds=self.operation_deadline_seconds,
                ),
            )
        with repair_context:
            authoring = CharacterAuthoringWorkflow(
                _CompletedDraftSource(generated.draft),
                self.repair_agent,
                checker=self.checker,
            ).run(
                request,
                field_authorization_policy=workflow_result.audit.field_authorization_policy,
                bounded_canon_evidence=workflow_result.bounded_canon_evidence,
                protected_fields=(
                    ("name", "gender")
                    if parse_explicit_gender_requirement("\n".join((request.brief, *request.hard_constraints)))
                    is not None
                    else ("name",)
                ),
            )
        evaluation = self._evaluate(
            EvaluationSubject(
                request=request,
                generation_result=None,
                authoring_result=authoring,
                draft=generated.draft,
                design_plan=workflow_result.evaluation_design_plan,
                field_authorization_policy=workflow_result.audit.field_authorization_policy,
            ),
            request,
        )
        repair = authoring.repair_result
        # The shared workflow checks once; repair reuses that report on
        # pre-check failure and returns a distinct report only after rechecking.
        accounting = replace(
            workflow_result.call_accounting,
            canon_checks=1 + int(repair.final_check is not repair.initial_check),
            repair=int(repair.repair_attempted),
            evaluation=1,
        )
        return CharacterGenerationApplicationResult(
            request=request,
            generator_result=generated,
            authoring=authoring,
            evaluation=evaluation,
            design_plan=workflow_result.evaluation_design_plan,
            route=CharacterGenerationRoute.CHARACTER_GENERATION_V2,
            workflow_audit=workflow_result.audit,
            call_accounting=accounting,
            canon_field_evidence_audit=canon_evidence.audit,
            naming_design=workflow_result.naming_design,
        )

    def _evaluate(
        self,
        subject: EvaluationSubject,
        request: CharacterDesignRequest,
    ) -> EvaluationResult:
        progress = current_live_execution_progress()
        if progress is not None:
            progress.mark_phase("EVALUATION")
        evaluation = self.evaluation_runner.run(
            subject,
            evaluation_id=f"evaluation:{request.request_id}",
        )
        if progress is not None:
            progress.mark_phase("EVALUATION", stage="EVALUATION_COMPLETED")
        return evaluation

    def submit_live_job(
        self,
        payload: CharacterGenerationRequestDTO,
        registry: LiveJobRegistry,
    ) -> LiveJobSnapshot:
        """Submit this same V2 workflow to the shared live registry."""

        try:
            settings = LiveLLMSettings.from_environment(self.environment)
        except ModelConfigurationError as error:
            raise WebApplicationError(
                "CHARACTER_LIVE_CONFIGURATION_INVALID",
                "The backend live provider is not configured for this request.",
                status_code=503,
                stage="routing",
                retryable=False,
            ) from error
        service = self
        if self.generation_mode != "live":
            try:
                service = build_character_generation_v2_application(
                    environment=self.environment,
                    generation_mode="live",
                )
            except ModelConfigurationError as error:
                raise WebApplicationError(
                    "CHARACTER_LIVE_CONFIGURATION_INVALID",
                    "The backend live provider is not configured for this request.",
                    status_code=503,
                    stage="routing",
                    retryable=False,
                ) from error
        from ..mappers.character_generation import to_character_generation_response

        return registry.submit(
            kind="character_generation",
            provider=settings.provider,
            model=settings.model,
            work=lambda: to_character_generation_response(payload, service.generate(payload)),
        )


def build_character_generation_v2_application(
    *,
    environment: Mapping[str, str] | None = None,
    model_factory: Callable[..., AgentModel] | None = None,
    generation_mode: str = "offline",
    default_new_design_fields: tuple[CharacterGenerationField, ...] = DEFAULT_NEW_DESIGN_FIELDS,
    optional_new_design_fields: tuple[CharacterGenerationField, ...] = (),
) -> CharacterGenerationApplication:
    """Build the one production V2 Application in offline or live mode."""

    if generation_mode not in {"offline", "live"}:
        raise ValueError("generation_mode must be 'offline' or 'live'")
    new_design_fields = tuple(default_new_design_fields)
    if any(not isinstance(field_value, CharacterGenerationField) for field_value in new_design_fields):
        raise TypeError("default_new_design_fields must use CharacterGenerationField")
    if len(new_design_fields) != len(set(new_design_fields)):
        raise ValueError("default_new_design_fields must not contain duplicates")
    optional_fields = tuple(optional_new_design_fields)
    if any(not isinstance(field_value, CharacterGenerationField) for field_value in optional_fields):
        raise TypeError("optional_new_design_fields must use CharacterGenerationField")
    if len(optional_fields) != len(set(optional_fields)):
        raise ValueError("optional_new_design_fields must not contain duplicates")
    if not set(optional_fields).issubset(new_design_fields):
        raise ValueError("optional_new_design_fields must be authorized new-design fields")
    optional_field_set = frozenset(optional_fields)

    if model_factory is not None:
        generation_model = model_factory(
            environment=environment,
            mode_override=generation_mode,
        )
    elif generation_mode == "offline":
        generation_model = OfflineCharacterGenerationV2Model()
    else:
        generation_model = character_model_from_environment(
            environment=environment,
            mode_override="live",
        )

    resolver = KnowledgeResolver()
    checker = CanonChecker(resolver=resolver)

    def build_context(request: CharacterDesignRequest):
        intent_text = "\n".join((request.brief, *request.hard_constraints))
        parsed_intent = parse_character_design_intent(
            intent_text,
            factions=resolver.factions,
        )
        requested_combat = request.combat_role_profile
        if requested_combat is not None and not requested_combat.is_unspecified:
            parsed_intent = replace(
                parsed_intent,
                combat_role_profile=requested_combat,
            )
        parsed_intent = replace(
            parsed_intent,
            raw_request=request.brief,
            age_requirement=parse_explicit_age_requirement(intent_text),
            gender_requirement=parse_explicit_gender_requirement(intent_text),
        )
        plan = CharacterDesignPlan.from_intent(
            parsed_intent,
            factions=resolver.factions,
        )
        return assemble_character_planning_context_v2(
            plan,
            request=request.to_dict(),
            resolver=resolver,
            snapshot_id=f"character-generation-v2:{request.request_id}",
        )

    def build_spec_inputs(
        request: CharacterDesignRequest,
        context: CharacterPlanningContextV2,
        policy: FieldAuthorizationPolicy,
    ) -> CharacterGenerationV2SpecInputs:
        spec_inputs = build_character_generation_v2_spec_inputs(
            request,
            context,
            policy,
        )
        required_fields = tuple(
            field_value
            for field_value in spec_inputs.required_generation_fields
            if not (
                field_value in optional_field_set
                and policy.for_field(field_value).state
                is FieldAuthorizationState.NEW_DESIGN_AUTHORIZED
            )
        )
        if required_fields == spec_inputs.required_generation_fields:
            return spec_inputs
        return replace(spec_inputs, required_generation_fields=required_fields)

    workflow = CharacterGenerationV2Workflow(
        model=generation_model,
        context_builder=build_context,
        spec_inputs_provider=build_spec_inputs,
    )
    repair_model: AgentModel = (
        DeterministicCharacterRepairModel()
        if generation_mode == "offline"
        else generation_model
    )
    return CharacterGenerationApplication(
        repair_agent=CharacterRepairAgent(repair_model, checker=checker),
        checker=checker,
        generation_mode=generation_mode,
        environment=environment,
        default_new_design_fields=new_design_fields,
        v2_workflow=workflow,
    )


__all__ = [
    "build_character_generation_v2_application",
    "CharacterGenerationApplication",
    "CharacterGenerationApplicationResult",
    "CharacterGenerationRoute",
    "DEFAULT_NEW_DESIGN_FIELDS",
    "OfflineCharacterGenerationV2Model",
]
