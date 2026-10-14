"""Immutable Planner-to-Generator contract for Character Generation V2 Slice 1.

The module stops at the generation boundary: it performs no provider calls,
prompt construction, route wiring, or creative selection.  Freeze projects
already-resolved inputs; validation remains deterministic and fail-closed.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING

from combat_semantics import CombatRoleProfile

from ..context.schema import CharacterPlanningContextV2, ContextGap, ContextGapCode
from ..field_authorization import (
    CharacterGenerationField,
    FieldAuthorization,
    FieldAuthorizationPolicy,
    FieldAuthorizationState,
)
from ..intent import (
    ExplicitAgeRequirement,
    ExplicitGenderRequirement,
    parse_explicit_age_requirement,
    parse_explicit_gender_requirement,
)
from ..naming_design import (
    CharacterNamingDesignV1,
    CharacterNamingOwner,
    extract_explicit_character_names,
)
from .character_concept_v2 import CharacterConceptSeedStatus, CharacterConceptSeedV2
from .character_plan_v2 import CharacterDesignPlanV2Status
from .character_planner_v2 import CharacterPlannerV1Result
from .decision_metadata import (
    CharacterResolutionResult,
    DecisionResolutionStatus,
    ResolutionAction,
)

if TYPE_CHECKING:
    from agents.character_generation import CharacterDesignRequest


RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA = "resolved-character-generation-spec/v1"
CHARACTER_GENERATION_V2_ROUTE = "CHARACTER_GENERATION_V2"
_FIELD_AUTHORIZATION_STATES = frozenset(
    {"NEW_DESIGN_AUTHORIZED", "CANON_GROUNDED_ONLY", "UNAUTHORIZED"}
)
_ASSIGNMENT_RE = re.compile(
    r"^(?P<field>[A-Za-z][A-Za-z0-9_.:-]*)\s*(?:=|:|\bis\b)\s*(?P<value>.+)$",
    re.IGNORECASE,
)
_DEFAULT_BLOCKING_GAP_CODES = frozenset(
    {
        ContextGapCode.CANON_CONTEXT_UNAVAILABLE,
        ContextGapCode.ROSTER_CONTEXT_UNAVAILABLE,
        ContextGapCode.RELATIONSHIP_CONTEXT_UNAVAILABLE,
        ContextGapCode.RELATIONSHIP_COVERAGE_INCOMPLETE,
        ContextGapCode.RELATIONSHIP_VOCABULARY_UNAVAILABLE,
    }
)


class GenerationSpecValidationReason(str, Enum):
    """Finite machine-readable outcomes for deterministic validation."""

    VALID = "VALID"
    INVALID_SPEC = "INVALID_SPEC"
    INVALID_RESOLUTION = "INVALID_RESOLUTION"
    SEED_IDENTITY_MISMATCH = "SEED_IDENTITY_MISMATCH"
    PLANNER_IDENTITY_MISMATCH = "PLANNER_IDENTITY_MISMATCH"
    HARD_FORBIDDEN_CONFLICT = "HARD_FORBIDDEN_CONFLICT"
    CANON_CONFLICT = "CANON_CONFLICT"
    INVALID_FIELD_AUTHORIZATION = "INVALID_FIELD_AUTHORIZATION"
    INVALID_RELATIONSHIP_TARGET = "INVALID_RELATIONSHIP_TARGET"
    BLOCKING_GAP = "BLOCKING_GAP"
    MISSING_REQUIRED_GENERATION_FIELD = "MISSING_REQUIRED_GENERATION_FIELD"
    INVALID_EVIDENCE_REFERENCE = "INVALID_EVIDENCE_REFERENCE"


class GenerationSpecFreezeError(ValueError):
    """Raised when a freeze cannot produce a complete spec atomically."""

    def __init__(self, reason: GenerationSpecValidationReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


@dataclass(frozen=True)
class GenerationSpecValidationResult:
    """Deterministic validation result with no free-form contract reason."""

    reason: GenerationSpecValidationReason
    detail: str = ""

    @property
    def valid(self) -> bool:
        return self.reason is GenerationSpecValidationReason.VALID

    @property
    def ok(self) -> bool:
        return self.valid

    def __bool__(self) -> bool:
        return self.valid


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _normalized(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _strings(value: object, name: str, *, sort: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        item = _text(item, f"{name}[]")
        marker = _normalized(item)
        if marker not in seen:
            result.append(item)
            seen.add(marker)
    if sort:
        result.sort(key=lambda item: (_normalized(item), item))
    return tuple(result)


def _ids(value: object, name: str) -> tuple[str, ...]:
    """Canonicalize ID sets; IDs have no business ordering here."""

    return _strings(value, name, sort=True)


def _freeze(value: object) -> object:
    """Detach caller-owned containers so later source mutation is harmless."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        result = [_jsonable(item) for item in value]
        return sorted(result, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _digest(value: object) -> str:
    encoded = json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedCharacterDirectionV1:
    """The selected concept direction; it is not a Canon assertion."""

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

    def __post_init__(self) -> None:
        for name in (
            "concept_id", "one_line_identity", "dramatic_axis", "character_contradiction",
            "player_hook", "relationship_axis", "gameplay_fantasy", "visual_anchor", "major_risk",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "differentiation_basis", _strings(self.differentiation_basis, "differentiation_basis"))

    @classmethod
    def from_seed(cls, seed: CharacterConceptSeedV2) -> ResolvedCharacterDirectionV1:
        if not isinstance(seed, CharacterConceptSeedV2):
            raise TypeError("seed must be a CharacterConceptSeedV2")
        return cls(
            concept_id=seed.concept_id,
            one_line_identity=seed.one_line_identity,
            dramatic_axis=seed.dramatic_axis,
            character_contradiction=seed.character_contradiction,
            player_hook=seed.player_hook,
            relationship_axis=seed.relationship_axis,
            gameplay_fantasy=seed.gameplay_fantasy,
            visual_anchor=seed.visual_anchor,
            differentiation_basis=seed.differentiation_basis,
            major_risk=seed.major_risk,
        )

    def to_dict(self) -> dict[str, object]:
        return _jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class GenerationSpecAuditMetadataV1:
    """Model-hidden provenance and resolution references."""

    request_digest: str
    candidate_set_digest: str
    selected_seed_digest: str
    resolution_id: str
    resolution_mode: str
    resolution_action: str
    resolution_status: str
    planner_snapshot_id: str
    planning_context_snapshot_id: str
    evidence_snapshot_id: str
    selected_seed_id: str = ""

    def __post_init__(self) -> None:
        for name in (
            "request_digest", "candidate_set_digest", "selected_seed_digest", "resolution_id",
            "resolution_mode", "resolution_action", "resolution_status", "planner_snapshot_id",
            "planning_context_snapshot_id", "evidence_snapshot_id", "selected_seed_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    def to_dict(self) -> dict[str, str]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True)
class ResolvedCharacterGenerationSpecV1:
    """Immutable, provider-independent semantic input for the future Generator."""

    spec_version: str
    spec_id: str
    spec_digest: str
    request_id: str
    route_identity: str
    hard_requirements: tuple[str, ...]
    forbidden_constraints: tuple[str, ...]
    resolved_direction: ResolvedCharacterDirectionV1
    story_boundaries: Mapping[str, object]
    gameplay_boundaries: Mapping[str, object]
    visual_boundaries: Mapping[str, object]
    canon_exact_values: Mapping[str, object]
    allowed_faction_ids: tuple[str, ...]
    allowed_organization_ids: tuple[str, ...]
    allowed_relationship_targets: tuple[str, ...]
    field_authorization: Mapping[str, object]
    known_gaps: tuple[ContextGap, ...]
    required_generation_fields: Mapping[str, object]
    evidence_snapshot_id: str
    authorized_evidence_source_ids: tuple[str, ...]
    evidence_supported_fields: tuple[str, ...]
    audit_metadata: GenerationSpecAuditMetadataV1
    combat_semantics: CombatRoleProfile | None = None
    soft_preferences: tuple[str, ...] = ()
    bounded_reference_precedent: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    allowed_surface_style: tuple[str, ...] = ()
    bounded_open_questions: tuple[str, ...] = ()
    non_blocking_relationship_hints: tuple[object, ...] = ()
    naming_design: CharacterNamingDesignV1 | None = None
    gender_requirement: ExplicitGenderRequirement | None = None
    age_requirement: ExplicitAgeRequirement | None = None
    requested_affiliation_id: str | None = None

    def __post_init__(self) -> None:
        if self.spec_version != RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA:
            raise ValueError(f"unsupported spec_version: {self.spec_version!r}")
        object.__setattr__(self, "spec_id", _text(self.spec_id, "spec_id"))
        object.__setattr__(self, "spec_digest", _text(self.spec_digest, "spec_digest"))
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        if self.route_identity != CHARACTER_GENERATION_V2_ROUTE:
            raise ValueError(f"unsupported route_identity: {self.route_identity!r}")
        object.__setattr__(self, "hard_requirements", _strings(self.hard_requirements, "hard_requirements", sort=True))
        object.__setattr__(self, "forbidden_constraints", _strings(self.forbidden_constraints, "forbidden_constraints", sort=True))
        if isinstance(self.resolved_direction, Mapping):
            object.__setattr__(self, "resolved_direction", ResolvedCharacterDirectionV1(**dict(self.resolved_direction)))
        if not isinstance(self.resolved_direction, ResolvedCharacterDirectionV1):
            raise TypeError("resolved_direction must be ResolvedCharacterDirectionV1")
        for name in (
            "story_boundaries", "gameplay_boundaries", "visual_boundaries", "canon_exact_values",
            "field_authorization", "required_generation_fields", "bounded_reference_precedent",
        ):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, _freeze(value))
        for name in (
            "allowed_faction_ids", "allowed_organization_ids", "allowed_relationship_targets",
            "authorized_evidence_source_ids", "evidence_supported_fields",
        ):
            object.__setattr__(self, name, _ids(getattr(self, name), name))
        object.__setattr__(self, "evidence_snapshot_id", _text(self.evidence_snapshot_id, "evidence_snapshot_id"))
        gaps = tuple(self.known_gaps)
        if not all(isinstance(item, ContextGap) for item in gaps):
            raise TypeError("known_gaps must contain ContextGap values")
        object.__setattr__(self, "known_gaps", gaps)
        object.__setattr__(self, "soft_preferences", _strings(self.soft_preferences, "soft_preferences", sort=True))
        object.__setattr__(self, "allowed_surface_style", _strings(self.allowed_surface_style, "allowed_surface_style", sort=True))
        object.__setattr__(self, "bounded_open_questions", _strings(self.bounded_open_questions, "bounded_open_questions", sort=True))
        object.__setattr__(self, "non_blocking_relationship_hints", _freeze(tuple(self.non_blocking_relationship_hints)))
        if self.naming_design is not None and not isinstance(
            self.naming_design, CharacterNamingDesignV1
        ):
            raise TypeError("naming_design must be CharacterNamingDesignV1 or None")
        if self.gender_requirement is not None and not isinstance(
            self.gender_requirement, ExplicitGenderRequirement
        ):
            raise TypeError("gender_requirement must be ExplicitGenderRequirement or None")
        if self.age_requirement is not None and not isinstance(
            self.age_requirement, ExplicitAgeRequirement
        ):
            raise TypeError("age_requirement must be ExplicitAgeRequirement or None")
        if self.requested_affiliation_id is not None:
            affiliation_id = _text(
                self.requested_affiliation_id,
                "requested_affiliation_id",
            )
            if not affiliation_id.startswith("faction_"):
                raise ValueError("requested_affiliation_id must be a Canon faction ID")
            if affiliation_id not in self.allowed_faction_ids:
                raise ValueError("requested_affiliation_id is outside the allowed faction set")
            object.__setattr__(self, "requested_affiliation_id", affiliation_id)
        if self.combat_semantics is not None and not isinstance(self.combat_semantics, CombatRoleProfile):
            raise TypeError("combat_semantics must be a CombatRoleProfile or None")
        if not isinstance(self.audit_metadata, GenerationSpecAuditMetadataV1):
            raise TypeError("audit_metadata must be GenerationSpecAuditMetadataV1")

    def semantic_dict(self) -> dict[str, object]:
        """Return the model-visible part; audit and evidence references stay out."""

        return {
            "spec_version": self.spec_version,
            "request_id": self.request_id,
            "route_identity": self.route_identity,
            "hard_requirements": list(self.hard_requirements),
            "forbidden_constraints": list(self.forbidden_constraints),
            "resolved_direction": self.resolved_direction.to_dict(),
            "story_boundaries": _jsonable(self.story_boundaries),
            "gameplay_boundaries": _jsonable(self.gameplay_boundaries),
            "visual_boundaries": _jsonable(self.visual_boundaries),
            "canon_exact_values": _jsonable(self.canon_exact_values),
            "allowed_faction_ids": list(self.allowed_faction_ids),
            "allowed_organization_ids": list(self.allowed_organization_ids),
            "allowed_relationship_targets": list(self.allowed_relationship_targets),
            "field_authorization_policy": _jsonable(self.field_authorization),
            "known_gaps": [_jsonable(item) for item in self.known_gaps],
            "required_generation_fields": list(self.required_generation_fields),
            "combat_semantics": _jsonable(self.combat_semantics),
            "soft_preferences": list(self.soft_preferences),
            "bounded_reference_precedent": _jsonable(self.bounded_reference_precedent),
            "allowed_surface_style": list(self.allowed_surface_style),
            "bounded_open_questions": list(self.bounded_open_questions),
            "non_blocking_relationship_hints": _jsonable(self.non_blocking_relationship_hints),
            "naming_design": self.naming_design.to_dict() if self.naming_design else None,
            "gender_requirement": (
                self.gender_requirement.to_dict() if self.gender_requirement else None
            ),
            "age_requirement": (
                self.age_requirement.to_dict() if self.age_requirement else None
            ),
            "requested_affiliation_id": self.requested_affiliation_id,
        }

    @property
    def field_authorization_policy(self) -> FieldAuthorizationPolicy:
        """Rehydrate B1A's typed policy from the frozen semantic snapshot."""

        raw_authorizations = self.field_authorization.get("field_authorizations")
        if not isinstance(raw_authorizations, Mapping):
            raise ValueError("field_authorization is missing its typed field matrix")
        state_projection = self.field_authorization.get("field_states")
        if not isinstance(state_projection, Mapping):
            raise ValueError("field_authorization is missing its state projection")
        authorizations: dict[CharacterGenerationField, FieldAuthorization] = {}
        for field_value in CharacterGenerationField:
            raw = raw_authorizations.get(field_value.value)
            if not isinstance(raw, Mapping) or raw.get("field") != field_value.value:
                raise ValueError(
                    f"field_authorization has no valid entry for {field_value.value!r}"
                )
            authorization = FieldAuthorization(
                field=field_value,
                state=FieldAuthorizationState(raw.get("state")),
                authorized_source_ids=raw.get("authorized_source_ids", ()),
                allowed_exact_values=raw.get("allowed_exact_values", ()),
                requires_grounding=raw.get("requires_grounding", False),
            )
            if state_projection.get(field_value.value) != authorization.state.value:
                raise ValueError(
                    f"field_authorization state projections disagree for {field_value.value!r}"
                )
            authorizations[field_value] = authorization
        return FieldAuthorizationPolicy(authorizations)

    def audit_dict(self) -> dict[str, object]:
        """Return model-hidden evidence and audit metadata."""

        return {
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "authorized_evidence_source_ids": list(self.authorized_evidence_source_ids),
            "evidence_supported_fields": list(self.evidence_supported_fields),
            "metadata": self.audit_metadata.to_dict(),
        }

    def to_model_input(self) -> dict[str, object]:
        """Explicitly exclude all audit/provenance metadata from a future prompt."""

        return self.semantic_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "semantic": self.semantic_dict(),
            "audit": self.audit_dict(),
            "spec_id": self.spec_id,
            "spec_digest": self.spec_digest,
        }


