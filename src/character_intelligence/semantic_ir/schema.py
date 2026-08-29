"""Mechanically-light semantic SkillKit planning values.

The semantic IR deliberately describes gameplay intent instead of reproducing
the canonical SkillKit wire format.  It has no canonical IDs, typed
references, root schema literal, or lifecycle arrays.  Parsing is strict and
the validator in :mod:`.validator` owns semantic acceptance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from character_skill.contract import (
    ABILITY_MODES,
    CENTRALITIES,
    FEEDBACK_EVENTS,
    FEEDBACK_OPERATIONS,
    SUBJECT_KINDS,
    TRIGGER_EVENTS,
)

SEMANTIC_IR_VERSION = "semantic-skill-plan-ir/0.1.0"
SEMANTIC_IR_V2_VERSION = "semantic-skill-plan-ir/0.2.0"

# This is intentionally a semantic vocabulary, not a second copy of the
# canonical effect-operation enum.  The compiler owns the explicit mapping.
SEMANTIC_EFFECT_INTENTS = frozenset(
    {
        "enable_ally",
        "deal_damage",
        "control_enemy",
        "mitigate_ally",
    }
)
SEMANTIC_EFFECT_INTENTS_V2 = SEMANTIC_EFFECT_INTENTS | frozenset(
    {
        "deal_follow_up_damage",
        "protect_ally",
    }
)


class SemanticIRShapeError(ValueError):
    """A strict IR parsing failure with a stable safe code and path."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SemanticIRShapeError("IR_INVALID", path, "must be an object")
    if any(not isinstance(key, str) for key in value):
        raise SemanticIRShapeError("IR_INVALID", path, "object keys must be strings")
    return value


def _require_keys(payload: Mapping[str, object], expected: set[str], path: str) -> None:
    unknown = sorted(set(payload) - expected)
    if unknown:
        raise SemanticIRShapeError("UNKNOWN_FIELD", f"{path}/{unknown[0]}", "field is not allowed")
    missing = sorted(expected - set(payload))
    if missing:
        raise SemanticIRShapeError("MISSING_FIELD", f"{path}/{missing[0]}", "field is required")


def _string(payload: Mapping[str, object], key: str, path: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise SemanticIRShapeError("IR_INVALID", f"{path}/{key}", "must be a string")
    return value


def _discriminator(payload: Mapping[str, object], path: str) -> str:
    """Read a variant discriminator without exposing a raw mapping KeyError."""

    if "kind" not in payload:
        raise SemanticIRShapeError("MISSING_FIELD", f"{path}/kind", "field is required")
    return _string(payload, "kind", path)


def _nullable_string(payload: Mapping[str, object], key: str, path: str) -> str | None:
    value = payload[key]
    if value is not None and not isinstance(value, str):
        raise SemanticIRShapeError("IR_INVALID", f"{path}/{key}", "must be a string or null")
    return value


@dataclass(frozen=True)
class SemanticTrigger:
    """A semantic trigger; ``actor`` is not a canonical reference."""

    actor: str
    event: str
    qualifier: str | None = None

    def to_mapping(self) -> dict[str, object]:
        return {
            "actor": self.actor,
            "event": self.event,
            "qualifier": self.qualifier,
        }

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "SemanticTrigger":
        payload = _require_mapping(value, path)
        _require_keys(payload, {"actor", "event", "qualifier"}, path)
        return cls(
            _string(payload, "actor", path),
            _string(payload, "event", path),
            _nullable_string(payload, "qualifier", path),
        )


@dataclass(frozen=True)
class SemanticEffect:
    """A semantic effect intent without operation IDs or typed references."""

    actor: str
    intent: str
    description: str = ""

    def to_mapping(self) -> dict[str, object]:
        return {
            "actor": self.actor,
            "intent": self.intent,
            "description": self.description,
        }

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "SemanticEffect":
        payload = _require_mapping(value, path)
        _require_keys(payload, {"actor", "intent", "description"}, path)
        return cls(
            _string(payload, "actor", path),
            _string(payload, "intent", path),
            _string(payload, "description", path),
        )


@dataclass(frozen=True)
class SemanticFeedback:
    """A local feedback relationship and its continuation action."""

    event: str
    relation: str
    response_trigger: SemanticTrigger
    response_effect: SemanticEffect

    def to_mapping(self) -> dict[str, object]:
        return {
            "event": self.event,
            "relation": self.relation,
            "response_trigger": self.response_trigger.to_mapping(),
            "response_effect": self.response_effect.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "SemanticFeedback":
        payload = _require_mapping(value, path)
        _require_keys(
            payload,
            {"event", "relation", "response_trigger", "response_effect"},
            path,
        )
        return cls(
            _string(payload, "event", path),
            _string(payload, "relation", path),
            SemanticTrigger.from_mapping(payload["response_trigger"], f"{path}/response_trigger"),
            SemanticEffect.from_mapping(payload["response_effect"], f"{path}/response_effect"),
        )


@dataclass(frozen=True)
class SemanticMechanic:
    trigger: SemanticTrigger
    effect: SemanticEffect
    feedback: SemanticFeedback

    def to_mapping(self) -> dict[str, object]:
        return {
            "trigger": self.trigger.to_mapping(),
            "effect": self.effect.to_mapping(),
            "feedback": self.feedback.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "SemanticMechanic":
        payload = _require_mapping(value, path)
        _require_keys(payload, {"trigger", "effect", "feedback"}, path)
        return cls(
            SemanticTrigger.from_mapping(payload["trigger"], f"{path}/trigger"),
            SemanticEffect.from_mapping(payload["effect"], f"{path}/effect"),
            SemanticFeedback.from_mapping(payload["feedback"], f"{path}/feedback"),
        )


@dataclass(frozen=True)
class TriggeredMechanicV2:
    """A v2 triggered mechanic with an optional real feedback continuation."""

    kind: str
    trigger: SemanticTrigger
    effect: SemanticEffect
    feedback: SemanticFeedback | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "trigger": self.trigger.to_mapping(),
            "effect": self.effect.to_mapping(),
            "feedback": self.feedback.to_mapping() if self.feedback is not None else None,
        }


@dataclass(frozen=True)
class PassiveMechanicV2:
    """A minimal triggerless always-on passive mechanic."""

    kind: str
    persistence: str
    effect: SemanticEffect

    def to_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "persistence": self.persistence,
            "effect": self.effect.to_mapping(),
        }


@dataclass(frozen=True)
class SemanticRolePath:
    trigger: SemanticTrigger
    effect: SemanticEffect

    def to_mapping(self) -> dict[str, object]:
        return {
            "trigger": self.trigger.to_mapping(),
            "effect": self.effect.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object, path: str) -> "SemanticRolePath":
        payload = _require_mapping(value, path)
        _require_keys(payload, {"trigger", "effect"}, path)
        return cls(
            SemanticTrigger.from_mapping(payload["trigger"], f"{path}/trigger"),
            SemanticEffect.from_mapping(payload["effect"], f"{path}/effect"),
        )


@dataclass(frozen=True)
class TriggeredRolePathV2:
    """Role evidence path for a triggered v2 mechanic."""

    kind: str
    trigger: SemanticTrigger
    effect: SemanticEffect

    def to_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "trigger": self.trigger.to_mapping(),
            "effect": self.effect.to_mapping(),
        }


