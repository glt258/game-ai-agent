from __future__ import annotations

from copy import deepcopy

import pytest
import character_skill

from character_skill import (
    AbilityEntry,
    BehaviorProtocol,
    Effect,
    FeedbackRelation,
    ProtocolSkillKitCandidate,
    ResourceLease,
    RoleEvidence,
    SkillKitShapeError,
    StateLease,
    Subject,
    SummonLease,
    Trigger,
    TypedRef,
    parse_candidate,
)


EMPTY_CANDIDATE = {
    "schema_version": "skill-kit-candidate/0.1.1",
    "entries": [],
    "feedback_relations": [],
    "resources": [],
    "states": [],
    "summons": [],
    "role_evidence": [],
    "display_summary": "",
}


def test_empty_candidate_parses_round_trips_and_has_fixed_digest() -> None:
    candidate = parse_candidate(EMPTY_CANDIDATE)

    assert isinstance(candidate, ProtocolSkillKitCandidate)
    assert candidate.entries == ()
    assert candidate.feedback_relations == ()
    assert candidate.resources == ()
    assert candidate.states == ()
    assert candidate.summons == ()
    assert candidate.role_evidence == ()
    assert candidate.to_mapping() == EMPTY_CANDIDATE
    assert candidate.canonical_json() == (
        '{"display_summary":"","entries":[],"feedback_relations":[],'
        '"resources":[],"role_evidence":[],"schema_version":'
        '"skill-kit-candidate/0.1.1","states":[],"summons":[]}'
    )
    assert candidate.digest == (
        "541afbbf09eb26136c9cf30bdc619213b51f27e46782f8506344dc4e2eb1c934"
    )


FULL_CANDIDATE = {
    "schema_version": "skill-kit-candidate/0.1.1",
    "entries": [
        {
            "ability_id": "echo",
            "name": "Echo",
            "mode": "reaction",
            "protocols": [
                {
                    "protocol_id": "trigger",
                    "when": {
                        "subject": {
                            "kind": "ally",
                            "selector": "teammate",
                            "entity_ref": None,
                        },
                        "event": "action_completed",
                        "source_ref": None,
                        "qualifier": None,
                    },
                    "causes": [
                        {
                            "effect_id": "apply_echo",
                            "subject": {
                                "kind": "ally",
                                "selector": None,
                                "entity_ref": None,
                            },
                            "operation": "ally_enablement",
                            "object_ref": None,
                            "description": "enables an ally",
                        }
                    ],
                }
            ],
            "display_text": "Echo response",
        }
    ],
    "feedback_relations": [
        {
            "feedback_id": "echo_feedback",
            "source_effect": {"kind": "effect", "id": "echo/trigger/apply_echo"},
            "target_protocol": {"kind": "protocol", "id": "echo/trigger"},
            "event": "effect_resolved",
            "operation": "enables",
        }
    ],
    "resources": [
        {
            "resource_id": "mark",
            "opened_by": [{"kind": "effect", "id": "echo/trigger/apply_echo"}],
            "used_or_transformed_by": [],
            "closed_by": [],
        }
    ],
    "states": [
        {
            "state_id": "focus",
            "established_by": [],
            "active_effects": [],
            "ended_or_replaced_by": [],
        }
    ],
    "summons": [
        {
            "summon_id": "field",
            "spawned_by": [],
            "active_effects": [],
            "departed_or_replaced_by": [],
            "repeat_policy": None,
        }
    ],
    "role_evidence": [
        {
            "effect_refs": [{"kind": "effect", "id": "echo/trigger/apply_echo"}],
            "centrality": "core",
        }
    ],
    "display_summary": "Echo response",
}