def _assignment(value: str) -> tuple[str, str] | None:
    match = _ASSIGNMENT_RE.match(_normalized(value))
    if match is None:
        return None
    return _normalized(match.group("field")), _normalized(match.group("value"))


def _constraint_conflict(hard: Sequence[str], forbidden: Sequence[str]) -> bool:
    hard_values = {_normalized(item) for item in hard}
    forbidden_values = {_normalized(item) for item in forbidden}
    if hard_values & forbidden_values:
        return True
    hard_assignments = {_assignment(item) for item in hard}
    forbidden_assignments = {_assignment(item) for item in forbidden}
    return bool({item for item in hard_assignments if item is not None} & forbidden_assignments)


def _context_source_ids(context: CharacterPlanningContextV2) -> set[str]:
    source_ids: set[str] = set()
    for collection in (context.canon, context.roster, context.references, context.story):
        for item in collection:
            source_id = getattr(getattr(item, "source", None), "source_id", None)
            if isinstance(source_id, str):
                source_ids.add(source_id)
    for collection in (
        context.canon_relationships, context.reference_relationships,
        context.draft_relationships, context.evaluation_relationships,
    ):
        source_ids.update(item.source_id for item in collection)
    for item in context.references:
        source_ids.update(item.source_ids)
    return source_ids


