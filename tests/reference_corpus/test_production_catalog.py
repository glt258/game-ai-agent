from __future__ import annotations

from pathlib import Path

import pytest

from along_street_resources import data_resource
from reference_corpus.errors import ReferenceValidationError
from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.validator import validate_character_reference


CATALOG_PATH = data_resource("reference_corpus", "characters", "_catalog", "games.yaml")
CATALOG = load_game_catalog(CATALOG_PATH)

PRODUCTION_GAMES = {
    "genshin-impact": "Genshin Impact",
    "wuthering-waves": "Wuthering Waves",
    "zenless-zone-zero": "Zenless Zone Zero",
    "neverness-to-everness": "Neverness to Everness",
    "honkai-impact-3rd": "Honkai Impact 3rd",
}


def test_production_catalog_registers_commercial_games() -> None:
    assert {
        game_id: CATALOG.games[game_id].display_name
        for game_id in PRODUCTION_GAMES
    } == PRODUCTION_GAMES


def test_production_catalog_rejects_unknown_commercial_typo() -> None:
    with pytest.raises(KeyError, match="unknown game_id"):
        CATALOG.require("genshin-impactt")


def test_catalog_rejects_duplicate_game_ids_after_trimming(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-games.yaml"
    path.write_text(
        """schema_version: \"game-catalog/0.1\"
games:
  genshin-impact:
    display_name: \"Genshin Impact\"
  \" genshin-impact \":
    display_name: \"Duplicate\"
""",
        encoding="utf-8",
    )

    with pytest.raises(ReferenceValidationError, match="duplicate game_id"):
        load_game_catalog(path)


@pytest.mark.parametrize(
    ("game_id", "character_id"),
    [
        ("genshin-impact", "keqing"),
        ("wuthering-waves", "jinhsi"),
        ("zenless-zone-zero", "jane-doe"),
    ],
)
def test_committed_golden_records_pass_catalog_backed_validation(
    game_id: str, character_id: str
) -> None:
    character_dir = data_resource(
        "reference_corpus",
        "characters",
        game_id.replace("-", "_"),
        character_id.replace("-", "_"),
    )
    reference = CharacterReferenceLoader(CATALOG).load(character_dir)
    report = validate_character_reference(reference, CATALOG)

    assert reference.reference_id == f"{game_id}:{character_id}"
    assert reference.facts.identity.game_id == game_id
    assert report.valid is True
    assert report.errors == []
    assert reference.quality.analysis_status.value == "completed"
