from __future__ import annotations

from pathlib import Path

import pytest

from agents.response_contracts import CHARACTER_SKILL_KIT_JSON_SCHEMA
from evals import character_skill_s2_shadow_evidence as evidence

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


def test_v2_live_is_fail_closed_without_constructing_provider() -> None:
    factory_called = False

    def factory() -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    with pytest.raises(evidence.EvidenceRunnerError, match="COMPACT_V2_LIVE_DISABLED"):
        evidence.CompactContractV2Runner(ROOT).run(live=True, model_factory=factory)
    assert factory_called is False


def test_v2_complete_cohort_blocks_second_sample(tmp_path: Path) -> None:
    output = tmp_path / "v2.json"
    runner = evidence.CompactContractV2Runner(ROOT)
    planned = runner.dry_run(output_path=output)
    output.write_text(
        '{"run_id":"' + planned["run_id"] + '","complete":true,"sample_index":1}',
        encoding="utf-8",
    )
    complete = runner.dry_run(output_path=output)
    assert complete["status"] == "COHORT_ALREADY_COMPLETE"
    assert complete["existing_sample_count"] == 1
    assert complete["next_sample_index"] is None
    assert complete["provider_factory_constructed"] is False
    assert complete["provider_called"] is False


def test_production_contract_builder_remains_separate() -> None:
    assert evidence._compact_v2_contract() != evidence.character_skill_kit_prompt_contract()
    assert "Closed enum vocabulary:" in evidence.character_skill_kit_prompt_contract()
