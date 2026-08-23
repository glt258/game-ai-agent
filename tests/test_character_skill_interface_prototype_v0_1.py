from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evals.character_skill_interface_prototype_v0_1 import (
    CandidateShapeError,
    PatchRejected,
    apply_patch,
    evaluate,
    parse_candidate,
    render_ability_concept,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "character_skill_interface_prototype_cases_v0.1.1.json"
PUBLIC_FIXTURE = ROOT / "evals" / "fixtures" / "character_skill_interface_prototype_cases_v0.1.1.public.json"


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _case_inputs() -> dict[str, tuple[dict[str, object], dict[str, object]]]:
    fixture = _load()
    candidates = fixture["candidates"]
    contexts = fixture["contexts"]
    result: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for case in fixture["cases"]:
        payload = copy.deepcopy(candidates[case["candidate_ref"]])
        context = copy.deepcopy(contexts[case["context_ref"]])
        result[case["id"]] = (payload, context)
    return result


def _typed(kind: str, identifier: str) -> dict[str, str]:
    return {"kind": kind, "id": identifier}


def _feedback(source: str, target: str, feedback_id: str = "feedback") -> dict[str, object]:
    return {
        "feedback_id": feedback_id,
        "source_effect": _typed("effect", source),
        "target_protocol": _typed("protocol", target),
        "event": "effect_resolved",
        "operation": "enables",
    }


def test_protocol_surface_reproduces_all_nineteen_frozen_oracles() -> None:
    fixture = _load()
    inputs = _case_inputs()
    assert len(inputs) == 19
    for case in fixture["cases"]:
        payload, context = inputs[case["id"]]
        report = evaluate(parse_candidate(payload), context)
        expected = case["expected"]
        assert report.outcome == expected["outcome"], case["id"]
        if expected["primary"]:
            assert report.findings[0].code == expected["primary"], case["id"]
        else:
            assert not report.findings, case["id"]


def test_shape_contract_rejects_implements_bare_refs_and_prose_event() -> None:
    payload, _ = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][0]["implements"] = ["req_echo"]
    with pytest.raises(CandidateShapeError):
        parse_candidate(payload)

    payload, _ = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][0]["causes"][0]["object_ref"] = "bare_id"
    with pytest.raises(CandidateShapeError):
        parse_candidate(payload)

    payload, _ = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][0]["when"]["event"] = "after an ally finishes an action"
    with pytest.raises(CandidateShapeError):
        parse_candidate(payload)


def test_implements_only_self_declaration_cannot_claim_content_mechanic() -> None:
    payload, context = _case_inputs()["skill_s0_13_requested_mechanic_missing"]
    payload["entries"][0]["protocols"][0]["implements"] = ["req_echo"]
    with pytest.raises(CandidateShapeError):
        parse_candidate(payload)


@pytest.mark.parametrize("relation", [
    _feedback("echo/trigger/apply", "echo/trigger", "self_loop"),
    _feedback("echo/support/support", "echo/feedback", "unrelated"),
])
def test_self_or_unrelated_feedback_relation_is_invalid(relation: dict[str, object]) -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["feedback_relations"] = [relation]
    report = evaluate(parse_candidate(payload), context)
    assert report.outcome == "FAIL"
    assert "FEEDBACK_RELATION_INVALID" in report.finding_codes
    assert "REQUESTED_MECHANIC_UNREPRESENTED" in report.finding_codes


def test_empty_feedback_target_is_repairable_when_core_skeleton_survives() -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][1]["causes"] = []
    payload["feedback_relations"] = [_feedback("echo/trigger/apply", "echo/feedback")]

    target = payload["entries"][0]["protocols"][1]
    assert target["when"]["event"] == "feedback_received"
    assert target["when"]["source_ref"] == _typed("effect", "echo/trigger/apply")
    assert target["causes"] == []

    without_feedback = copy.deepcopy(payload)
    without_feedback["feedback_relations"] = []
    core_report = evaluate(parse_candidate(without_feedback), context)
    assert core_report.outcome == "REPAIR"
    assert "MECHANIC_SKELETON_ABSENT" not in core_report.finding_codes

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "REPAIR"
    assert "FEEDBACK_RELATION_INVALID" in report.finding_codes
    assert "MECHANIC_SKELETON_ABSENT" not in report.finding_codes


