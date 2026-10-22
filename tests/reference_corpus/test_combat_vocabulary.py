from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from along_street_resources import data_resource
from reference_corpus.combat_vocabulary import (
    COMBAT_VOCABULARY_DOMAINS,
    COMBAT_VOCABULARY_SCHEMA_VERSION,
    CombatVocabulary,
)
from reference_corpus.loader import load_combat_vocabulary


VOCABULARY_PATH = data_resource("reference_corpus", "combat_vocabulary.yaml")


def test_combat_vocabulary_loads_with_all_controlled_domains() -> None:
    vocabulary = load_combat_vocabulary(VOCABULARY_PATH)

    assert vocabulary.schema_version == COMBAT_VOCABULARY_SCHEMA_VERSION
    assert vocabulary.domain_ids == COMBAT_VOCABULARY_DOMAINS
    assert vocabulary.canonical_id("combat_role", "on_field_dps") == "main_dps"
    assert vocabulary.canonical_id("team_position", "速切") == "quick_swap"
    assert vocabulary.tokens("mechanic")
    assert all(entry.description for domain in vocabulary.domain_ids for entry in vocabulary.tokens(domain))


def test_unknown_tokens_and_domains_are_rejected() -> None:
    vocabulary = load_combat_vocabulary(VOCABULARY_PATH)

    with pytest.raises(ValueError, match="unknown combat_role combat vocabulary token"):
        vocabulary.canonical_id("combat_role", "not_a_real_role")
    with pytest.raises(ValueError, match="unknown combat vocabulary domain"):
        vocabulary.tokens("unknown")  # type: ignore[arg-type]


def test_invalid_vocabulary_shape_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly"):
        CombatVocabulary.model_validate(
            {
                "schema_version": COMBAT_VOCABULARY_SCHEMA_VERSION,
                "domains": {domain: [] for domain in COMBAT_VOCABULARY_DOMAINS[:-1]},
            }
        )


def test_vocabulary_order_is_deterministic_independent_of_input_order() -> None:
    source = load_combat_vocabulary(VOCABULARY_PATH)
    raw = source.model_dump()
    raw["domains"] = {
        domain: list(reversed(raw["domains"][domain]))
        for domain in reversed(COMBAT_VOCABULARY_DOMAINS)
    }

    reordered = CombatVocabulary.model_validate(raw)

    assert reordered.domain_ids == source.domain_ids
    for domain in source.domain_ids:
        assert [entry.id for entry in reordered.tokens(domain)] == [
            entry.id for entry in source.tokens(domain)
        ]
        assert [entry.id for entry in reordered.tokens(domain)] == sorted(
            entry.id for entry in reordered.tokens(domain)
        )
