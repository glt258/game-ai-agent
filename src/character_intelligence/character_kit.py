"""Thin, session-only Character Skill Kit aggregate.

The Kit owns membership ordering and structural identity.  It does not own a
Character, copy Skill contents, evaluate semantics, or persist anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from .character_skill_alignment import (
    CharacterSkillAlignmentFinding,
    CharacterSkillAlignmentResult,
    CharacterSkillEvidence,
)
from .character_skill_association import (
    SLOT_ORDER,
    CharacterSkillAssociation,
    CharacterSkillCollection,
    SkillSlot,
)
from .skill_artifact import (
    CharacterSkillArtifactBinding,
    SkillDesignArtifact,
)

CHARACTER_KIT_CONTRACT_VERSION = "character-kit/0.1.0"
KIT_PLACEMENT_SCHEMA_VERSION = "character-kit-placement/0.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KitValidationStatus = Literal["PASS", "FAIL"]


class CharacterKitContractError(ValueError):
    """Stable fail-closed error for malformed Kit values."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class CharacterKitStructuralFinding:
    code: str
    field_path: str
    message: str
    blocking: bool = True

    def to_mapping(self) -> dict[str, object]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "message": self.message,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class CharacterKitStructuralValidationResult:
    status: KitValidationStatus
    blocking: bool
    findings: tuple[CharacterKitStructuralFinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "blocking": self.blocking,
            "findings": [item.to_mapping() for item in self.findings],
        }


@dataclass(frozen=True)
class CharacterKit:
    """Immutable ordered references to session Character-Skill associations."""

    contract_version: str
    associations: tuple[CharacterSkillAssociation, ...]
    kit_digest: str
    placement_schema_version: str = KIT_PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        associations = tuple(self.associations)
        if self.contract_version != CHARACTER_KIT_CONTRACT_VERSION:
            raise CharacterKitContractError(
                "KIT_UNSUPPORTED_CONTRACT_VERSION",
                "Kit contract version is not supported",
            )
        if self.placement_schema_version != KIT_PLACEMENT_SCHEMA_VERSION:
            raise CharacterKitContractError(
                "KIT_UNSUPPORTED_PLACEMENT_SCHEMA_VERSION",
                "Kit placement schema version is not supported",
            )
        if not all(isinstance(item, CharacterSkillAssociation) for item in associations):
            raise CharacterKitContractError(
                "KIT_ASSOCIATIONS_INVALID",
                "associations must contain CharacterSkillAssociation values",
            )
        if not isinstance(self.kit_digest, str) or not _SHA256_RE.fullmatch(self.kit_digest):
            raise CharacterKitContractError("KIT_DIGEST_INVALID", "kit_digest must be SHA-256")
        object.__setattr__(self, "associations", associations)

    @classmethod
    def from_mapping(cls, value: object) -> "CharacterKit":
        payload = _mapping(value, "character_kit")
        raw_contract_version = payload.get("contract_version")
        if raw_contract_version != CHARACTER_KIT_CONTRACT_VERSION:
            raise CharacterKitContractError(
                "KIT_UNSUPPORTED_CONTRACT_VERSION",
                "Kit contract version is not supported",
            )
        _exact_keys(
            payload,
            {"contract_version", "placement_schema_version", "associations", "kit_digest"},
            "character_kit",
        )
        contract_version = _string(payload["contract_version"], "character_kit/contract_version")
        placement_schema_version = _string(
            payload["placement_schema_version"],
            "character_kit/placement_schema_version",
        )
        if placement_schema_version != KIT_PLACEMENT_SCHEMA_VERSION:
            raise CharacterKitContractError(
                "KIT_UNSUPPORTED_PLACEMENT_SCHEMA_VERSION",
                "Kit placement schema version is not supported",
            )
        raw_associations = payload["associations"]
        if not isinstance(raw_associations, list):
            raise CharacterKitContractError("KIT_ASSOCIATIONS_INVALID", "associations must be an array")
        associations = tuple(
            _association_from_mapping(item, f"character_kit/associations/{index}")
            for index, item in enumerate(raw_associations)
        )
        return cls(
            contract_version,
            associations,
            _string(payload["kit_digest"], "character_kit/kit_digest"),
            placement_schema_version,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "placement_schema_version": self.placement_schema_version,
            "associations": [item.to_mapping() for item in self.associations],
            "kit_digest": self.kit_digest,
        }

    def structural_validation(self) -> CharacterKitStructuralValidationResult:
        return CharacterKitStructuralValidator().validate(self)