def test_empty_feedback_target_stays_fail_when_feedback_is_the_required_skeleton() -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][1]["causes"] = []
    payload["feedback_relations"] = [_feedback("echo/trigger/apply", "echo/feedback")]
    requirement = context["intent"]["mechanic_requirements"][0]
    requirement["trigger"] = {
        "subject_kinds": ["self"],
        "events": ["feedback_received"],
        "source_kinds": ["effect"],
    }
    requirement["effect"] = {
        "subject_kinds": ["self"],
        "operations": ["ally_enablement"],
        "object_kinds": [],
    }

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "FAIL"
    assert "MECHANIC_SKELETON_ABSENT" in report.finding_codes
    assert "FEEDBACK_RELATION_INVALID" in report.finding_codes


def test_summon_subject_without_live_entity_ref_fails_closed() -> None:
    payload, context = _case_inputs()["skill_s0_18_control_near_neighbor_pass"]
    payload["entries"][0]["protocols"][2]["when"]["subject"]["entity_ref"] = None

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "FAIL"
    assert "REFERENCE_DANGLING" in report.finding_codes


def test_feedback_relation_without_mechanic_requirement_is_invalid() -> None:
    payload, _ = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    _, context = _case_inputs()["skill_s0_01_resource_loop_complete"]
    payload["feedback_relations"] = [_feedback("echo/trigger/apply", "echo/feedback")]

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "FAIL"
    assert report.finding_codes == ("FEEDBACK_RELATION_INVALID",)


def test_unrelated_second_ability_does_not_make_resource_loop_multi_skill() -> None:
    payload, context = _case_inputs()["skill_s0_02_resource_loop_incomplete"]
    payload["entries"].append(
        {
            "ability_id": "unrelated",
            "name": "Unrelated",
            "mode": "active",
            "display_text": "",
            "protocols": [
                {
                    "protocol_id": "plain",
                    "when": {
                        "subject": {"kind": "self", "selector": "owner", "entity_ref": None},
                        "event": "ability_invoked",
                        "source_ref": None,
                        "qualifier": None,
                    },
                    "causes": [
                        {
                            "effect_id": "plain",
                            "subject": {"kind": "self", "selector": "owner", "entity_ref": None},
                            "operation": "direct_output",
                            "object_ref": None,
                            "description": "",
                        }
                    ],
                }
            ],
        }
    )

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "REPAIR"
    assert "RESOURCE_LOOP_INCOMPLETE" in report.finding_codes
    assert "MULTI_SKILL_LOOP_INCOHERENT" not in report.finding_codes


def test_live_id_in_another_reference_namespace_is_kind_mismatch() -> None:
    payload, context = _case_inputs()["skill_s0_01_resource_loop_complete"]
    payload["entries"][0]["protocols"][0]["causes"][0]["object_ref"] = _typed("state", "mark")

    report = evaluate(parse_candidate(payload), context)

    assert report.outcome == "FAIL"
    assert "REFERENCE_KIND_MISMATCH" in report.finding_codes
    assert "REFERENCE_DANGLING" not in report.finding_codes


def test_dangling_lifecycle_reference_does_not_close_resource() -> None:
    payload, context = _case_inputs()["skill_s0_01_resource_loop_complete"]
    payload["resources"][0]["opened_by"] = [_typed("effect", "resource/missing/gain")]
    report = evaluate(parse_candidate(payload), context)
    assert "LIFECYCLE_REFERENCE_DANGLING" in report.finding_codes
    assert "RESOURCE_LOOP_INCOMPLETE" in report.finding_codes


