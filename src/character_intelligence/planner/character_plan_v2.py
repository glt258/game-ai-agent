"""Typed, provider-independent Character Design Plan v2 shadow contract.

This module is intentionally not imported by the production generation path.
The adapter projects already-known request, intent, and V1 plan data only; it
does not make new planning decisions or perform retrieval/model calls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar

from combat_semantics import CombatRoleProfile

from ..intent import CharacterDesignIntent
from ..naming_design import CharacterNamingDesignV1
from .character_plan import CharacterDesignPlan

CHARACTER_DESIGN_PLAN_V2_SCHEMA = "character-design-plan/v2"


class CharacterDesignPlanV2Status(str, Enum):
    """Planning completeness, never Canon or acceptance state."""

    SHADOW_PROJECTED = "SHADOW_PROJECTED"
    PROPOSED = "PROPOSED"
    SELECTED = "SELECTED"
    REVIEWABLE = "REVIEWABLE"


class CharacterPlanV2Source(str, Enum):
    """Allowed origins for values recorded by a future planner."""

    USER_SUPPLIED = "USER_SUPPLIED"
    INTENT = "INTENT"
    DETERMINISTIC = "DETERMINISTIC"
    CANON_RETRIEVAL = "CANON_RETRIEVAL"
    REFERENCE_CORPUS = "REFERENCE_CORPUS"
    PLANNER_PROPOSAL = "PLANNER_PROPOSAL"
    CONCEPT_SELECTION = "CONCEPT_SELECTION"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class CharacterPlanV2Owner(str, Enum):
    """Decision owners, distinct from the evidence/source origin."""

    USER = "USER"
    INTENT = "INTENT"
    DETERMINISTIC = "DETERMINISTIC"
    RETRIEVAL = "RETRIEVAL"
    PLANNER = "PLANNER"
    GENERATOR = "GENERATOR"
    HUMAN = "HUMAN"


class CharacterPlanV2ConstraintKind(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    INFERRED = "INFERRED"
    UNRESOLVED = "UNRESOLVED"


_T = TypeVar("_T")


def _strings(value: Sequence[str] | None, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        cleaned = item.strip()
        if cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _text(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not allow_empty and not cleaned:
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


def _mapping(value: object, type_name: str, allowed: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{type_name} has unknown field(s): {sorted(unknown)}")
    return value


def _serialize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _normalize_optional_fields(
    instance: object,
    optional_fields: Sequence[str],
    sequence_fields: Sequence[str] = (),
) -> None:
    for field_name in optional_fields:
        object.__setattr__(
            instance, field_name, _optional_text(getattr(instance, field_name), field_name)
        )
    for field_name in sequence_fields:
        object.__setattr__(
            instance, field_name, _strings(getattr(instance, field_name), field_name)
        )


@dataclass(frozen=True)
class CharacterPlanV2Constraint:
    """One request/intent binding; soft values never become hard silently."""

    key: str
    value: str
    kind: CharacterPlanV2ConstraintKind
    source: CharacterPlanV2Source
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _text(self.key, "key"))
        object.__setattr__(self, "value", _text(self.value, "value"))
        object.__setattr__(self, "kind", _enum(CharacterPlanV2ConstraintKind, self.kind, "kind"))
        object.__setattr__(self, "source", _enum(CharacterPlanV2Source, self.source, "source"))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterPlanV2Constraint":
        data = _mapping(payload, cls.__name__, {"key", "value", "kind", "source", "evidence_refs"})
        return cls(
            key=data["key"],
            value=data["value"],
            kind=data["kind"],
            source=data["source"],
            evidence_refs=data.get("evidence_refs", ()),
        )


@dataclass(frozen=True)
class CharacterPlanV2RelationshipBinding:
    """A relation candidate with explicit semantics; never a Canon mutation."""

    target: str
    source: CharacterPlanV2Source
    description: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _text(self.target, "target"))
        object.__setattr__(self, "source", _enum(CharacterPlanV2Source, self.source, "source"))
        object.__setattr__(self, "description", _optional_text(self.description, "description"))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterPlanV2RelationshipBinding":
        data = _mapping(
            payload,
            cls.__name__,
            {"target", "source", "description", "evidence_refs"},
        )
        return cls(
            target=data["target"],
            source=data["source"],
            description=data.get("description"),
            evidence_refs=data.get("evidence_refs", ()),
        )


@dataclass(frozen=True)
class CharacterPlanV2ReferenceProvenance:
    """Safe reference metadata; source text and provider material are excluded."""

    pattern: str
    origin: CharacterPlanV2Source
    source_reference_id: str | None = None
    source_display_name: str | None = None
    selection_role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", _text(self.pattern, "pattern"))
        object.__setattr__(self, "origin", _enum(CharacterPlanV2Source, self.origin, "origin"))
        for field_name in ("source_reference_id", "source_display_name", "selection_role"):
            object.__setattr__(
                self, field_name, _optional_text(getattr(self, field_name), field_name)
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterPlanV2ReferenceProvenance":
        data = _mapping(
            payload,
            cls.__name__,
            {"pattern", "origin", "source_reference_id", "source_display_name", "selection_role"},
        )
        return cls(
            pattern=data["pattern"],
            origin=data["origin"],
            source_reference_id=data.get("source_reference_id"),
            source_display_name=data.get("source_display_name"),
            selection_role=data.get("selection_role"),
        )


@dataclass(frozen=True)
class CharacterPlanV2Decision:
    """Provenance/ownership note for a known or future decision boundary."""

    field_path: str
    owner: CharacterPlanV2Owner
    source: CharacterPlanV2Source
    evidence_refs: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_path", _text(self.field_path, "field_path"))
        object.__setattr__(self, "owner", _enum(CharacterPlanV2Owner, self.owner, "owner"))
        object.__setattr__(self, "source", _enum(CharacterPlanV2Source, self.source, "source"))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))
        object.__setattr__(self, "note", _optional_text(self.note, "note"))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterPlanV2Decision":
        data = _mapping(
            payload,
            cls.__name__,
            {"field_path", "owner", "source", "evidence_refs", "note"},
        )
        return cls(
            field_path=data["field_path"],
            owner=data["owner"],
            source=data["source"],
            evidence_refs=data.get("evidence_refs", ()),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class CharacterPlanV2ProductRosterPositioning:
    """Future product/roster home; shadow projection intentionally leaves it empty."""

    roster_role: str | None = None
    debut_function: str | None = None
    cast_differentiation: str | None = None
    player_facing_hook: str | None = None
    overlap_risks: tuple[str, ...] = ()
    availability_positioning: str | None = None

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            (
                "roster_role",
                "debut_function",
                "cast_differentiation",
                "player_facing_hook",
                "availability_positioning",
            ),
            ("overlap_risks",),
        )


@dataclass(frozen=True)
class CharacterPlanV2NarrativeRole:
    dramatic_function: str | None = None
    story_entry_function: str | None = None
    protagonist_connection: str | None = None
    faction_story_function: str | None = None
    long_term_narrative_utility: str | None = None

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            (
                "dramatic_function",
                "story_entry_function",
                "protagonist_connection",
                "faction_story_function",
                "long_term_narrative_utility",
            ),
        )


@dataclass(frozen=True)
class CharacterPlanV2CharacterCore:
    surface_impression: str | None = None
    core_desire: str | None = None
    core_fear: str | None = None
    internal_contradiction: str | None = None
    false_belief: str | None = None
    emotional_need: str | None = None
    values_or_moral_boundary: str | None = None
    behavioral_pressure_point: str | None = None

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            (
                "surface_impression",
                "core_desire",
                "core_fear",
                "internal_contradiction",
                "false_belief",
                "emotional_need",
                "values_or_moral_boundary",
                "behavioral_pressure_point",
            ),
        )


@dataclass(frozen=True)
class CharacterPlanV2RelationshipStrategy:
    """Separate relation categories prevent a proposal from becoming a fact."""

    requested_relationships: tuple[CharacterPlanV2RelationshipBinding, ...] = ()
    canon_grounded_relationships: tuple[CharacterPlanV2RelationshipBinding, ...] = ()
    proposed_relationship_opportunities: tuple[CharacterPlanV2RelationshipBinding, ...] = ()
    conflict_opportunities: tuple[CharacterPlanV2RelationshipBinding, ...] = ()
    affinity_opportunities: tuple[CharacterPlanV2RelationshipBinding, ...] = ()
    relationship_risks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in _RELATION_FIELDS:
            value = tuple(getattr(self, field_name))
            if not all(isinstance(item, CharacterPlanV2RelationshipBinding) for item in value):
                raise TypeError(
                    f"{field_name} must contain CharacterPlanV2RelationshipBinding values"
                )
            object.__setattr__(self, field_name, value)
        object.__setattr__(
            self, "relationship_risks", _strings(self.relationship_risks, "relationship_risks")
        )


@dataclass(frozen=True)
class CharacterPlanV2GameplayIdentity:
    """Gameplay fields reuse the existing canonical combat-role profile."""

    combat_role_profile: CombatRoleProfile | None = None
    gameplay_fantasy: str | None = None
    mechanic_identity_direction: str | None = None
    narrative_gameplay_linkage: str | None = None
    field_time: str | None = None
    resource_model: tuple[str, ...] = ()
    state_model: tuple[str, ...] = ()
    core_loop: tuple[str, ...] = ()
    payoff: tuple[str, ...] = ()
    team_handoff: str | None = None

    def __post_init__(self) -> None:
        if self.combat_role_profile is not None and not isinstance(
            self.combat_role_profile, CombatRoleProfile
        ):
            raise TypeError(
                "gameplay_identity.combat_role_profile must be a CombatRoleProfile or None"
            )
        _normalize_optional_fields(
            self,
            (
                "gameplay_fantasy",
                "mechanic_identity_direction",
                "narrative_gameplay_linkage",
                "field_time",
                "team_handoff",
            ),
            ("resource_model", "state_model", "core_loop", "payoff"),
        )


@dataclass(frozen=True)
class CharacterPlanV2VisualIdentity:
    silhouette_direction: str | None = None
    motif_direction: str | None = None
    costume_logic: str | None = None
    signature_visual_feature: str | None = None
    visual_differentiation_risks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            (
                "silhouette_direction",
                "motif_direction",
                "costume_logic",
                "signature_visual_feature",
            ),
            ("visual_differentiation_risks",),
        )


@dataclass(frozen=True)
class CharacterPlanV2ArcSeed:
    initial_state: str | None = None
    pressure_point: str | None = None
    possible_transformation: str | None = None
    unresolved_future_hook: str | None = None

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            (
                "initial_state",
                "pressure_point",
                "possible_transformation",
                "unresolved_future_hook",
            ),
        )


@dataclass(frozen=True)
class CharacterPlanV2RiskAnalysis:
    roster_overlap_risks: tuple[str, ...] = ()
    trope_dependence_risks: tuple[str, ...] = ()
    genericness_risks: tuple[str, ...] = ()
    canon_risks: tuple[str, ...] = ()
    relationship_contradiction_risks: tuple[str, ...] = ()
    combat_identity_overlap_risks: tuple[str, ...] = ()
    visual_overlap_risks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalize_optional_fields(self, (), tuple(item.name for item in fields(self)))


@dataclass(frozen=True)
class CharacterPlanV2ReferenceBasis:
    selected_pattern_ids: tuple[str, ...] = ()
    contrast_pattern_ids: tuple[str, ...] = ()
    negative_pattern_ids: tuple[str, ...] = ()
    provenance: tuple[CharacterPlanV2ReferenceProvenance, ...] = ()
    low_coverage_axes: tuple[str, ...] = ()
    novelty_basis: str | None = None
    coverage_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalize_optional_fields(
            self,
            ("novelty_basis",),
            (
                "selected_pattern_ids",
                "contrast_pattern_ids",
                "negative_pattern_ids",
                "low_coverage_axes",
                "coverage_notes",
            ),
        )
        provenance = tuple(self.provenance)
        if not all(isinstance(item, CharacterPlanV2ReferenceProvenance) for item in provenance):
            raise TypeError("provenance must contain CharacterPlanV2ReferenceProvenance values")
        object.__setattr__(self, "provenance", provenance)


_RELATION_FIELDS = (
    "requested_relationships",
    "canon_grounded_relationships",
    "proposed_relationship_opportunities",
    "conflict_opportunities",
    "affinity_opportunities",
)


@dataclass(frozen=True)
class CharacterDesignPlanV2:
    """A forward planning boundary; a shadow projection is not a finished design."""

    intent: CharacterDesignIntent
    request_id: str = "request_001"
    status: CharacterDesignPlanV2Status = CharacterDesignPlanV2Status.SHADOW_PROJECTED
    constraints: tuple[CharacterPlanV2Constraint, ...] = ()
    product_roster_positioning: CharacterPlanV2ProductRosterPositioning = field(
        default_factory=CharacterPlanV2ProductRosterPositioning
    )
    narrative_role: CharacterPlanV2NarrativeRole = field(
        default_factory=CharacterPlanV2NarrativeRole
    )
    character_core: CharacterPlanV2CharacterCore = field(
        default_factory=CharacterPlanV2CharacterCore
    )
    relationship_strategy: CharacterPlanV2RelationshipStrategy = field(
        default_factory=CharacterPlanV2RelationshipStrategy
    )
    gameplay_identity: CharacterPlanV2GameplayIdentity = field(
        default_factory=CharacterPlanV2GameplayIdentity
    )
    visual_identity: CharacterPlanV2VisualIdentity = field(
        default_factory=CharacterPlanV2VisualIdentity
    )
    arc_seed: CharacterPlanV2ArcSeed = field(default_factory=CharacterPlanV2ArcSeed)
    reference_basis: CharacterPlanV2ReferenceBasis = field(
        default_factory=CharacterPlanV2ReferenceBasis
    )
    risks: CharacterPlanV2RiskAnalysis = field(default_factory=CharacterPlanV2RiskAnalysis)
    naming_design: CharacterNamingDesignV1 | None = None
    decisions: tuple[CharacterPlanV2Decision, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = CHARACTER_DESIGN_PLAN_V2_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.intent, CharacterDesignIntent):
            raise TypeError("intent must be a CharacterDesignIntent")
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(
            self, "status", _enum(CharacterDesignPlanV2Status, self.status, "status")
        )
        if self.schema_version != CHARACTER_DESIGN_PLAN_V2_SCHEMA:
            raise ValueError(f"unsupported schema_version: {self.schema_version!r}")
        object.__setattr__(self, "constraints", tuple(self.constraints))
        if not all(isinstance(item, CharacterPlanV2Constraint) for item in self.constraints):
            raise TypeError("constraints must contain CharacterPlanV2Constraint values")
        for field_name, field_type in (
            ("product_roster_positioning", CharacterPlanV2ProductRosterPositioning),
            ("narrative_role", CharacterPlanV2NarrativeRole),
            ("character_core", CharacterPlanV2CharacterCore),
            ("relationship_strategy", CharacterPlanV2RelationshipStrategy),
            ("gameplay_identity", CharacterPlanV2GameplayIdentity),
            ("visual_identity", CharacterPlanV2VisualIdentity),
            ("arc_seed", CharacterPlanV2ArcSeed),
            ("reference_basis", CharacterPlanV2ReferenceBasis),
            ("risks", CharacterPlanV2RiskAnalysis),
        ):
            if not isinstance(getattr(self, field_name), field_type):
                raise TypeError(f"{field_name} must be a {field_type.__name__}")
        if self.naming_design is not None and not isinstance(
            self.naming_design, CharacterNamingDesignV1
        ):
            raise TypeError("naming_design must be CharacterNamingDesignV1 or None")
        object.__setattr__(self, "decisions", tuple(self.decisions))
        if not all(isinstance(item, CharacterPlanV2Decision) for item in self.decisions):
            raise TypeError("decisions must contain CharacterPlanV2Decision values")
        object.__setattr__(
            self,
            "unresolved_questions",
            _strings(self.unresolved_questions, "unresolved_questions"),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings"))

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic JSON-compatible data with no provider state."""

        return _serialize(self)  # type: ignore[return-value]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CharacterDesignPlanV2":
        allowed = {
            "intent",
            "request_id",
            "status",
            "constraints",
            "product_roster_positioning",
            "narrative_role",
            "character_core",
            "relationship_strategy",
            "gameplay_identity",
            "visual_identity",
            "arc_seed",
            "reference_basis",
            "risks",
            "naming_design",
            "decisions",
            "unresolved_questions",
            "warnings",
            "schema_version",
        }
        data = _mapping(payload, cls.__name__, allowed)
        return cls(
            intent=CharacterDesignIntent.from_mapping(data["intent"]),
            request_id=data.get("request_id", "request_001"),
            status=data.get("status", CharacterDesignPlanV2Status.SHADOW_PROJECTED),
            constraints=tuple(
                CharacterPlanV2Constraint.from_mapping(item) for item in data.get("constraints", ())
            ),
            product_roster_positioning=_simple_from_mapping(
                CharacterPlanV2ProductRosterPositioning,
                data.get("product_roster_positioning"),
                "product_roster_positioning",
            ),
            narrative_role=_simple_from_mapping(
                CharacterPlanV2NarrativeRole, data.get("narrative_role"), "narrative_role"
            ),
            character_core=_simple_from_mapping(
                CharacterPlanV2CharacterCore, data.get("character_core"), "character_core"
            ),
            relationship_strategy=_relationship_strategy_from_mapping(
                data.get("relationship_strategy")
            ),
            gameplay_identity=_gameplay_identity_from_mapping(data.get("gameplay_identity")),
            visual_identity=_simple_from_mapping(
                CharacterPlanV2VisualIdentity, data.get("visual_identity"), "visual_identity"
            ),
            arc_seed=_simple_from_mapping(CharacterPlanV2ArcSeed, data.get("arc_seed"), "arc_seed"),
            reference_basis=_reference_basis_from_mapping(data.get("reference_basis")),
            risks=_simple_from_mapping(CharacterPlanV2RiskAnalysis, data.get("risks"), "risks"),
            naming_design=(
                CharacterNamingDesignV1.from_mapping(data["naming_design"])
                if data.get("naming_design") is not None
                else None
            ),
            decisions=tuple(
                CharacterPlanV2Decision.from_mapping(item) for item in data.get("decisions", ())
            ),
            unresolved_questions=data.get("unresolved_questions", ()),
            warnings=data.get("warnings", ()),
            schema_version=data.get("schema_version", CHARACTER_DESIGN_PLAN_V2_SCHEMA),
        )


