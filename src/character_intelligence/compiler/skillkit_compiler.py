"""Deterministic compiler from semantic SkillKit IR to canonical SkillKit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from character_skill import (
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    FeedbackRelation,
    ProtocolSkillKitCandidate,
    RoleEvidence,
    SCHEMA_VERSION,
    Subject,
    Trigger,
    TypedRef,
)
from character_skill._graph import build_graph, resolve_ref

from ..semantic_ir import (
    PassiveMechanicV2,
    PassiveRolePathV2,
    SemanticEffect,
    SemanticTrigger,
    SkillSemanticIR,
    SkillSemanticIRV2,
    TriggeredMechanicV2,
    TriggeredRolePathV2,
    ValidatedSkillSemanticIR,
)
from .provenance import COMPILER_VERSION, COMPILER_VERSION_V2, CompilerProvenance, CompilerProvenanceEntry


SEMANTIC_EFFECT_OPERATION_MAP: Mapping[str, str] = MappingProxyType(
    {
        "enable_ally": "ally_enablement",
        "deal_damage": "direct_output",
        "control_enemy": "enemy_action_control",
        "mitigate_ally": "recover_or_mitigate",
        "deal_follow_up_damage": "follow_up_output",
        "protect_ally": "threat_protection",
    }
)

_SELECTOR_BY_ACTOR: Mapping[str, str] = MappingProxyType(
    {
        "self": "owner",
        "ally": "ally",
        "team": "team",
        "enemy": "enemy",
        "scene": "scene",
    }
)


class SkillKitCompilerError(ValueError):
    """A bounded compiler failure with a stable code and path."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


