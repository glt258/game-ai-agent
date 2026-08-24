from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agents import CharacterDesignRequest, CharacterGenerationAudit, CharacterGenerationResult, CharacterDraft
from agents.evaluation import (
    EvaluationContext,
    EvaluationRunner,
    EvaluationSubject,
    RepresentationCompletenessValidator,
    RequestAlignmentValidator,
)
from agents.models import CharacterSkillShadowResult
from character_skill import SkillKitShapeError, SkillValidationContext, evaluate, parse_candidate


def _draft():
    return {
            "draft_id": "draft_skill_alignment",
            "status": "draft",
            "name": "Alignment",
            "canonical_character_id": None,
            "age": None,
            "age_range": None,
            "gender": None,
            "faction_id": None,
            "occupation": "occupation",
            "social_role": "role",
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
            "design_pitch": "pitch",
            "personality": ["calm"],
            "background": "background",
            "story_hook": "hook",
            "relationships": [],
            "ability_concept": "legacy ability concept",
            "knowledge_scope": "public",
            "canon_basis": [],
            "new_design_elements": [],
            "open_questions": [],
            "constraint_notes": [],
            "story_link": None,
            "proposed_new_content": [],
    }


def _fixture_case(case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    fixture = json.loads(
        Path(
            "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json"
        ).read_text(encoding="utf-8")
    )
    case = next(item for item in fixture["cases"] if item["case_id"] == case_id)
    return copy.deepcopy(case["candidate"]), copy.deepcopy(case["context"])


def _subject(*, candidate=None, skill_context=None, primary_role: str = "support", report=None):
    request = CharacterDesignRequest("design a support character", request_id="skill_alignment")
    draft_payload = _draft()
    draft_payload["combat_role_profile"] = {
        "primary_role": primary_role,
        "secondary_roles": [],
    }
    draft = CharacterDraft.from_mapping(draft_payload)
    if candidate is None:
        candidate = {
            "schema_version": "skill-kit-candidate/0.1.1",
            "entries": [],
            "feedback_relations": [],
            "resources": [],
            "states": [],
            "summons": [],
            "role_evidence": [],
            "display_summary": "",
        }
    candidate = parse_candidate(candidate)
    generation = CharacterGenerationResult(
        draft=draft,
        sources=(),
        audit=CharacterGenerationAudit(
            request_id=request.request_id,
            tool_rounds=0,
            tool_calls=(),
            source_ids=(),
        ),
        skill_shadow=CharacterSkillShadowResult(
            draft_id=draft.draft_id,
            response_compliant=True,
            candidate=candidate,
            validation_report=report,
        ),
    )
    return EvaluationSubject(
        request=request,
        generation_result=generation,
        skill_validation_context=skill_context,
    )


def test_skill_context_hard_conflict_is_visible_through_evaluation_runner():
    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(
            skill_context={
                "intent": {
                    "mechanic_requirements": [],
                    "forbidden_mechanic_families": [],
                    "hard_constraint_conflicts": ["no-summons"],
                },
                "combat_role_profile": None,
                "reference_review_context": None,
            }
        )
    )

    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("HARD_CONSTRAINT_CONFLICT", "/context/intent/hard_constraint_conflicts")
    ]


def test_forbidden_resource_family_is_reported_at_the_resource_root():
    candidate, skill_context = _fixture_case("case_03")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context)
    )

    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("FORBIDDEN_RESOURCE_INTRODUCED", "/resources")
    ]


def test_ambiguous_ally_trigger_is_a_repairable_warning_at_the_when_object():
    candidate, skill_context = _fixture_case("case_05")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context)
    )

    assert [
        (finding.code, finding.field_path, finding.severity, finding.blocking)
        for finding in result.findings
    ] == [("TRIGGER_SUBJECT_AMBIGUOUS", "/entries/0/protocols/0/when", "WARNING", False)]


