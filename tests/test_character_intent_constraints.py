from __future__ import annotations

import pytest

from character_intelligence.intent import parse_explicit_age_requirement


def test_explicit_age_parser_keeps_exact_age_exact() -> None:
    requirement = parse_explicit_age_requirement("角色年龄是25岁")

    assert requirement is not None
    assert requirement.preferred_age == 25
    assert requirement.minimum_age == 25
    assert requirement.maximum_age == 25
    assert requirement.approximate is False


def test_explicit_age_parser_bounds_approximate_age() -> None:
    requirement = parse_explicit_age_requirement("设计一名25岁左右的角色")

    assert requirement is not None
    assert requirement.preferred_age == 25
    assert requirement.minimum_age == 23
    assert requirement.maximum_age == 27
    assert requirement.approximate is True


def test_explicit_age_parser_rejects_conflicting_ages() -> None:
    with pytest.raises(ValueError, match="conflicting explicit character ages"):
        parse_explicit_age_requirement("角色25岁，设定年龄为30岁")
