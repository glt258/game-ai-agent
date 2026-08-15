from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from reference_corpus.errors import (
    ReferenceLoadError,
    ReferenceNotFoundError,
    ReferenceValidationError,
    UnsupportedSchemaVersionError,
)
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog


ROOT = Path(__file__).parent / "fixtures"
CATALOG = load_game_catalog(Path("data/reference_corpus/characters/_catalog/games.yaml"))


def test_valid_three_file_load() -> None:
    reference = CharacterReferenceLoader(CATALOG).load(ROOT / "valid" / "complete_valid")
    assert reference.reference_id == "test-game-alpha:test-character-complete"
    assert reference.analysis is not None
    assert reference.quality.completeness.analysis == 1.0


def test_analysis_is_optional() -> None:
    reference = CharacterReferenceLoader(CATALOG).load(
        ROOT / "valid" / "missing_optional_analysis"
    )
    assert reference.analysis is None
    assert reference.quality.analysis_status.value == "missing"


@pytest.mark.parametrize("filename", ["facts.yaml", "sources.yaml"])
def test_missing_required_file_is_distinguished(tmp_path: Path, filename: str) -> None:
    source = ROOT / "valid" / "minimal_valid"
    target = tmp_path / "character"
    shutil.copytree(source, target)
    (target / filename).unlink()
    with pytest.raises(ReferenceNotFoundError):
        CharacterReferenceLoader(CATALOG).load(target)


def test_invalid_yaml_is_distinguished(tmp_path: Path) -> None:
    source = ROOT / "valid" / "minimal_valid"
    target = tmp_path / "character"
    shutil.copytree(source, target)
    (target / "facts.yaml").write_text("identity: [broken", encoding="utf-8")
    with pytest.raises(ReferenceLoadError, match="invalid YAML"):
        CharacterReferenceLoader(CATALOG).load(target)


def test_unsupported_schema_version_and_cross_file_mismatch(tmp_path: Path) -> None:
    source = ROOT / "valid" / "minimal_valid"
    target = tmp_path / "character"
    shutil.copytree(source, target)
    facts = (target / "facts.yaml").read_text(encoding="utf-8")
    (target / "facts.yaml").write_text(
        facts.replace('"character-facts/0.2"', '"character-facts/9.0"'), encoding="utf-8"
    )
    with pytest.raises(UnsupportedSchemaVersionError):
        CharacterReferenceLoader(CATALOG).load(target)

    shutil.copytree(source, target / "mismatch")
    mismatch_sources = target / "mismatch" / "sources.yaml"
    text = mismatch_sources.read_text(encoding="utf-8")
    mismatch_sources.write_text(
        text.replace("test-game-alpha:test-character-a", "test-game-alpha:other"),
        encoding="utf-8",
    )
    with pytest.raises(ReferenceValidationError, match="reference_id mismatch"):
        CharacterReferenceLoader(CATALOG).load(target / "mismatch")


def test_unknown_game_is_rejected_by_loader(tmp_path: Path) -> None:
    source = ROOT / "valid" / "minimal_valid"
    target = tmp_path / "character"
    shutil.copytree(source, target)
    facts = (target / "facts.yaml").read_text(encoding="utf-8")
    (target / "facts.yaml").write_text(
        facts.replace("game_id: test-game-alpha", "game_id: unknown-game"),
        encoding="utf-8",
    )
    with pytest.raises(ReferenceValidationError, match="unknown game_id"):
        CharacterReferenceLoader(CATALOG).load(target)


def test_v02_graph_fixture_and_golden_records_load() -> None:
    graph = CharacterReferenceLoader(CATALOG).load(ROOT / "valid" / "mechanic_graph")
    assert graph.facts.schema_version == "character-facts/0.2"
    assert len(graph.facts.combat.relations) == 4

    data_root = Path("data/reference_corpus/characters")
    keqing = CharacterReferenceLoader().load(data_root / "genshin_impact" / "keqing")
    jinhsi = CharacterReferenceLoader().load(data_root / "wuthering_waves" / "jinhsi")
    assert keqing.analysis is not None
    assert keqing.quality.analysis_status.value == "completed"
    assert jinhsi.analysis is None
    assert jinhsi.quality.analysis_status.value == "missing"
    assert any(
        relation.relation_type == "generates"
        for relation in jinhsi.facts.combat.relations
    )
