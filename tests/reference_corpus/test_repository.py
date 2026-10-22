from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from along_street_resources import data_resource
from reference_corpus.enums import NormalizedRole
from reference_corpus.errors import (
    CorpusBoundaryError,
    CorpusManifestNotFoundError,
    DuplicateReferenceError,
    ReferenceNotFoundError,
)
from reference_corpus.loader import load_corpus_manifest, load_game_catalog
from reference_corpus.repository import CharacterReferenceRepository


FIXTURES = Path(__file__).parent / "fixtures" / "valid"
CATALOG = load_game_catalog(
    Path(__file__).parent / "fixtures" / "test_games.yaml"
)
PRODUCTION_ROOT = Path(__file__).parents[2] / "src" / "along_street_resources" / "data" / "reference_corpus" / "characters"
PRODUCTION_CATALOG = load_game_catalog(PRODUCTION_ROOT / "_catalog" / "games.yaml")


def _repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    characters = root / "characters" / "test-game-alpha"
    shutil.copytree(FIXTURES / "complete_valid", characters / "complete")
    shutil.copytree(FIXTURES / "missing_optional_analysis", characters / "minimal")
    return root


def test_repository_get_filters_and_deterministic_listing(tmp_path: Path) -> None:
    repository = CharacterReferenceRepository(
        _repository_root(tmp_path), catalog=CATALOG, manifest_policy="unmanaged"
    )
    all_references = repository.list_all()
    assert [item.reference_id for item in all_references] == sorted(
        item.reference_id for item in all_references
    )
    assert repository.get("test-game-alpha:test-character-complete").analysis is not None
    assert repository.list_by_game("test-game-alpha") == all_references
    assert repository.list_by_role(NormalizedRole.ON_FIELD_DPS)[0].reference_id.endswith(
        "test-character-complete"
    )
    assert repository.count() == 2
    assert repository.exists("test-game-alpha:test-character-b")
    with pytest.raises(ReferenceNotFoundError):
        repository.get("missing:character")


def test_repository_requires_manifest_by_default(tmp_path: Path) -> None:
    with pytest.raises(CorpusManifestNotFoundError):
        CharacterReferenceRepository(_repository_root(tmp_path), catalog=CATALOG).list_all()


def test_required_repository_requires_game_catalog(tmp_path: Path) -> None:
    root = _production_copy(tmp_path)
    (root / "characters" / "_catalog" / "games.yaml").unlink()

    with pytest.raises(CorpusBoundaryError, match="required game catalog not found"):
        CharacterReferenceRepository(root)


def test_repository_rejects_duplicate_reference_ids(tmp_path: Path) -> None:
    root = tmp_path / "corpus" / "characters" / "test-game-alpha"
    shutil.copytree(FIXTURES / "minimal_valid", root / "one")
    shutil.copytree(FIXTURES / "minimal_valid", root / "two")
    with pytest.raises(DuplicateReferenceError):
        CharacterReferenceRepository(
            tmp_path / "corpus", catalog=CATALOG, manifest_policy="unmanaged"
        ).list_all()


def _production_copy(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    shutil.copytree(PRODUCTION_ROOT, root / "characters")
    return root


def test_repository_accepts_explicit_unmanaged_synthetic_corpus(tmp_path: Path) -> None:
    repository = CharacterReferenceRepository(
        _repository_root(tmp_path), catalog=CATALOG, manifest_policy="unmanaged"
    )
    assert repository.manifest is None
    assert repository.count() == 2


def test_unmanaged_repository_rejects_a_manifest_argument(tmp_path: Path) -> None:
    manifest = load_corpus_manifest(
        PRODUCTION_ROOT / "_catalog" / "corpus_manifest.yaml"
    )
    with pytest.raises(ValueError, match="manifest_policy='unmanaged'"):
        CharacterReferenceRepository(
            _repository_root(tmp_path),
            catalog=CATALOG,
            manifest=manifest,
            manifest_policy="unmanaged",
        )


@pytest.mark.parametrize("mutation", ["extra", "missing", "id", "game", "schema"])
def test_required_repository_fails_closed_on_manifest_boundary_mismatch(
    tmp_path: Path, mutation: str
) -> None:
    root = _production_copy(tmp_path)
    if mutation == "extra":
        shutil.copytree(
            root / "characters" / "genshin_impact" / "furina",
            root / "characters" / "genshin_impact" / "extra_character",
        )
    elif mutation == "missing":
        shutil.rmtree(root / "characters" / "genshin_impact" / "furina")
    elif mutation == "id":
        manifest_path = root / "characters" / "_catalog" / "corpus_manifest.yaml"
        text = manifest_path.read_text(encoding="utf-8")
        manifest_path.write_text(
            text.replace("genshin-impact:furina", "genshin-impact:furina-alt", 1),
            encoding="utf-8",
        )
    elif mutation == "game":
        facts_path = root / "characters" / "genshin_impact" / "furina" / "facts.yaml"
        text = facts_path.read_text(encoding="utf-8")
        facts_path.write_text(
            text.replace("game_id: genshin-impact", "game_id: wuthering-waves", 1),
            encoding="utf-8",
        )
    else:
        facts_path = root / "characters" / "genshin_impact" / "furina" / "facts.yaml"
        text = facts_path.read_text(encoding="utf-8")
        facts_path.write_text(
            text.replace('"character-facts/0.3"', '"character-facts/0.2"', 1),
            encoding="utf-8",
        )

    with pytest.raises(CorpusBoundaryError) as caught:
        CharacterReferenceRepository(root, catalog=PRODUCTION_CATALOG).list_all()
    assert list(caught.value.errors) == sorted(caught.value.errors)
