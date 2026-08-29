"""Immutable request/context values used by structural SkillKit evaluation.

The context parser is deliberately request-owned and fail-closed.  The
evaluation report produced in this commit is structural-only; later reviewed
commits may consume the same context for mechanic, role, or reference checks.
The production shadow evaluator supplies this context explicitly; provider
adapters never receive it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any

from .errors import SkillKitShapeError


VALIDATOR_CONTRACT = "skill-kit-validator/0.1.1"

_REF_KINDS = frozenset({"protocol", "effect", "resource", "state", "summon"})
_SUBJECT_KINDS = frozenset({"self", "ally", "team", "enemy", "scene", "summon"})
_TRIGGER_EVENTS = frozenset(
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
_FEEDBACK_EVENTS = frozenset(
    {"effect_resolved", "resource_changed", "state_changed", "summon_changed"}
)
_FEEDBACK_OPERATIONS = frozenset({"enables", "modifies", "terminates"})
_EFFECT_OPERATIONS = frozenset(
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
_MECHANIC_KINDS = frozenset({"triggered", "passive"})
# Generic semantic families used to constrain a continuation without pinning
# the model to one exact response operation or wording.
RESPONSE_EFFECT_FAMILIES = frozenset({"damage", "control", "support", "recovery"})
_SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _plain(value: object) -> object:
    """Convert frozen values to the canonical JSON-compatible representation."""

    # These fields were added after the original validator contract.  Omit
    # their empty defaults so legacy contexts retain byte-identical digests;
    # populated requirements serialize the new generic validity constraints.
    if isinstance(value, MechanicRequirement):
        payload = {
            "requirement_id": value.requirement_id,
            **({"mechanic_kind": value.mechanic_kind} if value.mechanic_kind != "triggered" else {}),
            "trigger": _plain(value.trigger),
            "effect": _plain(value.effect),
            "feedback": _plain(value.feedback),
        }
        if value.allowed_modes:
            payload["allowed_modes"] = sorted(value.allowed_modes)
        if value.allowed_response_effect_families:
            payload["allowed_response_effect_families"] = sorted(
                value.allowed_response_effect_families
            )
        return payload
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    return value


def _fail(code: str, path: str, detail: str) -> None:
    raise SkillKitShapeError(code, path or "/", detail)


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail("TYPE_MISMATCH", path, "must be an object")
    return value


def _array(value: object, path: str) -> tuple[object, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or isinstance(value, Mapping)
    ):
        _fail("TYPE_MISMATCH", path, "must be an array")
    return tuple(value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        _fail("TYPE_MISMATCH", path, "must be a string")
    return value


def _tag(value: object, allowed: frozenset[str], path: str) -> str:
    token = _string(value, path)
    if token not in allowed:
        _fail("UNSUPPORTED_VALUE", path, "unsupported closed value")
    return token


def _id(value: object, path: str, *, allow_path: bool = False) -> str:
    token = _string(value, path)
    parts = token.split("/") if allow_path else [token]
    if not parts or any(not _SEGMENT_RE.fullmatch(part) for part in parts):
        _fail("INVALID_ID", path, "must use lower snake-case ASCII ID segments")
    return token


def _sha256(value: object, path: str) -> str:
    token = _string(value, path)
    if not _SHA256_RE.fullmatch(token):
        _fail("INVALID_DIGEST", path, "must be a lowercase SHA-256 digest")
    return token


def _require_exact_keys(
    payload: Mapping[str, object], expected: frozenset[str], path: str
) -> None:
    actual = set(payload)
    unknown = sorted(actual - expected, key=str)
    if unknown:
        _fail("UNKNOWN_FIELD", f"{path}/{unknown[0]}" if path else f"/{unknown[0]}", "field is not allowed")
    missing = sorted(expected - actual)
    if missing:
        _fail("MISSING_FIELD", f"{path}/{missing[0]}" if path else f"/{missing[0]}", "field is required")


def _string_sequence(value: object, path: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{path}/{index}") for index, item in enumerate(_array(value, path)))


def _tag_set(
    value: object,
    allowed: frozenset[str],
    path: str,
    *,
    nonempty: bool = False,
) -> frozenset[str]:
    values = frozenset(
        _tag(item, allowed, f"{path}/{index}")
        for index, item in enumerate(_array(value, path))
    )
    if nonempty and not values:
        _fail("UNSUPPORTED_VALUE", path, "must not be empty")
    return values


def _freeze(value: Any) -> Any:
    """Copy arbitrary profile mappings into immutable nested values."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _freeze_profile(value: object, path: str) -> Mapping[str, object]:
    """Snapshot a canonical profile without importing or normalizing its taxonomy."""

    if isinstance(value, Mapping):
        return _freeze(_mapping_value(value, path))
    if is_dataclass(value):
        return _freeze(_plain(value))  # type: ignore[return-value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _freeze(_mapping_value(to_dict(), path))
    _fail("TYPE_MISMATCH", path, "must be a mapping, profile, or null")


