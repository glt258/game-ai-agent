from __future__ import annotations

from pathlib import Path

from along_street_resources import data_resource
from reference_corpus.loader import CharacterReferenceLoader


def test_jane_doe_golden_record_semantics() -> None:
    jane = CharacterReferenceLoader().load(
        data_resource(
            "reference_corpus", "characters", "zenless_zone_zero", "jane_doe"
        )
    )
    states = {state.state_id: state.subject_scope for state in jane.facts.combat.mechanics.states}
    assert states == {"passion": "self", "gnawed": "target"}

    insight_relation = next(
        relation
        for relation in jane.facts.combat.relations
        if relation.relation_id == "insight-applies-gnawed"
    )
    assert (insight_relation.relation_type, insight_relation.target.id) == ("applies", "gnawed")
    assert jane.analysis is not None
    assert jane.quality.analysis_status.value == "completed"
