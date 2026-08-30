from __future__ import annotations

# Dynamic loading keeps the direct script import path under test.
# ruff: noqa: I001

import importlib.util
import io
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from character_intelligence.hybrid_ir import runner as hybrid_runner
from character_intelligence.hybrid_ir import (
    build_model_facing_request,
    detect_output_language,
    resolve_output_language,
)
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

CHINESE_PASSIVE = {
    "ir_version": "semantic-skill-plan-ir/0.2.0",
    "ability_name": "不屈支援",
    "summary": "常驻支援队伍并帮助队友稳定作战。",
    "mode": "passive",
    "role": "support",
    "centrality": "core",
    "mechanic": {
        "kind": "passive",
        "persistence": "always_on",
        "effect": {
            "actor": "team",
            "intent": "enable_ally",
            "description": "持续支援队伍。",
        },
    },
    "role_path": {
        "kind": "passive",
        "effect": {
            "actor": "team",
            "intent": "enable_ally",
            "description": "体现辅助职责。",
        },
    },
}


def _valid_triggered() -> dict[str, object]:
    return {
        "ir_version": "semantic-skill-plan-ir/0.2.0",
        "ability_name": "Guardian Intercept",
        "summary": "An ally reaction protects the team.",
        "mode": "reaction",
        "role": "defense",
        "centrality": "core",
        "mechanic": {
            "kind": "triggered",
            "trigger": {"actor": "ally", "event": "damage_received", "qualifier": None},
            "effect": {
                "actor": "ally",
                "intent": "protect_ally",
                "description": "Protect the damaged ally.",
            },
            "feedback": None,
        },
        "role_path": {
            "kind": "triggered",
            "trigger": {"actor": "ally", "event": "damage_received", "qualifier": None},
            "effect": {
                "actor": "ally",
                "intent": "protect_ally",
                "description": "Provide defense role evidence.",
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


def test_auto_language_detection_and_explicit_override_are_deterministic():
    assert detect_output_language("设计一个常驻辅助技能") == "zh-CN"
    assert detect_output_language("Design an always-on support passive.") == "en"
    assert resolve_output_language("en", "设计一个常驻辅助技能") == "en"
    assert resolve_output_language("zh-CN", "Design a support passive.") == "zh-CN"


def test_generation_request_has_prose_language_directive_without_ir_language_field():
    chinese = playground.build_playground_context("support", "passive", "设计一个常驻辅助技能")
    english = playground.build_playground_context("support", "passive", "Design a support passive.")
    chinese_request = build_model_facing_request(chinese, language="zh-CN")
    english_request = build_model_facing_request(english, language="en")

    assert "Human-readable prose: Simplified Chinese (zh-CN)." in chinese_request.text
    assert chinese_request.text.count("Human-readable prose:") == 1
    assert "Human-readable prose: English (en)." in english_request.text
    assert english_request.text.count("Human-readable prose:") == 1
    assert "output_language=" not in chinese_request.text
    assert '"language"' not in chinese_request.text
    assert "设计一个常驻辅助技能" in chinese_request.text
    assert chinese_request.contract.version == "semantic-skill-plan-ir-contract/0.7.3"
    assert "valid semantic subjects for the main effect and its role-path proof in this request are: ally, team." in chinese_request.case_text
    assert "effect_subject_kinds" not in chinese_request.text
    assert "MECHANIC_SKELETON" not in chinese_request.text


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


def test_chinese_fake_e2e_localizes_presentation_but_keeps_protocol_values():
    class CaptureProvider(FakeProvider):
        def __init__(self, response):
            super().__init__(response)
            self.requests: list[str] = []

        def complete(self, request_text):
            self.requests.append(request_text)
            return super().complete(request_text)

    provider = CaptureProvider(CHINESE_PASSIVE)
    result = playground.execute_playground(
        provider,
        "support",
        "passive",
        "设计一个辅助角色的常驻核心被动。",
        language="auto",
        repo_root=ROOT,
    )
    output = io.StringIO()
    playground.render_result(
        result,
        "support",
        "passive",
        language="zh-CN",
        output=output,
    )

    rendered = output.getvalue()
    assert result.final.evidence.evaluator_outcome == "PASS"
    assert len(provider.requests) == 1
    assert "Human-readable prose: Simplified Chinese (zh-CN)." in provider.requests[0]
    assert "valid semantic subjects for the main effect and its role-path proof in this request are: ally, team." in provider.requests[0]
    assert '"role": "support"' not in provider.requests[0]
    assert "=== 技能设计结果 ===" in rendered
    assert "角色定位： 辅助" in rendered
    assert "技能模式： 被动" in rendered
    assert "技能名称： 不屈支援" in rendered
    assert "队伍 / 队友支援：" in rendered
    assert "评估结果： 通过" in rendered
    assert "修复： 无需修复" in rendered


def test_chinese_protocol_values_are_required_and_chinese_enums_fail_validation():
    from character_intelligence.semantic_ir import (
        SemanticIRValidationError,
        parse_semantic_ir,
        validate_skill_semantic_ir,
    )

    parsed = parse_semantic_ir(CHINESE_PASSIVE)
    assert parsed.role == "support"
    assert parsed.mode == "passive"
    invalid = deepcopy(CHINESE_PASSIVE)
    invalid["role"] = "辅助"
    invalid["mode"] = "被动"
    with pytest.raises(SemanticIRValidationError):
        validate_skill_semantic_ir(parse_semantic_ir(invalid))


def test_repair_inherits_chinese_language_without_translation_call():
    invalid = deepcopy(CHINESE_PASSIVE)
    invalid["role"] = "main_dps"
    invalid["mechanic"]["effect"] = {
        "actor": "enemy",
        "intent": "deal_damage",
        "description": "错误的输出职责。",
    }
    invalid["role_path"]["effect"] = {
        "actor": "enemy",
        "intent": "deal_damage",
        "description": "错误的职责证明。",
    }

    class SequenceProvider:
        def __init__(self):
            self.calls = 0
            self.transport_attempts = 0
            self.requests: list[str] = []
            self.latency_ms = 0.0
            self.outcome = "NOT_CALLED"

        def complete(self, request_text):
            self.calls += 1
            self.transport_attempts += 1
            self.requests.append(request_text)
            self.outcome = "SUCCESS"
            return invalid if self.calls == 1 else CHINESE_PASSIVE

    provider = SequenceProvider()
    result = playground.execute_playground(
        provider,
        "support",
        "passive",
        "设计一个辅助角色的常驻核心被动。",
        language="auto",
        repair_decider=lambda: True,
        repo_root=ROOT,
    )

    assert result.repair_status == "SUCCESS"
    assert result.final.evidence.evaluator_outcome == "PASS"
    assert provider.calls == 2
    directive = "Human-readable prose: Simplified Chinese (zh-CN)."
    assert all(request.count(directive) == 1 for request in provider.requests)
    assert all("Write ability names, summaries, descriptions" not in request for request in provider.requests)
    assert "不屈支援" == result.final.candidate.entries[0].name


def test_structural_ir_parse_failure_never_offers_repair():
    provider = FakeProvider({"not": "a skill plan"})
    result = _run(provider, repair_decider=lambda: (_ for _ in ()).throw(AssertionError("offered")))

    assert result.initial.evidence.first_failure_layer == "IR_PARSE"
    assert result.repair is None
    assert result.repair_status == "UNAVAILABLE"
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("variant", "role", "mode", "expected_code"),
    (
        ("unknown_field", "support", "passive", "IR_UNKNOWN_FIELD"),
        ("missing_trigger", "defense", "reaction", "IR_MISSING_REQUIRED_FIELD"),
        ("wrong_discriminator", "support", "passive", "IR_WRONG_TYPE"),
        ("triggered_passive_field", "defense", "reaction", "IR_UNKNOWN_FIELD"),
        ("passive_trigger", "support", "passive", "IR_UNKNOWN_FIELD"),
        ("passive_feedback", "support", "passive", "IR_UNKNOWN_FIELD"),
    ),
)
def test_v2_ir_parse_classifications_are_safe(variant, role, mode, expected_code):
    payload = deepcopy(VALID_PASSIVE if mode == "passive" else _valid_triggered())
    if variant == "unknown_field":
        payload["raw_marker"] = "DO_NOT_PRINT"
    elif variant == "missing_trigger":
        del payload["mechanic"]["trigger"]
    elif variant == "wrong_discriminator":
        payload["mechanic"]["kind"] = "unknown_variant"
    elif variant == "triggered_passive_field":
        payload["mechanic"]["persistence"] = "always_on"
    elif variant == "passive_trigger":
        payload["mechanic"]["trigger"] = {
            "actor": "self",
            "event": "ability_invoked",
            "qualifier": None,
        }
    elif variant == "passive_feedback":
        payload["mechanic"]["feedback"] = None

    result = _run(FakeProvider(payload), role=role, mode=mode)

    assert result.initial.evidence.first_failure_layer == "IR_PARSE"
    assert result.initial.evidence.failure_code == expected_code


def test_invalid_passive_persistence_is_validation_not_parse():
    payload = deepcopy(VALID_PASSIVE)
    payload["mechanic"]["persistence"] = "sometimes"

    result = _run(FakeProvider(payload))

    assert result.initial.evidence.first_failure_layer == "IR_VALIDATION"
    assert result.initial.evidence.failure_code == "IR_INVALID_SEMANTIC_VALUE"


def test_safe_debug_shows_pipeline_and_parse_classification_without_raw_material():
    payload = deepcopy(VALID_PASSIVE)
    payload["raw_marker"] = "RAW_RESPONSE_SENTINEL"
    provider = FakeProvider(payload)
    execution = _run(provider)
    output = io.StringIO()

    playground.render_result(
        execution,
        "support",
        "passive",
        show_safe_debug=True,
        provider=provider,
        output=output,
    )
    text = output.getvalue()

    assert "Pipeline:\n" in text
    assert "  PROVIDER: PASS" in text
    assert "  IR_PARSE: FAIL" in text
    assert "  IR_VALIDATION: NOT_REACHED" in text
    assert "  COMPILER: NOT_REACHED" in text
    assert "  EVALUATOR: NOT_REACHED" in text
    assert "Parse classification: IR_UNKNOWN_FIELD" in text
    assert "RAW_RESPONSE_SENTINEL" not in text
    assert "semantic-skill-plan-ir/0.2.0" not in text
    assert "NPC_LLM_API_KEY" not in text


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
    output = io.StringIO()
    playground.render_result(
        result,
        "support",
        "passive",
        show_safe_debug=True,
        provider=None,
        output=output,
    )
    assert "Provider classification: PROVIDER_TRANSPORT_FAILURE" in output.getvalue()


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


def test_cli_help_exposes_language_option(capsys):
    with pytest.raises(SystemExit) as error:
        playground.main(["--help"])

    assert error.value.code == 0
    captured = capsys.readouterr().out
    assert "--language {auto,zh-CN,en}" in captured
    assert "auto follows" in captured
    assert "Chinese/English user input" in captured


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