def _mapping_value(value: object, path: str) -> Mapping[str, object]:
    payload = _mapping(value, path)
    if any(not isinstance(key, str) for key in payload):
        _fail("TYPE_MISMATCH", path, "mapping keys must be strings")
    return payload


@dataclass(frozen=True)
class TriggerPredicate:
    subject_kinds: frozenset[str]
    events: frozenset[str]
    source_kinds: frozenset[str]

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class EffectPredicate:
    subject_kinds: frozenset[str]
    operations: frozenset[str]
    object_kinds: frozenset[str]

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class FeedbackPredicate:
    required: bool
    events: frozenset[str]
    operations: frozenset[str]

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class MechanicRequirement:
    requirement_id: str
    trigger: TriggerPredicate | None
    effect: EffectPredicate
    feedback: FeedbackPredicate
    mechanic_kind: str = "triggered"
    allowed_modes: frozenset[str] = frozenset()
    allowed_response_effect_families: frozenset[str] = frozenset()

    @property
    def requires_feedback(self) -> bool:
        return self.feedback.required

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "MechanicRequirement":
        payload = _mapping_value(value, path)
        mechanic_kind = payload.get("mechanic_kind", "triggered")
        if mechanic_kind not in _MECHANIC_KINDS:
            _fail("UNSUPPORTED_VALUE", f"{path}/mechanic_kind", "unsupported mechanic kind")
        required_keys = frozenset({"requirement_id", "effect", "feedback"})
        if mechanic_kind == "triggered":
            required_keys = required_keys | {"trigger"}
        optional_keys = frozenset({"allowed_modes", "allowed_response_effect_families"})
        _require_exact_keys(
            payload,
            required_keys
            | ({"mechanic_kind"} if "mechanic_kind" in payload else set())
            | (set(payload) & optional_keys),
            path,
        )
        allowed_keys = required_keys | optional_keys | (
            {"mechanic_kind"} if "mechanic_kind" in payload else set()
        )
        unknown = sorted(set(payload) - allowed_keys)
        if unknown:
            _fail("UNKNOWN_FIELD", f"{path}/{unknown[0]}", "field is not allowed")
        requirement_id = _id(payload["requirement_id"], f"{path}/requirement_id")

        if mechanic_kind == "triggered":
            trigger_payload = _mapping_value(payload["trigger"], f"{path}/trigger")
            _require_exact_keys(trigger_payload, frozenset({"subject_kinds", "events", "source_kinds"}), f"{path}/trigger")
            trigger = TriggerPredicate(
                _tag_set(trigger_payload["subject_kinds"], _SUBJECT_KINDS, f"{path}/trigger/subject_kinds", nonempty=True),
                _tag_set(trigger_payload["events"], _TRIGGER_EVENTS, f"{path}/trigger/events", nonempty=True),
                _tag_set(trigger_payload["source_kinds"], _REF_KINDS, f"{path}/trigger/source_kinds"),
            )
        else:
            trigger = None

        effect_payload = _mapping_value(payload["effect"], f"{path}/effect")
        _require_exact_keys(effect_payload, frozenset({"subject_kinds", "operations", "object_kinds"}), f"{path}/effect")
        effect = EffectPredicate(
            _tag_set(effect_payload["subject_kinds"], _SUBJECT_KINDS, f"{path}/effect/subject_kinds", nonempty=True),
            _tag_set(effect_payload["operations"], _EFFECT_OPERATIONS, f"{path}/effect/operations", nonempty=True),
            _tag_set(effect_payload["object_kinds"], _REF_KINDS, f"{path}/effect/object_kinds"),
        )

        feedback_payload = _mapping_value(payload["feedback"], f"{path}/feedback")
        _require_exact_keys(feedback_payload, frozenset({"required", "events", "operations"}), f"{path}/feedback")
        required = feedback_payload["required"]
        if not isinstance(required, bool):
            _fail("TYPE_MISMATCH", f"{path}/feedback/required", "must be a boolean")
        feedback = FeedbackPredicate(
            required,
            _tag_set(feedback_payload["events"], _FEEDBACK_EVENTS, f"{path}/feedback/events", nonempty=required),
            _tag_set(feedback_payload["operations"], _FEEDBACK_OPERATIONS, f"{path}/feedback/operations", nonempty=required),
        )
        allowed_modes = _tag_set(
            payload.get("allowed_modes", ()),
            frozenset({"active", "passive", "reaction"}),
            f"{path}/allowed_modes",
        )
        allowed_families = _tag_set(
            payload.get("allowed_response_effect_families", ()),
            RESPONSE_EFFECT_FAMILIES,
            f"{path}/allowed_response_effect_families",
        )
        if mechanic_kind == "passive" and feedback.required:
            _fail("IR_INVALID", f"{path}/feedback/required", "passive requirements cannot require feedback")
        return cls(requirement_id, trigger, effect, feedback, mechanic_kind, allowed_modes, allowed_families)


