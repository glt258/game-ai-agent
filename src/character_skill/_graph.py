"""Private immutable indexes for structural SkillKit evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .models import (
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    ProtocolSkillKitCandidate,
    TypedRef,
)


@dataclass(frozen=True)
class EffectLocation:
    entry: AbilityEntry
    protocol: BehaviorProtocol
    effect: Effect
    effect_ref: TypedRef
    protocol_ref: TypedRef


@dataclass(frozen=True)
class DerivedGraph:
    protocols: Mapping[str, BehaviorProtocol]
    effects: Mapping[str, EffectLocation]
    leases: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocols", MappingProxyType(dict(self.protocols)))
        object.__setattr__(self, "effects", MappingProxyType(dict(self.effects)))
        object.__setattr__(self, "leases", MappingProxyType(dict(self.leases)))


def build_graph(candidate: ProtocolSkillKitCandidate) -> DerivedGraph:
    """Index protocol/effect paths and typed lease namespaces privately."""

    protocols: dict[str, BehaviorProtocol] = {}
    effects: dict[str, EffectLocation] = {}
    leases: dict[str, object] = {}
    for entry in candidate.entries:
        for protocol in entry.protocols:
            protocol_id = f"{entry.ability_id}/{protocol.protocol_id}"
            protocol_ref = TypedRef("protocol", protocol_id)
            protocols[protocol_id] = protocol
            for effect in protocol.causes:
                effect_id = f"{protocol_id}/{effect.effect_id}"
                effects[effect_id] = EffectLocation(
                    entry=entry,
                    protocol=protocol,
                    effect=effect,
                    effect_ref=TypedRef("effect", effect_id),
                    protocol_ref=protocol_ref,
                )
    for lease in candidate.resources:
        leases[f"resource/{lease.resource_id}"] = lease
    for lease in candidate.states:
        leases[f"state/{lease.state_id}"] = lease
    for lease in candidate.summons:
        leases[f"summon/{lease.summon_id}"] = lease
    return DerivedGraph(protocols, effects, leases)


def resolve_ref(ref: TypedRef, graph: DerivedGraph) -> object | None:
    """Resolve a typed reference in its declared namespace."""

    if ref.kind == "protocol":
        return graph.protocols.get(ref.id)
    if ref.kind == "effect":
        return graph.effects.get(ref.id)
    return graph.leases.get(f"{ref.kind}/{ref.id}")


def exists_in_other_namespace(ref: TypedRef, graph: DerivedGraph) -> bool:
    """Return whether the same textual ID is live under another typed kind."""

    for kind in ("protocol", "effect", "resource", "state", "summon"):
        if kind == ref.kind:
            continue
        if resolve_ref(TypedRef(kind, ref.id), graph) is not None:
            return True
    return False
