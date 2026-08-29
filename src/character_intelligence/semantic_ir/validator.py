"""Fail-closed semantic validation for the H1 SkillKit IR pilot."""

from __future__ import annotations

from dataclasses import dataclass
from character_skill.contract import ABILITY_MODES, CENTRALITIES, FEEDBACK_EVENTS, FEEDBACK_OPERATIONS, SUBJECT_KINDS, TRIGGER_EVENTS
from combat_semantics import CANONICAL_COMBAT_ROLES

from .schema import SEMANTIC_EFFECT_INTENTS, SEMANTIC_IR_VERSION, SkillSemanticIR


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

    value: SkillSemanticIR

    def __post_init__(self) -> None:
        if not isinstance(self.value, SkillSemanticIR):
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


def _validate_effect(effect, path: str, *, require_description: bool = False) -> None:
    _choice(effect.actor, SUPPORTED_SEMANTIC_ACTORS, f"{path}/actor")
    if effect.intent not in SEMANTIC_EFFECT_INTENTS:
        raise SemanticIRValidationError(
            "UNSUPPORTED_SEMANTIC_MAPPING",
            f"{path}/intent",
            "no deterministic canonical operation mapping exists",
        )
    _text(effect.description, f"{path}/description", required=require_description)


def validate_skill_semantic_ir(ir: SkillSemanticIR) -> ValidatedSkillSemanticIR:
    """Validate one immutable semantic IR without compiling or mutating it."""

    if not isinstance(ir, SkillSemanticIR):
        raise SemanticIRValidationError("IR_INVALID", "/semantic_skill_plan", "expected SkillSemanticIR")
    _choice(ir.ir_version, frozenset({SEMANTIC_IR_VERSION}), "/semantic_skill_plan/ir_version")
    _text(ir.ability_name, "/semantic_skill_plan/ability_name", required=True)
    _text(ir.summary, "/semantic_skill_plan/summary", required=True)
    _choice(ir.mode, ABILITY_MODES, "/semantic_skill_plan/mode")
    _choice(ir.role, frozenset(CANONICAL_COMBAT_ROLES), "/semantic_skill_plan/role")
    _choice(ir.centrality, CENTRALITIES, "/semantic_skill_plan/centrality")

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
