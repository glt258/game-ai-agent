from __future__ import annotations

from typing import Any

from agents.canon_checker import CanonCheckReport, CanonCheckStatus
from agents.character_generation import CharacterDraft
from agents.evaluation.models import EvaluationOutcome, EvaluationResult
from agents.models import (
    ModelInvocationAudit,
    ModelUsage,
    summarize_model_usage,
)

from ..errors import WebApplicationError
from ..schemas.characters import (
    CanonBasisDTO,
    CharacterAffiliationContextDTO,
    CharacterDraftDTO,
    CharacterGenerationRequestDTO,
    CharacterGenerationResponseDTO,
    CharacterIntentDTO,
    CharacterPlanDTO,
    CombatDTO,
    CombatRoleProfileDTO,
    ContractRecoveryDTO,
    GenerationAuditDTO,
    PipelineStepDTO,
    RawCharacterResultDTO,
    RepairDTO,
)
from ..schemas.common import (
    ErrorAuditDTO,
    ErrorBodyDTO,
    ErrorResponseDTO,
    ModelAttemptDTO,
    ModelInvocationDTO,
    ModelUsageDTO,
    ModelUsageSummaryDTO,
    ValidatorResultDTO,
)
from ..schemas.validation import (
    CanonValidationDTO,
    CanonValidationSummaryDTO,
    CharacterValidationResponseDTO,
    ValidationSummaryDTO,
)
from ..services.character_generation_v2_production import (
    CharacterGenerationApplicationResult,
)
from ..services.character_validation import CharacterValidationApplicationResult


def _usage(value: ModelUsage | None) -> ModelUsageDTO | None:
    if value is None:
        return None
    return ModelUsageDTO(
        input_tokens=value.input_tokens,
        output_tokens=value.output_tokens,
        total_tokens=value.total_tokens,
    )


def to_model_invocation(value: ModelInvocationAudit) -> ModelInvocationDTO:
    return ModelInvocationDTO(
        provider=value.provider,
        model=value.model,
        turn_number=value.turn_number,
        outcome=value.outcome,
        latency_ms=value.latency_ms,
        retry_count=value.retry_count,
        finish_reason=value.finish_reason,
        tool_call_count=value.tool_call_count,
        usage=_usage(value.usage),
        purpose=value.purpose,
        provider_status_code=value.provider_status_code,
        provider_retryable=value.provider_retryable,
        provider_request_id=value.provider_request_id,
        upstream_status=value.upstream_status,
        upstream_error_type=value.upstream_error_type,
        upstream_error_code=value.upstream_error_code,
        upstream_error_param=value.upstream_error_param,
        logical_invocation_index=value.logical_invocation_index,
        started_offset_ms=value.started_offset_ms,
        completed_offset_ms=value.completed_offset_ms,
        remaining_budget_at_start_ms=value.remaining_budget_at_start_ms,
        attempts_started=value.attempts_started,
        attempts_completed=value.attempts_completed,
        attempts=[
            ModelAttemptDTO(
                attempt_number=item.attempt_number,
                outcome=item.outcome,
                latency_ms=item.latency_ms,
                error_code=item.error_code,
                provider_request_id=item.provider_request_id,
                finish_reason=item.finish_reason,
                usage=_usage(item.usage),
                logical_invocation_index=item.logical_invocation_index,
                provider_attempt_index=item.provider_attempt_index,
                started_offset_ms=item.started_offset_ms,
                completed_offset_ms=item.completed_offset_ms,
                remaining_budget_at_start_ms=item.remaining_budget_at_start_ms,
                effective_attempt_timeout_ms=item.effective_attempt_timeout_ms,
                retry_reason=item.retry_reason,
            )
            for item in value.attempts
        ],
    )


def to_usage_summary(values: tuple[ModelInvocationAudit, ...]) -> ModelUsageSummaryDTO:
    summary = summarize_model_usage(values)
    return ModelUsageSummaryDTO(
        invocation_count=summary.invocation_count,
        reported_usage_count=summary.reported_usage_count,
        known_input_tokens=summary.known_input_tokens,
        known_output_tokens=summary.known_output_tokens,
        known_total_tokens=summary.known_total_tokens,
        complete=summary.complete,
    )


def _draft(value: CharacterDraft) -> CharacterDraftDTO:
    return CharacterDraftDTO.model_validate(value.to_dict())


