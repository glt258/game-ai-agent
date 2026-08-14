import pytest

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import KnowledgeConfigurationError
from knowledge.responsibility_validation import validate_knowledge_responsibilities
from knowledge.loader import load_canon

from test_knowledge_resolver import datasets


def _repository_resolver_with_character(character, *, extra_responsibilities=None):
    data = load_canon()
    data["characters"] = [*data["characters"], character]
    if extra_responsibilities:
        data["knowledge_rules"]["vocabulary"]["responsibility_types"].update(
            extra_responsibilities
        )
    return KnowledgeResolver(
        characters_data=data["characters"],
        lore_data=data["lore"],
        knowledge_rules_data=data["knowledge_rules"],
        factions_data=data["factions"],
        condition_scopes_data=data["condition_scopes"],
        projects_data=data["projects"],
        authorizations_data=data["authorizations"],
    )


def _synthetic_character(character_id, faction_id, responsibilities):
    return {
        "id": character_id,
        "identity": {
            "faction_id": faction_id,
            "responsibilities": responsibilities,
            "roles": [],
            "assignments": [],
            "division_ids": [],
            "explicit_grants": [],
        },
    }


def test_registered_responsibility_allows_only_matching_faction_and_duty():
    data = datasets()
    data["knowledge_rules_data"]["vocabulary"]["responsibility_types"] = {
        "r1": {"faction_id": "f1", "description": "Registered institutional duty"}
    }
    resolver = KnowledgeResolver(**data)
    assert resolver.resolve("c1", "restricted").decision == "allow"

    wrong_duty = resolver.resolve("c2", "restricted")
    assert wrong_duty.decision == "deny"

    data = datasets()
    data["characters_data"]["characters"][0]["identity"]["faction_id"] = "other"
    assert KnowledgeResolver(**data).resolve("c1", "restricted").decision == "deny"


@pytest.mark.parametrize(
    "identity_field, value",
    [
        ("responsibilities", []),
        ("tags", ["research", "model_review", "community"]),
        ("agent_profile", {"responsibility": "r1"}),
    ],
)
def test_occupation_tags_and_agent_profile_do_not_substitute_for_responsibility(
    identity_field, value
):
    data = datasets()
    character = data["characters_data"]["characters"][1]
    character["basic_profile"] = {"occupation": "r1"}
    if identity_field == "agent_profile":
        character[identity_field] = value
    else:
        character[identity_field] = value
    assert KnowledgeResolver(**data).resolve("c2", "restricted").decision == "deny"


def test_responsibility_validator_rejects_forbidden_suffix_and_cross_faction_scope():
    data = datasets()
    data["knowledge_rules_data"]["vocabulary"]["responsibility_types"]["bad_access"] = {
        "faction_id": "f1",
        "description": "An institutional duty",
    }
    with pytest.raises(KnowledgeConfigurationError, match="forbidden responsibility naming suffix"):
        validate_knowledge_responsibilities(
            knowledge_rules_data=data["knowledge_rules_data"],
            condition_scopes_data=data["condition_scopes_data"],
            factions_data=data["factions_data"],
            characters_data=data["characters_data"],
        )


@pytest.mark.parametrize(
    "responsibility, faction_id, lore_id",
    [
        ("professional_standards_governance", "faction_001", "lore_003"),
        ("research_ethics_data_governance", "faction_002", "lore_009"),
        ("risk_model_development_maintenance", "faction_003", "lore_014"),
        ("model_governance_duty", "faction_003", "lore_014"),
        ("artist_risk_management", "faction_004", "lore_020"),
    ],
)
def test_repository_responsibilities_allow_synthetic_character(
    responsibility, faction_id, lore_id
):
    character_id = f"synthetic_{responsibility}"
    resolver = _repository_resolver_with_character(
        _synthetic_character(character_id, faction_id, [responsibility])
    )
    assert resolver.resolve(character_id, lore_id).decision == "allow"


def test_rule_008_remains_unresolved_without_institutional_methodology_responsibility():
    data = load_canon()
    responsibilities = data["knowledge_rules"]["vocabulary"]["responsibility_types"]
    assert "research_methodology_duty" not in responsibilities
    binding = next(
        item
        for item in data["condition_scopes"]["bindings"]
        if item["rule_id"] == "knowledge_rule_008"
    )
    assert binding["status"] == "unresolved"
    assert binding["scope"] == {"type": "responsibility", "match": "any", "values": []}

    resolver = _repository_resolver_with_character(
        _synthetic_character("synthetic_researcher", "faction_002", [])
    )
    result = resolver.resolve(
        "synthetic_researcher",
        "lore_008",
        KnowledgeContext(active_responsibilities={"research_methodology_duty"}),
    )
    assert result.decision == "deny"
    assert result.reason_code == "condition_scope_unresolved"


