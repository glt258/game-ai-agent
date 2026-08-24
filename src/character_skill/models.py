"""Frozen public value objects for the Character Skill contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Literal


SCHEMA_VERSION = "skill-kit-candidate/0.1.1"


def _plain(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
        }
    if hasattr(value, "to_mapping"):
        return _plain(value.to_mapping())
    return value


@dataclass(frozen=True)
class TypedRef:
    kind: str
    id: str


@dataclass(frozen=True)
class Subject:
    kind: str
    selector: str | None
    entity_ref: TypedRef | None


@dataclass(frozen=True)
class Trigger:
    subject: Subject | None
    event: str | None
    source_ref: TypedRef | None
    qualifier: str | None


@dataclass(frozen=True)
class Effect:
    effect_id: str
    subject: Subject | None
    operation: str | None
    object_ref: TypedRef | None
    description: str


@dataclass(frozen=True)
class BehaviorProtocol:
    protocol_id: str
    when: Trigger | None
    causes: tuple[Effect, ...]


@dataclass(frozen=True)
class FeedbackRelation:
    feedback_id: str
    source_effect: TypedRef
    target_protocol: TypedRef
    event: str
    operation: str


@dataclass(frozen=True)
class AbilityEntry:
    ability_id: str
    name: str
    mode: str
    protocols: tuple[BehaviorProtocol, ...]
    display_text: str


@dataclass(frozen=True)
class ResourceLease:
    resource_id: str
    opened_by: tuple[TypedRef, ...]
    used_or_transformed_by: tuple[TypedRef, ...]
    closed_by: tuple[TypedRef, ...]


@dataclass(frozen=True)
class StateLease:
    state_id: str
    established_by: tuple[TypedRef, ...]
    active_effects: tuple[TypedRef, ...]
    ended_or_replaced_by: tuple[TypedRef, ...]


@dataclass(frozen=True)
class SummonLease:
    summon_id: str
    spawned_by: tuple[TypedRef, ...]
    active_effects: tuple[TypedRef, ...]
    departed_or_replaced_by: tuple[TypedRef, ...]
    repeat_policy: str | None


@dataclass(frozen=True)
class RoleEvidence:
    effect_refs: tuple[TypedRef, ...]
    centrality: str


@dataclass(frozen=True)
class ProtocolSkillKitCandidate:
    schema_version: str
    entries: tuple[AbilityEntry, ...]
    feedback_relations: tuple[FeedbackRelation, ...]
    resources: tuple[ResourceLease, ...]
    states: tuple[StateLease, ...]
    summons: tuple[SummonLease, ...]
    role_evidence: tuple[RoleEvidence, ...]
    display_summary: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": _plain(self.entries),
            "feedback_relations": _plain(self.feedback_relations),
            "resources": _plain(self.resources),
            "states": _plain(self.states),
            "summons": _plain(self.summons),
            "role_evidence": _plain(self.role_evidence),
            "display_summary": self.display_summary,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LegacyAbilityConcept:
    ability_concept: str

    def to_mapping(self) -> dict[str, str]:
        return {"ability_concept": self.ability_concept}

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SkillFinding:
    """One deterministic structural finding produced by the evaluator."""

    code: str
    field_path: str
    blocking: bool = True
    repairable: bool = False
    evidence_refs: tuple[str, ...] = ()
    authorized_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "authorized_paths", tuple(self.authorized_paths))

    @property
    def priority(self) -> int:
        if self.code in {
            "HARD_CONSTRAINT_CONFLICT",
            "CROSS_TAXONOMY_ROLE_LABEL",
            "REFERENCE_COPYING",
        }:
            return 0
        if self.code in {
            "MECHANIC_SKELETON_ABSENT",
            "FORBIDDEN_RESOURCE_INTRODUCED",
            "FORBIDDEN_STATE_INTRODUCED",
            "FORBIDDEN_SUMMON_INTRODUCED",
        }:
            return 1
        if self.code in {
            "LIFECYCLE_REFERENCE_DANGLING",
            "LIFECYCLE_REFERENCE_WRONG_KIND",
            "REFERENCE_KIND_MISMATCH",
            "LIFECYCLE_OPERATION_MISMATCH",
            "FEEDBACK_REFERENCE_DANGLING",
            "FEEDBACK_RELATION_INVALID",
            "REFERENCE_DANGLING",
        }:
            return 2
        if self.code in {
            "RESOURCE_LOOP_INCOMPLETE",
            "STATE_EXIT_MISSING",
            "SUMMON_LIFECYCLE_INCOMPLETE",
            "MULTI_SKILL_LOOP_INCOHERENT",
            "TRIGGER_SUBJECT_AMBIGUOUS",
            "REQUESTED_MECHANIC_UNREPRESENTED",
        }:
            return 3
        if self.code == "ROLE_EFFECT_MISMATCH":
            return 4
        if self.code == "LEGACY_SKILL_KIT_UNVERIFIED":
            return 5
        return 2

    def to_mapping(self) -> dict[str, object]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "blocking": self.blocking,
            "repairable": self.repairable,
            "evidence_refs": list(self.evidence_refs),
            "authorized_paths": list(self.authorized_paths),
            "priority": self.priority,
        }

    def to_dict(self) -> dict[str, object]:
        return self.to_mapping()


@dataclass(frozen=True)
class SkillValidationReport:
    """Digest-bound structural-only validation result."""

    outcome: Literal["PASS", "REPAIR", "FAIL"]
    blocking: bool
    repair_allowed: bool
    findings: tuple[SkillFinding, ...]
    candidate_digest: str
    context_digest: str
    report_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def base_digest(self) -> str:
        return self.candidate_digest

    @property
    def finding_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.findings)

    def to_mapping(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "blocking": self.blocking,
            "repair_allowed": self.repair_allowed,
            "findings": [item.to_mapping() for item in self.findings],
            "candidate_digest": self.candidate_digest,
            "context_digest": self.context_digest,
            "report_digest": self.report_digest,
            "base_digest": self.base_digest,
            "finding_codes": list(self.finding_codes),
        }

    def to_dict(self) -> dict[str, object]:
        return self.to_mapping()


__all__ = [
    "AbilityEntry",
    "BehaviorProtocol",
    "Effect",
    "FeedbackRelation",
    "LegacyAbilityConcept",
    "ProtocolSkillKitCandidate",
    "ResourceLease",
    "RoleEvidence",
    "SCHEMA_VERSION",
    "SkillFinding",
    "SkillValidationReport",
    "StateLease",
    "Subject",
    "SummonLease",
    "Trigger",
    "TypedRef",
]
