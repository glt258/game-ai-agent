from copy import deepcopy

import pytest

from knowledge import KnowledgeResolver
from story import (
    IllegalStoryTransitionError,
    KnowledgeContextProvider,
    StoryConfigurationError,
    StoryRuntime,
    StoryState,
    StoryStateValidationError,
    UnknownStoryError,
    UnknownTransitionError,
    load_story_repository,
)
from story.loader import StoryRepository
from story.models import StoryDefinition, StoryTransition
from story.validation import validate_story_canon, validate_story_definitions


STORY_ID = "story_after_the_show_001"
CASE_ID = "case_nanzhan_postshow_coordination_001"
INCIDENT_ID = "incident_nanzhan_postshow_route_conflict_001"
TRANSITIONS = [
    "transition_start_route_conflict",
    "transition_record_incident",
    "transition_open_case",
    "transition_begin_joint_fact_check",
    "transition_complete_vertical_slice",
]


def _advance(runtime: StoryRuntime, count: int = 5) -> StoryState:
    state = runtime.initial_state(STORY_ID)
    for transition_id in TRANSITIONS[:count]:
        state = runtime.transition(state, transition_id)
    return state


def test_story_definition_and_registered_instance_refs_load():
    repository = load_story_repository()
    resolver = KnowledgeResolver()
    assert set(repository.canon) == {STORY_ID}
    assert set(repository.definitions) == {STORY_ID}
    assert set(resolver.cases) == {CASE_ID}
    assert set(resolver.incidents) == {INCIDENT_ID}
    assert resolver.cases[CASE_ID]["story_refs"] == [STORY_ID]
    assert resolver.incidents[INCIDENT_ID]["story_refs"] == [STORY_ID]
    assert resolver.cases[CASE_ID]["related_incident_ids"] == [INCIDENT_ID]
    assert resolver.incidents[INCIDENT_ID]["related_case_ids"] == [CASE_ID]
    assert CASE_ID != INCIDENT_ID


def test_story_canon_keeps_player_unregistered_and_witness_unassigned():
    story = load_story_repository().canon[STORY_ID]
    assert story["player_participation"]["present"] is True
    assert story["player_participation"]["character_id"] is None
    assert story["player_participation"]["player_identity_integration"] == "deferred"
    witness = next(
        fact for fact in story["character_facts"] if fact["character_id"] == "char_launch_004"
    )
    assert witness["participation"] == "stage_worker_and_witness"


def test_initial_state_is_minimal():
    state = StoryRuntime().initial_state(STORY_ID)
    assert state.to_dict() == {
        "story_id": STORY_ID,
        "current_node_id": "node_pre_close",
        "completed_node_ids": [],
        "active_case_ids": [],
        "active_incident_ids": [],
        "character_case_assignments": {},
        "character_incident_assignments": {},
        "story_flags": {},
    }


def test_incident_and_case_activate_with_separate_assignments():
    runtime = StoryRuntime()
    incident_state = _advance(runtime, 1)
    assert incident_state.active_incident_ids == {INCIDENT_ID}
    assert incident_state.character_incident_assignments["char_launch_007"] == {INCIDENT_ID}
    assert incident_state.active_case_ids == set()
    case_state = _advance(runtime, 3)
    assert case_state.active_case_ids == {CASE_ID}
    assert case_state.character_case_assignments["char_launch_001"] == {CASE_ID}
    assert CASE_ID not in case_state.active_incident_ids
    assert INCIDENT_ID not in case_state.active_case_ids


def test_complete_sequence_is_deterministic_and_does_not_mutate_input():
    runtime = StoryRuntime()
    initial = runtime.initial_state(STORY_ID)
    first = _advance(runtime)
    second = _advance(runtime)
    assert first == second
    assert initial.current_node_id == "node_pre_close"
    assert initial.completed_node_ids == set()
    assert first.current_node_id == "node_slice_complete"
    assert first.completed_node_ids == {
        "node_pre_close",
        "node_route_conflict",
        "node_incident_handling",
        "node_case_opened",
        "node_joint_fact_check",
    }
    assert dict(first.story_flags) == {
        "joint_facts_confirmed": True,
        "vertical_slice_complete": True,
    }


