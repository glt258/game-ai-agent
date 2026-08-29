from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from agents.models import ModelInvocationAudit, ModelTurn
from evals import character_skill_s2_shadow_evidence as evidence
from tests.historical_fixtures import historical_fixture_path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = historical_fixture_path(evidence.COMPLIANCE_RESULT_RELATIVE_PATH)
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


class _FakeModel:
    def __init__(self, payload: object = EMPTY_CANDIDATE) -> None:
        self.payload = payload
        self.calls = 0

    def generate(self, prompt: object) -> ModelTurn:
        del prompt
        self.calls += 1
        return ModelTurn(
            structured_output=copy.deepcopy(self.payload),
            invocation=ModelInvocationAudit(
                session_id="fixed-cohort-test",
                turn_number=1,
                provider="opencode_go",
                model="deepseek-v4-flash",
                outcome="success",
                latency_ms=1.0,
                retry_count=0,
                transport="openai_chat_completions",
                response_contract="character_skill_kit",
            ),
        )


def _append(output: Path, model: _FakeModel, **kwargs: object) -> dict[str, object]:
    return evidence.FixedContractComplianceCohortRunner(ROOT).run(
        source_path=SOURCE,
        live=True,
        output_path=output,
        append_next_sample=True,
        shadow_model=model,
        enforce_clean_tree=False,
        **kwargs,
    )


def _cohort(output: Path, model: _FakeModel | None = None) -> dict[str, object]:
    return _append(output, model or _FakeModel())


def _refresh_digest(bundle: dict[str, object]) -> None:
    for item in bundle["observations"]:
        body = {
            "observation": item["observation"],
            "audit": item["audit"],
            "sanitization": item["sanitization"],
        }
        item["record_digest"] = evidence._record_digest(body)
    bundle["bundle_digest"] = evidence._fixed_compliance_bundle_digest(bundle)


def test_create_fixed_cohort_from_legacy_sample_preserves_sample_one(tmp_path: Path) -> None:
    source_before = SOURCE.read_bytes()
    output = tmp_path / "cohort.json"
    plan = evidence.FixedContractComplianceCohortRunner(ROOT).dry_run(source_path=SOURCE, output_path=output)
    assert plan["target_sample_count"] == 3
    assert plan["existing_sample_indexes"] == [1]
    assert plan["next_sample_index"] == 2
    assert SOURCE.read_bytes() == source_before

    bundle = _cohort(output)
    assert [record["sample_index"] for record in bundle["observations"]] == [1, 2]
    assert bundle["observations"][0]["observation"] == json.loads(SOURCE.read_text(encoding="utf-8"))["observations"][0]["observation"]
    evidence.validate_fixed_contract_compliance_bundle(bundle)
    assert SOURCE.read_bytes() == source_before


