import pytest

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import KnowledgeAccessDenied, KnowledgeConfigurationError


def datasets(*, with_scope_bindings=True):
    data = {
        "characters_data": {"characters": [
            {"id": "c1", "identity": {"faction_id": "f1", "division_ids": ["d1"], "roles": ["registered_test_role"], "responsibilities": ["r1"], "assignments": [], "explicit_grants": ["grant-lore"]}},
            {"id": "c2", "identity": {"faction_id": "f1", "division_ids": [], "roles": [], "responsibilities": [], "assignments": [], "explicit_grants": []}},
        ]},
        "lore_data": {"lore": [{"id": "public", "sensitivity": "public"}, {"id": "restricted", "sensitivity": "restricted"}, {"id": "secret", "sensitivity": "secret"}]},
        "factions_data": {"factions": [{"id": "f1", "internal_structure": {"divisions": [{"id": "d1"}]}}]},
        "knowledge_rules_data": {
            "principles": {"default_policy": "deny", "public_lore_access": "allow"},
            "vocabulary": {
                "subject_types": ["everyone", "faction", "division", "role", "responsibility", "assignment", "explicit_grant"],
                "condition_types": {
                    "needs_resp": {"evaluator": "has_relevant_responsibility"},
                    "needs_assignment": {"evaluator": "assignment_match"},
                    "needs_case": {"evaluator": "case_assignment_match"},
                    "needs_grant": {"evaluator": "explicit_authorization"},
                },
                "role_types": {"registered_test_role": {"faction_id": "f1"}},
                "responsibility_types": {"r1": {"faction_id": "f1"}},
                "assignment_types": {"a1": {"faction_id": "f1"}},
                "acquisition_channels": ["public_information", "case_assignment"],
            },
            "rules": [
                {"id": "public-rule", "lore_id": "public", "grants": [{"subject": {"type": "everyone"}, "conditions": []}], "acquisition": {"channels": ["public_information"]}},
                {"id": "role-rule", "lore_id": "restricted", "grants": [{"subject": {"type": "role", "faction_id": "f1", "role": "registered_test_role"}, "conditions": []}], "acquisition": {"channels": ["case_assignment"]}},
                {"id": "resp-rule", "lore_id": "restricted", "grants": [{"subject": {"type": "responsibility", "faction_id": "f1", "responsibility": "r1"}, "conditions": ["needs_resp"]}], "acquisition": {"channels": ["case_assignment"]}},
                {"id": "assignment-rule", "lore_id": "secret", "grants": [{"subject": {"type": "everyone"}, "conditions": ["needs_assignment"]}], "acquisition": {"channels": ["case_assignment"]}},
                {"id": "dynamic-rule", "lore_id": "secret", "grants": [{"subject": {"type": "everyone"}, "conditions": ["needs_case"]}], "acquisition": {"channels": ["case_assignment"]}},
            ],
        },
        "condition_scopes_data": {"bindings": [
            {"id": "resp-binding", "rule_id": "resp-rule", "lore_id": "restricted", "condition": "needs_resp", "evaluator": "has_relevant_responsibility", "status": "resolved", "scope": {"type": "responsibility", "match": "any", "values": ["r1"]}},
            {"id": "assignment-binding", "rule_id": "assignment-rule", "lore_id": "secret", "condition": "needs_assignment", "evaluator": "assignment_match", "status": "resolved", "scope": {"type": "assignment", "match": "any", "values": ["a1"]}},
            {"id": "case-binding", "rule_id": "dynamic-rule", "lore_id": "secret", "condition": "needs_case", "evaluator": "case_assignment_match", "status": "unresolved", "scope": {"type": "case", "match": "any", "values": []}, "unresolved_reason": "synthetic fixture has no case registry"},
        ]} if with_scope_bindings else {"bindings": []},
    }
    return data


@pytest.fixture
def resolver():
    return KnowledgeResolver(**datasets())


def test_public_lore_is_accessible_without_faction(resolver):
    result = resolver.resolve("c2", "public")
    assert result.decision == "allow"
    assert result.reason_code == "public_lore"


def test_role_subject_requires_exact_registered_role(resolver):
    assert resolver.resolve("c1", "restricted").decision == "allow"
    assert resolver.resolve("c2", "restricted").decision == "deny"