def _simple_from_mapping(type_: type[_T], value: object, field_name: str) -> _T:
    if value is None:
        return type_()  # type: ignore[call-arg]
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    allowed = {item.name for item in fields(type_)}
    data = _mapping(value, type_.__name__, allowed)
    kwargs: dict[str, Any] = {}
    for item in fields(type_):
        raw = data.get(item.name, item.default)
        if (
            item.name.endswith("_risks")
            or item.name.endswith("_notes")
            or item.name.endswith("_questions")
        ):
            kwargs[item.name] = _strings(raw, f"{field_name}.{item.name}")
        elif (
            item.type == "str | None" or item.type is str | None
        ):  # pragma: no cover - annotation compatibility
            kwargs[item.name] = _optional_text(raw, f"{field_name}.{item.name}")
        else:
            kwargs[item.name] = raw
    return type_(**kwargs)  # type: ignore[call-arg,return-value]


def _relationship_strategy_from_mapping(value: object) -> CharacterPlanV2RelationshipStrategy:
    if value is None:
        return CharacterPlanV2RelationshipStrategy()
    if not isinstance(value, Mapping):
        raise TypeError("relationship_strategy must be a mapping")
    allowed = set(_RELATION_FIELDS) | {"relationship_risks"}
    data = _mapping(value, "CharacterPlanV2RelationshipStrategy", allowed)
    kwargs = {
        field_name: tuple(
            CharacterPlanV2RelationshipBinding.from_mapping(item)
            for item in data.get(field_name, ())
        )
        for field_name in _RELATION_FIELDS
    }
    kwargs["relationship_risks"] = _strings(
        data.get("relationship_risks", ()), "relationship_risks"
    )
    return CharacterPlanV2RelationshipStrategy(**kwargs)


