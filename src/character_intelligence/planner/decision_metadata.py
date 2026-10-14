"""Small, request-scoped metadata for character-planning decisions.

This module deliberately does not carry character values.  Existing planning
contracts remain the source of truth; these records explain ownership,
provenance, and resolution state at a bounded decision path.  The Phase 7
SELECT route consumes the contract only after Concept Search and Selector;
legacy Phase 4 callers remain unchanged and the metadata layer never calls a
provider or mutates a planning object.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar

DECISION_METADATA_SCHEMA = "character-decision-metadata/v1"
_DECISION_PATH_ROOTS = frozenset(
    {
        "arc_seed",
        "character_core",
        "gameplay_identity",
        "narrative_role",
        "product_roster_positioning",
        "relationship_strategy",
        "request",
        "selected_concept_seed",
        "visual_identity",
    }
)
_PATH_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")


class DecisionMetadataError(ValueError):
    """Raised when metadata would violate the ownership contract."""


class DecisionOwner(str, Enum):
    """Who owns the decision slot, independent of where evidence came from."""

    USER = "USER"
    CANON = "CANON"
    AI = "AI"
    SYSTEM = "SYSTEM"
    UNRESOLVED = "UNRESOLVED"


class DecisionSource(str, Enum):
    """The bounded stage or authority that produced the metadata value."""

    USER_BRIEF = "USER_BRIEF"
    CANON = "CANON"
    CONCEPT_SEARCH = "CONCEPT_SEARCH"
    SELECTOR = "SELECTOR"
    PLANNER = "PLANNER"
    SYSTEM_POLICY = "SYSTEM_POLICY"
    CANON_GROUNDING = "CANON_GROUNDING"


class DecisionResolutionStatus(str, Enum):
    """Resolution state, not an operation such as SELECT or MIX."""

    PROPOSED = "PROPOSED"
    RESOLVED = "RESOLVED"
    LOCKED = "LOCKED"
    UNRESOLVED = "UNRESOLVED"


class DecisionResolutionMode(str, Enum):
    """Resolution modes understood by the input and resolver contracts."""

    LEGACY_AI_SELECT = "LEGACY_AI_SELECT"
    AI_DECIDE = "AI_DECIDE"
    USER_DECIDE = "USER_DECIDE"


# Public short name for the P7.4 contract.  The P7.2 name remains canonical
# for backward compatibility with existing metadata callers.
ResolutionMode = DecisionResolutionMode


class ResolutionAction(str, Enum):
    """What a resolution operation did, independent of who performed it."""

    SELECT = "SELECT"
    MIX = "MIX"
    KEEP_BOTH = "KEEP_BOTH"
    REQUEST_MORE = "REQUEST_MORE"
    REVISE = "REVISE"


class CandidateDecisionOutcome(str, Enum):
    """Outcome metadata for a candidate without copying its seed value."""

    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


_T = TypeVar("_T")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be non-empty")
    return cleaned


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _enum(enum_type: type[_T], value: object, field_name: str) -> _T:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(str(item.value) for item in enum_type)  # type: ignore[union-attr]
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _sequence(value: object, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(value)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Normalize selector text while retaining its contract-defined order."""

    return tuple(_text(item, field_name) for item in _sequence(value, field_name))


