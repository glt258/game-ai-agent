from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agents import (
    CanonCheckStatus,
    CanonChecker,
    CharacterDesignRequest,
    CharacterDraft,
    CharacterGenerationAudit,
    CharacterGenerationResult,
    CharacterRepairAgent,
    DeterministicCharacterRepairModel,
)
from agents.official_character_authoring import (
    OfficialCharacterAuthoringDemo,
    _request_for_scenario,
    load_reference_grounding,
    make_demo,
    render,
    request_from_inputs,
)


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def test_valid_brief_runs_real_pipeline_and_passes() -> None:
    request = _request_for_scenario("valid")
    demo = make_demo(mode="offline", scenario="valid", brief=request.brief)

    run = demo.run(request)

    assert run.authoring.final_status == CanonCheckStatus.PASS
    assert run.authoring.initial_check.status == CanonCheckStatus.PASS
    assert not run.authoring.repair_result.repair_attempted
    assert run.references.total_records == 10
    assert run.generation.audit.reference_ids == run.references.reference_ids
    assert run.generation.audit.source_ids
    assert demo.generation_agent.model.prompts[0].runtime.reference_context


def test_conflicting_brief_hits_real_checker_and_repair_passes() -> None:
    request = _request_for_scenario("conflict")
    demo = make_demo(mode="offline", scenario="canon_conflict", brief=request.brief)

    run = demo.run(request)

    codes = {item.code.value for item in run.authoring.initial_check.findings}
    assert run.authoring.initial_check.status == CanonCheckStatus.FAIL
    assert "FORBIDDEN_PATTERN" in codes
    assert "WORLD_RULE_VIOLATION" in codes
    assert run.authoring.repair_result.repair_attempted
    assert run.authoring.repair_result.repair_succeeded
    assert run.authoring.final_check.status == CanonCheckStatus.PASS
    assert demo.repair_agent.model.call_count == 1


def test_demo_does_not_turn_a_failed_checker_result_into_pass() -> None:
    payload = json.loads((FIXTURES / "canon_checker_bad.json").read_text(encoding="utf-8"))
    draft = CharacterDraft.from_mapping(payload["draft"])
    request = replace(
        CharacterDesignRequest(**payload["request"]),
        request_id="official_failure_001",
    )

    class StaticGenerationAgent:
        def generate(self, _request):
            return CharacterGenerationResult(
                draft,
                (),
                CharacterGenerationAudit(draft.draft_id, 0, (), ()),
            )

    checker = CanonChecker()
    demo = OfficialCharacterAuthoringDemo(
        generation_agent=StaticGenerationAgent(),
        repair_agent=CharacterRepairAgent(
            DeterministicCharacterRepairModel(mode="regression"),
            checker=checker,
        ),
        checker=checker,
        reference_grounding=load_reference_grounding(request.brief),
    )

    run = demo.run(request)

    assert run.authoring.initial_check.status == CanonCheckStatus.FAIL
    assert run.authoring.final_check.status == CanonCheckStatus.FAIL
    assert run.authoring.final_status == CanonCheckStatus.FAIL


def test_scope_violation_is_not_presented_as_applied_or_accepted() -> None:
    payload = json.loads((FIXTURES / "canon_checker_bad.json").read_text(encoding="utf-8"))
    draft = CharacterDraft.from_mapping(payload["draft"])
    request = replace(
        CharacterDesignRequest(**payload["request"]),
        request_id="official_scope_001",
    )

    class StaticGenerationAgent:
        def generate(self, _request):
            return CharacterGenerationResult(
                draft,
                (),
                CharacterGenerationAudit(draft.draft_id, 0, (), ()),
            )

    checker = CanonChecker()
    demo = OfficialCharacterAuthoringDemo(
        generation_agent=StaticGenerationAgent(),
        repair_agent=CharacterRepairAgent(
            DeterministicCharacterRepairModel(mode="scope_violation"),
            checker=checker,
        ),
        checker=checker,
        reference_grounding=load_reference_grounding(request.brief),
    )
    run = demo.run(request)
    output = render(run, scenario="scope-test", model_mode="offline")

    assert run.authoring.repair_result.status.value == "REPAIR_SCOPE_VIOLATION"
    assert "Status: NOT APPLIED" in output
    assert "FINAL: NEEDS_REVIEW" in output
    assert "Status: APPLIED" not in output
    assert "Final status: ACCEPTED" not in output


def test_accepted_always_implies_final_canon_pass() -> None:
    for scenario, generation_scenario in (("valid", "valid"), ("conflict", "canon_conflict")):
        request = _request_for_scenario(scenario)
        run = make_demo(
            mode="offline",
            scenario=generation_scenario,
            brief=request.brief,
        ).run(request)
        if run.authoring.final_status == CanonCheckStatus.PASS:
            assert run.authoring.final_check.status == CanonCheckStatus.PASS


def test_custom_brief_uses_the_same_authoring_pipeline() -> None:
    brief = "设计一个与临洲大学有关的都市辅助角色。"
    request, presentation_scenario, generation_scenario = request_from_inputs(brief=brief)
    run = make_demo(
        mode="offline",
        scenario=generation_scenario,
        brief=request.brief,
    ).run(request)

    assert presentation_scenario == "custom"
    assert run.request.brief == brief
    assert run.generation.draft.draft_id == "draft_official_custom_001"
    assert run.generation.audit.source_ids


def test_brief_file_content_enters_request(tmp_path: Path) -> None:
    brief = "设计一个带有明显都市生活感的辅助角色。\n不要改变世界观。"
    path = tmp_path / "brief.txt"
    path.write_text(brief, encoding="utf-8")

    request, presentation_scenario, _ = request_from_inputs(brief_file=str(path))

    assert presentation_scenario == "custom"
    assert request.brief == brief


def test_cli_input_is_mutually_exclusive() -> None:
    from agents.official_character_authoring import main

    with pytest.raises(SystemExit):
        main(["--scenario", "valid", "--brief", "另一个 brief"])


def test_reference_labels_and_pass_summary_are_derived_from_real_data() -> None:
    request = _request_for_scenario("valid")
    run = make_demo(mode="offline", scenario="valid", brief=request.brief).run(request)
    output = render(run, scenario="valid", model_mode="offline")

    labels = dict(run.source_labels)
    assert labels["world_rules"] == "World Rules (world_rules)"
    assert any("(faction_" in value for value in labels.values())
    assert "No forbidden world-pattern violations detected." in output
    assert "Referenced faction resolved successfully." in output
    assert "field-level causal attribution" in output


def test_audit_summary_keeps_reference_and_canon_evidence() -> None:
    request = _request_for_scenario("valid")
    run = make_demo(mode="offline", scenario="valid", brief=request.brief).run(request)

    payload = run.to_dict()

    assert payload["references"]["total_records"] == 10
    assert payload["generation"]["audit"]["reference_ids"]
    assert payload["generation"]["audit"]["source_ids"]
    assert "chain_of_thought" not in json.dumps(payload, ensure_ascii=False)
