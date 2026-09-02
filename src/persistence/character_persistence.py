"""Application seam for explicit Character persistence intents."""

from __future__ import annotations

from agents.character_generation import CharacterDraft

from .characters import CharacterRepository, CharacterRevision, PersistedCharacter


class CharacterPersistenceService:
    """Keep generated and edited saves explicit without depending on Web."""

    def __init__(self, repository: CharacterRepository) -> None:
        self._repository = repository

    def save_generated_character(self, draft: CharacterDraft) -> PersistedCharacter:
        return self._repository.create(draft)

    def save_edited_character(
        self,
        character_id: str,
        draft: CharacterDraft,
        *,
        expected_current_revision_id: str,
    ) -> PersistedCharacter:
        self._repository.append_revision(
            character_id,
            draft,
            expected_current_revision_id=expected_current_revision_id,
            revision_kind="EDITED",
        )
        return self._repository.get_character(character_id)

    def load_current_character(self, character_id: str) -> PersistedCharacter:
        return self._repository.get_character(character_id)

    def load_revision(self, character_id: str, revision_id: str) -> CharacterRevision:
        return self._repository.get_revision(character_id, revision_id)


__all__ = ["CharacterPersistenceService"]