def test_fully_nested_candidate_returns_frozen_value_objects_and_typed_refs() -> None:
    candidate = parse_candidate(FULL_CANDIDATE)

    assert isinstance(candidate.entries, tuple)
    entry = candidate.entries[0]
    assert isinstance(entry, AbilityEntry)
    assert isinstance(entry.protocols, tuple)
    protocol = entry.protocols[0]
    assert isinstance(protocol, BehaviorProtocol)
    assert isinstance(protocol.when, Trigger)
    assert isinstance(protocol.when.subject, Subject)
    assert protocol.when.subject.kind == "ally"
    effect = protocol.causes[0]
    assert isinstance(effect, Effect)
    assert effect.effect_id == "apply_echo"
    assert isinstance(candidate.feedback_relations[0], FeedbackRelation)
    assert isinstance(candidate.feedback_relations[0].source_effect, TypedRef)
    assert isinstance(candidate.resources[0], ResourceLease)
    assert isinstance(candidate.states[0], StateLease)
    assert isinstance(candidate.summons[0], SummonLease)
    assert isinstance(candidate.role_evidence[0], RoleEvidence)
    assert candidate.summons[0].repeat_policy is None
    assert candidate.to_mapping() == FULL_CANDIDATE


def test_nullable_and_empty_semantic_slots_are_parseable() -> None:
    payload = {
        "schema_version": "skill-kit-candidate/0.1.1",
        "entries": [
            {
                "ability_id": "empty_ability",
                "name": "",
                "mode": "active",
                "protocols": [
                    {
                        "protocol_id": "empty_protocol",
                        "when": None,
                        "causes": [],
                    }
                ],
                "display_text": "",
            }
        ],
        "feedback_relations": [],
        "resources": [],
        "states": [],
        "summons": [
            {
                "summon_id": "empty_summon",
                "spawned_by": [],
                "active_effects": [],
                "departed_or_replaced_by": [],
                "repeat_policy": None,
            }
        ],
        "role_evidence": [],
        "display_summary": "",
    }

    candidate = parse_candidate(payload)

    assert candidate.entries[0].protocols[0].when is None
    assert candidate.entries[0].protocols[0].causes == ()
    assert candidate.summons[0].repeat_policy is None
    assert candidate.summons[0].spawned_by == ()


def _assert_shape_error(payload: object, code: str, field_path: str) -> None:
    try:
        parse_candidate(payload)  # type: ignore[arg-type]
    except SkillKitShapeError as error:
        assert error.code == code
        assert error.field_path == field_path
        assert error.message == error.detail
        assert error.to_dict() == {
            "code": code,
            "field_path": field_path,
            "message": error.message,
            "detail": error.detail,
        }
    else:
        raise AssertionError("parse_candidate accepted an invalid shape")


def test_unknown_and_missing_fields_report_stable_json_pointer_paths() -> None:
    unknown = dict(EMPTY_CANDIDATE)
    unknown["unexpected"] = True
    _assert_shape_error(unknown, "UNKNOWN_FIELD", "/unexpected")

    missing = dict(EMPTY_CANDIDATE)
    del missing["entries"]
    _assert_shape_error(missing, "MISSING_FIELD", "/entries")

    nested_unknown = dict(FULL_CANDIDATE)
    nested_unknown["entries"] = [dict(FULL_CANDIDATE["entries"][0])]
    nested_unknown["entries"][0]["extra"] = True
    _assert_shape_error(nested_unknown, "UNKNOWN_FIELD", "/entries/0/extra")

    nested_missing = dict(FULL_CANDIDATE)
    nested_missing["entries"] = [dict(FULL_CANDIDATE["entries"][0])]
    del nested_missing["entries"][0]["mode"]
    _assert_shape_error(nested_missing, "MISSING_FIELD", "/entries/0/mode")

    escaped = dict(EMPTY_CANDIDATE)
    escaped["a/b"] = True
    _assert_shape_error(escaped, "UNKNOWN_FIELD", "/a~1b")


