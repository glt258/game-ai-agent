from __future__ import annotations

# Dynamic loading keeps the direct script import path under test.
# ruff: noqa: I001

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from character_intelligence.hybrid_ir import runner as hybrid_runner
from character_intelligence.hybrid_ir.runner import FakeProvider, HybridProviderInvocationError



ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skill_playground", ROOT / "scripts" / "skill_playground.py")
assert SPEC is not None and SPEC.loader is not None
playground = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = playground
SPEC.loader.exec_module(playground)


VALID_PASSIVE = {
    "ir_version": "semantic-skill-plan-ir/0.2.0",
    "ability_name": "Steady Formation",
    "summary": "An always-on team support trait.",
    "mode": "passive",
    "role": "support",
    "centrality": "core",
    "mechanic": {
        "kind": "passive",
        "persistence": "always_on",
        "effect": {
            "actor": "team",
            "intent": "enable_ally",
            "description": "Provide an always-on team enablement trait.",
        },
    },
    "role_path": {
        "kind": "passive",
        "effect": {
            "actor": "team",
            "intent": "enable_ally",
            "description": "Provide passive support role evidence.",
        },
    },
}


def _run(provider, *, repair_decider=None, role="support", mode="passive"):
    return playground.execute_playground(
        provider,
        role,
        mode,
        "Design a concise skill that helps the team survive.",
        repair_decider=repair_decider,
        repo_root=ROOT,
    )


def test_initial_pass_does_not_repair():
    provider = FakeProvider(VALID_PASSIVE)
    result = _run(provider)

    assert result.final.evidence.evaluator_outcome == "PASS"
    assert result.repair is None
    assert result.repair_status == "NOT_NEEDED"
    assert provider.calls == 1
    assert result.initial.evidence.run_id.startswith("manual-playground-")


def test_evaluator_fail_can_use_one_bounded_repair():
    invalid_role = {
        **VALID_PASSIVE,
        "role": "main_dps",
        "mechanic": {
            **VALID_PASSIVE["mechanic"],
            "effect": {
                "actor": "enemy",
                "intent": "deal_damage",
                "description": "Deal damage instead of supporting the team.",
            },
        },
        "role_path": {
            **VALID_PASSIVE["role_path"],
            "effect": {
                "actor": "enemy",
                "intent": "deal_damage",
                "description": "Provide damage role evidence.",
            },
        },
    }

    class SequenceProvider:
        def __init__(self):
            self.model = "deepseek-v4-flash"
            self.calls = 0
            self.transport_attempts = 0
            self.latency_ms = 0.0
            self.outcome = "NOT_CALLED"

        def complete(self, request_text):
            self.calls += 1
            self.transport_attempts += 1
            self.outcome = "SUCCESS"
            return invalid_role if self.calls == 1 else json.dumps(VALID_PASSIVE)

    provider = SequenceProvider()
    result = playground.execute_playground(
        provider,
        "support",
        "passive",
        "Design a concise skill that helps the team survive.",
        model="deepseek-v4-flash",
        repair_decider=lambda: True,
        repo_root=ROOT,
    )

    assert result.initial.evidence.first_failure_layer == "EVALUATOR"
    assert result.initial.evidence.evaluator_outcome == "FAIL"
    assert result.repair_status == "SUCCESS"
    assert result.final.evidence.evaluator_outcome == "PASS"
    assert result.repair is not None and result.repair.repair_attempts == 1
    assert provider.calls == 2
    assert result.initial.evidence.identity.model == "deepseek-v4-flash"
    assert result.final.evidence.identity.model == "deepseek-v4-flash"


def test_structural_ir_parse_failure_never_offers_repair():
    provider = FakeProvider({"not": "a skill plan"})
    result = _run(provider, repair_decider=lambda: (_ for _ in ()).throw(AssertionError("offered")))

    assert result.initial.evidence.first_failure_layer == "IR_PARSE"
    assert result.repair is None
    assert result.repair_status == "UNAVAILABLE"
    assert provider.calls == 1


