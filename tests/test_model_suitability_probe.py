from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agents.models import ModelInvocationAudit, ModelTurn
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
    def __init__(self, model: str = "deepseek-v4-pro") -> None:
        self.calls = 0
        self.prompts: list[object] = []
        self.model = model

    def generate(self, prompt: object) -> ModelTurn:
        self.calls += 1
        self.prompts.append(prompt)
        return ModelTurn(
            structured_output=copy.deepcopy(EMPTY_CANDIDATE),
            invocation=ModelInvocationAudit(
                session_id="model-suitability-test",
                turn_number=1,
                provider="opencode_go",
                model=self.model,
                outcome="success",
                latency_ms=1.0,
                retry_count=0,
                transport="openai_chat_completions",
                response_contract="character_skill_kit",
            ),
        )


def test_model_identity_is_separate_from_flash() -> None:
    source = "f03a1ed87722b560dc136512e7ef298a83b54156"
    digest = "910f0d1da5c657460f864d085d7223dc618d1f4fa283f0fb2e5f1b5274474ec7"
    pro_id = evidence._model_suitability_run_id(source, digest)
    flash_id = evidence._timeout_suitability_run_id(source, digest)
    assert pro_id != flash_id
    assert "deepseek-v4-pro" in pro_id and "model-suitability" in pro_id


def test_model_suitability_dry_run_is_provider_free(tmp_path: Path) -> None:
    result = evidence.ModelSuitabilityProbeRunner(ROOT).dry_run(output_path=tmp_path / "pro.json")
    assert result["experiment_type"] == "model_suitability"
    assert result["provider"] == "opencode_go"
    assert result["model"] == "deepseek-v4-pro"
    assert result["timeout_seconds"] == 60
    assert result["max_transport_retries"] == 2
    assert result["target_sample_count"] == 1
    assert result["existing_sample_count"] == 0
    assert result["existing_sample_indexes"] == []
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False


@pytest.mark.parametrize(
    ("timeout", "retries", "target"),
    [(30, 2, 1), (60, 1, 1), (60, 3, 1), (60, 2, 2)],
)
def test_model_suitability_freezes_variables(tmp_path: Path, timeout: int, retries: int, target: int) -> None:
    with pytest.raises(evidence.EvidenceRunnerError, match="MODEL_SUITABILITY_VARIABLE_MISMATCH"):
        evidence.ModelSuitabilityProbeRunner(ROOT).dry_run(
            timeout_seconds=timeout,
            max_transport_retries=retries,
            target_sample_count=target,
            output_path=tmp_path / "pro.json",
        )


def test_model_suitability_fake_sample_completes_and_second_is_blocked(tmp_path: Path) -> None:
    output = tmp_path / "pro.json"
    model = _FakeModel()
    bundle = evidence.ModelSuitabilityProbeRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        shadow_model=model,
        enforce_clean_tree=False,
    )
    evidence.validate_model_suitability_bundle(bundle)
    assert bundle["complete"] is True
    assert bundle["sample_index"] == 1
    assert bundle["provider"]["model_requested"] == "deepseek-v4-pro"
    assert model.calls == 1

    called = {"factory": 0}

    def factory() -> object:
        called["factory"] += 1
        raise AssertionError("provider factory must not be constructed")

    with pytest.raises(evidence.EvidenceRunnerError, match="COHORT_ALREADY_COMPLETE"):
        evidence.ModelSuitabilityProbeRunner(ROOT).run(
            live=True,
            expected_source_commit=evidence._source_commit(ROOT),
            resume=True,
            output_path=output,
            model_factory=factory,
            enforce_clean_tree=False,
        )
    assert called["factory"] == 0


def test_model_profile_resolves_to_pro() -> None:
    from agents.model_factory import character_model_from_environment

    model = character_model_from_environment(
        environment={
            "NPC_AGENT_MODEL": "live",
            "NPC_LLM_PROVIDER": "opencode_go",
            "NPC_LLM_MODEL": "deepseek-v4-pro",
            "NPC_LLM_API_KEY": "placeholder-test-key",
            "NPC_LLM_TRANSPORT": "openai_chat_completions",
            "NPC_LLM_STRUCTURED_OUTPUT": "json_object",
            "NPC_LLM_TIMEOUT_SECONDS": "60",
            "NPC_LLM_MAX_RETRIES": "2",
        },
        mode_override="live",
    )
    assert model.model == "deepseek-v4-pro"
    assert model.timeout_seconds == 60.0
    assert model.max_retries == 2


def test_model_suitability_preserves_historical_evidence(tmp_path: Path) -> None:
    paths = [
        ROOT / evidence.RESULT_RELATIVE_TEMPLATE.format(repeat=1),
        ROOT / evidence.RETRY_RESULT_RELATIVE_PATH,
        ROOT / evidence.DIAGNOSTIC_RESULT_RELATIVE_PATH,
        ROOT / evidence.COMPLIANCE_RESULT_RELATIVE_PATH,
        ROOT / evidence.FIXED_COMPLIANCE_RESULT_RELATIVE_PATH,
        ROOT / evidence.TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH,
    ]
    before = [path.read_bytes() for path in paths]
    evidence.ModelSuitabilityProbeRunner(ROOT).dry_run(output_path=tmp_path / "pro.json")
    assert [path.read_bytes() for path in paths] == before


def test_model_suitability_bundle_rejects_flash_model() -> None:
    with pytest.raises(evidence.EvidenceContractError):
        evidence.validate_model_suitability_bundle(
            {"schema_version": "character-skill-s2-shadow-model-suitability/0.1.0"}
        )
