"""Offline tests for the formal Hybrid H3 live executor seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_intelligence.hybrid_ir.runner as hybrid_runner
from character_intelligence.compiler import SemanticMappingRegistry
from character_intelligence.hybrid_ir import (
    HybridGenerationContext,
    HybridProviderInvocationError,
    HybridSemanticIRRunner,
    OpenCodeGoHybridProvider,
    validate_hybrid_evidence,
)
from character_intelligence.semantic_ir import SEMANTIC_IR_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _offline_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep injected fake-provider tests independent of host credentials."""

    monkeypatch.setenv("NPC_LLM_API_KEY", "offline-test-key")


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


def _ir() -> dict[str, object]:
    return {
        "ir_version": SEMANTIC_IR_VERSION,
        "ability_name": "Support Echo",
        "summary": "Enable an ally after invocation.",
        "mode": "active",
        "role": "support",
        "centrality": "core",
        "mechanic": {
            "trigger": {"actor": "self", "event": "ability_invoked", "qualifier": None},
            "effect": {"actor": "ally", "intent": "enable_ally", "description": "Support an ally."},
            "feedback": {
                "event": "effect_resolved",
                "relation": "enables",
                "response_trigger": {"actor": "ally", "event": "feedback_received", "qualifier": None},
                "response_effect": {"actor": "ally", "intent": "enable_ally", "description": "Continue support."},
            },
        },
        "role_path": {
            "trigger": {"actor": "self", "event": "ability_invoked", "qualifier": None},
            "effect": {"actor": "ally", "intent": "enable_ally", "description": "Support an ally."},
        },
    }


