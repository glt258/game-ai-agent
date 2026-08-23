"""CS-S1.1 SkillKit protocol surface and validator-owned graph prototype.

This module is intentionally isolated under ``evals``.  It is an executable
form of ``character_skill_interface_options_v0.1.1.md`` and does not provide
production integration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import Literal

from combat_semantics.roles import CombatRoleProfile


SCHEMA_VERSION = "skill-kit-candidate/0.1.1"
VALIDATOR_CONTRACT = "skill-kit-validator/0.1.1"
REF_KINDS = frozenset({"protocol", "effect", "resource", "state", "summon"})
SUBJECT_KINDS = frozenset({"self", "ally", "team", "enemy", "scene", "summon"})
ABILITY_MODES = frozenset({"active", "passive", "reaction"})
TRIGGER_EVENTS = frozenset(
    {
        "ability_invoked",
        "action_completed",
        "damage_received",
        "healing_received",
        "resource_gained",
        "resource_spent",
        "state_entered",
        "state_exited",
        "summon_spawned",
        "summon_acted",
        "summon_departed",
        "scene_entered",
        "scene_exited",
        "feedback_received",
    }
)
FEEDBACK_EVENTS = frozenset({"effect_resolved", "resource_changed", "state_changed", "summon_changed"})
EFFECT_OPERATIONS = frozenset(
    {
        "direct_output",
        "follow_up_output",
        "ally_enablement",
        "recover_or_mitigate",
        "enemy_action_control",
        "threat_protection",
        "resource_gain",
        "resource_use",
        "resource_transform",
        "resource_clear",
        "state_enter",
        "state_apply",
        "state_exit",
        "state_replace",
        "summon_spawn",
        "summon_act",
        "summon_exit",
        "summon_replace",
        "emit_event",
    }
)
FEEDBACK_DOWNSTREAM_OPERATIONS: dict[str, frozenset[str]] = {
    "enables": frozenset(
        {
            "direct_output",
            "follow_up_output",
            "ally_enablement",
            "recover_or_mitigate",
            "enemy_action_control",
            "threat_protection",
            "resource_gain",
            "state_enter",
            "summon_spawn",
        }
    ),
    "modifies": frozenset(
        {
            "direct_output",
            "follow_up_output",
            "ally_enablement",
            "recover_or_mitigate",
            "enemy_action_control",
            "threat_protection",
            "resource_transform",
            "state_apply",
            "summon_act",
        }
    ),
    "terminates": frozenset(
        {
            "resource_clear",
            "state_exit",
            "state_replace",
            "summon_exit",
            "summon_replace",
        }
    ),
}
LIFECYCLE_OPERATION_KINDS: dict[str, str] = {
    "resource_gain": "resource",
    "resource_transform": "resource",
    "resource_clear": "resource",
    "state_enter": "state",
    "state_apply": "state",
    "state_exit": "state",
    "state_replace": "state",
    "summon_spawn": "summon",
    "summon_act": "summon",
    "summon_exit": "summon",
    "summon_replace": "summon",
}
CENTRALITIES = frozenset({"core", "secondary"})
REPEAT_POLICIES = frozenset({"replace", "refresh", "reject"})
PATCH_OPS = frozenset({"add", "replace"})
SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

RefKind = Literal["protocol", "effect", "resource", "state", "summon"]
TriggerEvent = Literal[
    "ability_invoked",
    "action_completed",
    "damage_received",
    "healing_received",
    "resource_gained",
    "resource_spent",
    "state_entered",
    "state_exited",
    "summon_spawned",
    "summon_acted",
    "summon_departed",
    "scene_entered",
    "scene_exited",
    "feedback_received",
]
FeedbackEvent = Literal["effect_resolved", "resource_changed", "state_changed", "summon_changed"]
EffectOperation = Literal[
    "direct_output",
    "follow_up_output",
    "ally_enablement",
    "recover_or_mitigate",
    "enemy_action_control",
    "threat_protection",
    "resource_gain",
    "resource_use",
    "resource_transform",
    "resource_clear",
    "state_enter",
    "state_apply",
    "state_exit",
    "state_replace",
    "summon_spawn",
    "summon_act",
    "summon_exit",
    "summon_replace",
    "emit_event",
]


class SkillKitShapeError(ValueError):
    """Raised when a provider payload violates the closed shape contract."""


class SkillKitPatchError(ValueError):
    """Raised when a patch is not authorized by a digest-bound report."""


@dataclass(frozen=True)
class TypedRef:
    kind: str
    id: str


@dataclass(frozen=True)
class Subject:
    kind: str
    selector: str | None
    entity_ref: TypedRef | None

    @property
    def ref(self) -> str | None:
        """Compatibility accessor; provider JSON uses ``entity_ref``."""

        return self.entity_ref.id if self.entity_ref is not None else None


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

    @property
    def departed_by(self) -> tuple[TypedRef, ...]:
        return self.departed_or_replaced_by


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


@dataclass(frozen=True)
class LegacyAbilityConcept:
    ability_concept: str


@dataclass(frozen=True)
class TriggerPredicate:
    subject_kinds: frozenset[str]
    events: frozenset[str]
    source_kinds: frozenset[str]


@dataclass(frozen=True)
class EffectPredicate:
    subject_kinds: frozenset[str]
    operations: frozenset[str]
    object_kinds: frozenset[str]


@dataclass(frozen=True)
class FeedbackPredicate:
    required: bool
    events: frozenset[str]
    operations: frozenset[str]


@dataclass(frozen=True)
class MechanicRequirement:
    requirement_id: str
    trigger: TriggerPredicate
    effect: EffectPredicate
    feedback: FeedbackPredicate

    @property
    def requires_feedback(self) -> bool:
        return self.feedback.required


@dataclass(frozen=True)
class SkillIntent:
    mechanic_requirements: tuple[MechanicRequirement, ...] = ()
    forbidden_mechanic_families: tuple[str, ...] = ()
    hard_constraint_conflicts: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SkillIntent":
        _require_exact_keys(
            payload,
            {"mechanic_requirements", "forbidden_mechanic_families", "hard_constraint_conflicts"},
            "intent",
        )
        requirements = tuple(
            _parse_requirement(item, f"intent.mechanic_requirements[{index}]")
            for index, item in enumerate(_array(payload["mechanic_requirements"], "intent.mechanic_requirements"))
        )
        if len({item.requirement_id for item in requirements}) != len(requirements):
            raise SkillKitShapeError("intent.mechanic_requirements must have unique requirement_id values")
        return cls(
            requirements,
            _string_sequence(payload["forbidden_mechanic_families"], "intent.forbidden_mechanic_families"),
            _string_sequence(payload["hard_constraint_conflicts"], "intent.hard_constraint_conflicts"),
        )


@dataclass(frozen=True)
class ReferenceFingerprint:
    record_id: str
    scope: str
    sha256: str


@dataclass(frozen=True)
class ReferenceReviewContext:
    corpus_version: str
    corpus_digest: str
    structural_fingerprints: tuple[ReferenceFingerprint, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ReferenceReviewContext":
        _require_exact_keys(payload, {"corpus_version", "corpus_digest", "structural_fingerprints"}, "reference_review_context")
        fingerprints: list[ReferenceFingerprint] = []
        for index, item in enumerate(_array(payload["structural_fingerprints"], "reference_review_context.structural_fingerprints")):
            row = _mapping(item, f"reference_review_context.structural_fingerprints[{index}]")
            _require_exact_keys(row, {"record_id", "scope", "sha256"}, f"reference_review_context.structural_fingerprints[{index}]")
            fingerprints.append(
                ReferenceFingerprint(
                    _id(_string(row["record_id"], "reference_fingerprint.record_id"), "reference_fingerprint.record_id", allow_path=True),
                    _tag(row["scope"], frozenset({"protocol", "connected_component"}), "reference_fingerprint.scope"),
                    _sha256(row["sha256"], "reference_fingerprint.sha256"),
                )
            )
        return cls(
            _string(payload["corpus_version"], "reference_review_context.corpus_version"),
            _sha256(payload["corpus_digest"], "reference_review_context.corpus_digest"),
            tuple(fingerprints),
        )


@dataclass(frozen=True)
class SkillValidationContext:
    intent: SkillIntent
    combat_role_profile: CombatRoleProfile | Mapping[str, object] | None
    reference_review_context: ReferenceReviewContext | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SkillValidationContext":
        _require_exact_keys(payload, {"intent", "combat_role_profile", "reference_review_context"}, "context")
        profile = payload["combat_role_profile"]
        if profile is not None and not isinstance(profile, (Mapping, CombatRoleProfile)):
            raise SkillKitShapeError("context.combat_role_profile must be a mapping, profile, or null")
        review_raw = payload["reference_review_context"]
        if review_raw is None:
            review = None
        elif isinstance(review_raw, ReferenceReviewContext):
            review = review_raw
        else:
            review = ReferenceReviewContext.from_mapping(_mapping(review_raw, "context.reference_review_context"))
        return cls(SkillIntent.from_mapping(_mapping(payload["intent"], "context.intent")), profile, review)


@dataclass(frozen=True)
class SkillFinding:
    code: str
    field_path: str
    blocking: bool = True
    repairable: bool = False
    evidence_refs: tuple[str, ...] = ()
    authorized_paths: tuple[str, ...] = ()

    @property
    def priority(self) -> int:
        if self.code in {"HARD_CONSTRAINT_CONFLICT", "CROSS_TAXONOMY_ROLE_LABEL", "REFERENCE_COPYING"}:
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

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "blocking": self.blocking,
            "repairable": self.repairable,
            "evidence_refs": list(self.evidence_refs),
            "authorized_paths": list(self.authorized_paths),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class SkillValidationReport:
    outcome: Literal["PASS", "REPAIR", "FAIL", "LEGACY_UNVERIFIED"]
    blocking: bool
    repair_allowed: bool
    findings: tuple[SkillFinding, ...]
    candidate_digest: str
    context_digest: str
    report_digest: str

    @property
    def base_digest(self) -> str:
        return self.candidate_digest

    @property
    def finding_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "blocking": self.blocking,
            "repair_allowed": self.repair_allowed,
            "findings": [item.to_dict() for item in self.findings],
            "candidate_digest": self.candidate_digest,
            "context_digest": self.context_digest,
            "report_digest": self.report_digest,
            "base_digest": self.base_digest,
        }


@dataclass(frozen=True)
class SkillKitPatch:
    candidate_digest: str
    context_digest: str
    report_digest: str
    operations: tuple[Mapping[str, object], ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "context_digest": self.context_digest,
            "report_digest": self.report_digest,
            "operations": [dict(operation) for operation in self.operations],
        }


SkillKitAssessment = SkillValidationReport


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], path: str) -> None:
    actual = set(payload)
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise SkillKitShapeError(f"{path} has unknown field(s): {sorted(unknown)}")
    if missing:
        raise SkillKitShapeError(f"{path} is missing field(s): {sorted(missing)}")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SkillKitShapeError(f"{path} must be a mapping")
    return value


def _array(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SkillKitShapeError(f"{path} must be an array")
    return tuple(value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise SkillKitShapeError(f"{path} must be a string")
    return value


def _nullable_string(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise SkillKitShapeError(f"{path} must be a string or null")
    return value


def _string_sequence(value: object, path: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{path}[{index}]") for index, item in enumerate(_array(value, path)))


def _tag(value: object, allowed: frozenset[str], path: str) -> str:
    token = _string(value, path)
    if token not in allowed:
        raise SkillKitShapeError(f"{path} has unsupported tag: {token!r}")
    return token


def _nullable_tag(value: object, allowed: frozenset[str], path: str) -> str | None:
    return None if value is None else _tag(value, allowed, path)


def _id(value: str, path: str, *, allow_path: bool = False) -> str:
    parts = value.split("/") if allow_path else [value]
    if not parts or any(not SEGMENT_RE.fullmatch(part) for part in parts):
        raise SkillKitShapeError(f"{path} must use lower snake-case ID segments")
    return value


def _sha256(value: object, path: str) -> str:
    token = _string(value, path)
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise SkillKitShapeError(f"{path} must be a lowercase SHA-256 digest")
    return token


def _parse_ref(value: object, path: str) -> TypedRef:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"kind", "id"}, path)
    kind = _tag(payload["kind"], REF_KINDS, f"{path}.kind")
    identifier = _string(payload["id"], f"{path}.id")
    parts = identifier.split("/")
    if kind == "protocol" and len(parts) != 2:
        raise SkillKitShapeError(f"{path}.id must be <ability_id>/<protocol_id>")
    if kind == "effect" and len(parts) != 3:
        raise SkillKitShapeError(f"{path}.id must be <ability_id>/<protocol_id>/<effect_id>")
    if kind in {"resource", "state", "summon"} and len(parts) != 1:
        raise SkillKitShapeError(f"{path}.id must be a kit-local entity ID")
    _id(identifier, f"{path}.id", allow_path=True)
    return TypedRef(kind, identifier)


def _parse_subject(value: object, path: str) -> Subject | None:
    if value is None:
        return None
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"kind", "selector", "entity_ref"}, path)
    return Subject(
        _tag(payload["kind"], SUBJECT_KINDS, f"{path}.kind"),
        _nullable_string(payload["selector"], f"{path}.selector"),
        None if payload["entity_ref"] is None else _parse_ref(payload["entity_ref"], f"{path}.entity_ref"),
    )


def _parse_trigger(value: object, path: str) -> Trigger | None:
    if value is None:
        return None
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"subject", "event", "source_ref", "qualifier"}, path)
    return Trigger(
        _parse_subject(payload["subject"], f"{path}.subject"),
        _nullable_tag(payload["event"], TRIGGER_EVENTS, f"{path}.event"),
        None if payload["source_ref"] is None else _parse_ref(payload["source_ref"], f"{path}.source_ref"),
        _nullable_string(payload["qualifier"], f"{path}.qualifier"),
    )


def _parse_effect(value: object, path: str) -> Effect:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"effect_id", "subject", "operation", "object_ref", "description"}, path)
    return Effect(
        _id(_string(payload["effect_id"], f"{path}.effect_id"), f"{path}.effect_id"),
        _parse_subject(payload["subject"], f"{path}.subject"),
        _nullable_tag(payload["operation"], EFFECT_OPERATIONS, f"{path}.operation"),
        None if payload["object_ref"] is None else _parse_ref(payload["object_ref"], f"{path}.object_ref"),
        _string(payload["description"], f"{path}.description"),
    )


def _parse_protocol(value: object, path: str) -> BehaviorProtocol:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"protocol_id", "when", "causes"}, path)
    causes = _array(payload["causes"], f"{path}.causes")
    return BehaviorProtocol(
        _id(_string(payload["protocol_id"], f"{path}.protocol_id"), f"{path}.protocol_id"),
        _parse_trigger(payload["when"], f"{path}.when"),
        tuple(_parse_effect(item, f"{path}.causes[{index}]") for index, item in enumerate(causes)),
    )


def _parse_feedback(value: object, path: str) -> FeedbackRelation:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"feedback_id", "source_effect", "target_protocol", "event", "operation"}, path)
    return FeedbackRelation(
        _id(_string(payload["feedback_id"], f"{path}.feedback_id"), f"{path}.feedback_id"),
        _parse_ref(payload["source_effect"], f"{path}.source_effect"),
        _parse_ref(payload["target_protocol"], f"{path}.target_protocol"),
        _tag(payload["event"], FEEDBACK_EVENTS, f"{path}.event"),
        _tag(payload["operation"], frozenset({"enables", "modifies", "terminates"}), f"{path}.operation"),
    )


def _parse_ability(value: object, path: str) -> AbilityEntry:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"ability_id", "name", "mode", "protocols", "display_text"}, path)
    protocols = _array(payload["protocols"], f"{path}.protocols")
    return AbilityEntry(
        _id(_string(payload["ability_id"], f"{path}.ability_id"), f"{path}.ability_id"),
        _string(payload["name"], f"{path}.name"),
        _tag(payload["mode"], ABILITY_MODES, f"{path}.mode"),
        tuple(_parse_protocol(item, f"{path}.protocols[{index}]") for index, item in enumerate(protocols)),
        _string(payload["display_text"], f"{path}.display_text"),
    )


def _parse_ref_sequence(value: object, path: str) -> tuple[TypedRef, ...]:
    return tuple(_parse_ref(item, f"{path}[{index}]") for index, item in enumerate(_array(value, path)))


def _parse_resource(value: object, path: str) -> ResourceLease:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"resource_id", "opened_by", "used_or_transformed_by", "closed_by"}, path)
    return ResourceLease(
        _id(_string(payload["resource_id"], f"{path}.resource_id"), f"{path}.resource_id"),
        _parse_ref_sequence(payload["opened_by"], f"{path}.opened_by"),
        _parse_ref_sequence(payload["used_or_transformed_by"], f"{path}.used_or_transformed_by"),
        _parse_ref_sequence(payload["closed_by"], f"{path}.closed_by"),
    )


def _parse_state(value: object, path: str) -> StateLease:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"state_id", "established_by", "active_effects", "ended_or_replaced_by"}, path)
    return StateLease(
        _id(_string(payload["state_id"], f"{path}.state_id"), f"{path}.state_id"),
        _parse_ref_sequence(payload["established_by"], f"{path}.established_by"),
        _parse_ref_sequence(payload["active_effects"], f"{path}.active_effects"),
        _parse_ref_sequence(payload["ended_or_replaced_by"], f"{path}.ended_or_replaced_by"),
    )


def _parse_summon(value: object, path: str) -> SummonLease:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"summon_id", "spawned_by", "active_effects", "departed_or_replaced_by", "repeat_policy"}, path)
    return SummonLease(
        _id(_string(payload["summon_id"], f"{path}.summon_id"), f"{path}.summon_id"),
        _parse_ref_sequence(payload["spawned_by"], f"{path}.spawned_by"),
        _parse_ref_sequence(payload["active_effects"], f"{path}.active_effects"),
        _parse_ref_sequence(payload["departed_or_replaced_by"], f"{path}.departed_or_replaced_by"),
        _nullable_tag(payload["repeat_policy"], REPEAT_POLICIES, f"{path}.repeat_policy"),
    )


def _parse_role_evidence(value: object, path: str) -> RoleEvidence:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"effect_refs", "centrality"}, path)
    return RoleEvidence(
        _parse_ref_sequence(payload["effect_refs"], f"{path}.effect_refs"),
        _tag(payload["centrality"], CENTRALITIES, f"{path}.centrality"),
    )


def _parse_set(value: object, allowed: frozenset[str], path: str, *, nonempty: bool = False) -> frozenset[str]:
    values = frozenset(_tag(item, allowed, f"{path}[{index}]") for index, item in enumerate(_array(value, path)))
    if nonempty and not values:
        raise SkillKitShapeError(f"{path} must not be empty")
    return values


def _parse_requirement(value: object, path: str) -> MechanicRequirement:
    payload = _mapping(value, path)
    _require_exact_keys(payload, {"requirement_id", "trigger", "effect", "feedback"}, path)
    requirement_id = _id(_string(payload["requirement_id"], f"{path}.requirement_id"), f"{path}.requirement_id")
    trigger_raw = _mapping(payload["trigger"], f"{path}.trigger")
    _require_exact_keys(trigger_raw, {"subject_kinds", "events", "source_kinds"}, f"{path}.trigger")
    trigger = TriggerPredicate(
        _parse_set(trigger_raw["subject_kinds"], SUBJECT_KINDS, f"{path}.trigger.subject_kinds", nonempty=True),
        _parse_set(trigger_raw["events"], TRIGGER_EVENTS, f"{path}.trigger.events", nonempty=True),
        _parse_set(trigger_raw["source_kinds"], REF_KINDS, f"{path}.trigger.source_kinds"),
    )
    effect_raw = _mapping(payload["effect"], f"{path}.effect")
    _require_exact_keys(effect_raw, {"subject_kinds", "operations", "object_kinds"}, f"{path}.effect")
    effect = EffectPredicate(
        _parse_set(effect_raw["subject_kinds"], SUBJECT_KINDS, f"{path}.effect.subject_kinds", nonempty=True),
        _parse_set(effect_raw["operations"], EFFECT_OPERATIONS, f"{path}.effect.operations", nonempty=True),
        _parse_set(effect_raw["object_kinds"], REF_KINDS, f"{path}.effect.object_kinds"),
    )
    feedback_raw = _mapping(payload["feedback"], f"{path}.feedback")
    _require_exact_keys(feedback_raw, {"required", "events", "operations"}, f"{path}.feedback")
    required = feedback_raw["required"]
    if not isinstance(required, bool):
        raise SkillKitShapeError(f"{path}.feedback.required must be boolean")
    feedback = FeedbackPredicate(
        required,
        _parse_set(feedback_raw["events"], FEEDBACK_EVENTS, f"{path}.feedback.events", nonempty=required),
        _parse_set(feedback_raw["operations"], frozenset({"enables", "modifies", "terminates"}), f"{path}.feedback.operations", nonempty=required),
    )
    return MechanicRequirement(requirement_id, trigger, effect, feedback)


def parse_candidate(payload: Mapping[str, object]) -> ProtocolSkillKitCandidate | LegacyAbilityConcept:
    """Parse a strict provider candidate or the explicit legacy display seam."""

    payload = _mapping(payload, "candidate")
    if "skill_kit" in payload:
        _require_exact_keys(payload, {"skill_kit"}, "legacy_payload")
        payload = _mapping(payload["skill_kit"], "legacy_payload.skill_kit")
    elif "ability_concept" in payload and "schema_version" not in payload:
        _require_exact_keys(payload, {"ability_concept"}, "legacy_payload")
        return LegacyAbilityConcept(_string(payload["ability_concept"], "legacy_payload.ability_concept"))
    _require_exact_keys(
        payload,
        {"schema_version", "entries", "feedback_relations", "resources", "states", "summons", "role_evidence", "display_summary"},
        "candidate",
    )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise SkillKitShapeError(f"candidate.schema_version must be {SCHEMA_VERSION!r}")
    candidate = ProtocolSkillKitCandidate(
        SCHEMA_VERSION,
        tuple(_parse_ability(item, f"candidate.entries[{index}]") for index, item in enumerate(_array(payload["entries"], "candidate.entries"))),
        tuple(_parse_feedback(item, f"candidate.feedback_relations[{index}]") for index, item in enumerate(_array(payload["feedback_relations"], "candidate.feedback_relations"))),
        tuple(_parse_resource(item, f"candidate.resources[{index}]") for index, item in enumerate(_array(payload["resources"], "candidate.resources"))),
        tuple(_parse_state(item, f"candidate.states[{index}]") for index, item in enumerate(_array(payload["states"], "candidate.states"))),
        tuple(_parse_summon(item, f"candidate.summons[{index}]") for index, item in enumerate(_array(payload["summons"], "candidate.summons"))),
        tuple(_parse_role_evidence(item, f"candidate.role_evidence[{index}]") for index, item in enumerate(_array(payload["role_evidence"], "candidate.role_evidence"))),
        _string(payload["display_summary"], "candidate.display_summary"),
    )
    _validate_unique_ids(candidate)
    return candidate


def _validate_unique_ids(candidate: ProtocolSkillKitCandidate) -> None:
    seen: set[tuple[str, str]] = set()

    def add(kind: str, identifier: str) -> None:
        key = (kind, identifier)
        if key in seen:
            raise SkillKitShapeError(f"duplicate {kind} ID {identifier!r}")
        seen.add(key)

    ability_ids: set[str] = set()
    feedback_ids: set[str] = set()
    for relation in candidate.feedback_relations:
        if relation.feedback_id in feedback_ids:
            raise SkillKitShapeError(f"duplicate feedback ID {relation.feedback_id!r}")
        feedback_ids.add(relation.feedback_id)
    for entry in candidate.entries:
        if entry.ability_id in ability_ids:
            raise SkillKitShapeError(f"duplicate ability ID {entry.ability_id!r}")
        ability_ids.add(entry.ability_id)
        protocol_ids: set[str] = set()
        for protocol in entry.protocols:
            if protocol.protocol_id in protocol_ids:
                raise SkillKitShapeError(f"duplicate protocol ID {protocol.protocol_id!r} in {entry.ability_id!r}")
            protocol_ids.add(protocol.protocol_id)
            add("protocol", f"{entry.ability_id}/{protocol.protocol_id}")
            effect_ids: set[str] = set()
            for effect in protocol.causes:
                if effect.effect_id in effect_ids:
                    raise SkillKitShapeError(f"duplicate effect ID {effect.effect_id!r} in {protocol.protocol_id!r}")
                effect_ids.add(effect.effect_id)
                add("effect", f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}")
    for kind, leases in (("resource", candidate.resources), ("state", candidate.states), ("summon", candidate.summons)):
        for lease in leases:
            add(kind, getattr(lease, f"{kind}_id"))


def _plain(value: object) -> object:
    if isinstance(value, CombatRoleProfile):
        return value.to_dict()
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_digest(candidate: ProtocolSkillKitCandidate | LegacyAbilityConcept) -> str:
    return hashlib.sha256(_canonical_json(candidate).encode("utf-8")).hexdigest()


def _coerce_context(context: SkillValidationContext | Mapping[str, object]) -> SkillValidationContext:
    if isinstance(context, SkillValidationContext):
        return context
    if isinstance(context, Mapping):
        return SkillValidationContext.from_mapping(context)
    raise TypeError("context must be a SkillValidationContext or mapping")


def _context_plain(context: SkillValidationContext) -> dict[str, object]:
    return {
        "intent": _plain(context.intent),
        "combat_role_profile": _plain(context.combat_role_profile),
        "reference_review_context": _plain(context.reference_review_context),
        "validator_contract": VALIDATOR_CONTRACT,
    }


def _context_digest(context: SkillValidationContext) -> str:
    return hashlib.sha256(_canonical_json(_context_plain(context)).encode("utf-8")).hexdigest()


def _report_digest(candidate_digest: str, context_digest: str, findings: Sequence[SkillFinding], outcome: str) -> str:
    payload = {
        "candidate_digest": candidate_digest,
        "context_digest": context_digest,
        "findings": [item.to_dict() for item in findings],
        "outcome": outcome,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _EffectLocation:
    entry: AbilityEntry
    protocol: BehaviorProtocol
    effect: Effect
    effect_ref: TypedRef
    protocol_ref: TypedRef


def _indexes(candidate: ProtocolSkillKitCandidate) -> tuple[dict[str, BehaviorProtocol], dict[str, _EffectLocation], dict[str, object]]:
    protocols: dict[str, BehaviorProtocol] = {}
    effects: dict[str, _EffectLocation] = {}
    leases: dict[str, object] = {}
    for entry in candidate.entries:
        for protocol in entry.protocols:
            protocol_id = f"{entry.ability_id}/{protocol.protocol_id}"
            protocols[protocol_id] = protocol
            protocol_ref = TypedRef("protocol", protocol_id)
            for effect in protocol.causes:
                effect_id = f"{protocol_id}/{effect.effect_id}"
                effects[effect_id] = _EffectLocation(entry, protocol, effect, TypedRef("effect", effect_id), protocol_ref)
    for lease in candidate.resources:
        leases[f"resource/{lease.resource_id}"] = lease
    for lease in candidate.states:
        leases[f"state/{lease.state_id}"] = lease
    for lease in candidate.summons:
        leases[f"summon/{lease.summon_id}"] = lease
    return protocols, effects, leases


def _resolve_ref(ref: TypedRef, protocols: Mapping[str, BehaviorProtocol], effects: Mapping[str, _EffectLocation], leases: Mapping[str, object]) -> object | None:
    if ref.kind == "protocol":
        return protocols.get(ref.id)
    if ref.kind == "effect":
        return effects.get(ref.id)
    return leases.get(f"{ref.kind}/{ref.id}")


def _ref_exists_in_other_namespace(
    ref: TypedRef,
    protocols: Mapping[str, BehaviorProtocol],
    effects: Mapping[str, _EffectLocation],
    leases: Mapping[str, object],
) -> bool:
    return any(
        _resolve_ref(TypedRef(kind, ref.id), protocols, effects, leases) is not None
        for kind in REF_KINDS
        if kind != ref.kind
    )


def _finding(
    code: str,
    path: str,
    *,
    repairable: bool,
    blocking: bool = True,
    evidence_refs: Sequence[str] = (),
    authorized_paths: Sequence[str] = (),
) -> SkillFinding:
    return SkillFinding(code, path, blocking, repairable, tuple(evidence_refs), tuple(authorized_paths))


def _dedupe_sort(findings: Sequence[SkillFinding]) -> tuple[SkillFinding, ...]:
    unique: dict[tuple[str, str, tuple[str, ...]], SkillFinding] = {}
    for item in findings:
        unique.setdefault((item.code, item.field_path, tuple(sorted(item.evidence_refs))), item)
    return tuple(sorted(unique.values(), key=lambda item: (item.priority, item.code, item.field_path, tuple(sorted(item.evidence_refs)))))


def _all_protocols(candidate: ProtocolSkillKitCandidate) -> list[tuple[int, int, AbilityEntry, BehaviorProtocol]]:
    return [
        (entry_index, protocol_index, entry, protocol)
        for entry_index, entry in enumerate(candidate.entries)
        for protocol_index, protocol in enumerate(entry.protocols)
    ]


ROLE_ROWS: dict[str, dict[str, object]] = {
    "main_dps": {"duty": "direct_output", "subjects": {"enemy"}, "triggers": {("self", "ability_invoked")}},
    "sub_dps": {"duty": "follow_up_output", "subjects": {"enemy"}, "triggers": {("ally", "action_completed"), ("team", "action_completed")}},
    "support": {"duty": "ally_enablement", "subjects": {"ally", "team"}, "triggers": {("self", "ability_invoked"), ("ally", "action_completed"), ("team", "action_completed")}},
    "healer": {"duty": "recover_or_mitigate", "subjects": {"ally", "team"}, "triggers": {("self", "ability_invoked"), ("ally", "damage_received"), ("team", "damage_received")}},
    "control": {"duty": "enemy_action_control", "subjects": {"enemy"}, "triggers": {("self", "ability_invoked"), ("ally", "action_completed"), ("summon", "summon_acted"), ("scene", "scene_entered")}},
    "defense": {"duty": "threat_protection", "subjects": {"ally", "team"}, "triggers": {("self", "ability_invoked"), ("ally", "damage_received"), ("team", "damage_received")}},
}


def _profile_or_finding(profile: CombatRoleProfile | Mapping[str, object] | None) -> tuple[CombatRoleProfile | None, SkillFinding | None]:
    if profile is None:
        return None, None
    if isinstance(profile, CombatRoleProfile):
        return profile, None
    try:
        # CI-B1.5 is deliberately fail-closed: no legacy flat alias normalizer.
        return CombatRoleProfile.from_mapping(profile), None
    except (TypeError, ValueError):
        return None, _finding("CROSS_TAXONOMY_ROLE_LABEL", "context.combat_role_profile", repairable=False)


def _validate_general_refs(candidate: ProtocolSkillKitCandidate, protocols: Mapping[str, BehaviorProtocol], effects: Mapping[str, _EffectLocation], leases: Mapping[str, object], findings: list[SkillFinding]) -> None:
    for entry_index, protocol_index, _, protocol in _all_protocols(candidate):
        base = f"/entries/{entry_index}/protocols/{protocol_index}"
        if protocol.when is not None:
            if protocol.when.source_ref is not None:
                ref = protocol.when.source_ref
                if ref.kind != "effect":
                    findings.append(_finding("REFERENCE_KIND_MISMATCH", f"{base}/when/source_ref", repairable=False, evidence_refs=(ref.id,)))
                elif ref.id not in effects:
                    findings.append(_finding("REFERENCE_DANGLING", f"{base}/when/source_ref", repairable=False, evidence_refs=(ref.id,)))
            if protocol.when.subject is not None:
                subject = protocol.when.subject
                subject_path = f"{base}/when/subject/entity_ref"
                ref = subject.entity_ref
                if subject.kind == "summon" and ref is None:
                    findings.append(_finding("REFERENCE_DANGLING", subject_path, repairable=False))
                elif ref is not None:
                    if subject.kind != "summon":
                        findings.append(_finding("REFERENCE_KIND_MISMATCH", subject_path, repairable=False, evidence_refs=(ref.id,)))
                    elif ref.kind != "summon":
                        findings.append(_finding("REFERENCE_KIND_MISMATCH", subject_path, repairable=False, evidence_refs=(ref.id,)))
                    elif f"summon/{ref.id}" not in leases:
                        code = "REFERENCE_KIND_MISMATCH" if _ref_exists_in_other_namespace(ref, protocols, effects, leases) else "REFERENCE_DANGLING"
                        findings.append(_finding(code, subject_path, repairable=False, evidence_refs=(ref.id,)))
        for effect_index, effect in enumerate(protocol.causes):
            if effect.object_ref is not None and _resolve_ref(effect.object_ref, protocols, effects, leases) is None:
                code = "REFERENCE_KIND_MISMATCH" if _ref_exists_in_other_namespace(effect.object_ref, protocols, effects, leases) else "REFERENCE_DANGLING"
                findings.append(_finding(code, f"{base}/causes/{effect_index}/object_ref", repairable=False, evidence_refs=(effect.object_ref.id,)))
            if effect.subject is not None:
                subject = effect.subject
                subject_path = f"{base}/causes/{effect_index}/subject/entity_ref"
                ref = subject.entity_ref
                if subject.kind == "summon" and ref is None:
                    findings.append(_finding("REFERENCE_DANGLING", subject_path, repairable=False))
                elif ref is not None:
                    if subject.kind != "summon":
                        findings.append(_finding("REFERENCE_KIND_MISMATCH", subject_path, repairable=False, evidence_refs=(ref.id,)))
                    elif ref.kind != "summon":
                        findings.append(_finding("REFERENCE_KIND_MISMATCH", subject_path, repairable=False, evidence_refs=(ref.id,)))
                    elif f"summon/{ref.id}" not in leases:
                        code = "REFERENCE_KIND_MISMATCH" if _ref_exists_in_other_namespace(ref, protocols, effects, leases) else "REFERENCE_DANGLING"
                        findings.append(_finding(code, subject_path, repairable=False, evidence_refs=(ref.id,)))


def _lifecycle_slot(
    lease_kind: str,
    lease_index: int,
    slot: str,
    refs: Sequence[TypedRef],
    allowed_operations: frozenset[str],
    entity_id: str,
    effects: Mapping[str, _EffectLocation],
    findings: list[SkillFinding],
) -> list[TypedRef]:
    valid: list[TypedRef] = []
    for ref_index, ref in enumerate(refs):
        path = f"/{lease_kind}s/{lease_index}/{slot}/{ref_index}"
        if ref.kind != "effect":
            findings.append(_finding("LIFECYCLE_REFERENCE_WRONG_KIND", path, repairable=False, evidence_refs=(ref.id,)))
            continue
        location = effects.get(ref.id)
        if location is None:
            findings.append(_finding("LIFECYCLE_REFERENCE_DANGLING", path, repairable=False, evidence_refs=(ref.id,)))
            continue
        effect = location.effect
        if effect.operation not in allowed_operations or effect.object_ref != TypedRef(lease_kind, entity_id):
            findings.append(_finding("LIFECYCLE_OPERATION_MISMATCH", path, repairable=False, evidence_refs=(ref.id,)))
            continue
        valid.append(ref)
    return valid


def _lifecycle_findings(candidate: ProtocolSkillKitCandidate, effects: Mapping[str, _EffectLocation], findings: list[SkillFinding]) -> None:
    for index, lease in enumerate(candidate.resources):
        opened = _lifecycle_slot("resource", index, "opened_by", lease.opened_by, frozenset({"resource_gain"}), lease.resource_id, effects, findings)
        used = _lifecycle_slot("resource", index, "used_or_transformed_by", lease.used_or_transformed_by, frozenset({"resource_use", "resource_transform"}), lease.resource_id, effects, findings)
        closed = _lifecycle_slot("resource", index, "closed_by", lease.closed_by, frozenset({"resource_clear", "resource_transform"}), lease.resource_id, effects, findings)
        if not (opened and used and closed):
            targeted_abilities = {
                location.entry.ability_id
                for location in effects.values()
                if location.effect.object_ref == TypedRef("resource", lease.resource_id)
            }
            code = "MULTI_SKILL_LOOP_INCOHERENT" if len(targeted_abilities) >= 2 else "RESOURCE_LOOP_INCOMPLETE"
            findings.append(_finding(code, f"/resources/{index}", repairable=True, authorized_paths=(f"/resources/{index}/opened_by/-", f"/resources/{index}/used_or_transformed_by/-", f"/resources/{index}/closed_by/-")))
    for index, lease in enumerate(candidate.states):
        established = _lifecycle_slot("state", index, "established_by", lease.established_by, frozenset({"state_enter"}), lease.state_id, effects, findings)
        active = _lifecycle_slot("state", index, "active_effects", lease.active_effects, frozenset({"state_apply"}), lease.state_id, effects, findings)
        ended = _lifecycle_slot("state", index, "ended_or_replaced_by", lease.ended_or_replaced_by, frozenset({"state_exit", "state_replace"}), lease.state_id, effects, findings)
        if established and active and not ended:
            findings.append(_finding("STATE_EXIT_MISSING", f"/states/{index}/ended_or_replaced_by", repairable=True, authorized_paths=(f"/states/{index}/ended_or_replaced_by/-",)))
    for index, lease in enumerate(candidate.summons):
        spawned = _lifecycle_slot("summon", index, "spawned_by", lease.spawned_by, frozenset({"summon_spawn"}), lease.summon_id, effects, findings)
        active = _lifecycle_slot("summon", index, "active_effects", lease.active_effects, frozenset({"summon_act"}), lease.summon_id, effects, findings)
        departed = _lifecycle_slot("summon", index, "departed_or_replaced_by", lease.departed_or_replaced_by, frozenset({"summon_exit", "summon_replace"}), lease.summon_id, effects, findings)
        has_replace = any(effects.get(ref.id) is not None and effects[ref.id].effect.operation == "summon_replace" for ref in departed)
        if spawned and active and (not departed or (lease.repeat_policy is None and not has_replace)):
            findings.append(_finding("SUMMON_LIFECYCLE_INCOMPLETE", f"/summons/{index}", repairable=True, authorized_paths=(f"/summons/{index}/departed_or_replaced_by/-", f"/summons/{index}/repeat_policy")))


def _role_findings(candidate: ProtocolSkillKitCandidate, profile: CombatRoleProfile | None, effects: Mapping[str, _EffectLocation], findings: list[SkillFinding]) -> None:
    if profile is None:
        return
    requested: list[tuple[str, str]] = []
    if profile.primary_role is not None:
        requested.append((profile.primary_role, "core"))
    requested.extend((role, "secondary") for role in profile.secondary_roles)
    for role, centrality in requested:
        row = ROLE_ROWS.get(role)
        if row is None:
            continue
        valid = False
        for evidence in candidate.role_evidence:
            if evidence.centrality != centrality:
                continue
            for ref in evidence.effect_refs:
                location = effects.get(ref.id) if ref.kind == "effect" else None
                if location is None:
                    continue
                trigger = location.protocol.when
                pair = (trigger.subject.kind, trigger.event) if trigger is not None and trigger.subject is not None else (None, None)
                effect = location.effect
                if effect.operation == row["duty"] and effect.subject is not None and effect.subject.kind in row["subjects"] and pair in row["triggers"]:
                    valid = True
                    break
            if valid:
                break
        if not valid:
            findings.append(_finding("ROLE_EFFECT_MISMATCH", "/role_evidence", repairable=False))


def _skeletons(candidate: ProtocolSkillKitCandidate, requirement: MechanicRequirement, protocols: Mapping[str, BehaviorProtocol], effects: Mapping[str, _EffectLocation], leases: Mapping[str, object]) -> list[tuple[BehaviorProtocol, _EffectLocation]]:
    matches: list[tuple[BehaviorProtocol, _EffectLocation]] = []
    for _, _, entry, protocol in _all_protocols(candidate):
        trigger = protocol.when
        if trigger is None or trigger.subject is None or trigger.subject.kind not in requirement.trigger.subject_kinds or trigger.event not in requirement.trigger.events:
            continue
        if requirement.trigger.source_kinds:
            source = trigger.source_ref
            if source is None or source.kind not in requirement.trigger.source_kinds or _resolve_ref(source, protocols, effects, leases) is None:
                continue
        for effect in protocol.causes:
            if effect.subject is None or effect.subject.kind not in requirement.effect.subject_kinds or effect.operation not in requirement.effect.operations:
                continue
            if requirement.effect.object_kinds:
                object_ref = effect.object_ref
                if object_ref is None or object_ref.kind not in requirement.effect.object_kinds or _resolve_ref(object_ref, protocols, effects, leases) is None:
                    continue
            location = effects.get(f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}")
            if location is not None:
                matches.append((protocol, location))
    return matches


def _feedback_downstream_valid(effect: Effect, relation: FeedbackRelation, leases: Mapping[str, object]) -> bool:
    if effect.subject is None:
        return False
    if effect.operation not in FEEDBACK_DOWNSTREAM_OPERATIONS.get(relation.operation, frozenset()):
        return False
    expected_kind = LIFECYCLE_OPERATION_KINDS.get(effect.operation or "")
    if expected_kind is not None:
        object_ref = effect.object_ref
        if object_ref is None or object_ref.kind != expected_kind or f"{expected_kind}/{object_ref.id}" not in leases:
            return False
    return True


def _feedback_attached_to_skeleton(
    relation: FeedbackRelation,
    source: _EffectLocation,
    protocols: Mapping[str, BehaviorProtocol],
    requirement: MechanicRequirement | None,
) -> bool:
    if relation.source_effect.kind != "effect" or relation.source_effect != source.effect_ref:
        return False
    if relation.target_protocol.kind != "protocol":
        return False
    target = protocols.get(relation.target_protocol.id)
    if target is None or relation.target_protocol.id == source.protocol_ref.id:
        return False
    if target.when is None or target.when.event != "feedback_received" or target.when.source_ref != relation.source_effect:
        return False
    if requirement is not None and (relation.event not in requirement.feedback.events or relation.operation not in requirement.feedback.operations):
        return False
    source_subject = source.effect.subject
    target_subject = target.when.subject
    if source_subject is None or target_subject is None or source_subject.kind != target_subject.kind:
        return False
    if source_subject.kind == "summon" and source_subject.entity_ref != target_subject.entity_ref:
        return False
    return True


def _feedback_valid_for(
    relation: FeedbackRelation,
    source: _EffectLocation,
    protocols: Mapping[str, BehaviorProtocol],
    effects: Mapping[str, _EffectLocation],
    leases: Mapping[str, object],
    requirement: MechanicRequirement | None,
) -> bool:
    if not _feedback_attached_to_skeleton(relation, source, protocols, requirement):
        return False
    target = protocols[relation.target_protocol.id]
    return any(_feedback_downstream_valid(effect, relation, leases) for effect in target.causes)


def _feedback_authorized_paths(
    candidate: ProtocolSkillKitCandidate,
    rows: Sequence[tuple[BehaviorProtocol, _EffectLocation]],
    requirement: MechanicRequirement,
    leases: Mapping[str, object],
) -> tuple[str, ...]:
    paths = {"/feedback_relations/-"}
    requested_operations = tuple(requirement.feedback.operations)
    requested_event = next(iter(requirement.feedback.events), "effect_resolved")
    for _, source in rows:
        source_subject = source.effect.subject
        for entry_index, protocol_index, entry, target in _all_protocols(candidate):
            target_id = f"{entry.ability_id}/{target.protocol_id}"
            if target_id == source.protocol_ref.id or target.when is None:
                continue
            if target.when.event != "feedback_received" or target.when.source_ref != source.effect_ref:
                continue
            target_subject = target.when.subject
            if source_subject is None or target_subject is None or source_subject.kind != target_subject.kind:
                continue
            if source_subject.kind == "summon" and source_subject.entity_ref != target_subject.entity_ref:
                continue
            has_compatible_cause = any(
                _feedback_downstream_valid(
                    effect,
                    FeedbackRelation(
                        "authorized",
                        source.effect_ref,
                        TypedRef("protocol", target_id),
                        requested_event,
                        operation,
                    ),
                    leases,
                )
                for operation in requested_operations
                for effect in target.causes
            )
            if not has_compatible_cause:
                paths.add(f"/entries/{entry_index}/protocols/{protocol_index}/causes/-")
    return tuple(sorted(paths))


def _mechanic_findings(candidate: ProtocolSkillKitCandidate, context: SkillValidationContext, effects: Mapping[str, _EffectLocation], leases: Mapping[str, object], protocols: Mapping[str, BehaviorProtocol], findings: list[SkillFinding]) -> dict[str, list[tuple[BehaviorProtocol, _EffectLocation]]]:
    matched: dict[str, list[tuple[BehaviorProtocol, _EffectLocation]]] = {}
    for requirement in context.intent.mechanic_requirements:
        rows = _skeletons(candidate, requirement, protocols, effects, leases)
        matched[requirement.requirement_id] = rows
        if not rows:
            findings.append(_finding("MECHANIC_SKELETON_ABSENT", "/entries", repairable=False))
            continue
        if requirement.feedback.required:
            valid_feedback = any(
                _feedback_valid_for(relation, source, protocols, effects, leases, requirement)
                for relation in candidate.feedback_relations
                for _, source in rows
            )
            locally_attached_feedback = any(
                _feedback_attached_to_skeleton(relation, source, protocols, requirement)
                for relation in candidate.feedback_relations
                for _, source in rows
            )
            if not valid_feedback and not locally_attached_feedback:
                findings.append(
                    _finding(
                        "REQUESTED_MECHANIC_UNREPRESENTED",
                        "/feedback_relations/-",
                        repairable=True,
                        authorized_paths=_feedback_authorized_paths(candidate, rows, requirement, leases),
                    )
                )
    return matched


def _feedback_findings(
    candidate: ProtocolSkillKitCandidate,
    matched: Mapping[str, list[tuple[BehaviorProtocol, _EffectLocation]]],
    requirements: Sequence[MechanicRequirement],
    protocols: Mapping[str, BehaviorProtocol],
    effects: Mapping[str, _EffectLocation],
    leases: Mapping[str, object],
    findings: list[SkillFinding],
) -> None:
    requirements_by_id = {requirement.requirement_id: requirement for requirement in requirements}
    for index, relation in enumerate(candidate.feedback_relations):
        path = f"/feedback_relations/{index}"
        if relation.source_effect.kind != "effect" or relation.target_protocol.kind != "protocol" or relation.source_effect.id not in effects or relation.target_protocol.id not in protocols:
            findings.append(_finding("FEEDBACK_REFERENCE_DANGLING", path, repairable=False, evidence_refs=(relation.source_effect.id, relation.target_protocol.id)))
            continue
        valid = any(
            _feedback_valid_for(relation, source, protocols, effects, leases, requirements_by_id[requirement_id])
            for requirement_id, rows in matched.items()
            if requirement_id in requirements_by_id
            for _, source in rows
        )
        if not valid:
            locally_repairable = any(
                _feedback_attached_to_skeleton(relation, source, protocols, requirements_by_id[requirement_id])
                and protocols[relation.target_protocol.id].causes == ()
                for requirement_id, rows in matched.items()
                if requirement_id in requirements_by_id
                for _, source in rows
            )
            findings.append(
                _finding(
                    "FEEDBACK_RELATION_INVALID",
                    path,
                    repairable=locally_repairable,
                    evidence_refs=(relation.source_effect.id, relation.target_protocol.id),
                )
            )


def _graph_payload(candidate: ProtocolSkillKitCandidate) -> tuple[dict[str, dict[str, object]], list[tuple[str, str, str]]]:
    protocols, effects, leases = _indexes(candidate)
    role_centralities: dict[str, list[str]] = {}
    for evidence in candidate.role_evidence:
        for ref in evidence.effect_refs:
            if ref.kind == "effect":
                role_centralities.setdefault(ref.id, []).append(evidence.centrality)

    nodes: dict[str, dict[str, object]] = {}
    edges: list[tuple[str, str, str]] = []
    for pid, protocol in protocols.items():
        trigger_subject = protocol.when.subject.kind if protocol.when is not None and protocol.when.subject is not None else None
        trigger_event = protocol.when.event if protocol.when is not None else None
        nodes[f"p:{pid}"] = {"kind": "protocol", "tags": [trigger_subject, trigger_event]}
        for effect in protocol.causes:
            eid = f"{pid}/{effect.effect_id}"
            nodes[f"e:{eid}"] = {
                "kind": "effect",
                "tags": [
                    effect.operation,
                    effect.subject.kind if effect.subject else None,
                    effect.object_ref.kind if effect.object_ref else None,
                    sorted(role_centralities.get(eid, [])),
                ],
            }
            edges.append((f"p:{pid}", "causes", f"e:{eid}"))
            if effect.object_ref is not None and effect.object_ref.kind in {"resource", "state", "summon"}:
                lease_key = f"{effect.object_ref.kind}/{effect.object_ref.id}"
                if lease_key in leases:
                    edges.append((f"e:{eid}", "targets", f"l:{lease_key}"))

    for kind, leases_seq in (("resource", candidate.resources), ("state", candidate.states), ("summon", candidate.summons)):
        for lease in leases_seq:
            lease_id = getattr(lease, f"{kind}_id")
            tags: list[object] = [lease.repeat_policy] if kind == "summon" else []
            nodes[f"l:{kind}/{lease_id}"] = {"kind": kind, "tags": tags}

    for relation in candidate.feedback_relations:
        source_node = f"e:{relation.source_effect.id}"
        target_node = f"p:{relation.target_protocol.id}"
        if source_node in nodes and target_node in nodes:
            edges.append((source_node, f"feedback:{relation.event}:{relation.operation}", target_node))

    lifecycle_slots = {
        "resource": {"opened_by": "opened_by", "used_or_transformed_by": "used_or_transformed_by", "closed_by": "closed_by"},
        "state": {"established_by": "established_by", "active_effects": "active_effects", "ended_or_replaced_by": "ended_or_replaced_by"},
        "summon": {"spawned_by": "spawned_by", "active_effects": "active_effects", "departed_or_replaced_by": "departed_or_replaced_by"},
    }
    for kind, leases_seq in (("resource", candidate.resources), ("state", candidate.states), ("summon", candidate.summons)):
        for lease in leases_seq:
            lease_node = f"l:{kind}/{getattr(lease, f'{kind}_id')}"
            for slot, label in lifecycle_slots[kind].items():
                for ref in getattr(lease, slot):
                    effect_node = f"e:{ref.id}"
                    if effect_node in nodes:
                        edges.append((lease_node, label, effect_node))
    return nodes, edges


def _induced_graph(
    nodes: Mapping[str, dict[str, object]],
    edges: Sequence[tuple[str, str, str]],
    keep: set[str],
) -> tuple[dict[str, dict[str, object]], list[tuple[str, str, str]]]:
    return (
        {node: value for node, value in nodes.items() if node in keep},
        [edge for edge in edges if edge[0] in keep and edge[2] in keep],
    )


def _weak_components(nodes: Mapping[str, dict[str, object]], edges: Sequence[tuple[str, str, str]]) -> list[set[str]]:
    adjacent: dict[str, set[str]] = {node: set() for node in nodes}
    for source, _, target in edges:
        adjacent.setdefault(source, set()).add(target)
        adjacent.setdefault(target, set()).add(source)
    components: list[set[str]] = []
    unseen = set(nodes)
    while unseen:
        start = min(unseen)
        component: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node not in unseen:
                continue
            unseen.remove(node)
            component.add(node)
            stack.extend(adjacent[node] & unseen)
        components.append(component)
    return components


def _fingerprint_graph(nodes: Mapping[str, dict[str, object]], edges: Sequence[tuple[str, str, str]]) -> str:
    colors = {
        node: hashlib.sha256(
            _canonical_json({"kind": value["kind"], "tags": value["tags"]}).encode("utf-8")
        ).hexdigest()
        for node, value in nodes.items()
    }
    for _ in range(max(1, len(nodes))):
        next_colors: dict[str, str] = {}
        for node, value in nodes.items():
            incoming = sorted([[label, colors[source]] for source, label, target in edges if target == node])
            outgoing = sorted([[label, colors[target]] for source, label, target in edges if source == node])
            next_colors[node] = hashlib.sha256(
                _canonical_json(
                    {
                        "kind": value["kind"],
                        "tags": value["tags"],
                        "incoming": incoming,
                        "outgoing": outgoing,
                    }
                ).encode("utf-8")
            ).hexdigest()
        colors = next_colors
    canonical_nodes = sorted([[value["kind"], colors[node]] for node, value in nodes.items()])
    canonical_edges = sorted([[colors[source], label, colors[target]] for source, label, target in edges])
    return hashlib.sha256(_canonical_json({"nodes": canonical_nodes, "edges": canonical_edges}).encode("utf-8")).hexdigest()


def _scoped_graphs(candidate: ProtocolSkillKitCandidate, scope: str, protocol_id: str | None = None) -> list[tuple[dict[str, dict[str, object]], list[tuple[str, str, str]]]]:
    nodes, edges = _graph_payload(candidate)
    if scope == "protocol":
        if protocol_id is None:
            return []
        protocol_node = f"p:{protocol_id}"
        keep = {protocol_node}
        keep.update(dst for source, label, dst in edges if source == protocol_node and label == "causes")
        keep.update(dst for source, label, dst in edges if source in keep and label == "targets")
        return [_induced_graph(nodes, edges, keep)]
    if scope == "connected_component":
        return [_induced_graph(nodes, edges, component) for component in _weak_components(nodes, edges)]
    raise ValueError(f"unsupported fingerprint scope: {scope}")


def _structural_fingerprint(candidate: ProtocolSkillKitCandidate, scope: str, protocol_id: str | None = None) -> str:
    graphs = _scoped_graphs(candidate, scope, protocol_id)
    if not graphs:
        return _fingerprint_graph({}, [])
    return _fingerprint_graph(*graphs[0])


def _reference_copying(candidate: ProtocolSkillKitCandidate, context: SkillValidationContext, findings: list[SkillFinding]) -> None:
    review = context.reference_review_context
    if review is None:
        return
    expected = {
        "protocol": {item.sha256 for item in review.structural_fingerprints if item.scope == "protocol"},
        "connected_component": {item.sha256 for item in review.structural_fingerprints if item.scope == "connected_component"},
    }
    protocol_match = any(
        _structural_fingerprint(candidate, "protocol", f"{entry.ability_id}/{protocol.protocol_id}") in expected["protocol"]
        for entry in candidate.entries
        for protocol in entry.protocols
    )
    component_match = any(
        _fingerprint_graph(*graph) in expected["connected_component"]
        for graph in _scoped_graphs(candidate, "connected_component")
    )
    if protocol_match or component_match:
        findings.append(_finding("REFERENCE_COPYING", "/context/reference_review_context", repairable=False))


def _candidate_mechanic_families(candidate: ProtocolSkillKitCandidate) -> frozenset[str]:
    families: set[str] = set()
    if candidate.resources or any(
        effect.operation is not None and effect.operation.startswith("resource_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("resource")
    if candidate.states or any(
        effect.operation is not None and effect.operation.startswith("state_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("state")
    if candidate.summons or any(
        effect.operation is not None and effect.operation.startswith("summon_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("summon")
    return frozenset(families)


def evaluate(candidate: ProtocolSkillKitCandidate | LegacyAbilityConcept, context: SkillValidationContext | Mapping[str, object]) -> SkillValidationReport:
    """Evaluate a parsed candidate and accumulate all independently provable findings."""

    context = _coerce_context(context)
    if isinstance(candidate, LegacyAbilityConcept):
        context_findings: list[SkillFinding] = []
        _, profile_finding = _profile_or_finding(context.combat_role_profile)
        if profile_finding is not None:
            context_findings.append(profile_finding)
        if context.intent.hard_constraint_conflicts:
            context_findings.append(_finding("HARD_CONSTRAINT_CONFLICT", "/context/intent/hard_constraint_conflicts", repairable=False))
        context_findings.append(_finding("LEGACY_SKILL_KIT_UNVERIFIED", "/ability_concept", repairable=False, blocking=False))
        findings = _dedupe_sort(context_findings)
        outcome: Literal["FAIL", "LEGACY_UNVERIFIED"] = "FAIL" if any(not item.repairable for item in findings if item.code != "LEGACY_SKILL_KIT_UNVERIFIED") else "LEGACY_UNVERIFIED"
        candidate_digest = _candidate_digest(candidate)
        context_digest = _context_digest(context)
        return SkillValidationReport(outcome, outcome == "FAIL", False, findings, candidate_digest, context_digest, _report_digest(candidate_digest, context_digest, findings, outcome))
    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("evaluate expects a ProtocolSkillKitCandidate or LegacyAbilityConcept")

    findings: list[SkillFinding] = []
    profile, profile_finding = _profile_or_finding(context.combat_role_profile)
    if profile_finding is not None:
        findings.append(profile_finding)
    if context.intent.hard_constraint_conflicts:
        findings.append(_finding("HARD_CONSTRAINT_CONFLICT", "/context/intent/hard_constraint_conflicts", repairable=False))
    candidate_families = _candidate_mechanic_families(candidate)
    forbidden_finding_paths = {
        "resource": "/resources",
        "state": "/states",
        "summon": "/summons",
    }
    for family in sorted(set(context.intent.forbidden_mechanic_families) & candidate_families & set(forbidden_finding_paths)):
        findings.append(_finding(f"FORBIDDEN_{family.upper()}_INTRODUCED", forbidden_finding_paths[family], repairable=False))

    protocols, effects, leases = _indexes(candidate)
    _validate_general_refs(candidate, protocols, effects, leases, findings)
    _lifecycle_findings(candidate, effects, findings)
    matched = _mechanic_findings(candidate, context, effects, leases, protocols, findings)
    _feedback_findings(candidate, matched, context.intent.mechanic_requirements, protocols, effects, leases, findings)
    for entry_index, protocol_index, _, protocol in _all_protocols(candidate):
        if protocol.when is not None and protocol.when.subject is not None and protocol.when.subject.kind in {"ally", "team"}:
            if not protocol.when.subject.selector or protocol.when.event is None:
                findings.append(_finding("TRIGGER_SUBJECT_AMBIGUOUS", f"/entries/{entry_index}/protocols/{protocol_index}/when", repairable=True, authorized_paths=(f"/entries/{entry_index}/protocols/{protocol_index}/when",)))
    _role_findings(candidate, profile, effects, findings)
    _reference_copying(candidate, context, findings)

    ordered = _dedupe_sort(findings)
    if any(not item.repairable for item in ordered):
        outcome: Literal["PASS", "REPAIR", "FAIL", "LEGACY_UNVERIFIED"] = "FAIL"
    elif ordered:
        outcome = "REPAIR"
    else:
        outcome = "PASS"
    candidate_digest = _candidate_digest(candidate)
    context_digest = _context_digest(context)
    return SkillValidationReport(outcome, outcome != "PASS", outcome == "REPAIR", ordered, candidate_digest, context_digest, _report_digest(candidate_digest, context_digest, ordered, outcome))


def _json_pointer_parts(path: str) -> list[str]:
    if not path.startswith("/"):
        raise SkillKitPatchError("patch path must be an RFC 6901 JSON Pointer")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def _apply_pointer(document: object, path: str, op: str, value: object) -> None:
    parts = _json_pointer_parts(path)
    if not parts:
        raise SkillKitPatchError("root replacement is not authorized")
    cursor = document
    for part in parts[:-1]:
        if isinstance(cursor, list):
            try:
                cursor = cursor[int(part)]
            except (ValueError, IndexError):
                raise SkillKitPatchError(f"patch path does not resolve: {path}") from None
        elif isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            raise SkillKitPatchError(f"patch path does not resolve: {path}")
    leaf = parts[-1]
    if isinstance(cursor, list):
        if op == "add" and leaf == "-":
            cursor.append(copy.deepcopy(value))
        elif op == "replace" and leaf.isdigit() and int(leaf) < len(cursor):
            cursor[int(leaf)] = copy.deepcopy(value)
        else:
            raise SkillKitPatchError(f"patch list operation is not authorized: {path}")
    elif isinstance(cursor, dict):
        if op == "replace" and leaf in cursor:
            cursor[leaf] = copy.deepcopy(value)
        else:
            raise SkillKitPatchError(f"patch mapping operation is not authorized: {path}")
    else:
        raise SkillKitPatchError(f"patch path does not resolve: {path}")


def apply_patch(candidate: ProtocolSkillKitCandidate, patch: Mapping[str, object] | SkillKitPatch, report: SkillValidationReport, context: SkillValidationContext | Mapping[str, object]) -> SkillValidationReport:
    """Apply an atomic ``add``/``replace`` operation on report-authorized paths."""

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("apply_patch expects a ProtocolSkillKitCandidate")
    if not isinstance(report, SkillValidationReport):
        raise TypeError("apply_patch expects a SkillValidationReport")
    context = _coerce_context(context)
    candidate_digest = _candidate_digest(candidate)
    context_digest = _context_digest(context)
    if report.candidate_digest != candidate_digest:
        raise SkillKitPatchError("candidate_digest does not match candidate")
    if report.context_digest != context_digest:
        raise SkillKitPatchError("context_digest does not match context")
    if report.report_digest != _report_digest(report.candidate_digest, report.context_digest, report.findings, report.outcome):
        raise SkillKitPatchError("report_digest does not match report contents")
    if report.outcome != "REPAIR" or not report.repair_allowed or any(not item.repairable for item in report.findings):
        raise SkillKitPatchError("only an all-repairable report can authorize a patch")
    if isinstance(patch, SkillKitPatch):
        patch = patch.to_mapping()
    payload = _mapping(patch, "patch")
    _require_exact_keys(payload, {"candidate_digest", "context_digest", "report_digest", "operations"}, "patch")
    if payload["candidate_digest"] != candidate_digest or payload["context_digest"] != context_digest or payload["report_digest"] != report.report_digest:
        raise SkillKitPatchError("patch digest binding does not match candidate, context, and report")
    operations = _array(payload["operations"], "patch.operations")
    authorized = {path for finding in report.findings for path in finding.authorized_paths}
    if not authorized:
        raise SkillKitPatchError("report contains no authorized patch path")
    document = _plain(candidate)
    for index, raw_operation in enumerate(operations):
        operation = _mapping(raw_operation, f"patch.operations[{index}]")
        _require_exact_keys(operation, {"op", "path", "value"}, f"patch.operations[{index}]")
        op = _tag(operation["op"], PATCH_OPS, f"patch.operations[{index}].op")
        path = _string(operation["path"], f"patch.operations[{index}].path")
        if path not in authorized:
            raise SkillKitPatchError(f"patch path is not authorized by report: {path}")
        _apply_pointer(document, path, op, operation["value"])
    patched = parse_candidate(document)
    if not isinstance(patched, ProtocolSkillKitCandidate):
        raise SkillKitPatchError("patch produced a legacy payload")
    result = evaluate(patched, context)
    original_keys = {(item.code, item.field_path) for item in report.findings}
    result_keys = {(item.code, item.field_path) for item in result.findings}
    if not result_keys.issubset(original_keys):
        raise SkillKitPatchError("patch introduced a new finding")
    if result_keys & original_keys:
        raise SkillKitPatchError("patch did not remove all targeted findings")
    rank = {"LEGACY_UNVERIFIED": -1, "FAIL": 0, "REPAIR": 1, "PASS": 2}
    if rank[result.outcome] <= rank[report.outcome]:
        raise SkillKitPatchError("patch outcome did not strictly improve")
    return result


def render_ability_concept(candidate: ProtocolSkillKitCandidate | LegacyAbilityConcept) -> str:
    """Render a deterministic one-way compatibility summary."""

    if isinstance(candidate, LegacyAbilityConcept):
        return candidate.ability_concept
    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("render_ability_concept expects a SkillKit candidate")
    parts: list[str] = []
    if candidate.display_summary.strip():
        parts.append(candidate.display_summary.strip())
    for entry in sorted(candidate.entries, key=lambda item: item.ability_id):
        clauses: list[str] = []
        for protocol in sorted(entry.protocols, key=lambda item: item.protocol_id):
            trigger = "unspecified trigger"
            if protocol.when is not None:
                subject = protocol.when.subject
                if subject is not None:
                    selector = f"/{subject.selector}" if subject.selector else ""
                    trigger = f"{subject.kind}{selector} {protocol.when.event or 'event'}".strip()
                elif protocol.when.event:
                    trigger = protocol.when.event
            operations = ", ".join(sorted(effect.operation or "unspecified effect" for effect in protocol.causes)) or "no effects"
            clauses.append(f"{trigger} -> {operations}")
        parts.append(f"{entry.name or entry.ability_id}: {'; '.join(clauses) if clauses else 'no protocols'}")
    return " ".join(parts) if parts else "SkillKit concept: no ability entries declared."


__all__ = [
    "AbilityEntry",
    "BehaviorProtocol",
    "Effect",
    "EffectPredicate",
    "FeedbackPredicate",
    "FeedbackRelation",
    "LegacyAbilityConcept",
    "MechanicRequirement",
    "ProtocolSkillKitCandidate",
    "ReferenceFingerprint",
    "ReferenceReviewContext",
    "ResourceLease",
    "RoleEvidence",
    "SkillFinding",
    "SkillIntent",
    "SkillKitAssessment",
    "SkillKitPatch",
    "SkillKitPatchError",
    "SkillKitShapeError",
    "SkillValidationContext",
    "SkillValidationReport",
    "StateLease",
    "Subject",
    "SummonLease",
    "Trigger",
    "TriggerPredicate",
    "TypedRef",
    "RefKind",
    "TriggerEvent",
    "FeedbackEvent",
    "EffectOperation",
    "apply_patch",
    "CandidateShapeError",
    "PatchRejected",
    "evaluate",
    "parse_candidate",
    "render_ability_concept",
]


# Compatibility names retained for the first contract-test slice.
CandidateShapeError = SkillKitShapeError
PatchRejected = SkillKitPatchError
