from __future__ import annotations

from pathlib import Path

from reference_corpus.loader import CharacterReferenceLoader, load_game_catalog
from reference_corpus.validator import validate_character_reference


def test_shinku_golden_record_semantics() -> None:
    catalog = load_game_catalog(
        Path("data/reference_corpus/characters/_catalog/games.yaml")
    )
    shinku = CharacterReferenceLoader(catalog).load(
        Path("data/reference_corpus/characters/neverness_to_everness/shinku")
    )
    states = {
        state.state_id: state.subject_scope
        for state in shinku.facts.combat.mechanics.states
    }
    assert states == {"menacing_gaze": "self", "surging_crimson": "self"}

    relation = next(
        relation
        for relation in shinku.facts.combat.relations
        if relation.relation_id == "surging-crimson-modifies-special-combat-arts"
    )
    assert (relation.relation_type, relation.target.id) == (
        "modifies",
        "special_combat_arts",
    )

    report = validate_character_reference(shinku, catalog)
    assert report.valid is True
    assert report.errors == []
    assert shinku.analysis is not None
    assert shinku.quality.analysis_status.value == "completed"
