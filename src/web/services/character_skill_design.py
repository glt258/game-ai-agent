from __future__ import annotations

from dataclasses import dataclass

from agents.character_generation import CharacterDesignRequest, CharacterDraft
from character_intelligence.character_kit import (
    CharacterKit,
    CharacterKitContractError,
    CharacterKitStructuralFinding,
    CharacterKitStructuralValidationResult,
    CharacterKitStructuralValidator,
    placement_metadata,
)
from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentContext,
    evaluate_character_skill_alignment,
)
from character_intelligence.character_skill_design import (
    CharacterSkillDesignInput,
    run_character_skill_design,
)
from character_intelligence.character_skill_projection import (
    CharacterSkillDesignContext,
    build_character_skill_design_context,
)
from character_intelligence.planner import CharacterDesignPlan
from character_intelligence.skill_artifact import (
    CharacterSkillArtifactBinding,
    SkillDesignArtifact,
    build_character_skill_artifact_binding,
    build_skill_design_artifact_from_pipeline_result,
)

from ..errors import WebApplicationError
from ..schemas.character_skill import (
    CharacterKitStructuralFindingDTO,
    CharacterKitStructuralValidationDTO,
    CharacterKitValidationRequestDTO,
    CharacterKitValidationResponseDTO,
    CharacterSkillAlignmentResultDTO,
    CharacterSkillArtifactBindingDTO,
    CharacterSkillContextRequestDTO,
    CharacterSkillContextResponseDTO,
    CharacterSkillContextSummaryDTO,
    CharacterSkillDesignRequestDTO,
    CharacterSkillDesignResponseDTO,
    CharacterSkillMetaDTO,
    CharacterSkillSlotDTO,
    SkillDesignArtifactDTO,
)
from ..schemas.characters import CharacterPlanDTO
from ..schemas.skills import SkillPlaygroundRequestDTO
from .character_generation import CharacterGenerationApplication
from .live_jobs import LiveJobRegistry, LiveJobSnapshot
from .skill_playground import SkillPlaygroundApplication


@dataclass(frozen=True)
class _CharacterInputs:
    request: CharacterDesignRequest
    draft: CharacterDraft
    plan: CharacterDesignPlan | None


