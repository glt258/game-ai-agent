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
        self.prompt = None

    def generate(self, prompt: object) -> ModelTurn:
        self.calls += 1
        self.prompt = prompt
        return ModelTurn(
            text=self.text,
            invocation=ModelInvocationAudit(
                session_id="full-input-tiny-output-test",
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
    return evidence.FullInputTinyOutputRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "full-input-tiny-output.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def test_input_baseline_is_reconstructed_and_preserved(tmp_path: Path) -> None:
    runner = evidence.FullInputTinyOutputRunner(ROOT)
    result = runner.dry_run(output_path=tmp_path / "probe.json")
    assert result["historical_full_input"]["message_count"] == 2
    assert result["historical_full_input"]["chars"] == 5157
    assert result["historical_full_input"]["bytes"] == 5281
    assert result["request_metrics"]["chars"] >= 5157 * 0.9
    assert result["request_metrics"]["chars"] > 144 * 10
    assert result["input_preservation_ratio"] >= 0.9


def test_identity_is_independent_and_variables_are_frozen() -> None:
    source = evidence._source_commit(ROOT)
    digest = evidence.load_manifest(ROOT).raw_digest
    run_id = evidence._full_input_tiny_output_run_id(source, digest)
    assert run_id != evidence._minimal_transport_sanity_run_id(source)
    assert "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1" in run_id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"status":"ok"}', "FULL_INPUT_TINY_OUTPUT_PASS"),
        ('{"status":"ok","x":1}', "PROVIDER_SUCCESS_TINY_CONTRACT_REJECTED"),
        ('{"status":"wrong"}', "PROVIDER_SUCCESS_TINY_CONTRACT_REJECTED"),
        ('not-json', "PROVIDER_SUCCESS_TINY_CONTRACT_REJECTED"),
    ],
)
def test_tiny_output_contract_outcomes(tmp_path: Path, text: str, expected: str) -> None:
    model = _FakeModel(text)
    bundle = _run(tmp_path, model)
    assert bundle["observation"]["tiny_contract_outcome"] == expected
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1
    evidence.validate_full_input_tiny_output_bundle(bundle)


def test_probe_only_instruction_is_present_without_skillkit_parser(tmp_path: Path) -> None:
    model = _FakeModel()
    _run(tmp_path, model)
    assert evidence.FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION in model.prompt.system_contract
    assert model.prompt.invocation_purpose == "full_input_tiny_output"


def test_timeout_is_unavailable_and_not_retried(tmp_path: Path) -> None:
    class TimeoutModel:
        calls = 0

        def generate(self, prompt: object) -> ModelTurn:
            self.calls += 1
            raise ModelTimeoutError("timeout")

    model = TimeoutModel()
    bundle = evidence.FullInputTinyOutputRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "timeout.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    assert bundle["observation"]["tiny_contract_outcome"] == "FULL_INPUT_TINY_OUTPUT_UNAVAILABLE"
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1


def test_n1_complete_blocks_second_sample(tmp_path: Path) -> None:
    output = tmp_path / "complete.json"
    model = _FakeModel()
    runner = evidence.FullInputTinyOutputRunner(ROOT)
    runner.run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
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
    path = ROOT / evidence.MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH
    before = path.read_bytes()
    evidence.FullInputTinyOutputRunner(ROOT).dry_run(output_path=tmp_path / "probe.json")
    assert path.read_bytes() == before
