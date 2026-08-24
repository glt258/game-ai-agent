"""Public-seam tests for the structural SkillKit evaluator."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import character_skill
from character_skill import (
    LegacyAbilityConcept,
    SkillKitShapeError,
    evaluate,
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


EMPTY_CONTEXT = {
    "intent": {
        "mechanic_requirements": [],
        "forbidden_mechanic_families": [],
        "hard_constraint_conflicts": [],
    },
    "combat_role_profile": None,
    "reference_review_context": None,
}

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE = ROOT / "evals" / "fixtures" / "character_skill_interface_prototype_cases_v0.1.1.public.json"


def _case(case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    fixture = json.loads(PUBLIC_FIXTURE.read_text(encoding="utf-8"))
    row = next(item for item in fixture["cases"] if item["case_id"] == case_id)
    return copy.deepcopy(row["candidate"]), copy.deepcopy(row["context"])


def test_empty_candidate_passes_through_public_evaluator():
    candidate = parse_candidate(EMPTY_CANDIDATE)

    report = evaluate(candidate, EMPTY_CONTEXT)

    assert report.outcome == "PASS"
    assert report.finding_codes == ()


@pytest.mark.parametrize(
    ("case_id", "outcome", "primary"),
    [
        ("case_01", "PASS", None),
        ("case_02", "REPAIR", "RESOURCE_LOOP_INCOMPLETE"),
        ("case_04", "REPAIR", "STATE_EXIT_MISSING"),
        ("case_06", "REPAIR", "SUMMON_LIFECYCLE_INCOMPLETE"),
        ("case_17", "REPAIR", "MULTI_SKILL_LOOP_INCOHERENT"),
        ("case_18", "PASS", None),
    ],
)
def test_frozen_public_cases_cover_structural_subset(case_id, outcome, primary):
    candidate_payload, context_payload = _case(case_id)

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert report.outcome == outcome
    if primary is None:
        assert report.findings == ()
    else:
        assert report.finding_codes[0] == primary


def test_known_public_case_has_fixed_candidate_context_and_report_digests():
    candidate_payload, context_payload = _case("case_01")

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    # These literals are independent values recorded by the frozen prototype
    # contract, not values calculated by this implementation in the test.
    assert report.candidate_digest == "5090c635d1d94df2a82384d5a79432317807f0b6a751c19f450a9a6c0886a09a"
    assert report.context_digest == "484cf36660bea0ecc2c1436475c5cc6df16cb111beff1ad9915b5927997a0e30"
    assert report.report_digest == "7b47fc43823ceb0a9be016cd724ae9e7c9ba5b9b0641d5ad299aea83b7898a6b"
    assert report.base_digest == report.candidate_digest


def test_unused_context_changes_context_and_report_digest_only():
    candidate_payload, context_payload = _case("case_01")
    altered_context = copy.deepcopy(context_payload)
    altered_context["combat_role_profile"] = {
        "primary_role": "support",
        "secondary_roles": [],
    }

    original = evaluate(parse_candidate(candidate_payload), context_payload)
    altered = evaluate(parse_candidate(candidate_payload), altered_context)

    assert altered.finding_codes == original.finding_codes
    assert altered.candidate_digest == original.candidate_digest
    assert altered.context_digest != original.context_digest
    assert altered.report_digest != original.report_digest


def test_general_reference_mismatch_and_dangling_paths_are_accumulated():
    candidate_payload, context_payload = _case("case_01")
    candidate_payload["entries"][0]["protocols"][0]["when"]["source_ref"] = {
        "kind": "protocol",
        "id": "resource/open",
    }
    candidate_payload["entries"][0]["protocols"][0]["causes"][0]["object_ref"] = {
        "kind": "state",
        "id": "ghost",
    }

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert report.outcome == "FAIL"
    assert ("REFERENCE_KIND_MISMATCH", "/entries/0/protocols/0/when/source_ref") in {
        (finding.code, finding.field_path) for finding in report.findings
    }
    assert ("REFERENCE_DANGLING", "/entries/0/protocols/0/causes/0/object_ref") in {
        (finding.code, finding.field_path) for finding in report.findings
    }


def test_summon_subject_requires_live_entity_reference():
    candidate_payload, context_payload = _case("case_18")
    candidate_payload["entries"][0]["protocols"][2]["when"]["subject"]["entity_ref"] = None

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert report.outcome == "FAIL"
    assert report.finding_codes == ("REFERENCE_DANGLING",)
    assert report.findings[0].field_path == "/entries/0/protocols/2/when/subject/entity_ref"


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        ({"kind": "resource", "id": "mark"}, "LIFECYCLE_REFERENCE_WRONG_KIND"),
        ({"kind": "effect", "id": "resource/missing/gain"}, "LIFECYCLE_REFERENCE_DANGLING"),
        ({"kind": "effect", "id": "resource/use/spend"}, "LIFECYCLE_OPERATION_MISMATCH"),
    ],
)
def test_lifecycle_slots_report_specific_invalid_member_and_remain_open(replacement, code):
    candidate_payload, context_payload = _case("case_01")
    candidate_payload["resources"][0]["opened_by"] = [replacement]

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert code in report.finding_codes
    assert "RESOURCE_LOOP_INCOMPLETE" in report.finding_codes
    assert report.outcome == "FAIL"


def test_independent_lifecycle_findings_accumulate_and_sort_deterministically():
    candidate_payload, context_payload = _case("case_04")
    candidate_payload["resources"] = [
        {
            "resource_id": "mark",
            "opened_by": [],
            "used_or_transformed_by": [],
            "closed_by": [],
        }
    ]

    first = evaluate(parse_candidate(candidate_payload), context_payload)
    second = evaluate(parse_candidate(candidate_payload), context_payload)

    assert first.finding_codes == (
        "RESOURCE_LOOP_INCOMPLETE",
        "STATE_EXIT_MISSING",
    )
    assert first.to_mapping() == second.to_mapping()


def test_multi_skill_resource_finding_requires_two_targeting_abilities():
    candidate_payload, context_payload = _case("case_02")
    second_ability = copy.deepcopy(candidate_payload["entries"][0])
    second_ability["ability_id"] = "other"
    second_ability["protocols"][0]["protocol_id"] = "use"
    second_ability["protocols"][0]["causes"][0]["effect_id"] = "spend"
    candidate_payload["entries"].append(second_ability)

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert report.finding_codes == ("MULTI_SKILL_LOOP_INCOHERENT",)


def test_summon_repeat_rule_requires_replacement_when_repeat_policy_is_null():
    candidate_payload, context_payload = _case("case_18")
    candidate_payload["summons"][0]["repeat_policy"] = None

    report = evaluate(parse_candidate(candidate_payload), context_payload)

    assert report.outcome == "PASS"
    assert report.findings == ()

    candidate_payload["entries"][0]["protocols"][3]["causes"][0]["operation"] = "summon_exit"
    report_without_replace = evaluate(parse_candidate(candidate_payload), context_payload)
    assert report_without_replace.finding_codes == ("SUMMON_LIFECYCLE_INCOMPLETE",)


def test_shape_context_errors_are_exceptions_not_findings():
    candidate_payload, context_payload = _case("case_01")
    malformed_context = copy.deepcopy(context_payload)
    malformed_context["intent"]["unexpected"] = True

    with pytest.raises(SkillKitShapeError) as exc_info:
        evaluate(parse_candidate(candidate_payload), malformed_context)

    assert exc_info.value.code == "UNKNOWN_FIELD"
    assert exc_info.value.field_path == "/intent/unexpected"


def test_evaluate_rejects_unparsed_mappings_and_legacy_display_values():
    with pytest.raises(TypeError, match="ProtocolSkillKitCandidate"):
        evaluate(EMPTY_CANDIDATE, EMPTY_CONTEXT)
    with pytest.raises(TypeError, match="ProtocolSkillKitCandidate"):
        evaluate(LegacyAbilityConcept("legacy"), EMPTY_CONTEXT)


def test_public_exports_include_structural_surface_but_not_private_graph():
    expected = {
        "evaluate",
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
    }

    assert expected <= set(character_skill.__all__)
    assert "_graph" not in character_skill.__all__
