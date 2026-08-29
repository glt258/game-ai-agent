"""Public parser for the frozen Character Skill candidate contract."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .errors import SkillKitShapeError, build_shape_diagnostic
from .models import (
    SCHEMA_VERSION,
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    FeedbackRelation,
    LegacyAbilityConcept,
    ProtocolSkillKitCandidate,
    ResourceLease,
    RoleEvidence,
    StateLease,
    Subject,
    SummonLease,
    Trigger,
    TypedRef,
)

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
FEEDBACK_EVENTS = frozenset(
    {"effect_resolved", "resource_changed", "state_changed", "summon_changed"}
)
FEEDBACK_OPERATIONS = frozenset({"enables", "modifies", "terminates"})
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
CENTRALITIES = frozenset({"core", "secondary"})
REPEAT_POLICIES = frozenset({"replace", "refresh", "reject"})
SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "entries",
        "feedback_relations",
        "resources",
        "states",
        "summons",
        "role_evidence",
        "display_summary",
    }
)


def _join(path: str, token: str | int) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}" if path else f"/{escaped}"


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SkillKitShapeError("TYPE_MISMATCH", path or "/", "must be an object")
    return value


def _array(value: object, path: str) -> tuple[object, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or isinstance(value, Mapping)
    ):
        raise SkillKitShapeError("TYPE_MISMATCH", path, "must be an array")
    return tuple(value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise SkillKitShapeError("TYPE_MISMATCH", path, "must be a string")
    return value


def _nullable_string(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise SkillKitShapeError("TYPE_MISMATCH", path, "must be a string or null")
    return value


def _tag(value: object, allowed: frozenset[str], path: str) -> str:
    token = _string(value, path)
    if token not in allowed:
        raise SkillKitShapeError("UNSUPPORTED_VALUE", path, "unsupported closed value")
    return token


def _nullable_tag(
    value: object,
    allowed: frozenset[str],
    path: str,
) -> str | None:
    return None if value is None else _tag(value, allowed, path)


def _id(value: object, path: str, *, segments: int = 1) -> str:
    identifier = _string(value, path)
    parts = identifier.split("/")
    if len(parts) != segments or any(not SEGMENT_RE.fullmatch(part) for part in parts):
        raise SkillKitShapeError("INVALID_ID", path, "must use lower snake-case ASCII ID segments")
    return identifier


def _require_exact_keys(
    payload: Mapping[str, object],
    expected: frozenset[str],
    path: str,
) -> None:
    actual = set(payload)
    for key in sorted(actual - expected, key=str):
        raise SkillKitShapeError("UNKNOWN_FIELD", _join(path, str(key)), "field is not allowed")
    for key in sorted(expected - actual):
        raise SkillKitShapeError("MISSING_FIELD", _join(path, key), "field is required")


def _parse_ref(value: object, path: str) -> TypedRef:
    payload = _mapping(value, path)
    _require_exact_keys(payload, frozenset({"kind", "id"}), path)
    kind = _tag(payload["kind"], REF_KINDS, _join(path, "kind"))
    segments = {"protocol": 2, "effect": 3}.get(kind, 1)
    identifier = _id(payload["id"], _join(path, "id"), segments=segments)
    return TypedRef(kind, identifier)


def _parse_subject(value: object, path: str) -> Subject | None:
    if value is None:
        return None
    payload = _mapping(value, path)
    _require_exact_keys(payload, frozenset({"kind", "selector", "entity_ref"}), path)
    return Subject(
        _tag(payload["kind"], SUBJECT_KINDS, _join(path, "kind")),
        _nullable_string(payload["selector"], _join(path, "selector")),
        None
        if payload["entity_ref"] is None
        else _parse_ref(payload["entity_ref"], _join(path, "entity_ref")),
    )


def _parse_trigger(value: object, path: str) -> Trigger | None:
    if value is None:
        return None
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"subject", "event", "source_ref", "qualifier"}),
        path,
    )
    return Trigger(
        _parse_subject(payload["subject"], _join(path, "subject")),
        _nullable_tag(payload["event"], TRIGGER_EVENTS, _join(path, "event")),
        None
        if payload["source_ref"] is None
        else _parse_ref(payload["source_ref"], _join(path, "source_ref")),
        _nullable_string(payload["qualifier"], _join(path, "qualifier")),
    )


def _parse_effect(value: object, path: str) -> Effect:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"effect_id", "subject", "operation", "object_ref", "description"}),
        path,
    )
    return Effect(
        _id(payload["effect_id"], _join(path, "effect_id")),
        _parse_subject(payload["subject"], _join(path, "subject")),
        _nullable_tag(payload["operation"], EFFECT_OPERATIONS, _join(path, "operation")),
        None
        if payload["object_ref"] is None
        else _parse_ref(payload["object_ref"], _join(path, "object_ref")),
        _string(payload["description"], _join(path, "description")),
    )


def _parse_protocol(value: object, path: str) -> BehaviorProtocol:
    payload = _mapping(value, path)
    _require_exact_keys(payload, frozenset({"protocol_id", "when", "causes"}), path)
    causes = _array(payload["causes"], _join(path, "causes"))
    return BehaviorProtocol(
        _id(payload["protocol_id"], _join(path, "protocol_id")),
        _parse_trigger(payload["when"], _join(path, "when")),
        tuple(
            _parse_effect(item, _join(_join(path, "causes"), index))
            for index, item in enumerate(causes)
        ),
    )


def _parse_feedback(value: object, path: str) -> FeedbackRelation:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"feedback_id", "source_effect", "target_protocol", "event", "operation"}),
        path,
    )
    return FeedbackRelation(
        _id(payload["feedback_id"], _join(path, "feedback_id")),
        _parse_ref(payload["source_effect"], _join(path, "source_effect")),
        _parse_ref(payload["target_protocol"], _join(path, "target_protocol")),
        _tag(payload["event"], FEEDBACK_EVENTS, _join(path, "event")),
        _tag(payload["operation"], FEEDBACK_OPERATIONS, _join(path, "operation")),
    )


def _parse_ability(value: object, path: str) -> AbilityEntry:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"ability_id", "name", "mode", "protocols", "display_text"}),
        path,
    )
    protocols = _array(payload["protocols"], _join(path, "protocols"))
    return AbilityEntry(
        _id(payload["ability_id"], _join(path, "ability_id")),
        _string(payload["name"], _join(path, "name")),
        _tag(payload["mode"], ABILITY_MODES, _join(path, "mode")),
        tuple(
            _parse_protocol(item, _join(_join(path, "protocols"), index))
            for index, item in enumerate(protocols)
        ),
        _string(payload["display_text"], _join(path, "display_text")),
    )


def _parse_ref_sequence(value: object, path: str) -> tuple[TypedRef, ...]:
    values = _array(value, path)
    return tuple(_parse_ref(item, _join(path, index)) for index, item in enumerate(values))


def _parse_resource(value: object, path: str) -> ResourceLease:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"resource_id", "opened_by", "used_or_transformed_by", "closed_by"}),
        path,
    )
    return ResourceLease(
        _id(payload["resource_id"], _join(path, "resource_id")),
        _parse_ref_sequence(payload["opened_by"], _join(path, "opened_by")),
        _parse_ref_sequence(
            payload["used_or_transformed_by"],
            _join(path, "used_or_transformed_by"),
        ),
        _parse_ref_sequence(payload["closed_by"], _join(path, "closed_by")),
    )


def _parse_state(value: object, path: str) -> StateLease:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset({"state_id", "established_by", "active_effects", "ended_or_replaced_by"}),
        path,
    )
    return StateLease(
        _id(payload["state_id"], _join(path, "state_id")),
        _parse_ref_sequence(payload["established_by"], _join(path, "established_by")),
        _parse_ref_sequence(payload["active_effects"], _join(path, "active_effects")),
        _parse_ref_sequence(
            payload["ended_or_replaced_by"],
            _join(path, "ended_or_replaced_by"),
        ),
    )


def _parse_summon(value: object, path: str) -> SummonLease:
    payload = _mapping(value, path)
    _require_exact_keys(
        payload,
        frozenset(
            {
                "summon_id",
                "spawned_by",
                "active_effects",
                "departed_or_replaced_by",
                "repeat_policy",
            }
        ),
        path,
    )
    return SummonLease(
        _id(payload["summon_id"], _join(path, "summon_id")),
        _parse_ref_sequence(payload["spawned_by"], _join(path, "spawned_by")),
        _parse_ref_sequence(payload["active_effects"], _join(path, "active_effects")),
        _parse_ref_sequence(
            payload["departed_or_replaced_by"],
            _join(path, "departed_or_replaced_by"),
        ),
        _nullable_tag(payload["repeat_policy"], REPEAT_POLICIES, _join(path, "repeat_policy")),
    )


def _parse_role_evidence(value: object, path: str) -> RoleEvidence:
    payload = _mapping(value, path)
    _require_exact_keys(payload, frozenset({"effect_refs", "centrality"}), path)
    return RoleEvidence(
        _parse_ref_sequence(payload["effect_refs"], _join(path, "effect_refs")),
        _tag(payload["centrality"], CENTRALITIES, _join(path, "centrality")),
    )


def _parse_root(payload: object, path: str) -> ProtocolSkillKitCandidate:
    mapping = _mapping(payload, path)
    _require_exact_keys(mapping, _ROOT_KEYS, path)
    schema_path = _join(path, "schema_version")
    schema_version = _string(mapping["schema_version"], schema_path)
    if schema_version != SCHEMA_VERSION:
        raise SkillKitShapeError(
            "UNSUPPORTED_SCHEMA_VERSION",
            schema_path,
            f"must equal {SCHEMA_VERSION!r}",
        )
    entries = _array(mapping["entries"], _join(path, "entries"))
    feedback_relations = _array(
        mapping["feedback_relations"], _join(path, "feedback_relations")
    )
    resources = _array(mapping["resources"], _join(path, "resources"))
    states = _array(mapping["states"], _join(path, "states"))
    summons = _array(mapping["summons"], _join(path, "summons"))
    role_evidence = _array(mapping["role_evidence"], _join(path, "role_evidence"))
    candidate = ProtocolSkillKitCandidate(
        schema_version,
        tuple(
            _parse_ability(item, _join(_join(path, "entries"), index))
            for index, item in enumerate(entries)
        ),
        tuple(
            _parse_feedback(item, _join(_join(path, "feedback_relations"), index))
            for index, item in enumerate(feedback_relations)
        ),
        tuple(
            _parse_resource(item, _join(_join(path, "resources"), index))
            for index, item in enumerate(resources)
        ),
        tuple(
            _parse_state(item, _join(_join(path, "states"), index))
            for index, item in enumerate(states)
        ),
        tuple(
            _parse_summon(item, _join(_join(path, "summons"), index))
            for index, item in enumerate(summons)
        ),
        tuple(
            _parse_role_evidence(item, _join(_join(path, "role_evidence"), index))
            for index, item in enumerate(role_evidence)
        ),
        _string(mapping["display_summary"], _join(path, "display_summary")),
    )
    _validate_unique_ids(candidate, path)
    return candidate


def _validate_unique_ids(candidate: ProtocolSkillKitCandidate, path: str) -> None:
    seen_abilities: set[str] = set()
    seen_feedback: set[str] = set()
    for index, relation in enumerate(candidate.feedback_relations):
        if relation.feedback_id in seen_feedback:
            raise SkillKitShapeError(
                "DUPLICATE_ID",
                _join(_join(path, "feedback_relations"), index) + "/feedback_id",
                "feedback_id must be globally unique",
            )
        seen_feedback.add(relation.feedback_id)

    for entry_index, entry in enumerate(candidate.entries):
        entry_path = _join(_join(path, "entries"), entry_index)
        if entry.ability_id in seen_abilities:
            raise SkillKitShapeError(
                "DUPLICATE_ID",
                _join(entry_path, "ability_id"),
                "ability_id must be globally unique",
            )
        seen_abilities.add(entry.ability_id)
        seen_protocols: set[str] = set()
        for protocol_index, protocol in enumerate(entry.protocols):
            protocol_path = _join(_join(entry_path, "protocols"), protocol_index)
            if protocol.protocol_id in seen_protocols:
                raise SkillKitShapeError(
                    "DUPLICATE_ID",
                    _join(protocol_path, "protocol_id"),
                    "protocol_id must be unique within an ability",
                )
            seen_protocols.add(protocol.protocol_id)
            seen_effects: set[str] = set()
            for effect_index, effect in enumerate(protocol.causes):
                effect_path = _join(_join(protocol_path, "causes"), effect_index)
                if effect.effect_id in seen_effects:
                    raise SkillKitShapeError(
                        "DUPLICATE_ID",
                        _join(effect_path, "effect_id"),
                        "effect_id must be unique within a protocol",
                    )
                seen_effects.add(effect.effect_id)

    for kind, field in (("resource", "resources"), ("state", "states"), ("summon", "summons")):
        seen_entities: set[str] = set()
        for index, entity in enumerate(getattr(candidate, field)):
            identifier = getattr(entity, f"{kind}_id")
            if identifier in seen_entities:
                raise SkillKitShapeError(
                    "DUPLICATE_ID",
                    _join(_join(_join(path, field), index), f"{kind}_id"),
                    f"{kind}_id must be unique within its namespace",
                )
            seen_entities.add(identifier)


def parse_candidate(payload: Mapping[str, object]) -> ProtocolSkillKitCandidate | LegacyAbilityConcept:
    """Parse a strict candidate or the explicit legacy display seam."""
    try:
        if not isinstance(payload, Mapping):
            raise SkillKitShapeError("TYPE_MISMATCH", "/", "candidate must be an object")
        if "skill_kit" in payload:
            _require_exact_keys(payload, frozenset({"skill_kit"}), "")
            return _parse_root(payload["skill_kit"], "/skill_kit")
        if "ability_concept" in payload and "schema_version" not in payload:
            _require_exact_keys(payload, frozenset({"ability_concept"}), "")
            return LegacyAbilityConcept(_string(payload["ability_concept"], "/ability_concept"))
        return _parse_root(payload, "")
    except SkillKitShapeError as error:
        if error.diagnostic is None:
            error.attach_diagnostic(build_shape_diagnostic(payload, error))
        raise


__all__ = ["parse_candidate"]
