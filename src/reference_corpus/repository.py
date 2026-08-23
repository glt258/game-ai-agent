from __future__ import annotations

from typing import Literal

from .enums import NormalizedRole
from .errors import (
    CorpusBoundaryError,
    CorpusManifestNotFoundError,
    DuplicateReferenceError,
    ReferenceCorpusError,
    ReferenceNotFoundError,
)
from .loader import (
    CharacterReferenceLoader,
    Resource,
    join_resource,
    load_game_catalog,
    load_corpus_manifest,
    normalize_resource,
)
from .models import CharacterReference, CorpusManifest, GameCatalog
from .validator import validate_manifest_boundary


ManifestPolicy = Literal["required", "unmanaged"]


class CharacterReferenceRepository:
    """Deterministic file-backed repository for external reference records."""

    def __init__(
        self,
        root: Resource | str,
        *,
        catalog: GameCatalog | None = None,
        manifest: CorpusManifest | None = None,
        manifest_policy: ManifestPolicy = "required",
        loader: CharacterReferenceLoader | None = None,
    ):
        if manifest_policy not in {"required", "unmanaged"}:
            raise ValueError("manifest_policy must be 'required' or 'unmanaged'")
        if manifest_policy == "unmanaged" and manifest is not None:
            raise ValueError("manifest must not be supplied when manifest_policy='unmanaged'")
        self.root = normalize_resource(root)
        self.manifest_policy = manifest_policy
        self.manifest = manifest
        self.catalog = catalog or self._discover_catalog()
        self.loader = loader or CharacterReferenceLoader(self.catalog)
        if self.manifest_policy == "required" and self.manifest is None:
            manifest_path = join_resource(
                self._characters_root(), "_catalog", "corpus_manifest.yaml"
            )
            if not manifest_path.is_file():
                raise CorpusManifestNotFoundError(
                    f"required corpus manifest not found: {manifest_path}"
                )
            self.manifest = load_corpus_manifest(manifest_path)
        if self.manifest_policy == "required" and self.catalog is None:
            raise CorpusBoundaryError("required game catalog not found")

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

    def _actual_character_entries(self) -> dict[str, Resource]:
        root = self._characters_root()
        if not root.is_dir():
            return {}

        entries: dict[str, Resource] = {}

        def visit(current: Resource, parts: tuple[str, ...]) -> None:
            children = sorted(
                (child for child in current.iterdir() if child.is_dir()),
                key=lambda child: child.name,
            )
            if not children:
                if parts:
                    entries["/".join(parts)] = current
                return
            for child in children:
                visit(child, (*parts, child.name))

        for child in sorted(
            (item for item in root.iterdir() if item.is_dir() and item.name != "_catalog"),
            key=lambda item: item.name,
        ):
            visit(child, (child.name,))
        return entries

    def _boundary_references(self) -> list[CharacterReference]:
        assert self.manifest is not None
        entries = self._actual_character_entries()
        errors = validate_manifest_boundary(self.manifest, entries, self.catalog)
        loaded: list[CharacterReference] = []
        records_by_path = {record.path: record for record in self.manifest.records}
        for record in self.manifest.records:
            character_dir = entries.get(record.path)
            if character_dir is None:
                continue
            try:
                reference = self.loader.load(character_dir)
            except ReferenceCorpusError as exc:
                errors.append(f"record load failed at {record.path}: {exc}")
                continue
            loaded.append(reference)
            if reference.reference_id != record.reference_id:
                errors.append(
                    f"reference_id mismatch at {record.path}: "
                    f"manifest={record.reference_id}, loaded={reference.reference_id}"
                )
            expected_game = record.reference_id.split(":", 1)[0]
            actual_game = reference.facts.identity.game_id
            if actual_game != expected_game:
                errors.append(
                    f"game mismatch at {record.path}: "
                    f"manifest={expected_game}, loaded={actual_game}"
                )
            schema_versions = self.manifest.record_schema_versions
            actual_schemas = {
                "facts": reference.facts.schema_version,
                "analysis": (
                    reference.analysis.schema_version
                    if reference.analysis is not None
                    else None
                ),
                "sources": reference.provenance.schema_version,
            }
            expected_schemas = schema_versions.model_dump()
            for name in sorted(expected_schemas):
                if actual_schemas[name] != expected_schemas[name]:
                    errors.append(
                        f"schema mismatch at {record.path}: {name}="
                        f"{actual_schemas[name]!r}, expected={expected_schemas[name]!r}"
                    )

        loaded_games = {reference.facts.identity.game_id for reference in loaded}
        manifest_games = set(self.manifest.games)
        errors.extend(
            f"game missing from loaded records: {game_id}"
            for game_id in sorted(manifest_games - loaded_games)
        )
        errors.extend(
            f"extra game in loaded records: {game_id}"
            for game_id in sorted(loaded_games - manifest_games)
        )
        if errors:
            raise CorpusBoundaryError(errors)

        loaded_by_path = {
            record.path: reference
            for record, reference in zip(self.manifest.records, loaded, strict=False)
            if record.path in records_by_path
        }
        return [loaded_by_path[record.path] for record in self.manifest.records]

    def list_all(self) -> list[CharacterReference]:
        if self.manifest_policy == "required":
            return self._boundary_references()
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
