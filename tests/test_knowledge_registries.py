import pytest

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import KnowledgeConfigurationError, KnowledgeContextValidationError
from knowledge.registries import (
    validate_authorizations,
    validate_case_incident_relationships,
    validate_cases,
    validate_incidents,
    validate_projects,
)

from test_knowledge_resolver import datasets


def _project(project_id="project_a"):
    return {
        "version": "0.1",
        "projects": [{
            "id": project_id,
            "name": "Synthetic project",
            "faction_id": "f1",
            "description": "Synthetic fixture",
            "lore_refs": ["secret"],
            "assignment_refs": ["a1"],
        }],
    }


def _authorization(authorization_id="auth_a", target="project_a"):
    return {
        "version": "0.1",
        "authorizations": [{
            "id": authorization_id,
            "name": "Synthetic authorization",
            "faction_id": "f1",
            "purpose": "Synthetic fixture access",
            "scope_type": "project",
            "target_refs": [target],
        }],
    }


def _case(case_id="case_a"):
    return {
        "version": "0.1",
        "cases": [{
            "id": case_id,
            "name": "Synthetic case",
            "faction_id": "f1",
            "description": "Synthetic fixture",
            "lore_refs": ["secret"],
            "related_incident_ids": [],
            "related_project_ids": [],
            "status": "ongoing",
        }],
    }


def _incident(incident_id="incident_a"):
    return {
        "version": "0.1",
        "incidents": [{
            "id": incident_id,
            "name": "Synthetic incident",
            "faction_ids": ["f1"],
            "description": "Synthetic fixture",
            "lore_refs": ["secret"],
            "related_case_ids": [],
            "status": "historical",
        }],
    }


def _projects():
    document = _project()
    document["projects"].append({
        "id": "project_b",
        "name": "Synthetic alternate project",
        "faction_id": "f1",
        "description": "Synthetic alternate fixture",
        "lore_refs": ["secret"],
        "assignment_refs": ["a1"],
    })
    return document


def _authorizations():
    document = _authorization()
    document["authorizations"].append({
        "id": "auth_b",
        "name": "Synthetic alternate authorization",
        "faction_id": "f1",
        "purpose": "Synthetic fixture alternate access",
        "scope_type": "project",
        "target_refs": ["project_a"],
    })
    return document


def _cases():
    document = _case()
    document["cases"].append({
        "id": "case_b",
        "name": "Synthetic alternate case",
        "faction_id": "f1",
        "lore_refs": ["secret"],
        "related_incident_ids": [],
        "related_project_ids": [],
        "status": "open",
    })
    return document


def _incidents():
    document = _incident()
    document["incidents"].append({
        "id": "incident_b",
        "name": "Synthetic alternate incident",
        "faction_ids": ["f1"],
        "lore_refs": ["secret"],
        "related_case_ids": [],
        "status": "closed",
    })
    return document


def _resolver_with_condition(
    *,
    scope_type,
    scope_value,
    evaluator,
    projects=None,
    cases=None,
    incidents=None,
    authorizations=None,
    subject=None,
    character_faction=None,
):
    data = datasets()
    if character_faction is not None:
        data["characters_data"]["characters"][0]["identity"]["faction_id"] = character_faction
    data["lore_data"]["lore"].append({"id": "registry_secret", "sensitivity": "restricted"})
    data["knowledge_rules_data"]["rules"].append({
        "id": "registry-rule",
        "lore_id": "registry_secret",
        "grants": [{"subject": subject or {"type": "everyone"}, "conditions": ["registry_condition"]}],
        "acquisition": {"channels": ["case_assignment"]},
    })
    data["knowledge_rules_data"]["vocabulary"]["condition_types"]["registry_condition"] = {
        "evaluator": evaluator,
    }
    data["condition_scopes_data"]["bindings"].append({
        "id": "registry-binding",
        "rule_id": "registry-rule",
        "lore_id": "registry_secret",
        "condition": "registry_condition",
        "evaluator": evaluator,
        "status": "resolved",
        "scope": {"type": scope_type, "match": "any", "values": [scope_value]},
    })
    return KnowledgeResolver(
        **data,
        projects_data=projects,
        cases_data=cases,
        incidents_data=incidents,
        authorizations_data=authorizations,
    )


