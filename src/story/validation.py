from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType
from typing import Any, Mapping

from .errors import StoryConfigurationError, StoryStateValidationError
from .models import FORBIDDEN_PERMISSION_KEYS, StoryDefinition, StoryState, StoryTransition


EFFECT_FIELDS = {
    "activate_incident": {"type", "incident_id"},
    "activate_case": {"type", "case_id"},
    "assign_character_to_incident": {"type", "character_id", "incident_id"},
    "assign_character_to_case": {"type", "character_id", "case_id"},
    "unassign_character_from_incident": {"type", "character_id", "incident_id"},
    "unassign_character_from_case": {"type", "character_id", "case_id"},
    "set_story_flag": {"type", "flag", "value"},
    "complete_node": {"type", "node_id"},
}


def _document(data: Any, key: str) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(data, Mapping):
        raise StoryConfigurationError(f"{key} document must be a mapping")
    version, records = data.get("version"), data.get(key)
    if not isinstance(version, str) or not version:
        raise StoryConfigurationError(f"{key} document requires a version")
    if not isinstance(records, list):
        raise StoryConfigurationError(f"{key} document requires a list")
    return version, records


def validate_story_canon(
    data: Any,
    *,
    city_ids: set[str],
    faction_ids: set[str],
    character_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _, records = _document(data, "stories")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise StoryConfigurationError("every Story Canon record must be a mapping")
        story_id = record.get("id")
        if not isinstance(story_id, str) or not story_id:
            raise StoryConfigurationError("every Story Canon record needs an id")
        if story_id in result:
            raise StoryConfigurationError(f"duplicate story id: {story_id}")
        if not isinstance(record.get("title"), str) or not record["title"].strip():
            raise StoryConfigurationError(f"{story_id}: title must be non-empty")
        if not isinstance(record.get("premise"), str) or not record["premise"].strip():
            raise StoryConfigurationError(f"{story_id}: premise must be non-empty")
        setting = record.get("setting", {})
        if not isinstance(setting, Mapping):
            raise StoryConfigurationError(f"{story_id}: setting must be a mapping")
        if setting.get("city_id") not in city_ids:
            raise StoryConfigurationError(f"{story_id}: unknown city {setting.get('city_id')}")
        if "district_id" in setting:
            raise StoryConfigurationError(f"{story_id}: district_id is not registered; use district_name")
        if not isinstance(setting.get("district_name"), str) or not setting["district_name"].strip():
            raise StoryConfigurationError(f"{story_id}: district_name must be non-empty")
        factions = record.get("involved_faction_ids", [])
        characters = record.get("featured_character_ids", [])
        if not isinstance(factions, list) or len(factions) != len(set(factions)):
            raise StoryConfigurationError(f"{story_id}: involved_faction_ids must be unique")
        if not isinstance(characters, list) or len(characters) != len(set(characters)):
            raise StoryConfigurationError(f"{story_id}: featured_character_ids must be unique")
        for faction_id in factions:
            if faction_id not in faction_ids:
                raise StoryConfigurationError(f"{story_id}: unknown faction {faction_id}")
        for character_id in characters:
            if character_id not in character_ids:
                raise StoryConfigurationError(f"{story_id}: unknown character {character_id}")
        objective_facts = record.get("objective_facts")
        if not isinstance(objective_facts, list) or not objective_facts or any(
            not isinstance(fact, str) or not fact.strip() for fact in objective_facts
        ):
            raise StoryConfigurationError(f"{story_id}: objective_facts must be non-empty text")
        character_facts = record.get("character_facts")
        if not isinstance(character_facts, list):
            raise StoryConfigurationError(f"{story_id}: character_facts must be a list")
        for fact in character_facts:
            if not isinstance(fact, Mapping):
                raise StoryConfigurationError(f"{story_id}: character fact must be a mapping")
            if fact.get("character_id") not in character_ids:
                raise StoryConfigurationError(f"{story_id}: unknown character fact reference")
        player = record.get("player_participation", {})
        if not isinstance(player, Mapping):
            raise StoryConfigurationError(f"{story_id}: player_participation must be a mapping")
        if player.get("character_id") is not None:
            raise StoryConfigurationError(f"{story_id}: player must not receive a Character ID in v0.1")
        if player.get("player_identity_integration") != "deferred":
            raise StoryConfigurationError(f"{story_id}: Player Identity integration must remain deferred")
        result[story_id] = dict(record)
    return result


def validate_story_definitions(
    data: Any,
    *,
    story_ids: set[str],
    case_ids: set[str],
    incident_ids: set[str],
    character_ids: set[str],
) -> dict[str, StoryDefinition]:
    _, records = _document(data, "story_definitions")
    result: dict[str, StoryDefinition] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise StoryConfigurationError("every StoryDefinition must be a mapping")
        story_id = record.get("story_id")
        if story_id not in story_ids:
            raise StoryConfigurationError(f"unknown Story Canon reference: {story_id}")
        if story_id in result:
            raise StoryConfigurationError(f"duplicate StoryDefinition: {story_id}")
        node_records = record.get("nodes")
        if not isinstance(node_records, list) or not node_records:
            raise StoryConfigurationError(f"{story_id}: nodes must be a non-empty list")
        node_ids: set[str] = set()
        terminals: set[str] = set()
        for node in node_records:
            node_id = node.get("id") if isinstance(node, Mapping) else None
            if not isinstance(node_id, str) or not node_id or node_id in node_ids:
                raise StoryConfigurationError(f"{story_id}: invalid or duplicate node id {node_id!r}")
            node_ids.add(node_id)
            if not isinstance(node.get("summary"), str) or not node["summary"].strip():
                raise StoryConfigurationError(f"{story_id}: node {node_id} needs a summary")
            if node.get("terminal") is True:
                terminals.add(node_id)
        initial = record.get("initial_node_id")
        if initial not in node_ids:
            raise StoryConfigurationError(f"{story_id}: unknown initial node {initial}")
        transitions: dict[str, StoryTransition] = {}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for item in record.get("transitions", []):
            if not isinstance(item, Mapping):
                raise StoryConfigurationError(f"{story_id}: transition must be a mapping")
            transition_id = item.get("id")
            if not isinstance(transition_id, str) or not transition_id or transition_id in transitions:
                raise StoryConfigurationError(f"{story_id}: invalid or duplicate transition id")
            source, target = item.get("from_node_id"), item.get("to_node_id")
            if source not in node_ids or target not in node_ids:
                raise StoryConfigurationError(f"{transition_id}: unknown node reference")
            effects = item.get("effects")
            if not isinstance(effects, list):
                raise StoryConfigurationError(f"{transition_id}: effects must be a list")
            validated_effects = tuple(
                _validate_effect(effect, transition_id, source, case_ids, incident_ids, character_ids)
                for effect in effects
            )
            transitions[transition_id] = StoryTransition(
                transition_id, source, target, validated_effects
            )
            outgoing[source].append(target)
        if any(len(targets) > 1 for targets in outgoing.values()):
            raise StoryConfigurationError(f"{story_id}: branching is outside StoryDefinition v0.1")
        if len(terminals) != 1:
            raise StoryConfigurationError(f"{story_id}: StoryDefinition v0.1 requires one terminal")
        if any(outgoing.get(node_id) for node_id in terminals):
            raise StoryConfigurationError(f"{story_id}: terminal nodes cannot have transitions")
        missing_outgoing = (node_ids - terminals) - set(outgoing)
        if missing_outgoing:
            raise StoryConfigurationError(
                f"{story_id}: non-terminal nodes need one transition: {sorted(missing_outgoing)}"
            )
        incoming: dict[str, int] = defaultdict(int)
        for targets in outgoing.values():
            for target in targets:
                incoming[target] += 1
        if incoming.get(initial, 0) or any(
            incoming.get(node_id, 0) != 1 for node_id in node_ids - {initial}
        ):
            raise StoryConfigurationError(f"{story_id}: nodes must form one linear path")
        reachable = {initial}
        frontier = [initial]
        while frontier:
            current = frontier.pop()
            for target in outgoing.get(current, []):
                if target not in reachable:
                    reachable.add(target)
                    frontier.append(target)
        if reachable != node_ids:
            raise StoryConfigurationError(f"{story_id}: unreachable nodes {sorted(node_ids - reachable)}")
        if not terminals or not terminals <= reachable:
            raise StoryConfigurationError(f"{story_id}: a reachable terminal node is required")
        result[story_id] = StoryDefinition(
            story_id, initial, frozenset(node_ids), frozenset(terminals), transitions
        )
    return result


def _validate_effect(
    effect: Any,
    transition_id: str,
    source_node_id: str,
    case_ids: set[str],
    incident_ids: set[str],
    character_ids: set[str],
) -> Mapping[str, Any]:
    if not isinstance(effect, Mapping):
        raise StoryConfigurationError(f"{transition_id}: effect must be a mapping")
    effect_type = effect.get("type")
    expected = EFFECT_FIELDS.get(effect_type)
    if expected is None:
        raise StoryConfigurationError(f"{transition_id}: unsupported effect {effect_type!r}")
    if set(effect) != expected:
        raise StoryConfigurationError(f"{transition_id}: invalid fields for {effect_type}")
    if "case_id" in effect and effect["case_id"] not in case_ids:
        raise StoryConfigurationError(f"{transition_id}: unknown case {effect['case_id']}")
    if "incident_id" in effect and effect["incident_id"] not in incident_ids:
        raise StoryConfigurationError(f"{transition_id}: unknown incident {effect['incident_id']}")
    if "character_id" in effect and effect["character_id"] not in character_ids:
        raise StoryConfigurationError(f"{transition_id}: unknown character {effect['character_id']}")
    if effect_type == "complete_node" and effect["node_id"] != source_node_id:
        raise StoryConfigurationError(f"{transition_id}: complete_node must target its from node")
    if effect_type == "set_story_flag":
        flag, value = effect["flag"], effect["value"]
        if not isinstance(flag, str) or not flag or flag in FORBIDDEN_PERMISSION_KEYS:
            raise StoryConfigurationError(f"{transition_id}: forbidden story flag {flag!r}")
        if not isinstance(value, (bool, str, int)):
            raise StoryConfigurationError(f"{transition_id}: story flag value must be scalar")
    return MappingProxyType(dict(effect))


def validate_story_state(
    state: StoryState,
    *,
    definition: StoryDefinition,
    case_ids: set[str],
    incident_ids: set[str],
    character_ids: set[str],
) -> None:
    if state.story_id != definition.story_id:
        raise StoryStateValidationError(f"state story {state.story_id} does not match definition")
    unknown_nodes = (state.completed_node_ids | {state.current_node_id}) - definition.node_ids
    if unknown_nodes:
        raise StoryStateValidationError(f"unknown runtime node ID(s): {sorted(unknown_nodes)}")
    expected_completed: set[str] = set()
    cursor = definition.initial_node_id
    visited: set[str] = set()
    while cursor != state.current_node_id:
        if cursor in visited:
            raise StoryStateValidationError("StoryDefinition path contains a cycle")
        visited.add(cursor)
        outgoing = [item for item in definition.transitions.values() if item.from_node_id == cursor]
        if len(outgoing) != 1:
            raise StoryStateValidationError(f"cannot reach current node {state.current_node_id}")
        expected_completed.add(cursor)
        cursor = outgoing[0].to_node_id
    if state.completed_node_ids != expected_completed:
        raise StoryStateValidationError(
            "completed_node_ids must be the exact linear prefix before current_node_id"
        )
    unknown_cases = state.active_case_ids - case_ids
    unknown_incidents = state.active_incident_ids - incident_ids
    if unknown_cases:
        raise StoryStateValidationError(f"unknown runtime case ID(s): {sorted(unknown_cases)}")
    if unknown_incidents:
        raise StoryStateValidationError(f"unknown runtime incident ID(s): {sorted(unknown_incidents)}")
    for mapping, active, label in (
        (state.character_case_assignments, state.active_case_ids, "case"),
        (state.character_incident_assignments, state.active_incident_ids, "incident"),
    ):
        unknown_characters = set(mapping) - character_ids
        if unknown_characters:
            raise StoryStateValidationError(
                f"unknown runtime character ID(s): {sorted(unknown_characters)}"
            )
        assigned = set().union(*mapping.values()) if mapping else set()
        if assigned - active:
            raise StoryStateValidationError(
                f"{label} assignment targets inactive ID(s): {sorted(assigned - active)}"
            )
