from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from reference_corpus.enums import NormalizedRole
from reference_corpus.errors import DuplicateReferenceError, ReferenceNotFoundError
from reference_corpus.loader import load_game_catalog
from reference_corpus.repository import CharacterReferenceRepository


FIXTURES = Path(__file__).parent / "fixtures" / "valid"
CATALOG = load_game_catalog(Path("data/reference_corpus/characters/_catalog/games.yaml"))


def _repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    characters = root / "characters" / "test-game-alpha"
    shutil.copytree(FIXTURES / "complete_valid", characters / "complete")
    shutil.copytree(FIXTURES / "missing_optional_analysis", characters / "minimal")
    return root


def test_repository_get_filters_and_deterministic_listing(tmp_path: Path) -> None:
    repository = CharacterReferenceRepository(_repository_root(tmp_path), catalog=CATALOG)
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


def test_repository_rejects_duplicate_reference_ids(tmp_path: Path) -> None:
    root = tmp_path / "corpus" / "characters" / "test-game-alpha"
    shutil.copytree(FIXTURES / "minimal_valid", root / "one")
    shutil.copytree(FIXTURES / "minimal_valid", root / "two")
    with pytest.raises(DuplicateReferenceError):
        CharacterReferenceRepository(tmp_path / "corpus", catalog=CATALOG).list_all()
