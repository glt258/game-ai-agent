from __future__ import annotations

import copy
import json

import pytest

from agents.models import ModelInvocationAudit, ModelTurn
from agents.response_contracts import character_skill_kit_prompt_contract
from character_skill import SkillKitShapeError, parse_candidate
from evals import character_skill_s2_shadow_evidence as evidence
from tests.historical_fixtures import historical_fixture_path

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


def _error(payload: object) -> SkillKitShapeError:
    with pytest.raises(SkillKitShapeError) as captured:
        parse_candidate(payload)  # type: ignore[arg-type]
    assert captured.value.diagnostic is not None
    return captured.value


def test_valid_candidate_acceptance_is_unchanged() -> None:
    candidate = parse_candidate(EMPTY_CANDIDATE)
    assert candidate.to_mapping() == EMPTY_CANDIDATE


def test_model_facing_contract_projection_is_explicit_and_schema_derived() -> None:
    contract = character_skill_kit_prompt_contract()
    for field in (
        "schema_version",
        "display_summary",
        "entries",
        "feedback_relations",
        "resources",
        "role_evidence",
        "states",
        "summons",
    ):
        assert f"- {field}" in contract
    assert "Do not add any other root keys." in contract
    assert "Do not wrap the object in candidate, result, data" in contract
    assert "Do not return prose, Markdown, code fences, explanations, or reasoning" in contract
    assert "mode" in contract and "active" in contract and "passive" in contract
    assert "entries: array of ability objects" in contract
    assert "protocols" in contract and "causes" in contract


def test_wrong_root_type_is_content_free() -> None:
    error = _error([])
    diagnostic = error.diagnostic.to_dict()
    assert error.code == "TYPE_MISMATCH"
    assert diagnostic["parsed_top_level_type"] == "array"
    assert diagnostic["expected_top_level_type"] == "object"
    assert diagnostic["key_count"] is None
    assert diagnostic["parser_error_code"] == "INVALID_TOP_LEVEL_TYPE"


def test_multiple_missing_fields_are_bounded_and_deterministic() -> None:
    payload = {"schema_version": EMPTY_CANDIDATE["schema_version"]}
    first = _error(payload).diagnostic.to_dict()
    second = _error(payload).diagnostic.to_dict()
    assert first == second
    assert first["parser_error_code"] == "MISSING_REQUIRED_FIELD"
    assert first["missing_required_count"] == 7
    assert first["missing_required_fields"] == sorted(first["missing_required_fields"])
    assert set(first["missing_required_fields"]).issubset(EMPTY_CANDIDATE)


def test_unknown_secret_field_only_emits_count() -> None:
    payload = copy.deepcopy(EMPTY_CANDIDATE)
    payload["super_secret_api_key"] = "sk-FAKE_SECRET_SHOULD_NOT_LEAK"
    error = _error(payload)
    serialized = json.dumps(error.diagnostic.to_dict(), sort_keys=True)
    assert error.diagnostic.unknown_key_count == 1
    assert "super_secret_api_key" not in serialized
    assert "sk-FAKE_SECRET_SHOULD_NOT_LEAK" not in serialized
    assert "bearer" not in serialized.lower()


def test_invalid_enum_has_fixed_code_and_no_raw_value() -> None:
    payload = copy.deepcopy(EMPTY_CANDIDATE)
    payload["entries"] = [
        {
            "ability_id": "echo",
            "name": "Echo",
            "mode": "forbidden-mode",
            "protocols": [],
            "display_text": "",
        }
    ]
    error = _error(payload)
    serialized = json.dumps(error.diagnostic.to_dict(), sort_keys=True)
    assert error.diagnostic.parser_error_code == "INVALID_ENUM"
    assert "forbidden-mode" not in serialized