def test_rule_014_accepts_model_development_or_model_governance_responsibility():
    data = load_canon()
    definition = data["knowledge_rules"]["vocabulary"]["responsibility_types"][
        "risk_model_development_maintenance"
    ]
    assert definition["faction_id"] == "faction_003"
    for boundary in ("模型数据访问", "治理权限", "衡信全部 Lore Access"):
        assert boundary in definition["description"]

    for responsibility in (
        "risk_model_development_maintenance",
        "model_governance_duty",
    ):
        character_id = f"synthetic_rule_014_{responsibility}"
        resolver = _repository_resolver_with_character(
            _synthetic_character(character_id, "faction_003", [responsibility])
        )
        assert resolver.resolve(character_id, "lore_014").decision == "allow"

    unrelated_id = "unrelated_hengxin_duty"
    resolver = _repository_resolver_with_character(
        _synthetic_character("synthetic_rule_014_unrelated", "faction_003", [unrelated_id]),
        extra_responsibilities={
            unrelated_id: {
                "faction_id": "faction_003",
                "description": "Synthetic unrelated institutional duty.",
            }
        },
    )
    assert resolver.resolve("synthetic_rule_014_unrelated", "lore_014").decision == "deny"


def test_rule_015_is_not_resolved_by_model_governance_duty():
    resolver = _repository_resolver_with_character(
        _synthetic_character(
            "synthetic_rule_015_governance",
            "faction_003",
            ["model_governance_duty"],
        )
    )
    result = resolver.resolve("synthetic_rule_015_governance", "lore_015")
    assert result.decision == "deny"
    assert result.reason_code == "condition_scope_unresolved"


def test_rule_021_is_not_resolved_by_artist_risk_management():
    resolver = _repository_resolver_with_character(
        _synthetic_character(
            "synthetic_rule_021_artist_risk",
            "faction_004",
            ["artist_risk_management"],
        )
    )
    result = resolver.resolve("synthetic_rule_021_artist_risk", "lore_021")
    assert result.decision == "deny"
    assert result.reason_code == "condition_scope_unresolved"


def test_semantic_cleanup_gap_taxonomy_distinguishes_vocabulary_and_context_gaps():
    resolver = KnowledgeResolver()
    inventory = {
        item["rule_id"]: item
        for item in resolver.scope_registry.inventory(
            resolver.rules, resolver.vocabulary["condition_types"]
        )
    }
    assert inventory["knowledge_rule_008"]["gap_type"] == "insufficient_responsibility_vocabulary"
    assert inventory["knowledge_rule_015"]["gap_type"] == "insufficient_context_model"
    assert inventory["knowledge_rule_021"]["gap_type"] == "insufficient_context_model"


def test_repository_responsibility_cannot_be_replaced_by_occupation_tags_or_profile():
    data = load_canon()
    data["characters"] = list(data["characters"])
    data["characters"].append(
        {
            "id": "synthetic_no_responsibility",
            "identity": {
                "faction_id": "faction_003",
                "responsibilities": [],
                "roles": [],
                "assignments": [],
                "division_ids": [],
                "explicit_grants": [],
                "tags": ["model_review"],
            },
            "basic_profile": {"occupation": "model governance duty"},
            "agent_profile": {"responsibility": "model_governance_duty"},
        }
    )
    resolver = KnowledgeResolver(
        characters_data=data["characters"],
        lore_data=data["lore"],
        knowledge_rules_data=data["knowledge_rules"],
        factions_data=data["factions"],
        condition_scopes_data=data["condition_scopes"],
        projects_data=data["projects"],
        authorizations_data=data["authorizations"],
    )
    assert resolver.resolve("synthetic_no_responsibility", "lore_014").decision == "deny"

    data = datasets()
    data["knowledge_rules_data"]["vocabulary"]["responsibility_types"]["r1"]["faction_id"] = "other"
    with pytest.raises(KnowledgeConfigurationError, match="responsibility faction does not match"):
        validate_knowledge_responsibilities(
            knowledge_rules_data=data["knowledge_rules_data"],
            condition_scopes_data=data["condition_scopes_data"],
            factions_data=data["factions_data"],
            characters_data=data["characters_data"],
        )