def test_type_enum_and_id_shape_errors_are_closed_and_locatable() -> None:
    _assert_shape_error(
        {**EMPTY_CANDIDATE, "entries": "not-an-array"},
        "TYPE_MISMATCH",
        "/entries",
    )

    bad_mode = dict(FULL_CANDIDATE)
    bad_mode["entries"] = [dict(FULL_CANDIDATE["entries"][0])]
    bad_mode["entries"][0]["mode"] = "unknown_mode"
    _assert_shape_error(bad_mode, "UNSUPPORTED_VALUE", "/entries/0/mode")

    bad_id = dict(FULL_CANDIDATE)
    bad_id["entries"] = [dict(FULL_CANDIDATE["entries"][0])]
    bad_id["entries"][0]["ability_id"] = "Echo"
    _assert_shape_error(bad_id, "INVALID_ID", "/entries/0/ability_id")

    bad_ref_kind = dict(FULL_CANDIDATE)
    bad_ref_kind["feedback_relations"] = [dict(FULL_CANDIDATE["feedback_relations"][0])]
    bad_ref_kind["feedback_relations"][0]["source_effect"] = {
        "kind": "unknown",
        "id": "echo/trigger/apply_echo",
    }
    _assert_shape_error(
        bad_ref_kind,
        "UNSUPPORTED_VALUE",
        "/feedback_relations/0/source_effect/kind",
    )

    bad_ref_shape = dict(FULL_CANDIDATE)
    bad_ref_shape["feedback_relations"] = [dict(FULL_CANDIDATE["feedback_relations"][0])]
    bad_ref_shape["feedback_relations"][0]["target_protocol"] = {
        "kind": "protocol",
        "id": "echo",
    }
    _assert_shape_error(
        bad_ref_shape,
        "INVALID_ID",
        "/feedback_relations/0/target_protocol/id",
    )


@pytest.mark.parametrize(
    ("field_path", "mutate"),
    [
        ("/schema_version", lambda payload: payload.update({"schema_version": "skill-kit-candidate/9.9.9"})),
        ("/entries/0/protocols/0/when/subject/kind", lambda payload: payload["entries"][0]["protocols"][0]["when"]["subject"].update({"kind": "invalid"})),
        ("/entries/0/protocols/0/when/event", lambda payload: payload["entries"][0]["protocols"][0]["when"].update({"event": "invalid"})),
        ("/entries/0/protocols/0/causes/0/operation", lambda payload: payload["entries"][0]["protocols"][0]["causes"][0].update({"operation": "invalid"})),
        ("/feedback_relations/0/event", lambda payload: payload["feedback_relations"][0].update({"event": "invalid"})),
        ("/feedback_relations/0/operation", lambda payload: payload["feedback_relations"][0].update({"operation": "invalid"})),
        ("/summons/0/repeat_policy", lambda payload: payload["summons"][0].update({"repeat_policy": "invalid"})),
        ("/role_evidence/0/centrality", lambda payload: payload["role_evidence"][0].update({"centrality": "invalid"})),
    ],
)
def test_every_closed_value_rejects_unknown_tokens(field_path: str, mutate) -> None:
    payload = deepcopy(FULL_CANDIDATE)
    mutate(payload)
    expected_code = (
        "UNSUPPORTED_SCHEMA_VERSION"
        if field_path == "/schema_version"
        else "UNSUPPORTED_VALUE"
    )
    _assert_shape_error(payload, expected_code, field_path)


def test_array_like_mappings_bytes_and_non_objects_fail_at_their_paths() -> None:
    _assert_shape_error([], "TYPE_MISMATCH", "/")

    mapping_array = deepcopy(FULL_CANDIDATE)
    mapping_array["entries"] = {"not": "an array"}
    _assert_shape_error(mapping_array, "TYPE_MISMATCH", "/entries")

    bytes_array = deepcopy(FULL_CANDIDATE)
    bytes_array["entries"] = b"not-an-array"
    _assert_shape_error(bytes_array, "TYPE_MISMATCH", "/entries")

    scalar_string = deepcopy(FULL_CANDIDATE)
    scalar_string["display_summary"] = 12
    _assert_shape_error(scalar_string, "TYPE_MISMATCH", "/display_summary")