def _plan(value: Any) -> CharacterPlanDTO | None:
    if value is None:
        return None
    payload = value.to_dict()
    intent_payload = dict(payload["parsed_intent"])
    # Keep the established public V1 plan DTO stable; V2's typed constraints
    # remain in the audit's raw plan projection and the generated draft.
    intent_payload.pop("gender_requirement", None)
    intent_payload.pop("age_requirement", None)
    return CharacterPlanDTO(
        parsed_intent=CharacterIntentDTO.model_validate(intent_payload),
        combat_role_profile=payload["combat_role_profile"],
        generation_constraints=payload["generation_constraints"],
        recommended_traits=payload["recommended_traits"],
        expected_affiliation_id=payload.get("expected_affiliation_id"),
        affiliation_context=(
            CharacterAffiliationContextDTO.model_validate(payload["affiliation_context"])
            if payload.get("affiliation_context") is not None
            else None
        ),
    )


def _canon_basis(value: CharacterDraft) -> list[CanonBasisDTO]:
    return [CanonBasisDTO.model_validate(item.to_dict()) for item in value.canon_basis]


def _status(value: str) -> str:
    return {"pass": "passed", "warn": "warning", "fail": "failed"}.get(value, "not_available")


def _canon_validators(report: CanonCheckReport) -> list[ValidatorResultDTO]:
    if not report.findings:
        return [
            ValidatorResultDTO(
                name="canon_checker",
                status=_status(report.status.value),
                message="CanonChecker returned a clean report.",
            )
        ]
    return [
        ValidatorResultDTO(
            name="canon_checker",
            status=_status(report.status.value),
            code=finding.code.value,
            severity=finding.severity.value,
            blocking=finding.severity.value == "error",
            field_path=finding.field_path,
            message=finding.message,
            evidence_ids=list(finding.evidence_ids),
        )
        for finding in report.findings
    ]


def _evaluation_validators(result: EvaluationResult) -> list[ValidatorResultDTO]:
    if not result.findings:
        return [
            ValidatorResultDTO(
                name="evaluation_runner",
                status=_evaluation_status(result.outcome),
                message="EvaluationRunner returned no findings.",
            )
        ]
    return [
        ValidatorResultDTO(
            name=finding.validator_id,
            status=(
                "failed"
                if finding.blocking or finding.severity.casefold() == "error"
                else "warning"
            ),
            code=finding.code,
            severity=finding.severity,
            blocking=finding.blocking,
            field_path=finding.field_path,
            message=finding.message,
        )
        for finding in result.findings
    ]


def _evaluation_status(outcome: EvaluationOutcome) -> str:
    return {
        EvaluationOutcome.PASS: "passed",
        EvaluationOutcome.WARN: "warning",
        EvaluationOutcome.FAIL: "failed",
    }.get(outcome, "not_available")


def _repair(result: CharacterGenerationApplicationResult) -> RepairDTO:
    repair = result.authoring.repair_result
    return RepairDTO(
        repair_performed=repair.repair_attempted,
        repair_attempts=repair.repair_attempt,
        status=repair.status.value,
        repair_succeeded=repair.repair_succeeded,
        changed_fields=list(repair.changed_fields),
        initial_status=repair.initial_check.status.value,
        final_status=repair.final_check.status.value,
        failure_code=None if repair.repair_succeeded else repair.status.value,
    )