class CharacterKitStructuralValidator:
    """Provider-free structural validator for one CharacterKit value."""

    def validate(self, kit: CharacterKit) -> CharacterKitStructuralValidationResult:
        findings: list[CharacterKitStructuralFinding] = []
        if not isinstance(kit, CharacterKit):
            return CharacterKitStructuralValidationResult(
                "FAIL",
                True,
                (CharacterKitStructuralFinding("KIT_TYPE_INVALID", "/", "value is not a CharacterKit"),),
            )
        if kit.contract_version != CHARACTER_KIT_CONTRACT_VERSION:
            findings.append(
                CharacterKitStructuralFinding(
                    "KIT_UNSUPPORTED_CONTRACT_VERSION",
                    "/contract_version",
                    "Kit contract version is not supported",
                )
            )
        if kit.placement_schema_version != KIT_PLACEMENT_SCHEMA_VERSION:
            findings.append(
                CharacterKitStructuralFinding(
                    "KIT_UNSUPPORTED_PLACEMENT_SCHEMA_VERSION",
                    "/placement_schema_version",
                    "Kit placement schema version is not supported",
                )
            )

        canonical = _canonical_associations(kit.associations)
        if kit.associations != canonical:
            findings.append(
                CharacterKitStructuralFinding(
                    "KIT_ORDER_INVALID",
                    "/associations",
                    "associations must use authoritative placement and digest ordering",
                )
            )
        association_ids: set[str] = set()
        artifact_digests: set[str] = set()
        placement_counts: dict[SkillSlot, int] = {}
        for index, association in enumerate(kit.associations):
            path = f"/associations/{index}"
            if not isinstance(association, CharacterSkillAssociation):
                findings.append(
                    CharacterKitStructuralFinding("KIT_ASSOCIATIONS_INVALID", path, "association is invalid")
                )
                continue
            if association.association_id in association_ids:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_DUPLICATE_ASSOCIATION", f"{path}/association_id", "association identity is duplicated"
                    )
                )
            association_ids.add(association.association_id)
            if association.artifact_digest in artifact_digests:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_DUPLICATE_ARTIFACT", f"{path}/artifact_digest", "artifact identity is duplicated"
                    )
                )
            artifact_digests.add(association.artifact_digest)
            slot = getattr(association, "slot", None)
            if not isinstance(slot, SkillSlot):
                findings.append(
                    CharacterKitStructuralFinding("KIT_UNKNOWN_PLACEMENT", f"{path}/slot", "placement is not supported")
                )
                continue
            placement_counts[slot] = placement_counts.get(slot, 0) + 1
            max_items = _placement_max_items(slot)
            if max_items is not None and placement_counts[slot] > max_items:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_PLACEMENT_CARDINALITY_EXCEEDED",
                        f"{path}/slot",
                        f"placement '{slot.value}' allows at most {max_items} association",
                    )
                )
            expected_id = f"session-skill:{slot.value}:{association.artifact_digest}"
            if association.association_id != expected_id or association.order != SLOT_ORDER[slot]:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_ASSOCIATION_BINDING_INVALID",
                        path,
                        "association identity or authoritative placement order is invalid",
                    )
                )
            if association.binding.artifact_digest != association.artifact_digest:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_ASSOCIATION_BINDING_INVALID",
                        f"{path}/binding/artifact_digest",
                        "binding is not bound to association artifact",
                    )
                )
            if association.artifact.identity.artifact_digest != association.artifact_digest:
                findings.append(
                    CharacterKitStructuralFinding(
                        "KIT_ASSOCIATION_BINDING_INVALID",
                        f"{path}/artifact/identity/artifact_digest",
                        "artifact identity is not bound to artifact content",
                    )
                )

        expected_digest = compute_character_kit_digest(
            kit.associations,
            contract_version=kit.contract_version,
            placement_schema_version=kit.placement_schema_version,
        )
        if kit.kit_digest != expected_digest:
            findings.append(
                CharacterKitStructuralFinding(
                    "KIT_DIGEST_MISMATCH",
                    "/kit_digest",
                    "kit_digest does not match canonical Kit content identity",
                )
            )
        findings.sort(key=lambda item: (item.field_path, item.code, item.message))
        return CharacterKitStructuralValidationResult(
            "FAIL" if findings else "PASS",
            bool(findings),
            tuple(findings),
        )


