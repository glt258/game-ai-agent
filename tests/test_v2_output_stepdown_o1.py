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


def _run_diagnostic(tmp_path: Path, model: _FakeModel, *, guided: bool = False) -> dict[str, object]:
    return evidence.O1SafeDiagnosticRunner(ROOT, guided=guided).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "diagnostic.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def _run_o2(tmp_path: Path, model: _FakeModel) -> dict[str, object]:
    return evidence.O2LocalStructureRunner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=tmp_path / "o2.json",
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )


def _nested_fixture() -> dict[str, object]:
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


def test_safe_snapshot_is_pure_bounded_and_value_free() -> None:
    fixture = evidence.build_o1_root_only_fixture()
    before = copy.deepcopy(fixture)
    first = evidence.build_o1_safe_diagnostic_snapshot(fixture)
    second = evidence.build_o1_safe_diagnostic_snapshot(fixture)
    assert first == second
    assert fixture == before
    assert first.root_schema_version_exact_match is True
    assert first.collection_shape_valid is True
    assert first.nonempty_collection_count == 0
    assert first.unexpected_nested_content is False


def test_safe_diagnostic_classifies_schema_mismatch_without_value_leak(tmp_path: Path) -> None:
    payload = evidence.build_o1_root_only_fixture()
    payload["schema_version"] = "TOP-SECRET-GENERATED-VALUE"
    bundle = _run_diagnostic(tmp_path, _FakeModel(text=json.dumps(payload)))
    safe = bundle["observation"]["safe_diagnostics"]
    assert safe["root_schema_version_present"] is True
    assert safe["root_schema_version_is_string"] is True
    assert safe["root_schema_version_exact_match"] is False
    assert safe["unexpected_nested_content"] is False
    assert safe["diagnostic_category"] == "ROOT_SCHEMA_VERSION_MISMATCH"
    assert safe["diagnostic_resolution"] == "FIELD_RESOLVED"
    assert "TOP-SECRET-GENERATED-VALUE" not in json.dumps(bundle)
    evidence.validate_o1_safe_diagnostic_bundle(bundle)


def test_safe_diagnostic_captures_nested_and_multiple_signals(tmp_path: Path) -> None:
    nested = _nested_fixture()
    snapshot = evidence.build_o1_safe_diagnostic_snapshot(nested)
    assert snapshot.root_schema_version_exact_match is True
    assert snapshot.nonempty_collection_count >= 1
    assert snapshot.unexpected_nested_content is True
    category, resolution = evidence.classify_o1_safe_diagnostic(snapshot, "INVALID_CANONICAL_VALUE")
    assert category == "O1_CONTRACT_NESTED_CONTENT_VIOLATION"
    assert resolution == "PARTIALLY_RESOLVED"

    nested["entries"][0]["protocols"][0]["when"]["event"] = "TOP-SECRET-GENERATED-VALUE"
    bundle = _run_diagnostic(tmp_path / "nested", _FakeModel(text=json.dumps(nested)))
    safe = bundle["observation"]["safe_diagnostics"]
    assert safe["diagnostic_category"] == "NESTED_INVALID_CANONICAL_VALUE"
    assert safe["diagnostic_resolution"] == "FIELD_RESOLVED"
    assert "TOP-SECRET-GENERATED-VALUE" not in json.dumps(bundle)

    multiple = _nested_fixture()
    multiple["schema_version"] = "TOP-SECRET-GENERATED-VALUE"
    bundle = _run_diagnostic(tmp_path / "multiple", _FakeModel(text=json.dumps(multiple)))
    safe = bundle["observation"]["safe_diagnostics"]
    assert safe["diagnostic_category"] == "MULTIPLE_OR_AMBIGUOUS_VIOLATIONS"
    assert safe["diagnostic_resolution"] == "PARTIALLY_RESOLVED"
    assert "TOP-SECRET-GENERATED-VALUE" not in json.dumps(bundle)


def test_safe_diagnostic_preserves_shape_taxonomy_and_timeout_boundary(tmp_path: Path) -> None:
    unknown = evidence.build_o1_root_only_fixture()
    unknown["unknown_generated_key"] = "sk-FAKE Authorization Bearer"
    unknown_bundle = _run_diagnostic(tmp_path / "unknown", _FakeModel(text=json.dumps(unknown)))
    unknown_obs = unknown_bundle["observation"]
    assert unknown_obs["parser_failure_categories"] == ("UNKNOWN_FIELD",)
    assert unknown_obs["safe_diagnostics"]["diagnostic_category"] == "SHAPE_FAILURE"
    assert "unknown_generated_key" not in json.dumps(unknown_bundle)
    assert "sk-FAKE" not in json.dumps(unknown_bundle)
    assert "Authorization" not in json.dumps(unknown_bundle)
    assert "Bearer" not in json.dumps(unknown_bundle)

    malformed = _run_diagnostic(tmp_path / "malformed", _FakeModel(text="{not-json"))["observation"]
    assert malformed["principal_verdict"] == "O1_ROOT_ONLY_MALFORMED"
    assert malformed["parser_invoked"] is False
    timeout = _run_diagnostic(tmp_path / "timeout", _FakeModel(error=ModelTimeoutError("timeout")))["observation"]
    assert timeout["principal_verdict"] == "O1_ROOT_ONLY_UNAVAILABLE"
    assert timeout["parser_invoked"] is False
    assert timeout["safe_diagnostics"]["parser_failure_class"] == "UNAVAILABLE"


