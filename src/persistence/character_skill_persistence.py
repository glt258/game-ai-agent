"""SQLite adapter for Character-specific Skill bindings, associations, and Kits."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from character_intelligence.character_kit import (
    CHARACTER_KIT_CONTRACT_VERSION,
    KIT_PLACEMENT_SCHEMA_VERSION,
    CharacterKit,
    CharacterKitContractError,
    CharacterKitStructuralValidationResult,
    CharacterKitStructuralValidator,
    build_character_kit,
)
from character_intelligence.character_skill_alignment import (
    CharacterSkillAlignmentFinding,
    CharacterSkillAlignmentResult,
    CharacterSkillEvidence,
)
from character_intelligence.character_skill_association import (
    CharacterSkillAssociation,
    CharacterSkillAssociationError,
    SkillSlot,
)
from character_intelligence.skill_artifact import (
    CHARACTER_SKILL_BINDING_CONTRACT_VERSION,
    ArtifactContractError,
    ArtifactDriftInspection,
    CharacterSkillArtifactBinding,
    SkillArtifactVersionMetadata,
    SkillDesignArtifact,
    current_skill_artifact_versions,
    inspect_skill_artifact_compatibility,
)

from .characters import CharacterRepository
from .errors import (
    CharacterSkillPersistenceConflictError,
    PersistenceContractUnsupportedError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceRecordNotFoundError,
)
from .skill_artifacts import SkillArtifactRepository

BINDING_CONTRACT_VERSION = CHARACTER_SKILL_BINDING_CONTRACT_VERSION
_ALIGNMENT_STATUSES = {"PASS", "FAIL", "PARTIAL", "NOT_EVALUATED"}
_ALIGNMENT_COVERAGES = {"primary", "secondary", "none", "not_evaluated"}
_FINDING_KINDS = {
    "supporting_evidence",
    "missing_evidence",
    "direct_contradiction",
    "not_evaluated",
}


@dataclass(frozen=True)
class PersistedBinding:
    binding_id: str
    character_id: str
    artifact_record_id: int
    binding: CharacterSkillArtifactBinding
    created_at: str


@dataclass(frozen=True)
class PersistedAssociation:
    association_id: str
    character_id: str
    revision_id: str
    binding_id: str
    artifact_record_id: int
    ordinal: int
    association: CharacterSkillAssociation
    created_at: str


@dataclass(frozen=True)
class AssociationRevisionSummary:
    association_revision_id: str
    association_id: str
    binding_id: str
    placement: SkillSlot
    placement_order: int
    ordinal: int
    parent_revision_id: str | None
    created_at: str
    is_current: bool


@dataclass(frozen=True)
class CharacterSkillState:
    character_id: str
    character_revision_id: str
    active_associations: tuple[PersistedAssociation, ...]
    current_kit_assignment_id: str | None
    current_kit: CharacterKit | None
    freshness_by_association_id: dict[str, Literal["current", "stale"]]
    compatibility_by_association_id: dict[str, ArtifactDriftInspection]
    structural_validation: CharacterKitStructuralValidationResult | None


class CharacterSkillRepository:
    """Deep persistence adapter for Character-specific Skill state."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        characters: CharacterRepository,
        artifacts: SkillArtifactRepository,
    ) -> None:
        self._connection = connection
        self._characters = characters
        self._artifacts = artifacts

    def attach(
        self,
        character_id: str,
        association: CharacterSkillAssociation,
        *,
        artifact_record_id: int,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        def operation() -> CharacterSkillState:
            character = self._guard_character(character_id, expected_character_revision_id)
            self._guard_kit_assignment(character_id, expected_current_kit_assignment_id)
            versions = _current_versions(current_versions)
            artifact = self._load_exact_artifact(artifact_record_id, association.artifact)
            context = _context_fingerprint(current_context)
            self._verify_attach(association, artifact, context, versions)
            active = list(self._load_active_associations(character_id))
            self._reject_duplicate_or_occupied(active, association)
            binding_id = self._save_binding(character_id, artifact_record_id, association.binding)
            durable_association_id = _new_id()
            association_revision_id = _new_id()
            candidate = active + [
                _UnpersistedAssociation(
                    durable_association_id,
                    character_id,
                    association_revision_id,
                    binding_id,
                    artifact_record_id,
                    association,
                    None,
                )
            ]
            kit = _build_checked_kit(item.association for item in candidate)
            ordinal = _ordinal_for(kit, association)
            self._insert_association(
                durable_association_id,
                character_id,
                association_revision_id,
                binding_id,
                association,
                ordinal,
                parent_revision_id=None,
            )
            self._persist_kit_assignment(
                character,
                candidate,
                kit,
                expected_current_kit_assignment_id,
            )
            return self._load_current_state(character_id, context, versions)

        return self._run_write("attach_character_skill", operation)

    def detach(
        self,
        character_id: str,
        association_id: str,
        *,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        def operation() -> CharacterSkillState:
            character = self._guard_character(character_id, expected_character_revision_id)
            self._guard_kit_assignment(character_id, expected_current_kit_assignment_id)
            versions = _current_versions(current_versions)
            context = _context_fingerprint(current_context)
            active = list(self._load_active_associations(character_id))
            target = _find_active(active, association_id)
            remaining = [item for item in active if item.association_id != association_id]
            self._close_association(target)
            kit = _build_checked_kit(item.association for item in remaining)
            self._persist_kit_assignment(
                character,
                remaining,
                kit,
                expected_current_kit_assignment_id,
            )
            return self._load_current_state(character_id, context, versions)

        return self._run_write("detach_character_skill", operation)

    def replace(
        self,
        character_id: str,
        association_id: str,
        replacement: CharacterSkillAssociation,
        *,
        artifact_record_id: int,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        def operation() -> CharacterSkillState:
            character = self._guard_character(character_id, expected_character_revision_id)
            self._guard_kit_assignment(character_id, expected_current_kit_assignment_id)
            versions = _current_versions(current_versions)
            context = _context_fingerprint(current_context)
            active = list(self._load_active_associations(character_id))
            target = _find_active(active, association_id)
            if replacement.slot != target.association.slot:
                raise PersistenceIntegrityError("replacement must keep the existing placement")
            artifact = self._load_exact_artifact(artifact_record_id, replacement.artifact)
            self._verify_attach(replacement, artifact, context, versions)
            remaining = [item for item in active if item.association_id != association_id]
            self._reject_duplicate_or_occupied(remaining, replacement)
            self._close_association(target)
            binding_id = self._save_binding(character_id, artifact_record_id, replacement.binding)
            durable_association_id = _new_id()
            association_revision_id = _new_id()
            candidate = remaining + [
                _UnpersistedAssociation(
                    durable_association_id,
                    character_id,
                    association_revision_id,
                    binding_id,
                    artifact_record_id,
                    replacement,
                    None,
                )
            ]
            kit = _build_checked_kit(item.association for item in candidate)
            ordinal = _ordinal_for(kit, replacement)
            self._insert_association(
                durable_association_id,
                character_id,
                association_revision_id,
                binding_id,
                replacement,
                ordinal,
                parent_revision_id=None,
            )
            self._persist_kit_assignment(
                character,
                candidate,
                kit,
                expected_current_kit_assignment_id,
            )
            return self._load_current_state(character_id, context, versions)

        return self._run_write("replace_character_skill", operation)

    def change_placement(
        self,
        character_id: str,
        association_id: str,
        *,
        slot: SkillSlot | str,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        def operation() -> CharacterSkillState:
            character = self._guard_character(character_id, expected_character_revision_id)
            self._guard_kit_assignment(character_id, expected_current_kit_assignment_id)
            versions = _current_versions(current_versions)
            context = _context_fingerprint(current_context)
            active = list(self._load_active_associations(character_id))
            target = _find_active(active, association_id)
            resolved_slot = _resolve_slot(slot)
            if resolved_slot == target.association.slot:
                return self._load_current_state(character_id, context, versions)
            if any(item.association.slot == resolved_slot for item in active):
                raise PersistenceIntegrityError("placement is already occupied")
            changed = CharacterSkillAssociation.from_artifact(
                target.association.artifact,
                target.association.binding,
                slot=resolved_slot,
                family=target.association.family,
                mode=target.association.mode,
                display_summary=target.association.display_summary,
            )
            remaining = [item for item in active if item.association_id != association_id]
            association_revision_id = _new_id()
            candidate = remaining + [
                _UnpersistedAssociation(
                    target.association_id,
                    character_id,
                    association_revision_id,
                    target.binding_id,
                    target.artifact_record_id,
                    changed,
                    target.revision_id,
                )
            ]
            kit = _build_checked_kit(item.association for item in candidate)
            ordinal = _ordinal_for(kit, changed)
            self._insert_association_revision(
                association_revision_id,
                target.association_id,
                character_id,
                target.binding_id,
                changed,
                ordinal,
                parent_revision_id=target.revision_id,
            )
            updated = self._connection.execute(
                """
                UPDATE associations
                SET current_revision_id = ?, closed_at = NULL
                WHERE association_id = ? AND character_id = ?
                  AND current_revision_id = ?
                """,
                (association_revision_id, target.association_id, character_id, target.revision_id),
            )
            if updated.rowcount != 1:
                raise self._association_conflict(character_id, association_id, target.revision_id)
            self._persist_kit_assignment(
                character,
                candidate,
                kit,
                expected_current_kit_assignment_id,
            )
            return self._load_current_state(character_id, context, versions)

        return self._run_write("change_character_skill_placement", operation)

    def load_current_state(
        self,
        character_id: str,
        *,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._load_current_state(
            character_id,
            _context_fingerprint(current_context),
            _current_versions(current_versions),
        )

    def rebind_current_kit(
        self,
        character_id: str,
        *,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        """Move an unchanged Kit assignment to a newly-current Character revision."""

        def operation() -> CharacterSkillState:
            character = self._guard_character(character_id, expected_character_revision_id)
            self._guard_kit_assignment(character_id, expected_current_kit_assignment_id)
            versions = _current_versions(current_versions)
            context = _context_fingerprint(current_context)
            state = self._load_current_state(character_id, context, versions)
            if state.current_kit is not None:
                self._persist_kit_assignment(
                    character,
                    list(state.active_associations),
                    state.current_kit,
                    expected_current_kit_assignment_id,
                )
            return self._load_current_state(character_id, context, versions)

        return self._run_write("rebind_character_kit", operation)

    def current_kit_record_id(self, character_id: str) -> int | None:
        row = self._current_assignment(character_id)
        return int(row["kit_record_id"]) if row is not None else None

    def get_binding(self, character_id: str, binding_id: str) -> PersistedBinding:
        row = self._connection.execute(
            """
            SELECT binding_id, character_id, artifact_record_id, artifact_digest,
                   binding_contract_version, source_context_fingerprint,
                   binding_payload_json, created_at
            FROM bindings WHERE character_id = ? AND binding_id = ?
            """,
            (character_id, binding_id),
        ).fetchone()
        if row is None:
            raise PersistenceRecordNotFoundError(
                f"binding {binding_id} was not found for Character {character_id}"
            )
        return self._binding_from_row(row)

    def list_association_revisions(
        self,
        character_id: str,
        association_id: str,
    ) -> tuple[AssociationRevisionSummary, ...]:
        association = self._association_row(character_id, association_id)
        rows = self._connection.execute(
            """
            SELECT association_revision_id, association_id, binding_id,
                   placement, placement_order, ordinal, parent_revision_id,
                   revision_sequence, created_at
            FROM association_revisions
            WHERE association_id = ? AND character_id = ?
            ORDER BY revision_sequence
            """,
            (association_id, character_id),
        ).fetchall()
        return tuple(
            AssociationRevisionSummary(
                association_revision_id=row["association_revision_id"],
                association_id=row["association_id"],
                binding_id=row["binding_id"],
                placement=_resolve_slot(row["placement"]),
                placement_order=row["placement_order"],
                ordinal=row["ordinal"],
                parent_revision_id=row["parent_revision_id"],
                created_at=row["created_at"],
                is_current=row["association_revision_id"] == association["current_revision_id"],
            )
            for row in rows
        )

    def _load_current_state(
        self,
        character_id: str,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata,
    ) -> CharacterSkillState:
        character = self._characters.get_character(character_id)
        context_fingerprint = current_context
        active = self._load_active_associations(character_id)
        assignment = self._current_assignment(character_id)
        if assignment is None:
            if active:
                raise PersistenceIntegrityError(
                    "active associations have no current Kit assignment"
                )
            return CharacterSkillState(
                character_id,
                character.current_revision_id,
                active,
                None,
                None,
                {},
                {},
                None,
            )

        kit = self._load_assigned_kit(character_id, assignment, active)
        active = tuple(
            replace(item, ordinal=_ordinal_for(kit, item.association)) for item in active
        )
        freshness = {
            item.association_id: item.association.binding.freshness_for(context_fingerprint)
            for item in active
        }
        compatibility = {
            item.association_id: inspect_skill_artifact_compatibility(
                item.association.artifact.versions,
                current_versions,
            )
            for item in active
        }
        return CharacterSkillState(
            character_id,
            character.current_revision_id,
            active,
            assignment["assignment_id"],
            kit,
            freshness,
            compatibility,
            CharacterKitStructuralValidator().validate(kit),
        )

    def _load_active_associations(self, character_id: str) -> tuple[PersistedAssociation, ...]:
        rows = self._connection.execute(
            """
            SELECT a.association_id, a.character_id, a.current_revision_id,
                   ar.binding_id, ar.placement,
                   ar.placement_order, ar.ordinal, ar.family, ar.mode,
                   ar.display_summary, ar.parent_revision_id, ar.created_at
            FROM associations AS a
            JOIN association_revisions AS ar
              ON ar.association_revision_id = a.current_revision_id
            WHERE a.character_id = ? AND a.current_revision_id IS NOT NULL
              AND a.closed_at IS NULL
            """,
            (character_id,),
        ).fetchall()
        values = tuple(self._association_from_row(row) for row in rows)
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.association.order,
                    item.association.artifact_digest,
                    item.association_id,
                ),
            )
        )

    def _association_from_row(self, row: sqlite3.Row) -> PersistedAssociation:
        binding = self._binding_from_row_by_id(row["character_id"], row["binding_id"])
        stored_artifact = self._load_exact_artifact(binding.artifact_record_id, None)
        if stored_artifact.artifact_digest != binding.binding.artifact_digest:
            raise PersistenceIntegrityError("binding artifact digest is inconsistent")
        try:
            association = CharacterSkillAssociation.from_artifact(
                stored_artifact,
                binding.binding,
                slot=_resolve_slot(row["placement"]),
                family=row["family"],
                mode=row["mode"],
                display_summary=row["display_summary"],
            )
        except (CharacterSkillAssociationError, TypeError, ValueError) as error:
            raise PersistenceIntegrityError("stored association is invalid") from error
        if association.order != row["placement_order"]:
            raise PersistenceIntegrityError("association placement order is inconsistent")
        if row["ordinal"] < 0:
            raise PersistenceIntegrityError("association ordinal is invalid")
        return PersistedAssociation(
            association_id=row["association_id"],
            character_id=row["character_id"],
            revision_id=row["current_revision_id"],
            binding_id=row["binding_id"],
            artifact_record_id=binding.artifact_record_id,
            ordinal=row["ordinal"],
            association=association,
            created_at=row["created_at"],
        )

    def _binding_from_row_by_id(self, character_id: str, binding_id: str) -> PersistedBinding:
        row = self._connection.execute(
            """
            SELECT binding_id, character_id, artifact_record_id, artifact_digest,
                   binding_contract_version, source_context_fingerprint,
                   binding_payload_json, created_at
            FROM bindings WHERE character_id = ? AND binding_id = ?
            """,
            (character_id, binding_id),
        ).fetchone()
        if row is None:
            raise PersistenceIntegrityError("association references missing Binding")
        return self._binding_from_row(row)

    def _binding_from_row(self, row: sqlite3.Row) -> PersistedBinding:
        try:
            payload = json.loads(row["binding_payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("binding payload JSON is malformed") from error
        if (
            not isinstance(payload, Mapping)
            or _canonical_json(payload) != row["binding_payload_json"]
        ):
            raise PersistenceIntegrityError("binding payload JSON is not canonical")
        binding = _binding_from_mapping(payload)
        if row["binding_contract_version"] != binding.binding_contract_version:
            raise PersistenceIntegrityError("binding contract metadata is inconsistent")
        if row["source_context_fingerprint"] != binding.source_context_fingerprint:
            raise PersistenceIntegrityError("binding fingerprint metadata is inconsistent")
        artifact = self._load_exact_artifact(row["artifact_record_id"], None)
        if row["artifact_digest"] != binding.artifact_digest != artifact.artifact_digest:
            raise PersistenceIntegrityError("binding artifact reference is inconsistent")
        return PersistedBinding(
            row["binding_id"],
            row["character_id"],
            row["artifact_record_id"],
            binding,
            row["created_at"],
        )

    def _load_assigned_kit(
        self,
        character_id: str,
        assignment: sqlite3.Row,
        active: tuple[PersistedAssociation, ...],
    ) -> CharacterKit:
        if assignment["character_id"] != character_id:
            raise PersistenceIntegrityError("Kit assignment ownership is inconsistent")
        try:
            self._characters.get_revision(character_id, assignment["character_revision_id"])
        except PersistenceError as error:
            raise PersistenceIntegrityError(
                "Kit assignment Character revision is inconsistent"
            ) from error
        content = self._connection.execute(
            """
            SELECT kit_record_id, kit_digest, kit_contract_version,
                   placement_schema_version, kit_payload_json, created_at
            FROM character_kit_contents WHERE kit_record_id = ?
            """,
            (assignment["kit_record_id"],),
        ).fetchone()
        if content is None:
            raise PersistenceIntegrityError("Kit assignment references missing Kit content")
        kit = _build_checked_kit(item.association for item in active)
        if content["kit_digest"] != kit.kit_digest:
            raise PersistenceIntegrityError("Kit digest does not match active associations")
        if content["kit_contract_version"] != CHARACTER_KIT_CONTRACT_VERSION:
            raise PersistenceContractUnsupportedError(content["kit_contract_version"])
        if content["placement_schema_version"] != KIT_PLACEMENT_SCHEMA_VERSION:
            raise PersistenceContractUnsupportedError(content["placement_schema_version"])
        try:
            payload = json.loads(content["kit_payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PersistenceIntegrityError("Kit payload JSON is malformed") from error
        if (
            not isinstance(payload, Mapping)
            or payload != _kit_snapshot_payload(kit)
            or _canonical_json(payload) != content["kit_payload_json"]
        ):
            raise PersistenceIntegrityError("Kit snapshot does not match canonical Kit content")

        relation_rows = self._connection.execute(
            """
            SELECT association_id, association_revision_id, artifact_record_id,
                   artifact_digest, placement, placement_order, ordinal
            FROM character_kit_assignment_members
            WHERE assignment_id = ?
            ORDER BY placement_order, ordinal, association_id
            """,
            (assignment["assignment_id"],),
        ).fetchall()
        if len(relation_rows) != len(active):
            raise PersistenceIntegrityError("Kit snapshot and active relations differ")
        by_id = {item.association_id: item for item in active}
        for relation in relation_rows:
            item = by_id.get(relation["association_id"])
            if item is None or item.revision_id != relation["association_revision_id"]:
                raise PersistenceIntegrityError(
                    "Kit relation does not reference current association revision"
                )
            if (
                item.artifact_record_id != relation["artifact_record_id"]
                or item.association.artifact_digest != relation["artifact_digest"]
                or item.association.slot.value != relation["placement"]
                or item.association.order != relation["placement_order"]
                or _ordinal_for(kit, item.association) != relation["ordinal"]
            ):
                raise PersistenceIntegrityError("Kit relation metadata is inconsistent")
        return kit

    def _persist_kit_assignment(
        self,
        character: Any,
        associations: list["_UnpersistedAssociation"] | list[PersistedAssociation],
        kit: CharacterKit,
        expected_assignment_id: str | None,
    ) -> str:
        payload_json = _canonical_json(_kit_snapshot_payload(kit))
        row = self._connection.execute(
            "SELECT kit_record_id, kit_payload_json FROM character_kit_contents WHERE kit_digest = ?",
            (kit.kit_digest,),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO character_kit_contents (
                    kit_digest, kit_contract_version, placement_schema_version,
                    kit_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    kit.kit_digest,
                    kit.contract_version,
                    kit.placement_schema_version,
                    payload_json,
                    _utc_now(),
                ),
            )
            row = self._connection.execute(
                "SELECT kit_record_id, kit_payload_json FROM character_kit_contents WHERE kit_digest = ?",
                (kit.kit_digest,),
            ).fetchone()
        if row is None or row["kit_payload_json"] != payload_json:
            raise PersistenceIntegrityError("Kit content conflicts with kit_digest")
        assignment_id = _new_id()
        self._connection.execute(
            """
            INSERT INTO character_kit_assignments (
                assignment_id, character_id, character_revision_id,
                kit_record_id, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                assignment_id,
                character.character_id,
                character.current_revision_id,
                row["kit_record_id"],
                _utc_now(),
            ),
        )
        for item in associations:
            self._connection.execute(
                """
                INSERT INTO character_kit_assignment_members (
                    assignment_id, association_id, association_revision_id,
                    artifact_record_id, artifact_digest, placement,
                    placement_order, ordinal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    item.association_id,
                    item.revision_id,
                    item.artifact_record_id,
                    item.association.artifact_digest,
                    item.association.slot.value,
                    item.association.order,
                    _ordinal_for(kit, item.association),
                ),
            )
        self._cas_current_assignment(character.character_id, expected_assignment_id, assignment_id)
        return assignment_id

    def _save_binding(
        self,
        character_id: str,
        artifact_record_id: int,
        binding: CharacterSkillArtifactBinding,
    ) -> str:
        payload = binding.to_mapping()
        restored = _binding_from_mapping(payload)
        payload_json = _canonical_json(payload)
        existing = self._connection.execute(
            """
            SELECT binding_id, binding_payload_json
            FROM bindings
            WHERE character_id = ? AND artifact_record_id = ?
              AND binding_payload_json = ?
            """,
            (character_id, artifact_record_id, payload_json),
        ).fetchone()
        if existing is not None:
            if existing["binding_payload_json"] != payload_json:
                raise PersistenceIntegrityError("Binding payload conflicts with stored data")
            self._binding_from_row_by_id(character_id, existing["binding_id"])
            return existing["binding_id"]
        binding_id = _new_id()
        self._connection.execute(
            """
            INSERT INTO bindings (
                binding_id, character_id, artifact_record_id, artifact_digest,
                binding_contract_version, source_context_fingerprint,
                binding_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding_id,
                character_id,
                artifact_record_id,
                restored.artifact_digest,
                restored.binding_contract_version,
                restored.source_context_fingerprint,
                payload_json,
                _utc_now(),
            ),
        )
        return binding_id

    def _insert_association(
        self,
        association_id: str,
        character_id: str,
        revision_id: str,
        binding_id: str,
        association: CharacterSkillAssociation,
        ordinal: int,
        *,
        parent_revision_id: str | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO associations (
                association_id, character_id, current_revision_id, created_at, closed_at
            ) VALUES (?, ?, ?, ?, NULL)
            """,
            (association_id, character_id, revision_id, _utc_now()),
        )
        self._insert_association_revision(
            revision_id,
            association_id,
            character_id,
            binding_id,
            association,
            ordinal,
            parent_revision_id=parent_revision_id,
        )

    def _insert_association_revision(
        self,
        revision_id: str,
        association_id: str,
        character_id: str,
        binding_id: str,
        association: CharacterSkillAssociation,
        ordinal: int,
        *,
        parent_revision_id: str | None,
    ) -> None:
        next_sequence = self._connection.execute(
            """
            SELECT COALESCE(MAX(revision_sequence), 0) + 1
            FROM association_revisions WHERE association_id = ?
            """,
            (association_id,),
        ).fetchone()[0]
        self._connection.execute(
            """
            INSERT INTO association_revisions (
                association_revision_id, association_id, character_id, binding_id,
                placement, placement_order, ordinal, family, mode, display_summary,
                parent_revision_id, revision_sequence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                association_id,
                character_id,
                binding_id,
                association.slot.value,
                association.order,
                ordinal,
                association.family,
                association.mode,
                association.display_summary,
                parent_revision_id,
                next_sequence,
                _utc_now(),
            ),
        )

    def _close_association(self, association: PersistedAssociation) -> None:
        updated = self._connection.execute(
            """
            UPDATE associations
            SET current_revision_id = NULL, closed_at = ?
            WHERE association_id = ? AND character_id = ? AND current_revision_id = ?
            """,
            (
                _utc_now(),
                association.association_id,
                association.character_id,
                association.revision_id,
            ),
        )
        if updated.rowcount != 1:
            raise self._association_conflict(
                association.character_id,
                association.association_id,
                association.revision_id,
            )

    def _guard_character(self, character_id: str, expected_revision_id: str):
        character = self._characters.get_character(character_id)
        if character.current_revision_id != expected_revision_id:
            raise CharacterSkillPersistenceConflictError(
                "character revision",
                expected_revision_id,
                character.current_revision_id,
            )
        updated = self._connection.execute(
            """
            UPDATE characters SET updated_at = updated_at
            WHERE character_id = ? AND current_revision_id = ?
            """,
            (character_id, expected_revision_id),
        )
        if updated.rowcount != 1:
            current = self._characters.get_character(character_id).current_revision_id
            raise CharacterSkillPersistenceConflictError(
                "character revision", expected_revision_id, current
            )
        return character

    def _guard_kit_assignment(self, character_id: str, expected_assignment_id: str | None) -> None:
        current = self._current_assignment(character_id)
        actual = current["assignment_id"] if current is not None else None
        if actual != expected_assignment_id:
            raise CharacterSkillPersistenceConflictError(
                "Kit assignment", expected_assignment_id, actual
            )

    def _cas_current_assignment(
        self,
        character_id: str,
        expected_assignment_id: str | None,
        assignment_id: str,
    ) -> None:
        if expected_assignment_id is None:
            try:
                self._connection.execute(
                    """
                    INSERT INTO character_kit_current (
                        character_id, current_assignment_id, updated_at
                    ) VALUES (?, ?, ?)
                    """,
                    (character_id, assignment_id, _utc_now()),
                )
            except sqlite3.IntegrityError as error:
                current = self._current_assignment(character_id)
                actual = current["assignment_id"] if current is not None else None
                raise CharacterSkillPersistenceConflictError(
                    "Kit assignment", expected_assignment_id, actual
                ) from error
            return
        updated = self._connection.execute(
            """
            UPDATE character_kit_current
            SET current_assignment_id = ?, updated_at = ?
            WHERE character_id = ? AND current_assignment_id = ?
            """,
            (assignment_id, _utc_now(), character_id, expected_assignment_id),
        )
        if updated.rowcount != 1:
            current = self._current_assignment(character_id)
            actual = current["assignment_id"] if current is not None else None
            raise CharacterSkillPersistenceConflictError(
                "Kit assignment", expected_assignment_id, actual
            )

    def _current_assignment(self, character_id: str) -> sqlite3.Row | None:
        row = self._connection.execute(
            """
            SELECT c.current_assignment_id AS assignment_id, a.kit_record_id,
                   a.character_id, a.character_revision_id
            FROM character_kit_current AS c
            LEFT JOIN character_kit_assignments AS a
              ON a.assignment_id = c.current_assignment_id
            WHERE c.character_id = ?
            """,
            (character_id,),
        ).fetchone()
        if row is not None and row["kit_record_id"] is None:
            raise PersistenceIntegrityError("current Kit assignment is missing")
        return row

    def _association_row(self, character_id: str, association_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """
            SELECT association_id, character_id, current_revision_id
            FROM associations WHERE character_id = ? AND association_id = ?
            """,
            (character_id, association_id),
        ).fetchone()
        if row is None:
            if not self._characters.exists(character_id):
                raise PersistenceRecordNotFoundError(f"Character {character_id} was not found")
            raise PersistenceRecordNotFoundError(
                f"association {association_id} was not found for Character {character_id}"
            )
        return row

    def _association_conflict(
        self,
        character_id: str,
        association_id: str,
        expected_revision_id: str,
    ) -> CharacterSkillPersistenceConflictError:
        row = self._association_row(character_id, association_id)
        return CharacterSkillPersistenceConflictError(
            "association revision",
            expected_revision_id,
            row["current_revision_id"],
        )

    def _load_exact_artifact(
        self,
        artifact_record_id: int,
        expected: SkillDesignArtifact | None,
    ) -> SkillDesignArtifact:
        try:
            stored = self._artifacts.get(artifact_record_id)
        except PersistenceError as error:
            raise PersistenceIntegrityError("referenced Skill artifact is unavailable") from error
        if expected is not None and stored.artifact != expected:
            raise PersistenceIntegrityError("artifact authoring record does not match association")
        return stored.artifact

    def _verify_attach(
        self,
        association: CharacterSkillAssociation,
        artifact: SkillDesignArtifact,
        context_fingerprint: str,
        current_versions: SkillArtifactVersionMetadata,
    ) -> None:
        if association.artifact != artifact:
            raise PersistenceIntegrityError("association artifact does not match stored artifact")
        binding = association.binding
        if binding.artifact_digest != artifact.artifact_digest:
            raise PersistenceIntegrityError("binding artifact digest does not match artifact")
        if binding.alignment.artifact_digest != artifact.artifact_digest:
            raise PersistenceIntegrityError("alignment artifact digest does not match artifact")
        if binding.alignment.source_context_fingerprint != binding.source_context_fingerprint:
            raise PersistenceIntegrityError("alignment context fingerprint does not match binding")
        if binding.source_context_fingerprint != context_fingerprint:
            raise CharacterSkillPersistenceConflictError(
                "binding freshness", context_fingerprint, binding.source_context_fingerprint
            )
        if artifact.original_evaluation.outcome != "PASS" or binding.alignment.status != "PASS":
            raise PersistenceIntegrityError(
                "Attach requires Skill Evaluation PASS and Alignment PASS"
            )
        compatibility = inspect_skill_artifact_compatibility(artifact.versions, current_versions)
        if compatibility.status.value != "CURRENT_COMPATIBLE":
            raise PersistenceIntegrityError("Attach requires current compatible artifact versions")

    @staticmethod
    def _reject_duplicate_or_occupied(
        active: list[PersistedAssociation] | list["_UnpersistedAssociation"],
        association: CharacterSkillAssociation,
    ) -> None:
        if any(item.association.artifact_digest == association.artifact_digest for item in active):
            raise PersistenceIntegrityError("one artifact may be attached only once")
        if association.slot in (SkillSlot.PRIMARY, SkillSlot.SECONDARY) and any(
            item.association.slot == association.slot for item in active
        ):
            raise PersistenceIntegrityError("placement is occupied; use replace explicitly")

    def _run_write(self, name: str, operation):
        self._connection.execute(f"SAVEPOINT {name}")
        try:
            result = operation()
            self._connection.execute(f"RELEASE SAVEPOINT {name}")
            return result
        except PersistenceError:
            self._rollback_savepoint(name)
            raise
        except (
            CharacterKitContractError,
            CharacterSkillAssociationError,
            ArtifactContractError,
            TypeError,
            ValueError,
        ) as error:
            self._rollback_savepoint(name)
            if isinstance(error, ArtifactContractError) and "UNSUPPORTED" in error.code:
                raise PersistenceContractUnsupportedError(error.code) from error
            raise PersistenceIntegrityError(
                "Character Skill persistence contract is invalid"
            ) from error
        except sqlite3.IntegrityError as error:
            self._rollback_savepoint(name)
            raise PersistenceIntegrityError(
                "Character Skill persistence integrity check failed"
            ) from error
        except sqlite3.DatabaseError as error:
            self._rollback_savepoint(name)
            raise PersistenceIntegrityError("SQLite Character Skill write failed") from error

    def _rollback_savepoint(self, name: str) -> None:
        try:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
            self._connection.execute(f"RELEASE SAVEPOINT {name}")
        except sqlite3.DatabaseError:
            self._connection.rollback()


@dataclass(frozen=True)
class _UnpersistedAssociation:
    association_id: str
    character_id: str
    revision_id: str
    binding_id: str
    artifact_record_id: int
    association: CharacterSkillAssociation
    previous_revision_id: str | None


class CharacterSkillPersistenceService:
    """Explicit backend seam for Attach, Detach, Replace, and Skill-state load."""

    def __init__(self, repository: CharacterSkillRepository) -> None:
        self._repository = repository

    def attach(
        self,
        character_id: str,
        association: CharacterSkillAssociation,
        *,
        artifact_record_id: int,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.attach(
            character_id,
            association,
            artifact_record_id=artifact_record_id,
            expected_character_revision_id=expected_character_revision_id,
            expected_current_kit_assignment_id=expected_current_kit_assignment_id,
            current_context=current_context,
            current_versions=current_versions,
        )

    def detach(
        self,
        character_id: str,
        association_id: str,
        *,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.detach(
            character_id,
            association_id,
            expected_character_revision_id=expected_character_revision_id,
            expected_current_kit_assignment_id=expected_current_kit_assignment_id,
            current_context=current_context,
            current_versions=current_versions,
        )

    def replace(
        self,
        character_id: str,
        association_id: str,
        replacement: CharacterSkillAssociation,
        *,
        artifact_record_id: int,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.replace(
            character_id,
            association_id,
            replacement,
            artifact_record_id=artifact_record_id,
            expected_character_revision_id=expected_character_revision_id,
            expected_current_kit_assignment_id=expected_current_kit_assignment_id,
            current_context=current_context,
            current_versions=current_versions,
        )

    def change_placement(
        self,
        character_id: str,
        association_id: str,
        *,
        slot: SkillSlot | str,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.change_placement(
            character_id,
            association_id,
            slot=slot,
            expected_character_revision_id=expected_character_revision_id,
            expected_current_kit_assignment_id=expected_current_kit_assignment_id,
            current_context=current_context,
            current_versions=current_versions,
        )

    def load_current_state(
        self,
        character_id: str,
        *,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.load_current_state(
            character_id,
            current_context=current_context,
            current_versions=current_versions,
        )

    def rebind_current_kit(
        self,
        character_id: str,
        *,
        expected_character_revision_id: str,
        expected_current_kit_assignment_id: str | None,
        current_context: object,
        current_versions: SkillArtifactVersionMetadata | None = None,
    ) -> CharacterSkillState:
        return self._repository.rebind_current_kit(
            character_id,
            expected_character_revision_id=expected_character_revision_id,
            expected_current_kit_assignment_id=expected_current_kit_assignment_id,
            current_context=current_context,
            current_versions=current_versions,
        )


def _build_checked_kit(associations) -> CharacterKit:
    try:
        kit = build_character_kit(tuple(associations))
    except (
        CharacterKitContractError,
        CharacterSkillAssociationError,
        TypeError,
        ValueError,
    ) as error:
        raise PersistenceIntegrityError("CharacterKit structural contract is invalid") from error
    result = CharacterKitStructuralValidator().validate(kit)
    if result.status != "PASS":
        raise PersistenceIntegrityError("CharacterKit structural validation failed")
    return kit


def _ordinal_for(kit: CharacterKit, association: CharacterSkillAssociation) -> int:
    occurrence = 0
    for item in kit.associations:
        if item.slot == association.slot:
            if item.artifact_digest == association.artifact_digest:
                return occurrence
            occurrence += 1
    raise PersistenceIntegrityError("association is missing from Kit")


def _kit_snapshot_payload(kit: CharacterKit) -> dict[str, object]:
    occurrence: dict[SkillSlot, int] = {}
    members: list[dict[str, object]] = []
    for association in kit.associations:
        ordinal = occurrence.get(association.slot, 0)
        occurrence[association.slot] = ordinal + 1
        members.append(
            {
                "artifact_digest": association.artifact_digest,
                "placement": association.slot.value,
                "placement_order": association.order,
                "ordinal": ordinal,
            }
        )
    return {
        "contract_version": kit.contract_version,
        "placement_schema_version": kit.placement_schema_version,
        "associations": members,
        "kit_digest": kit.kit_digest,
    }


def _binding_from_mapping(value: object) -> CharacterSkillArtifactBinding:
    if not isinstance(value, Mapping):
        raise PersistenceIntegrityError("binding payload must be an object")
    payload = dict(value)
    expected = {
        "binding_contract_version",
        "artifact_digest",
        "source_context_fingerprint",
        "alignment",
        "alignment_version",
        "character_context_projection_version",
    }
    if set(payload) != expected:
        raise PersistenceIntegrityError("binding payload fields are not exact")
    contract_version = _string(payload["binding_contract_version"])
    if contract_version != BINDING_CONTRACT_VERSION:
        raise PersistenceContractUnsupportedError(contract_version)
    alignment = _alignment_from_mapping(payload["alignment"])
    binding = CharacterSkillArtifactBinding(
        artifact_digest=_string(payload["artifact_digest"]),
        source_context_fingerprint=_string(payload["source_context_fingerprint"]),
        alignment=alignment,
        alignment_version=_string(payload["alignment_version"]),
        character_context_projection_version=_string(
            payload["character_context_projection_version"]
        ),
        binding_contract_version=contract_version,
    )
    if alignment.artifact_digest != binding.artifact_digest:
        raise PersistenceIntegrityError("binding alignment digest does not match binding")
    if alignment.source_context_fingerprint != binding.source_context_fingerprint:
        raise PersistenceIntegrityError("binding alignment fingerprint does not match binding")
    return binding


def _alignment_from_mapping(value: object) -> CharacterSkillAlignmentResult:
    payload = _mapping(value)
    expected = {
        "status",
        "coverage",
        "findings",
        "blocking",
        "summary",
        "artifact_digest",
        "source_context_fingerprint",
        "skill_roles",
        "evidence",
    }
    if set(payload) != expected:
        raise PersistenceIntegrityError("alignment payload fields are not exact")
    status = _string(payload["status"])
    coverage = _string(payload["coverage"])
    if status not in _ALIGNMENT_STATUSES or coverage not in _ALIGNMENT_COVERAGES:
        raise PersistenceIntegrityError("alignment status or coverage is invalid")
    findings = tuple(_alignment_finding(item) for item in _list(payload["findings"]))
    evidence = tuple(_alignment_evidence(item) for item in _list(payload["evidence"]))
    skill_roles = tuple(_string(item) for item in _list(payload["skill_roles"]))
    artifact_digest = payload["artifact_digest"]
    if artifact_digest is not None and not isinstance(artifact_digest, str):
        raise PersistenceIntegrityError("alignment artifact digest is invalid")
    return CharacterSkillAlignmentResult(
        status=status,  # type: ignore[arg-type]
        coverage=coverage,  # type: ignore[arg-type]
        findings=findings,
        blocking=_bool(payload["blocking"]),
        summary=_string(payload["summary"]),
        artifact_digest=artifact_digest,
        source_context_fingerprint=_string(payload["source_context_fingerprint"]),
        skill_roles=skill_roles,  # type: ignore[arg-type]
        evidence=evidence,
    )


def _alignment_finding(value: object) -> CharacterSkillAlignmentFinding:
    payload = _mapping(value)
    expected = {
        "code",
        "kind",
        "blocking",
        "character_role",
        "skill_evidence",
        "field_path",
        "artifact_path",
        "message",
    }
    if set(payload) != expected:
        raise PersistenceIntegrityError("alignment finding fields are not exact")
    kind = _string(payload["kind"])
    if kind not in _FINDING_KINDS:
        raise PersistenceIntegrityError("alignment finding kind is invalid")
    character_role = payload["character_role"]
    if character_role is not None and not isinstance(character_role, str):
        raise PersistenceIntegrityError("alignment finding role is invalid")
    artifact_path = payload["artifact_path"]
    if artifact_path is not None and not isinstance(artifact_path, str):
        raise PersistenceIntegrityError("alignment finding artifact path is invalid")
    return CharacterSkillAlignmentFinding(
        code=_string(payload["code"]),
        kind=kind,  # type: ignore[arg-type]
        blocking=_bool(payload["blocking"]),
        character_role=character_role,  # type: ignore[arg-type]
        skill_evidence=tuple(
            _alignment_evidence(item) for item in _list(payload["skill_evidence"])
        ),
        field_path=_string(payload["field_path"]),
        artifact_path=artifact_path,
        message=_string(payload["message"]),
    )


def _alignment_evidence(value: object) -> CharacterSkillEvidence:
    payload = _mapping(value)
    expected = {"role", "operation", "family", "mode", "artifact_paths", "centrality"}
    if set(payload) != expected:
        raise PersistenceIntegrityError("alignment evidence fields are not exact")
    centrality = payload["centrality"]
    if centrality is not None and not isinstance(centrality, str):
        raise PersistenceIntegrityError("alignment evidence centrality is invalid")
    return CharacterSkillEvidence(
        role=_string(payload["role"]),  # type: ignore[arg-type]
        operation=_string(payload["operation"]),
        family=_string(payload["family"]),
        mode=_string(payload["mode"]),
        artifact_paths=tuple(_string(item) for item in _list(payload["artifact_paths"])),
        centrality=centrality,
    )


def _current_versions(value: SkillArtifactVersionMetadata | None) -> SkillArtifactVersionMetadata:
    if value is None:
        return current_skill_artifact_versions()
    if not isinstance(value, SkillArtifactVersionMetadata):
        raise TypeError("current_versions must be SkillArtifactVersionMetadata")
    return value


def _context_fingerprint(value: object) -> str:
    fingerprint = getattr(value, "source_context_fingerprint", None)
    if not isinstance(fingerprint, str) or not fingerprint:
        raise TypeError("current_context must expose source_context_fingerprint")
    return fingerprint


def _resolve_slot(value: SkillSlot | str) -> SkillSlot:
    if isinstance(value, SkillSlot):
        return value
    try:
        return SkillSlot(value)
    except (TypeError, ValueError) as error:
        raise PersistenceIntegrityError("placement is unsupported") from error


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise PersistenceIntegrityError("value must be an object")
    return dict(value)


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise PersistenceIntegrityError("value must be an array")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise PersistenceIntegrityError("value must be a string")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise PersistenceIntegrityError("value must be a boolean")
    return value


def _find_active(active: list[PersistedAssociation], association_id: str) -> PersistedAssociation:
    for item in active:
        if item.association_id == association_id:
            return item
    raise PersistenceRecordNotFoundError(f"active association {association_id} was not found")


def _new_id() -> str:
    return str(uuid.uuid4())


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "AssociationRevisionSummary",
    "BINDING_CONTRACT_VERSION",
    "CharacterSkillPersistenceService",
    "CharacterSkillRepository",
    "CharacterSkillState",
    "PersistedAssociation",
    "PersistedBinding",
]