def _pipeline(result: CharacterGenerationApplicationResult) -> list[PipelineStepDTO]:
    accounting = result.call_accounting
    repair = result.authoring.repair_result
    canon = result.authoring.final_check.status
    evaluation = result.evaluation.outcome
    repair_status = (
        "skipped"
        if not repair.repair_attempted
        else "repaired"
        if repair.repair_succeeded
        else "failed"
    )
    return [
        PipelineStepDTO(
            id="concept_search",
            label="Concept Search",
            status="passed",
            detail=f"{accounting.concept_search if accounting else 0} bounded search call(s).",
        ),
        PipelineStepDTO(
            id="concept_selector",
            label="Concept Selector",
            status="passed",
            detail=f"{accounting.selector if accounting else 0} selection call(s).",
        ),
        PipelineStepDTO(
            id="planner",
            label="Planner",
            status="passed",
            detail=f"{accounting.planner if accounting else 0} planning call(s).",
        ),
        PipelineStepDTO(
            id="naming",
            label="Naming Design",
            status="passed",
            detail=(
                f"{result.naming_design.owner.value} owns the frozen name."
                if result.naming_design is not None
                else "Planner naming design was unavailable."
            ),
        ),
        PipelineStepDTO(
            id="spec_freeze",
            label="Frozen Generation Spec",
            status="passed",
            detail=(
                f"Spec {result.workflow_audit.spec_id} was frozen before generation."
                if result.workflow_audit is not None
                else "V2 generation spec was frozen before generation."
            ),
        ),
        PipelineStepDTO(
            id="generation",
            label="V2 Generator",
            status="passed",
            detail="The shared V2 Generator returned a validated CharacterDraft.",
        ),
        PipelineStepDTO(
            id="evaluation",
            label="Evaluation",
            status="failed" if evaluation == EvaluationOutcome.FAIL else "passed",
            detail=f"Evaluation outcome: {evaluation.value}.",
        ),
        PipelineStepDTO(
            id="canon",
            label="Canon Check",
            status="failed" if canon == CanonCheckStatus.FAIL else "passed",
            detail=f"CanonChecker status: {canon.value}.",
        ),
        PipelineStepDTO(
            id="repair",
            label="Repair",
            status=repair_status,
            detail=f"Repair status: {repair.status.value}.",
        ),
        PipelineStepDTO(
            id="final",
            label="Final Candidate",
            status=(
                "failed"
                if result.authoring.final_status == CanonCheckStatus.FAIL
                or evaluation == EvaluationOutcome.FAIL
                else "passed"
            ),
            detail=f"Final authoring status: {result.authoring.final_status.value}.",
        ),
    ]


def _to_character_generation_response(
    payload: CharacterGenerationRequestDTO,
    result: CharacterGenerationApplicationResult,
) -> CharacterGenerationResponseDTO:
    draft = result.authoring.final_draft
    draft_dto = _draft(draft)
    repair = _repair(result)
    output_audit = result.generator_result.audit.draft_output_audit
    output_inspection = result.generator_result.audit.draft_output_inspection
    recovery_status = "not_attempted"
    if output_audit is not None and output_audit.recovery_requested:
        recovery_status = (
            "recovered"
            if output_audit.merge_status.value == "APPLIED"
            else "failed"
        )
    generation_audit = GenerationAuditDTO(
        request_id=result.request.request_id,
        tool_rounds=0,
        tool_calls=[],
        source_ids=[],
        reference_ids=[],
        normalized_fields=list(
            output_inspection.normalized_fields if output_inspection is not None else ()
        ),
        contract_recovery=ContractRecoveryDTO(
            status=recovery_status,
            attempted=bool(output_audit and output_audit.recovery_requested),
            missing_required=list(output_audit.requested_fields if output_audit else ()),
            unknown_fields=list(output_inspection.unknown_fields if output_inspection else ()),
            invalid_fields=(
                [output_inspection.failure_reason.value]
                if output_inspection is not None and output_inspection.failure_reason is not None
                else []
            ),
            recovered_fields=list(output_audit.returned_fields if output_audit else ()),
            discarded_unknown_fields=[],
        ),
    )
    canon_basis = _canon_basis(draft)
    validators = [
        ValidatorResultDTO(
            name="generation_runtime",
            status="passed",
            message="The V2 Generator returned a draft under the frozen Spec.",
        ),
        *_evaluation_validators(result.evaluation),
        *_canon_validators(result.authoring.final_check),
    ]
    authoring_audit = {
        "initial_check": result.authoring.initial_check.to_dict(),
        "final_check": result.authoring.final_check.to_dict(),
        "repair": repair.model_dump(),
    }
    workflow = result.workflow_audit
    safe_generation_audit = {
        "route": result.route.value,
        "status": result.generator_result.status.value,
        "initial_call_count": result.generator_result.audit.initial_call_count,
        "recovery_call_count": result.generator_result.audit.recovery_call_count,
        "naming_enforcement": result.generator_result.audit.naming_enforcement,
        "planning_model_invocation_count": (
            len(workflow.planning_model_invocations) if workflow is not None else 0
        ),
        "spec_id": workflow.spec_id if workflow is not None else None,
        "spec_digest": workflow.spec_digest if workflow is not None else None,
        "selected_concept_id": workflow.selected_concept_id if workflow is not None else None,
        "call_accounting": (
            result.call_accounting.__dict__ if result.call_accounting is not None else {}
        ),
    }
    return CharacterGenerationResponseDTO(
        schema_version="web-character-generation/0.1",
        status="completed",
        request=payload,
        draft=draft_dto,
        plan=_plan(result.design_plan),
        combat=CombatDTO(
            combat_role_profile=CombatRoleProfileDTO.model_validate(
                draft.combat_role_profile.to_dict()
            ),
            skill_shadow_available=False,
            skill_shadow_status="not_available",
        ),
        canon_basis=canon_basis,
        validators=validators,
        repair=repair,
        model_invocations=[to_model_invocation(item) for item in result.model_invocations],
        usage_summary=to_usage_summary(tuple(result.model_invocations)),
        pipeline=_pipeline(result),
        audit=generation_audit,
        raw_data=RawCharacterResultDTO(
            draft=draft.to_dict(),
            plan=result.design_plan.to_dict(),
            generation_audit=safe_generation_audit,
            authoring_audit=authoring_audit,
        ),
    )


