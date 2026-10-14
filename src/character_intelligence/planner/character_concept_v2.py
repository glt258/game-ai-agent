"""Compact, provider-independent concept-search contracts for Phase 4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from agents.response_contracts import (
    CHARACTER_CONCEPT_SEARCH_JSON_SCHEMA,
    CHARACTER_CONCEPT_SEED_JSON_SCHEMA,
    CHARACTER_CONCEPT_SELECTION_JSON_SCHEMA,
)

from .character_plan_v2 import CharacterPlanV2Source

_CONCEPT_FIELDS = frozenset(
    {
        "concept_id",
        "one_line_identity",
        "dramatic_axis",
        "character_contradiction",
        "player_hook",
        "relationship_axis",
        "gameplay_fantasy",
        "visual_anchor",
        "differentiation_basis",
        "major_risk",
    }
)
_DIVERSITY_AXES = (
    "dramatic_axis",
    "character_contradiction",
    "relationship_axis",
    "gameplay_fantasy",
    "visual_anchor",
)


class CharacterConceptSeedStatus(str, Enum):
    PROPOSED = "PROPOSED"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


class CharacterConceptV2Error(ValueError):
    """Raised when concept search or selection violates its contract."""


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterConceptV2Error(f"{field_name} must be a non-empty string")
    return value.strip()


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CharacterConceptV2Error(f"{field_name} must be an array of strings")
    result: list[str] = []
    for item in value:
        cleaned = _text(item, f"{field_name}[]")
        if cleaned not in result:
            result.append(cleaned)
    if not result:
        raise CharacterConceptV2Error(f"{field_name} must not be empty")
    return tuple(result)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterConceptV2Error(f"{field_name} must be an object")
    return value


@dataclass(frozen=True)
class CharacterConceptSeedV2:
    """One thin creative direction; it is never Canon or roster data."""

    concept_id: str
    one_line_identity: str
    dramatic_axis: str
    character_contradiction: str
    player_hook: str
    relationship_axis: str
    gameplay_fantasy: str
    visual_anchor: str
    differentiation_basis: tuple[str, ...]
    major_risk: str
    status: CharacterConceptSeedStatus = CharacterConceptSeedStatus.PROPOSED
    source: CharacterPlanV2Source = field(
        default=CharacterPlanV2Source.PLANNER_PROPOSAL,
        init=False,
    )

    def __post_init__(self) -> None:
        for field_name in _CONCEPT_FIELDS - {"differentiation_basis"}:
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(
            self,
            "differentiation_basis",
            _strings(self.differentiation_basis, "differentiation_basis"),
        )
        try:
            status = self.status if isinstance(self.status, CharacterConceptSeedStatus) else CharacterConceptSeedStatus(self.status)
        except (TypeError, ValueError) as error:
            raise CharacterConceptV2Error("status is invalid") from error
        object.__setattr__(self, "status", status)
        if self.source is not CharacterPlanV2Source.PLANNER_PROPOSAL:
            raise CharacterConceptV2Error("concept seed source must be PLANNER_PROPOSAL")

    @classmethod
    def from_provider_mapping(cls, value: Mapping[str, Any]) -> "CharacterConceptSeedV2":
        data = _mapping(value, "concept seed")
        if set(data) != _CONCEPT_FIELDS:
            unknown = sorted(set(data) - _CONCEPT_FIELDS)
            missing = sorted(_CONCEPT_FIELDS - set(data))
            raise CharacterConceptV2Error(
                f"concept seed fields are invalid; missing={missing}, unknown={unknown}"
            )
        return cls(**{field_name: data[field_name] for field_name in _CONCEPT_FIELDS})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CharacterConceptSeedV2":
        data = _mapping(value, "concept seed")
        allowed = _CONCEPT_FIELDS | {"status", "source"}
        unknown = set(data) - allowed
        if unknown:
            raise CharacterConceptV2Error(
                f"concept seed has unknown field(s): {sorted(unknown)}"
            )
        source = data.get("source", CharacterPlanV2Source.PLANNER_PROPOSAL)
        if source is not CharacterPlanV2Source.PLANNER_PROPOSAL:
            try:
                source = CharacterPlanV2Source(source)
            except (TypeError, ValueError) as error:
                raise CharacterConceptV2Error("concept seed source is invalid") from error
        if source is not CharacterPlanV2Source.PLANNER_PROPOSAL:
            raise CharacterConceptV2Error("concept seed source must be PLANNER_PROPOSAL")
        return cls(
            **{field_name: data[field_name] for field_name in _CONCEPT_FIELDS},
            status=data.get("status", CharacterConceptSeedStatus.PROPOSED),
        )

    def with_status(self, status: CharacterConceptSeedStatus) -> "CharacterConceptSeedV2":
        return replace(self, status=status)

    def to_provider_dict(self) -> dict[str, Any]:
        return {
            field_name: (
                list(self.differentiation_basis)
                if field_name == "differentiation_basis"
                else getattr(self, field_name)
            )
            for field_name in sorted(_CONCEPT_FIELDS)
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.to_provider_dict()
        result["status"] = self.status.value
        result["source"] = self.source.value
        return result


@dataclass(frozen=True)
class CharacterConceptSelectionV2:
    """Selector decision that points to an existing seed by ID only."""

    selected_concept_id: str
    selection_reasons: tuple[str, ...]
    tradeoffs: tuple[str, ...] = ()
    preserve_elements: tuple[str, ...] = ()
    rejected_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_concept_id", _text(self.selected_concept_id, "selected_concept_id"))
        object.__setattr__(self, "selection_reasons", _strings(self.selection_reasons, "selection_reasons"))
        for field_name in ("tradeoffs", "preserve_elements", "rejected_reasons"):
            value = getattr(self, field_name)
            if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
                raise CharacterConceptV2Error(f"{field_name} must be an array")
            object.__setattr__(self, field_name, tuple(_text(item, f"{field_name}[]") for item in value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_concept_id": self.selected_concept_id,
            "selection_reasons": list(self.selection_reasons),
            "tradeoffs": list(self.tradeoffs),
            "preserve_elements": list(self.preserve_elements),
            "rejected_reasons": list(self.rejected_reasons),
        }


def build_character_concept_seed_schema() -> dict[str, Any]:
    return deepcopy(dict(CHARACTER_CONCEPT_SEED_JSON_SCHEMA))


def build_character_concept_search_schema() -> dict[str, Any]:
    return deepcopy(dict(CHARACTER_CONCEPT_SEARCH_JSON_SCHEMA))


def build_character_concept_selection_schema() -> dict[str, Any]:
    return deepcopy(dict(CHARACTER_CONCEPT_SELECTION_JSON_SCHEMA))


def validate_concept_seed_set(
    seeds: Sequence[CharacterConceptSeedV2],
) -> tuple[CharacterConceptSeedV2, ...]:
    result = tuple(seeds)
    if len(result) != 3:
        raise CharacterConceptV2Error("Concept Search must produce exactly three seeds")
    if not all(isinstance(seed, CharacterConceptSeedV2) for seed in result):
        raise CharacterConceptV2Error("Concept Search returned an invalid seed")
    concept_ids = [seed.concept_id for seed in result]
    if len(set(concept_ids)) != len(concept_ids):
        raise CharacterConceptV2Error("Concept Search concept IDs must be unique")
    distinct_axes = [
        axis
        for axis in _DIVERSITY_AXES
        if len({_normalized(getattr(seed, axis)) for seed in result}) > 1
    ]
    if len(distinct_axes) < 3:
        raise CharacterConceptV2Error(
            "Concept seeds are insufficiently diverse across design axes"
        )
    return result


def validate_character_concept_search_response(
    value: object,
) -> tuple[CharacterConceptSeedV2, ...]:
    data = _mapping(value, "Concept Search response")
    if set(data) != {"concepts"}:
        raise CharacterConceptV2Error(
            "Concept Search response must contain only concepts"
        )
    concepts = data["concepts"]
    if isinstance(concepts, (str, bytes)) or not isinstance(concepts, Sequence):
        raise CharacterConceptV2Error("Concept Search concepts must be an array")
    seeds = tuple(CharacterConceptSeedV2.from_provider_mapping(item) for item in concepts)
    return validate_concept_seed_set(seeds)


def validate_character_concept_selection(
    value: object,
    seeds: Sequence[CharacterConceptSeedV2],
) -> CharacterConceptSelectionV2:
    valid_seeds = validate_concept_seed_set(seeds)
    data = _mapping(value, "Concept Selector response")
    allowed = {
        "selected_concept_id",
        "selection_reasons",
        "tradeoffs",
        "preserve_elements",
        "rejected_reasons",
    }
    unknown = set(data) - allowed
    if unknown or "selected_concept_id" not in data or "selection_reasons" not in data:
        raise CharacterConceptV2Error(
            f"Concept Selector response fields are invalid; unknown={sorted(unknown)}"
        )
    selection = CharacterConceptSelectionV2(
        selected_concept_id=data["selected_concept_id"],
        selection_reasons=data["selection_reasons"],
        tradeoffs=data.get("tradeoffs", ()),
        preserve_elements=data.get("preserve_elements", ()),
        rejected_reasons=data.get("rejected_reasons", ()),
    )
    if selection.selected_concept_id not in {seed.concept_id for seed in valid_seeds}:
        raise CharacterConceptV2Error(
            f"Concept Selector selected unknown concept ID: {selection.selected_concept_id}"
        )
    return selection


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


__all__ = [
    "CharacterConceptSeedStatus",
    "CharacterConceptV2Error",
    "CharacterConceptSeedV2",
    "CharacterConceptSelectionV2",
    "build_character_concept_seed_schema",
    "build_character_concept_search_schema",
    "build_character_concept_selection_schema",
    "validate_concept_seed_set",
    "validate_character_concept_search_response",
    "validate_character_concept_selection",
]