def test_lifecycle_operation_mismatch_does_not_close_resource() -> None:
    payload, context = _case_inputs()["skill_s0_01_resource_loop_complete"]
    payload["resources"][0]["opened_by"] = [_typed("effect", "resource/use/spend")]
    report = evaluate(parse_candidate(payload), context)
    assert "LIFECYCLE_OPERATION_MISMATCH" in report.finding_codes
    assert "RESOURCE_LOOP_INCOMPLETE" in report.finding_codes


def test_prose_event_cannot_form_mechanic_skeleton() -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    payload["entries"][0]["protocols"][0]["when"]["event"] = None
    payload["entries"][0]["protocols"][0]["when"]["qualifier"] = "after an ally finishes an action"
    report = evaluate(parse_candidate(payload), context)
    assert report.outcome == "FAIL"
    assert "MECHANIC_SKELETON_ABSENT" in report.finding_codes
    assert "REQUESTED_MECHANIC_UNREPRESENTED" not in report.finding_codes


def test_wrong_effect_subject_cannot_satisfy_canonical_role() -> None:
    payload, context = _case_inputs()["skill_s0_18_control_near_neighbor_pass"]
    act = payload["entries"][0]["protocols"][1]["causes"][0]
    act["subject"] = {"kind": "ally", "selector": "ally", "entity_ref": None}
    report = evaluate(parse_candidate(payload), context)
    assert report.outcome == "FAIL"
    assert "ROLE_EFFECT_MISMATCH" in report.finding_codes


def test_patch_digest_cannot_replay_across_context_or_report() -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    candidate = parse_candidate(payload)
    report = evaluate(candidate, context)
    patch = {
        "candidate_digest": report.candidate_digest,
        "context_digest": report.context_digest,
        "report_digest": report.report_digest,
        "operations": [{
            "op": "add",
            "path": "/feedback_relations/-",
            "value": _feedback("echo/trigger/apply", "echo/feedback"),
        }],
    }
    replay_context = copy.deepcopy(context)
    replay_context["combat_role_profile"] = None
    with pytest.raises(PatchRejected):
        apply_patch(candidate, patch, report, replay_context)

    altered_report = evaluate(candidate, context)
    altered_report = altered_report.__class__(
        altered_report.outcome,
        altered_report.blocking,
        altered_report.repair_allowed,
        altered_report.findings,
        altered_report.candidate_digest,
        altered_report.context_digest,
        "0" * 64,
    )
    with pytest.raises(PatchRejected):
        apply_patch(candidate, patch, altered_report, context)


def test_authorized_feedback_patch_improves_case_19() -> None:
    payload, context = _case_inputs()["skill_s0_19_requested_mechanic_near_neighbor_repair"]
    candidate = parse_candidate(payload)
    report = evaluate(candidate, context)
    patched = apply_patch(
        candidate,
        {
            "candidate_digest": report.candidate_digest,
            "context_digest": report.context_digest,
            "report_digest": report.report_digest,
            "operations": [{"op": "add", "path": "/feedback_relations/-", "value": _feedback("echo/trigger/apply", "echo/feedback")}],
        },
        report,
        context,
    )
    assert patched.outcome == "PASS"
    assert patched.findings == ()