def _derive_allowed_ids(context: CharacterPlanningContextV2) -> tuple[tuple[str, ...], tuple[str, ...]]:
    factions = {item.faction_id for item in context.roster if item.faction_id}
    expected_affiliation_id = context.plan_v1.expected_affiliation_id
    if expected_affiliation_id is not None:
        affiliation = context.plan_v1.affiliation_context
        if affiliation is None or affiliation.faction_id != expected_affiliation_id:
            raise _fail(
                GenerationSpecValidationReason.INVALID_SPEC,
                "requested Canon affiliation is missing its resolved context",
            )
        factions.add(expected_affiliation_id)
    organizations: set[str] = set()
    for item in context.canon:
        entity_type = item.entity_type.casefold()
        if entity_type in {"faction", "faction_id"}:
            factions.add(item.entity_id)
        elif entity_type in {"organization", "organization_id"}:
            organizations.add(item.entity_id)
    return tuple(sorted(factions)), tuple(sorted(organizations))


def _derive_relationship_targets(context: CharacterPlanningContextV2) -> tuple[str, ...]:
    targets = {item.character_id for item in context.roster}
    for collection in (
        context.canon_relationships, context.reference_relationships,
        context.draft_relationships, context.evaluation_relationships,
    ):
        targets.update(item.target_id for item in collection)
    return tuple(sorted(targets))


