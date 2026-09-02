from __future__ import annotations

from typing import Any

from agents.canon_checker import CanonCheckReport, CanonCheckStatus
from agents.character_generation import CharacterDraft
from agents.evaluation.models import EvaluationOutcome, EvaluationResult
from agents.models import ModelInvocationAudit, ModelUsage

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
    ToolAuditDTO,
)
from ..schemas.common import (
    ErrorAuditDTO,
    ErrorBodyDTO,
    ErrorResponseDTO,
    ModelInvocationDTO,
    ModelUsageDTO,
    ValidatorResultDTO,
)
from ..schemas.validation import (
    CanonValidationDTO,
    CanonValidationSummaryDTO,
    CharacterValidationResponseDTO,
    ValidationSummaryDTO,
)
from ..services.character_generation import CharacterGenerationApplicationResult
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
    )


def _draft(value: CharacterDraft) -> CharacterDraftDTO:
    return CharacterDraftDTO.model_validate(value.to_dict())


def _plan(value: Any) -> CharacterPlanDTO | None:
    if value is None:
        return None
    payload = value.to_dict()
    return CharacterPlanDTO(
        parsed_intent=CharacterIntentDTO.model_validate(payload["parsed_intent"]),
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


def _tool_audit(value: Any) -> ToolAuditDTO:
    return ToolAuditDTO(
        round=value.round,
        tool_name=value.tool_name,
        result_status=value.result_status,
        source_ids=list(value.allowed_lore_ids),
        denied_requested_ids=list(value.denied_requested_ids),
        resolver_reason_code=value.resolver_reason_code,
    )


def _audit(result: CharacterGenerationApplicationResult) -> GenerationAuditDTO:
    source = result.generation.audit
    recovery = source.contract_recovery
    return GenerationAuditDTO(
        request_id=source.request_id,
        tool_rounds=source.tool_rounds,
        tool_calls=[_tool_audit(item) for item in source.tool_calls],
        source_ids=list(source.source_ids),
        reference_ids=list(source.reference_ids),
        normalized_fields=list(source.normalized_fields),
        contract_recovery=ContractRecoveryDTO(
            status=recovery.status,
            attempted=recovery.attempted,
            missing_required=list(recovery.missing_required),
            unknown_fields=list(recovery.unknown_fields),
            invalid_fields=list(recovery.invalid_fields),
            recovered_fields=list(recovery.recovered_fields),
            discarded_unknown_fields=list(recovery.discarded_unknown_fields),
        ),
    )


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
        failure_code=(None if repair.repair_succeeded else repair.status.value),
    )


def _pipeline(result: CharacterGenerationApplicationResult) -> list[PipelineStepDTO]:
    generation = result.generation
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
            id="intent",
            label="Intent / Plan",
            status="passed" if generation.design_plan is not None else "skipped",
            detail=(
                "CharacterDesignPlan produced."
                if generation.design_plan is not None
                else "Intent layer was not enabled."
            ),
        ),
        PipelineStepDTO(
            id="retrieval",
            label="Canon Retrieval",
            status="passed" if generation.audit.tool_rounds > 0 else "skipped",
            detail=f"{generation.audit.tool_rounds} bounded tool round(s).",
        ),
        PipelineStepDTO(
            id="generation",
            label="Generation",
            status="passed",
            detail="CharacterDraft returned by the existing runtime.",
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
            status="failed" if result.authoring.final_status == CanonCheckStatus.FAIL else "passed",
            detail=f"Final authoring status: {result.authoring.final_status.value}.",
        ),
    ]


def _combat(result: CharacterGenerationApplicationResult) -> CombatDTO:
    profile = result.generation.draft.combat_role_profile.to_dict()
    shadow = result.generation.skill_shadow
    if shadow is None:
        return CombatDTO(
            combat_role_profile=profile,
            skill_shadow_available=False,
            skill_shadow_status="not_available",
        )
    report = shadow.validation_report
    return CombatDTO(
        combat_role_profile=profile,
        skill_shadow_available=True,
        skill_shadow_status="passed" if shadow.response_compliant else "failed",
        skill_summary=shadow.rendered_ability_concept,
        skill_evaluation=report.to_dict() if report is not None else None,
    )


def to_character_generation_response(
    payload: CharacterGenerationRequestDTO,
    result: CharacterGenerationApplicationResult,
) -> CharacterGenerationResponseDTO:
    draft = _draft(result.authoring.final_draft)
    plan = _plan(result.generation.design_plan)
    audit = _audit(result)
    generation_invocations = list(result.generation.audit.model_invocations)
    repair_invocations = list(result.authoring.repair_result.model_audit)
    invocations = [
        to_model_invocation(item) for item in (*generation_invocations, *repair_invocations)
    ]
    validators = [
        ValidatorResultDTO(
            name="generation_runtime",
            status="passed",
            message="CharacterGenerationAgent returned a validated CharacterDraft.",
        ),
        *_evaluation_validators(result.evaluation),
        *_canon_validators(result.authoring.final_check),
    ]
    authoring_audit = {
        "initial_check": result.authoring.initial_check.to_dict(),
        "final_check": result.authoring.final_check.to_dict(),
        "repair": _repair(result).model_dump(),
    }
    raw = RawCharacterResultDTO(
        draft=result.authoring.final_draft.to_dict(),
        plan=result.generation.design_plan.to_dict()
        if result.generation.design_plan is not None
        else None,
        generation_audit=audit.model_dump(),
        authoring_audit=authoring_audit,
    )
    return CharacterGenerationResponseDTO(
        schema_version="web-character-generation/0.1",
        status="completed",
        request=payload,
        draft=draft,
        plan=plan,
        combat=_combat(result),
        canon_basis=[CanonBasisDTO.model_validate(item) for item in draft.canon_basis],
        validators=validators,
        repair=_repair(result),
        model_invocations=invocations,
        pipeline=_pipeline(result),
        audit=audit,
        raw_data=raw,
    )


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