@dataclass(frozen=True)
class PassiveRolePathV2:
    """Role evidence path for a triggerless v2 passive."""

    kind: str
    effect: SemanticEffect

    def to_mapping(self) -> dict[str, object]:
        return {"kind": self.kind, "effect": self.effect.to_mapping()}


@dataclass(frozen=True)
class SkillSemanticIR:
    """The H1 semantic source of truth for one SkillKit ability graph."""

    ir_version: str
    ability_name: str
    summary: str
    mode: str
    role: str
    centrality: str
    mechanic: SemanticMechanic
    role_path: SemanticRolePath

    def to_mapping(self) -> dict[str, object]:
        return {
            "ir_version": self.ir_version,
            "ability_name": self.ability_name,
            "summary": self.summary,
            "mode": self.mode,
            "role": self.role,
            "centrality": self.centrality,
            "mechanic": self.mechanic.to_mapping(),
            "role_path": self.role_path.to_mapping(),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_mapping(cls, value: object) -> "SkillSemanticIR":
        path = "/semantic_skill_plan"
        payload = _require_mapping(value, path)
        _require_keys(
            payload,
            {
                "ir_version",
                "ability_name",
                "summary",
                "mode",
                "role",
                "centrality",
                "mechanic",
                "role_path",
            },
            path,
        )
        return cls(
            _string(payload, "ir_version", path),
            _string(payload, "ability_name", path),
            _string(payload, "summary", path),
            _string(payload, "mode", path),
            _string(payload, "role", path),
            _string(payload, "centrality", path),
            SemanticMechanic.from_mapping(payload["mechanic"], f"{path}/mechanic"),
            SemanticRolePath.from_mapping(payload["role_path"], f"{path}/role_path"),
        )


@dataclass(frozen=True)
class SkillSemanticIRV2:
    """Versioned semantic source supporting optional feedback and passives."""

    ir_version: str
    ability_name: str
    summary: str
    mode: str
    role: str
    centrality: str
    mechanic: TriggeredMechanicV2 | PassiveMechanicV2
    role_path: TriggeredRolePathV2 | PassiveRolePathV2

    def to_mapping(self) -> dict[str, object]:
        return {
            "ir_version": self.ir_version,
            "ability_name": self.ability_name,
            "summary": self.summary,
            "mode": self.mode,
            "role": self.role,
            "centrality": self.centrality,
            "mechanic": self.mechanic.to_mapping(),
            "role_path": self.role_path.to_mapping(),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_mapping(cls, value: object) -> "SkillSemanticIRV2":
        path = "/semantic_skill_plan"
        payload = _require_mapping(value, path)
        _require_keys(
            payload,
            {
                "ir_version",
                "ability_name",
                "summary",
                "mode",
                "role",
                "centrality",
                "mechanic",
                "role_path",
            },
            path,
        )
        version = _string(payload, "ir_version", path)
        mechanic_payload = _require_mapping(payload["mechanic"], f"{path}/mechanic")
        kind = _discriminator(mechanic_payload, f"{path}/mechanic")
        if kind == "triggered":
            _require_keys(mechanic_payload, {"kind", "trigger", "effect", "feedback"}, f"{path}/mechanic")
            feedback_value = mechanic_payload["feedback"]
            feedback = (
                None
                if feedback_value is None
                else SemanticFeedback.from_mapping(feedback_value, f"{path}/mechanic/feedback")
            )
            mechanic: TriggeredMechanicV2 | PassiveMechanicV2 = TriggeredMechanicV2(
                kind,
                SemanticTrigger.from_mapping(mechanic_payload["trigger"], f"{path}/mechanic/trigger"),
                SemanticEffect.from_mapping(mechanic_payload["effect"], f"{path}/mechanic/effect"),
                feedback,
            )
        elif kind == "passive":
            _require_keys(mechanic_payload, {"kind", "persistence", "effect"}, f"{path}/mechanic")
            mechanic = PassiveMechanicV2(
                kind,
                _string(mechanic_payload, "persistence", f"{path}/mechanic"),
                SemanticEffect.from_mapping(mechanic_payload["effect"], f"{path}/mechanic/effect"),
            )
        else:
            raise SemanticIRShapeError("IR_INVALID", f"{path}/mechanic/kind", "unsupported mechanic variant")

        role_payload = _require_mapping(payload["role_path"], f"{path}/role_path")
        role_kind = _discriminator(role_payload, f"{path}/role_path")
        if role_kind == "triggered":
            _require_keys(role_payload, {"kind", "trigger", "effect"}, f"{path}/role_path")
            role_path: TriggeredRolePathV2 | PassiveRolePathV2 = TriggeredRolePathV2(
                role_kind,
                SemanticTrigger.from_mapping(role_payload["trigger"], f"{path}/role_path/trigger"),
                SemanticEffect.from_mapping(role_payload["effect"], f"{path}/role_path/effect"),
            )
        elif role_kind == "passive":
            _require_keys(role_payload, {"kind", "effect"}, f"{path}/role_path")
            role_path = PassiveRolePathV2(
                role_kind,
                SemanticEffect.from_mapping(role_payload["effect"], f"{path}/role_path/effect"),
            )
        else:
            raise SemanticIRShapeError("IR_INVALID", f"{path}/role_path/kind", "unsupported role path variant")
        return cls(
            version,
            _string(payload, "ability_name", path),
            _string(payload, "summary", path),
            _string(payload, "mode", path),
            _string(payload, "role", path),
            _string(payload, "centrality", path),
            mechanic,
            role_path,
        )


def parse_semantic_ir(value: object) -> SkillSemanticIR | SkillSemanticIRV2:
    """Dispatch strictly by declared version; never reinterpret v1 as v2."""

    payload = _require_mapping(value, "/semantic_skill_plan")
    version = payload.get("ir_version")
    if version == SEMANTIC_IR_VERSION:
        return SkillSemanticIR.from_mapping(payload)
    if version == SEMANTIC_IR_V2_VERSION:
        return SkillSemanticIRV2.from_mapping(payload)
    raise SemanticIRShapeError("IR_INVALID", "/semantic_skill_plan/ir_version", "unsupported semantic IR version")


__all__ = [
    "ABILITY_MODES",
    "CENTRALITIES",
    "FEEDBACK_EVENTS",
    "FEEDBACK_OPERATIONS",
    "SEMANTIC_EFFECT_INTENTS",
    "SEMANTIC_EFFECT_INTENTS_V2",
    "SEMANTIC_IR_VERSION",
    "SEMANTIC_IR_V2_VERSION",
    "PassiveMechanicV2",
    "PassiveRolePathV2",
    "SUBJECT_KINDS",
    "TRIGGER_EVENTS",
    "SemanticEffect",
    "SemanticFeedback",
    "SemanticIRShapeError",
    "SemanticMechanic",
    "SemanticRolePath",
    "SemanticTrigger",
    "SkillSemanticIRV2",
    "SkillSemanticIR",
    "TriggeredMechanicV2",
    "TriggeredRolePathV2",
    "parse_semantic_ir",
]
