from __future__ import annotations

from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from along_street_resources import data_resource

from .errors import (
    CorpusManifestError,
    CorpusManifestNotFoundError,
    ReferenceLoadError,
    ReferenceNotFoundError,
    ReferenceValidationError,
    UnsupportedSchemaVersionError,
)
from .combat_vocabulary import CombatVocabulary
from .models import (
    CharacterAnalysis,
    CharacterFacts,
    CharacterProvenance,
    CharacterReference,
    GameCatalog,
    CorpusManifest,
    FixturePlan,
)
from .normalizer import build_quality
from .provenance import validate_combat_analysis, validate_provenance


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that does not silently overwrite duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


Resource = Path | Traversable


def normalize_resource(value: Resource | str) -> Resource:
    if isinstance(value, (Path, Traversable)):
        return value
    return Path(value)


def join_resource(root: Resource, *parts: str) -> Resource:
    return root.joinpath(*parts)


def _read_yaml(path: Resource | str) -> dict[str, Any]:
    path = normalize_resource(path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.load(stream, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ReferenceLoadError(f"invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ReferenceLoadError(f"could not read {path}: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ReferenceLoadError(f"YAML root must be a mapping: {path}")
    return value


def _model(path: Resource | str, model_type):
    path = normalize_resource(path)
    try:
        return model_type.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ReferenceValidationError(f"schema validation failed for {path}: {exc}") from exc


def _require_schema_version(actual: str, expected: str, path: Path) -> None:
    if actual != expected:
        raise UnsupportedSchemaVersionError(
            f"unsupported schema version in {path}: {actual!r}; expected {expected!r}"
        )


class CharacterReferenceLoader:
    def __init__(
        self,
        catalog: GameCatalog | None = None,
        combat_vocabulary: CombatVocabulary | None = None,
    ):
        self.catalog = catalog
        self.combat_vocabulary = combat_vocabulary

    @staticmethod
    def _discover_combat_vocabulary(character_dir: Resource) -> CombatVocabulary | None:
        character_dir = normalize_resource(character_dir)
        candidates: list[Resource] = []
        if isinstance(character_dir, Path) and len(character_dir.parents) >= 3:
            candidates.append(character_dir.parents[2] / "combat_vocabulary.yaml")
        candidates.append(data_resource("reference_corpus", "combat_vocabulary.yaml"))
        for candidate in candidates:
            if candidate.is_file():
                return load_combat_vocabulary(candidate)
        return None

    def load(self, character_dir: Resource | str) -> CharacterReference:
        character_dir = normalize_resource(character_dir)
        facts_path = join_resource(character_dir, "facts.yaml")
        sources_path = join_resource(character_dir, "sources.yaml")
        analysis_path = join_resource(character_dir, "analysis.yaml")
        if not facts_path.is_file():
            raise ReferenceNotFoundError(f"missing required file: {facts_path}")
        if not sources_path.is_file():
            raise ReferenceNotFoundError(f"missing required file: {sources_path}")

        facts = _model(facts_path, CharacterFacts)
        _require_schema_version(facts.schema_version, "character-facts/0.3", facts_path)
        if self.catalog is not None and facts.identity.game_id not in self.catalog.games:
            raise ReferenceValidationError(
                f"unknown game_id in {facts_path}: {facts.identity.game_id}"
            )

        provenance = _model(sources_path, CharacterProvenance)
        _require_schema_version(provenance.schema_version, "character-sources/0.2", sources_path)
        analysis = None
        if analysis_path.is_file():
            analysis = _model(analysis_path, CharacterAnalysis)
            _require_schema_version(analysis.schema_version, "character-analysis/0.1", analysis_path)

        ids = {facts.reference_id, provenance.reference_id}
        if analysis is not None:
            ids.add(analysis.reference_id)
        if len(ids) != 1:
            raise ReferenceValidationError(
                f"reference_id mismatch across files in {character_dir}: {sorted(ids)}"
            )
        reference_id = facts.reference_id
        try:
            validate_provenance(provenance, facts, analysis)
            validate_combat_analysis(
                analysis,
                facts,
                self.combat_vocabulary or self._discover_combat_vocabulary(character_dir),
            )
        except ReferenceValidationError:
            raise
        except Exception as exc:
            raise ReferenceValidationError(
                f"provenance validation failed for {character_dir}: {exc}"
            ) from exc

        quality = build_quality(
            facts,
            analysis,
            provenance.verification.status,
            list(provenance.verification.conflicts),
        )
        try:
            return CharacterReference(
                reference_id=reference_id,
                facts=facts,
                analysis=analysis,
                provenance=provenance,
                quality=quality,
            )
        except ValidationError as exc:
            raise ReferenceValidationError(
                f"combined reference validation failed for {character_dir}: {exc}"
            ) from exc


def load_game_catalog(path: Resource | str) -> GameCatalog:
    path = normalize_resource(path)
    catalog = _model(path, GameCatalog)
    _require_schema_version(catalog.schema_version, "game-catalog/0.1", path)
    return catalog


def load_corpus_manifest(path: Resource | str) -> CorpusManifest:
    path = normalize_resource(path)
    if not path.is_file():
        raise CorpusManifestNotFoundError(f"corpus manifest not found: {path}")
    raw = _read_yaml(path)
    actual_schema = raw.get("schema_version")
    if actual_schema != "character-reference-corpus-manifest/0.2":
        raise UnsupportedSchemaVersionError(
            f"unsupported schema version in {path}: {actual_schema!r}; "
            "expected 'character-reference-corpus-manifest/0.2'"
        )
    try:
        return CorpusManifest.model_validate(raw)
    except ValidationError as exc:
        raise CorpusManifestError(
            f"corpus manifest validation failed for {path}: {exc}"
        ) from exc


def load_fixture_plan(path: Resource | str) -> FixturePlan:
    path = normalize_resource(path)
    plan = _model(path, FixturePlan)
    _require_schema_version(
        plan.corpus_version, "character-reference-corpus/0.1", path
    )
    return plan


def load_combat_vocabulary(path: Resource | str) -> CombatVocabulary:
    """Load and validate the standalone v0.6.2-A combat vocabulary."""

    path = normalize_resource(path)
    vocabulary = _model(path, CombatVocabulary)
    _require_schema_version(
        vocabulary.schema_version,
        "combat-vocabulary/0.6.2-A",
        path,
    )
    return vocabulary