def build_character_kit(
    associations: CharacterSkillCollection | Iterable[CharacterSkillAssociation],
    *,
    contract_version: str = CHARACTER_KIT_CONTRACT_VERSION,
) -> CharacterKit:
    """Build a canonical Kit without invoking any semantic pipeline."""

    if contract_version != CHARACTER_KIT_CONTRACT_VERSION:
        raise CharacterKitContractError("KIT_UNSUPPORTED_CONTRACT_VERSION", "Kit contract version is not supported")
    values = tuple(associations.associations if isinstance(associations, CharacterSkillCollection) else associations)
    if not all(isinstance(item, CharacterSkillAssociation) for item in values):
        raise CharacterKitContractError("KIT_ASSOCIATIONS_INVALID", "associations must contain CharacterSkillAssociation values")
    canonical = _canonical_associations(values)
    for slot in SkillSlot:
        max_items = _placement_max_items(slot)
        if max_items is not None and sum(item.slot == slot for item in canonical) > max_items:
            raise CharacterKitContractError(
                "KIT_PLACEMENT_CARDINALITY_EXCEEDED",
                f"placement '{slot.value}' allows at most {max_items} association",
            )
    if len({item.artifact_digest for item in canonical}) != len(canonical):
        raise CharacterKitContractError("KIT_DUPLICATE_ARTIFACT", "one artifact may be attached once per Kit")
    kit = CharacterKit(
        CHARACTER_KIT_CONTRACT_VERSION,
        canonical,
        compute_character_kit_digest(canonical),
    )
    result = kit.structural_validation()
    if result.status != "PASS":
        first = result.findings[0]
        raise CharacterKitContractError(first.code, first.message)
    return kit


def build_character_kit_from_association_mappings(
    associations: Iterable[Mapping[str, object]],
    *,
    contract_version: str = CHARACTER_KIT_CONTRACT_VERSION,
    placement_schema_version: str = KIT_PLACEMENT_SCHEMA_VERSION,
) -> CharacterKit:
    """Parse transported associations, then use the canonical Kit builder."""

    if placement_schema_version != KIT_PLACEMENT_SCHEMA_VERSION:
        raise CharacterKitContractError(
            "KIT_UNSUPPORTED_PLACEMENT_SCHEMA_VERSION",
            "Kit placement schema version is not supported",
        )
    parsed = tuple(
        _association_from_mapping(item, f"character_kit/associations/{index}")
        for index, item in enumerate(associations)
    )
    return build_character_kit(parsed, contract_version=contract_version)


