"""Structural-only SkillKit evaluation over the public domain contract.

This module intentionally reports representation and lifecycle findings only.
Mechanic matching, role alignment, reference copying, repair, rendering, and
runtime integration belong to later independently reviewed commits.  No
production caller is connected here yet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any

from ._graph import DerivedGraph, build_graph, exists_in_other_namespace, resolve_ref
from .context import VALIDATOR_CONTRACT, SkillValidationContext
from .models import (
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    ProtocolSkillKitCandidate,
    SkillFinding,
    SkillValidationReport,
    TypedRef,
)


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


def _context_plain(context: SkillValidationContext) -> dict[str, object]:
    return {
        "intent": _plain(context.intent),
        "combat_role_profile": _plain(context.combat_role_profile),
        "reference_review_context": _plain(context.reference_review_context),
        "validator_contract": VALIDATOR_CONTRACT,
    }


def _context_digest(context: SkillValidationContext) -> str:
    return hashlib.sha256(_canonical_json(_context_plain(context)).encode("utf-8")).hexdigest()


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


def evaluate(
    candidate: ProtocolSkillKitCandidate,
    context: SkillValidationContext | Mapping[str, object],
) -> SkillValidationReport:
    """Accumulate representation/lifecycle findings for a parsed candidate.

    The report scope is structural-only until later reviewed commits; this
    function intentionally does not perform mechanic, role, or copying
    evaluation and has no production caller yet.
    """

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("evaluate expects a ProtocolSkillKitCandidate")
    context_value = _coerce_context(context)
    graph = build_graph(candidate)
    findings: list[SkillFinding] = []
    _validate_general_refs(candidate, graph, findings)
    _lifecycle_findings(candidate, graph, findings)
    ordered = _dedupe_sort(findings)
    if any(not item.repairable for item in ordered):
        outcome = "FAIL"
    elif ordered:
        outcome = "REPAIR"
    else:
        outcome = "PASS"
    candidate_digest = candidate.digest
    context_digest = _context_digest(context_value)
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