def _path_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Normalize references through the single P7.2 decision-path registry."""

    return tuple(
        _validate_decision_path(item)
        for item in _sequence(value, field_name)
    )


def _validate_decision_path(value: object) -> str:
    path = _text(value, "decision_path")
    parts = path.split(".")
    if parts[0] not in _DECISION_PATH_ROOTS:
        raise DecisionMetadataError(
            f"decision_path root is not bounded by the V2 schema: {parts[0]!r}"
        )
    for index, part in enumerate(parts):
        if part == "*" and index == len(parts) - 1:
            continue
        if not _PATH_SEGMENT.fullmatch(part):
            raise DecisionMetadataError(f"decision_path is not canonical: {path!r}")
    return path


def _validate_action_status(
    action: ResolutionAction,
    status: DecisionResolutionStatus,
) -> None:
    """Keep action semantics explicit instead of accepting arbitrary pairs."""

    allowed = {
        ResolutionAction.SELECT: {DecisionResolutionStatus.RESOLVED},
        ResolutionAction.MIX: {
            DecisionResolutionStatus.RESOLVED,
            DecisionResolutionStatus.UNRESOLVED,
        },
        ResolutionAction.KEEP_BOTH: {DecisionResolutionStatus.RESOLVED},
        ResolutionAction.REQUEST_MORE: {DecisionResolutionStatus.UNRESOLVED},
        ResolutionAction.REVISE: {DecisionResolutionStatus.UNRESOLVED},
    }
    if status not in allowed[action]:
        raise DecisionMetadataError(
            f"{action.value} cannot use resolution status {status.value}"
        )


@dataclass(frozen=True)
class DecisionProvenance:
    """Small references to the source event; never a copy of a seed or plan."""

    source_id: str | None = None
    source_invocation_id: str | None = None
    candidate_id: str | None = None
    resolved_from: str | None = None
    request_field: str | None = None
    resolution_mode: DecisionResolutionMode | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "source_id",
            "source_invocation_id",
            "candidate_id",
            "resolved_from",
            "request_field",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "resolution_mode",
            None
            if self.resolution_mode is None
            else _enum(DecisionResolutionMode, self.resolution_mode, "resolution_mode"),
        )
        if self.resolved_from is not None and self.candidate_id != self.resolved_from:
            raise DecisionMetadataError(
                "resolved_from must match candidate_id for candidate-backed metadata"
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in (
            "source_id",
            "source_invocation_id",
            "candidate_id",
            "resolved_from",
            "request_field",
            "resolution_mode",
        ):
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value.value if isinstance(value, Enum) else value
        return result


@dataclass(frozen=True)
class DecisionRecord:
    """Ownership and resolution metadata for a path in an existing contract."""

    decision_path: str
    owner: DecisionOwner
    source: DecisionSource
    resolution_status: DecisionResolutionStatus
    provenance: DecisionProvenance = DecisionProvenance()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_path", _validate_decision_path(self.decision_path))
        object.__setattr__(self, "owner", _enum(DecisionOwner, self.owner, "owner"))
        object.__setattr__(self, "source", _enum(DecisionSource, self.source, "source"))
        object.__setattr__(
            self,
            "resolution_status",
            _enum(DecisionResolutionStatus, self.resolution_status, "resolution_status"),
        )
        if not isinstance(self.provenance, DecisionProvenance):
            raise TypeError("provenance must be DecisionProvenance")
        self._validate_authority_pair()

    def _validate_authority_pair(self) -> None:
        owner = self.owner
        source = self.source
        status = self.resolution_status
        provenance = self.provenance

        if owner is DecisionOwner.AI and status is DecisionResolutionStatus.LOCKED:
            raise DecisionMetadataError("AI proposals cannot create LOCKED decisions")
        if owner is DecisionOwner.USER and (
            source is not DecisionSource.USER_BRIEF
            or status is not DecisionResolutionStatus.LOCKED
            or provenance.request_field is None
        ):
            raise DecisionMetadataError(
                "USER decisions must be explicit USER_BRIEF fields and LOCKED"
            )
        if owner is DecisionOwner.CANON and (
            source is not DecisionSource.CANON
            or status is not DecisionResolutionStatus.LOCKED
            or provenance.source_id is None
        ):
            raise DecisionMetadataError(
                "CANON decisions must be source-backed and LOCKED"
            )
        if owner is DecisionOwner.UNRESOLVED and (
            source not in {DecisionSource.CANON, DecisionSource.SYSTEM_POLICY}
            or status is not DecisionResolutionStatus.UNRESOLVED
        ):
            raise DecisionMetadataError(
                "UNRESOLVED decisions must retain an unresolved Canon/system source"
            )
        if owner is DecisionOwner.SYSTEM and (
            source not in {DecisionSource.SYSTEM_POLICY, DecisionSource.CANON_GROUNDING}
            or status not in {
                DecisionResolutionStatus.RESOLVED,
                DecisionResolutionStatus.LOCKED,
            }
        ):
            raise DecisionMetadataError(
                "SYSTEM decisions must come from bounded system policy/grounding"
            )
        if source is DecisionSource.USER_BRIEF and owner is not DecisionOwner.USER:
            raise DecisionMetadataError("USER_BRIEF cannot assign a non-user owner")
        if source is DecisionSource.CANON and owner not in {
            DecisionOwner.CANON,
            DecisionOwner.UNRESOLVED,
        }:
            raise DecisionMetadataError("CANON cannot assign an AI or system owner")
        if source in {DecisionSource.CONCEPT_SEARCH, DecisionSource.PLANNER} and (
            owner is not DecisionOwner.AI
            or status is not DecisionResolutionStatus.PROPOSED
        ):
            raise DecisionMetadataError(
                f"{source.value} must remain an AI PROPOSED decision"
            )
        if source is DecisionSource.SELECTOR and owner is not DecisionOwner.AI:
            raise DecisionMetadataError("SELECTOR metadata must remain AI-owned")
        if source in {DecisionSource.CONCEPT_SEARCH, DecisionSource.SELECTOR} and (
            provenance.candidate_id is None
        ):
            raise DecisionMetadataError(
                f"{source.value} metadata must reference a candidate_id"
            )
        if source is DecisionSource.SELECTOR and status is DecisionResolutionStatus.RESOLVED:
            if (
                provenance.resolution_mode is not DecisionResolutionMode.LEGACY_AI_SELECT
                or provenance.resolved_from is None
            ):
                raise DecisionMetadataError(
                    "legacy selector resolution must record mode and resolved_from"
                )

    @classmethod
    def user_locked(cls, decision_path: str, request_field: str) -> "DecisionRecord":
        """Create metadata for one explicitly supplied user requirement."""

        return cls(
            decision_path,
            DecisionOwner.USER,
            DecisionSource.USER_BRIEF,
            DecisionResolutionStatus.LOCKED,
            DecisionProvenance(request_field=request_field),
        )

    @classmethod
    def canon_locked(cls, decision_path: str, source_id: str) -> "DecisionRecord":
        """Create metadata for one source-backed Canon value."""

        return cls(
            decision_path,
            DecisionOwner.CANON,
            DecisionSource.CANON,
            DecisionResolutionStatus.LOCKED,
            DecisionProvenance(source_id=source_id),
        )

    @classmethod
    def unresolved_gap(cls, decision_path: str) -> "DecisionRecord":
        """Represent missing Canon/system knowledge without resolving it."""

        return cls(
            decision_path,
            DecisionOwner.UNRESOLVED,
            DecisionSource.CANON,
            DecisionResolutionStatus.UNRESOLVED,
        )

    @classmethod
    def ai_proposal(
        cls,
        decision_path: str,
        candidate_id: str,
        *,
        source_invocation_id: str | None = None,
    ) -> "DecisionRecord":
        """Create a concept-search proposal without treating it as resolved."""

        return cls(
            decision_path,
            DecisionOwner.AI,
            DecisionSource.CONCEPT_SEARCH,
            DecisionResolutionStatus.PROPOSED,
            DecisionProvenance(
                candidate_id=candidate_id,
                source_invocation_id=source_invocation_id,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_path": self.decision_path,
            "owner": self.owner.value,
            "source": self.source.value,
            "resolution_status": self.resolution_status.value,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class CandidateDecisionMetadata:
    """Lineage for a candidate without storing its CharacterConceptSeedV2 value."""

    candidate_id: str
    outcome: CandidateDecisionOutcome
    reason_available: bool = False
    source_invocation_id: str | None = None
    selector_invocation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        object.__setattr__(
            self,
            "outcome",
            _enum(CandidateDecisionOutcome, self.outcome, "outcome"),
        )
        if not isinstance(self.reason_available, bool):
            raise TypeError("reason_available must be a boolean")
        for field_name in ("source_invocation_id", "selector_invocation_id"):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "outcome": self.outcome.value,
            "reason_available": self.reason_available,
        }
        if self.source_invocation_id is not None:
            result["source_invocation_id"] = self.source_invocation_id
        if self.selector_invocation_id is not None:
            result["selector_invocation_id"] = self.selector_invocation_id
        return result


@dataclass(frozen=True)
class DecisionMetadataSet:
    """Bounded immutable request-scoped records and candidate lineage."""

    records: tuple[DecisionRecord, ...] = ()
    candidates: tuple[CandidateDecisionMetadata, ...] = ()

    def __post_init__(self) -> None:
        records = _sequence(self.records, "records")
        candidates = _sequence(self.candidates, "candidates")
        if not all(isinstance(item, DecisionRecord) for item in records):
            raise TypeError("records must contain DecisionRecord values")
        if not all(isinstance(item, CandidateDecisionMetadata) for item in candidates):
            raise TypeError(
                "candidates must contain CandidateDecisionMetadata values"
            )

        ordered_records = tuple(sorted(records, key=lambda item: item.decision_path))
        paths = [item.decision_path for item in ordered_records]
        if len(paths) != len(set(paths)):
            raise DecisionMetadataError(
                "DecisionMetadataSet cannot contain duplicate decision paths"
            )
        ordered_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
        candidate_ids = [item.candidate_id for item in ordered_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise DecisionMetadataError(
                "DecisionMetadataSet cannot contain duplicate candidate IDs"
            )
        known_ids = set(candidate_ids)
        for record in ordered_records:
            for candidate_id in (
                record.provenance.candidate_id,
                record.provenance.resolved_from,
            ):
                if candidate_id is not None and candidate_id not in known_ids:
                    raise DecisionMetadataError(
                        f"candidate provenance references unknown candidate: {candidate_id}"
                    )
        object.__setattr__(self, "records", ordered_records)
        object.__setattr__(self, "candidates", ordered_candidates)

    @classmethod
    def from_selector(
        cls,
        seeds: Sequence[object],
        selection: object,
        *,
        source_invocation_id: str | None = None,
        selector_invocation_id: str | None = None,
    ) -> "DecisionMetadataSet":
        """Overlay legacy selector resolution without changing seeds or selection.

        The helper validates the existing Phase 4 contracts, records every
        candidate outcome, and marks the one selected branch as a compatibility
        resolution.  It does not mutate a seed and does not call a provider.
        """

        from .character_concept_v2 import (
            CharacterConceptSeedV2,
            CharacterConceptSelectionV2,
            validate_concept_seed_set,
        )

        if not isinstance(selection, CharacterConceptSelectionV2):
            raise TypeError("selection must be CharacterConceptSelectionV2")
        if not isinstance(seeds, Sequence) or isinstance(seeds, (str, bytes)):
            raise TypeError("seeds must be a sequence")
        if not all(isinstance(seed, CharacterConceptSeedV2) for seed in seeds):
            raise TypeError("seeds must contain CharacterConceptSeedV2 values")
        try:
            valid_seeds = validate_concept_seed_set(seeds)
        except Exception as exc:
            raise DecisionMetadataError("selector lineage received invalid seeds") from exc
        candidate_ids = {seed.concept_id for seed in valid_seeds}
        selected_id = selection.selected_concept_id
        if selected_id not in candidate_ids:
            raise DecisionMetadataError(
                f"selector lineage references unknown candidate: {selected_id}"
            )

        candidates = tuple(
            CandidateDecisionMetadata(
                candidate_id=seed.concept_id,
                outcome=(
                    CandidateDecisionOutcome.SELECTED
                    if seed.concept_id == selected_id
                    else CandidateDecisionOutcome.REJECTED
                ),
                reason_available=(
                    bool(selection.selection_reasons)
                    if seed.concept_id == selected_id
                    else bool(selection.rejected_reasons)
                ),
                source_invocation_id=source_invocation_id,
                selector_invocation_id=selector_invocation_id,
            )
            for seed in valid_seeds
        )
        record = DecisionRecord(
            decision_path="selected_concept_seed",
            owner=DecisionOwner.AI,
            source=DecisionSource.SELECTOR,
            resolution_status=DecisionResolutionStatus.RESOLVED,
            provenance=DecisionProvenance(
                source_invocation_id=selector_invocation_id,
                candidate_id=selected_id,
                resolved_from=selected_id,
                resolution_mode=DecisionResolutionMode.LEGACY_AI_SELECT,
            ),
        )
        return cls(records=(record,), candidates=candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DECISION_METADATA_SCHEMA,
            "records": [item.to_dict() for item in self.records],
            "candidates": [item.to_dict() for item in self.candidates],
        }


@dataclass(frozen=True)
class CandidateLineage:
    """Request-scoped origin and selector state for one immutable candidate."""

    candidate_id: str
    origin: DecisionSource
    origin_invocation_id: str | None
    selector_outcome: CandidateDecisionOutcome
    selector_reason_available: bool
    tradeoff_available: bool
    decision_metadata_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "origin", _enum(DecisionSource, self.origin, "origin"))
        if self.origin is not DecisionSource.CONCEPT_SEARCH:
            raise DecisionMetadataError(
                "current candidate lineage must originate from CONCEPT_SEARCH"
            )
        object.__setattr__(
            self,
            "origin_invocation_id",
            _optional_text(self.origin_invocation_id, "origin_invocation_id"),
        )
        object.__setattr__(
            self,
            "selector_outcome",
            _enum(CandidateDecisionOutcome, self.selector_outcome, "selector_outcome"),
        )
        for field_name in ("selector_reason_available", "tradeoff_available"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        refs = tuple(_validate_decision_path(item) for item in _sequence(
            self.decision_metadata_refs, "decision_metadata_refs"
        ))
        if len(refs) != len(set(refs)):
            raise DecisionMetadataError("decision_metadata_refs cannot contain duplicates")
        object.__setattr__(self, "decision_metadata_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "origin": self.origin.value,
            "origin_invocation_id": self.origin_invocation_id,
            "selector_outcome": self.selector_outcome.value,
            "selector_reason_available": self.selector_reason_available,
            "tradeoff_available": self.tradeoff_available,
            "decision_metadata_refs": list(self.decision_metadata_refs),
        }


@dataclass(frozen=True)
class CharacterCandidateSet:
    """The three Phase 4 seeds plus lineage retained for one request only."""

    candidates: tuple[object, ...]
    lineage: tuple[CandidateLineage, ...]
    selected_candidate_id: str | None = None

    def __post_init__(self) -> None:
        from .character_concept_v2 import CharacterConceptSeedV2

        candidates = _sequence(self.candidates, "candidates")
        lineage = _sequence(self.lineage, "lineage")
        if len(candidates) != 3:
            raise DecisionMetadataError(
                "CharacterCandidateSet must contain exactly three Phase 4 candidates"
            )
        if not all(isinstance(item, CharacterConceptSeedV2) for item in candidates):
            raise TypeError("candidates must contain CharacterConceptSeedV2 values")
        if not all(isinstance(item, CandidateLineage) for item in lineage):
            raise TypeError("lineage must contain CandidateLineage values")

        ordered_candidates = tuple(sorted(candidates, key=lambda item: item.concept_id))
        candidate_ids = tuple(item.concept_id for item in ordered_candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise DecisionMetadataError("CharacterCandidateSet cannot contain duplicate IDs")
        ordered_lineage = tuple(sorted(lineage, key=lambda item: item.candidate_id))
        lineage_ids = tuple(item.candidate_id for item in ordered_lineage)
        if lineage_ids != candidate_ids:
            raise DecisionMetadataError(
                "candidate lineage must cover exactly the immutable candidate set"
            )
        selected_id = _optional_text(self.selected_candidate_id, "selected_candidate_id")
        if selected_id is not None and selected_id not in candidate_ids:
            raise DecisionMetadataError(
                f"selected_candidate_id references unknown candidate: {selected_id}"
            )
        object.__setattr__(self, "candidates", ordered_candidates)
        object.__setattr__(self, "lineage", ordered_lineage)
        object.__setattr__(self, "selected_candidate_id", selected_id)

    def get(self, candidate_id: str) -> object:
        """Return a candidate by exact ID; unknown IDs fail closed."""

        requested_id = _text(candidate_id, "candidate_id")
        for candidate in self.candidates:
            if candidate.concept_id == requested_id:
                return candidate
        raise DecisionMetadataError(f"unknown candidate_id: {requested_id}")

    def lineage_for(self, candidate_id: str) -> CandidateLineage:
        """Return lineage by exact ID; unknown IDs fail closed."""

        requested_id = _text(candidate_id, "candidate_id")
        for item in self.lineage:
            if item.candidate_id == requested_id:
                return item
        raise DecisionMetadataError(f"unknown candidate_id: {requested_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "lineage": [item.to_dict() for item in self.lineage],
            "selected_candidate_id": self.selected_candidate_id,
        }


@dataclass(frozen=True)
class CharacterResolutionInput:
    """Pure, request-scoped input shared by every resolution mode.

    ``recommended_candidate_id`` is a compatibility recommendation, never a
    final user decision.  The filtered decision properties expose locked
    decisions, AI proposals, and unresolved Canon/system gaps without copying
    candidate values or changing any current production runtime stage.
    """

    candidate_set: CharacterCandidateSet
    decision_metadata: DecisionMetadataSet
    selection_reasons: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    preserve_elements: tuple[str, ...]
    rejected_reasons: tuple[str, ...]
    current_resolution_mode: DecisionResolutionMode
    recommended_candidate_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_set, CharacterCandidateSet):
            raise TypeError("candidate_set must be CharacterCandidateSet")
        if not isinstance(self.decision_metadata, DecisionMetadataSet):
            raise TypeError("decision_metadata must be DecisionMetadataSet")
        for field_name in (
            "selection_reasons",
            "tradeoffs",
            "preserve_elements",
            "rejected_reasons",
        ):
            object.__setattr__(
                self,
                field_name,
                _string_tuple(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "current_resolution_mode",
            _enum(
                DecisionResolutionMode,
                self.current_resolution_mode,
                "current_resolution_mode",
            ),
        )
        recommended_id = _optional_text(
            self.recommended_candidate_id, "recommended_candidate_id"
        )
        if recommended_id is not None:
            self.candidate_set.get(recommended_id)
        if (
            self.current_resolution_mode is DecisionResolutionMode.LEGACY_AI_SELECT
            and recommended_id is None
        ):
            raise DecisionMetadataError(
                "LEGACY_AI_SELECT requires a recommended candidate ID"
            )
        object.__setattr__(self, "recommended_candidate_id", recommended_id)

    @property
    def locked_decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(
            item
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.LOCKED
        )

    @property
    def proposed_decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(
            item
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.PROPOSED
        )

    @property
    def unresolved_decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(
            item
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.UNRESOLVED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_set": self.candidate_set.to_dict(),
            "decision_metadata": self.decision_metadata.to_dict(),
            "selector_comparative_metadata": {
                "selection_reasons": list(self.selection_reasons),
                "tradeoffs": list(self.tradeoffs),
                "preserve_elements": list(self.preserve_elements),
                "rejected_reasons": list(self.rejected_reasons),
            },
            "locked_decisions": [item.to_dict() for item in self.locked_decisions],
            "proposed_decisions": [item.to_dict() for item in self.proposed_decisions],
            "unresolved_decisions": [
                item.to_dict() for item in self.unresolved_decisions
            ],
            "current_resolution_mode": self.current_resolution_mode.value,
            "recommended_candidate_id": self.recommended_candidate_id,
        }


@dataclass(frozen=True)
class ResolutionRationale:
    """Selector evidence retained as rationale, not upgraded to authority."""

    selection_reasons: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    preserve_elements: tuple[str, ...] = ()
    rejected_reasons: tuple[str, ...] = ()
    request_more_reason: str | None = None
    requested_direction_hints: tuple[str, ...] = ()

    @classmethod
    def from_input(cls, resolution_input: CharacterResolutionInput) -> "ResolutionRationale":
        """Retain comparative selector evidence without changing its meaning."""

        if not isinstance(resolution_input, CharacterResolutionInput):
            raise TypeError("resolution_input must be CharacterResolutionInput")
        return cls(
            selection_reasons=resolution_input.selection_reasons,
            tradeoffs=resolution_input.tradeoffs,
            preserve_elements=resolution_input.preserve_elements,
            rejected_reasons=resolution_input.rejected_reasons,
        )

    def __post_init__(self) -> None:
        for field_name in (
            "selection_reasons",
            "tradeoffs",
            "preserve_elements",
            "rejected_reasons",
            "requested_direction_hints",
        ):
            object.__setattr__(
                self,
                field_name,
                _string_tuple(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "request_more_reason",
            _optional_text(self.request_more_reason, "request_more_reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_reasons": list(self.selection_reasons),
            "tradeoffs": list(self.tradeoffs),
            "preserve_elements": list(self.preserve_elements),
            "rejected_reasons": list(self.rejected_reasons),
            "request_more_reason": self.request_more_reason,
            "requested_direction_hints": list(self.requested_direction_hints),
        }


@dataclass(frozen=True)
class ResolvedDecision:
    """One path-level resolution reference without copying candidate values."""

    decision_path: str
    action: ResolutionAction
    source_candidate_ids: tuple[str, ...]
    resolution_status: DecisionResolutionStatus
    source_decision_refs: tuple[str, ...] = ()
    provenance: DecisionProvenance = DecisionProvenance()
    base_candidate_id: str | None = None
    revision_targets: tuple[str, ...] = ()
    revision_constraints: tuple[str, ...] = ()
    coexistable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_path", _validate_decision_path(self.decision_path))
        object.__setattr__(self, "action", _enum(ResolutionAction, self.action, "action"))
        object.__setattr__(
            self,
            "resolution_status",
            _enum(
                DecisionResolutionStatus,
                self.resolution_status,
                "resolution_status",
            ),
        )
        _validate_action_status(self.action, self.resolution_status)
        source_ids = _string_tuple(self.source_candidate_ids, "source_candidate_ids")
        if len(source_ids) != len(set(source_ids)):
            raise DecisionMetadataError("source_candidate_ids cannot contain duplicates")
        refs = _path_tuple(self.source_decision_refs, "source_decision_refs")
        if len(refs) != len(set(refs)):
            raise DecisionMetadataError("source_decision_refs cannot contain duplicates")
        if not isinstance(self.provenance, DecisionProvenance):
            raise TypeError("provenance must be DecisionProvenance")
        if not isinstance(self.coexistable, bool):
            raise TypeError("coexistable must be a boolean")

        base_candidate_id = _optional_text(self.base_candidate_id, "base_candidate_id")
        revision_targets = _path_tuple(self.revision_targets, "revision_targets")
        revision_constraints = _string_tuple(
            self.revision_constraints, "revision_constraints"
        )
        if len(revision_targets) != len(set(revision_targets)):
            raise DecisionMetadataError("revision_targets cannot contain duplicates")
        if self.action is ResolutionAction.REQUEST_MORE:
            if source_ids or refs or base_candidate_id or revision_targets or revision_constraints:
                raise DecisionMetadataError(
                    "REQUEST_MORE cannot claim a candidate or resolved decision"
                )
            if self.coexistable:
                raise DecisionMetadataError("REQUEST_MORE cannot be coexistable")
        else:
            if not source_ids:
                raise DecisionMetadataError(
                    f"{self.action.value} requires source candidate IDs"
                )
            if self.action is ResolutionAction.SELECT and len(source_ids) != 1:
                raise DecisionMetadataError("SELECT requires exactly one source candidate")
            if self.action is ResolutionAction.REVISE:
                if len(source_ids) != 1 or base_candidate_id != source_ids[0]:
                    raise DecisionMetadataError(
                        "REVISE requires one source candidate as its base"
                    )
                if not revision_targets:
                    raise DecisionMetadataError("REVISE requires revision targets")
            elif base_candidate_id or revision_targets or revision_constraints:
                raise DecisionMetadataError(
                    "revision fields are only valid for REVISE"
                )
            if self.action is not ResolutionAction.KEEP_BOTH and self.coexistable:
                raise DecisionMetadataError(
                    "coexistable is only valid for KEEP_BOTH"
                )
            if self.provenance.resolution_mode is None:
                raise DecisionMetadataError(
                    "resolved decisions must retain a resolution mode"
                )
            if (
                self.provenance.candidate_id is not None
                and self.provenance.candidate_id not in source_ids
            ):
                raise DecisionMetadataError(
                    "decision provenance references a non-source candidate"
                )
            if self.action is ResolutionAction.SELECT and (
                self.provenance.candidate_id != source_ids[0]
            ):
                raise DecisionMetadataError(
                    "SELECT provenance must identify its sole source candidate"
                )

        object.__setattr__(self, "source_candidate_ids", source_ids)
        object.__setattr__(self, "source_decision_refs", refs)
        object.__setattr__(self, "base_candidate_id", base_candidate_id)
        object.__setattr__(self, "revision_targets", revision_targets)
        object.__setattr__(self, "revision_constraints", revision_constraints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_path": self.decision_path,
            "action": self.action.value,
            "source_candidate_ids": list(self.source_candidate_ids),
            "source_decision_refs": list(self.source_decision_refs),
            "resolution_status": self.resolution_status.value,
            "provenance": self.provenance.to_dict(),
            "base_candidate_id": self.base_candidate_id,
            "revision_targets": list(self.revision_targets),
            "revision_constraints": list(self.revision_constraints),
            "coexistable": self.coexistable,
        }


@dataclass(frozen=True)
class CharacterResolutionResult:
    """Immutable request-scoped result of a resolution contract operation."""

    resolution_id: str
    mode: DecisionResolutionMode
    action: ResolutionAction
    resolution_status: DecisionResolutionStatus
    source_candidate_ids: tuple[str, ...]
    resolved_decisions: tuple[ResolvedDecision, ...]
    lineage: tuple[CandidateLineage, ...]
    decision_metadata: DecisionMetadataSet
    rationale: ResolutionRationale = ResolutionRationale()
    unresolved_decision_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolution_id", _text(self.resolution_id, "resolution_id"))
        object.__setattr__(
            self,
            "mode",
            _enum(DecisionResolutionMode, self.mode, "mode"),
        )
        object.__setattr__(self, "action", _enum(ResolutionAction, self.action, "action"))
        object.__setattr__(
            self,
            "resolution_status",
            _enum(
                DecisionResolutionStatus,
                self.resolution_status,
                "resolution_status",
            ),
        )
        _validate_action_status(self.action, self.resolution_status)
        if not isinstance(self.decision_metadata, DecisionMetadataSet):
            raise TypeError("decision_metadata must be DecisionMetadataSet")
        if not isinstance(self.rationale, ResolutionRationale):
            raise TypeError("rationale must be ResolutionRationale")

        source_ids = _string_tuple(self.source_candidate_ids, "source_candidate_ids")
        if len(source_ids) != len(set(source_ids)):
            raise DecisionMetadataError("source_candidate_ids cannot contain duplicates")
        unresolved_paths = _path_tuple(
            self.unresolved_decision_paths, "unresolved_decision_paths"
        )
        if len(unresolved_paths) != len(set(unresolved_paths)):
            raise DecisionMetadataError(
                "unresolved_decision_paths cannot contain duplicates"
            )
        resolved_decisions = _sequence(self.resolved_decisions, "resolved_decisions")
        if not all(isinstance(item, ResolvedDecision) for item in resolved_decisions):
            raise TypeError("resolved_decisions must contain ResolvedDecision values")
        resolved_decisions = tuple(resolved_decisions)
        candidate_lineage = _sequence(self.lineage, "lineage")
        if not all(isinstance(item, CandidateLineage) for item in candidate_lineage):
            raise TypeError("lineage must contain CandidateLineage values")
        candidate_lineage = tuple(candidate_lineage)
        lineage_ids = tuple(item.candidate_id for item in candidate_lineage)
        if len(lineage_ids) != 3 or len(lineage_ids) != len(set(lineage_ids)):
            raise DecisionMetadataError(
                "resolution result must preserve exactly three unique candidate lineage entries"
            )

        if self.action is ResolutionAction.REQUEST_MORE:
            if source_ids or resolved_decisions:
                raise DecisionMetadataError(
                    "REQUEST_MORE must not expose a final selected direction"
                )
            if self.rationale.request_more_reason is None:
                raise DecisionMetadataError("REQUEST_MORE requires a reason")
        else:
            if not source_ids or not resolved_decisions:
                raise DecisionMetadataError(
                    f"{self.action.value} requires resolved decision entries"
                )
            if any(item.action is not self.action for item in resolved_decisions):
                raise DecisionMetadataError(
                    "resolved decision action must match result action"
                )
            referenced_sources = {
                candidate_id
                for item in resolved_decisions
                for candidate_id in item.source_candidate_ids
            }
            if referenced_sources != set(source_ids):
                raise DecisionMetadataError(
                    "result source_candidate_ids must match decision references"
                )
            for candidate_id in source_ids:
                if candidate_id not in lineage_ids:
                    raise DecisionMetadataError(
                        f"result references unknown candidate: {candidate_id}"
                    )
            if self.action in {ResolutionAction.MIX, ResolutionAction.KEEP_BOTH} and len(
                source_ids
            ) < 2:
                raise DecisionMetadataError(
                    f"{self.action.value} requires at least two source candidates"
                )

        known_paths = {item.decision_path for item in self.decision_metadata.records}
        resolved_paths = [item.decision_path for item in resolved_decisions]
        if any(path not in known_paths for item in resolved_decisions for path in item.source_decision_refs):
            raise DecisionMetadataError(
                "source_decision_refs must reference known decision metadata paths"
            )
        if self.action is not ResolutionAction.REVISE and (
            set(resolved_paths) & set(unresolved_paths)
        ):
            raise DecisionMetadataError(
                "a decision path cannot be both resolved and unresolved"
            )
        locked_paths = {
            item.decision_path
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.LOCKED
        }
        if locked_paths & set(resolved_paths):
            raise DecisionMetadataError(
                "resolution cannot override USER or CANON locked decisions"
            )
        if self.action is ResolutionAction.SELECT and unresolved_paths:
            raise DecisionMetadataError("SELECT cannot contain unresolved targets")
        if self.action is ResolutionAction.REVISE:
            revision_targets = {
                target
                for item in resolved_decisions
                for target in item.revision_targets
            }
            if not revision_targets.issubset(unresolved_paths):
                raise DecisionMetadataError(
                    "REVISE targets must remain unresolved until revised"
                )
        if self.action is ResolutionAction.MIX and (
            self.resolution_status is DecisionResolutionStatus.UNRESOLVED
            and not unresolved_paths
        ):
            raise DecisionMetadataError(
                "partially unresolved MIX must identify unresolved paths"
            )

        path_entries: dict[str, list[ResolvedDecision]] = {}
        for item in resolved_decisions:
            path_entries.setdefault(item.decision_path, []).append(item)
            if item.provenance.resolution_mode is not self.mode:
                raise DecisionMetadataError(
                    "decision provenance mode must match result mode"
                )
        for path, entries in path_entries.items():
            if len(entries) > 1 and (
                self.action is not ResolutionAction.KEEP_BOTH
                or not all(item.coexistable for item in entries)
            ):
                raise DecisionMetadataError(
                    f"duplicate exclusive decision path is not structurally compatible: {path}"
                )

        object.__setattr__(self, "source_candidate_ids", source_ids)
        object.__setattr__(self, "resolved_decisions", resolved_decisions)
        object.__setattr__(self, "lineage", candidate_lineage)
        object.__setattr__(self, "unresolved_decision_paths", unresolved_paths)

    @property
    def candidate_lineage(self) -> tuple[CandidateLineage, ...]:
        """Compatibility name for callers that distinguish seeds from lineage."""

        return self.lineage

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "mode": self.mode.value,
            "action": self.action.value,
            "resolution_status": self.resolution_status.value,
            "source_candidate_ids": list(self.source_candidate_ids),
            "resolved_decisions": [
                item.to_dict() for item in self.resolved_decisions
            ],
            "lineage": [item.to_dict() for item in self.lineage],
            "decision_metadata": self.decision_metadata.to_dict(),
            "rationale": self.rationale.to_dict(),
            "unresolved_decision_paths": list(self.unresolved_decision_paths),
        }


@dataclass(frozen=True)
class ResolvedCharacterDirection:
    """Small deterministic direction derived from a resolution result."""

    candidate_set: CharacterCandidateSet
    decision_metadata: DecisionMetadataSet
    resolved_decisions: tuple[ResolvedDecision, ...]
    unresolved_decision_paths: tuple[str, ...] = ()

    @classmethod
    def from_result(
        cls,
        result: CharacterResolutionResult,
        candidate_set: CharacterCandidateSet,
    ) -> "ResolvedCharacterDirection":
        """Combine result references with seeds without materializing a composite seed."""

        if not isinstance(result, CharacterResolutionResult):
            raise TypeError("result must be CharacterResolutionResult")
        if not isinstance(candidate_set, CharacterCandidateSet):
            raise TypeError("candidate_set must be CharacterCandidateSet")
        if candidate_set.lineage != result.lineage:
            raise DecisionMetadataError(
                "result lineage does not match the supplied candidate set"
            )
        return cls(
            candidate_set=candidate_set,
            decision_metadata=result.decision_metadata,
            resolved_decisions=result.resolved_decisions,
            unresolved_decision_paths=result.unresolved_decision_paths,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_set, CharacterCandidateSet):
            raise TypeError("candidate_set must be CharacterCandidateSet")
        if not isinstance(self.decision_metadata, DecisionMetadataSet):
            raise TypeError("decision_metadata must be DecisionMetadataSet")
        decisions = _sequence(self.resolved_decisions, "resolved_decisions")
        if not all(isinstance(item, ResolvedDecision) for item in decisions):
            raise TypeError("resolved_decisions must contain ResolvedDecision values")
        unresolved_paths = _path_tuple(
            self.unresolved_decision_paths, "unresolved_decision_paths"
        )
        if len(unresolved_paths) != len(set(unresolved_paths)):
            raise DecisionMetadataError(
                "unresolved_decision_paths cannot contain duplicates"
            )
        resolved_paths = {item.decision_path for item in decisions}
        if any(item.action is not ResolutionAction.REVISE for item in decisions) and (
            resolved_paths & set(unresolved_paths)
        ):
            raise DecisionMetadataError(
                "a direction path cannot be both resolved and unresolved"
            )
        locked_paths = {
            item.decision_path
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.LOCKED
        }
        if locked_paths & resolved_paths:
            raise DecisionMetadataError(
                "direction cannot override USER or CANON locked decisions"
            )
        known_paths = {item.decision_path for item in self.decision_metadata.records}
        for item in decisions:
            for candidate_id in item.source_candidate_ids:
                self.candidate_set.get(candidate_id)
            if any(ref not in known_paths for ref in item.source_decision_refs):
                raise DecisionMetadataError(
                    "direction contains an unknown source decision reference"
                )
        object.__setattr__(self, "resolved_decisions", tuple(decisions))
        object.__setattr__(self, "unresolved_decision_paths", unresolved_paths)

    @property
    def locked_decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(
            item
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.LOCKED
        )

    @property
    def unresolved_decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(
            item
            for item in self.decision_metadata.records
            if item.resolution_status is DecisionResolutionStatus.UNRESOLVED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_set": self.candidate_set.to_dict(),
            "decision_metadata": self.decision_metadata.to_dict(),
            "resolved_decisions": [
                item.to_dict() for item in self.resolved_decisions
            ],
            "unresolved_decision_paths": list(self.unresolved_decision_paths),
        }


def build_resolution_input(
    phase4_result: object,
    decision_metadata: DecisionMetadataSet,
) -> CharacterResolutionInput:
    """Build legacy resolution input without provider calls or object mutation.

    The adapter keeps all three Phase 4 seeds and copies only the selector's
    comparative metadata into a frozen request object.  It deliberately does
    not invoke Planner, produce a resolution output, or persist anything.
    """

    from .concept_search_v2 import CharacterPlanningV2Phase4Result

    if not isinstance(phase4_result, CharacterPlanningV2Phase4Result):
        raise TypeError("phase4_result must be CharacterPlanningV2Phase4Result")

    return build_resolution_input_from_search_and_selection(
        phase4_result.search,
        phase4_result.selection,
        decision_metadata,
    )


def build_resolution_input_from_search_and_selection(
    search_result: object,
    selection_result: object,
    decision_metadata: DecisionMetadataSet,
) -> CharacterResolutionInput:
    """Build resolution input before Planner without fabricating a Phase 4 result.

    WHY: the production SELECT route must resolve the Selector output before
    the single Planner call.  Reusing ``build_resolution_input`` directly
    would require a fake Planner result, so this shared adapter validates the
    same search/selection invariants from their real pre-Planner components.
    """

    from .character_concept_v2 import CharacterConceptSeedStatus
    from .concept_search_v2 import ConceptSearchResult, ConceptSelectionResult

    if not isinstance(search_result, ConceptSearchResult):
        raise TypeError("search_result must be ConceptSearchResult")
    if not isinstance(selection_result, ConceptSelectionResult):
        raise TypeError("selection_result must be ConceptSelectionResult")
    if not isinstance(decision_metadata, DecisionMetadataSet):
        raise TypeError("decision_metadata must be DecisionMetadataSet")

    selection = selection_result.selection
    search_seeds = tuple(search_result.seeds)
    selected_seeds = tuple(selection_result.seeds)
    if len(search_seeds) != 3 or len(selected_seeds) != 3:
        raise DecisionMetadataError("Phase 4 resolution input requires exactly three seeds")
    search_by_id = {seed.concept_id: seed for seed in search_seeds}
    selected_by_id = {seed.concept_id: seed for seed in selected_seeds}
    if (
        len(search_by_id) != 3
        or len(selected_by_id) != 3
        or set(search_by_id) != set(selected_by_id)
    ):
        raise DecisionMetadataError("Phase 4 search and selection candidates diverged")
    for candidate_id, seed in search_by_id.items():
        if seed.to_provider_dict() != selected_by_id[candidate_id].to_provider_dict():
            raise DecisionMetadataError(
                f"Phase 4 candidate changed before resolution input: {candidate_id}"
            )

    candidate_metadata = {
        item.candidate_id: item for item in decision_metadata.candidates
    }
    candidate_ids = set(selected_by_id)
    selected_id = selection.selected_concept_id
    if selected_id not in candidate_ids:
        raise DecisionMetadataError(
            f"selector references unknown candidate: {selected_id}"
        )
    if set(candidate_metadata) != candidate_ids:
        raise DecisionMetadataError(
            "resolution metadata must cover exactly the current Phase 4 candidates"
        )
    for candidate_id, item in candidate_metadata.items():
        expected = (
            CandidateDecisionOutcome.SELECTED
            if candidate_id == selected_id
            else CandidateDecisionOutcome.REJECTED
        )
        if item.outcome is not expected:
            raise DecisionMetadataError(
                f"legacy selector outcome mismatch for candidate: {candidate_id}"
            )

    selected_seed = selection_result.selected_seed
    expected_selected_seed = selected_by_id[selected_id]
    if (
        selected_seed.concept_id != selected_id
        or selected_seed.status is not CharacterConceptSeedStatus.SELECTED
        or selected_seed.to_provider_dict() != expected_selected_seed.to_provider_dict()
    ):
        raise DecisionMetadataError("selected seed integrity check failed")

    lineage = []
    for candidate_id in sorted(candidate_ids):
        item = candidate_metadata[candidate_id]
        refs = tuple(
            record.decision_path
            for record in decision_metadata.records
            if record.provenance.candidate_id == candidate_id
            or record.provenance.resolved_from == candidate_id
        )
        lineage.append(
            CandidateLineage(
                candidate_id=candidate_id,
                origin=DecisionSource.CONCEPT_SEARCH,
                origin_invocation_id=item.source_invocation_id,
                selector_outcome=item.outcome,
                selector_reason_available=item.reason_available,
                tradeoff_available=bool(selection.tradeoffs),
                decision_metadata_refs=refs,
            )
        )

    return CharacterResolutionInput(
        candidate_set=CharacterCandidateSet(
            candidates=selected_seeds,
            lineage=tuple(lineage),
            selected_candidate_id=selected_id,
        ),
        decision_metadata=decision_metadata,
        selection_reasons=selection.selection_reasons,
        tradeoffs=selection.tradeoffs,
        preserve_elements=selection.preserve_elements,
        rejected_reasons=selection.rejected_reasons,
        current_resolution_mode=DecisionResolutionMode.LEGACY_AI_SELECT,
        recommended_candidate_id=selected_id,
    )


def legacy_selector_to_resolution_result(
    resolution_input: CharacterResolutionInput,
    *,
    resolution_id: str | None = None,
) -> CharacterResolutionResult:
    """Map the existing selector recommendation to one explicit SELECT result.

    This compatibility adapter never re-selects, calls a provider, mutates a
    seed, or drops rejected candidates.  It is intentionally separate from
    Planner wiring so P7.5 can add resolver modes without changing legacy
    production behavior.
    """

    if not isinstance(resolution_input, CharacterResolutionInput):
        raise TypeError("resolution_input must be CharacterResolutionInput")
    if resolution_input.current_resolution_mode is not DecisionResolutionMode.LEGACY_AI_SELECT:
        raise DecisionMetadataError(
            "legacy selector adapter only accepts LEGACY_AI_SELECT input"
        )
    selected_id = resolution_input.recommended_candidate_id
    if selected_id is None:
        raise DecisionMetadataError("legacy selector input has no recommendation")
    if resolution_input.candidate_set.selected_candidate_id != selected_id:
        raise DecisionMetadataError(
            "legacy selector recommendation does not match candidate-set selection"
        )
    if (
        resolution_input.candidate_set.lineage_for(selected_id).selector_outcome
        is not CandidateDecisionOutcome.SELECTED
    ):
        raise DecisionMetadataError(
            "legacy selector recommendation is not the selected candidate lineage"
        )

    selector_records = tuple(
        item
        for item in resolution_input.decision_metadata.records
        if item.decision_path == "selected_concept_seed"
        and item.source is DecisionSource.SELECTOR
        and item.provenance.resolved_from == selected_id
    )
    if len(selector_records) != 1:
        raise DecisionMetadataError(
            "legacy selector input must contain exactly one selected seed record"
        )
    selector_record = selector_records[0]
    decision = ResolvedDecision(
        decision_path="selected_concept_seed",
        action=ResolutionAction.SELECT,
        source_candidate_ids=(selected_id,),
        resolution_status=DecisionResolutionStatus.RESOLVED,
        source_decision_refs=(selector_record.decision_path,),
        provenance=DecisionProvenance(
            source_invocation_id=selector_record.provenance.source_invocation_id,
            candidate_id=selected_id,
            resolved_from=selected_id,
            resolution_mode=DecisionResolutionMode.LEGACY_AI_SELECT,
        ),
    )
    return CharacterResolutionResult(
        resolution_id=resolution_id or f"legacy-ai-select:{selected_id}",
        mode=DecisionResolutionMode.LEGACY_AI_SELECT,
        action=ResolutionAction.SELECT,
        resolution_status=DecisionResolutionStatus.RESOLVED,
        source_candidate_ids=(selected_id,),
        resolved_decisions=(decision,),
        lineage=resolution_input.candidate_set.lineage,
        decision_metadata=resolution_input.decision_metadata,
        rationale=ResolutionRationale.from_input(resolution_input),
    )


class CharacterResolver(Protocol):
    """Pure resolver boundary shared by every resolution mode.

    The protocol deliberately accepts only the request-scoped input.  Provider
    transport, UI state, and Planner routing therefore cannot become hidden
    inputs to a resolver implementation.
    """

    def resolve(
        self, resolution_input: CharacterResolutionInput
    ) -> CharacterResolutionResult:
        """Resolve one input into the single P7.4 result contract."""


def _build_select_resolution_result(
    resolution_input: CharacterResolutionInput,
    *,
    mode: DecisionResolutionMode,
    selected_candidate_id: str,
    selection_reasons: Sequence[str],
    tradeoffs: Sequence[str] | None = None,
    require_reasons: bool = False,
    resolution_id: str,
) -> CharacterResolutionResult:
    """Build a SELECT result so AI and user paths share P7.4 validation.

    Candidate values remain in the immutable input.  The result contains only
    the selected ID and provenance; ``CharacterResolutionResult`` performs the
    final lock, path, candidate, and status checks for every caller.
    """

    if not isinstance(resolution_input, CharacterResolutionInput):
        raise TypeError("resolution_input must be CharacterResolutionInput")
    selected_id = _text(selected_candidate_id, "selected_candidate_id")
    resolution_input.candidate_set.get(selected_id)
    mode = _enum(DecisionResolutionMode, mode, "mode")
    reasons = _string_tuple(selection_reasons, "selection_reasons")
    if require_reasons and not reasons:
        raise DecisionMetadataError("SELECT requires bounded selection reasons")
    resolved_tradeoffs = (
        resolution_input.tradeoffs
        if tradeoffs is None
        else _string_tuple(tradeoffs, "tradeoffs")
    )
    decision = ResolvedDecision(
        decision_path="selected_concept_seed",
        action=ResolutionAction.SELECT,
        source_candidate_ids=(selected_id,),
        resolution_status=DecisionResolutionStatus.RESOLVED,
        provenance=DecisionProvenance(
            candidate_id=selected_id,
            resolved_from=selected_id,
            resolution_mode=mode,
        ),
    )
    return CharacterResolutionResult(
        resolution_id=resolution_id,
        mode=mode,
        action=ResolutionAction.SELECT,
        resolution_status=DecisionResolutionStatus.RESOLVED,
        source_candidate_ids=(selected_id,),
        resolved_decisions=(decision,),
        lineage=resolution_input.candidate_set.lineage,
        decision_metadata=resolution_input.decision_metadata,
        rationale=ResolutionRationale(
            selection_reasons=reasons,
            tradeoffs=resolved_tradeoffs,
            preserve_elements=resolution_input.preserve_elements,
            rejected_reasons=resolution_input.rejected_reasons,
        ),
    )


class LegacyAISelectResolver:
    """Formal resolver wrapper for the unchanged legacy selector behavior."""

    def resolve(
        self, resolution_input: CharacterResolutionInput
    ) -> CharacterResolutionResult:
        """Use the existing recommendation without rescoring or provider calls."""

        return legacy_selector_to_resolution_result(resolution_input)


@dataclass(frozen=True)
class AIResolutionPayload:
    """Strict, bounded AI decision payload accepted by the mock AI resolver."""

    action: ResolutionAction
    candidate_id: str | None = None
    reasons: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _enum(ResolutionAction, self.action, "action"))
        object.__setattr__(
            self,
            "candidate_id",
            _optional_text(self.candidate_id, "candidate_id"),
        )
        object.__setattr__(self, "reasons", _string_tuple(self.reasons, "reasons"))
        object.__setattr__(self, "tradeoffs", _string_tuple(self.tradeoffs, "tradeoffs"))
        if self.action is not ResolutionAction.SELECT:
            raise DecisionMetadataError(
                f"AI_DECIDE runtime action {self.action.value} is not enabled"
            )
        if self.candidate_id is None:
            raise DecisionMetadataError("AI SELECT requires candidate_id")
        if not self.reasons:
            raise DecisionMetadataError("AI SELECT requires reasons")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AIResolutionPayload":
        """Parse only the small structured payload owned by an AI resolver."""

        if not isinstance(value, Mapping):
            raise TypeError("AI resolution payload must be a mapping")
        allowed = {"action", "candidate_id", "reasons", "tradeoffs"}
        unknown = set(value) - allowed
        if unknown:
            raise DecisionMetadataError(
                f"AI resolution payload contains unknown fields: {sorted(unknown)!r}"
            )
        return cls(
            action=value.get("action"),
            candidate_id=value.get("candidate_id"),
            reasons=value.get("reasons", ()),
            tradeoffs=value.get("tradeoffs", ()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "candidate_id": self.candidate_id,
            "reasons": list(self.reasons),
            "tradeoffs": list(self.tradeoffs),
        }


@dataclass(frozen=True)
class AIResolver:
    """Resolve one injected structured AI decision without calling a provider.

    P7.5 intentionally stops at a deterministic, production-shaped payload
    boundary.  A future transport may produce ``AIResolutionPayload``; it may
    not bypass the shared result validator or silently fall back to Legacy.
    """

    payload: AIResolutionPayload

    def __post_init__(self) -> None:
        if not isinstance(self.payload, AIResolutionPayload):
            raise TypeError("payload must be AIResolutionPayload")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AIResolver":
        """Create a resolver from a strict structured payload mapping."""

        return cls(AIResolutionPayload.from_mapping(value))

    def resolve(
        self, resolution_input: CharacterResolutionInput
    ) -> CharacterResolutionResult:
        """Turn the AI SELECT payload into a validated resolution result."""

        return _build_select_resolution_result(
            resolution_input,
            mode=DecisionResolutionMode.AI_DECIDE,
            selected_candidate_id=self.payload.candidate_id or "",
            selection_reasons=self.payload.reasons,
            tradeoffs=self.payload.tradeoffs,
            require_reasons=True,
            resolution_id=f"ai-select:{self.payload.candidate_id}",
        )


@dataclass(frozen=True)
class UserResolutionCommand:
    """Minimal structured human command; it does not duplicate resolution input."""

    action: ResolutionAction
    candidate_id: str | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _enum(ResolutionAction, self.action, "action"))
        object.__setattr__(
            self,
            "candidate_id",
            _optional_text(self.candidate_id, "candidate_id"),
        )
        object.__setattr__(self, "reasons", _string_tuple(self.reasons, "reasons"))
        if self.action is not ResolutionAction.SELECT:
            raise DecisionMetadataError(
                f"USER_DECIDE runtime action {self.action.value} is not enabled"
            )
        if self.candidate_id is None:
            raise DecisionMetadataError("USER SELECT requires candidate_id")

    @classmethod
    def select(
        cls, candidate_id: str, *, reasons: Sequence[str] = ()
    ) -> "UserResolutionCommand":
        """Create the supported explicit user SELECT command."""

        return cls(
            action=ResolutionAction.SELECT,
            candidate_id=candidate_id,
            reasons=tuple(reasons),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "candidate_id": self.candidate_id,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class UserResolver:
    """Resolve one explicit user command while retaining all contract locks."""

    command: UserResolutionCommand

    def __post_init__(self) -> None:
        if not isinstance(self.command, UserResolutionCommand):
            raise TypeError("command must be UserResolutionCommand")

    def resolve(
        self, resolution_input: CharacterResolutionInput
    ) -> CharacterResolutionResult:
        """Make the user's candidate choice authoritative for this request only."""

        reasons = self.command.reasons or resolution_input.selection_reasons
        return _build_select_resolution_result(
            resolution_input,
            mode=DecisionResolutionMode.USER_DECIDE,
            selected_candidate_id=self.command.candidate_id or "",
            selection_reasons=reasons,
            resolution_id=f"user-select:{self.command.candidate_id}",
        )


