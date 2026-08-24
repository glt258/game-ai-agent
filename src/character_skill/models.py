"""Frozen public value objects for the Character Skill contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from typing import Any


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
    "StateLease",
    "Subject",
    "SummonLease",
    "Trigger",
    "TypedRef",
]
