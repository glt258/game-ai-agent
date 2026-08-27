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
                session_id="enum-stepdown-test",
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


def test_l1_dry_run_is_frozen_and_provider_free(tmp_path: Path) -> None:
    result = evidence.EnumExpansionStepdownRunner(ROOT).dry_run(
        output_path=tmp_path / "probe.json"
    )
    assert result["l0_chars"] == 5617
    assert result["l1_chars"] == 2131
    assert result["l1_l0_char_ratio"] < 0.5
    assert result["l1_chars"] > 1000
    assert result["enum_expansion_included"] is False
    assert result["enum_semantic_guidance_reduced"] is True
    assert result["nested_shape_included"] is True
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"status":"ok"}', "L1_ENUM_STEPDOWN_PASS"),
        ('{"status":"bad"}', "L1_ENUM_STEPDOWN_TRANSPORT_REACHABLE_CONTRACT_REJECTED"),
    ],
)
def test_l1_tiny_contract_outcomes(tmp_path: Path, text: str, expected: str) -> None:
    model = _FakeModel(text)
    bundle = evidence.EnumExpansionStepdownRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "probe.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    assert bundle["observation"]["tiny_contract_outcome"] == expected
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1
    assert model.prompt.invocation_purpose == "enum_expansion_stepdown"
    assert evidence.FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION in model.prompt.system_contract
    assert "Closed enum vocabulary:" not in model.prompt.system_contract
    assert "Use only valid canonical enum values defined by the SkillKit contract." in model.prompt.system_contract
    evidence.validate_enum_stepdown_bundle(bundle)


def test_l1_timeout_is_unavailable_without_retry(tmp_path: Path) -> None:
    class TimeoutModel:
        calls = 0

        def generate(self, prompt: object) -> ModelTurn:
            self.calls += 1
            raise ModelTimeoutError("timeout")

    model = TimeoutModel()
    bundle = evidence.EnumExpansionStepdownRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "timeout.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    assert bundle["observation"]["tiny_contract_outcome"] == "L1_ENUM_STEPDOWN_UNAVAILABLE"
    assert bundle["observation"]["transport_attempts"] == 1
    assert model.calls == 1


def test_l1_complete_blocks_second_sample(tmp_path: Path) -> None:
    output = tmp_path / "complete.json"
    model = _FakeModel()
    runner = evidence.EnumExpansionStepdownRunner(ROOT)
    runner.run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    complete = runner.dry_run(output_path=output)
    assert complete["status"] == "COHORT_ALREADY_COMPLETE"
    assert complete["provider_factory_constructed"] is False
    assert complete["provider_called"] is False
    with pytest.raises(evidence.EvidenceRunnerError, match="COHORT_ALREADY_COMPLETE"):
        runner.run(
            live=True,
            expected_source_commit=evidence._source_commit(ROOT),
            output_path=output,
            resume=True,
            model_factory=lambda: (_ for _ in ()).throw(AssertionError("factory called")),
            enforce_clean_tree=False,
        )