def _gameplay_identity_from_mapping(value: object) -> CharacterPlanV2GameplayIdentity:
    if value is None:
        return CharacterPlanV2GameplayIdentity()
    if not isinstance(value, Mapping):
        raise TypeError("gameplay_identity must be a mapping")
    allowed = {item.name for item in fields(CharacterPlanV2GameplayIdentity)}
    data = _mapping(value, "CharacterPlanV2GameplayIdentity", allowed)
    profile = data.get("combat_role_profile")
    return CharacterPlanV2GameplayIdentity(
        combat_role_profile=(
            CombatRoleProfile.from_mapping(profile) if profile is not None else None
        ),
        gameplay_fantasy=_optional_text(
            data.get("gameplay_fantasy"), "gameplay_identity.gameplay_fantasy"
        ),
        mechanic_identity_direction=_optional_text(
            data.get("mechanic_identity_direction"), "gameplay_identity.mechanic_identity_direction"
        ),
        narrative_gameplay_linkage=_optional_text(
            data.get("narrative_gameplay_linkage"), "gameplay_identity.narrative_gameplay_linkage"
        ),
        field_time=_optional_text(data.get("field_time"), "gameplay_identity.field_time"),
        resource_model=_strings(data.get("resource_model", ()), "gameplay_identity.resource_model"),
        state_model=_strings(data.get("state_model", ()), "gameplay_identity.state_model"),
        core_loop=_strings(data.get("core_loop", ()), "gameplay_identity.core_loop"),
        payoff=_strings(data.get("payoff", ()), "gameplay_identity.payoff"),
        team_handoff=_optional_text(data.get("team_handoff"), "gameplay_identity.team_handoff"),
    )


