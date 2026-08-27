from __future__ import annotations

import copy
import json
from pathlib import Path

from agents.errors import ModelTimeoutError
from agents.models import ModelInvocationAudit, ModelTurn
from evals import character_skill_s2_shadow_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]


def _audit(outcome: str = "success") -> ModelInvocationAudit:
    return ModelInvocationAudit(
        session_id="o1-root-only-test",
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
        self.text = text if text is not None else json.dumps(evidence.build_o1_root_only_fixture())
        self.error = error
        self.calls = 0

    def generate(self, prompt: object) -> ModelTurn:
        del prompt
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ModelTurn(text=self.text, invocation=_audit())


def _run(tmp_path: Path, model: _FakeModel) -> dict[str, object]:
    return evidence.OutputStepdownRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "o1.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def test_o1_dry_run_is_provider_free_and_preserves_frozen_v2_metrics(tmp_path: Path) -> None:
    result = evidence.OutputStepdownRunner(ROOT).dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_o1_root_only"
    assert result["experiment_type"] == "compact_contract_v2_output_stepdown"
    assert result["level"] == "O1_ROOT_ONLY"
    assert result["contract_digest"] == "5dd592925cb4cdc0e20cbb564deedba4c64fe74e8fd79bb2925db66cde801bce"
    assert result["request_metrics"]["chars"] == 1461
    assert result["request_metrics"]["bytes"] == 1589
    assert result["output_contract_version"] == "v2-output-stepdown-o1-root-only/0.2.0"
    assert result["output_contract_digest"] == "961f19f4a40fa59c2078d73eae94d38041e92c967160d11d78b2eb0e250d98a6"
    assert result["v2_tiny_request_metrics"]["chars"] == 1709
    assert result["v2_minimal_request_metrics"]["chars"] == 1724
    assert result["output_fixture_metrics"] == {
        "chars": 163,
        "bytes": 163,
        "objects": 1,
        "fields": 8,
        "refs": 0,
        "enum_decisions": 0,
        "parser_legal": True,
    }
    assert result["existing_sample_count"] == 0
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["evaluator_invoked"] is False
    assert not (tmp_path / "plan.json").exists()


def test_o1_fixture_is_exact_canonical_root_only_and_parser_legal() -> None:
    fixture = evidence.build_o1_root_only_fixture()
    assert tuple(fixture) == (
        "schema_version", "entries", "feedback_relations", "resources",
        "states", "summons", "role_evidence", "display_summary",
    )
    assert set(fixture) == {
        "schema_version", "entries", "feedback_relations", "resources",
        "states", "summons", "role_evidence", "display_summary",
    }
    assert all(fixture[name] == [] for name in (
        "entries", "feedback_relations", "resources", "states", "summons", "role_evidence",
    ))
    assert evidence.parse_candidate(fixture).entries == ()
    assert len(evidence._canonical_json(fixture)) == 163


def test_o1_fake_structural_pass_does_not_invoke_evaluator(tmp_path: Path) -> None:
    model = _FakeModel()
    bundle = _run(tmp_path, model)
    observation = bundle["observation"]
    assert model.calls == 1
    assert observation["principal_verdict"] == "O1_ROOT_ONLY_STRUCTURAL_PASS"
    assert observation["parser_invoked"] is True
    assert observation["parser_outcome"] == "PARSER_PASS"
    assert observation["evaluator_invoked"] is False
    assert observation["evaluator_outcome"] == "NOT_RUN"
    assert observation["repair_calls"] == 0
    evidence.validate_o1_root_only_bundle(bundle)


def test_o1_parser_failures_are_bounded_and_do_not_store_raw_content(tmp_path: Path) -> None:
    fixture = evidence.build_o1_root_only_fixture()
    cases = []
    missing = copy.deepcopy(fixture)
    del missing["entries"]
    cases.append((missing, "MISSING_REQUIRED_FIELD"))
    unknown = copy.deepcopy(fixture)
    unknown["unexpected_secret_field"] = "sk-FAKE Authorization Bearer"
    cases.append((unknown, "UNKNOWN_FIELD"))
    wrong_type = copy.deepcopy(fixture)
    wrong_type["states"] = {}
    cases.append((wrong_type, "WRONG_TYPE"))
    for payload, category in cases:
        observation = _run(tmp_path / category, _FakeModel(text=json.dumps(payload)))["observation"]
        assert observation["principal_verdict"] == "O1_ROOT_ONLY_PARSE_REJECTED"
        assert observation["parser_failure_categories"] == (category,)
        serialized = json.dumps(observation)
        assert "unexpected_secret_field" not in serialized
        assert "sk-FAKE" not in serialized
        assert "Authorization" not in serialized
        assert "Bearer" not in serialized


def test_o1_malformed_and_provider_timeout_are_distinct(tmp_path: Path) -> None:
    malformed = _run(tmp_path / "malformed", _FakeModel(text="{not-json"))["observation"]
    assert malformed["principal_verdict"] == "O1_ROOT_ONLY_MALFORMED"
    assert malformed["parser_invoked"] is False
    timeout = _run(tmp_path / "timeout", _FakeModel(error=ModelTimeoutError("timeout")))["observation"]
    assert timeout["principal_verdict"] == "O1_ROOT_ONLY_UNAVAILABLE"
    assert timeout["parser_invoked"] is False
    assert timeout["transport_attempts"] == 1


def test_o1_identity_is_independent_and_complete_blocks_second_sample(tmp_path: Path) -> None:
    runner = evidence.OutputStepdownRunner(ROOT)
    plan = runner.dry_run(output_path=tmp_path / "o1.json")
    assert plan["run_id"] != evidence._compact_v2_run_id(
        plan["source_commit"], plan["manifest_digest"], plan["contract_digest"]
    )
    model = _FakeModel()
    output = tmp_path / "o1.json"
    runner.run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    complete = runner.dry_run(output_path=output)
    assert complete["status"] == "COHORT_ALREADY_COMPLETE"
    assert complete["existing_sample_count"] == 1
    assert complete["next_sample_index"] is None
    assert complete["remaining_sample_count"] == 0
    assert complete["provider_factory_constructed"] is False
    assert complete["provider_called"] is False
    assert model.calls == 1


def test_o1_output_instruction_is_compact_and_does_not_embed_fixture() -> None:
    instruction = evidence.O1_ROOT_ONLY_OUTPUT_INSTRUCTION
    assert len(instruction) == 210
    assert "canonical CharacterSkillKit root" in instruction
    assert "canonical schema_version" in instruction
    assert "keep all collections empty" in instruction
    assert "shortest legal display_summary" in instruction
    assert "no nested content" in instruction
    assert "JSON only" in instruction
    assert "wrapper" not in instruction
    assert "additional fields" not in instruction
    assert instruction.count("schema_version") == 1
    assert '"entries": []' not in instruction
    assert '"schema_version": "skill-kit-candidate/0.1.1"' not in instruction


def test_o1_compression_is_versioned_and_identity_changes() -> None:
    assert evidence.O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION != "v2-output-stepdown-o1-root-only/0.1.0"
    assert evidence._o1_root_only_output_contract_digest() != "74a490909a43407384c1c04f807f82e65411b639e3b5c0f30aee404597516a16"
    assert evidence.O1_ROOT_ONLY_OUTPUT_INSTRUCTION.count("feedback_relations") == 0
    assert evidence.O1_ROOT_ONLY_OUTPUT_INSTRUCTION.count("role_evidence") == 0
    assert evidence.O1_ROOT_ONLY_OUTPUT_INSTRUCTION.count("no wrapper") == 0
    assert evidence.O1_ROOT_ONLY_OUTPUT_INSTRUCTION.count("additional fields") == 0
