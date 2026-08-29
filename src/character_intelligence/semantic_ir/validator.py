"""Fail-closed semantic validation for the H1 SkillKit IR pilot."""

from __future__ import annotations

from dataclasses import dataclass
from character_skill.contract import ABILITY_MODES, CENTRALITIES, FEEDBACK_EVENTS, FEEDBACK_OPERATIONS, SUBJECT_KINDS, TRIGGER_EVENTS
from combat_semantics import CANONICAL_COMBAT_ROLES

from .schema import (
    SEMANTIC_EFFECT_INTENTS,
    SEMANTIC_EFFECT_INTENTS_V2,
    SEMANTIC_IR_V2_VERSION,
    SEMANTIC_IR_VERSION,
    PassiveMechanicV2,
    PassiveRolePathV2,
    SkillSemanticIR,
    SkillSemanticIRV2,
    TriggeredMechanicV2,
    TriggeredRolePathV2,
)


MAX_TEXT_LENGTH = 512
SUPPORTED_SEMANTIC_ACTORS = frozenset(SUBJECT_KINDS - {"summon"})


class SemanticIRValidationError(ValueError):
    """A bounded semantic validation failure."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


@dataclass(frozen=True)
class ValidatedSkillSemanticIR:
    """A proof-carrying IR value accepted by :func:`validate_skill_semantic_ir`."""

    value: SkillSemanticIR | SkillSemanticIRV2

    def __post_init__(self) -> None:
        if not isinstance(self.value, (SkillSemanticIR, SkillSemanticIRV2)):
            raise TypeError("ValidatedSkillSemanticIR.value must be SkillSemanticIR")

    @property
    def digest(self) -> str:
        return self.value.digest


def _text(value: str, path: str, *, required: bool = False) -> None:
    if not isinstance(value, str):
        raise SemanticIRValidationError("IR_INVALID", path, "must be a string")
    if required and not value.strip():
        raise SemanticIRValidationError("IR_INVALID", path, "must not be empty")
    if len(value) > MAX_TEXT_LENGTH:
        raise SemanticIRValidationError("IR_INVALID", path, "exceeds bounded text length")


def _choice(value: str, allowed: frozenset[str] | tuple[str, ...], path: str) -> None:
    if value not in allowed:
        raise SemanticIRValidationError("IR_INVALID", path, "unsupported semantic value")


def _validate_trigger(trigger, path: str) -> None:
    _choice(trigger.actor, SUPPORTED_SEMANTIC_ACTORS, f"{path}/actor")
    _choice(trigger.event, TRIGGER_EVENTS, f"{path}/event")
    if trigger.qualifier is not None:
        _text(trigger.qualifier, f"{path}/qualifier")


def _validate_effect(
    effect,
    path: str,
    *,
    require_description: bool = False,
    allowed_intents=SEMANTIC_EFFECT_INTENTS,
) -> None:
    _choice(effect.actor, SUPPORTED_SEMANTIC_ACTORS, f"{path}/actor")
    if effect.intent not in allowed_intents:
        raise SemanticIRValidationError(
            "UNSUPPORTED_SEMANTIC_MAPPING",
            f"{path}/intent",
            "no deterministic canonical operation mapping exists",
        )
    _text(effect.description, f"{path}/description", required=require_description)


def _validate_common(ir: SkillSemanticIR | SkillSemanticIRV2) -> None:
    _text(ir.ability_name, "/semantic_skill_plan/ability_name", required=True)
    _text(ir.summary, "/semantic_skill_plan/summary", required=True)
    _choice(ir.mode, ABILITY_MODES, "/semantic_skill_plan/mode")
    _choice(ir.role, frozenset(CANONICAL_COMBAT_ROLES), "/semantic_skill_plan/role")
    _choice(ir.centrality, CENTRALITIES, "/semantic_skill_plan/centrality")


def _validate_v1(ir: SkillSemanticIR) -> None:
    _choice(ir.ir_version, frozenset({SEMANTIC_IR_VERSION}), "/semantic_skill_plan/ir_version")

    _validate_trigger(ir.mechanic.trigger, "/semantic_skill_plan/mechanic/trigger")
    _validate_effect(
        ir.mechanic.effect,
        "/semantic_skill_plan/mechanic/effect",
        require_description=True,
    )
    _choice(ir.mechanic.feedback.event, FEEDBACK_EVENTS, "/semantic_skill_plan/mechanic/feedback/event")
    _choice(
        ir.mechanic.feedback.relation,
        FEEDBACK_OPERATIONS,
        "/semantic_skill_plan/mechanic/feedback/relation",
    )
    _validate_trigger(
        ir.mechanic.feedback.response_trigger,
        "/semantic_skill_plan/mechanic/feedback/response_trigger",
    )
    _validate_effect(
        ir.mechanic.feedback.response_effect,
        "/semantic_skill_plan/mechanic/feedback/response_effect",
        require_description=True,
    )
    if ir.mechanic.feedback.response_trigger.actor != ir.mechanic.effect.actor:
        raise SemanticIRValidationError(
            "IR_INVALID",
            "/semantic_skill_plan/mechanic/feedback/response_trigger/actor",
            "must match the mechanic effect actor for local feedback wiring",
        )

    _validate_trigger(ir.role_path.trigger, "/semantic_skill_plan/role_path/trigger")
    _validate_effect(ir.role_path.effect, "/semantic_skill_plan/role_path/effect", require_description=True)


def _validate_v2(ir: SkillSemanticIRV2) -> None:
    _choice(ir.ir_version, frozenset({SEMANTIC_IR_V2_VERSION}), "/semantic_skill_plan/ir_version")
    mechanic = ir.mechanic
    role_path = ir.role_path
    if isinstance(mechanic, TriggeredMechanicV2):
        if mechanic.kind != "triggered":
            raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/mechanic/kind", "invalid triggered variant")
        if ir.mode == "passive":
            raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/mode", "passive mode requires passive mechanic")
        _validate_trigger(mechanic.trigger, "/semantic_skill_plan/mechanic/trigger")
        _validate_effect(
            mechanic.effect,
            "/semantic_skill_plan/mechanic/effect",
            require_description=True,
            allowed_intents=SEMANTIC_EFFECT_INTENTS_V2,
        )
        if mechanic.feedback is not None:
            _choice(mechanic.feedback.event, FEEDBACK_EVENTS, "/semantic_skill_plan/mechanic/feedback/event")
            _choice(mechanic.feedback.relation, FEEDBACK_OPERATIONS, "/semantic_skill_plan/mechanic/feedback/relation")
            _validate_trigger(mechanic.feedback.response_trigger, "/semantic_skill_plan/mechanic/feedback/response_trigger")
            _validate_effect(
                mechanic.feedback.response_effect,
                "/semantic_skill_plan/mechanic/feedback/response_effect",
                require_description=True,
                allowed_intents=SEMANTIC_EFFECT_INTENTS_V2,
            )
            if mechanic.feedback.response_trigger.actor != mechanic.effect.actor:
                raise SemanticIRValidationError(
                    "IR_INVALID",
                    "/semantic_skill_plan/mechanic/feedback/response_trigger/actor",
                    "must match the mechanic effect actor for local feedback wiring",
                )
        if not isinstance(role_path, TriggeredRolePathV2) or role_path.kind != "triggered":
            raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/role_path/kind", "triggered mechanic requires triggered role path")
        _validate_trigger(role_path.trigger, "/semantic_skill_plan/role_path/trigger")
        _validate_effect(
            role_path.effect,
            "/semantic_skill_plan/role_path/effect",
            require_description=True,
            allowed_intents=SEMANTIC_EFFECT_INTENTS_V2,
        )
        return
    if isinstance(mechanic, PassiveMechanicV2):
        if mechanic.kind != "passive":
            raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/mechanic/kind", "invalid passive variant")
        _choice(ir.mode, frozenset({"passive"}), "/semantic_skill_plan/mode")
        _choice(mechanic.persistence, frozenset({"always_on"}), "/semantic_skill_plan/mechanic/persistence")
        _validate_effect(
            mechanic.effect,
            "/semantic_skill_plan/mechanic/effect",
            require_description=True,
            allowed_intents=SEMANTIC_EFFECT_INTENTS_V2,
        )
        if not isinstance(role_path, PassiveRolePathV2) or role_path.kind != "passive":
            raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/role_path/kind", "passive mechanic requires passive role path")
        _validate_effect(
            role_path.effect,
            "/semantic_skill_plan/role_path/effect",
            require_description=True,
            allowed_intents=SEMANTIC_EFFECT_INTENTS_V2,
        )
        if (role_path.effect.actor, role_path.effect.intent) != (mechanic.effect.actor, mechanic.effect.intent):
            raise SemanticIRValidationError(
                "IR_INVALID",
                "/semantic_skill_plan/role_path/effect",
                "passive role evidence must preserve the passive effect responsibility",
            )
        return
    raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan/mechanic", "unsupported semantic mechanic variant")


def validate_skill_semantic_ir(ir: SkillSemanticIR | SkillSemanticIRV2) -> ValidatedSkillSemanticIR:
    """Validate one immutable versioned semantic IR without compiling or mutating it."""

    if not isinstance(ir, (SkillSemanticIR, SkillSemanticIRV2)):
        raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan", "expected SkillSemanticIR")
    _validate_common(ir)
    if isinstance(ir, SkillSemanticIR):
        _validate_v1(ir)
    else:
        _validate_v2(ir)
    return ValidatedSkillSemanticIR(ir)


class SemanticIRValidator:
    """Public validator seam kept deliberately smaller than the compiler."""

    @staticmethod
    def validate(ir: SkillSemanticIR) -> ValidatedSkillSemanticIR:
        return validate_skill_semantic_ir(ir)


__all__ = [
    "MAX_TEXT_LENGTH",
    "SUPPORTED_SEMANTIC_ACTORS",
    "SemanticIRValidationError",
    "SemanticIRValidator",
    "ValidatedSkillSemanticIR",
    "validate_skill_semantic_ir",
]
