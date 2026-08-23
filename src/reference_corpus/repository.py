from __future__ import annotations

from .enums import NormalizedRole
from .errors import DuplicateReferenceError, ReferenceNotFoundError
from .loader import (
    CharacterReferenceLoader,
    Resource,
    join_resource,
    load_game_catalog,
    normalize_resource,
)
from .models import CharacterReference, GameCatalog


class CharacterReferenceRepository:
    """Deterministic file-backed repository for external reference records."""

    def __init__(
        self,
        root: Resource | str,
        *,
        catalog: GameCatalog | None = None,
        loader: CharacterReferenceLoader | None = None,
    ):
        self.root = normalize_resource(root)
        self.catalog = catalog or self._discover_catalog()
        self.loader = loader or CharacterReferenceLoader(self.catalog)

    def _characters_root(self) -> Resource:
        candidate = join_resource(self.root, "characters")
        return candidate if candidate.is_dir() else self.root

    def _discover_catalog(self) -> GameCatalog | None:
        candidates = [
            join_resource(self.root, "_catalog", "games.yaml"),
            join_resource(self.root, "characters", "_catalog", "games.yaml"),
        ]
        for path in candidates:
            if path.is_file():
                return load_game_catalog(path)
        return None

    def _character_dirs(self) -> list[Resource]:
        root = self._characters_root()
        if not root.is_dir():
            return []
        return sorted(
            (
                path
                for game_dir in root.iterdir()
                if game_dir.is_dir() and game_dir.name != "_catalog"
                for path in game_dir.iterdir()
                if path.is_dir()
            ),
            key=lambda path: str(path).replace("\\", "/"),
        )

    def list_all(self) -> list[CharacterReference]:
        references = [self.loader.load(path) for path in self._character_dirs()]
        references.sort(key=lambda reference: reference.reference_id)
        seen: set[str] = set()
        for reference in references:
            if reference.reference_id in seen:
                raise DuplicateReferenceError(
                    f"duplicate reference_id in repository: {reference.reference_id}"
                )
            seen.add(reference.reference_id)
        return references

    def get(self, reference_id: str) -> CharacterReference:
        for reference in self.list_all():
            if reference.reference_id == reference_id:
                return reference
        raise ReferenceNotFoundError(f"reference not found: {reference_id}")

    def list_by_game(self, game_id: str) -> list[CharacterReference]:
        return [item for item in self.list_all() if item.facts.identity.game_id == game_id]

    def list_by_role(self, role: NormalizedRole) -> list[CharacterReference]:
        role = NormalizedRole(role)
        return [
            item
            for item in self.list_all()
            if item.analysis is not None and role in item.analysis.combat_design.normalized_roles
        ]

    def exists(self, reference_id: str) -> bool:
        try:
            self.get(reference_id)
        except ReferenceNotFoundError:
            return False
        return True

    def count(self) -> int:
        return len(self.list_all())