def compute_character_kit_digest(
    associations: Iterable[CharacterSkillAssociation],
    *,
    contract_version: str = CHARACTER_KIT_CONTRACT_VERSION,
    placement_schema_version: str = KIT_PLACEMENT_SCHEMA_VERSION,
) -> str:
    """Hash only Kit-owned structural identity and ordered artifact digests."""

    canonical = _canonical_associations(tuple(associations))
    occurrence: dict[SkillSlot, int] = {}
    members: list[dict[str, object]] = []
    for association in canonical:
        index = occurrence.get(association.slot, 0)
        occurrence[association.slot] = index + 1
        members.append(
            {
                "placement": _slot_value(association.slot),
                "placement_order": association.order,
                "placement_index": index,
                "artifact_digest": association.artifact_digest,
            }
        )
    payload = {
        "contract_version": contract_version,
        "placement_schema_version": placement_schema_version,
        "associations": members,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def placement_metadata() -> tuple[dict[str, object], ...]:
    """Return the authoritative placement/cardinality projection for Web."""

    return tuple(
        {
            "id": slot.slot.value,
            "order": slot.order,
            "label": slot.label,
            "description": slot.description,
            "max_items": slot.max_items,
        }
        for slot in _placement_metadata()
    )


def _placement_metadata():
    from .character_skill_association import slot_metadata

    return slot_metadata()


def _placement_max_items(slot: SkillSlot) -> int | None:
    return next(item.max_items for item in _placement_metadata() if item.slot == slot)


def _canonical_associations(values: tuple[CharacterSkillAssociation, ...]) -> tuple[CharacterSkillAssociation, ...]:
    return tuple(sorted(values, key=lambda item: (SLOT_ORDER.get(item.slot, 999), item.artifact_digest, item.association_id)))


def _slot_value(value: object) -> str:
    return value.value if isinstance(value, SkillSlot) else str(value)


def _association_from_mapping(value: object, path: str) -> CharacterSkillAssociation:
    payload = _mapping(value, path)
    _exact_keys(
        payload,
        {"association_id", "artifact", "binding", "slot", "order", "family", "mode", "display_summary"},
        path,
    )
    try:
        slot = SkillSlot(_string(payload["slot"], f"{path}/slot"))
    except ValueError as error:
        raise CharacterKitContractError("KIT_UNKNOWN_PLACEMENT", f"{path}/slot is not supported") from error
    artifact = SkillDesignArtifact.from_mapping(payload["artifact"])
    binding_payload = _mapping(payload["binding"], f"{path}/binding")
    _exact_keys(
        binding_payload,
        {
            "binding_contract_version",
            "artifact_digest",
            "source_context_fingerprint",
            "alignment",
            "alignment_version",
            "character_context_projection_version",
        },
        f"{path}/binding",
    )
    binding = CharacterSkillArtifactBinding(
        artifact_digest=_string(binding_payload["artifact_digest"], f"{path}/binding/artifact_digest"),
        source_context_fingerprint=_string(
            binding_payload["source_context_fingerprint"], f"{path}/binding/source_context_fingerprint"
        ),
        alignment=_alignment_from_mapping(binding_payload["alignment"], f"{path}/binding/alignment"),
        alignment_version=_string(binding_payload["alignment_version"], f"{path}/binding/alignment_version"),
        character_context_projection_version=_string(
            binding_payload["character_context_projection_version"],
            f"{path}/binding/character_context_projection_version",
        ),
        binding_contract_version=_string(
            binding_payload["binding_contract_version"], f"{path}/binding/binding_contract_version"
        ),
    )
    return CharacterSkillAssociation(
        association_id=_string(payload["association_id"], f"{path}/association_id"),
        artifact=artifact,
        binding=binding,
        slot=slot,
        order=_int(payload["order"], f"{path}/order"),
        family=_string(payload["family"], f"{path}/family"),
        mode=_string(payload["mode"], f"{path}/mode"),
        display_summary=_string(payload["display_summary"], f"{path}/display_summary"),
    )


def _alignment_from_mapping(value: object, path: str) -> CharacterSkillAlignmentResult:
    payload = _mapping(value, path)
    _exact_keys(
        payload,
        {"status", "coverage", "findings", "blocking", "summary", "artifact_digest", "source_context_fingerprint", "skill_roles", "evidence"},
        path,
    )
    evidence = tuple(_evidence_from_mapping(item, f"{path}/evidence/{index}") for index, item in enumerate(_list(payload["evidence"], f"{path}/evidence")))
    findings = tuple(_finding_from_mapping(item, f"{path}/findings/{index}") for index, item in enumerate(_list(payload["findings"], f"{path}/findings")))
    return CharacterSkillAlignmentResult(
        status=_string(payload["status"], f"{path}/status"),  # type: ignore[arg-type]
        coverage=_string(payload["coverage"], f"{path}/coverage"),  # type: ignore[arg-type]
        findings=findings,
        blocking=_bool(payload["blocking"], f"{path}/blocking"),
        summary=_string(payload["summary"], f"{path}/summary"),
        artifact_digest=_optional_string(payload["artifact_digest"], f"{path}/artifact_digest"),
        source_context_fingerprint=_string(payload["source_context_fingerprint"], f"{path}/source_context_fingerprint"),
        skill_roles=tuple(_string(item, f"{path}/skill_roles") for item in _list(payload["skill_roles"], f"{path}/skill_roles")),
        evidence=evidence,
    )


def _evidence_from_mapping(value: object, path: str) -> CharacterSkillEvidence:
    payload = _mapping(value, path)
    _exact_keys(payload, {"role", "operation", "family", "mode", "artifact_paths", "centrality"}, path)
    return CharacterSkillEvidence(
        role=_string(payload["role"], f"{path}/role"),  # type: ignore[arg-type]
        operation=_string(payload["operation"], f"{path}/operation"),
        family=_string(payload["family"], f"{path}/family"),
        mode=_string(payload["mode"], f"{path}/mode"),
        artifact_paths=tuple(_string(item, f"{path}/artifact_paths") for item in _list(payload["artifact_paths"], f"{path}/artifact_paths")),
        centrality=_optional_string(payload["centrality"], f"{path}/centrality"),
    )


def _finding_from_mapping(value: object, path: str) -> CharacterSkillAlignmentFinding:
    payload = _mapping(value, path)
    _exact_keys(payload, {"code", "kind", "blocking", "character_role", "skill_evidence", "field_path", "artifact_path", "message"}, path)
    return CharacterSkillAlignmentFinding(
        code=_string(payload["code"], f"{path}/code"),
        kind=_string(payload["kind"], f"{path}/kind"),  # type: ignore[arg-type]
        blocking=_bool(payload["blocking"], f"{path}/blocking"),
        character_role=_optional_string(payload["character_role"], f"{path}/character_role"),  # type: ignore[arg-type]
        skill_evidence=tuple(_evidence_from_mapping(item, f"{path}/skill_evidence/{index}") for index, item in enumerate(_list(payload["skill_evidence"], f"{path}/skill_evidence"))),
        field_path=_string(payload["field_path"], f"{path}/field_path"),
        artifact_path=_optional_string(payload["artifact_path"], f"{path}/artifact_path"),
        message=_string(payload["message"], f"{path}/message"),
    )


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be an object")
    return dict(value)


def _exact_keys(payload: dict[str, object], expected: set[str], path: str) -> None:
    if set(payload) != expected:
        raise CharacterKitContractError("KIT_UNKNOWN_OR_MISSING_FIELD", f"{path} fields are not exact")


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be a string")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be a string or null")
    return value


def _bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be a boolean")
    return value


def _int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be an integer")
    return value


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise CharacterKitContractError("KIT_TYPE_MISMATCH", f"{path} must be an array")
    return value


__all__ = [
    "CHARACTER_KIT_CONTRACT_VERSION",
    "KIT_PLACEMENT_SCHEMA_VERSION",
    "CharacterKit",
    "CharacterKitContractError",
    "CharacterKitStructuralFinding",
    "CharacterKitStructuralValidationResult",
    "CharacterKitStructuralValidator",
    "build_character_kit",
    "build_character_kit_from_association_mappings",
    "compute_character_kit_digest",
    "placement_metadata",
]