def to_character_generation_response(
    payload: CharacterGenerationRequestDTO,
    result: CharacterGenerationApplicationResult,
) -> CharacterGenerationResponseDTO:
    return _to_character_generation_response(payload, result)


def to_error_response(error: WebApplicationError) -> ErrorResponseDTO:
    audit = None
    if error.model_invocations:
        audit = ErrorAuditDTO(
            stage=error.stage,
            model_invocations=[to_model_invocation(item) for item in error.model_invocations],
        )
    return ErrorResponseDTO(
        error=ErrorBodyDTO(
            code=error.code,
            message=error.message,
            stage=error.stage,
            retryable=error.retryable,
            context_failure_reason=error.context_failure_reason,
            details=error.details,
            audit=audit,
        )
    )


def _validation_pipeline(result: CharacterValidationApplicationResult) -> list[PipelineStepDTO]:
    evaluation = result.evaluation.outcome
    canon = result.canon.status
    status = (
        "failed"
        if evaluation == EvaluationOutcome.FAIL or canon == CanonCheckStatus.FAIL
        else "passed"
    )
    return [
        PipelineStepDTO(
            id="input",
            label="Edited Draft Input",
            status="passed",
            detail="Draft parsed through the domain CharacterDraft contract.",
        ),
        PipelineStepDTO(
            id="evaluation",
            label="Evaluation",
            status="failed" if evaluation == EvaluationOutcome.FAIL else "passed",
            detail=f"Evaluation outcome: {evaluation.value}.",
        ),
        PipelineStepDTO(
            id="canon",
            label="Canon Check",
            status="failed" if canon == CanonCheckStatus.FAIL else "passed",
            detail=f"CanonChecker status: {canon.value}.",
        ),
        PipelineStepDTO(
            id="final",
            label="Validation Result",
            status=status,
            detail=f"Edited draft validation status: {status}.",
        ),
    ]


def to_character_validation_response(
    result: CharacterValidationApplicationResult,
) -> CharacterValidationResponseDTO:
    canon_findings = _canon_validators(result.canon)
    validators = [*_evaluation_validators(result.evaluation), *canon_findings]
    status = "failed" if any(item.status == "failed" for item in validators) else "passed"
    return CharacterValidationResponseDTO(
        schema_version="web-character-validation/0.1",
        status=status,
        request_id=result.request.request_id,
        draft_id=result.draft.draft_id,
        validators=validators,
        canon=CanonValidationDTO(
            status=_status(result.canon.status.value),
            checked_source_ids=list(result.canon.checked_source_ids),
            summary=CanonValidationSummaryDTO(
                errors=result.canon.summary.errors,
                warnings=result.canon.summary.warnings,
                infos=result.canon.summary.infos,
            ),
            findings=canon_findings,
        ),
        combat=CombatRoleProfileDTO.model_validate(result.draft.combat_role_profile.to_dict()),
        pipeline=_validation_pipeline(result),
        summary=ValidationSummaryDTO(
            status=status,
            blocking=result.evaluation.blocking or result.canon.status == CanonCheckStatus.FAIL,
            validator_count=len(validators),
            failed_count=sum(item.status == "failed" for item in validators),
            warning_count=sum(item.status == "warning" for item in validators),
        ),
    )


__all__ = [
    "to_character_generation_response",
    "to_character_validation_response",
    "to_error_response",
    "to_model_invocation",
]