def _evaluation_context() -> dict[str, object]:
    return {
        "intent": {
            "mechanic_requirements": [
                {
                    "requirement_id": "req_support",
                    "trigger": {"subject_kinds": ["self"], "events": ["ability_invoked"], "source_kinds": []},
                    "effect": {"subject_kinds": ["ally"], "operations": ["ally_enablement"], "object_kinds": []},
                    "feedback": {"required": True, "events": ["effect_resolved"], "operations": ["enables"]},
                }
            ],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "reference_review_context": None,
    }


class CountingProvider:
    def __init__(self, response: object, *, error: str | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0
        self.transport_attempts = 0
        self.latency_ms = 1.0
        self.outcome = "NOT_CALLED"
        self.request_text: str | None = None

    def complete(self, request_text: str) -> object:
        self.calls += 1
        self.transport_attempts += 1
        self.request_text = request_text
        if self.error is not None:
            self.outcome = self.error
            raise HybridProviderInvocationError(self.error)
        self.outcome = "SUCCESS"
        return self.response


def test_shared_opencode_transport_adapter_is_single_attempt_and_json_object() -> None:
    from agents.provider_protocol import ProviderCompletion

    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def complete(self, **kwargs: object) -> ProviderCompletion:
            self.calls.append(kwargs)
            return ProviderCompletion(text='{"status":"ok"}')

    client = Client()
    provider = OpenCodeGoHybridProvider(client, model="deepseek-v4-pro", timeout_seconds=60)
    assert provider.complete("frozen request") == '{"status":"ok"}'
    assert provider.calls == 1 and provider.transport_attempts == 1
    assert provider.outcome == "SUCCESS"
    assert client.calls[0]["model"] == "deepseek-v4-pro"
    assert client.calls[0]["timeout_seconds"] == 60
    assert client.calls[0]["response_contract"].mode.value == "json_object"


def test_shared_opencode_transport_adapter_maps_timeout_without_raw_error() -> None:
    from agents.provider_protocol import ProviderClientError

    class Client:
        def complete(self, **_: object) -> object:
            raise ProviderClientError("timeout", retryable=False)

    provider = OpenCodeGoHybridProvider(Client(), model="deepseek-v4-pro", timeout_seconds=60)
    with pytest.raises(HybridProviderInvocationError, match="TIMEOUT"):
        provider.complete("frozen request")
    assert provider.calls == 1 and provider.transport_attempts == 1
    assert provider.outcome == "TIMEOUT"


def _run(provider: CountingProvider, tmp_path: Path, **kwargs: object):
    return HybridSemanticIRRunner(ROOT, _context()).run_live(
        _evaluation_context(),
        provider_factory=lambda: provider,
        output_path=tmp_path / "hybrid.json",
        enforce_clean_tree=False,
        **kwargs,
    )


def test_formal_executor_fake_pass_reaches_evaluator_once(tmp_path: Path) -> None:
    provider = CountingProvider(_ir())
    result = _run(provider, tmp_path)
    assert result.status == "HYBRID_SEMANTIC_IR_END_TO_END_PASS"
    assert result.consumed is True
    assert result.provider_factory_constructed is True
    assert (result.provider_called, result.transport_attempts) == (True, 1)
    assert result.stages == {
        "provider": "PASS", "json": "PASS", "ir_parse": "PASS", "ir_validation": "PASS",
        "compiler": "PASS", "canonical_parser": "PASS", "reference_integrity": "PASS", "evaluator": "PASS",
    }
    assert result.report is not None and result.report.outcome == "PASS"
    assert result.evidence_path is not None and result.evidence_path.exists()
    evidence_payload = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    validate_hybrid_evidence(evidence_payload)
    serialized = json.dumps(evidence_payload, ensure_ascii=False)
    assert '"candidate"' not in serialized
    assert "Support Echo" not in serialized
    assert "Support an ally." not in serialized
    assert provider.request_text is not None and len(provider.request_text) == 1032


@pytest.mark.parametrize(
    ("response", "error", "status", "layer"),
    [
        (None, "TIMEOUT", "HYBRID_SEMANTIC_IR_UNAVAILABLE", "PROVIDER"),
        (None, "TRANSPORT_FAILURE", "HYBRID_SEMANTIC_IR_UNAVAILABLE", "PROVIDER"),
        ("{bad", None, "HYBRID_SEMANTIC_IR_JSON_REJECTED", "JSON"),
        ({"ir_version": SEMANTIC_IR_VERSION}, None, "HYBRID_SEMANTIC_IR_IR_REJECTED", "IR_PARSE"),
        ({**_ir(), "mode": "invalid"}, None, "HYBRID_SEMANTIC_IR_IR_REJECTED", "IR_VALIDATION"),
    ],
)
def test_formal_executor_first_failure_is_deterministic(
    response: object, error: str | None, status: str, layer: str, tmp_path: Path
) -> None:
    provider = CountingProvider(response, error=error)
    result = _run(provider, tmp_path)
    assert result.status == status
    assert result.first_failure_layer == layer
    assert result.consumed is True
    assert provider.calls == 1 and provider.transport_attempts == 1
    assert result.evidence_path is not None
    ordered = list(result.stages)
    failure_index = ordered.index(layer.lower())
    assert all(value == "PASS" for value in list(result.stages.values())[:failure_index])
    assert list(result.stages.values())[failure_index] == "FAIL"
    assert all(value == "NOT_REACHED" for value in list(result.stages.values())[failure_index + 1 :])


def test_compiler_parser_reference_and_evaluator_failures_are_attributed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _run(
        CountingProvider(_ir()),
        tmp_path,
        # The registry is a deterministic injected compiler failure.
        compiler_registry=SemanticMappingRegistry(effect_operations={}),
    )
    assert compiler.first_failure_layer == "COMPILER"

    original_parse_candidate = hybrid_runner.parse_candidate
    original_validate_refs = hybrid_runner.validate_reference_integrity
    monkeypatch.setattr(hybrid_runner, "parse_candidate", lambda _: (_ for _ in ()).throw(ValueError("hidden")))
    parser = _run(CountingProvider(_ir()), tmp_path / "parser")
    assert parser.first_failure_layer == "CANONICAL_PARSER"

    monkeypatch.setattr(hybrid_runner, "parse_candidate", original_parse_candidate)
    monkeypatch.setattr(
        hybrid_runner,
        "validate_reference_integrity",
        lambda _: (_ for _ in ()).throw(hybrid_runner.SkillKitCompilerError("HIDDEN", "candidate", "hidden")),
    )
    refs = _run(CountingProvider(_ir()), tmp_path / "refs")
    assert refs.first_failure_layer == "REFERENCE_INTEGRITY"

    monkeypatch.setattr(hybrid_runner, "validate_reference_integrity", original_validate_refs)
    failing_context = _evaluation_context()
    failing_context["combat_role_profile"] = {"primary_role": "control", "secondary_roles": []}
    evaluator = HybridSemanticIRRunner(ROOT, _context()).run_live(
        failing_context,
        provider_factory=lambda: CountingProvider(_ir()),
        output_path=tmp_path / "evaluator" / "hybrid.json",
        enforce_clean_tree=False,
    )
    assert evaluator.first_failure_layer == "EVALUATOR"
    assert evaluator.status == "HYBRID_SEMANTIC_IR_EVALUATOR_REJECTED"
    assert evaluator.report is not None and evaluator.report.outcome == "FAIL"


@pytest.mark.parametrize("kwargs", [{"sample_index": 2}, {"expected_run_id": "old-run-id"}])
def test_pre_provider_identity_gates_do_not_construct_provider(tmp_path: Path, kwargs: dict[str, object]) -> None:
    calls = 0

    def factory() -> CountingProvider:
        nonlocal calls
        calls += 1
        return CountingProvider(_ir())

    result = HybridSemanticIRRunner(ROOT, _context()).run_live(
        _evaluation_context(), provider_factory=factory, output_path=tmp_path / "hybrid.json", enforce_clean_tree=False, **kwargs
    )
    expected_status = "BLOCKED_INVALID_HYBRID_COHORT_STATE" if "sample_index" in kwargs else "BLOCKED_HYBRID_IDENTITY_DRIFT"
    assert result.status == expected_status
    assert calls == 0 and result.consumed is False and result.evidence_path is None


def test_pre_provider_request_credential_and_cohort_gates_are_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory_calls = 0

    def factory() -> CountingProvider:
        nonlocal factory_calls
        factory_calls += 1
        return CountingProvider(_ir())

    drift = HybridSemanticIRRunner(ROOT, HybridGenerationContext("different brief" )).run_live(
        _evaluation_context(), provider_factory=factory, output_path=tmp_path / "drift.json", enforce_clean_tree=False
    )
    assert drift.status == "BLOCKED_HYBRID_REQUEST_DRIFT"
    monkeypatch.delenv("NPC_LLM_API_KEY", raising=False)
    missing = HybridSemanticIRRunner(ROOT, _context()).run_live(
        _evaluation_context(), provider_factory=factory, output_path=tmp_path / "missing.json", enforce_clean_tree=False
    )
    assert missing.status == "BLOCKED_PROVIDER_CREDENTIAL_MISSING"
    complete = HybridSemanticIRRunner(ROOT, _context(), existing_sample_indexes=(1,)).run_live(
        _evaluation_context(), provider_factory=factory, output_path=tmp_path / "complete.json", enforce_clean_tree=False
    )
    assert complete.status == "COHORT_ALREADY_COMPLETE"
    assert factory_calls == 0


def test_dirty_tracked_source_blocks_before_factory(tmp_path: Path) -> None:
    calls = 0

    def factory() -> CountingProvider:
        nonlocal calls
        calls += 1
        return CountingProvider(_ir())

    result = HybridSemanticIRRunner(ROOT, _context()).run_live(
        _evaluation_context(),
        provider_factory=factory,
        output_path=tmp_path / "dirty.json",
        enforce_clean_tree=True,
    )
    # This implementation tree is intentionally dirty while the test is run;
    # the gate must reject before constructing any provider adapter.
    assert result.status == "BLOCKED_SOURCE_BASELINE_DRIFT"
    assert calls == 0 and result.consumed is False


def test_complete_cohort_blocks_second_formal_execution(tmp_path: Path) -> None:
    first_provider = CountingProvider(_ir())
    output = tmp_path / "cohort.json"
    first = HybridSemanticIRRunner(ROOT, _context()).run_live(
        _evaluation_context(), provider_factory=lambda: first_provider, output_path=output, enforce_clean_tree=False
    )
    assert first.consumed is True and first_provider.calls == 1
    second_provider = CountingProvider(_ir())
    second = HybridSemanticIRRunner(ROOT, _context(), existing_sample_indexes=(1,)).run_live(
        _evaluation_context(), provider_factory=lambda: second_provider, output_path=output, enforce_clean_tree=False
    )
    assert second.status == "COHORT_ALREADY_COMPLETE"
    assert second_provider.calls == 0 and second.provider_factory_constructed is False
