from knowledge import KnowledgeContext
from knowledge.errors import UnknownCharacterError

from .loader import StoryRepository, load_story_repository
from .models import StoryState
from .validation import validate_story_state


class KnowledgeContextProvider:
    """Adapt explicit Story assignments to factual resolver context only."""

    def __init__(self, repository: StoryRepository | None = None) -> None:
        self.repository = repository or load_story_repository()

    def for_character(self, character_id: str, state: StoryState) -> KnowledgeContext:
        if character_id not in self.repository.character_ids:
            raise UnknownCharacterError(character_id)
        definition = self.repository.definitions.get(state.story_id)
        if definition is None:
            from .errors import UnknownStoryError

            raise UnknownStoryError(f"Unknown story: {state.story_id}")
        validate_story_state(
            state,
            definition=definition,
            case_ids=set(self.repository.case_ids),
            incident_ids=set(self.repository.incident_ids),
            character_ids=set(self.repository.character_ids),
        )
        return KnowledgeContext(
            active_cases=state.character_case_assignments.get(character_id, frozenset()),
            active_incidents=state.character_incident_assignments.get(character_id, frozenset()),
        )
