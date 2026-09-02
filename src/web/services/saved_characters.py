from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.character_generation import CharacterDraft
from character_intelligence.character_kit import CharacterKit
from character_intelligence.character_skill_association import CharacterSkillAssociation
from character_intelligence.character_skill_projection import build_character_skill_design_context
from character_intelligence.planner import CharacterDesignPlan
from character_intelligence.skill_artifact import CharacterSkillArtifactBinding, SkillDesignArtifact
from persistence import (
    CharacterRevisionConflictError,
    CharacterSkillPersistenceConflictError,
    CharacterSkillPersistenceService,
    PersistenceUnitOfWork,
    SavedCharacterSummary,
)
from persistence.character_skill_persistence import _alignment_from_mapping

from ..schemas.character_skill import CharacterSkillAssociationDTO
from ..schemas.characters import CharacterGenerationRequestDTO, CharacterPlanDTO
from ..schemas.saved_characters import (
    SavedCharacterAssociationDTO,
    SavedCharacterDerivedStateDTO,
    SavedCharacterDTO,
    SavedCharacterHistorySummaryDTO,
    SavedCharacterListResponseDTO,
    SavedCharacterRevisionDTO,
    SavedCharacterSaveRequestDTO,
    SavedCharacterSaveResponseDTO,
    SavedCharacterSummaryDTO,
)
from .character_generation import CharacterGenerationApplication


@dataclass(frozen=True)
class _RequestedAssociation:
    transport_id: str
    association: CharacterSkillAssociation


