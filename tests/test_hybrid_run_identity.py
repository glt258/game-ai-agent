"""Offline deterministic identity and tamper-resistance tests for Hybrid H3."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from character_intelligence.hybrid_ir import (
    HYBRID_RUN_ID_PREFIX,
    HybridExperimentIdentity,
    HybridGenerationContext,
    HybridSemanticIRRunner,
    build_hybrid_run_id,
    build_model_facing_request,
    run_fake_pipeline,
    validate_hybrid_evidence,
)
from character_intelligence.semantic_ir import SEMANTIC_IR_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _identity() -> HybridExperimentIdentity:
    return HybridExperimentIdentity(
        experiment="character_skill_s2_hybrid_semantic_ir",
        source_commit="f1c5f55e34c39ecaf17576fbf2c5401f9267d3f6",
        ir_schema_version=SEMANTIC_IR_VERSION,
        model_facing_contract_version="semantic-skill-plan-ir-contract/0.1.0",
        model_facing_contract_digest="8716a5770d4b1d12c92c546990b5274d7de4f95528cbd06445540a404efa806b",
        compiler_version="skillkit-compiler/0.1.0",
        canonical_schema_version="skill-kit-candidate/0.1.1",
        provider="opencode_go",
        model="deepseek-v4-pro",
        case_id="case_13",
        timeout_seconds=60,
        max_transport_retries=0,
        target_sample_count=1,
        response_mode="json_object",
        feature_flag="OFF",
        record_only=True,
    )


def _context() -> HybridGenerationContext:
    return HybridGenerationContext(
        "Design a support ability that enables an ally after the ability is invoked.",
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked", "feedback_received"),
        allowed_feedback_events=("effect_resolved",),
        allowed_feedback_relations=("enables",),
        allowed_modes=("active",),
        allowed_roles=("support",),
        allowed_centralities=("core",),
    )


def test_run_id_is_deterministic_and_has_full_digest() -> None:
    identity = _identity()
    first = build_hybrid_run_id(identity, sample_index=1)
    second = build_hybrid_run_id(identity, sample_index=1)
    assert first == second
    prefix, sample, digest = first.rsplit("-", 2)
    assert prefix == f"{HYBRID_RUN_ID_PREFIX}-sample"
    assert sample == "01"
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


@pytest.mark.parametrize(
    "field",
    [
        "experiment",
        "source_commit",
        "ir_schema_version",
        "model_facing_contract_version",
        "model_facing_contract_digest",
        "compiler_version",
        "canonical_schema_version",
        "provider",
        "model",
        "case_id",
        "timeout_seconds",
        "max_transport_retries",
        "target_sample_count",
        "response_mode",
        "feature_flag",
        "record_only",
    ],
)
def test_every_identity_field_changes_run_id(field: str) -> None:
    identity = _identity()
    original = build_hybrid_run_id(identity, sample_index=1)
    value = getattr(identity, field)
    changed_value = (not value) if isinstance(value, bool) else value + 1 if isinstance(value, int) else f"{value}-changed"
    changed = replace(identity, **{field: changed_value})
    assert build_hybrid_run_id(changed, sample_index=1) != original


def test_sample_index_is_bound_and_non_identity_noise_is_not() -> None:
    identity = _identity()
    assert build_hybrid_run_id(identity, sample_index=1) != build_hybrid_run_id(identity, sample_index=2)
    first_observation = {"latency_ms": 4891, "timestamp": "2026-08-27T00:00:00+08:00", "outcome": "PASS"}
    second_observation = {"latency_ms": 99999, "timestamp": "2026-08-28T00:00:00+08:00", "outcome": "FAIL"}
    assert first_observation != second_observation
    # Observation noise is intentionally outside the identity API boundary.
    assert build_hybrid_run_id(identity, sample_index=1) == build_hybrid_run_id(identity, sample_index=1)


def test_identity_mapping_round_trip_and_schema_fail_closed() -> None:
    identity = _identity()
    assert HybridExperimentIdentity.from_mapping(identity.to_mapping()) == identity
    with pytest.raises(ValueError, match="HYBRID_IDENTITY_SCHEMA_INVALID"):
        HybridExperimentIdentity.from_mapping({**identity.to_mapping(), "unexpected": True})
    with pytest.raises(ValueError, match="HYBRID_IDENTITY_FIELD_INVALID"):
        HybridExperimentIdentity.from_mapping({**identity.to_mapping(), "timeout_seconds": True})


def test_evidence_run_id_recomputes_and_rejects_tampering() -> None:
    from character_intelligence.hybrid_ir import FakeProvider
    from tests.test_hybrid_ir_contract import _evaluation_context, _generic_ir

    result = run_fake_pipeline(
        FakeProvider(_generic_ir().to_mapping()),
        _context(),
        _evaluation_context(),
        repo_root=ROOT,
        sample_index=1,
    )
    payload = result.evidence.to_mapping()
    validate_hybrid_evidence(payload)
    assert payload["sample_index"] == 1
    assert payload["run_id"] == build_hybrid_run_id(
        HybridExperimentIdentity.from_mapping(payload["identity"]), sample_index=1
    )
    for field in (
        "source_commit",
        "model_facing_contract_digest",
        "compiler_version",
        "provider",
        "model",
    ):
        tampered = {**payload, "identity": {**payload["identity"], field: f"tampered-{field}"}}
        with pytest.raises(ValueError, match="HYBRID_IDENTITY_MISMATCH"):
            validate_hybrid_evidence(tampered)
    with pytest.raises(ValueError, match="HYBRID_IDENTITY_MISMATCH"):
        validate_hybrid_evidence({**payload, "sample_index": 2})
    tampered_run = {**payload, "run_id": payload["run_id"].replace("-01-", "-02-")}
    with pytest.raises(ValueError, match="HYBRID_IDENTITY_MISMATCH"):
        validate_hybrid_evidence(tampered_run)


def test_hybrid_dry_run_exposes_identity_bound_next_sample_without_provider() -> None:
    result = HybridSemanticIRRunner(ROOT, _context()).dry_run()
    identity = HybridExperimentIdentity.from_mapping(result["identity"])
    assert result["sample_index"] == 1
    assert result["run_id"] == build_hybrid_run_id(identity, sample_index=1)
    assert result["target_sample_count"] == 1
    assert result["existing_sample_count"] == 0
    assert result["existing_sample_indexes"] == []
    assert result["next_sample_index"] == 1
    assert result["remaining_sample_count"] == 1
    assert result["complete"] is False
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["transport_attempts"] == 0


def test_frozen_h2_request_digest_remains_unchanged() -> None:
    request = build_model_facing_request(_context())
    wide = build_model_facing_request(HybridGenerationContext("Design a support ability"))
    assert request.metrics.total_chars == 1032
    assert request.metrics.total_bytes == 1032
    assert request.contract.digest == "8716a5770d4b1d12c92c546990b5274d7de4f95528cbd06445540a404efa806b"
    assert wide.metrics.total_chars == 1181
    assert wide.metrics.total_bytes == 1181
