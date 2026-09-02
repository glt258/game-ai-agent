from __future__ import annotations

from collections.abc import Iterable

from along_street_resources import data_resource
from reference_corpus.enums import NormalizedRole
from reference_corpus.models import CharacterReference, GameCatalog
from reference_corpus.repository import CharacterReferenceRepository

from ..mappers.reference_characters import to_reference_detail, to_reference_list
from ..schemas.reference_characters import ReferenceCharacterDetailDTO, ReferenceCharacterListDTO

DEFAULT_REFERENCE_ROOT = data_resource("reference_corpus", "characters")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class ReferenceCharacterReadApplication:
    """Read-only Web seam over the frozen reference corpus repository."""

    def __init__(self, repository: CharacterReferenceRepository | None = None) -> None:
        self.repository = repository or CharacterReferenceRepository(DEFAULT_REFERENCE_ROOT)

    @property
    def catalog(self) -> GameCatalog | None:
        return self.repository.catalog

    @property
    def baseline_id(self) -> str | None:
        return (
            self.repository.manifest.baseline_id if self.repository.manifest is not None else None
        )

    def list(
        self,
        *,
        query: str | None = None,
        ip: str | None = None,
        combat_role: NormalizedRole | None = None,
        limit: int = 50,
    ) -> ReferenceCharacterListDTO:
        references = self.repository.list_all()
        if ip:
            wanted_ip = _normalized(ip)
            references = [item for item in references if self._matches_ip(item, wanted_ip)]
        if combat_role is not None:
            references = [
                item
                for item in references
                if item.analysis is not None
                and combat_role in item.analysis.combat_design.normalized_roles
            ]
        if query:
            wanted_query = _normalized(query)
            references = [item for item in references if self._matches_query(item, wanted_query)]
        return to_reference_list(references[:limit], self.catalog)

    def get(self, reference_id: str) -> ReferenceCharacterDetailDTO:
        return to_reference_detail(
            self.repository.get(reference_id), self.catalog, self.baseline_id
        )

    def _matches_ip(self, reference: CharacterReference, wanted_ip: str) -> bool:
        game_id = reference.facts.identity.game_id
        if _normalized(game_id) == wanted_ip:
            return True
        if self.catalog is None or game_id not in self.catalog.games:
            return False
        definition = self.catalog.games[game_id]
        return wanted_ip in {
            _normalized(definition.display_name),
            *(_normalized(alias) for alias in definition.aliases),
        }

    def _matches_query(self, reference: CharacterReference, wanted_query: str) -> bool:
        identity = reference.facts.identity
        game_name = (
            self.catalog.games[identity.game_id].display_name
            if self.catalog and identity.game_id in self.catalog.games
            else identity.game_id
        )
        values: Iterable[str] = (
            reference.reference_id,
            identity.names.canonical,
            identity.native_character_id or "",
            identity.game_id,
            game_name,
            *identity.names.localized.values(),
            reference.facts.narrative.faction or "",
            reference.facts.narrative.occupation or "",
        )
        return any(wanted_query in _normalized(value) for value in values)


__all__ = ["ReferenceCharacterReadApplication"]