def test_ref_id_segment_counts_are_checked_without_reference_resolution() -> None:
    for kind, identifier in (
        ("protocol", "echo"),
        ("effect", "echo/trigger"),
        ("resource", "mark/extra"),
        ("state", "focus/extra"),
        ("summon", "field/extra"),
    ):
        payload = deepcopy(FULL_CANDIDATE)
        payload["feedback_relations"] = [deepcopy(FULL_CANDIDATE["feedback_relations"][0])]
        payload["feedback_relations"][0]["target_protocol"] = {
            "kind": kind,
            "id": identifier,
        }
        _assert_shape_error(
            payload,
            "INVALID_ID",
            "/feedback_relations/0/target_protocol/id",
        )


def test_duplicate_ids_are_rejected_in_their_declared_namespaces() -> None:
    duplicate_abilities = deepcopy(FULL_CANDIDATE)
    duplicate_abilities["entries"] = [
        deepcopy(FULL_CANDIDATE["entries"][0]),
        deepcopy(FULL_CANDIDATE["entries"][0]),
    ]
    _assert_shape_error(
        duplicate_abilities,
        "DUPLICATE_ID",
        "/entries/1/ability_id",
    )

    duplicate_feedback = deepcopy(FULL_CANDIDATE)
    duplicate_feedback["feedback_relations"] = [
        deepcopy(FULL_CANDIDATE["feedback_relations"][0]),
        deepcopy(FULL_CANDIDATE["feedback_relations"][0]),
    ]
    _assert_shape_error(
        duplicate_feedback,
        "DUPLICATE_ID",
        "/feedback_relations/1/feedback_id",
    )

    duplicate_protocols = deepcopy(FULL_CANDIDATE)
    duplicate_protocols["entries"] = [deepcopy(FULL_CANDIDATE["entries"][0])]
    duplicate_protocols["entries"][0]["protocols"] = [
        deepcopy(FULL_CANDIDATE["entries"][0]["protocols"][0]),
        deepcopy(FULL_CANDIDATE["entries"][0]["protocols"][0]),
    ]
    _assert_shape_error(
        duplicate_protocols,
        "DUPLICATE_ID",
        "/entries/0/protocols/1/protocol_id",
    )

    duplicate_effects = deepcopy(FULL_CANDIDATE)
    duplicate_effects["entries"] = [deepcopy(FULL_CANDIDATE["entries"][0])]
    duplicate_effects["entries"][0]["protocols"] = [
        deepcopy(FULL_CANDIDATE["entries"][0]["protocols"][0])
    ]
    duplicate_effects["entries"][0]["protocols"][0]["causes"] = [
        deepcopy(FULL_CANDIDATE["entries"][0]["protocols"][0]["causes"][0]),
        deepcopy(FULL_CANDIDATE["entries"][0]["protocols"][0]["causes"][0]),
    ]
    _assert_shape_error(
        duplicate_effects,
        "DUPLICATE_ID",
        "/entries/0/protocols/0/causes/1/effect_id",
    )

    for field, identifier, path in (
        ("resources", "resource_id", "/resources/1/resource_id"),
        ("states", "state_id", "/states/1/state_id"),
        ("summons", "summon_id", "/summons/1/summon_id"),
    ):
        payload = deepcopy(FULL_CANDIDATE)
        first = deepcopy(payload[field][0]) if payload[field] else {
            identifier: "shared",
            "opened_by": [],
            "used_or_transformed_by": [],
            "closed_by": [],
        }
        if field == "states":
            first = {"state_id": "shared", "established_by": [], "active_effects": [], "ended_or_replaced_by": []}
        if field == "summons":
            first = {"summon_id": "shared", "spawned_by": [], "active_effects": [], "departed_or_replaced_by": [], "repeat_policy": None}
        second = deepcopy(first)
        payload[field] = [{**first, identifier: "shared"}, {**second, identifier: "shared"}]
        _assert_shape_error(payload, "DUPLICATE_ID", path)


def test_same_textual_id_is_allowed_in_distinct_entity_namespaces() -> None:
    payload = deepcopy(EMPTY_CANDIDATE)
    payload["resources"] = [{
        "resource_id": "shared",
        "opened_by": [],
        "used_or_transformed_by": [],
        "closed_by": [],
    }]
    payload["states"] = [{
        "state_id": "shared",
        "established_by": [],
        "active_effects": [],
        "ended_or_replaced_by": [],
    }]
    payload["summons"] = [{
        "summon_id": "shared",
        "spawned_by": [],
        "active_effects": [],
        "departed_or_replaced_by": [],
        "repeat_policy": None,
    }]

    candidate = parse_candidate(payload)

    assert candidate.resources[0].resource_id == "shared"
    assert candidate.states[0].state_id == "shared"
    assert candidate.summons[0].summon_id == "shared"