def test_duplicate_assignment_is_idempotent():
    runtime = StoryRuntime()
    preassigned = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
        active_incident_ids={INCIDENT_ID},
        character_incident_assignments={"char_launch_007": {INCIDENT_ID}},
    )
    state = runtime.transition(preassigned, TRANSITIONS[0])
    assert state.character_incident_assignments["char_launch_007"] == {INCIDENT_ID}


def test_illegal_and_unknown_transitions_are_domain_errors():
    runtime = StoryRuntime()
    initial = runtime.initial_state(STORY_ID)
    with pytest.raises(IllegalStoryTransitionError):
        runtime.transition(initial, "transition_open_case")
    with pytest.raises(UnknownTransitionError):
        runtime.transition(initial, "missing_transition")
    with pytest.raises(UnknownStoryError):
        runtime.initial_state("missing_story")


def test_serialization_round_trip_is_stable():
    runtime = StoryRuntime()
    state = _advance(runtime)
    payload = state.to_dict()
    restored = runtime.restore(payload)
    assert restored == state
    assert restored.to_dict() == payload


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("active_case_ids", ["missing_case"], "unknown runtime case"),
        ("active_incident_ids", ["missing_incident"], "unknown runtime incident"),
        (
            "character_case_assignments",
            {"missing_character": [CASE_ID]},
            "unknown runtime character",
        ),
    ],
)
def test_restore_rejects_unknown_runtime_references(field, value, message):
    runtime = StoryRuntime()
    payload = runtime.initial_state(STORY_ID).to_dict()
    payload[field] = value
    if field == "character_case_assignments":
        payload["active_case_ids"] = [CASE_ID]
    with pytest.raises(StoryStateValidationError, match=message):
        runtime.restore(payload)


def test_restore_rejects_assignment_to_inactive_object():
    runtime = StoryRuntime()
    payload = runtime.initial_state(STORY_ID).to_dict()
    payload["character_case_assignments"] = {"char_launch_001": [CASE_ID]}
    with pytest.raises(StoryStateValidationError, match="inactive"):
        runtime.restore(payload)


@pytest.mark.parametrize("field", ["allow_lore", "grant_knowledge", "can_access"])
def test_story_state_cannot_directly_grant_knowledge(field):
    payload = StoryRuntime().initial_state(STORY_ID).to_dict()
    payload[field] = True
    with pytest.raises(StoryStateValidationError, match="unknown StoryState"):
        StoryState.from_dict(payload)


@pytest.mark.parametrize("flag", ["allow_lore", "grant_knowledge", "can_access", "permission"])
def test_permission_like_story_flags_are_rejected(flag):
    with pytest.raises(StoryStateValidationError, match="forbidden"):
        StoryState(story_id=STORY_ID, current_node_id="node_pre_close", story_flags={flag: True})


def test_knowledge_context_provider_emits_only_explicit_assignments():
    runtime = StoryRuntime()
    provider = KnowledgeContextProvider(runtime.repository)
    state = _advance(runtime, 3)
    tang = provider.for_character("char_launch_001", state)
    ji = provider.for_character("char_launch_007", state)
    yu = provider.for_character("char_launch_004", state)
    lumi = provider.for_character("char_launch_002", state)
    assert tang.active_cases == {CASE_ID} and not tang.active_incidents
    assert ji.active_incidents == {INCIDENT_ID} and not ji.active_cases
    assert not yu.active_cases and not yu.active_incidents
    assert not lumi.active_cases and not lumi.active_incidents
    for context in (tang, ji, yu, lumi):
        assert not context.active_responsibilities
        assert not context.active_assignments
        assert not context.active_projects
        assert not context.authorizations
        assert not context.active_roles
        assert not context.artist_teams