def _fail(reason: GenerationSpecValidationReason, detail: str) -> GenerationSpecFreezeError:
    return GenerationSpecFreezeError(reason, detail)


def _normalize_field_authorization(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, "field_authorization must be a mapping")
    states = value.get("field_states")
    if not isinstance(states, Mapping) or not states:
        raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, "field_states must be non-empty")
    normalized_states: dict[str, str] = {}
    for field_name, state in states.items():
        field_name = _text(field_name, "field authorization field")
        if state not in _FIELD_AUTHORIZATION_STATES:
            raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, f"unsupported authorization state for {field_name!r}")
        normalized_states[field_name] = str(state)
    for flag in (
        "FIELD_AUTHORIZATION_COMPLETE",
        "FIELD_AUTHORIZATION_DISJOINT",
        "FIELD_EVIDENCE_BINDING_CONSISTENT",
    ):
        if flag in value and value[flag] != "YES":
            raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, f"{flag} is not YES")
    result = dict(value)
    result["field_states"] = normalized_states
    return result


def _normalize_required_fields(
    value: Mapping[str, object] | Sequence[str] | None,
    field_authorization: Mapping[str, object],
) -> dict[str, object]:
    if value is None:
        value = ()
    if isinstance(value, Mapping):
        result = {str(key): item for key, item in value.items()}
    else:
        names = _strings(value, "required_generation_fields")
        states = field_authorization["field_states"]
        result = {
            name: {
                "authority": states.get(name),
                "boundary": "field_authorization",
                "allowed_freedom": states.get(name) == "NEW_DESIGN_AUTHORIZED",
            }
            for name in names
        }
    for field_name, metadata in result.items():
        _text(field_name, "required generation field")
        if not isinstance(metadata, Mapping):
            raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"metadata missing for {field_name!r}")
        if not isinstance(metadata.get("authority"), str) or not metadata["authority"].strip():
            raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"authority missing for {field_name!r}")
        if not isinstance(metadata.get("boundary"), str) or not metadata["boundary"].strip():
            raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"boundary missing for {field_name!r}")
        if "allowed_freedom" not in metadata:
            raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"allowed_freedom missing for {field_name!r}")
    return result