@dataclass(frozen=True)
class SemanticMappingRegistry:
    """Immutable explicit semantic-to-canonical mapping registry."""

    effect_operations: Mapping[str, str] = field(
        default_factory=lambda: SEMANTIC_EFFECT_OPERATION_MAP
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_operations", MappingProxyType(dict(self.effect_operations)))

    def effect_operation(self, intent: str, path: str) -> str:
        try:
            return self.effect_operations[intent]
        except KeyError as error:
            raise SkillKitCompilerError(
                "UNSUPPORTED_SEMANTIC_MAPPING",
                path,
                "no deterministic canonical operation mapping exists",
            ) from error


DEFAULT_MAPPING_REGISTRY = SemanticMappingRegistry()


@dataclass(frozen=True)
class CompilerProvenanceResult:
    candidate: ProtocolSkillKitCandidate
    provenance: CompilerProvenance

    @property
    def candidate_digest(self) -> str:
        return self.candidate.digest

    @property
    def semantic_ir_digest(self) -> str:
        # The source digest is captured by the compiler result without storing
        # the source payload in provenance.
        return self._semantic_ir_digest

    _semantic_ir_digest: str = field(repr=False, compare=True, default="")


def _subject(actor: str) -> Subject:
    try:
        selector = _SELECTOR_BY_ACTOR[actor]
    except KeyError as error:
        raise SkillKitCompilerError("CANONICAL_MAPPING_FAILURE", "/subject", "unsupported actor") from error
    return Subject(actor, selector, None)


def _trigger(trigger: SemanticTrigger, source_ref: TypedRef | None = None) -> Trigger:
    return Trigger(_subject(trigger.actor), trigger.event, source_ref, trigger.qualifier)


def _effect(
    effect: SemanticEffect,
    registry: SemanticMappingRegistry,
    path: str,
    effect_id: str,
) -> Effect:
    return Effect(
        effect_id,
        _subject(effect.actor),
        registry.effect_operation(effect.intent, f"{path}/intent"),
        None,
        effect.description,
    )


def _entry_and_provenance(
    ir: SkillSemanticIR,
    registry: SemanticMappingRegistry,
) -> tuple[AbilityEntry, FeedbackRelation, tuple[RoleEvidence, ...], CompilerProvenance]:
    entry_id = "skill_01"
    trigger_protocol_id = "mechanic_trigger"
    feedback_protocol_id = "mechanic_feedback"
    role_protocol_id = "role_path"

    trigger_effect = _effect(ir.mechanic.effect, registry, "/mechanic/effect", "apply")
    response_effect = _effect(
        ir.mechanic.feedback.response_effect,
        registry,
        "/mechanic/feedback/response_effect",
        "continue",
    )
    role_effect = _effect(ir.role_path.effect, registry, "/role_path/effect", "support")

    trigger_ref = TypedRef("effect", f"{entry_id}/{trigger_protocol_id}/{trigger_effect.effect_id}")
    feedback_protocol_ref = TypedRef("protocol", f"{entry_id}/{feedback_protocol_id}")
    role_effect_ref = TypedRef("effect", f"{entry_id}/{role_protocol_id}/{role_effect.effect_id}")

    protocols = (
        BehaviorProtocol(
            trigger_protocol_id,
            _trigger(ir.mechanic.trigger),
            (trigger_effect,),
        ),
        BehaviorProtocol(
            feedback_protocol_id,
            _trigger(ir.mechanic.feedback.response_trigger, trigger_ref),
            (response_effect,),
        ),
        BehaviorProtocol(
            role_protocol_id,
            _trigger(ir.role_path.trigger),
            (role_effect,),
        ),
    )
    entry = AbilityEntry(entry_id, ir.ability_name, ir.mode, protocols, ir.summary)
    relation = FeedbackRelation(
        "feedback_01",
        trigger_ref,
        feedback_protocol_ref,
        ir.mechanic.feedback.event,
        ir.mechanic.feedback.relation,
    )
    role_evidence = (RoleEvidence((role_effect_ref,), ir.centrality),)
    provenance = CompilerProvenance(
        entries=(
            CompilerProvenanceEntry("/schema_version", "COMPILER_CONSTANT", rule_id="C-SCHEMA-VERSION"),
            CompilerProvenanceEntry("/entries", "COMPILER_DERIVED", rule_id="C-ROOT-ENVELOPE"),
            CompilerProvenanceEntry("/entries/0/ability_id", "COMPILER_DERIVED", rule_id="C-ENTRY-ID"),
            CompilerProvenanceEntry("/entries/0/name", "IR_SEMANTIC", "/ability_name"),
            CompilerProvenanceEntry("/entries/0/mode", "IR_SEMANTIC", "/mode"),
            CompilerProvenanceEntry("/entries/0/display_text", "IR_SEMANTIC", "/summary"),
            CompilerProvenanceEntry("/entries/0/protocols/0/when", "IR_SEMANTIC", "/mechanic/trigger"),
            CompilerProvenanceEntry("/entries/0/protocols/0/causes/0/operation", "IR_SEMANTIC", "/mechanic/effect/intent"),
            CompilerProvenanceEntry("/entries/0/protocols/1/when", "IR_SEMANTIC", "/mechanic/feedback/response_trigger"),
            CompilerProvenanceEntry("/entries/0/protocols/1/causes/0/operation", "IR_SEMANTIC", "/mechanic/feedback/response_effect/intent"),
            CompilerProvenanceEntry("/entries/0/protocols/2/when", "IR_SEMANTIC", "/role_path/trigger"),
            CompilerProvenanceEntry("/entries/0/protocols/2/causes/0/operation", "IR_SEMANTIC", "/role_path/effect/intent"),
            CompilerProvenanceEntry("/feedback_relations/0", "COMPILER_DERIVED", rule_id="C-FEEDBACK-WIRE"),
            CompilerProvenanceEntry("/role_evidence/0/effect_refs", "COMPILER_DERIVED", rule_id="C-ROLE-EVIDENCE-REF"),
            CompilerProvenanceEntry("/feedback_relations", "COMPILER_DERIVED", rule_id="C-ROOT-ENVELOPE"),
            CompilerProvenanceEntry("/resources", "COMPILER_DEFAULT", rule_id="C-EMPTY-COLLECTION"),
            CompilerProvenanceEntry("/states", "COMPILER_DEFAULT", rule_id="C-EMPTY-COLLECTION"),
            CompilerProvenanceEntry("/summons", "COMPILER_DEFAULT", rule_id="C-EMPTY-COLLECTION"),
        )
    )
    return entry, relation, role_evidence, provenance


def _entry_and_provenance_v2(
    ir: SkillSemanticIRV2,
    registry: SemanticMappingRegistry,
) -> tuple[AbilityEntry, tuple[FeedbackRelation, ...], tuple[RoleEvidence, ...], CompilerProvenance]:
    entry_id = "skill_01"
    protocols: list[BehaviorProtocol] = []
    feedback_relations: list[FeedbackRelation] = []

    if isinstance(ir.mechanic, TriggeredMechanicV2):
        trigger_effect = _effect(ir.mechanic.effect, registry, "/mechanic/effect", "apply")
        trigger_ref = TypedRef("effect", f"{entry_id}/mechanic_trigger/{trigger_effect.effect_id}")
        protocols.append(BehaviorProtocol("mechanic_trigger", _trigger(ir.mechanic.trigger), (trigger_effect,)))
        if ir.mechanic.feedback is not None:
            response_effect = _effect(
                ir.mechanic.feedback.response_effect,
                registry,
                "/mechanic/feedback/response_effect",
                "continue",
            )
            protocols.append(
                BehaviorProtocol(
                    "mechanic_feedback",
                    _trigger(ir.mechanic.feedback.response_trigger, trigger_ref),
                    (response_effect,),
                )
            )
            feedback_relations.append(
                FeedbackRelation(
                    "feedback_01",
                    trigger_ref,
                    TypedRef("protocol", f"{entry_id}/mechanic_feedback"),
                    ir.mechanic.feedback.event,
                    ir.mechanic.feedback.relation,
                )
            )
        role_path = ir.role_path
        if not isinstance(role_path, TriggeredRolePathV2):
            raise SkillKitCompilerError("IR_INVALID", "/role_path/kind", "triggered mechanic requires triggered role path")
        role_effect = _effect(role_path.effect, registry, "/role_path/effect", "support")
        protocols.append(BehaviorProtocol("role_path", _trigger(role_path.trigger), (role_effect,)))
        role_effect_ref = TypedRef("effect", f"{entry_id}/role_path/{role_effect.effect_id}")
        role_protocol_index = 2 if ir.mechanic.feedback is not None else 1
        provenance = CompilerProvenance(
            compiler_version=COMPILER_VERSION_V2,
            entries=(
                CompilerProvenanceEntry("/entries", "COMPILER_DERIVED", rule_id="C-V2-ROOT-ENVELOPE"),
                CompilerProvenanceEntry("/entries/0/mode", "IR_SEMANTIC", "/mode"),
                CompilerProvenanceEntry("/entries/0/protocols/0/when", "IR_SEMANTIC", "/mechanic/trigger"),
                CompilerProvenanceEntry("/entries/0/protocols/0/causes/0/operation", "IR_SEMANTIC", "/mechanic/effect/intent"),
                CompilerProvenanceEntry(f"/entries/0/protocols/{role_protocol_index}/when", "IR_SEMANTIC", "/role_path/trigger"),
                CompilerProvenanceEntry(f"/entries/0/protocols/{role_protocol_index}/causes/0/operation", "IR_SEMANTIC", "/role_path/effect/intent"),
                CompilerProvenanceEntry("/feedback_relations", "COMPILER_DERIVED", rule_id="C-V2-OPTIONAL-FEEDBACK"),
            )
        )
    else:
        if not isinstance(ir.mechanic, PassiveMechanicV2) or not isinstance(ir.role_path, PassiveRolePathV2):
            raise SkillKitCompilerError("IR_INVALID", "/semantic_skill_plan", "passive variants must be paired")
        passive_effect = _effect(ir.mechanic.effect, registry, "/mechanic/effect", "apply")
        role_effect = _effect(ir.role_path.effect, registry, "/role_path/effect", "support")
        protocols.extend(
            (
                BehaviorProtocol("passive_effect", None, (passive_effect,)),
                BehaviorProtocol("passive_role_path", None, (role_effect,)),
            )
        )
        role_effect_ref = TypedRef("effect", f"{entry_id}/passive_role_path/{role_effect.effect_id}")
        provenance = CompilerProvenance(
            compiler_version=COMPILER_VERSION_V2,
            entries=(
                CompilerProvenanceEntry("/entries", "COMPILER_DERIVED", rule_id="C-V2-ROOT-ENVELOPE"),
                CompilerProvenanceEntry("/entries/0/mode", "IR_SEMANTIC", "/mode"),
                CompilerProvenanceEntry("/entries/0/protocols/0/when", "COMPILER_DERIVED", rule_id="C-V2-TRIGGERLESS-PASSIVE"),
                CompilerProvenanceEntry("/entries/0/protocols/0/causes/0/operation", "IR_SEMANTIC", "/mechanic/effect/intent"),
                CompilerProvenanceEntry("/entries/0/protocols/1/when", "COMPILER_DERIVED", rule_id="C-V2-TRIGGERLESS-PASSIVE-ROLE"),
                CompilerProvenanceEntry("/feedback_relations", "COMPILER_DEFAULT", rule_id="C-V2-EMPTY-FEEDBACK"),
            )
        )
    entry = AbilityEntry(entry_id, ir.ability_name, ir.mode, tuple(protocols), ir.summary)
    role_evidence = (RoleEvidence((role_effect_ref,), ir.centrality),)
    return entry, tuple(feedback_relations), role_evidence, provenance


def compile_skill_semantic_ir(
    validated_ir: ValidatedSkillSemanticIR,
    *,
    registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
) -> CompilerProvenanceResult:
    """Compile a validated IR through a pure deterministic public seam."""

    if not isinstance(validated_ir, ValidatedSkillSemanticIR):
        raise SkillKitCompilerError("IR_INVALID", "/semantic_skill_plan", "input must be validated IR")
    if not isinstance(registry, SemanticMappingRegistry):
        raise TypeError("registry must be a SemanticMappingRegistry")
    if isinstance(validated_ir.value, SkillSemanticIRV2):
        entry, relations, role_evidence, provenance = _entry_and_provenance_v2(validated_ir.value, registry)
    else:
        entry, relation, role_evidence, provenance = _entry_and_provenance(validated_ir.value, registry)
        relations = (relation,)
    candidate = ProtocolSkillKitCandidate(
        SCHEMA_VERSION,
        (entry,),
        relations,
        (),
        (),
        (),
        role_evidence,
        validated_ir.value.summary,
    )
    return CompilerProvenanceResult(candidate, provenance, validated_ir.digest)


def validate_reference_integrity(candidate: ProtocolSkillKitCandidate) -> None:
    """Perform a generic compiler preflight; evaluator remains authoritative."""

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/candidate", "expected canonical candidate")
    graph = build_graph(candidate)
    for entry in candidate.entries:
        for protocol in entry.protocols:
            if protocol.when is not None and protocol.when.source_ref is not None:
                if protocol.when.source_ref.kind != "effect" or resolve_ref(protocol.when.source_ref, graph) is None:
                    raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/entries", "trigger source ref does not resolve")
            for effect in protocol.causes:
                if effect.object_ref is not None and resolve_ref(effect.object_ref, graph) is None:
                    raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/entries", "effect object ref does not resolve")
    for relation in candidate.feedback_relations:
        if relation.source_effect.kind != "effect" or resolve_ref(relation.source_effect, graph) is None:
            raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/feedback_relations", "feedback source does not resolve")
        if relation.target_protocol.kind != "protocol" or resolve_ref(relation.target_protocol, graph) is None:
            raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/feedback_relations", "feedback target does not resolve")
    for evidence in candidate.role_evidence:
        for ref in evidence.effect_refs:
            if ref.kind != "effect" or resolve_ref(ref, graph) is None:
                raise SkillKitCompilerError("REFERENCE_WIRING_FAILURE", "/role_evidence", "role effect ref does not resolve")


__all__ = [
    "COMPILER_VERSION",
    "DEFAULT_MAPPING_REGISTRY",
    "SEMANTIC_EFFECT_OPERATION_MAP",
    "CompilerProvenanceResult",
    "CompileResult",
    "SemanticMappingRegistry",
    "SkillKitCompilerError",
    "compile_skill_semantic_ir",
    "validate_reference_integrity",
]


CompileResult = CompilerProvenanceResult