def test_project_registry_rejects_unknown_faction():
    project = _project()
    project["projects"][0]["faction_id"] = "unknown"
    with pytest.raises(KnowledgeConfigurationError, match="unknown faction"):
        validate_projects(project, faction_ids={"f1"}, lore_ids={"secret"}, assignment_ids={"a1"})


def test_project_registry_rejects_unknown_lore():
    project = _project()
    project["projects"][0]["lore_refs"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown lore"):
        validate_projects(project, faction_ids={"f1"}, lore_ids={"secret"}, assignment_ids={"a1"})


def test_project_registry_rejects_unknown_assignment():
    project = _project()
    project["projects"][0]["assignment_refs"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown assignment"):
        validate_projects(project, faction_ids={"f1"}, lore_ids={"secret"}, assignment_ids={"a1"})


def test_case_registry_rejects_unknown_faction():
    document = _case()
    document["cases"][0]["faction_id"] = "unknown"
    with pytest.raises(KnowledgeConfigurationError, match="unknown faction"):
        validate_cases(
            document,
            faction_ids={"f1"},
            lore_ids={"secret"},
            incident_ids=set(),
            project_ids=set(),
        )


def test_case_registry_rejects_unknown_lore():
    document = _case()
    document["cases"][0]["lore_refs"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown lore"):
        validate_cases(
            document,
            faction_ids={"f1"},
            lore_ids={"secret"},
            incident_ids=set(),
            project_ids=set(),
        )


def test_case_registry_rejects_unknown_incident():
    document = _case()
    document["cases"][0]["related_incident_ids"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown incident"):
        validate_cases(
            document,
            faction_ids={"f1"},
            lore_ids={"secret"},
            incident_ids=set(),
            project_ids=set(),
        )


def test_case_registry_rejects_duplicate_refs():
    document = _case()
    document["cases"][0]["lore_refs"] = ["secret", "secret"]
    with pytest.raises(KnowledgeConfigurationError, match="duplicate lore_refs"):
        validate_cases(
            document,
            faction_ids={"f1"},
            lore_ids={"secret"},
            incident_ids=set(),
            project_ids=set(),
        )


def test_incident_registry_rejects_unknown_faction():
    document = _incident()
    document["incidents"][0]["faction_ids"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown faction"):
        validate_incidents(document, faction_ids={"f1"}, lore_ids={"secret"}, case_ids=set())


def test_incident_registry_rejects_unknown_lore():
    document = _incident()
    document["incidents"][0]["lore_refs"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown lore"):
        validate_incidents(document, faction_ids={"f1"}, lore_ids={"secret"}, case_ids=set())


def test_incident_registry_rejects_unknown_case():
    document = _incident()
    document["incidents"][0]["related_case_ids"] = ["unknown"]
    with pytest.raises(KnowledgeConfigurationError, match="unknown case"):
        validate_incidents(document, faction_ids={"f1"}, lore_ids={"secret"}, case_ids=set())


def test_incident_registry_rejects_duplicate_refs():
    document = _incident()
    document["incidents"][0]["faction_ids"] = ["f1", "f1"]
    with pytest.raises(KnowledgeConfigurationError, match="duplicate faction_ids"):
        validate_incidents(document, faction_ids={"f1"}, lore_ids={"secret"}, case_ids=set())


def test_case_incident_relationships_must_be_bidirectional():
    cases = {"case_a": {"related_incident_ids": ["incident_a"]}}
    incidents = {"incident_a": {"related_case_ids": []}}
    with pytest.raises(KnowledgeConfigurationError, match="not bidirectional"):
        validate_case_incident_relationships(cases, incidents)


def test_case_and_incident_ids_must_be_distinct():
    with pytest.raises(KnowledgeConfigurationError, match="IDs must be distinct"):
        validate_case_incident_relationships({"shared": {}}, {"shared": {}})


def test_resolved_project_scope_requires_registered_project():
    with pytest.raises(KnowledgeConfigurationError, match="canonical registry"):
        _resolver_with_condition(
            scope_type="project",
            scope_value="project_a",
            evaluator="assignment_match",
        )


def test_resolved_case_scope_requires_registered_case():
    with pytest.raises(KnowledgeConfigurationError, match="unknown case registry"):
        _resolver_with_condition(
            scope_type="case",
            scope_value="case_a",
            evaluator="case_assignment_match",
        )


def test_resolved_incident_scope_requires_registered_incident():
    with pytest.raises(KnowledgeConfigurationError, match="unknown incident registry"):
        _resolver_with_condition(
            scope_type="incident",
            scope_value="incident_a",
            evaluator="incident_assignment_match",
        )


def test_authorization_registry_rejects_unknown_target():
    with pytest.raises(KnowledgeConfigurationError, match="unknown project target"):
        validate_authorizations(
            _authorization(target="unknown"),
            faction_ids={"f1"},
            target_registries={"project": {"project_a"}},
        )


def test_resolved_authorization_scope_requires_registered_authorization():
    with pytest.raises(KnowledgeConfigurationError, match="unknown authorization registry"):
        _resolver_with_condition(
            scope_type="authorization",
            scope_value="auth_a",
            evaluator="explicit_authorization",
            projects=_project(),
        )


def test_project_scope_exact_match_allows():
    resolver = _resolver_with_condition(
        scope_type="project",
        scope_value="project_a",
        evaluator="assignment_match",
        projects=_project(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_projects={"project_a"}))
    assert result.decision == "allow"


def test_wrong_project_scope_denies():
    resolver = _resolver_with_condition(
        scope_type="project",
        scope_value="project_a",
        evaluator="assignment_match",
        projects=_projects(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_projects={"project_b"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"


def test_authorization_exact_match_allows():
    resolver = _resolver_with_condition(
        scope_type="authorization",
        scope_value="auth_a",
        evaluator="explicit_authorization",
        projects=_project(),
        authorizations=_authorization(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(authorizations={"auth_a"}))
    assert result.decision == "allow"


def test_wrong_authorization_denies():
    resolver = _resolver_with_condition(
        scope_type="authorization",
        scope_value="auth_a",
        evaluator="explicit_authorization",
        projects=_projects(),
        authorizations=_authorizations(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(authorizations={"auth_b"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"


def test_case_scope_exact_match_allows():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_case(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_cases={"case_a"}))
    assert result.decision == "allow"


def test_wrong_case_denies():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_cases(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_cases={"case_b"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"


def test_unknown_runtime_case_is_error():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_case(),
    )
    with pytest.raises(KnowledgeContextValidationError, match="case_not_exists"):
        resolver.resolve(
            "c1", "registry_secret", KnowledgeContext(active_cases={"case_not_exists"})
        )


def test_incident_scope_exact_match_allows():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        incidents=_incident(),
    )
    result = resolver.resolve(
        "c1", "registry_secret", KnowledgeContext(active_incidents={"incident_a"})
    )
    assert result.decision == "allow"


def test_wrong_incident_denies():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        incidents=_incidents(),
    )
    result = resolver.resolve(
        "c1", "registry_secret", KnowledgeContext(active_incidents={"incident_b"})
    )
    assert result.decision == "deny"
    assert result.reason_code == "condition_not_satisfied"


def test_unknown_runtime_incident_is_error():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        incidents=_incident(),
    )
    with pytest.raises(KnowledgeContextValidationError, match="incident_not_exists"):
        resolver.resolve(
            "c1",
            "registry_secret",
            KnowledgeContext(active_incidents={"incident_not_exists"}),
        )


def test_case_does_not_bypass_subject():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_case(),
        subject={"type": "faction", "faction_id": "f1"},
        character_faction="other",
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_cases={"case_a"}))
    assert result.decision == "deny"


def test_incident_does_not_bypass_subject():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        incidents=_incident(),
        subject={"type": "faction", "faction_id": "f1"},
        character_faction="other",
    )
    result = resolver.resolve(
        "c1", "registry_secret", KnowledgeContext(active_incidents={"incident_a"})
    )
    assert result.decision == "deny"


def test_case_does_not_unlock_unrelated_lore():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_case(),
    )
    assert resolver.resolve("c2", "restricted", KnowledgeContext(active_cases={"case_a"})).decision == "deny"


def test_incident_does_not_unlock_unrelated_lore():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        incidents=_incident(),
    )
    assert resolver.resolve(
        "c2", "restricted", KnowledgeContext(active_incidents={"incident_a"})
    ).decision == "deny"


def test_case_does_not_satisfy_incident_scope():
    resolver = _resolver_with_condition(
        scope_type="incident",
        scope_value="incident_a",
        evaluator="incident_assignment_match",
        cases=_case(),
        incidents=_incident(),
    )
    result = resolver.resolve("c1", "registry_secret", KnowledgeContext(active_cases={"case_a"}))
    assert result.decision == "deny"
    assert result.reason_code == "condition_context_missing"


def test_incident_does_not_satisfy_case_scope():
    resolver = _resolver_with_condition(
        scope_type="case",
        scope_value="case_a",
        evaluator="case_assignment_match",
        cases=_case(),
        incidents=_incident(),
    )
    result = resolver.resolve(
        "c1", "registry_secret", KnowledgeContext(active_incidents={"incident_a"})
    )
    assert result.decision == "deny"
    assert result.reason_code == "condition_context_missing"


def test_authorization_does_not_bypass_subject():
    data = datasets()
    data["knowledge_rules_data"]["rules"].append({
        "id": "subject-auth-rule",
        "lore_id": "secret",
        "grants": [{
            "subject": {"type": "faction", "faction_id": "f1"},
            "conditions": ["subject_auth"],
        }],
        "acquisition": {"channels": ["case_assignment"]},
    })
    data["knowledge_rules_data"]["vocabulary"]["condition_types"]["subject_auth"] = {
        "evaluator": "explicit_authorization",
    }
    data["condition_scopes_data"]["bindings"].append({
        "id": "subject-auth-binding",
        "rule_id": "subject-auth-rule",
        "lore_id": "secret",
        "condition": "subject_auth",
        "evaluator": "explicit_authorization",
        "status": "resolved",
        "scope": {"type": "authorization", "match": "any", "values": ["auth_a"]},
    })
    resolver = KnowledgeResolver(
        **data,
        projects_data=_project(),
        authorizations_data=_authorization(),
    )
    data["characters_data"]["characters"][0]["identity"]["faction_id"] = "other"
    result = resolver.resolve("c1", "secret", KnowledgeContext(authorizations={"auth_a"}))
    assert result.decision == "deny"


def test_authorization_does_not_unlock_unrelated_rule():
    resolver = _resolver_with_condition(
        scope_type="authorization",
        scope_value="auth_a",
        evaluator="explicit_authorization",
        projects=_project(),
        authorizations=_authorization(),
    )
    result = resolver.resolve("c2", "restricted", KnowledgeContext(authorizations={"auth_a"}))
    assert result.decision == "deny"


def test_unknown_formal_project_runtime_id_is_rejected():
    resolver = _resolver_with_condition(
        scope_type="project",
        scope_value="project_a",
        evaluator="assignment_match",
        projects=_project(),
    )
    with pytest.raises(KnowledgeContextValidationError, match="project_b"):
        resolver.resolve("c1", "registry_secret", KnowledgeContext(active_projects={"project_b"}))


def test_support_registry_does_not_require_new_responsibility_or_assignment_vocabulary():
    import yaml
    from pathlib import Path

    document = yaml.safe_load(Path("data/knowledge/knowledge_rules.yaml").read_text(encoding="utf-8"))
    responsibility_types = set(document["vocabulary"]["responsibility_types"])
    assignment_types = set(document["vocabulary"]["assignment_types"])
    assert not responsibility_types & {
        "insurance_claims_context",
        "model_review_context",
        "artist_project_context",
        "community_member_coordination",
        "research_project_leadership",
        "research_methodology_duty",
    }
    assert "writeback_longitudinal_research" not in assignment_types


def test_removed_project_reopens_project_scope_gaps():
    import yaml
    from pathlib import Path

    document = yaml.safe_load(Path("data/knowledge/condition_scopes.yaml").read_text(encoding="utf-8"))
    bindings = {(item["rule_id"], item["condition"]): item for item in document["bindings"]}
    for key in (("knowledge_rule_010", "relevant_project"), ("knowledge_rule_011", "assigned_to_related_project")):
        binding = bindings[key]
        assert binding["status"] == "unresolved"
        assert binding["scope"]["values"] == []
