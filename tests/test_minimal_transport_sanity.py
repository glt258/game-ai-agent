from __future__ import annotations

from pathlib import Path

import pytest

from agents.errors import ModelTimeoutError
from agents.models import ModelInvocationAudit, ModelTurn
from evals import character_skill_s2_shadow_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]


class _FakeModel:
    def __init__(self, text: str = '{"status":"ok"}') -> None:
        self.text = text
        self.calls = 0

    def generate(self, prompt: object) -> ModelTurn:
        self.calls += 1
        return ModelTurn(
            text=self.text,
            invocation=ModelInvocationAudit(
                session_id="minimal-sanity-test",
                turn_number=1,
                provider="opencode_go",
                model="deepseek-v4-pro",
                outcome="success",
                latency_ms=1.0,
                retry_count=0,
                transport="openai_chat_completions",
                response_contract="json_object",
            ),
        )


def _run(tmp_path: Path, model: _FakeModel) -> dict[str, object]:
    return evidence.MinimalTransportSanityRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "sanity.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def test_minimal_identity_is_independent() -> None:
    source = evidence._source_commit(ROOT)
    run_id = evidence._minimal_transport_sanity_run_id(source)
    assert run_id != evidence._model_suitability_run_id(source, evidence.load_manifest(ROOT).raw_digest)
    assert "opencode_go-deepseek-v4-pro-t60-r0-n1" in run_id


def test_dry_run_is_provider_free_and_frozen(tmp_path: Path) -> None:
    result = evidence.MinimalTransportSanityRunner(ROOT).dry_run(output_path=tmp_path / "sanity.json")
    assert result["experiment_type"] == "minimal_transport_sanity"
    assert result["provider"] == "opencode_go"
    assert result["model"] == "deepseek-v4-pro"
    assert result["timeout_seconds"] == 60
    assert result["max_transport_retries"] == 0
    assert result["target_sample_count"] == 1
    assert result["existing_sample_count"] == 0
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False


@pytest.mark.parametrize(
    ("timeout", "retries", "target"),
    [(30, 0, 1), (60, 1, 1), (60, 2, 1), (60, 0, 2)],
)
def test_frozen_variables_reject_drift(tmp_path: Path, timeout: int, retries: int, target: int) -> None:
    with pytest.raises(evidence.EvidenceRunnerError, match="MINIMAL_TRANSPORT_SANITY_VARIABLE_MISMATCH"):
        evidence.MinimalTransportSanityRunner(ROOT).dry_run(
            timeout_seconds=timeout,
            max_transport_retries=retries,
            target_sample_count=target,
            output_path=tmp_path / "sanity.json",
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"status":"ok"}', "TRANSPORT_SUCCESS_CONTRACT_PASS"),
        ('{"status":"ok","extra":"x"}', "TRANSPORT_SUCCESS_CONTRACT_REJECTED"),
        ('{"status":"wrong"}', "TRANSPORT_SUCCESS_CONTRACT_REJECTED"),
        ('[]', "TRANSPORT_SUCCESS_CONTRACT_REJECTED"),
        ('not-json', "TRANSPORT_SUCCESS_CONTRACT_REJECTED"),
    ],
)
def test_tiny_contract_outcomes(tmp_path: Path, text: str, expected: str) -> None:
    model = _FakeModel(text)
    bundle = _run(tmp_path, model)
    assert bundle["observation"]["tiny_contract_outcome"] == expected
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1
    evidence.validate_minimal_transport_sanity_bundle(bundle)


def test_timeout_is_unavailable_without_retry(tmp_path: Path) -> None:
    class TimeoutModel:
        calls = 0

        def generate(self, prompt: object) -> ModelTurn:
            self.calls += 1
            raise ModelTimeoutError("timeout")

    model = TimeoutModel()
    bundle = _run(tmp_path, model)  # type: ignore[arg-type]
    assert bundle["observation"]["tiny_contract_outcome"] == "TRANSPORT_UNAVAILABLE"
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1


def test_one_sample_completes_and_second_is_impossible(tmp_path: Path) -> None:
    output = tmp_path / "sanity.json"
    model = _FakeModel()
    runner = evidence.MinimalTransportSanityRunner(ROOT)
    bundle = runner.run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    assert bundle["complete"] is True
    assert bundle["sample_index"] == 1
    with pytest.raises(evidence.EvidenceRunnerError, match="COHORT_ALREADY_COMPLETE"):
        runner.run(
            live=True,
            expected_source_commit=evidence._source_commit(ROOT),
            output_path=output,
            resume=True,
            model_factory=lambda: (_ for _ in ()).throw(AssertionError("factory called")),
            enforce_clean_tree=False,
        )


def test_historical_evidence_is_unchanged(tmp_path: Path) -> None:
    before = (ROOT / evidence.MODEL_SUITABILITY_RESULT_RELATIVE_PATH).read_bytes()
    evidence.MinimalTransportSanityRunner(ROOT).dry_run(output_path=tmp_path / "sanity.json")
    assert (ROOT / evidence.MODEL_SUITABILITY_RESULT_RELATIVE_PATH).read_bytes() == before
