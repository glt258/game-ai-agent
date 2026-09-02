from __future__ import annotations

from dataclasses import dataclass

from character_intelligence.character_kit import (
    CharacterKit,
    CharacterKitContractError,
    CharacterKitStructuralValidator,
    build_character_kit_from_association_mappings,
)
from character_intelligence.character_kit_evaluation import (
    CharacterKitEvaluationContext,
    evaluate_character_kit_role_coverage,
)
from combat_semantics import CombatRoleProfile

from ..errors import WebApplicationError
from ..schemas.character_skill import (
    CharacterKitCoverageDTO,
    CharacterKitEvaluationFindingDTO,
    CharacterKitEvaluationKitDTO,
    CharacterKitRoleCoverageDTO,
    CharacterKitRoleCoverageEvidenceDTO,
    CharacterKitRoleCoverageItemDTO,
    CharacterKitRoleCoverageRequestDTO,
    CharacterKitRoleCoverageResponseDTO,
    CharacterKitStructuralFindingDTO,
    CharacterKitStructuralValidationDTO,
)


@dataclass(frozen=True)
class CharacterKitRoleCoverageApplication:
    """Thin Web adapter for the provider-free Kit role coverage module."""

    @staticmethod
    def evaluate(
        payload: CharacterKitRoleCoverageRequestDTO,
    ) -> CharacterKitRoleCoverageResponseDTO:
        try:
            kit = _build_kit(payload.kit)
            profile = CombatRoleProfile(
                primary_role=payload.combat_role_profile.primary_role,
                secondary_roles=tuple(payload.combat_role_profile.secondary_roles),
            )
            context = CharacterKitEvaluationContext(combat_role_profile=profile)
            structural = CharacterKitStructuralValidator().validate(kit)
            result = evaluate_character_kit_role_coverage(
                kit,
                context,
                current_skill_context_fingerprint=payload.current_skill_context_fingerprint,
            )
            return CharacterKitRoleCoverageResponseDTO(
                schema_version="web-character-kit-role-coverage/0.1",
                contract_version=kit.contract_version,
                kit_digest=kit.kit_digest,
                structural_validation=CharacterKitStructuralValidationDTO(
                    status=structural.status,
                    blocking=structural.blocking,
                    findings=[
                        CharacterKitStructuralFindingDTO(**item.to_mapping())
                        for item in structural.findings
                    ],
                ),
                role_coverage=CharacterKitRoleCoverageDTO(
                    status=result.status,
                    kit_digest=result.kit_digest,
                    evaluation_context_fingerprint=result.evaluation_context_fingerprint,
                    evaluator_version=result.evaluator_version,
                    coverage=CharacterKitCoverageDTO(
                        primary=CharacterKitRoleCoverageItemDTO(
                            role=result.coverage.primary.role,
                            supported=result.coverage.primary.supported,
                            evidence=[
                                CharacterKitRoleCoverageEvidenceDTO(**item.to_mapping())
                                for item in result.coverage.primary.evidence
                            ],
                        ),
                        secondary=[
                            CharacterKitRoleCoverageItemDTO(
                                role=item.role,
                                supported=item.supported,
                                evidence=[
                                    CharacterKitRoleCoverageEvidenceDTO(**evidence.to_mapping())
                                    for evidence in item.evidence
                                ],
                            )
                            for item in result.coverage.secondary
                        ],
                        observed_roles=list(result.coverage.observed_roles),
                    ),
                    findings=[
                        CharacterKitEvaluationFindingDTO(
                            **{
                                **item.to_mapping(),
                                "artifact_evidence": [
                                    evidence.to_mapping() for evidence in item.artifact_evidence
                                ],
                            }
                        )
                        for item in result.findings
                    ],
                    report_digest=result.report_digest,
                    blocking=result.blocking,
                    summary=result.summary,
                ),
            )
        except WebApplicationError:
            raise
        except (CharacterKitContractError, TypeError, ValueError) as error:
            raise WebApplicationError(
                "CHARACTER_KIT_ROLE_COVERAGE_INVALID",
                "The CharacterKit role coverage request could not be evaluated.",
                status_code=422,
                stage="character_kit_role_coverage",
                retryable=False,
            ) from error


__all__ = ["CharacterKitRoleCoverageApplication"]


def _build_kit(payload: CharacterKitEvaluationKitDTO) -> CharacterKit:
    if payload.kit_digest is not None:
        return CharacterKit.from_mapping(payload.model_dump())
    return build_character_kit_from_association_mappings(
        [item.model_dump() for item in payload.associations],
        contract_version=payload.contract_version,
        placement_schema_version=payload.placement_schema_version,
    )