@dataclass(frozen=True)
class SkillIntent:
    mechanic_requirements: tuple[MechanicRequirement, ...] = ()
    forbidden_mechanic_families: tuple[str, ...] = ()
    hard_constraint_conflicts: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SkillIntent":
        payload = _mapping_value(payload, "/intent")
        _require_exact_keys(
            payload,
            frozenset(
                {"mechanic_requirements", "forbidden_mechanic_families", "hard_constraint_conflicts"}
            ),
            "/intent",
        )
        requirements = tuple(
            MechanicRequirement.from_mapping(item, f"/intent/mechanic_requirements/{index}")
            for index, item in enumerate(_array(payload["mechanic_requirements"], "/intent/mechanic_requirements"))
        )
        seen: set[str] = set()
        for index, requirement in enumerate(requirements):
            if requirement.requirement_id in seen:
                _fail(
                    "DUPLICATE_ID",
                    f"/intent/mechanic_requirements/{index}/requirement_id",
                    "requirement_id must be unique",
                )
            seen.add(requirement.requirement_id)
        return cls(
            requirements,
            _string_sequence(payload["forbidden_mechanic_families"], "/intent/forbidden_mechanic_families"),
            _string_sequence(payload["hard_constraint_conflicts"], "/intent/hard_constraint_conflicts"),
        )

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ReferenceFingerprint:
    record_id: str
    scope: str
    sha256: str

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ReferenceReviewContext:
    corpus_version: str
    corpus_digest: str
    structural_fingerprints: tuple[ReferenceFingerprint, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ReferenceReviewContext":
        payload = _mapping_value(payload, "/reference_review_context")
        _require_exact_keys(payload, frozenset({"corpus_version", "corpus_digest", "structural_fingerprints"}), "/reference_review_context")
        fingerprints: list[ReferenceFingerprint] = []
        for index, item in enumerate(_array(payload["structural_fingerprints"], "/reference_review_context/structural_fingerprints")):
            path = f"/reference_review_context/structural_fingerprints/{index}"
            row = _mapping_value(item, path)
            _require_exact_keys(row, frozenset({"record_id", "scope", "sha256"}), path)
            scope = _tag(row["scope"], frozenset({"protocol", "connected_component"}), f"{path}/scope")
            fingerprints.append(
                ReferenceFingerprint(
                    _id(row["record_id"], f"{path}/record_id", allow_path=True),
                    scope,
                    _sha256(row["sha256"], f"{path}/sha256"),
                )
            )
        return cls(
            _string(payload["corpus_version"], "/reference_review_context/corpus_version"),
            _sha256(payload["corpus_digest"], "/reference_review_context/corpus_digest"),
            tuple(fingerprints),
        )

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class SkillValidationContext:
    intent: SkillIntent
    combat_role_profile: Mapping[str, object] | object | None = None
    reference_review_context: ReferenceReviewContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, SkillIntent):
            raise TypeError("intent must be a SkillIntent")
        profile = self.combat_role_profile
        if profile is not None:
            object.__setattr__(self, "combat_role_profile", _freeze_profile(profile, "/context/combat_role_profile"))
        if self.reference_review_context is not None and not isinstance(
            self.reference_review_context, ReferenceReviewContext
        ):
            raise TypeError("reference_review_context must be a ReferenceReviewContext or None")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SkillValidationContext":
        payload = _mapping_value(payload, "/context")
        _require_exact_keys(
            payload,
            frozenset({"intent", "combat_role_profile", "reference_review_context"}),
            "/context",
        )
        profile_raw = payload["combat_role_profile"]
        if profile_raw is not None:
            profile = _freeze_profile(profile_raw, "/context/combat_role_profile")
        else:
            profile = None
        review_raw = payload["reference_review_context"]
        if review_raw is None:
            review = None
        elif isinstance(review_raw, ReferenceReviewContext):
            review = review_raw
        else:
            review = ReferenceReviewContext.from_mapping(
                _mapping_value(review_raw, "/context/reference_review_context")
            )
        return cls(
            SkillIntent.from_mapping(_mapping_value(payload["intent"], "/context/intent")),
            profile,
            review,
        )

    def to_mapping(self) -> dict[str, object]:
        return _plain(self)  # type: ignore[return-value]

    def canonical_json(self) -> str:
        payload = dict(self.to_mapping())
        payload["validator_contract"] = VALIDATOR_CONTRACT
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        """Return the single canonical digest for this validation context."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


__all__ = [
    "EffectPredicate",
    "FeedbackPredicate",
    "MechanicRequirement",
    "ReferenceFingerprint",
    "ReferenceReviewContext",
    "RESPONSE_EFFECT_FAMILIES",
    "SkillIntent",
    "SkillValidationContext",
    "TriggerPredicate",
    "VALIDATOR_CONTRACT",
]