def resolve_character_direction(
    mode: DecisionResolutionMode | str,
    resolution_input: CharacterResolutionInput,
    *,
    ai_payload: AIResolutionPayload | Mapping[str, object] | None = None,
    user_command: UserResolutionCommand | None = None,
) -> CharacterResolutionResult:
    """Route only the resolution boundary; unknown modes fail closed.

    The router intentionally has no Planner, Phase 5, Web, or provider branch.
    Missing mode-specific input is an error rather than permission to fall
    back to the Legacy recommendation.
    """

    selected_mode = _enum(DecisionResolutionMode, mode, "mode")
    if selected_mode is DecisionResolutionMode.LEGACY_AI_SELECT:
        return LegacyAISelectResolver().resolve(resolution_input)
    if selected_mode is DecisionResolutionMode.AI_DECIDE:
        if ai_payload is None:
            raise DecisionMetadataError("AI_DECIDE requires a structured AI payload")
        resolver = (
            AIResolver(ai_payload)
            if isinstance(ai_payload, AIResolutionPayload)
            else AIResolver.from_mapping(ai_payload)
        )
        return resolver.resolve(resolution_input)
    if selected_mode is DecisionResolutionMode.USER_DECIDE:
        if user_command is None:
            raise DecisionMetadataError("USER_DECIDE requires a structured user command")
        return UserResolver(user_command).resolve(resolution_input)
    raise DecisionMetadataError(f"unsupported resolution mode: {selected_mode.value}")


__all__ = [
    "CandidateLineage",
    "CandidateDecisionMetadata",
    "CandidateDecisionOutcome",
    "CharacterCandidateSet",
    "CharacterResolutionInput",
    "DECISION_METADATA_SCHEMA",
    "DecisionMetadataError",
    "DecisionMetadataSet",
    "DecisionOwner",
    "DecisionProvenance",
    "DecisionRecord",
    "DecisionResolutionMode",
    "DecisionResolutionStatus",
    "DecisionSource",
    "ResolutionAction",
    "ResolutionMode",
    "ResolutionRationale",
    "ResolvedCharacterDirection",
    "ResolvedDecision",
    "CharacterResolutionResult",
    "build_resolution_input",
    "build_resolution_input_from_search_and_selection",
    "CharacterResolver",
    "LegacyAISelectResolver",
    "AIResolutionPayload",
    "AIResolver",
    "UserResolutionCommand",
    "UserResolver",
    "resolve_character_direction",
    "build_resolution_input",
    "legacy_selector_to_resolution_result",
]