def _reference_basis_from_mapping(value: object) -> CharacterPlanV2ReferenceBasis:
    if value is None:
        return CharacterPlanV2ReferenceBasis()
    if not isinstance(value, Mapping):
        raise TypeError("reference_basis must be a mapping")
    allowed = {item.name for item in fields(CharacterPlanV2ReferenceBasis)}
    data = _mapping(value, "CharacterPlanV2ReferenceBasis", allowed)
    return CharacterPlanV2ReferenceBasis(
        selected_pattern_ids=_strings(data.get("selected_pattern_ids", ()), "selected_pattern_ids"),
        contrast_pattern_ids=_strings(data.get("contrast_pattern_ids", ()), "contrast_pattern_ids"),
        negative_pattern_ids=_strings(data.get("negative_pattern_ids", ()), "negative_pattern_ids"),
        provenance=tuple(
            CharacterPlanV2ReferenceProvenance.from_mapping(item)
            for item in data.get("provenance", ())
        ),
        low_coverage_axes=_strings(data.get("low_coverage_axes", ()), "low_coverage_axes"),
        novelty_basis=_optional_text(data.get("novelty_basis"), "novelty_basis"),
        coverage_notes=_strings(data.get("coverage_notes", ()), "coverage_notes"),
    )


_SHADOW_UNRESOLVED_DOMAINS = (
    "product_roster_positioning",
    "narrative_role",
    "character_core",
    "future_relationship_opportunities",
    "visual_identity",
    "arc_seed",
    "differentiation_risk_analysis",
)


