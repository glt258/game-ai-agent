from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .errors import StoryStateValidationError


STORY_STATE_FIELDS = frozenset(
    {
        "story_id",
        "current_node_id",
        "completed_node_ids",
        "active_case_ids",
        "active_incident_ids",
        "character_case_assignments",
        "character_incident_assignments",
        "story_flags",
    }
)
FORBIDDEN_PERMISSION_KEYS = frozenset(
    {
        "allow_lore",
        "grant_knowledge",
        "can_access",
        "knowledge_allow",
        "permission",
        "access_decision",
        "authorization",
        "responsibility",
        "role",
        "project",
    }
)


@dataclass(frozen=True)
class StoryTransition:
    id: str
    from_node_id: str
    to_node_id: str
    effects: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class StoryDefinition:
    story_id: str
    initial_node_id: str
    node_ids: frozenset[str]
    terminal_node_ids: frozenset[str]
    transitions: Mapping[str, StoryTransition]

    def __post_init__(self) -> None:
        object.__setattr__(self, "transitions", MappingProxyType(dict(self.transitions)))


_ID_COLLECTION_TYPES = (list, tuple, set, frozenset)


def _normalize_id_collection(value: Any, field_name: str) -> frozenset[str]:
    if not isinstance(value, _ID_COLLECTION_TYPES):
        raise StoryStateValidationError(f"{field_name} must be an ID collection")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise StoryStateValidationError(f"{field_name} contains an invalid ID")
        normalized.append(item)
    return frozenset(normalized)


def _assignment_map(value: Any, field_name: str) -> Mapping[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        raise StoryStateValidationError(f"{field_name} must be a mapping")
    result: dict[str, frozenset[str]] = {}
    for character_id, refs in value.items():
        if not isinstance(character_id, str) or not character_id:
            raise StoryStateValidationError(f"{field_name} requires non-empty character IDs")
        if not isinstance(refs, _ID_COLLECTION_TYPES):
            raise StoryStateValidationError(f"{field_name} values must be ID collections")
        normalized = _normalize_id_collection(refs, field_name)
        if normalized:
            result[character_id] = normalized
    return MappingProxyType(result)


@dataclass(frozen=True)
class StoryState:
    story_id: str
    current_node_id: str
    completed_node_ids: frozenset[str] = field(default_factory=frozenset)
    active_case_ids: frozenset[str] = field(default_factory=frozenset)
    active_incident_ids: frozenset[str] = field(default_factory=frozenset)
    character_case_assignments: Mapping[str, frozenset[str]] = field(default_factory=dict)
    character_incident_assignments: Mapping[str, frozenset[str]] = field(default_factory=dict)
    story_flags: Mapping[str, bool | str | int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("story_id", "current_node_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise StoryStateValidationError(f"{name} must be a non-empty string")
        for name in ("completed_node_ids", "active_case_ids", "active_incident_ids"):
            object.__setattr__(
                self,
                name,
                _normalize_id_collection(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "character_case_assignments",
            _assignment_map(self.character_case_assignments, "character_case_assignments"),
        )
        object.__setattr__(
            self,
            "character_incident_assignments",
            _assignment_map(self.character_incident_assignments, "character_incident_assignments"),
        )
        if not isinstance(self.story_flags, Mapping):
            raise StoryStateValidationError("story_flags must be a mapping")
        flags: dict[str, bool | str | int] = {}
        for key, value in self.story_flags.items():
            if not isinstance(key, str) or not key or key in FORBIDDEN_PERMISSION_KEYS:
                raise StoryStateValidationError(f"forbidden or invalid story flag: {key!r}")
            if not isinstance(value, (bool, str, int)):
                raise StoryStateValidationError(f"story flag {key} must be a scalar")
            flags[key] = value
        object.__setattr__(self, "story_flags", MappingProxyType(flags))

    def to_dict(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "current_node_id": self.current_node_id,
            "completed_node_ids": sorted(self.completed_node_ids),
            "active_case_ids": sorted(self.active_case_ids),
            "active_incident_ids": sorted(self.active_incident_ids),
            "character_case_assignments": {
                key: sorted(self.character_case_assignments[key])
                for key in sorted(self.character_case_assignments)
            },
            "character_incident_assignments": {
                key: sorted(self.character_incident_assignments[key])
                for key in sorted(self.character_incident_assignments)
            },
            "story_flags": {key: self.story_flags[key] for key in sorted(self.story_flags)},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoryState":
        if not isinstance(payload, Mapping):
            raise StoryStateValidationError("StoryState payload must be a mapping")
        payload_keys = tuple(payload)
        if any(not isinstance(key, str) for key in payload_keys):
            raise StoryStateValidationError("StoryState field names must be strings")
        payload_fields = set(payload_keys)
        unknown = payload_fields - STORY_STATE_FIELDS
        missing = STORY_STATE_FIELDS - payload_fields
        if unknown:
            raise StoryStateValidationError(f"unknown StoryState field(s): {sorted(unknown)}")
        if missing:
            raise StoryStateValidationError(f"missing StoryState field(s): {sorted(missing)}")
        return cls(**{key: payload[key] for key in STORY_STATE_FIELDS})