def _validate_evidence(
    context: CharacterPlanningContextV2,
    snapshot_id: str | None,
    source_ids: Sequence[str],
    supported_fields: Sequence[str],
    metadata: Mapping[str, object] | None,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    metadata = metadata or {}
    snapshot_id = snapshot_id or metadata.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise _fail(GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE, "evidence_snapshot_id is required")
    supplied_sources = tuple(source_ids) or tuple(metadata.get("authorized_source_ids", ()))
    normalized_sources = _ids(supplied_sources, "authorized_evidence_source_ids")
    known_sources = _context_source_ids(context)
    known_sources.update(_ids(metadata.get("known_source_ids", metadata.get("available_source_ids", ())), "known_source_ids"))
    if any(source_id not in known_sources for source_id in normalized_sources):
        raise _fail(GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE, "evidence source is outside the bounded context")
    supplied_fields = tuple(supported_fields) or tuple(metadata.get("supported_fields", ()))
    return snapshot_id.strip(), normalized_sources, _ids(supplied_fields, "evidence_supported_fields")


def _validate_canon_conflict(
    hard: Sequence[str], forbidden: Sequence[str], exact_values: Mapping[str, object]
) -> None:
    canonical = {
        _normalized(key): _normalized(value)
        for key, value in exact_values.items()
        if isinstance(value, str)
    }
    for constraint in (*hard, *forbidden):
        assignment = _assignment(constraint)
        if assignment is not None and assignment[0] in canonical and assignment[1] != canonical[assignment[0]]:
            raise _fail(GenerationSpecValidationReason.CANON_CONFLICT, f"{assignment[0]} conflicts with exact Canon value")


def _validate_boundary_authority(boundaries: Mapping[str, object], states: Mapping[str, object]) -> None:
    """Only explicit Canon assertion lists are checked; prose is not quality-scored."""

    for key in ("canon_fields", "canonical_fields", "canon_assertions", "canonical_assertions"):
        values = boundaries.get(key, ())
        if isinstance(values, str):
            values = (values,)
        if isinstance(values, Sequence):
            for field_name in values:
                if states.get(str(field_name)) != "CANON_GROUNDED_ONLY":
                    raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, f"{field_name!r} is not Canon-authorized")


def _validate_relationships(
    targets: Sequence[str],
    known_targets: set[str],
    forbidden: Sequence[str],
) -> None:
    if any(target not in known_targets for target in targets):
        raise _fail(GenerationSpecValidationReason.INVALID_RELATIONSHIP_TARGET, "relationship target is not known to roster/relationship context")
    forbidden_values = {_normalized(value) for value in forbidden}
    if any(_normalized(target) in forbidden_values for target in targets):
        raise _fail(GenerationSpecValidationReason.INVALID_RELATIONSHIP_TARGET, "relationship target is forbidden")


def _check_resolution_lineage(
    request: CharacterDesignRequest,
    context: CharacterPlanningContextV2,
    resolution: CharacterResolutionResult,
    planner_result: CharacterPlannerV1Result,
    seed: CharacterConceptSeedV2,
) -> None:
    if seed.status is not CharacterConceptSeedStatus.SELECTED:
        raise _fail(GenerationSpecValidationReason.INVALID_RESOLUTION, "selected seed is not SELECTED")
    if resolution.action is not ResolutionAction.SELECT or resolution.resolution_status is not DecisionResolutionStatus.RESOLVED:
        raise _fail(GenerationSpecValidationReason.INVALID_RESOLUTION, "freeze requires SELECT + RESOLVED")
    if set(resolution.source_candidate_ids) != {seed.concept_id}:
        raise _fail(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "resolution and selected seed differ")
    if not any(
        item.decision_path == "selected_concept_seed"
        and tuple(item.source_candidate_ids) == (seed.concept_id,)
        for item in resolution.resolved_decisions
    ):
        raise _fail(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "selected_concept_seed resolution record is missing")
    if planner_result.diagnostics.selected_concept_id != seed.concept_id:
        raise _fail(GenerationSpecValidationReason.PLANNER_IDENTITY_MISMATCH, "Planner concept differs from resolution")
    if planner_result.plan.status is not CharacterDesignPlanV2Status.PROPOSED or planner_result.diagnostics.status is not CharacterDesignPlanV2Status.PROPOSED:
        raise _fail(GenerationSpecValidationReason.PLANNER_IDENTITY_MISMATCH, "Planner output must remain PROPOSED")
    if len({request.request_id, context.plan_v2.request_id, planner_result.plan.request_id}) != 1:
        raise _fail(GenerationSpecValidationReason.PLANNER_IDENTITY_MISMATCH, "request IDs differ across boundaries")
    if planner_result.diagnostics.context_snapshot_id != context.snapshot_id:
        raise _fail(GenerationSpecValidationReason.PLANNER_IDENTITY_MISMATCH, "Planner snapshot differs from context snapshot")


def _audit(
    request: CharacterDesignRequest,
    context: CharacterPlanningContextV2,
    resolution: CharacterResolutionResult,
    planner_result: CharacterPlannerV1Result,
    seed: CharacterConceptSeedV2,
    evidence_snapshot_id: str,
) -> GenerationSpecAuditMetadataV1:
    return GenerationSpecAuditMetadataV1(
        request_digest=_digest(request.to_dict()),
        candidate_set_digest=_digest(tuple(item.to_dict() for item in resolution.lineage)),
        selected_seed_digest=_digest(seed.to_dict()),
        resolution_id=resolution.resolution_id,
        resolution_mode=resolution.mode.value,
        resolution_action=resolution.action.value,
        resolution_status=resolution.resolution_status.value,
        planner_snapshot_id=_digest(planner_result.plan.to_dict()),
        planning_context_snapshot_id=context.snapshot_id,
        evidence_snapshot_id=evidence_snapshot_id,
        selected_seed_id=seed.concept_id,
    )