def test_nested_shape_and_wrapper_metadata_do_not_change_rejection() -> None:
    nested = copy.deepcopy(EMPTY_CANDIDATE)
    nested["entries"] = []
    nested["resources"] = [None]
    nested_error = _error(nested)
    assert nested_error.code == "TYPE_MISMATCH"
    assert nested_error.diagnostic.parser_error_code == "INVALID_NESTED_SHAPE"

    wrapper_error = _error({"candidate": copy.deepcopy(EMPTY_CANDIDATE)})
    assert wrapper_error.code == "UNKNOWN_FIELD"
    assert wrapper_error.diagnostic.wrapper_detected is True


def test_diagnostic_never_includes_raw_exception_text() -> None:
    error = SkillKitShapeError(
        "UNKNOWN_FIELD",
        "/api_key",
        "sk-FAKE_SECRET_SHOULD_NOT_LEAK full fake prompt model output",
    )
    diagnostic = error.attach_diagnostic(
        # Payload is deliberately content-free; no exception text is passed through.
        _error({"unexpected": "value"}).diagnostic
    ).diagnostic
    serialized = json.dumps(diagnostic.to_dict(), sort_keys=True)
    assert "sk-FAKE_SECRET_SHOULD_NOT_LEAK" not in serialized
    assert "full fake prompt" not in serialized


class _DiagnosticModel:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls = 0

    def generate(self, prompt: object) -> ModelTurn:
        del prompt
        self.calls += 1
        return ModelTurn(
            structured_output=self.payload,
            invocation=ModelInvocationAudit(
                session_id="diagnostic-session",
                turn_number=1,
                provider="opencode_go",
                model="deepseek-v4-flash",
                outcome="success",
                latency_ms=1.0,
                retry_count=0,
            ),
        )


def test_diagnostic_runner_dry_run_is_provider_free_and_targets_retry_case13() -> None:
    runner = evidence.ShapeDiagnosticCohortRunner()
    result = runner.run(
        source_path=historical_fixture_path(evidence.RETRY_RESULT_RELATIVE_PATH),
        live=False,
    )
    assert result["status"] == "dry_run_shape_diagnostic"
    assert result["case_ids"] == ["case_13"]
    assert result["provider_called"] is False
    assert result["provider_factory_constructed"] is False


def test_diagnostic_runner_emits_one_independent_lineage_record(tmp_path) -> None:
    runner = evidence.ShapeDiagnosticCohortRunner()
    model = _DiagnosticModel({"super_secret_api_key": "sk-FAKE_SECRET"})
    output = tmp_path / "diagnostic.json"
    bundle = runner.run(
        source_path=historical_fixture_path(evidence.RETRY_RESULT_RELATIVE_PATH),
        live=True,
        output_path=output,
        shadow_model=model,
        enforce_clean_tree=False,
    )
    assert model.calls == 1
    assert len(bundle["observations"]) == 1
    record = bundle["observations"][0]
    observation = record["observation"]
    assert observation["case_id"] == "case_13"
    assert observation["diagnoses_observation_id"] == bundle["diagnoses_observation_id"]
    diagnostic_text = json.dumps(observation["shape_diagnostic"], sort_keys=True)
    assert "super_secret_api_key" not in diagnostic_text
    assert "sk-FAKE_SECRET" not in diagnostic_text
    evidence.validate_shape_diagnostic_bundle(bundle)


def test_contract_compliance_runner_has_independent_baseline_lineage(tmp_path) -> None:
    runner = evidence.ContractComplianceCohortRunner()
    model = _DiagnosticModel(EMPTY_CANDIDATE)
    bundle = runner.run(
        source_path=historical_fixture_path(evidence.DIAGNOSTIC_RESULT_RELATIVE_PATH),
        live=True,
        output_path=tmp_path / "compliance.json",
        shadow_model=model,
        enforce_clean_tree=False,
    )
    assert model.calls == 1
    assert bundle["cohort_type"] == "contract_compliance"
    assert bundle["observations"][0]["observation"]["case_id"] == "case_13"
    assert bundle["observations"][0]["observation"]["baseline_observation_id"] == bundle["baseline_observation_id"]
    evidence.validate_contract_compliance_bundle(bundle)
