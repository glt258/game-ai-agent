from knowledge import KnowledgeResolver
from knowledge.errors import UnknownCharacterError, UnknownLoreError


def test_canonical_public_lore_is_accessible_without_faction():
    assert KnowledgeResolver().resolve("char_launch_002", "lore_018").reason_code == "public_lore"


def test_canonical_faction_does_not_grant_secret_access():
    result = KnowledgeResolver().resolve("char_launch_006", "lore_secret_002")
    assert result.decision == "deny"
    assert result.reason_code == "default_deny"


def test_canonical_public_safety_member_needs_context_for_restricted_lore():
    result = KnowledgeResolver().resolve("char_launch_007", "lore_027")
    assert result.decision == "deny"
    assert result.reason_code == "default_deny"


def test_canonical_minor_boundary_is_policy_denial_not_age_rule():
    result = KnowledgeResolver().resolve("char_launch_002", "lore_secret_001")
    assert result.decision == "deny"
    assert result.reason_code == "default_deny"
    assert "minor" not in result.reason.lower()


def test_invalid_query_is_not_disguised_as_deny():
    resolver = KnowledgeResolver()
    try:
        resolver.resolve("missing", "lore_001")
    except UnknownCharacterError:
        pass
    else:
        raise AssertionError("expected UnknownCharacterError")
    try:
        resolver.resolve("char_launch_001", "missing")
    except UnknownLoreError:
        pass
    else:
        raise AssertionError("expected UnknownLoreError")