class CharacterSkillDesignApplication:
    """Backend adapter that builds Character context and reuses Skill execution."""

    def __init__(
        self,
        *,
        skill_playground: SkillPlaygroundApplication,
    ) -> None:
        self.skill_playground = skill_playground

    @staticmethod
    def _character_inputs(payload: CharacterSkillContextRequestDTO) -> _CharacterInputs:
        request = CharacterGenerationApplication.to_domain_request(payload.request)
        draft = CharacterDraft.from_mapping(payload.draft.model_dump())
        plan = (
            CharacterDesignPlan.from_mapping(payload.plan.model_dump())
            if isinstance(payload.plan, CharacterPlanDTO)
            else None
        )
        return _CharacterInputs(request, draft, plan)

    @classmethod
    def to_context(
        cls,
        payload: CharacterSkillContextRequestDTO,
    ) -> CharacterSkillDesignContext:
        inputs = cls._character_inputs(payload)
        return build_character_skill_design_context(
            inputs.request,
            inputs.draft,
            inputs.plan,
        )

    @staticmethod
    def _summary(context: CharacterSkillDesignContext) -> CharacterSkillContextSummaryDTO:
        return CharacterSkillContextSummaryDTO(
            character_name=context.character_name,
            combat_role_profile=context.combat_role_profile.to_dict(),
            ability_concept=context.ability_concept,
            design_pitch=context.design_pitch,
            skill_relevant_hard_constraints=list(context.skill_relevant_hard_constraints),
            skill_relevant_forbidden_elements=list(context.skill_relevant_forbidden_elements),
            relevant_desired_connections=list(context.relevant_desired_connections),
            affiliation_context=(
                context.affiliation_context.to_dict()
                if context.affiliation_context is not None
                else None
            ),
            projection_version=context.projection_version,
        )

    def context(
        self,
        payload: CharacterSkillContextRequestDTO,
    ) -> CharacterSkillContextResponseDTO:
        try:
            context = self.to_context(payload)
            return CharacterSkillContextResponseDTO(
                schema_version="web-character-skill-context/0.1",
                source_context_fingerprint=context.source_context_fingerprint,
                character_context_summary=self._summary(context),
            )
        except WebApplicationError:
            raise
        except Exception as error:
            raise WebApplicationError(
                "CHARACTER_SKILL_CONTEXT_INVALID",
                "The Character context could not be projected for Skill design.",
                status_code=422,
                stage="character_skill_context",
                retryable=False,
            ) from error

    @staticmethod
    def meta() -> CharacterSkillMetaDTO:
        return CharacterSkillMetaDTO(
            schema_version="web-character-skill-meta/0.1",
            slots=[CharacterSkillSlotDTO(**item) for item in placement_metadata()],
        )

    @staticmethod
    def validate_kit(
        payload: CharacterKitValidationRequestDTO,
    ) -> CharacterKitValidationResponseDTO:
        try:
            kit = CharacterKit.from_mapping(payload.kit)
            result = CharacterKitStructuralValidator().validate(kit)
            kit_digest = kit.kit_digest
        except CharacterKitContractError as error:
            result = CharacterSkillDesignApplication._kit_error_result(error)
            raw_digest = payload.kit.get("kit_digest")
            kit_digest = raw_digest if isinstance(raw_digest, str) else "0" * 64
            contract_version = payload.kit.get("contract_version")
            contract_version = contract_version if isinstance(contract_version, str) else "unknown"
            associations = payload.kit.get("associations")
            associations = associations if isinstance(associations, list) else []
        else:
            contract_version = kit.contract_version
            associations = [item.to_mapping() for item in kit.associations]
        return CharacterKitValidationResponseDTO(
            schema_version="web-character-kit-validation/0.1",
            contract_version=contract_version,
            associations=associations,
            structural_validation=CharacterKitStructuralValidationDTO(
                status=result.status,
                blocking=result.blocking,
                findings=[
                    CharacterKitStructuralFindingDTO(**item.to_mapping())
                    for item in result.findings
                ],
            ),
            kit_digest=kit_digest,
        )

    @staticmethod
    def _kit_error_result(
        error: CharacterKitContractError,
    ) -> CharacterKitStructuralValidationResult:
        return CharacterKitStructuralValidationResult(
            "FAIL",
            True,
            (CharacterKitStructuralFinding(error.code, "/kit", str(error)),),
        )

    def design(
        self,
        payload: CharacterSkillDesignRequestDTO,
    ) -> CharacterSkillDesignResponseDTO:
        try:
            context = self.to_context(payload.character)
            skill_input = self._skill_input(payload.skill)
            provider = self.skill_playground.provider_for(payload.skill)
            execution = run_character_skill_design(
                provider,
                context,
                skill_input,
                repo_root=self.skill_playground.repo_root,
            )
            provider_mode = self.skill_playground._provider_mode(payload.skill)
            artifact: SkillDesignArtifact | None = None
            binding: CharacterSkillArtifactBinding | None = None
            artifact_digest = (
                execution.pipeline_result.candidate.digest
                if execution.pipeline_result.candidate is not None
                else execution.pipeline_result.evidence.candidate_digest
            )
            alignment = evaluate_character_skill_alignment(
                CharacterSkillAlignmentContext(
                    character_context=context,
                    skill_family=skill_input.family,
                    skill_mode=skill_input.mode,
                    candidate=execution.pipeline_result.candidate,
                    skill_evaluation=execution.pipeline_result.report,
                    artifact_digest=artifact_digest,
                    source_context_fingerprint=context.source_context_fingerprint,
                )
            )
            if (
                execution.pipeline_result.candidate is not None
                and execution.pipeline_result.report is not None
                and execution.pipeline_result.validated_ir is not None
                and execution.pipeline_result.compiler_provenance is not None
            ):
                artifact = build_skill_design_artifact_from_pipeline_result(
                    execution.pipeline_result,
                    alignment=alignment,
                    character_context=context,
                )
                binding = build_character_skill_artifact_binding(artifact, context, alignment)
            skill_response = self.skill_playground.response_from_result(
                payload.skill,
                execution.pipeline_result,
                provider,
                provider_mode,
                artifact=artifact,
            )
            artifact_digest = (
                artifact.artifact_digest
                if artifact is not None
                else skill_response.evaluation.candidate_digest
            )
            return CharacterSkillDesignResponseDTO(
                schema_version="web-character-skill-design/0.1",
                status=skill_response.status,
                source_context_fingerprint=context.source_context_fingerprint,
                character_context_summary=self._summary(context),
                skill_input=skill_response.input,
                semantic_ir=skill_response.semantic_ir,
                skillkit=skill_response.skillkit,
                evaluation=skill_response.evaluation,
                alignment=CharacterSkillAlignmentResultDTO.model_validate(alignment.to_mapping()),
                pipeline=skill_response.pipeline,
                artifact_digest=artifact_digest,
                freshness="current",
                provider=skill_response.provider,
                evidence=skill_response.evidence,
                artifact_versions=skill_response.artifact_versions,
                artifact_compatibility=skill_response.artifact_compatibility,
                artifact=(
                    SkillDesignArtifactDTO.model_validate(artifact.to_mapping())
                    if artifact is not None
                    else None
                ),
                binding=(
                    CharacterSkillArtifactBindingDTO.model_validate(binding.to_mapping())
                    if binding is not None
                    else None
                ),
            )
        except WebApplicationError:
            raise
        except Exception as error:
            raise WebApplicationError(
                "CHARACTER_SKILL_DESIGN_UNAVAILABLE",
                "The Character Skill Design provider could not complete the request.",
                status_code=503,
                stage="character_skill_design",
                retryable=True,
            ) from error

    def submit_live_job(
        self,
        payload: CharacterSkillDesignRequestDTO,
        registry: LiveJobRegistry,
    ) -> LiveJobSnapshot:
        if payload.skill.execution_mode != "live":
            raise WebApplicationError(
                "LIVE_EXECUTION_MODE_REQUIRED",
                "Live jobs require execution_mode=live.",
                status_code=422,
                stage="live_execution",
                retryable=False,
            )
        return registry.submit(
            kind="character_skill_design",
            provider=payload.skill.provider,
            model=payload.skill.model,
            work=lambda: self.design(payload),
        )

    @staticmethod
    def _skill_input(payload: SkillPlaygroundRequestDTO) -> CharacterSkillDesignInput:
        return CharacterSkillDesignInput(
            family=payload.family,
            mode=payload.mode,
            brief=payload.brief,
            constraints=tuple(payload.constraints),
            language=payload.language,
            model=payload.model,
            preset_id=payload.preset_id,
        )


__all__ = ["CharacterSkillDesignApplication"]
