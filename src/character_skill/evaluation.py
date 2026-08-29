"""Bounded SkillKit evaluation over the public domain contract.

The evaluator is deliberately request-owned and deterministic.  It validates
the structural graph and the reviewed S1 mechanic, role, and reference
dimensions; repair remains a separate public seam in ``_repair``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any

from ._graph import DerivedGraph, build_graph, exists_in_other_namespace, resolve_ref
from .context import SkillValidationContext
from .context import MechanicRequirement
from .models import (
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    FeedbackRelation,
    RoleEvidence,
    ProtocolSkillKitCandidate,
    SkillFinding,
    SkillValidationReport,
    TypedRef,
)


_FEEDBACK_DOWNSTREAM_OPERATIONS: dict[str, frozenset[str]] = {
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

_LIFECYCLE_OPERATION_KINDS: dict[str, str] = {
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

_CANONICAL_ROLES = frozenset(
    {"main_dps", "sub_dps", "support", "healer", "control", "defense"}
)
_ROLE_ROWS: dict[str, dict[str, object]] = {
    "main_dps": {
        "duty": "direct_output",
        "subjects": frozenset({"enemy"}),
        "triggers": frozenset({("self", "ability_invoked")}),
    },
    "sub_dps": {
        "duty": "follow_up_output",
        "subjects": frozenset({"enemy"}),
        "triggers": frozenset({("ally", "action_completed"), ("team", "action_completed")}),
    },
    "support": {
        "duty": "ally_enablement",
        "subjects": frozenset({"ally", "team"}),
        "triggers": frozenset(
            {
                ("self", "ability_invoked"),
                ("ally", "action_completed"),
                ("team", "action_completed"),
            }
        ),
    },
    "healer": {
        "duty": "recover_or_mitigate",
        "subjects": frozenset({"ally", "team"}),
        "triggers": frozenset(
            {
                ("self", "ability_invoked"),
                ("ally", "damage_received"),
                ("team", "damage_received"),
            }
        ),
    },
    "control": {
        "duty": "enemy_action_control",
        "subjects": frozenset({"enemy"}),
        "triggers": frozenset(
            {
                ("self", "ability_invoked"),
                ("ally", "action_completed"),
                ("summon", "summon_acted"),
                ("scene", "scene_entered"),
            }
        ),
    },
    "defense": {
        "duty": "threat_protection",
        "subjects": frozenset({"ally", "team"}),
        "triggers": frozenset(
            {
                ("self", "ability_invoked"),
                ("ally", "damage_received"),
                ("team", "damage_received"),
            }
        ),
    },
}


def _plain(value: object) -> object:
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


def _canonical_json(value: object) -> str:
    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _report_digest(
    candidate_digest: str,
    context_digest: str,
    findings: Sequence[SkillFinding],
    outcome: str,
) -> str:
    payload = {
        "candidate_digest": candidate_digest,
        "context_digest": context_digest,
        "findings": [item.to_mapping() for item in findings],
        "outcome": outcome,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _coerce_context(
    context: SkillValidationContext | Mapping[str, object],
) -> SkillValidationContext:
    if isinstance(context, SkillValidationContext):
        return context
    if isinstance(context, Mapping):
        return SkillValidationContext.from_mapping(context)
    raise TypeError("context must be a SkillValidationContext or mapping")


def _finding(
    code: str,
    path: str,
    *,
    repairable: bool,
    blocking: bool = True,
    evidence_refs: Sequence[str] = (),
    authorized_paths: Sequence[str] = (),
) -> SkillFinding:
    return SkillFinding(
        code,
        path,
        blocking,
        repairable,
        tuple(evidence_refs),
        tuple(authorized_paths),
    )


def _dedupe_sort(findings: Sequence[SkillFinding]) -> tuple[SkillFinding, ...]:
    unique: dict[tuple[str, str, tuple[str, ...]], SkillFinding] = {}
    for item in findings:
        evidence = tuple(sorted(item.evidence_refs))
        unique.setdefault((item.code, item.field_path, evidence), item)
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.priority,
                item.code,
                item.field_path,
                tuple(sorted(item.evidence_refs)),
            ),
        )
    )


def _all_protocols(
    candidate: ProtocolSkillKitCandidate,
) -> tuple[tuple[int, int, AbilityEntry, BehaviorProtocol], ...]:
    return tuple(
        (entry_index, protocol_index, entry, protocol)
        for entry_index, entry in enumerate(candidate.entries)
        for protocol_index, protocol in enumerate(entry.protocols)
    )


def _reference_failure(
    ref: TypedRef,
    graph: DerivedGraph,
    path: str,
    *,
    required_kind: str | None = None,
) -> SkillFinding | None:
    if required_kind is not None and ref.kind != required_kind:
        return _finding(
            "REFERENCE_KIND_MISMATCH",
            path,
            repairable=False,
            evidence_refs=(ref.id,),
        )
    if resolve_ref(ref, graph) is not None:
        return None
    code = "REFERENCE_KIND_MISMATCH" if exists_in_other_namespace(ref, graph) else "REFERENCE_DANGLING"
    return _finding(code, path, repairable=False, evidence_refs=(ref.id,))


def _subject_reference_findings(
    subject: object,
    path: str,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> None:
    # Parser-created candidates always contain Subject here; the explicit
    # guard keeps manually constructed value objects fail-closed as well.
    if subject is None:
        return
    kind = getattr(subject, "kind", None)
    ref = getattr(subject, "entity_ref", None)
    ref_path = f"{path}/entity_ref"
    if kind == "summon":
        if ref is None:
            findings.append(_finding("REFERENCE_DANGLING", ref_path, repairable=False))
            return
        failure = _reference_failure(ref, graph, ref_path, required_kind="summon")
        if failure is not None:
            findings.append(failure)
        return
    if ref is not None:
        findings.append(
            _finding(
                "REFERENCE_KIND_MISMATCH",
                ref_path,
                repairable=False,
                evidence_refs=(ref.id,),
            )
        )


def _validate_general_refs(
    candidate: ProtocolSkillKitCandidate,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> None:
    for entry_index, protocol_index, protocol_entry, protocol in _all_protocols(candidate):
        del protocol_entry
        base = f"/entries/{entry_index}/protocols/{protocol_index}"
        trigger = protocol.when
        if trigger is not None:
            if trigger.source_ref is not None:
                failure = _reference_failure(
                    trigger.source_ref,
                    graph,
                    f"{base}/when/source_ref",
                    required_kind="effect",
                )
                if failure is not None:
                    findings.append(failure)
            if trigger.subject is not None:
                _subject_reference_findings(trigger.subject, f"{base}/when/subject", graph, findings)
        for effect_index, effect in enumerate(protocol.causes):
            effect_base = f"{base}/causes/{effect_index}"
            if effect.object_ref is not None:
                failure = _reference_failure(
                    effect.object_ref,
                    graph,
                    f"{effect_base}/object_ref",
                )
                if failure is not None:
                    findings.append(failure)
            if effect.subject is not None:
                _subject_reference_findings(effect.subject, f"{effect_base}/subject", graph, findings)


def _lifecycle_slot(
    lease_kind: str,
    lease_index: int,
    slot: str,
    refs: Sequence[TypedRef],
    allowed_operations: frozenset[str],
    entity_id: str,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> list[TypedRef]:
    valid: list[TypedRef] = []
    for ref_index, ref in enumerate(refs):
        path = f"/{lease_kind}s/{lease_index}/{slot}/{ref_index}"
        if ref.kind != "effect":
            findings.append(
                _finding(
                    "LIFECYCLE_REFERENCE_WRONG_KIND",
                    path,
                    repairable=False,
                    evidence_refs=(ref.id,),
                )
            )
            continue
        location = graph.effects.get(ref.id)
        if location is None:
            findings.append(
                _finding(
                    "LIFECYCLE_REFERENCE_DANGLING",
                    path,
                    repairable=False,
                    evidence_refs=(ref.id,),
                )
            )
            continue
        effect = location.effect
        if effect.operation not in allowed_operations or effect.object_ref != TypedRef(lease_kind, entity_id):
            findings.append(
                _finding(
                    "LIFECYCLE_OPERATION_MISMATCH",
                    path,
                    repairable=False,
                    evidence_refs=(ref.id,),
                )
            )
            continue
        valid.append(ref)
    return valid


def _lifecycle_findings(
    candidate: ProtocolSkillKitCandidate,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> None:
    for index, lease in enumerate(candidate.resources):
        opened = _lifecycle_slot(
            "resource",
            index,
            "opened_by",
            lease.opened_by,
            frozenset({"resource_gain"}),
            lease.resource_id,
            graph,
            findings,
        )
        used = _lifecycle_slot(
            "resource",
            index,
            "used_or_transformed_by",
            lease.used_or_transformed_by,
            frozenset({"resource_use", "resource_transform"}),
            lease.resource_id,
            graph,
            findings,
        )
        closed = _lifecycle_slot(
            "resource",
            index,
            "closed_by",
            lease.closed_by,
            frozenset({"resource_clear", "resource_transform"}),
            lease.resource_id,
            graph,
            findings,
        )
        if not (opened and used and closed):
            targeted_abilities = {
                location.entry.ability_id
                for location in graph.effects.values()
                if location.effect.object_ref == TypedRef("resource", lease.resource_id)
            }
            code = (
                "MULTI_SKILL_LOOP_INCOHERENT"
                if len(targeted_abilities) >= 2
                else "RESOURCE_LOOP_INCOMPLETE"
            )
            findings.append(
                _finding(
                    code,
                    f"/resources/{index}",
                    repairable=True,
                    authorized_paths=(
                        f"/resources/{index}/opened_by/-",
                        f"/resources/{index}/used_or_transformed_by/-",
                        f"/resources/{index}/closed_by/-",
                    ),
                )
            )

    for index, lease in enumerate(candidate.states):
        established = _lifecycle_slot(
            "state",
            index,
            "established_by",
            lease.established_by,
            frozenset({"state_enter"}),
            lease.state_id,
            graph,
            findings,
        )
        active = _lifecycle_slot(
            "state",
            index,
            "active_effects",
            lease.active_effects,
            frozenset({"state_apply"}),
            lease.state_id,
            graph,
            findings,
        )
        ended = _lifecycle_slot(
            "state",
            index,
            "ended_or_replaced_by",
            lease.ended_or_replaced_by,
            frozenset({"state_exit", "state_replace"}),
            lease.state_id,
            graph,
            findings,
        )
        if established and active and not ended:
            findings.append(
                _finding(
                    "STATE_EXIT_MISSING",
                    f"/states/{index}/ended_or_replaced_by",
                    repairable=True,
                    authorized_paths=(f"/states/{index}/ended_or_replaced_by/-",),
                )
            )

    for index, lease in enumerate(candidate.summons):
        spawned = _lifecycle_slot(
            "summon",
            index,
            "spawned_by",
            lease.spawned_by,
            frozenset({"summon_spawn"}),
            lease.summon_id,
            graph,
            findings,
        )
        active = _lifecycle_slot(
            "summon",
            index,
            "active_effects",
            lease.active_effects,
            frozenset({"summon_act"}),
            lease.summon_id,
            graph,
            findings,
        )
        departed = _lifecycle_slot(
            "summon",
            index,
            "departed_or_replaced_by",
            lease.departed_or_replaced_by,
            frozenset({"summon_exit", "summon_replace"}),
            lease.summon_id,
            graph,
            findings,
        )
        has_replace = any(
            graph.effects.get(ref.id) is not None
            and graph.effects[ref.id].effect.operation == "summon_replace"
            for ref in departed
        )
        if spawned and active and (not departed or (lease.repeat_policy is None and not has_replace)):
            findings.append(
                _finding(
                    "SUMMON_LIFECYCLE_INCOMPLETE",
                    f"/summons/{index}",
                    repairable=True,
                    authorized_paths=(
                        f"/summons/{index}/departed_or_replaced_by/-",
                        f"/summons/{index}/repeat_policy",
                    ),
                )
            )


def _profile_or_finding(
    profile: Mapping[str, object] | object | None,
) -> tuple[tuple[str | None, tuple[str, ...]] | None, SkillFinding | None]:
    """Parse only the canonical role-profile mapping, without aliasing it."""

    if profile is None:
        return None, None
    if not isinstance(profile, Mapping):
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    if set(profile) != {"primary_role", "secondary_roles"}:
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    primary = profile.get("primary_role")
    secondary = profile.get("secondary_roles")
    if primary is not None and (
        not isinstance(primary, str) or primary not in _CANONICAL_ROLES
    ):
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    if not isinstance(secondary, Sequence) or isinstance(secondary, (str, bytes, bytearray)):
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    secondary_values = tuple(secondary)
    if any(
        not isinstance(role, str) or role not in _CANONICAL_ROLES
        for role in secondary_values
    ):
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    if (
        len(set(secondary_values)) != len(secondary_values)
        or (primary is not None and primary in secondary_values)
    ):
        return None, _finding(
            "CROSS_TAXONOMY_ROLE_LABEL",
            "context.combat_role_profile",
            repairable=False,
        )
    return (primary, secondary_values), None


def _role_findings(
    candidate: ProtocolSkillKitCandidate,
    profile: tuple[str | None, tuple[str, ...]] | None,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> None:
    if profile is None:
        return
    primary, secondary = profile
    requested: list[tuple[str, str]] = []
    if primary is not None:
        requested.append((primary, "core"))
    requested.extend((role, "secondary") for role in secondary)
    for role, centrality in requested:
        row = _ROLE_ROWS[role]
        valid = False
        for evidence in candidate.role_evidence:
            if evidence.centrality != centrality:
                continue
            for ref in evidence.effect_refs:
                location = graph.effects.get(ref.id) if ref.kind == "effect" else None
                if location is None:
                    continue
                trigger = location.protocol.when
                pair = (
                    (trigger.subject.kind, trigger.event)
                    if trigger is not None and trigger.subject is not None
                    else (None, None)
                )
                effect = location.effect
                if (
                    effect.operation == row["duty"]
                    and effect.subject is not None
                    and effect.subject.kind in row["subjects"]
                    and pair in row["triggers"]
                ):
                    valid = True
                    break
            if valid:
                break
        if not valid:
            findings.append(_finding("ROLE_EFFECT_MISMATCH", "/role_evidence", repairable=False))


def _skeletons(
    candidate: ProtocolSkillKitCandidate,
    requirement: MechanicRequirement,
    graph: DerivedGraph,
) -> list[tuple[BehaviorProtocol, object]]:
    matches: list[tuple[BehaviorProtocol, object]] = []
    for _, _, entry, protocol in _all_protocols(candidate):
        trigger = protocol.when
        if (
            trigger is None
            or trigger.subject is None
            or trigger.subject.kind not in requirement.trigger.subject_kinds
            or trigger.event not in requirement.trigger.events
        ):
            continue
        if requirement.trigger.source_kinds:
            source = trigger.source_ref
            if (
                source is None
                or source.kind not in requirement.trigger.source_kinds
                or resolve_ref(source, graph) is None
            ):
                continue
        for effect in protocol.causes:
            if (
                effect.subject is None
                or effect.subject.kind not in requirement.effect.subject_kinds
                or effect.operation not in requirement.effect.operations
            ):
                continue
            if requirement.effect.object_kinds:
                object_ref = effect.object_ref
                if (
                    object_ref is None
                    or object_ref.kind not in requirement.effect.object_kinds
                    or resolve_ref(object_ref, graph) is None
                ):
                    continue
            location = graph.effects.get(
                f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}"
            )
            if location is not None:
                matches.append((protocol, location))
    return matches


def _feedback_downstream_valid(
    effect: Effect,
    relation: FeedbackRelation,
    graph: DerivedGraph,
) -> bool:
    if effect.subject is None:
        return False
    if effect.operation not in _FEEDBACK_DOWNSTREAM_OPERATIONS.get(
        relation.operation, frozenset()
    ):
        return False
    expected_kind = _LIFECYCLE_OPERATION_KINDS.get(effect.operation or "")
    if expected_kind is not None:
        object_ref = effect.object_ref
        if (
            object_ref is None
            or object_ref.kind != expected_kind
            or f"{expected_kind}/{object_ref.id}" not in graph.leases
        ):
            return False
    return True


def _feedback_attached_to_skeleton(
    relation: FeedbackRelation,
    source: object,
    graph: DerivedGraph,
    requirement: MechanicRequirement | None,
) -> bool:
    source_effect = source.effect_ref
    if relation.source_effect.kind != "effect" or relation.source_effect != source_effect:
        return False
    if relation.target_protocol.kind != "protocol":
        return False
    target = graph.protocols.get(relation.target_protocol.id)
    if target is None or relation.target_protocol.id == source.protocol_ref.id:
        return False
    if (
        target.when is None
        or target.when.event != "feedback_received"
        or target.when.source_ref != relation.source_effect
    ):
        return False
    if requirement is not None and (
        relation.event not in requirement.feedback.events
        or relation.operation not in requirement.feedback.operations
    ):
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
    source: object,
    graph: DerivedGraph,
    requirement: MechanicRequirement | None,
) -> bool:
    if not _feedback_attached_to_skeleton(relation, source, graph, requirement):
        return False
    target = graph.protocols[relation.target_protocol.id]
    return any(_feedback_downstream_valid(effect, relation, graph) for effect in target.causes)


def _feedback_authorized_paths(
    candidate: ProtocolSkillKitCandidate,
    rows: Sequence[tuple[BehaviorProtocol, object]],
    requirement: MechanicRequirement,
    graph: DerivedGraph,
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
                    graph,
                )
                for operation in requested_operations
                for effect in target.causes
            )
            if not has_compatible_cause:
                paths.add(f"/entries/{entry_index}/protocols/{protocol_index}/causes/-")
    return tuple(sorted(paths))


def _mechanic_findings(
    candidate: ProtocolSkillKitCandidate,
    context: SkillValidationContext,
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> dict[str, list[tuple[BehaviorProtocol, object]]]:
    matched: dict[str, list[tuple[BehaviorProtocol, object]]] = {}
    for requirement in context.intent.mechanic_requirements:
        rows = _skeletons(candidate, requirement, graph)
        matched[requirement.requirement_id] = rows
        if not rows:
            findings.append(_finding("MECHANIC_SKELETON_ABSENT", "/entries", repairable=False))
            continue
        if requirement.feedback.required:
            valid_feedback = any(
                _feedback_valid_for(relation, source, graph, requirement)
                for relation in candidate.feedback_relations
                for _, source in rows
            )
            locally_attached_feedback = any(
                _feedback_attached_to_skeleton(relation, source, graph, requirement)
                for relation in candidate.feedback_relations
                for _, source in rows
            )
            if not valid_feedback and not locally_attached_feedback:
                findings.append(
                    _finding(
                        "REQUESTED_MECHANIC_UNREPRESENTED",
                        "/feedback_relations/-",
                        repairable=True,
                        authorized_paths=_feedback_authorized_paths(
                            candidate, rows, requirement, graph
                        ),
                    )
                )
    return matched


def _feedback_findings(
    candidate: ProtocolSkillKitCandidate,
    matched: Mapping[str, list[tuple[BehaviorProtocol, object]]],
    requirements: Sequence[MechanicRequirement],
    graph: DerivedGraph,
    findings: list[SkillFinding],
) -> None:
    requirements_by_id = {
        requirement.requirement_id: requirement for requirement in requirements
    }
    for index, relation in enumerate(candidate.feedback_relations):
        path = f"/feedback_relations/{index}"
        if (
            relation.source_effect.kind != "effect"
            or relation.target_protocol.kind != "protocol"
            or relation.source_effect.id not in graph.effects
            or relation.target_protocol.id not in graph.protocols
        ):
            findings.append(
                _finding(
                    "FEEDBACK_REFERENCE_DANGLING",
                    path,
                    repairable=False,
                    evidence_refs=(relation.source_effect.id, relation.target_protocol.id),
                )
            )
            continue
        valid = any(
            _feedback_valid_for(
                relation,
                source,
                graph,
                requirements_by_id[requirement_id],
            )
            for requirement_id, rows in matched.items()
            if requirement_id in requirements_by_id
            for _, source in rows
        )
        if not valid:
            locally_repairable = any(
                _feedback_attached_to_skeleton(
                    relation,
                    source,
                    graph,
                    requirements_by_id[requirement_id],
                )
                and graph.protocols[relation.target_protocol.id].causes == ()
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


def _candidate_mechanic_families(candidate: ProtocolSkillKitCandidate) -> frozenset[str]:
    families: set[str] = set()
    if candidate.resources or any(
        effect.operation is not None
        and effect.operation.startswith("resource_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("resource")
    if candidate.states or any(
        effect.operation is not None
        and effect.operation.startswith("state_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("state")
    if candidate.summons or any(
        effect.operation is not None
        and effect.operation.startswith("summon_")
        for entry in candidate.entries
        for protocol in entry.protocols
        for effect in protocol.causes
    ):
        families.add("summon")
    return frozenset(families)


def _graph_payload(
    candidate: ProtocolSkillKitCandidate,
) -> tuple[dict[str, dict[str, object]], list[tuple[str, str, str]]]:
    graph = build_graph(candidate)
    role_centralities: dict[str, list[str]] = {}
    for evidence in candidate.role_evidence:
        for ref in evidence.effect_refs:
            if ref.kind == "effect":
                role_centralities.setdefault(ref.id, []).append(evidence.centrality)

    nodes: dict[str, dict[str, object]] = {}
    edges: list[tuple[str, str, str]] = []
    for pid, protocol in graph.protocols.items():
        trigger_subject = (
            protocol.when.subject.kind
            if protocol.when is not None and protocol.when.subject is not None
            else None
        )
        trigger_event = protocol.when.event if protocol.when is not None else None
        nodes[f"p:{pid}"] = {
            "kind": "protocol",
            "tags": [trigger_subject, trigger_event],
        }
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
            if effect.object_ref is not None and effect.object_ref.kind in {
                "resource",
                "state",
                "summon",
            }:
                lease_key = f"{effect.object_ref.kind}/{effect.object_ref.id}"
                if lease_key in graph.leases:
                    edges.append((f"e:{eid}", "targets", f"l:{lease_key}"))

    for kind, leases in (
        ("resource", candidate.resources),
        ("state", candidate.states),
        ("summon", candidate.summons),
    ):
        for lease in leases:
            lease_id = getattr(lease, f"{kind}_id")
            tags: list[object] = [lease.repeat_policy] if kind == "summon" else []
            nodes[f"l:{kind}/{lease_id}"] = {"kind": kind, "tags": tags}

    for relation in candidate.feedback_relations:
        source_node = f"e:{relation.source_effect.id}"
        target_node = f"p:{relation.target_protocol.id}"
        if source_node in nodes and target_node in nodes:
            edges.append(
                (
                    source_node,
                    f"feedback:{relation.event}:{relation.operation}",
                    target_node,
                )
            )

    lifecycle_slots = {
        "resource": {
            "opened_by": "opened_by",
            "used_or_transformed_by": "used_or_transformed_by",
            "closed_by": "closed_by",
        },
        "state": {
            "established_by": "established_by",
            "active_effects": "active_effects",
            "ended_or_replaced_by": "ended_or_replaced_by",
        },
        "summon": {
            "spawned_by": "spawned_by",
            "active_effects": "active_effects",
            "departed_or_replaced_by": "departed_or_replaced_by",
        },
    }
    for kind, leases in (
        ("resource", candidate.resources),
        ("state", candidate.states),
        ("summon", candidate.summons),
    ):
        for lease in leases:
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


def _weak_components(
    nodes: Mapping[str, dict[str, object]],
    edges: Sequence[tuple[str, str, str]],
) -> list[set[str]]:
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


def _fingerprint_graph(
    nodes: Mapping[str, dict[str, object]],
    edges: Sequence[tuple[str, str, str]],
) -> str:
    colors = {
        node: hashlib.sha256(
            _canonical_json({"kind": value["kind"], "tags": value["tags"]}).encode(
                "utf-8"
            )
        ).hexdigest()
        for node, value in nodes.items()
    }
    for _ in range(max(1, len(nodes))):
        next_colors: dict[str, str] = {}
        for node, value in nodes.items():
            incoming = sorted(
                [[label, colors[source]] for source, label, target in edges if target == node]
            )
            outgoing = sorted(
                [[label, colors[target]] for source, label, target in edges if source == node]
            )
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
    canonical_edges = sorted(
        [[colors[source], label, colors[target]] for source, label, target in edges]
    )
    return hashlib.sha256(
        _canonical_json({"nodes": canonical_nodes, "edges": canonical_edges}).encode("utf-8")
    ).hexdigest()


def _scoped_graphs(
    candidate: ProtocolSkillKitCandidate,
    scope: str,
    protocol_id: str | None = None,
) -> list[tuple[dict[str, dict[str, object]], list[tuple[str, str, str]]]]:
    nodes, edges = _graph_payload(candidate)
    if scope == "protocol":
        if protocol_id is None:
            return []
        protocol_node = f"p:{protocol_id}"
        keep = {protocol_node}
        keep.update(
            dst
            for source, label, dst in edges
            if source == protocol_node and label == "causes"
        )
        keep.update(
            dst
            for source, label, dst in edges
            if source in keep and label == "targets"
        )
        return [_induced_graph(nodes, edges, keep)]
    if scope == "connected_component":
        return [_induced_graph(nodes, edges, component) for component in _weak_components(nodes, edges)]
    raise ValueError(f"unsupported fingerprint scope: {scope}")


def _structural_fingerprint(
    candidate: ProtocolSkillKitCandidate,
    scope: str,
    protocol_id: str | None = None,
) -> str:
    graphs = _scoped_graphs(candidate, scope, protocol_id)
    if not graphs:
        return _fingerprint_graph({}, [])
    return _fingerprint_graph(*graphs[0])


def _reference_copying(
    candidate: ProtocolSkillKitCandidate,
    context: SkillValidationContext,
    findings: list[SkillFinding],
) -> None:
    review = context.reference_review_context
    if review is None:
        return
    expected = {
        "protocol": {
            item.sha256
            for item in review.structural_fingerprints
            if item.scope == "protocol"
        },
        "connected_component": {
            item.sha256
            for item in review.structural_fingerprints
            if item.scope == "connected_component"
        },
    }
    protocol_match = any(
        _structural_fingerprint(
            candidate,
            "protocol",
            f"{entry.ability_id}/{protocol.protocol_id}",
        )
        in expected["protocol"]
        for entry in candidate.entries
        for protocol in entry.protocols
    )
    component_match = any(
        _fingerprint_graph(*graph) in expected["connected_component"]
        for graph in _scoped_graphs(candidate, "connected_component")
    )
    if protocol_match or component_match:
        findings.append(
            _finding(
                "REFERENCE_COPYING",
                "/context/reference_review_context",
                repairable=False,
            )
        )


def evaluate(
    candidate: ProtocolSkillKitCandidate,
    context: SkillValidationContext | Mapping[str, object],
) -> SkillValidationReport:
    """Accumulate the frozen structural and bounded S1 semantic findings."""

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("evaluate expects a ProtocolSkillKitCandidate")
    context_value = _coerce_context(context)
    graph = build_graph(candidate)
    findings: list[SkillFinding] = []
    profile, profile_finding = _profile_or_finding(context_value.combat_role_profile)
    if profile_finding is not None:
        findings.append(profile_finding)
    if context_value.intent.hard_constraint_conflicts:
        findings.append(
            _finding(
                "HARD_CONSTRAINT_CONFLICT",
                "/context/intent/hard_constraint_conflicts",
                repairable=False,
            )
        )
    candidate_families = _candidate_mechanic_families(candidate)
    forbidden_paths = {
        "resource": "/resources",
        "state": "/states",
        "summon": "/summons",
    }
    for family in sorted(
        set(context_value.intent.forbidden_mechanic_families)
        & candidate_families
        & set(forbidden_paths)
    ):
        findings.append(
            _finding(
                f"FORBIDDEN_{family.upper()}_INTRODUCED",
                forbidden_paths[family],
                repairable=False,
            )
        )
    _validate_general_refs(candidate, graph, findings)
    _lifecycle_findings(candidate, graph, findings)
    matched = _mechanic_findings(candidate, context_value, graph, findings)
    _feedback_findings(
        candidate,
        matched,
        context_value.intent.mechanic_requirements,
        graph,
        findings,
    )
    for entry_index, protocol_index, _, protocol in _all_protocols(candidate):
        if (
            protocol.when is not None
            and protocol.when.subject is not None
            and protocol.when.subject.kind in {"ally", "team"}
            and (
                not protocol.when.subject.selector
                or protocol.when.event is None
            )
        ):
            findings.append(
                _finding(
                    "TRIGGER_SUBJECT_AMBIGUOUS",
                    f"/entries/{entry_index}/protocols/{protocol_index}/when",
                    repairable=True,
                    authorized_paths=(
                        f"/entries/{entry_index}/protocols/{protocol_index}/when",
                    ),
                )
            )
    _role_findings(candidate, profile, graph, findings)
    _reference_copying(candidate, context_value, findings)
    ordered = _dedupe_sort(findings)
    if any(not item.repairable for item in ordered):
        outcome = "FAIL"
    elif ordered:
        outcome = "REPAIR"
    else:
        outcome = "PASS"
    candidate_digest = candidate.digest
    context_digest = context_value.digest
    return SkillValidationReport(
        outcome=outcome,
        blocking=outcome != "PASS",
        repair_allowed=outcome == "REPAIR",
        findings=ordered,
        candidate_digest=candidate_digest,
        context_digest=context_digest,
        report_digest=_report_digest(candidate_digest, context_digest, ordered, outcome),
    )


__all__ = ["evaluate"]
