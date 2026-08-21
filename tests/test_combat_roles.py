from __future__ import annotations

import pytest

from combat_semantics import CombatRoleProfile
from reference_corpus.loader import load_combat_vocabulary


VOCABULARY = load_combat_vocabulary("data/reference_corpus/combat_vocabulary.yaml")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("main_dps", "main_dps"),
        ("dps", "main_dps"),
        ("main damage dealer", "main_dps"),
        ("primary_dps", "main_dps"),
        ("sub_dps", "sub_dps"),
        ("secondary_dps", "sub_dps"),
        ("support", "support"),
        ("healer", "healer"),
        ("tank", "defense"),
        ("defender", "defense"),
        ("frontline_defender", "defense"),
    ],
)
def test_role_vocabulary_normalizes_canonical_and_legacy_aliases(value, expected):
    assert VOCABULARY.normalize_combat_role(value).canonical_role == expected


def test_off_field_dps_crosswalk_is_marked_lossy():
    result = VOCABULARY.normalize_combat_role("off_field_dps")

    assert result.canonical_role == "sub_dps"
    assert result.lossy is True
    assert result.note and "off-field" in result.note


@pytest.mark.parametrize("value", ["burst", "sustain", "hybrid", "buffer", "enabler"])
def test_behavior_and_composition_terms_are_not_role_tokens(value):
    with pytest.raises(ValueError, match="unknown combat_role"):
        VOCABULARY.normalize_combat_role(value)


def test_role_and_mechanic_control_are_domain_qualified():
    assert VOCABULARY.canonical_id("combat_role", "control") == "control"
    assert VOCABULARY.canonical_id("mechanic", "control") == "control"


def test_profile_preserves_secondary_order_and_rejects_duplicates():
    profile = CombatRoleProfile(
        primary_role="main_dps",
        secondary_roles=("support", "healer"),
    )
    assert profile.secondary_roles == ("support", "healer")

    with pytest.raises(ValueError, match="duplicates"):
        CombatRoleProfile(primary_role="main_dps", secondary_roles=("support", "support"))


def test_unspecified_profile_has_no_none_or_hybrid_sentinel():
    profile = CombatRoleProfile()

    assert profile.primary_role is None
    assert profile.secondary_roles == ()