@pytest.mark.parametrize(
    "field",
    [
        "implements",
        "satisfies",
        "request_requirement_ids",
        "combat_role",
        "combat_role_profile",
        "role",
    ],
)
def test_provider_self_attestation_and_role_fields_fail_as_unknown(field: str) -> None:
    payload = deepcopy(EMPTY_CANDIDATE)
    payload[field] = "provider-authored"
    _assert_shape_error(payload, "UNKNOWN_FIELD", f"/{field}")


def test_legacy_ability_concept_is_explicit_and_never_inferred() -> None:
    wrapped = parse_candidate({"skill_kit": EMPTY_CANDIDATE})
    assert isinstance(wrapped, ProtocolSkillKitCandidate)
    assert wrapped.to_mapping() == EMPTY_CANDIDATE

    legacy = parse_candidate({"ability_concept": "legacy display text"})

    from character_skill import LegacyAbilityConcept

    assert isinstance(legacy, LegacyAbilityConcept)
    assert legacy.to_mapping() == {"ability_concept": "legacy display text"}
    assert not isinstance(legacy, ProtocolSkillKitCandidate)
    assert not hasattr(legacy, "entries")

    sibling = {"ability_concept": "legacy display text", "extra": True}
    _assert_shape_error(sibling, "UNKNOWN_FIELD", "/extra")

    wrapped = {"skill_kit": EMPTY_CANDIDATE, "extra": True}
    _assert_shape_error(wrapped, "UNKNOWN_FIELD", "/extra")

    mixed = {"ability_concept": "legacy display text", "schema_version": "wrong"}
    _assert_shape_error(mixed, "UNKNOWN_FIELD", "/ability_concept")

    _assert_shape_error(
        {"ability_concept": 7},
        "TYPE_MISMATCH",
        "/ability_concept",
    )


def test_parse_and_mapping_are_isolated_from_input_mutation() -> None:
    payload = deepcopy(FULL_CANDIDATE)
    candidate = parse_candidate(payload)
    original_mapping = candidate.to_mapping()

    payload["display_summary"] = "mutated"
    payload["entries"][0]["protocols"][0]["causes"][0]["description"] = "mutated"
    assert candidate.to_mapping() == original_mapping

    exported = candidate.to_mapping()
    exported["entries"][0]["protocols"][0]["causes"][0]["description"] = "changed export"
    exported["entries"].append({})
    assert candidate.to_mapping() == original_mapping


def test_public_package_exports_only_the_contract_surface() -> None:
    expected = {
        "AbilityEntry",
        "BehaviorProtocol",
        "Effect",
        "FeedbackRelation",
        "LegacyAbilityConcept",
        "ProtocolSkillKitCandidate",
        "ResourceLease",
        "RoleEvidence",
        "SCHEMA_VERSION",
        "VALIDATOR_CONTRACT",
        "SkillKitShapeError",
        "SkillFinding",
        "SkillValidationReport",
        "SkillValidationContext",
        "SkillIntent",
        "MechanicRequirement",
        "TriggerPredicate",
        "EffectPredicate",
        "FeedbackPredicate",
        "ReferenceFingerprint",
        "ReferenceReviewContext",
        "StateLease",
        "Subject",
        "SummonLease",
        "Trigger",
        "TypedRef",
        "parse_candidate",
        "evaluate",
        "render_ability_concept",
        "SkillKitPatch",
        "SkillKitPatchError",
        "SkillKitRepairRequest",
        "SkillKitRepairResult",
        "repair_once",
    }
    assert set(character_skill.__all__) == expected
    assert all(not name.startswith("_") for name in character_skill.__all__)
    assert "evals" not in character_skill.parse_candidate.__module__
