"""Orchestrate the frozen V2 planning-to-draft path without legacy retrieval."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from character_intelligence.context import CharacterPlanningContextV2
from character_intelligence.field_authorization import (
    CHARACTER_GENERATION_FIELDS,
    CharacterGenerationField,
    FieldAuthorizationPolicy,
    FieldAuthorizationState,
)
from character_intelligence.finalization_input import (
    AllowedReferenceContextV1,
    BoundedGenerationEvidenceV1,
    build_character_finalization_input,
)
from character_intelligence.generator_v2 import (
    CharacterGenerationV2Generator,
    CharacterGenerationV2Result,
)
from character_intelligence.naming_design import CharacterNamingDesignV1
from character_intelligence.planner import CharacterDesignPlan
from character_intelligence.planner.character_generation_spec import (
    CHARACTER_GENERATION_V2_ROUTE,
    freeze_resolved_character_generation_spec,
)
from character_intelligence.planner.character_planner_v2 import CharacterPlannerV1Diagnostics
from character_intelligence.planner.resolution_routing import run_character_planning_v2_phase7

from .character_generation import CharacterDesignRequest
from .errors import ModelDeadlineExceededError
from .model_protocol import AgentModel
from .models import ModelInvocationAudit
from .reliability import OperationDeadline, current_invocation_context, invocation_context

_V2_GENERATOR_OPERATION_DEADLINE_SECONDS = 180.0


@dataclass(frozen=True)
class CharacterGenerationV2SpecInputs:
    """Bounded non-authority inputs supplied to the frozen V2 spec."""

    canon_locks: Mapping[str, object]
    required_generation_fields: tuple[CharacterGenerationField, ...]
    evidence: tuple[BoundedGenerationEvidenceV1, ...]
    reference_context: tuple[AllowedReferenceContextV1, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.canon_locks, Mapping):
            raise TypeError("canon_locks must be a mapping")
        object.__setattr__(self, "canon_locks", MappingProxyType(dict(self.canon_locks)))

        required_fields = tuple(self.required_generation_fields)
        if any(not isinstance(item, CharacterGenerationField) for item in required_fields):
            raise TypeError("required_generation_fields must use CharacterGenerationField")
        if len(required_fields) != len(set(required_fields)):
            raise ValueError("required_generation_fields must not contain duplicates")
        object.__setattr__(self, "required_generation_fields", required_fields)

        evidence = tuple(self.evidence)
        if any(not isinstance(item, BoundedGenerationEvidenceV1) for item in evidence):
            raise TypeError("evidence must contain BoundedGenerationEvidenceV1 values")
        object.__setattr__(self, "evidence", evidence)

        references = tuple(self.reference_context)
        if any(not isinstance(item, AllowedReferenceContextV1) for item in references):
            raise TypeError("reference_context must contain AllowedReferenceContextV1 values")
        object.__setattr__(self, "reference_context", references)


@dataclass(frozen=True)
class CharacterGenerationCallAccounting:
    """Count each logical workflow stage without conflating repair and B1C."""

    concept_search: int = 0
    selector: int = 0
    planner: int = 0
    generation: int = 0
    structural_recovery: int = 0
    canon_checks: int = 0
    repair: int = 0
    evaluation: int = 0


@dataclass(frozen=True)
class CharacterGenerationV2WorkflowAudit:
    """Identity, B1A authority, and safe Planner telemetry for V2 generation."""

    route_identity: str
    generator_identity: str
    request_id: str
    planning_context_snapshot_id: str
    selected_concept_id: str
    resolution_id: str
    planner_request_id: str
    spec_id: str
    spec_digest: str
    field_authorization_policy: FieldAuthorizationPolicy
    planner_diagnostics: CharacterPlannerV1Diagnostics
    planning_model_invocations: tuple[ModelInvocationAudit, ...]
    generator_operation_deadline_seconds: float | None
    generator_operation_duration_ms: float | None


@dataclass(frozen=True)
class CharacterGenerationV2WorkflowResult:
    """Return generated output plus the B1B evidence needed by downstream checks."""

    generator_result: CharacterGenerationV2Result
    audit: CharacterGenerationV2WorkflowAudit
    call_accounting: CharacterGenerationCallAccounting
    evaluation_design_plan: CharacterDesignPlan
    naming_design: CharacterNamingDesignV1
    bounded_canon_evidence: tuple[BoundedGenerationEvidenceV1, ...] = ()


PlanningContextBuilder = Callable[
    [CharacterDesignRequest], CharacterPlanningContextV2
]
SpecInputsProvider = Callable[
    [CharacterDesignRequest, CharacterPlanningContextV2, FieldAuthorizationPolicy],
    CharacterGenerationV2SpecInputs,
]


def build_character_generation_v2_spec_inputs(
    request: CharacterDesignRequest,
    context: CharacterPlanningContextV2,
    field_authorization_policy: FieldAuthorizationPolicy,
) -> CharacterGenerationV2SpecInputs:
    """Assemble bounded inputs from the Application-resolved B1A policy.

    This adapter supplies the injected SpecInputs seam but never owns or
    replaces the B1A policy. It selects fields already authorized for either
    new design or exact Canon grounding; bounded Canon facts arrive separately
    from the request-scoped evidence adapter at the workflow boundary.
    """

    if not isinstance(request, CharacterDesignRequest):
        raise TypeError("request must be a CharacterDesignRequest")
    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    if not isinstance(field_authorization_policy, FieldAuthorizationPolicy):
        raise TypeError("field_authorization_policy must be a FieldAuthorizationPolicy")

    # INVARIANT: this assembler reads policy states only; it never receives raw
    # Canon records or creates the values that establish field authority.
    required_fields = tuple(
        field_value
        for field_value in CHARACTER_GENERATION_FIELDS
        if field_authorization_policy.for_field(field_value).state
        in {
            FieldAuthorizationState.NEW_DESIGN_AUTHORIZED,
            FieldAuthorizationState.CANON_GROUNDED_ONLY,
        }
    )
    if not required_fields:
        raise ValueError(
            "V2 generation requires at least one authorized generation field"
        )

    return CharacterGenerationV2SpecInputs(
        canon_locks={},
        required_generation_fields=required_fields,
        evidence=(),
        reference_context=(),
    )


class CharacterGenerationV2Workflow:
    """Validate B1A authority before Phase 7, then freeze B1B input and generate.

    The injected model is shared by Search, Selector, Planner, and the V2
    Generator. B1C may add its one separate structural-recovery call; this
    workflow performs no retrieval or fallback to the legacy generation agent.
    The caller must supply the resolved B1A policy separately from the bounded
    SpecInputs provider. After planning, spec freeze receives that same policy;
    no provider, Selector, or Planner output can grant field authority.
    """

    def __init__(
        self,
        *,
        model: AgentModel,
        context_builder: PlanningContextBuilder,
        spec_inputs_provider: SpecInputsProvider,
    ) -> None:
        self._model = model
        self._context_builder = context_builder
        self._spec_inputs_provider = spec_inputs_provider
        self._generator = CharacterGenerationV2Generator(model)

    def generate(
        self,
        request: CharacterDesignRequest,
        *,
        field_authorization_policy: FieldAuthorizationPolicy,
        bounded_canon_evidence: Sequence[BoundedGenerationEvidenceV1] = (),
    ) -> CharacterGenerationV2WorkflowResult:
        """Run V2 with fixed B1A policy and adapter-projected, bounded Canon facts.

        Canon evidence is a separate B1B input: it cannot alter policy, and
        raw Project Canon records never enter this workflow.
        """

        if not isinstance(request, CharacterDesignRequest):
            raise TypeError("request must be a CharacterDesignRequest")
        if not isinstance(field_authorization_policy, FieldAuthorizationPolicy):
            raise TypeError("field_authorization_policy must be a FieldAuthorizationPolicy")
        if isinstance(bounded_canon_evidence, (str, bytes, Mapping)) or not isinstance(
            bounded_canon_evidence, Sequence
        ):
            raise TypeError("bounded_canon_evidence must be a sequence")
        canonical_evidence = tuple(bounded_canon_evidence)
        if any(
            not isinstance(item, BoundedGenerationEvidenceV1)
            for item in canonical_evidence
        ):
            raise TypeError(
                "bounded_canon_evidence must contain BoundedGenerationEvidenceV1 values"
            )

        context = self._context_builder(request)
        if not isinstance(context, CharacterPlanningContextV2):
            raise TypeError("context_builder must return CharacterPlanningContextV2")

        spec_inputs = self._spec_inputs_provider(
            request,
            context,
            field_authorization_policy,
        )
        if not isinstance(spec_inputs, CharacterGenerationV2SpecInputs):
            raise TypeError("spec_inputs_provider must return CharacterGenerationV2SpecInputs")

        unauthorized_required_fields = tuple(
            field_value.value
            for field_value in spec_inputs.required_generation_fields
            if field_authorization_policy.for_field(field_value).state
            is FieldAuthorizationState.UNAUTHORIZED
        )
        if unauthorized_required_fields:
            raise ValueError(
                "SpecInputs requires unauthorized generation field(s): "
                + ", ".join(unauthorized_required_fields)
            )
        if not spec_inputs.required_generation_fields:
            raise ValueError("SpecInputs must require at least one authorized field")

        # INVARIANT: resolve the authority input before any model-derived
        # semantic content exists; the provider receives but cannot replace it.
        planning = run_character_planning_v2_phase7(context, self._model)
        naming_design = planning.planner.plan.naming_design
        if naming_design is None:
            raise RuntimeError("validated Planner result is missing Naming Design v1")

        policy_projection = field_authorization_policy.to_dict()
        policy_projection["field_states"] = {
            field_value.value: authorization.state.value
            for field_value, authorization in field_authorization_policy.field_authorizations.items()
        }
        policy_projection.update(
            {
                "FIELD_AUTHORIZATION_COMPLETE": "YES",
                "FIELD_AUTHORIZATION_DISJOINT": "YES",
                "FIELD_EVIDENCE_BINDING_CONSISTENT": "YES",
            }
        )
        evidence_items = (*spec_inputs.evidence, *canonical_evidence)
        evidence_source_ids = tuple(item.source_id for item in evidence_items)
        evidence_supported_fields = tuple(
            field_value.value
            for item in evidence_items
            for field_value in item.field_values
        )

        spec = freeze_resolved_character_generation_spec(
            request,
            context,
            planning.resolution_result,
            planning.planner,
            selected_seed=planning.selection.selected_seed,
            field_authorization=policy_projection,
            canon_exact_values=spec_inputs.canon_locks,
            evidence_snapshot_id=context.snapshot_id,
            authorized_evidence_source_ids=evidence_source_ids,
            evidence_supported_fields=evidence_supported_fields,
            required_generation_fields=spec_inputs.required_generation_fields,
        )
        finalization_input = build_character_finalization_input(
            spec,
            evidence=(*spec_inputs.evidence, *canonical_evidence),
            reference_context=spec_inputs.reference_context,
        )
        # INVARIANT: the generator receives exactly the authoritative B1B value;
        # it does not receive the request, context, Planner, or retrieval tools.
        parent_invocation = current_invocation_context()
        generator_operation_deadline_seconds = None
        generator_operation_duration_ms = None
        if parent_invocation is None:
            generated = self._generator.generate(finalization_input)
        else:
            generator_operation_deadline_seconds = (
                _V2_GENERATOR_OPERATION_DEADLINE_SECONDS
            )
            generator_deadline = OperationDeadline(
                _V2_GENERATOR_OPERATION_DEADLINE_SECONDS
            )
            with invocation_context(
                deadline=generator_deadline,
                cancellation=parent_invocation.cancellation,
                policy=replace(
                    parent_invocation.policy,
                    operation_deadline_seconds=_V2_GENERATOR_OPERATION_DEADLINE_SECONDS,
                ),
            ):
                # One context covers initial generation and B1C's allowed
                # structural recovery, while retaining the caller's cancellation
                # token and transport attempt policy.
                generated = self._generator.generate(finalization_input)
            generator_operation_duration_ms = generator_deadline.elapsed_ms()
            if generator_deadline.expired():
                deadline_error = ModelDeadlineExceededError(
                    "The V2 Generator operation exceeded its deadline."
                )
                deadline_error.model_invocations = generated.audit.model_invocations
                raise deadline_error

        audit = CharacterGenerationV2WorkflowAudit(
            route_identity=CHARACTER_GENERATION_V2_ROUTE,
            generator_identity=CharacterGenerationV2Generator.__name__,
            request_id=request.request_id,
            planning_context_snapshot_id=context.snapshot_id,
            selected_concept_id=planning.selection.selected_seed.concept_id,
            resolution_id=planning.resolution_result.resolution_id,
            planner_request_id=planning.planner.plan.request_id,
            spec_id=spec.spec_id,
            spec_digest=spec.spec_digest,
            field_authorization_policy=field_authorization_policy,
            planner_diagnostics=planning.planner.diagnostics,
            planning_model_invocations=tuple(
                invocation
                for invocation in (
                    planning.search.diagnostics.model_invocation,
                    planning.selector_selection.diagnostics.model_invocation,
                    planning.planner.diagnostics.model_invocation,
                )
                if isinstance(invocation, ModelInvocationAudit)
            ),
            generator_operation_deadline_seconds=generator_operation_deadline_seconds,
            generator_operation_duration_ms=generator_operation_duration_ms,
        )
        return CharacterGenerationV2WorkflowResult(
            generator_result=generated,
            audit=audit,
            call_accounting=CharacterGenerationCallAccounting(
                concept_search=planning.search.diagnostics.logical_invocation_count,
                selector=planning.selector_selection.diagnostics.logical_invocation_count,
                planner=planning.planner.diagnostics.logical_invocation_count,
                generation=generated.audit.initial_call_count,
                structural_recovery=generated.audit.recovery_call_count,
            ),
            evaluation_design_plan=context.plan_v1,
            naming_design=naming_design,
            # Preserve the evidence that actually crossed B1B. The Application
            # forwards this immutable tuple to CanonChecker; it does not rebuild
            # provenance from model output or the earlier caller request.
            bounded_canon_evidence=finalization_input.evidence,
        )


__all__ = [
    "CharacterGenerationCallAccounting",
    "CharacterGenerationV2SpecInputs",
    "CharacterGenerationV2Workflow",
    "CharacterGenerationV2WorkflowAudit",
    "CharacterGenerationV2WorkflowResult",
    "build_character_generation_v2_spec_inputs",
]