def test_assignment_scope_requires_exact_match(resolver):
    assert resolver.resolve("c1", "secret", KnowledgeContext(active_assignments={"a1"})).decision == "allow"
    result = resolver.resolve("c1", "secret", KnowledgeContext(active_assignments={"other"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"


def test_missing_runtime_context_fails_closed(resolver):
    result = resolver.resolve("c2", "secret")
    assert result.decision == "deny"
    assert result.reason_code == "condition_context_missing"
    assert result.evaluated_conditions[0]["actual_scope"]["values"] == []


def test_runtime_boolean_bypass_is_not_supported():
    with pytest.raises(TypeError):
        KnowledgeContext(runtime_facts={"case_assignment_match": True})


def test_context_cannot_bypass_scope_registry(resolver):
    result = resolver.resolve("c1", "secret", KnowledgeContext(active_assignments={"case-2"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"
    assert result.evaluated_conditions[0]["matched_values"] == []


def test_unresolved_scope_fails_closed():
    data = datasets()
    data["knowledge_rules_data"]["rules"] = [rule for rule in data["knowledge_rules_data"]["rules"] if rule["id"] != "assignment-rule"]
    data["condition_scopes_data"]["bindings"] = [binding for binding in data["condition_scopes_data"]["bindings"] if binding["id"] != "assignment-binding"]
    result = KnowledgeResolver(**data).resolve("c2", "secret", KnowledgeContext(active_cases={"case-1"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_scope_unresolved"


def test_missing_scope_binding_fails_closed():
    resolver = KnowledgeResolver(**datasets(with_scope_bindings=False))
    result = resolver.resolve("c2", "secret")
    assert result.decision == "deny"
    assert result.reason_code == "condition_scope_missing"


def test_explicit_authorization_requires_exact_scope():
    data = datasets()
    data["knowledge_rules_data"]["rules"].append({"id": "grant-rule", "lore_id": "secret", "grants": [{"subject": {"type": "everyone"}, "conditions": ["needs_grant"]}], "acquisition": {"channels": ["case_assignment"]}})
    data["condition_scopes_data"]["registries"] = {"authorization": ["grant-lore"]}
    data["condition_scopes_data"]["bindings"].append({"id": "grant-binding", "rule_id": "grant-rule", "lore_id": "secret", "condition": "needs_grant", "evaluator": "explicit_authorization", "status": "resolved", "scope": {"type": "authorization", "match": "any", "values": ["grant-lore"]}})
    resolver = KnowledgeResolver(**data)
    assert resolver.resolve("c1", "secret").decision == "allow"
    assert resolver.resolve("c2", "secret", KnowledgeContext(authorizations={"grant-other"})).decision == "deny"


def test_scope_evaluator_mismatch_is_configuration_error():
    data = datasets()
    data["condition_scopes_data"]["bindings"][0]["scope"]["type"] = "assignment"
    with pytest.raises(KnowledgeConfigurationError):
        KnowledgeResolver(**data)


def test_duplicate_binding_fails_fast():
    data = datasets()
    data["condition_scopes_data"]["bindings"].append(dict(data["condition_scopes_data"]["bindings"][0]))
    with pytest.raises(KnowledgeConfigurationError):
        KnowledgeResolver(**data)


def test_context_rejects_generic_access_override():
    with pytest.raises(TypeError):
        KnowledgeContext(allow=True)


def test_unknown_evaluator_fails_fast():
    data = datasets()
    data["knowledge_rules_data"]["vocabulary"]["condition_types"]["bad"] = {"evaluator": "not_registered"}
    data["knowledge_rules_data"]["rules"][0]["grants"][0]["conditions"] = ["bad"]
    with pytest.raises(KnowledgeConfigurationError):
        KnowledgeResolver(**data)


def test_unknown_subject_type_fails_fast():
    data = datasets()
    data["knowledge_rules_data"]["rules"][0]["grants"][0]["subject"] = {"type": "not_registered"}
    with pytest.raises(KnowledgeConfigurationError):
        KnowledgeResolver(**data)


def test_require_access_raises_only_for_valid_denial(resolver):
    with pytest.raises(KnowledgeAccessDenied):
        resolver.require_access("c2", "secret")


def test_resolved_responsibility_scope_rejects_unregistered_value():
    data = datasets()
    data["condition_scopes_data"]["bindings"][0]["scope"]["values"] = ["fake_responsibility"]
    with pytest.raises(KnowledgeConfigurationError, match="invalid value"):
        KnowledgeResolver(**data)


def test_resolved_assignment_scope_rejects_unregistered_value():
    data = datasets()
    data["condition_scopes_data"]["bindings"][1]["scope"]["values"] = ["fake_assignment"]
    with pytest.raises(KnowledgeConfigurationError, match="invalid value"):
        KnowledgeResolver(**data)


def test_resolved_scope_requires_nonempty_values():
    data = datasets()
    data["condition_scopes_data"]["bindings"][0]["scope"]["values"] = []
    with pytest.raises(KnowledgeConfigurationError, match="resolved binding requires scope values"):
        KnowledgeResolver(**data)


def test_unresolved_scope_requires_empty_values_and_reason():
    data = datasets()
    binding = data["condition_scopes_data"]["bindings"][0]
    binding["status"] = "unresolved"
    binding["scope"]["values"] = ["r1"]
    with pytest.raises(KnowledgeConfigurationError, match="empty scope values"):
        KnowledgeResolver(**data)
    binding["scope"]["values"] = []
    with pytest.raises(KnowledgeConfigurationError, match="requires unresolved_reason"):
        KnowledgeResolver(**data)


def test_external_resolved_scope_requires_canonical_registry():
    data = datasets()
    binding = data["condition_scopes_data"]["bindings"][1]
    binding["scope"]["type"] = "project"
    binding["scope"]["values"] = ["a1"]
    with pytest.raises(KnowledgeConfigurationError, match="canonical registry"):
        KnowledgeResolver(**data)


def test_unknown_rule_reference_fails_fast():
    data = datasets()
    data["condition_scopes_data"]["bindings"][0]["rule_id"] = "missing-rule"
    with pytest.raises(KnowledgeConfigurationError, match="unknown rule_id"):
        KnowledgeResolver(**data)


def test_lore_reference_mismatch_fails_fast():
    data = datasets()
    data["condition_scopes_data"]["bindings"][0]["lore_id"] = "secret"
    with pytest.raises(KnowledgeConfigurationError, match="lore_id does not match"):
        KnowledgeResolver(**data)


def test_active_registry_does_not_contain_known_fake_responsibilities():
    from pathlib import Path
    import yaml

    registry = yaml.safe_load(Path("data/knowledge/condition_scopes.yaml").read_text(encoding="utf-8"))
    fake_values = {
        "insurance_claims_context",
        "model_review_context",
        "artist_project_context",
        "community_member_coordination",
        "research_project_leadership",
        "research_methodology_duty",
        "writeback_longitudinal_research",
    }
    resolved_values = {
        value
        for binding in registry["bindings"]
        if binding["status"] == "resolved"
        for value in binding.get("scope", {}).get("values", [])
    }
    assert not fake_values & resolved_values