def test_runtime_assignments_cannot_bypass_knowledge_subjects():
    runtime = StoryRuntime()
    provider = KnowledgeContextProvider(runtime.repository)
    resolver = KnowledgeResolver()
    state = _advance(runtime, 3)
    tang_result = resolver.resolve(
        "char_launch_001", "lore_005", provider.for_character("char_launch_001", state)
    )
    ji_result = resolver.resolve(
        "char_launch_007", "lore_027", provider.for_character("char_launch_007", state)
    )
    assert tang_result.decision == "deny"
    assert ji_result.decision == "deny"
    assert resolver.resolve("char_launch_002", "lore_018").decision == "allow"
    assert resolver.resolve("char_launch_006", "lore_secret_002").decision == "deny"


def test_definition_validator_rejects_unknown_refs_and_arbitrary_effects():
    repository = load_story_repository()
    from knowledge.loader import default_data_dir, load_yaml

    raw = load_yaml(default_data_dir() / "stories" / "story_definitions.yaml")
    unknown_case = deepcopy(raw)
    unknown_case["story_definitions"][0]["transitions"][2]["effects"][0]["case_id"] = "missing"
    with pytest.raises(StoryConfigurationError, match="unknown case"):
        validate_story_definitions(
            unknown_case,
            story_ids={STORY_ID},
            case_ids={CASE_ID},
            incident_ids={INCIDENT_ID},
            character_ids=set(repository.character_ids),
        )
    arbitrary = deepcopy(raw)
    arbitrary["story_definitions"][0]["transitions"][0]["effects"][0] = {
        "type": "eval",
        "code": "permission = True",
    }
    with pytest.raises(StoryConfigurationError, match="unsupported effect"):
        validate_story_definitions(
            arbitrary,
            story_ids={STORY_ID},
            case_ids={CASE_ID},
            incident_ids={INCIDENT_ID},
            character_ids=set(repository.character_ids),
        )


def test_story_canon_validator_rejects_unknown_character_and_district_id():
    from knowledge.loader import default_data_dir, load_yaml

    raw = load_yaml(default_data_dir() / "stories" / "story_canon.yaml")
    bad_character = deepcopy(raw)
    bad_character["stories"][0]["featured_character_ids"].append("missing")
    with pytest.raises(StoryConfigurationError, match="unknown character"):
        validate_story_canon(
            bad_character,
            city_ids={"city_linzhou"},
            faction_ids={"faction_001", "faction_005", "faction_006"},
            character_ids={"char_launch_001", "char_launch_004", "char_launch_007"},
        )
    bad_district = deepcopy(raw)
    bad_district["stories"][0]["setting"]["district_id"] = "district_nanzhan"
    with pytest.raises(StoryConfigurationError, match="district_id"):
        validate_story_canon(
            bad_district,
            city_ids={"city_linzhou"},
            faction_ids={"faction_001", "faction_005", "faction_006"},
            character_ids={"char_launch_001", "char_launch_004", "char_launch_007"},
        )


def test_assigning_inactive_case_is_an_illegal_transition():
    repository = load_story_repository()
    bad_transition = StoryTransition(
        "assign_inactive",
        "node_pre_close",
        "node_route_conflict",
        (
            {
                "type": "assign_character_to_case",
                "character_id": "char_launch_001",
                "case_id": CASE_ID,
            },
        ),
    )
    original = repository.definitions[STORY_ID]
    definition = StoryDefinition(
        original.story_id,
        original.initial_node_id,
        original.node_ids,
        original.terminal_node_ids,
        {**original.transitions, "assign_inactive": bad_transition},
    )
    injected = StoryRepository(
        repository.canon,
        {STORY_ID: definition},
        repository.character_ids,
        repository.case_ids,
        repository.incident_ids,
    )
    runtime = StoryRuntime(injected)
    with pytest.raises(IllegalStoryTransitionError, match="inactive case"):
        runtime.transition(runtime.initial_state(STORY_ID), "assign_inactive")