def freeze_resolved_character_generation_spec(
    request: CharacterDesignRequest,
    planning_context: CharacterPlanningContextV2,
    resolution: CharacterResolutionResult,
    planner_result: CharacterPlannerV1Result,
    *,
    selected_seed: CharacterConceptSeedV2 | None = None,
    selector_selected_seed: CharacterConceptSeedV2 | None = None,
    evidence_snapshot_id: str | None = None,
    evidence_metadata: Mapping[str, object] | None = None,
    authorized_evidence_source_ids: Sequence[str] = (),
    evidence_supported_fields: Sequence[str] = (),
    field_authorization: Mapping[str, object] | None = None,
    canon_exact_values: Mapping[str, object] | None = None,
    allowed_faction_ids: Sequence[str] | None = None,
    allowed_organization_ids: Sequence[str] | None = None,
    allowed_relationship_targets: Sequence[str] | None = None,
    required_generation_fields: Mapping[str, object] | Sequence[str] | None = None,
    blocking_gap_codes: Sequence[ContextGapCode | str] = (),
) -> ResolvedCharacterGenerationSpecV1:
    """Freeze one already-resolved planning result without fallback or provider calls."""

    from agents.character_generation import CharacterDesignRequest

    if selected_seed is not None and selector_selected_seed is not None and selected_seed.concept_id != selector_selected_seed.concept_id:
        raise _fail(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "two selected seed arguments differ")
    seed = selected_seed or selector_selected_seed
    if seed is None:
        raise _fail(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "selected_seed is required")
    if field_authorization is None:
        raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, "field_authorization is required")
    if not isinstance(request, CharacterDesignRequest):
        raise TypeError("request must be a CharacterDesignRequest")
    if not isinstance(planning_context, CharacterPlanningContextV2):
        raise TypeError("planning_context must be a CharacterPlanningContextV2")
    if not isinstance(resolution, CharacterResolutionResult):
        raise TypeError("resolution must be a CharacterResolutionResult")
    if not isinstance(planner_result, CharacterPlannerV1Result):
        raise TypeError("planner_result must be a CharacterPlannerV1Result")
    _check_resolution_lineage(request, planning_context, resolution, planner_result, seed)

    hard = _strings(request.hard_constraints, "hard_requirements", sort=True)
    gender_text = "\n".join((request.brief, *request.hard_constraints))
    gender_requirement = parse_explicit_gender_requirement(gender_text)
    age_requirement = parse_explicit_age_requirement(gender_text)
    planning_intents = (
        planning_context.intent,
        planning_context.plan_v1.parsed_intent,
        planning_context.plan_v2.intent,
        planner_result.plan.intent,
    )
    if gender_requirement is not None:
        # INVARIANT: a direct user gender constraint remains typed through every
        # planning boundary and reaches the Generator as a hard requirement.
        if any(item.gender_requirement != gender_requirement for item in planning_intents):
            raise _fail(
                GenerationSpecValidationReason.INVALID_SPEC,
                "explicit gender requirement was not preserved through Planner context",
            )
        hard = _strings(
            (*hard, gender_requirement.to_hard_requirement()),
            "hard_requirements",
            sort=True,
        )
    if age_requirement is not None:
        if any(item.age_requirement != age_requirement for item in planning_intents):
            raise _fail(
                GenerationSpecValidationReason.INVALID_SPEC,
                "explicit age requirement was not preserved through Planner context",
            )
        hard = _strings(
            (*hard, age_requirement.to_hard_requirement()),
            "hard_requirements",
            sort=True,
        )
    expected_affiliation_id = planning_context.plan_v1.expected_affiliation_id
    requested_affiliations = tuple(
        item.requested_affiliation_id for item in planning_intents
    )
    if any(item != expected_affiliation_id for item in requested_affiliations):
        raise _fail(
            GenerationSpecValidationReason.INVALID_SPEC,
            "requested Canon affiliation was not preserved through Planner context",
        )
    forbidden = _strings(request.forbidden_elements, "forbidden_constraints", sort=True)
    if _constraint_conflict(hard, forbidden):
        raise _fail(GenerationSpecValidationReason.HARD_FORBIDDEN_CONFLICT, "hard and forbidden constraints overlap")
    authorization = _normalize_field_authorization(field_authorization)
    field_matrix = authorization.get("field_authorizations")
    if not isinstance(field_matrix, Mapping):
        raise _fail(
            GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION,
            "field_authorization must include the complete typed policy matrix",
        )
    expected_policy_fields = {field_value.value for field_value in CharacterGenerationField}
    if set(field_matrix) != expected_policy_fields:
        raise _fail(
            GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION,
            "field authorization matrix must cover every governed field exactly once",
        )
    try:
        typed_policy = FieldAuthorizationPolicy(
            {
                field_value: FieldAuthorization(
                    field=field_value,
                    state=FieldAuthorizationState(field_matrix[field_value.value]["state"]),
                    authorized_source_ids=field_matrix[field_value.value].get(
                        "authorized_source_ids", ()
                    ),
                    allowed_exact_values=field_matrix[field_value.value].get(
                        "allowed_exact_values", ()
                    ),
                    requires_grounding=field_matrix[field_value.value].get(
                        "requires_grounding", False
                    ),
                )
                for field_value in CharacterGenerationField
                if isinstance(field_matrix.get(field_value.value), Mapping)
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _fail(
            GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION,
            "field authorization matrix contains an invalid entry",
        ) from error
    if len(typed_policy.field_authorizations) != len(CharacterGenerationField):
        raise _fail(
            GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION,
            "field authorization matrix contains an invalid entry",
        )
    if any(
        authorization["field_states"].get(field_value.value)
        != typed_policy.for_field(field_value).state.value
        for field_value in CharacterGenerationField
    ):
        raise _fail(
            GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION,
            "field authorization state projections disagree",
        )
    required = _normalize_required_fields(required_generation_fields, authorization)
    states = authorization["field_states"]
    for field_name in required:
        if states.get(field_name) == "UNAUTHORIZED":
            raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"required field {field_name!r} is unauthorized")
        if any(_normalized(field_name) == _normalized(value) for value in forbidden):
            raise _fail(GenerationSpecValidationReason.HARD_FORBIDDEN_CONFLICT, f"required field {field_name!r} is forbidden")

    exact_values = dict(canon_exact_values or {})
    _validate_canon_conflict(hard, forbidden, exact_values)
    for field_name in exact_values:
        if states.get(str(field_name)) != "CANON_GROUNDED_ONLY":
            raise _fail(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, f"Canon value {field_name!r} is unauthorized")

    snapshot_id, source_ids, supported_fields = _validate_evidence(
        planning_context,
        evidence_snapshot_id,
        authorized_evidence_source_ids,
        evidence_supported_fields,
        evidence_metadata,
    )
    for field_name in supported_fields:
        if states.get(field_name) == "UNAUTHORIZED":
            raise _fail(GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE, f"evidence supports unauthorized field {field_name!r}")

    derived_factions, derived_organizations = _derive_allowed_ids(planning_context)
    factions = _ids(derived_factions if allowed_faction_ids is None else allowed_faction_ids, "allowed_faction_ids")
    organizations = _ids(derived_organizations if allowed_organization_ids is None else allowed_organization_ids, "allowed_organization_ids")
    derived_targets = _derive_relationship_targets(planning_context)
    targets = _ids(derived_targets if allowed_relationship_targets is None else allowed_relationship_targets, "allowed_relationship_targets")
    _validate_relationships(targets, set(derived_targets), forbidden)

    blocking_codes = {
        code if isinstance(code, ContextGapCode) else ContextGapCode(code)
        for code in blocking_gap_codes
    }
    blocking_codes |= _DEFAULT_BLOCKING_GAP_CODES & {gap.code for gap in planning_context.gaps}
    blocking = [gap.code.value for gap in planning_context.gaps if gap.code in blocking_codes]
    if blocking:
        raise _fail(GenerationSpecValidationReason.BLOCKING_GAP, ", ".join(sorted(blocking)))

    combat = request.combat_role_profile or planning_context.combat.requested_role_profile
    if combat is not None and combat.is_unspecified:
        combat = None
    if any(_normalized(name).startswith("combat") for name in required) and combat is None:
        raise _fail(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, "combat semantics are required but absent")

    plan = planner_result.plan
    if plan.naming_design is None:
        raise _fail(
            GenerationSpecValidationReason.INVALID_SPEC,
            "Planner result has no validated Naming Design",
        )
    explicit_names = extract_explicit_character_names(
        (request.brief, *request.hard_constraints)
    )
    if len({unicodedata.normalize("NFKC", name).casefold() for name in explicit_names}) > 1:
        raise _fail(
            GenerationSpecValidationReason.INVALID_SPEC,
            "request contains conflicting explicit character names",
        )
    if plan.naming_design.owner is CharacterNamingOwner.USER_SPECIFIED:
        if (
            plan.naming_design.selected_candidate_id != "USER_SPECIFIED"
            or not explicit_names
            or plan.naming_design.selected_name != explicit_names[0]
        ):
            raise _fail(
                GenerationSpecValidationReason.INVALID_SPEC,
                "user-owned name has no matching explicit naming intent in the original request",
            )
    elif explicit_names:
        raise _fail(
            GenerationSpecValidationReason.INVALID_SPEC,
            "Planner owns a name despite explicit user naming intent",
        )
    story_boundaries = {
        "narrative_role": _jsonable(plan.narrative_role),
        "character_core": _jsonable(plan.character_core),
        "arc_seed": _jsonable(plan.arc_seed),
    }
    gameplay_boundaries = {"gameplay_identity": _jsonable(plan.gameplay_identity)}
    visual_boundaries = {"visual_identity": _jsonable(plan.visual_identity)}
    _validate_boundary_authority(story_boundaries, states)
    _validate_boundary_authority(gameplay_boundaries, states)
    _validate_boundary_authority(visual_boundaries, states)

    audit = _audit(request, planning_context, resolution, planner_result, seed, snapshot_id)
    # WHY: digest the normalized dataclass view, not pre-normalized caller
    # containers; otherwise tuple/list conversion or ordered question cleanup
    # could make an otherwise identical semantic input hash differently.
    draft = ResolvedCharacterGenerationSpecV1(
        spec_version=RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA,
        spec_id="pending",
        spec_digest="pending",
        request_id=request.request_id,
        route_identity=CHARACTER_GENERATION_V2_ROUTE,
        hard_requirements=hard,
        forbidden_constraints=forbidden,
        resolved_direction=ResolvedCharacterDirectionV1.from_seed(seed),
        story_boundaries=story_boundaries,
        gameplay_boundaries=gameplay_boundaries,
        visual_boundaries=visual_boundaries,
        canon_exact_values=exact_values,
        allowed_faction_ids=factions,
        allowed_organization_ids=organizations,
        allowed_relationship_targets=targets,
        field_authorization=authorization,
        known_gaps=planning_context.gaps,
        required_generation_fields=required,
        evidence_snapshot_id=snapshot_id,
        authorized_evidence_source_ids=source_ids,
        evidence_supported_fields=supported_fields,
        audit_metadata=audit,
        combat_semantics=combat,
        soft_preferences=_strings(request.soft_preferences, "soft_preferences", sort=True),
        bounded_open_questions=plan.unresolved_questions,
        non_blocking_relationship_hints=tuple(
            item.to_dict() for item in plan.relationship_strategy.proposed_relationship_opportunities
        ),
        naming_design=plan.naming_design,
        gender_requirement=gender_requirement,
        age_requirement=age_requirement,
        requested_affiliation_id=expected_affiliation_id,
    )
    digest = _digest(draft.semantic_dict())
    spec = replace(
        draft,
        spec_id=f"{RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA}:{digest}",
        spec_digest=digest,
    )
    result = GenerationSpecValidator().validate(spec)
    if not result.valid:
        raise GenerationSpecFreezeError(result.reason, result.detail)
    return spec


class GenerationSpecValidator:
    """Deterministic façade over structural and cross-boundary spec checks."""

    def validate(self, spec: ResolvedCharacterGenerationSpecV1) -> GenerationSpecValidationResult:
        if not isinstance(spec, ResolvedCharacterGenerationSpecV1):
            return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_SPEC, "value is not the V1 generation spec")
        try:
            if spec.spec_version != RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA or spec.route_identity != CHARACTER_GENERATION_V2_ROUTE:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_SPEC, "schema or route identity is unsupported")
            if not spec.spec_id.endswith(spec.spec_digest) or _digest(spec.semantic_dict()) != spec.spec_digest:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_SPEC, "spec digest does not match semantic payload")
            audit = spec.audit_metadata
            if audit.resolution_action != ResolutionAction.SELECT.value or audit.resolution_status != DecisionResolutionStatus.RESOLVED.value:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_RESOLUTION, "resolution gate is not SELECT + RESOLVED")
            if not audit.selected_seed_digest:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "selected seed digest is missing")
            if audit.selected_seed_id and audit.selected_seed_id != spec.resolved_direction.concept_id:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.SEED_IDENTITY_MISMATCH, "selected seed identity differs from resolved direction")
            if _constraint_conflict(spec.hard_requirements, spec.forbidden_constraints):
                return GenerationSpecValidationResult(GenerationSpecValidationReason.HARD_FORBIDDEN_CONFLICT, "hard and forbidden constraints overlap")
            authorization = _normalize_field_authorization(spec.field_authorization)
            spec.field_authorization_policy
            required = _normalize_required_fields(spec.required_generation_fields, authorization)
            states = authorization["field_states"]
            for field_name in required:
                if states.get(field_name) == "UNAUTHORIZED":
                    return GenerationSpecValidationResult(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, f"required field {field_name!r} is unauthorized")
                if any(_normalized(field_name) == _normalized(value) for value in spec.forbidden_constraints):
                    return GenerationSpecValidationResult(GenerationSpecValidationReason.HARD_FORBIDDEN_CONFLICT, f"required field {field_name!r} is forbidden")
            _validate_canon_conflict(spec.hard_requirements, spec.forbidden_constraints, spec.canon_exact_values)
            for field_name in spec.canon_exact_values:
                if states.get(field_name) != "CANON_GROUNDED_ONLY":
                    return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_FIELD_AUTHORIZATION, f"Canon value {field_name!r} is unauthorized")
            _validate_boundary_authority(spec.story_boundaries, states)
            _validate_boundary_authority(spec.gameplay_boundaries, states)
            _validate_boundary_authority(spec.visual_boundaries, states)
            if not spec.evidence_snapshot_id:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE, "evidence snapshot is missing")
            if (
                spec.requested_affiliation_id is not None
                and spec.requested_affiliation_id not in spec.allowed_faction_ids
            ):
                return GenerationSpecValidationResult(
                    GenerationSpecValidationReason.INVALID_SPEC,
                    "requested Canon affiliation is outside the allowed faction set",
                )
            if any(states.get(field_name) == "UNAUTHORIZED" for field_name in spec.evidence_supported_fields):
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_EVIDENCE_REFERENCE, "evidence supports an unauthorized field")
            if len(spec.allowed_relationship_targets) != len(set(spec.allowed_relationship_targets)):
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_RELATIONSHIP_TARGET, "relationship targets are duplicated")
            forbidden = {_normalized(value) for value in spec.forbidden_constraints}
            if any(_normalized(target) in forbidden for target in spec.allowed_relationship_targets):
                return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_RELATIONSHIP_TARGET, "relationship target is forbidden")
            if any(gap.code in _DEFAULT_BLOCKING_GAP_CODES for gap in spec.known_gaps):
                return GenerationSpecValidationResult(GenerationSpecValidationReason.BLOCKING_GAP, "known gaps contain a blocking gap")
            if any(_normalized(name).startswith("combat") for name in required) and spec.combat_semantics is None:
                return GenerationSpecValidationResult(GenerationSpecValidationReason.MISSING_REQUIRED_GENERATION_FIELD, "combat semantics are required but absent")
        except GenerationSpecFreezeError as error:
            return GenerationSpecValidationResult(error.reason, error.detail)
        except (TypeError, ValueError, KeyError) as error:
            return GenerationSpecValidationResult(GenerationSpecValidationReason.INVALID_SPEC, str(error))
        return GenerationSpecValidationResult(GenerationSpecValidationReason.VALID)

    def validate_or_raise(self, spec: ResolvedCharacterGenerationSpecV1) -> ResolvedCharacterGenerationSpecV1:
        """Validate and return the same immutable spec, or fail closed."""

        result = self.validate(spec)
        if not result.valid:
            raise GenerationSpecFreezeError(result.reason, result.detail)
        return spec


__all__ = [
    "CHARACTER_GENERATION_V2_ROUTE",
    "RESOLVED_CHARACTER_GENERATION_SPEC_V1_SCHEMA",
    "GenerationSpecAuditMetadataV1",
    "GenerationSpecFreezeError",
    "GenerationSpecValidationReason",
    "GenerationSpecValidationResult",
    "GenerationSpecValidator",
    "ResolvedCharacterDirectionV1",
    "ResolvedCharacterGenerationSpecV1",
    "freeze_resolved_character_generation_spec",
]
