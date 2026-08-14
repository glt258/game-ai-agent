from __future__ import annotations

from knowledge import KnowledgeResolver
from story import KnowledgeContextProvider, StoryRepository, StoryState

from .models import NpcCharacterView, NpcRuntimeView


class NpcViewFactory:
    def __init__(
        self,
        resolver: KnowledgeResolver,
        story_repository: StoryRepository,
        context_provider: KnowledgeContextProvider,
    ) -> None:
        self._resolver = resolver
        self._stories = story_repository
        self._contexts = context_provider

    def character_view(self, character_id: str) -> NpcCharacterView:
        character = self._resolver.characters[character_id]
        name = character.get("name", {})
        profile = character.get("agent_profile", {})
        personality = character.get("personality", {})
        basic = character.get("basic_profile", {})
        address = character.get("address_rules", {})
        return NpcCharacterView(
            character_id=character_id,
            display_name=name.get("display_name", character_id),
            occupation=basic.get("occupation", ""),
            surface_traits=tuple(personality.get("surface_traits", [])),
            values=tuple(personality.get("values", [])),
            knowledge_style=profile.get("knowledge_style", ""),
            speech_style=profile.get("speech_style", ""),
            communication_habits=tuple(profile.get("communication_habits", [])),
            default_information_behavior=profile.get("default_information_behavior", ""),
            public_address=address.get("public", name.get("display_name", character_id)),
        )

    def runtime_view(self, character_id: str, state: StoryState) -> NpcRuntimeView:
        context = self._contexts.for_character(character_id, state)
        story = self._stories.canon[state.story_id]
        role = next(
            (
                fact.get("participation")
                for fact in story.get("character_facts", [])
                if fact.get("character_id") == character_id
            ),
            None,
        )
        return NpcRuntimeView(
            story_id=state.story_id,
            story_title=story.get("title", state.story_id),
            participation_role=role,
            active_case_ids=tuple(sorted(context.active_cases)),
            active_incident_ids=tuple(sorted(context.active_incidents)),
        )
