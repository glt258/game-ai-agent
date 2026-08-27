from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agents.errors import ModelTimeoutError
from agents.models import ModelInvocationAudit, ModelTurn
from evals import character_skill_s2_shadow_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> dict[str, object]:
    source = json.loads(
        (ROOT / "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.json").read_text(
            encoding="utf-8"
        )
    )
    payload = copy.deepcopy(source["candidates"]["mechanic_repair"])
    payload["feedback_relations"] = [
        {
            "feedback_id": "echo_feedback",
            "source_effect": {"kind": "effect", "id": "echo/trigger/apply"},
            "target_protocol": {"kind": "protocol", "id": "echo/feedback"},
            "event": "effect_resolved",
            "operation": "enables",
        }
    ]
    return payload


def _audit(outcome: str = "success") -> ModelInvocationAudit:
    return ModelInvocationAudit(
        session_id="minimal-skillkit-test",
        turn_number=1,
        provider="opencode_go",
        model="deepseek-v4-pro",
        outcome=outcome,
        latency_ms=12.0,
        retry_count=0,
        transport="openai_chat_completions",
        response_contract="character_skill_kit",
    )


class _FakeModel:
    def __init__(self, *, text: str | None = None, error: BaseException | None = None) -> None:
        self.text = text if text is not None else json.dumps(_fixture(), ensure_ascii=False)
        self.error = error
        self.calls = 0

    def generate(self, prompt: object) -> ModelTurn:
        del prompt
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ModelTurn(text=self.text, invocation=_audit())


def _run(tmp_path: Path, model: _FakeModel) -> dict[str, object]:
    return evidence.MinimalSkillKitRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "minimal.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def test_dry_run_is_provider_free_and_preserves_frozen_metrics(tmp_path: Path) -> None:
    result = evidence.MinimalSkillKitRunner(ROOT).dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_minimal_skillkit"
    assert result["contract_digest"] == "5dd592925cb4cdc0e20cbb564deedba4c64fe74e8fd79bb2925db66cde801bce"
    assert result["request_metrics"]["chars"] > 1709
    assert result["production_request_metrics"] == {
        **result["production_request_metrics"],
        "chars": 5157,
        "bytes": 5281,
    }
    assert result["existing_sample_count"] == 0
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert not (tmp_path / "plan.json").exists()


def test_canonical_minimal_fixture_reaches_parser_refs_and_evaluator(tmp_path: Path) -> None:
    model = _FakeModel()
    bundle = _run(tmp_path, model)
    observation = bundle["observation"]
    assert model.calls == 1
    assert observation["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_STRUCTURAL_PASS"
    assert observation["parser_outcome"] == "PARSER_PASS"
    assert observation["reference_validation_result"] == "PASS"
    assert observation["evaluator_outcome"] == "PASS"
    evidence.validate_minimal_skillkit_bundle(bundle)


def test_parser_pass_evaluator_fail_remains_structural_pass(tmp_path: Path) -> None:
    payload = _fixture()
    payload["entries"][0]["protocols"][2]["causes"][0]["operation"] = "direct_output"
    model = _FakeModel(text=json.dumps(payload))
    observation = _run(tmp_path, model)["observation"]
    assert observation["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_STRUCTURAL_PASS"
    assert observation["parser_outcome"] == "PARSER_PASS"
    assert observation["evaluator_outcome"] == "FAIL"


def test_minimal_shape_counts_are_enforced_after_canonical_parse(tmp_path: Path) -> None:
    payload = _fixture()
    extra = copy.deepcopy(payload["entries"][0]["protocols"][2])
    extra["protocol_id"] = "extra"
    payload["entries"][0]["protocols"].append(extra)
    observation = _run(tmp_path, _FakeModel(text=json.dumps(payload)))["observation"]
    assert observation["parser_outcome"] == "PARSER_REJECTED"
    assert observation["parser_failure_categories"] == ("MINIMAL_SHAPE_MISMATCH",)
    assert observation["evaluator_invoked"] is False


@pytest.mark.parametrize(
    ("mutator", "category"),
    [
        (lambda p: p["entries"][0].pop("name"), "MISSING_REQUIRED_FIELD"),
        (lambda p: p["entries"][0]["protocols"][0]["when"].update({"event": "not_canonical"}), "INVALID_ENUM"),
    ],
)
def test_shape_rejections_are_sanitized(tmp_path: Path, mutator, category: str) -> None:
    payload = _fixture()
    mutator(payload)
    model = _FakeModel(text=json.dumps(payload))
    observation = _run(tmp_path, model)["observation"]
    assert observation["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
    assert observation["parser_failure_categories"] == (category,)
    assert "not_canonical" not in json.dumps(observation)


def test_broken_reference_is_evaluator_rejection_without_raw_ids(tmp_path: Path) -> None:
    payload = _fixture()
    payload["feedback_relations"][0]["source_effect"]["id"] = "echo/support/support"
    observation = _run(tmp_path, _FakeModel(text=json.dumps(payload)))["observation"]
    assert observation["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
    assert observation["reference_validation_result"] == "FAIL"
    assert "echo/support/support" not in json.dumps(observation)


def test_unknown_field_reports_only_count(tmp_path: Path) -> None:
    payload = _fixture()
    payload["unexpected_secret_field"] = "do-not-store"
    observation = _run(tmp_path, _FakeModel(text=json.dumps(payload)))["observation"]
    assert observation["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
    assert observation["parser_failure_categories"] == ("UNKNOWN_FIELD",)
    serialized = json.dumps(observation)
    assert "unexpected_secret_field" not in serialized
    assert "do-not-store" not in serialized


def test_malformed_and_timeout_are_distinct(tmp_path: Path) -> None:
    malformed = _run(tmp_path / "malformed", _FakeModel(text="{not-json"))["observation"]
    assert malformed["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_MALFORMED"
    timeout = _run(tmp_path / "timeout", _FakeModel(error=ModelTimeoutError("timeout")))["observation"]
    assert timeout["principal_verdict"] == "V2_A_MINIMAL_SKILLKIT_UNAVAILABLE"
    assert timeout["transport_attempts"] == 1


def test_complete_bundle_blocks_second_sample_without_provider(tmp_path: Path) -> None:
    model = _FakeModel()
    output = tmp_path / "minimal.json"
    runner = evidence.MinimalSkillKitRunner(ROOT)
    runner.run(live=True, expected_source_commit=evidence._source_commit(ROOT), output_path=output, model_factory=lambda: model, enforce_clean_tree=False)
    plan = runner.dry_run(output_path=output)
    assert plan["status"] == "COHORT_ALREADY_COMPLETE"
    assert plan["provider_factory_constructed"] is False
    assert plan["provider_called"] is False
    assert model.calls == 1