def test_safe_diagnostic_dry_run_is_independent_and_provider_free(tmp_path: Path) -> None:
    result = evidence.O1SafeDiagnosticRunner(ROOT).dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_o1_safe_diagnostic"
    assert result["experiment_type"] == "compact_contract_v2_output_stepdown_diagnostic"
    assert result["level"] == "O1_ROOT_ONLY"
    assert result["request_metrics"]["chars"] == 1461
    assert result["request_metrics"]["bytes"] == 1589
    assert result["existing_sample_count"] == 0
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["old_o1_cohort_complete"] is True
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert not (tmp_path / "plan.json").exists()


def test_schema_guided_diagnostic_is_independent_and_preserves_parser_boundary(tmp_path: Path) -> None:
    prompt = evidence._o1_root_only_guided_prompt(evidence.O1SafeDiagnosticRunner(ROOT).cases["case_13"])
    assert "schema_version exactly to skill-kit-candidate/0.1.1" in prompt.system_contract
    metrics = evidence._message_metrics(evidence.LiveLLMAdapter._provider_messages(prompt))
    assert metrics["chars"] == 1488
    assert metrics["bytes"] == 1616
    guided = _run_diagnostic(tmp_path / "guided", _FakeModel(), guided=True)
    assert guided["output_contract_version"] == evidence.O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION
    assert guided["output_contract_digest"] == evidence._o1_root_only_guided_output_contract_digest()
    assert guided["observation"]["parser_outcome"] == "PARSER_PASS"
    assert guided["observation"]["principal_verdict"] == "O1_ROOT_ONLY_STRUCTURAL_PASS"
    assert guided["observation"]["evaluator_invoked"] is False
    assert guided["observation"]["safe_diagnostics"]["diagnostic_category"] == "NO_DIAGNOSTIC"
    evidence.validate_o1_safe_diagnostic_bundle(guided)


def test_schema_guided_diagnostic_dry_run_has_new_identity_and_no_provider(tmp_path: Path) -> None:
    result = evidence.O1SafeDiagnosticRunner(ROOT, guided=True).dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_o1_safe_diagnostic"
    assert result["output_contract_version"] == evidence.O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION
    assert result["output_contract_digest"] == evidence._o1_root_only_guided_output_contract_digest()
    assert result["request_metrics"]["chars"] == 1488
    assert result["request_metrics"]["bytes"] == 1616
    assert result["existing_sample_count"] == 0
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert not (tmp_path / "plan.json").exists()


def test_o2_local_structure_fixture_is_canonical_and_scoped() -> None:
    fixture = evidence.build_o2_local_structure_fixture()
    candidate = evidence.parse_candidate(fixture)
    assert len(candidate.entries) == 1
    assert len(candidate.entries[0].protocols) == 1
    assert len(candidate.entries[0].protocols[0].causes) == 1
    snapshot = evidence._o2_local_structure_snapshot(fixture)
    assert snapshot == {
        "root_schema_version_exact_match": True,
        "collection_shape_valid": True,
        "entry_count": 1,
        "protocol_count": 1,
        "effect_count": 1,
        "typed_ref_count": 0,
        "local_structure_complete": True,
    }


def test_o2_local_structure_dry_run_and_fake_provider_are_independent(tmp_path: Path) -> None:
    result = evidence.O2LocalStructureRunner(ROOT).dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_o2_local_structure"
    assert result["existing_sample_count"] == 0
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["request_metrics"]["chars"] == 1781
    assert result["request_metrics"]["bytes"] == 1909
    bundle = _run_o2(tmp_path / "live", _FakeModel(text=json.dumps(evidence.build_o2_local_structure_fixture())))
    assert bundle["observation"]["provider_outcome"] == "success"
    assert bundle["observation"]["parser_outcome"] == "PARSER_PASS"
    assert bundle["observation"]["principal_verdict"] == "O2_LOCAL_STRUCTURE_STRUCTURAL_PASS"
    assert bundle["observation"]["evaluator_invoked"] is False
    evidence.validate_o2_local_structure_bundle(bundle)


def test_o2_compact_contract_is_a_new_shorter_identity(tmp_path: Path) -> None:
    runner = evidence.O2LocalStructureRunner(ROOT, compact=True)
    result = runner.dry_run(output_path=tmp_path / "plan.json")
    assert result["status"] == "dry_run_o2_local_structure"
    assert result["output_contract_version"] == evidence.O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION
    assert result["request_metrics"]["chars"] == 1533
    assert result["request_metrics"]["bytes"] == 1661
    assert result["existing_sample_count"] == 0
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False


def test_o1_5_entry_only_probe_is_shortest_nested_variant(tmp_path: Path) -> None:
    prompt = evidence._o2_entry_only_prompt(evidence.O2LocalStructureRunner(ROOT).cases["case_13"])
    metrics = evidence._message_metrics(evidence.LiveLLMAdapter._provider_messages(prompt))
    assert metrics["chars"] == 1454
    assert metrics["bytes"] == 1582
    payload = evidence.build_o2_local_structure_fixture()
    payload["entries"][0]["protocols"] = []
    assert evidence.parse_candidate(payload).entries[0].protocols == ()
    result = evidence.O2LocalStructureRunner(ROOT, entry_only=True).dry_run(output_path=tmp_path / "plan.json")
    assert result["output_contract_version"] == evidence.O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION
    assert result["existing_sample_count"] == 0
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