def test_external_structural_fingerprint_copy_detected_after_renaming() -> None:
    payload, context = _case_inputs()["skill_s0_15_reference_copying"]
    original = parse_candidate(payload)
    report = evaluate(original, context)
    assert report.outcome == "FAIL"
    assert "REFERENCE_COPYING" in report.finding_codes

    renamed = copy.deepcopy(payload)

    def rename(value: object, key: str | None = None) -> object:
        if isinstance(value, dict):
            return {name: rename(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [rename(item, key) for item in value]
        if isinstance(value, str) and key in {"ability_id", "protocol_id", "effect_id", "resource_id", "state_id", "summon_id", "id"}:
            return value.replace("control", "ward").replace("field", "zone")
        return value

    renamed_candidate = parse_candidate(rename(renamed))
    renamed_report = evaluate(renamed_candidate, context)
    assert renamed_report.outcome == "FAIL"
    assert "REFERENCE_COPYING" in renamed_report.finding_codes


def test_finding_accumulation_keeps_independent_lower_priority_defects() -> None:
    payload, context = _case_inputs()["skill_s0_04_state_exit_missing"]
    context["combat_role_profile"] = {"primary_role": "support", "secondary_roles": []}
    report = evaluate(parse_candidate(payload), context)
    assert report.finding_codes == ("STATE_EXIT_MISSING", "ROLE_EFFECT_MISMATCH")
    assert report.outcome == "FAIL"


def test_b15_taxonomy_remains_fail_closed() -> None:
    payload, context = _case_inputs()["skill_s0_14_cross_taxonomy_role"]
    report = evaluate(parse_candidate(payload), context)
    assert report.outcome == "FAIL"
    assert report.finding_codes == ("CROSS_TAXONOMY_ROLE_LABEL",)


def test_legacy_ability_concept_is_explicitly_non_pass() -> None:
    candidate = parse_candidate({"ability_concept": "旧能力文案"})
    _, context = _case_inputs()["skill_s0_01_resource_loop_complete"]
    report = evaluate(candidate, context)
    assert report.outcome == "LEGACY_UNVERIFIED"
    assert report.finding_codes == ("LEGACY_SKILL_KIT_UNVERIFIED",)
    assert render_ability_concept(candidate) == "旧能力文案"


def test_legacy_candidate_accumulates_noncanonical_role_taxonomy_failure() -> None:
    candidate = parse_candidate({"ability_concept": "旧能力文案"})
    _, context = _case_inputs()["skill_s0_14_cross_taxonomy_role"]
    report = evaluate(candidate, context)
    assert report.outcome == "FAIL"
    assert report.finding_codes == (
        "CROSS_TAXONOMY_ROLE_LABEL",
        "LEGACY_SKILL_KIT_UNVERIFIED",
    )


def test_reference_review_digest_must_be_lowercase_sha256() -> None:
    _, context = _case_inputs()["skill_s0_15_reference_copying"]
    context["reference_review_context"]["corpus_digest"] = "short"
    with pytest.raises(CandidateShapeError):
        evaluate(parse_candidate(_case_inputs()["skill_s0_15_reference_copying"][0]), context)

    _, context = _case_inputs()["skill_s0_15_reference_copying"]
    context["reference_review_context"]["structural_fingerprints"][0]["sha256"] = "not-a-digest"
    with pytest.raises(CandidateShapeError):
        evaluate(parse_candidate(_case_inputs()["skill_s0_15_reference_copying"][0]), context)


def test_renderer_is_deterministic_and_one_way() -> None:
    payload, _ = _case_inputs()["skill_s0_18_control_near_neighbor_pass"]
    candidate = parse_candidate(payload)
    assert render_ability_concept(candidate) == render_ability_concept(candidate)
    assert render_ability_concept(candidate).strip()
    assert not hasattr(candidate, "ability_concept")


def test_no_balance_or_generic_parameter_fields_in_public_fixture() -> None:
    serialized = PUBLIC_FIXTURE.read_text(encoding="utf-8").casefold()
    for forbidden in ("damage_multiplier", "frame_count", "exact_cooldown", "crit_rate", "attack_power", '"parameters"'):
        assert forbidden not in serialized


def test_public_blind_fixture_contains_no_oracle_answers_or_semantic_refs() -> None:
    payload = json.loads(PUBLIC_FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "character-skill-interface-blind-review-input/0.1.1"
    assert [case["case_id"] for case in payload["cases"]] == [
        f"case_{index:02d}" for index in range(1, 20)
    ]

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not {"expected", "outcome", "primary", "candidate_ref", "context_ref"} & keys(payload)