def test_provider_unavailable_is_safe_and_does_not_repair():
    class Unavailable:
        calls = 0
        transport_attempts = 0
        latency_ms = None
        outcome = "NOT_CALLED"

        def complete(self, request_text):
            del request_text
            self.calls += 1
            self.transport_attempts += 1
            raise HybridProviderInvocationError("TRANSPORT_FAILURE")

    result = _run(Unavailable(), repair_decider=lambda: (_ for _ in ()).throw(AssertionError("offered")))

    assert result.initial.evidence.first_failure_layer == "PROVIDER"
    assert result.repair_status == "UNAVAILABLE"


def test_passive_context_uses_real_passive_capability_without_trigger():
    context = playground.build_playground_context("support", "passive", "always help the team")
    evaluation = playground.build_playground_evaluation_context("support", "passive")

    assert context.contract_profile == "generalization_v2"
    assert context.allowed_trigger_events is None
    requirement = evaluation["intent"]["mechanic_requirements"][0]
    assert requirement["mechanic_kind"] == "passive"
    assert "trigger" not in requirement


def test_cli_missing_credential_reveals_only_status(monkeypatch, capsys):
    monkeypatch.delenv("NPC_LLM_API_KEY", raising=False)
    exit_code = playground.main(
        ["--role", "support", "--mode", "passive", "--prompt", "help the team"],
    )

    captured = capsys.readouterr().out
    assert exit_code == 2
    assert "NPC_LLM_API_KEY=MISSING" in captured
    assert "NPC_LLM_API_KEY=<" not in captured
    assert "sk-" not in captured.lower()


def test_cli_default_model_is_passed_to_provider_factory(monkeypatch):
    monkeypatch.setenv("NPC_LLM_API_KEY", "test-only")
    captured: dict[str, str] = {}

    def factory(model):
        captured["model"] = model
        return FakeProvider(VALID_PASSIVE)

    monkeypatch.setattr(playground, "_default_hybrid_provider_factory", factory)
    output = io.StringIO()
    assert playground.main(
        ["--role", "support", "--mode", "passive", "--prompt", "help the team"],
        output=output,
    ) == 0
    assert captured["model"] == "deepseek-v4-pro"


def test_cli_flash_model_is_passed_and_safe_debug_is_accurate(monkeypatch):
    monkeypatch.setenv("NPC_LLM_API_KEY", "test-only")
    captured: dict[str, str] = {}

    def factory(model):
        captured["model"] = model
        return FakeProvider(VALID_PASSIVE)

    monkeypatch.setattr(playground, "_default_hybrid_provider_factory", factory)
    output = io.StringIO()
    assert playground.main(
        [
            "--role",
            "support",
            "--mode",
            "passive",
            "--prompt",
            "help the team",
            "--model",
            "deepseek-v4-flash",
            "--show-safe-debug",
        ],
        output=output,
    ) == 0
    assert captured["model"] == "deepseek-v4-flash"
    assert "Provider: opencode_go / deepseek-v4-flash" in output.getvalue()
    assert "deepseek-v4-pro" not in output.getvalue()


def test_default_factory_forwards_model_to_existing_provider_config(monkeypatch):
    captured: dict[str, str] = {}

    class StubSettings:
        api_key = "test-only"
        base_url = None
        timeout_seconds = 60
        model = "deepseek-v4-flash"
        profile = SimpleNamespace(provider_options={})

        @classmethod
        def from_environment(cls, environment):
            captured.update(environment)
            return cls

    class StubClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agents.model_factory.LiveLLMSettings", StubSettings)
    monkeypatch.setattr("agents.openai_provider.OpenAIChatClient", StubClient)
    provider = hybrid_runner._default_hybrid_provider_factory(model="deepseek-v4-flash")

    assert captured["NPC_LLM_PROVIDER"] == "opencode_go"
    assert captured["NPC_LLM_MODEL"] == "deepseek-v4-flash"
    assert provider._model == "deepseek-v4-flash"
    assert provider.calls == 0
    assert provider.transport_attempts == 0


def test_manual_execution_does_not_write_formal_evidence():
    before = {path.name for path in (ROOT / "evals" / "results").glob("manual-playground-*")}
    _run(FakeProvider(VALID_PASSIVE))
    after = {path.name for path in (ROOT / "evals" / "results").glob("manual-playground-*")}
    assert after == before
