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
from along_street_resources import data_resource
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


INVALID_ID_COLLECTION_SHAPES = [
    pytest.param(None, id="none"),
    pytest.param(42, id="integer"),
    pytest.param(True, id="bool"),
    pytest.param(1.5, id="float"),
    pytest.param("case_id", id="string"),
    pytest.param(b"case_id", id="bytes"),
    pytest.param({"case_id": "case_id"}, id="mapping"),
    pytest.param(lambda: (item for item in ("case_id",)), id="generator"),
]
INVALID_ID_ELEMENTS = [
    pytest.param(42, id="integer"),
    pytest.param(True, id="bool"),
    pytest.param(None, id="none"),
    pytest.param("", id="empty-string"),
    pytest.param(["nested"], id="nested-list"),
]
ASSIGNMENT_FIELDS = [
    "character_case_assignments",
    "character_incident_assignments",
]
ID_COLLECTION_FIELDS = [
    "completed_node_ids",
    "active_case_ids",
    "active_incident_ids",
]


def _fresh_test_value(value):
    return value() if callable(value) else value


def _minimal_state_kwargs() -> dict:
    return {"story_id": STORY_ID, "current_node_id": "node_pre_close"}


@pytest.mark.parametrize("field", ID_COLLECTION_FIELDS)
@pytest.mark.parametrize("value", INVALID_ID_COLLECTION_SHAPES)
def test_story_state_rejects_invalid_id_collection_shapes(field, value):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = _fresh_test_value(value)
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} must be an ID collection",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("field", ID_COLLECTION_FIELDS)
@pytest.mark.parametrize("element", INVALID_ID_ELEMENTS)
def test_story_state_rejects_invalid_id_collection_elements(field, element):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = [element]
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} contains an invalid ID",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
@pytest.mark.parametrize("value", INVALID_ID_COLLECTION_SHAPES)
def test_story_state_rejects_invalid_assignment_value_shapes(field, value):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = {"char_launch_001": _fresh_test_value(value)}
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} values must be ID collections",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
@pytest.mark.parametrize("element", INVALID_ID_ELEMENTS)
def test_story_state_rejects_invalid_assignment_value_elements(field, element):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = {"char_launch_001": [element]}
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} contains an invalid ID",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
@pytest.mark.parametrize("value", [None, 42, [], (), set(), "assignments"])
def test_story_state_rejects_non_mapping_assignments(field, value):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = value
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} must be a mapping",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
@pytest.mark.parametrize("key", [None, "", 42, True])
def test_story_state_rejects_invalid_assignment_keys(field, key):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = {key: ["case_id"]}
    with pytest.raises(
        StoryStateValidationError,
        match=rf"{field} requires non-empty character IDs",
    ):
        StoryState(**kwargs)


@pytest.mark.parametrize("collection_type", [list, tuple, set, frozenset])
def test_story_state_accepts_all_id_collection_types_and_normalizes_them(collection_type):
    values = collection_type(("id_b", "id_a", "id_a"))
    state = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
        completed_node_ids=values,
        active_case_ids=values,
        active_incident_ids=values,
        character_case_assignments={"char_launch_001": values},
        character_incident_assignments={"char_launch_007": values},
    )
    assert state.completed_node_ids == {"id_a", "id_b"}
    assert state.active_case_ids == {"id_a", "id_b"}
    assert state.active_incident_ids == {"id_a", "id_b"}
    assert state.character_case_assignments["char_launch_001"] == {"id_a", "id_b"}
    assert state.character_incident_assignments["char_launch_007"] == {"id_a", "id_b"}
    assert state.to_dict()["completed_node_ids"] == ["id_a", "id_b"]


def test_story_state_allows_empty_id_collections_and_drops_empty_assignments():
    state = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
        completed_node_ids=[],
        active_case_ids=(),
        active_incident_ids=set(),
        character_case_assignments={"char_launch_001": frozenset()},
        character_incident_assignments={"char_launch_007": []},
    )
    assert state.completed_node_ids == set()
    assert state.active_case_ids == set()
    assert state.active_incident_ids == set()
    assert dict(state.character_case_assignments) == {}
    assert dict(state.character_incident_assignments) == {}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("active_case_ids", 42, "active_case_ids must be an ID collection"),
        (
            "character_case_assignments",
            {"char_launch_001": 42},
            "character_case_assignments values must be ID collections",
        ),
    ],
)
def test_exact_invalid_inputs_fail_at_direct_constructor_and_restore(field, value, message):
    kwargs = _minimal_state_kwargs()
    kwargs[field] = value
    with pytest.raises(StoryStateValidationError, match=message):
        StoryState(**kwargs)

    runtime = StoryRuntime()
    payload = runtime.initial_state(STORY_ID).to_dict()
    payload[field] = value
    with pytest.raises(StoryStateValidationError, match=message):
        runtime.restore(payload)


@pytest.mark.parametrize("payload", [None, 42, [], "state"])
def test_story_state_from_dict_requires_a_mapping(payload):
    with pytest.raises(StoryStateValidationError, match="payload must be a mapping"):
        StoryState.from_dict(payload)


@pytest.mark.parametrize("key", [42, None, True])
def test_story_state_from_dict_rejects_non_string_field_names(key):
    payload = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
    ).to_dict()
    payload[key] = "unexpected"
    with pytest.raises(StoryStateValidationError, match="StoryState field names must be strings"):
        StoryState.from_dict(payload)


def test_story_state_from_dict_rejects_heterogeneous_keys_before_sorting_them():
    payload = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
    ).to_dict()
    payload[42] = "unexpected"
    payload["also_unexpected"] = "unexpected"
    with pytest.raises(StoryStateValidationError, match="StoryState field names must be strings"):
        StoryState.from_dict(payload)


def test_story_state_flags_keep_bool_values_and_reject_explicit_none():
    state = StoryState(
        story_id=STORY_ID,
        current_node_id="node_pre_close",
        story_flags={"is_ready": True},
    )
    assert state.story_flags["is_ready"] is True
    with pytest.raises(StoryStateValidationError, match="story flag is_ready"):
        StoryState(story_id=STORY_ID, current_node_id="node_pre_close", story_flags={"is_ready": None})


def test_representative_story_state_error_has_no_python_exception_cause():
    with pytest.raises(StoryStateValidationError) as caught:
        StoryState(story_id=STORY_ID, current_node_id="node_pre_close", active_case_ids=42)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("state", [None, {}])
def test_runtime_validate_rejects_non_story_state(state):
    with pytest.raises(StoryStateValidationError, match="state must be a StoryState"):
        StoryRuntime().validate(state)


def test_runtime_transition_rejects_non_story_state_before_transition_lookup():
    with pytest.raises(StoryStateValidationError, match="state must be a StoryState"):
        StoryRuntime().transition(None, TRANSITIONS[0])


@pytest.mark.parametrize("story_id", [None, 42, True, 1.5, b"story", ""])
def test_initial_state_rejects_invalid_story_ids_before_repository_lookup(story_id):
    with pytest.raises(StoryStateValidationError, match="story_id must be a non-empty string"):
        StoryRuntime().initial_state(story_id)


def test_initial_state_keeps_unknown_valid_story_id_as_domain_error():
    with pytest.raises(UnknownStoryError, match="Unknown story"):
        StoryRuntime().initial_state("missing_story")


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
    from knowledge.loader import load_yaml

    raw = load_yaml(data_resource("stories", "story_definitions.yaml"))
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
    from knowledge.loader import load_yaml

    raw = load_yaml(data_resource("stories", "story_canon.yaml"))
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