class StudioSaveService:
    """Deep application seam for explicit, atomic Character workspace saves."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def list(self) -> SavedCharacterListResponseDTO:
        with PersistenceUnitOfWork(self.database_path) as unit:
            summaries = unit.characters.list_summaries()
        return SavedCharacterListResponseDTO(
            schema_version="web-saved-character-list/0.1",
            characters=[_summary(item) for item in summaries],
            total=len(summaries),
        )

    def open(self, character_id: str) -> SavedCharacterDTO:
        with PersistenceUnitOfWork(self.database_path) as unit:
            return self._open(unit, character_id)

    def create(self, payload: SavedCharacterSaveRequestDTO) -> SavedCharacterSaveResponseDTO:
        draft, request, plan, requested = _domain_inputs(payload)
        with PersistenceUnitOfWork(self.database_path) as unit:
            character = unit.characters.create(draft)
            context = build_character_skill_design_context(request, draft, plan)
            _persist_associations(
                unit,
                character.character_id,
                character.current_revision_id,
                None,
                context,
                requested,
            )
            unit.workspace.save(
                character.character_id,
                payload.request.model_dump(mode="json"),
                payload.plan.model_dump(mode="json") if payload.plan is not None else None,
            )
            saved = self._open(unit, character.character_id)
        return SavedCharacterSaveResponseDTO(
            schema_version="web-saved-character-save/0.1", saved=saved
        )

    def update(
        self,
        character_id: str,
        payload: SavedCharacterSaveRequestDTO,
    ) -> SavedCharacterSaveResponseDTO:
        if payload.expected_current_revision_id is None:
            raise CharacterRevisionConflictError("missing", "unknown")
        draft, request, plan, requested = _domain_inputs(payload)
        with PersistenceUnitOfWork(self.database_path) as unit:
            before = unit.characters.get_character(character_id)
            if before.current_revision_id != payload.expected_current_revision_id:
                raise CharacterRevisionConflictError(
                    payload.expected_current_revision_id, before.current_revision_id
                )
            context = build_character_skill_design_context(request, draft, plan)
            current_state = CharacterSkillPersistenceService(
                unit.character_skills
            ).load_current_state(character_id, current_context=context)
            if (
                current_state.current_kit_assignment_id
                != payload.expected_current_kit_assignment_id
            ):
                raise CharacterSkillPersistenceConflictError(
                    "Kit assignment",
                    payload.expected_current_kit_assignment_id,
                    current_state.current_kit_assignment_id,
                )
            _reject_stale_retained(current_state, requested)
            revision = unit.characters.append_revision(
                character_id,
                draft,
                expected_current_revision_id=payload.expected_current_revision_id,
            )
            _persist_associations(
                unit,
                character_id,
                revision.revision_id,
                payload.expected_current_kit_assignment_id,
                context,
                requested,
                current_state=current_state,
            )
            unit.workspace.save(
                character_id,
                payload.request.model_dump(mode="json"),
                payload.plan.model_dump(mode="json") if payload.plan is not None else None,
            )
            saved = self._open(unit, character_id)
        return SavedCharacterSaveResponseDTO(
            schema_version="web-saved-character-save/0.1", saved=saved
        )

    def _open(self, unit: PersistenceUnitOfWork, character_id: str) -> SavedCharacterDTO:
        character = unit.characters.get_character(character_id)
        metadata = unit.workspace.get(character_id)
        request_dto, plan_dto = _restore_context_metadata(
            metadata, character.current_revision.draft
        )
        request = CharacterGenerationApplication.to_domain_request(request_dto)
        plan = (
            CharacterDesignPlan.from_mapping(plan_dto.model_dump(mode="json")) if plan_dto else None
        )
        context = build_character_skill_design_context(
            request, character.current_revision.draft, plan
        )
        state = CharacterSkillPersistenceService(unit.character_skills).load_current_state(
            character_id, current_context=context
        )
        associations = [_association_dto(item, state) for item in state.active_associations]
        kit = (
            _kit_mapping(state.current_kit, state.active_associations, state)
            if state.current_kit
            else None
        )
        history = _history(unit, character_id, state)
        revisions = unit.characters.list_revisions(character_id)
        current_revision = next(item for item in revisions if item.is_current)
        structural = None
        if state.structural_validation is not None:
            structural = {
                "status": state.structural_validation.status,
                "blocking": state.structural_validation.blocking,
                "findings": [item.to_mapping() for item in state.structural_validation.findings],
            }
        return SavedCharacterDTO(
            character_id=character.character_id,
            current_revision_id=character.current_revision_id,
            current_kit_assignment_id=state.current_kit_assignment_id,
            created_at=character.created_at,
            updated_at=character.updated_at,
            revision=SavedCharacterRevisionDTO(**current_revision.__dict__),
            draft=character.current_revision.draft.to_dict(),
            request=request_dto,
            plan=plan_dto,
            associations=associations,
            kit=kit,
            derived=SavedCharacterDerivedStateDTO(
                freshness_by_association_id=state.freshness_by_association_id,
                compatibility_by_association_id={
                    key: value.status.value
                    for key, value in state.compatibility_by_association_id.items()
                },
                structural_validation=structural,
            ),
            history=history,
        )


def _domain_inputs(payload: SavedCharacterSaveRequestDTO):
    draft = CharacterDraft.from_mapping(payload.draft.model_dump(mode="json"))
    request = CharacterGenerationApplication.to_domain_request(payload.request)
    plan = (
        CharacterDesignPlan.from_mapping(payload.plan.model_dump(mode="json"))
        if payload.plan
        else None
    )
    requested = tuple(
        _RequestedAssociation(item.association_id, _domain_association(item))
        for item in payload.associations
    )
    return draft, request, plan, requested


def _domain_association(item: CharacterSkillAssociationDTO) -> CharacterSkillAssociation:
    artifact = SkillDesignArtifact.from_mapping(item.artifact.model_dump(mode="json"))
    binding_payload = item.binding.model_dump(mode="json")
    binding = CharacterSkillArtifactBinding(
        artifact_digest=binding_payload["artifact_digest"],
        source_context_fingerprint=binding_payload["source_context_fingerprint"],
        alignment=_alignment_from_mapping(binding_payload["alignment"]),
        alignment_version=binding_payload["alignment_version"],
        character_context_projection_version=binding_payload[
            "character_context_projection_version"
        ],
        binding_contract_version=binding_payload["binding_contract_version"],
    )
    return CharacterSkillAssociation.from_artifact(
        artifact,
        binding,
        slot=item.slot,
        family=item.family,
        mode=item.mode,
        display_summary=item.display_summary,
    )


def _persist_associations(
    unit: PersistenceUnitOfWork,
    character_id: str,
    revision_id: str,
    expected_assignment_id: str | None,
    context: object,
    requested: tuple[_RequestedAssociation, ...],
    *,
    current_state=None,
) -> None:
    service = CharacterSkillPersistenceService(unit.character_skills)
    state = current_state or service.load_current_state(character_id, current_context=context)
    current_by_id = {item.association_id: item for item in state.active_associations}
    requested_by_id = {item.transport_id: item for item in requested}
    assignment_id = expected_assignment_id
    for item in state.active_associations:
        if item.association_id not in requested_by_id:
            state = service.detach(
                character_id,
                item.association_id,
                expected_character_revision_id=revision_id,
                expected_current_kit_assignment_id=assignment_id,
                current_context=context,
            )
            assignment_id = state.current_kit_assignment_id
    for item in requested:
        current = current_by_id.get(item.transport_id)
        if current is None:
            record = unit.skill_artifacts.save(item.association.artifact)
            state = service.attach(
                character_id,
                item.association,
                artifact_record_id=record.record_id,
                expected_character_revision_id=revision_id,
                expected_current_kit_assignment_id=assignment_id,
                current_context=context,
            )
            assignment_id = state.current_kit_assignment_id
            continue
        if _same_association(current.association, item.association):
            continue
        if (
            current.association.artifact == item.association.artifact
            and current.association.binding == item.association.binding
            and current.association.family == item.association.family
            and current.association.mode == item.association.mode
            and current.association.display_summary == item.association.display_summary
        ):
            state = service.change_placement(
                character_id,
                current.association_id,
                slot=item.association.slot,
                expected_character_revision_id=revision_id,
                expected_current_kit_assignment_id=assignment_id,
                current_context=context,
            )
        else:
            record = unit.skill_artifacts.save(item.association.artifact)
            state = service.replace(
                character_id,
                current.association_id,
                item.association,
                artifact_record_id=record.record_id,
                expected_character_revision_id=revision_id,
                expected_current_kit_assignment_id=assignment_id,
                current_context=context,
            )
        assignment_id = state.current_kit_assignment_id
    if state.character_revision_id != revision_id:
        state = service.rebind_current_kit(
            character_id,
            expected_character_revision_id=revision_id,
            expected_current_kit_assignment_id=assignment_id,
            current_context=context,
        )


def _reject_stale_retained(state, requested: tuple[_RequestedAssociation, ...]) -> None:
    requested_ids = {item.transport_id for item in requested}
    stale = [
        item.association_id
        for item in state.active_associations
        if item.association_id in requested_ids
        and state.freshness_by_association_id.get(item.association_id) != "current"
    ]
    if stale:
        raise CharacterSkillPersistenceConflictError("binding freshness", "current", "stale")


def _same_association(left: CharacterSkillAssociation, right: CharacterSkillAssociation) -> bool:
    return (
        left.artifact == right.artifact
        and left.binding == right.binding
        and left.slot == right.slot
        and left.family == right.family
        and left.mode == right.mode
        and left.display_summary == right.display_summary
    )


def _association_dto(item, state) -> SavedCharacterAssociationDTO:
    compatibility = state.compatibility_by_association_id[item.association_id].status.value
    return _association_dto_with_compatibility(item, compatibility)


def _association_dto_with_compatibility(item, compatibility: str) -> SavedCharacterAssociationDTO:
    mapping = item.association.to_mapping()
    mapping["association_id"] = item.association_id
    mapping["artifact_compatibility"] = compatibility
    return SavedCharacterAssociationDTO.model_validate(mapping)


def _kit_mapping(kit: CharacterKit, active, state) -> dict[str, Any]:
    associations = []
    by_digest = {item.association.artifact_digest: item for item in active}
    for association in kit.associations:
        item = by_digest[association.artifact_digest]
        associations.append(_association_dto(item, state).model_dump(mode="json"))
    return {
        "contract_version": kit.contract_version,
        "placement_schema_version": kit.placement_schema_version,
        "associations": associations,
        "kit_digest": kit.kit_digest,
    }


def _history(
    unit: PersistenceUnitOfWork, character_id: str, state
) -> list[SavedCharacterHistorySummaryDTO]:
    values: list[SavedCharacterHistorySummaryDTO] = []
    for item in state.active_associations:
        for report in unit.historical_reports.list_skill_evaluations(item.artifact_record_id):
            values.append(
                SavedCharacterHistorySummaryDTO(
                    report_family="skill_evaluation",
                    report_id=report.report_id,
                    created_at=report.created_at,
                    target=item.association.artifact_digest,
                    version=report.evaluator_version,
                    status=_enum_value(report.report.outcome),
                )
            )
        for report in unit.historical_reports.list_alignments(
            item.artifact_record_id,
            source_context_fingerprint=item.association.binding.source_context_fingerprint,
        ):
            values.append(
                SavedCharacterHistorySummaryDTO(
                    report_family="alignment",
                    report_id=report.report_id,
                    created_at=report.created_at,
                    target=item.association.artifact_digest,
                    version=report.alignment_version,
                    status=report.report.status,
                )
            )
    kit_record_id = unit.character_skills.current_kit_record_id(character_id)
    if kit_record_id is not None:
        for report in unit.historical_reports.list_role_coverage(kit_record_id):
            values.append(
                SavedCharacterHistorySummaryDTO(
                    report_family="role_coverage",
                    report_id=report.report_id,
                    created_at=report.created_at,
                    target=report.kit_digest,
                    version=report.evaluator_version,
                    status=report.report.status,
                )
            )
    return sorted(values, key=lambda item: (item.created_at, item.report_id))


def _restore_context_metadata(metadata, draft: CharacterDraft):
    if metadata is not None:
        return (
            CharacterGenerationRequestDTO.model_validate(metadata.request),
            CharacterPlanDTO.model_validate(metadata.plan) if metadata.plan is not None else None,
        )
    return (
        CharacterGenerationRequestDTO(
            brief=draft.name,
            combat_role_profile=draft.combat_role_profile.to_dict(),
        ),
        None,
    )


def _summary(item: SavedCharacterSummary) -> SavedCharacterSummaryDTO:
    return SavedCharacterSummaryDTO(**item.__dict__)


def _enum_value(value: object) -> str:
    return getattr(value, "value", str(value))


__all__ = ["StudioSaveService"]
