from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agents.models import ModelInvocationAudit, ModelTurn
from agents.response_contracts import CHARACTER_SKILL_KIT_JSON_SCHEMA
from evals import character_skill_s2_shadow_evidence as evidence
from tests.historical_fixtures import historical_fixture_path

ROOT = Path(__file__).resolve().parents[1]


def test_v2_dry_run_is_provider_free_and_within_size_gate() -> None:
    result = evidence.CompactContractV2Runner(ROOT).dry_run()
    assert result["v2_request_metrics"]["chars"] < evidence.COMPACT_V2_L1_CHARS
    assert result["v2_request_metrics"]["chars"] <= 1800
    assert result["v2_request_metrics"]["chars"] > evidence.COMPACT_V2_L2_CHARS
    assert result["v2_request_metrics"]["bytes"] == 1837
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["feature_flag"] == "OFF"
    assert result["record_only"] is True


def test_v2_root_and_nested_fields_are_canonical_derived() -> None:
    contract = evidence._compact_v2_contract()
    for name in CHARACTER_SKILL_KIT_JSON_SCHEMA["required"]:
        assert name in contract
        assert f"{name}:{CHARACTER_SKILL_KIT_JSON_SCHEMA['properties'][name]['type']}" in contract
    for definition_name, alias in evidence._COMPACT_V2_DEFINITION_ALIASES:
        definition = CHARACTER_SKILL_KIT_JSON_SCHEMA["$defs"][definition_name]
        assert f"{alias}{{" in contract
        for field in ("kind", "id") if definition_name == "typed_ref" else definition["required"]:
            assert field in contract


def test_v2_compact_semantics_without_full_enum_expansion() -> None:
    contract = evidence._compact_v2_contract()
    assert "Ref{kind,id}" in contract
    assert "Edges: Trigger" in contract and "Effect" in contract and "Feedback" in contract
    assert "*_ref(s) are Ref(kind,id)" in contract
    assert "RoleEvidence.effect_refs" in contract
    assert "centrality" in contract
    assert "Canonical enum values only" in contract
    assert "Closed enum vocabulary:" not in contract
    assert "Nested shape summary" not in contract


def test_v2_rendering_and_digest_are_stable() -> None:
    first = evidence._compact_v2_contract()
    second = evidence._compact_v2_contract()
    assert first == second
    assert evidence._digest_bytes(first.encode("utf-8")) == evidence._digest_bytes(second.encode("utf-8"))


def test_v2_identity_is_independent_and_digest_bound() -> None:
    result = evidence.CompactContractV2Runner(ROOT).dry_run()
    assert result["contract_digest"][:12] in result["run_id"]
    assert result["contract_version"] not in {
        evidence.ENUM_STEPOWDOWN_CONTRACT_VERSION,
        evidence.NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION,
    }
    changed = evidence._compact_v2_run_id(
        result["source_commit"], result["manifest_digest"], "0" * 64
    )
    assert changed != result["run_id"]
    assert evidence._COMPACT_V2_RUN_ID_RE.fullmatch(result["run_id"])


def test_v2_live_requires_frozen_source_before_provider_construction() -> None:
    factory_called = False

    def factory() -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    with pytest.raises(evidence.EvidenceRunnerError, match="COMPACT_V2_SOURCE_COMMIT_REQUIRED"):
        evidence.CompactContractV2Runner(ROOT).run(live=True, model_factory=factory)
    assert factory_called is False


def test_v2_live_fake_observation_is_single_and_sanitized(tmp_path: Path) -> None:
    class FakeModel:
        calls = 0

        def generate(self, prompt: object) -> ModelTurn:
            self.calls += 1
            return ModelTurn(
                text='{"status":"ok"}',
                invocation=ModelInvocationAudit(
                    session_id="v2-test", turn_number=1, provider="opencode_go",
                    model="deepseek-v4-pro", outcome="success", latency_ms=1.0,
                    retry_count=0, transport="openai_chat_completions",
                    response_contract="json_object",
                ),
            )

    model = FakeModel()
    output = tmp_path / "v2.json"
    bundle = evidence.CompactContractV2Runner(ROOT).run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: model,
        enforce_clean_tree=False,
    )
    assert model.calls == 1
    assert bundle["observation"]["tiny_contract_outcome"] == "V2_A_TINY_OUTPUT_PASS"
    assert bundle["observation"]["failure_stage"] is None
    evidence.validate_compact_v2_bundle(bundle)


def test_v2_complete_cohort_blocks_second_sample(tmp_path: Path) -> None:
    output = tmp_path / "v2.json"
    runner = evidence.CompactContractV2Runner(ROOT)
    class CompleteModel:
        calls = 0

        def generate(self, prompt: object) -> ModelTurn:
            del prompt
            self.calls += 1
            return ModelTurn(
                text='{"status":"ok"}',
                invocation=ModelInvocationAudit(
                    session_id="v2-complete-test", turn_number=1,
                    provider="opencode_go", model="deepseek-v4-pro", outcome="success",
                    latency_ms=1.0, retry_count=0, transport="openai_chat_completions",
                    response_contract="json_object",
                ),
            )

    runner.run(
        live=True,
        expected_source_commit=evidence._source_commit(ROOT),
        output_path=output,
        model_factory=lambda: CompleteModel(),
        enforce_clean_tree=False,
    )
    complete = runner.dry_run(output_path=output)
    assert complete["status"] == "COHORT_ALREADY_COMPLETE"
    assert complete["existing_sample_count"] == 1
    assert complete["next_sample_index"] is None
    assert complete["provider_factory_constructed"] is False
    assert complete["provider_called"] is False


def test_historical_v2_identity_uses_bundle_source_not_current_head() -> None:
    path = historical_fixture_path(evidence.COMPACT_V2_RESULT_RELATIVE_PATH)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    evidence.validate_compact_v2_bundle(bundle)
    assert bundle["source_commit"] == "dd3bbdfbab644c36cdd7f7e8cb8661a6322abb4e"
    assert evidence._compact_v2_identity_from_bundle(bundle) == bundle["run_id"]
    assert evidence._source_commit(ROOT) != bundle["source_commit"]


@pytest.mark.parametrize("field", ["source_commit", "run_id", "contract_digest", "manifest_digest"])
def test_historical_v2_identity_tampering_fails_closed(field: str) -> None:
    path = historical_fixture_path(evidence.COMPACT_V2_RESULT_RELATIVE_PATH)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    tampered = copy.deepcopy(bundle)
    if field == "run_id":
        tampered[field] = "0" * 40
    elif field == "source_commit":
        tampered[field] = "0" * 40
    else:
        tampered[field] = "0" * 64
    with pytest.raises(evidence.EvidenceContractError):
        evidence.validate_compact_v2_bundle(tampered)


def test_new_identity_remains_bound_to_current_source() -> None:
    result = evidence.CompactContractV2Runner(ROOT).dry_run()
    assert evidence._source_commit(ROOT) in result["run_id"]
    assert "dd3bbdfbab644c36cdd7f7e8cb8661a6322abb4e" not in result["run_id"]


def test_production_contract_builder_remains_separate() -> None:
    assert evidence._compact_v2_contract() != evidence.character_skill_kit_prompt_contract()
    assert "Closed enum vocabulary:" in evidence.character_skill_kit_prompt_contract()
