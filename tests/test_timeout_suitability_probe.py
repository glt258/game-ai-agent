from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agents.models import ModelInvocationAudit, ModelTurn
from agents.provider_protocol import ProviderCompletion
from evals import character_skill_s2_shadow_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
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
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[object] = []

    def generate(self, prompt: object) -> ModelTurn:
        self.calls += 1
        self.prompts.append(prompt)
        return ModelTurn(
            structured_output=copy.deepcopy(EMPTY_CANDIDATE),
            invocation=ModelInvocationAudit(
                session_id="timeout-suitability-test",
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


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def complete(self, **request: object) -> ProviderCompletion:
        self.requests.append(request)
        return ProviderCompletion(text=json.dumps(EMPTY_CANDIDATE))


def test_timeout_identity_is_separate_from_fixed_30s_identity() -> None:
    source = "f03a1ed87722b560dc136512e7ef298a83b54156"
    digest = "910f0d1da5c657460f864d085d7223dc618d1f4fa283f0fb2e5f1b5274474ec7"
    timeout_id = evidence._timeout_suitability_run_id(source, digest)
    fixed_id = evidence._fixed_compliance_run_id(source, digest, 3)
    assert timeout_id != fixed_id
    assert "timeout-suitability" in timeout_id and "t60-r2-n1" in timeout_id


def test_timeout_dry_run_is_provider_free_and_targets_one(tmp_path: Path) -> None:
    output = tmp_path / "timeout.json"
    result = evidence.TimeoutSuitabilityProbeRunner(ROOT).dry_run(output_path=output)
    assert result["experiment_type"] == "timeout_suitability"
    assert result["timeout_seconds"] == 60
    assert result["max_transport_retries"] == 2
    assert result["target_sample_count"] == 1
    assert result["existing_sample_count"] == 0
    assert result["existing_sample_indexes"] == []
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert not output.exists()


@pytest.mark.parametrize(
    ("timeout", "retries"),
    [(30, 2), (90, 2), (60, 1), (60, 3)],
)
def test_timeout_probe_rejects_non_frozen_variables(tmp_path: Path, timeout: int, retries: int) -> None:
    with pytest.raises(evidence.EvidenceRunnerError, match="TIMEOUT_SUITABILITY_VARIABLE_MISMATCH"):
        evidence.TimeoutSuitabilityProbeRunner(ROOT).dry_run(
            timeout_seconds=timeout,
            max_transport_retries=retries,
            output_path=tmp_path / "timeout.json",
        )


def test_fake_observation_completes_n1_and_second_run_is_blocked(tmp_path: Path) -> None:
    output = tmp_path / "timeout.json"
    model = _FakeModel()
    bundle = evidence.TimeoutSuitabilityProbeRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        shadow_model=model,
        enforce_clean_tree=False,
    )
    evidence.validate_timeout_suitability_bundle(bundle)
    assert bundle["target_sample_count"] == 1
    assert bundle["complete"] is True
    assert bundle["sample_index"] == 1
    assert bundle["observation"]["observation"]["observation_id"].endswith(":sample-01")
    assert model.calls == 1

    called = {"factory": 0}

    def factory() -> object:
        called["factory"] += 1
        raise AssertionError("provider factory must not be constructed")

    with pytest.raises(evidence.EvidenceRunnerError, match="COHORT_ALREADY_COMPLETE"):
        evidence.TimeoutSuitabilityProbeRunner(ROOT).run(
            live=True,
            expected_source_commit=evidence._source_commit(ROOT),
            resume=True,
            output_path=output,
            model_factory=factory,
            enforce_clean_tree=False,
        )
    assert called["factory"] == 0


def test_live_settings_for_probe_are_exactly_60s_and_two_retries() -> None:
    client = _FakeClient()
    from agents.model_factory import character_model_from_environment

    model = character_model_from_environment(
        environment={
            "NPC_AGENT_MODEL": "live",
            "NPC_LLM_PROVIDER": "opencode_go",
            "NPC_LLM_MODEL": "deepseek-v4-flash",
            "NPC_LLM_API_KEY": "placeholder-test-key",
            "NPC_LLM_TRANSPORT": "openai_chat_completions",
            "NPC_LLM_STRUCTURED_OUTPUT": "json_object",
            "NPC_LLM_TIMEOUT_SECONDS": "60",
            "NPC_LLM_MAX_RETRIES": "2",
        },
        mode_override="live",
        client=client,
    )
    assert model.timeout_seconds == 60.0
    assert model.max_retries == 2
    assert model.backoff_seconds == 0.5


def test_timeout_probe_does_not_mutate_historical_evidence(tmp_path: Path) -> None:
    paths = [
        ROOT / evidence.RESULT_RELATIVE_TEMPLATE.format(repeat=1),
        ROOT / evidence.RETRY_RESULT_RELATIVE_PATH,
        ROOT / evidence.DIAGNOSTIC_RESULT_RELATIVE_PATH,
        ROOT / evidence.COMPLIANCE_RESULT_RELATIVE_PATH,
        ROOT / evidence.FIXED_COMPLIANCE_RESULT_RELATIVE_PATH,
    ]
    before = [path.read_bytes() for path in paths]
    evidence.TimeoutSuitabilityProbeRunner(ROOT).dry_run(output_path=tmp_path / "timeout.json")
    assert [path.read_bytes() for path in paths] == before