def test_append_sample_two_then_resume_sample_three_and_complete(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    first_model = _FakeModel()
    first = _cohort(output, first_model)
    assert first_model.calls == 1
    assert [item["sample_index"] for item in first["observations"]] == [1, 2]
    second_model = _FakeModel()
    second = _append(output, second_model, resume=True)
    assert second_model.calls == 1
    assert [item["sample_index"] for item in second["observations"]] == [1, 2, 3]
    assert second["complete"] is True
    evidence.validate_fixed_contract_compliance_bundle(second)


def test_complete_cohort_rejects_fourth_sample_before_provider(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    _cohort(output)
    _append(output, _FakeModel(), resume=True)
    forbidden = _FakeModel()
    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        _append(output, forbidden, resume=True)
    assert captured.value.code == "COHORT_ALREADY_COMPLETE"
    assert forbidden.calls == 0


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda b: b["observations"].append(copy.deepcopy(b["observations"][1])), "FIXED_COHORT_DUPLICATE_SAMPLE_INDEX"),
        (lambda b: (b["observations"].__setitem__(1, {**b["observations"][1], "sample_index": 3}), b["observations"][1]["observation"].update({"observation_id": b["run_id"] + ":case_13:sample-03"})), "FIXED_COHORT_SAMPLE_INDEX_GAP"),
        (lambda b: b["observations"][1]["sample_index"].__class__ and b["observations"][1]["observation"].update({"observation_id": "bad"}), "FIXED_COHORT_OBSERVATION_ID_INVALID"),
    ],
)
def test_invalid_indexes_and_ids_are_rejected(mutator, code: str, tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    bundle = _cohort(output)
    mutated = copy.deepcopy(bundle)
    mutator(mutated)
    _refresh_digest(mutated)
    with pytest.raises(evidence.EvidenceContractError) as captured:
        evidence.validate_fixed_contract_compliance_bundle(mutated)
    assert captured.value.code == code


def test_target_mutation_is_rejected_before_provider(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    _cohort(output)
    model = _FakeModel()
    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        _append(output, model, resume=True, target_sample_count=4)
    assert captured.value.code == "COHORT_TARGET_MISMATCH"
    assert model.calls == 0


def test_source_and_manifest_digest_mismatch_fail_before_provider(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["input_manifest_digest"] = "0" * 64
    source.write_text(json.dumps(payload), encoding="utf-8")
    model = _FakeModel()
    with pytest.raises(evidence.EvidenceRunnerError):
        evidence.FixedContractComplianceCohortRunner(ROOT).run(
            source_path=source,
            live=True,
            output_path=tmp_path / "cohort.json",
            append_next_sample=True,
            shadow_model=model,
            enforce_clean_tree=False,
        )
    assert model.calls == 0


def test_sample_one_mutation_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    bundle = _cohort(output)
    bundle["observations"][0]["observation"]["outcome"] = "PASS"
    with pytest.raises(evidence.EvidenceContractError):
        evidence.validate_fixed_contract_compliance_bundle(bundle)


def test_append_write_failure_keeps_original_cohort_readable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    first = _cohort(output)
    before = output.read_bytes()
    original_replace = evidence.os.replace

    def fail_replace(source: str | bytes, destination: str | bytes) -> None:
        del source, destination
        raise OSError("simulated write failure")

    monkeypatch.setattr(evidence.os, "replace", fail_replace)
    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        _append(output, _FakeModel(), resume=True)
    assert captured.value.code == "RESULT_ATOMIC_WRITE_FAILED"
    assert output.read_bytes() == before
    evidence.validate_fixed_contract_compliance_bundle(json.loads(before))
    monkeypatch.setattr(evidence.os, "replace", original_replace)
    assert first["observations"][0]["sample_index"] == 1


def test_raw_content_is_not_serialized_and_old_validators_still_pass(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    model = _FakeModel({"api_key": "sk-FAKE", "Authorization": "Bearer secret", "raw_prompt": "raw response"})
    bundle = _cohort(output, model)
    serialized = output.read_text(encoding="utf-8")
    for secret in ('"sk-FAKE"', '"Authorization"', '"Bearer', '"raw_prompt":', '"raw response"'):
        assert secret not in serialized
    evidence.validate_fixed_contract_compliance_bundle(bundle)
    evidence.validate_contract_compliance_bundle(json.loads(SOURCE.read_text(encoding="utf-8")))
    evidence.validate_shape_diagnostic_bundle(json.loads(historical_fixture_path(evidence.DIAGNOSTIC_RESULT_RELATIVE_PATH).read_text(encoding="utf-8")))
    evidence.validate_retry_evidence_bundle(json.loads(historical_fixture_path(evidence.RETRY_RESULT_RELATIVE_PATH).read_text(encoding="utf-8")))
    evidence.validate_evidence_bundle(json.loads(historical_fixture_path(evidence.RESULT_RELATIVE_TEMPLATE.format(repeat=1)).read_text(encoding="utf-8")))


def test_deterministic_identity_and_serialization(tmp_path: Path) -> None:
    first = _cohort(tmp_path / "first.json")
    second = _cohort(tmp_path / "second.json")
    assert first["run_id"] == second["run_id"]
    assert first["observations"][1]["observation"]["observation_id"] == second["observations"][1]["observation"]["observation_id"]
    assert first["bundle_digest"] == second["bundle_digest"]
    assert hashlib.sha256((tmp_path / "first.json").read_bytes()).hexdigest() == hashlib.sha256((tmp_path / "second.json").read_bytes()).hexdigest()


def test_dry_run_existing_cohort_is_provider_free(tmp_path: Path) -> None:
    output = tmp_path / "cohort.json"
    _cohort(output)
    result = evidence.FixedContractComplianceCohortRunner(ROOT).dry_run(source_path=SOURCE, output_path=output)
    assert result["existing_sample_indexes"] == [1, 2]
    assert result["remaining_sample_count"] == 1
    assert result["next_sample_index"] == 3
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