@pytest.mark.parametrize(
    ("case_id", "role"),
    [
        ("case_07", "main_dps"),
        ("case_08", "sub_dps"),
        ("case_09", "support"),
        ("case_10", "healer"),
        ("case_11", "control"),
        ("case_12", "defense"),
    ],
)
def test_role_profile_without_matching_core_effect_is_a_blocking_alignment_finding(case_id, role):
    candidate, skill_context = _fixture_case(case_id)

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context, primary_role=role)
    )

    assert [
        (finding.code, finding.field_path, finding.severity, finding.blocking)
        for finding in result.findings
    ] == [("ROLE_EFFECT_MISMATCH", "/role_evidence", "ERROR", True)]


def test_complete_structural_role_evidence_adds_no_alignment_finding():
    candidate, skill_context = _fixture_case("case_18")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context, primary_role="control")
    )

    assert result.findings == ()


def test_named_mechanic_without_a_causal_skeleton_is_blocking():
    candidate, skill_context = _fixture_case("case_13")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context, primary_role="support")
    )

    assert [
        (finding.code, finding.field_path, finding.severity, finding.blocking)
        for finding in result.findings
    ] == [("MECHANIC_SKELETON_ABSENT", "/entries", "ERROR", True)]


def test_causal_skeleton_without_required_feedback_is_a_repairable_gap():
    candidate, skill_context = _fixture_case("case_19")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context, primary_role="support")
    )

    assert [
        (finding.code, finding.field_path, finding.severity, finding.blocking)
        for finding in result.findings
    ] == [
        ("REQUESTED_MECHANIC_UNREPRESENTED", "/feedback_relations/-", "WARNING", False)
    ]


def test_structural_shadow_finding_is_forwarded_without_changing_the_legacy_draft():
    candidate_payload, context_payload = _fixture_case("case_02")
    candidate = parse_candidate(candidate_payload)
    report = evaluate(candidate, SkillValidationContext.from_mapping(context_payload))
    subject = _subject(
        candidate=candidate_payload,
        skill_context=context_payload,
        report=report,
    )
    original_report = subject.generation_result.skill_shadow.validation_report

    result = EvaluationRunner([RepresentationCompletenessValidator()]).run(subject)

    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("RESOURCE_LOOP_INCOMPLETE", "/resources/0")
    ]
    assert subject.generation_result is not None
    assert subject.generation_result.draft.ability_concept == "legacy ability concept"
    assert subject.generation_result.draft.status == "draft"
    assert subject.generation_result.skill_shadow.validation_report == original_report


def test_skill_validation_context_mapping_is_frozen_and_fail_closed():
    payload = {
        "intent": {
            "mechanic_requirements": [],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": None,
        "reference_review_context": None,
    }
    subject = _subject(candidate=None, skill_context=payload)
    payload["intent"]["hard_constraint_conflicts"].append("mutated-after-parse")

    context = EvaluationContext.from_subject(subject)

    assert context.skill_validation_context is not None
    assert context.skill_validation_context.intent.hard_constraint_conflicts == ()

    malformed = dict(payload)
    malformed["unexpected"] = True
    with pytest.raises(SkillKitShapeError):
        _subject(candidate=None, skill_context=malformed)


def test_case_16_hard_constraint_parity_uses_the_frozen_context_pointer():
    candidate, skill_context = _fixture_case("case_16")

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(candidate=candidate, skill_context=skill_context, primary_role="control")
    )

    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("HARD_CONSTRAINT_CONFLICT", "/context/intent/hard_constraint_conflicts")
    ]


def test_repeated_alignment_evidence_is_deduplicated_deterministically():
    requirement = {
        "requirement_id": "first",
        "trigger": {
            "subject_kinds": ["ally"],
            "events": ["action_completed"],
            "source_kinds": [],
        },
        "effect": {
            "subject_kinds": ["self"],
            "operations": ["ally_enablement"],
            "object_kinds": [],
        },
        "feedback": {
            "required": False,
            "events": [],
            "operations": [],
        },
    }
    second = dict(requirement)
    second["requirement_id"] = "second"
    context = {
        "intent": {
            "mechanic_requirements": [requirement, second],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": None,
        "reference_review_context": None,
    }

    result = EvaluationRunner([RequestAlignmentValidator()]).run(
        _subject(skill_context=context)
    )

    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("MECHANIC_SKELETON_ABSENT", "/entries")
    ]