def _request_strings(request: Mapping[str, Any] | None, key: str) -> tuple[str, ...]:
    if request is None:
        return ()
    return _strings(request.get(key, ()), f"request.{key}")


def _append_constraint(
    result: list[CharacterPlanV2Constraint],
    seen: set[tuple[str, str, CharacterPlanV2ConstraintKind, CharacterPlanV2Source]],
    *,
    key: str,
    value: str,
    kind: CharacterPlanV2ConstraintKind,
    source: CharacterPlanV2Source,
) -> None:
    marker = (key, value, kind, source)
    if marker in seen:
        return
    seen.add(marker)
    result.append(CharacterPlanV2Constraint(key, value, kind, source))


def project_character_plan_v2(
    plan: CharacterDesignPlan,
    *,
    request: Mapping[str, Any] | None = None,
) -> CharacterDesignPlanV2:
    """Project known V1/request artifacts without making new design decisions.

    ``request`` is intentionally a mapping rather than an import of the agent
    request class.  This keeps the shadow module independent from the
    production generation module and makes the adapter safe to inspect in
    isolation.  A validated ``CharacterDesignRequest.to_dict()`` is the
    intended input.
    """

    if not isinstance(plan, CharacterDesignPlan):
        raise TypeError("plan must be a CharacterDesignPlan")
    if request is not None and not isinstance(request, Mapping):
        raise TypeError("request must be a mapping or None")

    constraints: list[CharacterPlanV2Constraint] = []
    seen: set[tuple[str, str, CharacterPlanV2ConstraintKind, CharacterPlanV2Source]] = set()
    for value in _request_strings(request, "hard_constraints"):
        _append_constraint(
            constraints,
            seen,
            key="hard_constraint",
            value=value,
            kind=CharacterPlanV2ConstraintKind.HARD,
            source=CharacterPlanV2Source.USER_SUPPLIED,
        )
    for value in _request_strings(request, "forbidden_elements"):
        _append_constraint(
            constraints,
            seen,
            key="forbidden_element",
            value=value,
            kind=CharacterPlanV2ConstraintKind.HARD,
            source=CharacterPlanV2Source.USER_SUPPLIED,
        )
    for value in _request_strings(request, "soft_preferences"):
        _append_constraint(
            constraints,
            seen,
            key="soft_preference",
            value=value,
            kind=CharacterPlanV2ConstraintKind.SOFT,
            source=CharacterPlanV2Source.USER_SUPPLIED,
        )
    for value in (*plan.generation_constraints, *plan.parsed_intent.forbidden_patterns):
        _append_constraint(
            constraints,
            seen,
            key="generation_constraint",
            value=value,
            kind=CharacterPlanV2ConstraintKind.HARD,
            source=CharacterPlanV2Source.INTENT,
        )
    gender_requirement = plan.parsed_intent.gender_requirement
    if gender_requirement is not None:
        # Keep a reliable user attribute explicit in the same hard-constraint
        # channel used by Planner, while retaining its typed value in Intent.
        _append_constraint(
            constraints,
            seen,
            key="explicit_gender_requirement",
            value=gender_requirement.to_hard_requirement(),
            kind=CharacterPlanV2ConstraintKind.HARD,
            source=CharacterPlanV2Source.INTENT,
        )
    for value in plan.recommended_traits:
        _append_constraint(
            constraints,
            seen,
            key="recommended_trait",
            value=value,
            kind=CharacterPlanV2ConstraintKind.INFERRED,
            source=CharacterPlanV2Source.INTENT,
        )

    profile = plan.combat_role_profile
    request_profile = request.get("combat_role_profile") if request is not None else None
    if profile is not None and profile.is_unspecified and request_profile is not None:
        if isinstance(request_profile, CombatRoleProfile):
            profile = request_profile
        elif isinstance(request_profile, Mapping):
            profile = CombatRoleProfile.from_mapping(request_profile)
        else:
            raise TypeError("request.combat_role_profile must be a mapping or CombatRoleProfile")
    if profile is not None and profile.is_unspecified:
        profile = None

    provenance: list[CharacterPlanV2ReferenceProvenance] = []
    for item in plan.reference_provenance:
        if not isinstance(item, Mapping):
            raise TypeError("plan.reference_provenance must contain mappings")
        source = item.get("source")
        origin = (
            CharacterPlanV2Source.DETERMINISTIC
            if source == "first_principles"
            else CharacterPlanV2Source.REFERENCE_CORPUS
        )
        provenance.append(
            CharacterPlanV2ReferenceProvenance(
                pattern=item.get("pattern", ""),
                origin=origin,
                source_reference_id=item.get("source_reference_id"),
                source_display_name=item.get("source_display_name"),
                selection_role=item.get("selection_role"),
            )
        )

    requested_relationships = tuple(
        CharacterPlanV2RelationshipBinding(
            target=target,
            source=CharacterPlanV2Source.USER_SUPPLIED,
        )
        for target in _request_strings(request, "desired_connections")
    )
    request_id = request.get("request_id", "request_001") if request is not None else "request_001"
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request.request_id must be a non-empty string")

    decisions: list[CharacterPlanV2Decision] = []
    if constraints:
        decisions.append(
            CharacterPlanV2Decision(
                "constraints",
                CharacterPlanV2Owner.DETERMINISTIC,
                CharacterPlanV2Source.DETERMINISTIC,
                note="Projected from validated request and V1 plan bindings.",
            )
        )
    if requested_relationships:
        decisions.append(
            CharacterPlanV2Decision(
                "relationship_strategy.requested_relationships",
                CharacterPlanV2Owner.USER,
                CharacterPlanV2Source.USER_SUPPLIED,
                note="Requested targets only; no proposed or Canon-grounded relation was inferred.",
            )
        )
    if profile is not None:
        decisions.append(
            CharacterPlanV2Decision(
                "gameplay_identity.combat_role_profile",
                CharacterPlanV2Owner.USER
                if request_profile is not None
                else CharacterPlanV2Owner.INTENT,
                CharacterPlanV2Source.USER_SUPPLIED
                if request_profile is not None
                else CharacterPlanV2Source.INTENT,
                note="Reused existing canonical CombatRoleProfile; no second role ontology introduced.",
            )
        )
    if plan.reference_provenance:
        decisions.append(
            CharacterPlanV2Decision(
                "reference_basis",
                CharacterPlanV2Owner.DETERMINISTIC,
                CharacterPlanV2Source.REFERENCE_CORPUS,
                note="Projected from existing V1 S4 metadata; no new selection was performed.",
            )
        )

    gameplay = CharacterPlanV2GameplayIdentity(
        combat_role_profile=profile,
        gameplay_fantasy=plan.gameplay_identity or None,
        mechanic_identity_direction=plan.interaction_direction or None,
        field_time=plan.field_time or None,
        resource_model=plan.resource_model,
        state_model=plan.state_model,
        core_loop=plan.core_loop,
        payoff=plan.payoff,
        team_handoff=plan.team_handoff or None,
    )
    reference_basis = CharacterPlanV2ReferenceBasis(
        selected_pattern_ids=plan.selected_patterns,
        contrast_pattern_ids=plan.contrast_patterns,
        provenance=tuple(provenance),
        low_coverage_axes=plan.low_coverage_axes,
        novelty_basis=plan.novelty_basis or None,
        coverage_notes=plan.coverage_notes,
    )
    return CharacterDesignPlanV2(
        intent=plan.parsed_intent,
        request_id=request_id.strip(),
        status=CharacterDesignPlanV2Status.SHADOW_PROJECTED,
        constraints=tuple(constraints),
        relationship_strategy=CharacterPlanV2RelationshipStrategy(
            requested_relationships=requested_relationships
        ),
        gameplay_identity=gameplay,
        reference_basis=reference_basis,
        decisions=tuple(decisions),
        unresolved_questions=_SHADOW_UNRESOLVED_DOMAINS,
    )


__all__ = [
    "CHARACTER_DESIGN_PLAN_V2_SCHEMA",
    "CharacterDesignPlanV2Status",
    "CharacterPlanV2Source",
    "CharacterPlanV2Owner",
    "CharacterPlanV2ConstraintKind",
    "CharacterPlanV2Constraint",
    "CharacterPlanV2RelationshipBinding",
    "CharacterPlanV2ReferenceProvenance",
    "CharacterPlanV2Decision",
    "CharacterPlanV2ProductRosterPositioning",
    "CharacterPlanV2NarrativeRole",
    "CharacterPlanV2CharacterCore",
    "CharacterPlanV2RelationshipStrategy",
    "CharacterPlanV2GameplayIdentity",
    "CharacterPlanV2VisualIdentity",
    "CharacterPlanV2ArcSeed",
    "CharacterPlanV2RiskAnalysis",
    "CharacterPlanV2ReferenceBasis",
    "CharacterDesignPlanV2",
    "project_character_plan_v2",
]
