from __future__ import annotations

from dataclasses import replace

from .errors import IllegalStoryTransitionError, UnknownStoryError, UnknownTransitionError
from .loader import StoryRepository, load_story_repository
from .models import StoryState
from .validation import validate_story_state


class StoryRuntime:
    def __init__(self, repository: StoryRepository | None = None) -> None:
        self.repository = repository or load_story_repository()

    def initial_state(self, story_id: str) -> StoryState:
        definition = self.repository.definitions.get(story_id)
        if definition is None:
            raise UnknownStoryError(f"Unknown story: {story_id}")
        return StoryState(story_id=story_id, current_node_id=definition.initial_node_id)

    def restore(self, payload: dict) -> StoryState:
        state = StoryState.from_dict(payload)
        self.validate(state)
        return state

    def validate(self, state: StoryState) -> None:
        definition = self.repository.definitions.get(state.story_id)
        if definition is None:
            raise UnknownStoryError(f"Unknown story: {state.story_id}")
        validate_story_state(
            state,
            definition=definition,
            case_ids=set(self.repository.case_ids),
            incident_ids=set(self.repository.incident_ids),
            character_ids=set(self.repository.character_ids),
        )

    def transition(self, state: StoryState, transition_id: str) -> StoryState:
        self.validate(state)
        definition = self.repository.definitions[state.story_id]
        transition = definition.transitions.get(transition_id)
        if transition is None:
            raise UnknownTransitionError(f"Unknown transition: {transition_id}")
        if state.current_node_id != transition.from_node_id:
            raise IllegalStoryTransitionError(
                f"{transition_id} starts at {transition.from_node_id}, not {state.current_node_id}"
            )
        cases, incidents = set(state.active_case_ids), set(state.active_incident_ids)
        case_assignments = {key: set(value) for key, value in state.character_case_assignments.items()}
        incident_assignments = {
            key: set(value) for key, value in state.character_incident_assignments.items()
        }
        completed, flags = set(state.completed_node_ids), dict(state.story_flags)
        for effect in transition.effects:
            effect_type = effect["type"]
            if effect_type == "activate_case":
                cases.add(effect["case_id"])
            elif effect_type == "activate_incident":
                incidents.add(effect["incident_id"])
            elif effect_type == "assign_character_to_case":
                if effect["case_id"] not in cases:
                    raise IllegalStoryTransitionError("cannot assign an inactive case")
                case_assignments.setdefault(effect["character_id"], set()).add(effect["case_id"])
            elif effect_type == "assign_character_to_incident":
                if effect["incident_id"] not in incidents:
                    raise IllegalStoryTransitionError("cannot assign an inactive incident")
                incident_assignments.setdefault(effect["character_id"], set()).add(
                    effect["incident_id"]
                )
            elif effect_type == "unassign_character_from_case":
                case_assignments.setdefault(effect["character_id"], set()).discard(effect["case_id"])
            elif effect_type == "unassign_character_from_incident":
                incident_assignments.setdefault(effect["character_id"], set()).discard(
                    effect["incident_id"]
                )
            elif effect_type == "set_story_flag":
                flags[effect["flag"]] = effect["value"]
            elif effect_type == "complete_node":
                completed.add(effect["node_id"])
        next_state = replace(
            state,
            current_node_id=transition.to_node_id,
            completed_node_ids=completed,
            active_case_ids=cases,
            active_incident_ids=incidents,
            character_case_assignments=case_assignments,
            character_incident_assignments=incident_assignments,
            story_flags=flags,
        )
        self.validate(next_state)
        return next_state
