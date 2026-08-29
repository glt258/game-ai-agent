"""Offline four-family generalization proof for the Hybrid Semantic IR path."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from character_intelligence.hybrid_ir import (
    FORBIDDEN_MODEL_TOKENS,
    HYBRID_MULTI_CASE_EXPERIMENT,
    MODEL_FACING_SCHEMA_PATHS,
    FakeProvider,
    HybridSemanticIRRunner,
    build_authoritative_case_registry,
    build_authoritative_generalization_cases,
    build_model_facing_request,
    run_fake_pipeline,
    validate_model_facing_schema_surface,
)
from character_intelligence.semantic_ir import parse_semantic_ir

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "hybrid_multi_case_generalization_goldens.json"
COHORT_PURPOSE = "multi-case-generalization-pilot"


def _goldens() -> dict[str, dict[str, object]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _cases_by_id():
    return {case.case_id: case for case in build_authoritative_generalization_cases()}


def test_registry_has_four_distinct_authoritative_semantic_families() -> None:
    registry = build_authoritative_case_registry()
    cases = _cases_by_id()
    assert set(cases) <= set(registry)
    assert set(cases) == {
        "generalization_support_alternate_v1",
        "generalization_dps_v1",
        "generalization_control_v1",
        "generalization_reaction_heal_v1",
    }
    assert len({case.brief for case in cases.values()}) == 4
    assert {case.plan.combat_role_profile.primary_role for case in cases.values()} == {
        "support",
        "main_dps",
        "control",
        "healer",
    }
    assert {case.generation_mode for case in cases.values()} == {"active", "reaction"}


def test_generalization_contract_is_generic_and_case_projection_is_fair() -> None:
    requests = [build_model_facing_request(case.generation_context()) for case in _cases_by_id().values()]
    assert {request.contract.version for request in requests} == {
        "semantic-skill-plan-ir-contract/0.6.0"
    }
    assert len({request.contract.base_text for request in requests}) == 1
    assert len({request.contract.suffix_text for request in requests}) == 1
    # The generic guidance/version is shared, while the digest also binds the
    # fair per-case enum projection and therefore differs by case.
    assert len({request.contract.digest for request in requests}) == 4
    assert all(
        set(request.contract.projection.domain("intent").values)
        == {"control_enemy", "deal_damage", "enable_ally", "mitigate_ally"}
        for request in requests
    )
    assert all(
        "response_effect_family" not in request.contract.projection.to_mapping()
        for request in requests
    )
    assert all(
        "Continuation constraint:" in request.case_text
        for request in requests
    )
    assert all(
        all(
            path in request.contract.enum_text
            for paths in MODEL_FACING_SCHEMA_PATHS.values()
            for path in paths
        )
        for request in requests
    )
    assert len({request.metrics.total_chars for request in requests}) >= 2
    for request in requests:
        assert all(token not in request.text for token in FORBIDDEN_MODEL_TOKENS)
        assert "golden" not in request.text.lower()
        assert "expected" not in request.text.lower()
        assert "req_generalization" not in request.text
        assert "response_effect_family" not in request.text
        assert "allowed_response_effect_families" not in request.text
        validate_model_facing_schema_surface(request.contract.text)


def test_schema_surface_guard_rejects_pseudo_fields_and_accepts_real_paths() -> None:
    validate_model_facing_schema_surface("mechanic.trigger.event=[scene_entered]")
    with pytest.raises(ValueError, match="MODEL_FACING_NON_SCHEMA_FIELD"):
        validate_model_facing_schema_surface("response_effect_family=[damage]")


def test_context_digests_and_requests_are_deterministic_and_case_bound() -> None:
    cases = tuple(_cases_by_id().values())
    digests = [case.generation_context().context_projection_digest for case in cases]
    assert len(set(digests)) == len(digests)
    for case in cases:
        first = build_model_facing_request(case.generation_context())
        second = build_model_facing_request(case.generation_context())
        assert first.text == second.text
        assert first.contract.digest == second.contract.digest
        assert first.metrics.to_mapping() == second.metrics.to_mapping()


def test_hand_authored_goldens_pass_validator_compiler_parser_refs_and_evaluator() -> None:
    cases = _cases_by_id()
    goldens = _goldens()
    assert set(goldens) == set(cases)
    for case_id, case in cases.items():
        response = goldens[case_id]
        parse_semantic_ir(response)
        result = run_fake_pipeline(
            FakeProvider(response),
            case.generation_context(),
            case.evaluation_context(),
            repo_root=ROOT,
        )
        evidence = result.evidence
        assert evidence.first_failure_layer is None
        assert evidence.parser_invoked is True
        assert evidence.evaluator_invoked is True
        assert evidence.evaluator_outcome == "PASS"
        assert evidence.principal_verdict == "PASS"
        assert result.report is not None and result.report.outcome == "PASS"
        assert result.candidate is not None


def test_formal_run_live_fake_pipeline_passes_each_case_without_real_provider(tmp_path) -> None:
    cases = _cases_by_id()
    goldens = _goldens()
    run_ids: set[str] = set()
    for case_id, case in cases.items():
        runner = HybridSemanticIRRunner(
            ROOT,
            case.generation_context(),
            experiment=HYBRID_MULTI_CASE_EXPERIMENT,
            cohort_purpose=COHORT_PURPOSE,
        )
        dry = runner.dry_run()
        assert dry["target_sample_count"] == 1
        assert dry["existing_sample_count"] == 0
        assert dry["next_sample_index"] == 1
        assert dry["remaining_sample_count"] == 1
        assert dry["complete"] is False
        result = runner.run_live(
            case.evaluation_context(),
            provider_factory=lambda response=goldens[case_id]: FakeProvider(response),
            output_path=tmp_path / f"{case_id}.json",
            enforce_clean_tree=False,
        )
        assert result.status == "HYBRID_SEMANTIC_IR_END_TO_END_PASS"
        assert result.evidence is not None
        assert result.evidence.identity.experiment == HYBRID_MULTI_CASE_EXPERIMENT
        assert result.evidence.sample_index == 1
        run_ids.add(result.evidence.run_id)
    assert len(run_ids) == 4


def test_negative_semantic_variants_are_rejected_by_evaluator() -> None:
    cases = _cases_by_id()
    goldens = _goldens()
    defects = {
        "generalization_support_alternate_v1": ("mechanic", "relation", "enables"),
            "generalization_dps_v1": (
                "role_path",
                "effect",
                {"actor": "ally", "intent": "enable_ally", "description": "Wrong role duty."},
            ),
        "generalization_control_v1": ("mechanic", "effect", {"actor": "enemy", "intent": "deal_damage", "description": "Wrong duty."}),
        "generalization_reaction_heal_v1": ("mechanic", "trigger", {"actor": "ally", "event": "ability_invoked", "qualifier": None}),
    }
    for case_id, (section, field, value) in defects.items():
        payload = copy.deepcopy(goldens[case_id])
        if section == "role":
            payload["role"] = value
        elif section == "mechanic" and field == "relation":
            payload["mechanic"]["feedback"][field] = value
        else:
            payload[section][field] = value
        result = run_fake_pipeline(
            FakeProvider(payload),
            cases[case_id].generation_context(),
            cases[case_id].evaluation_context(),
            repo_root=ROOT,
        )
        assert result.evidence.evaluator_invoked is True
        assert result.evidence.evaluator_outcome == "FAIL"
        assert result.evidence.principal_verdict == "EVALUATOR_FAIL"


def test_authoritative_mode_requirements_reject_wrong_modes() -> None:
    cases = _cases_by_id()
    goldens = _goldens()
    wrong_modes = {
        "generalization_control_v1": "passive",
        "generalization_reaction_heal_v1": "active",
    }
    for case_id, wrong_mode in wrong_modes.items():
        payload = copy.deepcopy(goldens[case_id])
        payload["mode"] = wrong_mode
        result = run_fake_pipeline(
            FakeProvider(payload),
            cases[case_id].generation_context(),
            cases[case_id].evaluation_context(),
            repo_root=ROOT,
        )
        assert result.evidence.evaluator_outcome == "FAIL"
        assert any(
            finding.code == "MECHANIC_MODE_MISMATCH"
            for finding in result.report.findings
        )


def test_continuation_family_requirements_reject_semantic_drift() -> None:
    cases = _cases_by_id()
    goldens = _goldens()
    wrong_intents = {
        "generalization_support_alternate_v1": "deal_damage",
        "generalization_dps_v1": "enable_ally",
        "generalization_control_v1": "deal_damage",
        "generalization_reaction_heal_v1": "enable_ally",
    }
    for case_id, wrong_intent in wrong_intents.items():
        payload = copy.deepcopy(goldens[case_id])
        payload["mechanic"]["feedback"]["response_effect"]["intent"] = wrong_intent
        result = run_fake_pipeline(
            FakeProvider(payload),
            cases[case_id].generation_context(),
            cases[case_id].evaluation_context(),
            repo_root=ROOT,
        )
        assert result.evidence.evaluator_outcome == "FAIL"
        assert any(
            finding.code == "CONTINUATION_FAMILY_MISMATCH"
            for finding in result.report.findings
        )
