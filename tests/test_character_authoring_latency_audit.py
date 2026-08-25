from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from agents import (
    CharacterDesignRequest,
    DeterministicCharacterGenerationModel,
    DeterministicCharacterRepairModel,
    ModelInvocationAudit,
    ModelProviderError,
    ModelTurn,
    ModelUsage,
    ToolCall,
)
from agents.official_character_authoring import ReferenceGrounding

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_live_character_authoring_latency.py"
)
_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "audit_live_character_authoring_latency", _SCRIPT_PATH
)
assert _SCRIPT_SPEC is not None and _SCRIPT_SPEC.loader is not None
_SCRIPT_MODULE = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(_SCRIPT_MODULE)
audit_live_character_authoring = _SCRIPT_MODULE.audit_live_character_authoring


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value

    def advance_ms(self, value: float) -> None:
        self.value += value / 1000.0


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "draft_id": "draft_latency_001",
        "status": "draft",
        "canonical_character_id": None,
        "name": "审计角色",
        "age": 23,
        "age_range": "20-25",
        "gender": "女性",
        "faction_id": None,
        "occupation": "学生",
        "social_role": "校园志愿者",
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "design_pitch": "一名有限辅助型角色。",
        "personality": ["冷静"],
        "background": "她在校园与社区活动中逐渐形成了谨慎处理复杂关系的习惯。",
        "story_hook": "她只提供有限的现场协助。",
        "relationships": [],
        "ability_concept": "提供有限的行动节奏提示，不能替代专业训练。",
        "knowledge_scope": "仅接触公开信息。",
        "canon_basis": [],
        "new_design_elements": [
            "new_design:occupation: 职业是新设计",
            "new_design:social_role: 社会角色是新设计",
            "new_design:design_pitch: 角色概念是新设计",
            "new_design:personality: 性格是新设计",
            "new_design:background: 背景是新设计",
            "new_design:story_hook: 故事钩子是新设计",
            "new_design:ability_concept: 能力概念是新设计",
            "new_design:knowledge_scope: 知识范围是新设计",
        ],
        "open_questions": ["MODEL_OUTPUT_SECRET_OPEN_QUESTION"],
        "constraint_notes": [],
        "story_link": None,
        "proposed_new_content": [],
    }
    payload.update(overrides)
    return payload


def _grounding_loader(clock: FakeClock) -> Callable[[str], ReferenceGrounding]:
    def load(_brief: str) -> ReferenceGrounding:
        clock.advance_ms(3)
        return ReferenceGrounding(
            corpus_baseline_id="test-baseline",
            manifest_schema_version="test-schema",
            total_records=4,
            selected=(
                {
                    "reference_id": "reference-secret-id",
                    "display_name": "REFERENCE_CONTENT_SECRET",
                },
            ),
        )

    return load


class ScriptedModel:
    def __init__(self, clock: FakeClock, turns: list[tuple[ModelTurn, float, int]]) -> None:
        self.clock = clock
        self.turns = list(turns)
        self.prompts = []

    def generate(self, prompt) -> ModelTurn:
        self.prompts.append(prompt)
        if not self.turns:
            raise AssertionError("scripted model exhausted")
        turn, latency_ms, retry_count = self.turns.pop(0)
        self.clock.advance_ms(latency_ms)
        invocation = ModelInvocationAudit(
            session_id=prompt.session_id,
            turn_number=prompt.turn_number,
            provider="fake-provider",
            model="fake-model",
            outcome="success",
            latency_ms=latency_ms,
            retry_count=retry_count,
            tool_call_count=len(turn.tool_calls),
            usage=ModelUsage(10, 5, 15),
            transport="fake-transport",
            response_contract=(
                "text"
                if prompt.response_format == "character_authoring_action"
                else "json_object"
            ),
            purpose=prompt.invocation_purpose,
        )
        return replace(turn, invocation=invocation)


def _pass_model(clock: FakeClock) -> ScriptedModel:
    return ScriptedModel(
        clock,
        [
            (
                ModelTurn(
                    tool_calls=(
                        ToolCall("tool-1", "get_world_rules", {}),
                    )
                ),
                4,
                0,
            ),
            (
                ModelTurn(
                    tool_calls=(
                        ToolCall(
                            "tool-2",
                            "search_lore",
                            {"query": "TOOL_QUERY_SECRET", "limit": 1},
                        ),
                    )
                ),
                5,
                1,
            ),
            (ModelTurn(text="FINALIZE"), 6, 0),
            (ModelTurn(structured_output=_payload()), 7, 2),
        ],
    )


def test_pass_audit_measures_rounds_retries_and_keeps_repair_absent() -> None:
    clock = FakeClock()
    model = _pass_model(clock)
    request = CharacterDesignRequest(
        "PROMPT_SECRET: 设计一个完全原创的辅助角色。",
        request_id="latency_pass_001",
    )

    report = audit_live_character_authoring(
        request,
        model=model,
        reference_loader=_grounding_loader(clock),
        clock=clock,
    )

    assert report["status"] == "passed"
    assert report["retrieval_strategy"] == "model_loop"
    assert [item["classification"] for item in report["invocations"]] == [
        "retrieval_action",
        "retrieval_action",
        "retrieval_action",
        "finalization",
    ]
    assert report["counts"]["logical_llm_calls"] == 4
    assert report["counts"]["network_attempts"] == 7
    assert [item["network_attempts"] for item in report["invocations"]] == [1, 2, 1, 3]
    assert all(
        item["provider_status_code"] is None
        and item["provider_retryable"] is None
        for item in report["invocations"]
    )
    assert len(report["tools"]) == 2
    assert set(report["tools"][0]) == {
        "tool_name",
        "round",
        "elapsed_ms",
        "status",
        "source_count",
    }
    assert report["stages"]["repair"]["executed"] is False
    assert report["stages"]["canon_checker"]["initial"]["status"] == "pass"
    assert report["stages"]["canon_checker"]["final"]["executed"] is False
    assert report["pipeline"]["provider_latency_ms"] == pytest.approx(22.0)
    assert report["pipeline"]["local_orchestration_remainder_ms"] >= 0
    shape = report["invocations"][0]["shape"]
    for metric in (
        "system_contract_characters",
        "system_contract_utf8_bytes",
        "runtime_characters",
        "runtime_utf8_bytes",
        "history_messages_characters",
        "history_messages_utf8_bytes",
        "evidence_characters",
        "evidence_utf8_bytes",
        "available_tools_characters",
        "available_tools_utf8_bytes",
        "authoring_payload_characters",
        "authoring_payload_utf8_bytes",
        "aggregate_serialized_characters",
        "aggregate_serialized_utf8_bytes",
        "utf8_bytes_div_4_estimated_tokens",
    ):
        assert isinstance(shape[metric], (int, float))
        assert shape[metric] >= 0
    assert shape["aggregate_serialized_utf8_bytes"] >= shape["system_contract_utf8_bytes"]
    assert shape["utf8_bytes_div_4_estimated_tokens"] == pytest.approx(
        shape["aggregate_serialized_utf8_bytes"] / 4.0
    )

    serialized = json.dumps(report, ensure_ascii=False)
    for sentinel in (
        "PROMPT_SECRET",
        "TOOL_ARG_SECRET",
        "TOOL_QUERY_SECRET",
        "MODEL_OUTPUT_SECRET_OPEN_QUESTION",
        "REFERENCE_CONTENT_SECRET",
    ):
        assert sentinel not in serialized


def test_contract_recovery_is_classified_as_a_distinct_logical_call() -> None:
    clock = FakeClock()
    incomplete = _payload()
    incomplete.pop("new_design_elements")
    model = ScriptedModel(
        clock,
        [
            (ModelTurn(text="FINALIZE"), 3, 0),
            (ModelTurn(structured_output=incomplete), 4, 0),
            (ModelTurn(structured_output=_payload()), 5, 0),
        ],
    )

    report = audit_live_character_authoring(
        CharacterDesignRequest("恢复缺失字段", request_id="latency_recovery_001"),
        model=model,
        reference_loader=_grounding_loader(clock),
        clock=clock,
    )

    assert report["status"] == "passed"
    assert [item["classification"] for item in report["invocations"]] == [
        "retrieval_action",
        "finalization",
        "contract_recovery",
    ]
    assert report["stages"]["contract_recovery"]["invocation_count"] == 1


def test_conditional_repair_adds_one_repair_invocation_and_final_check() -> None:
    clock = FakeClock()

    class RepairingModel:
        def __init__(self) -> None:
            self.generation = DeterministicCharacterGenerationModel(scenario="canon_conflict")
            self.repair = DeterministicCharacterRepairModel()

        def generate(self, prompt) -> ModelTurn:
            delegate = self.repair if prompt.character.principal == "character_repair" else self.generation
            turn = delegate.generate(prompt)
            clock.advance_ms(5)
            return replace(
                turn,
                invocation=ModelInvocationAudit(
                    session_id=prompt.session_id,
                    turn_number=prompt.turn_number,
                    provider="fake-provider",
                    model="fake-model",
                    outcome="success",
                    latency_ms=5,
                    retry_count=1 if prompt.character.principal == "character_repair" else 0,
                    tool_call_count=len(turn.tool_calls),
                    transport="fake-transport",
                    response_contract="json_object" if prompt.response_format == "character_draft" else "text",
                    purpose=prompt.invocation_purpose,
                ),
            )

    report = audit_live_character_authoring(
        CharacterDesignRequest(
            "设计一个新的五星角色。角色概念：她是秘密政府能力管理局的一名普通辅助成员。定位：偏辅助；保持现代都市生活感。",
            hard_constraints=("偏辅助",),
            request_id="latency_repair_001",
        ),
        model=RepairingModel(),
        reference_loader=_grounding_loader(clock),
        clock=clock,
    )

    assert report["status"] == "passed"
    assert report["result"]["initial_canon_status"] == "fail"
    assert report["result"]["final_canon_status"] == "pass"
    assert report["stages"]["repair"]["executed"] is True
    assert report["stages"]["repair"]["invocation_count"] == 1
    assert report["stages"]["canon_checker"]["final"]["executed"] is True
    assert any(item["classification"] == "repair" for item in report["invocations"])


def test_failure_returns_sanitized_partial_audit_without_exception_text() -> None:
    clock = FakeClock()

    class FailingModel:
        def generate(self, prompt) -> ModelTurn:
            clock.advance_ms(2)
            error = ModelProviderError(
                "raw provider response contains API_KEY_SECRET and PROMPT_SECRET"
            )
            error.audit = ModelInvocationAudit(
                session_id=prompt.session_id,
                turn_number=prompt.turn_number,
                provider="fake-provider",
                model="fake-model",
                outcome="provider",
                latency_ms=None,
                retry_count=1,
                transport="fake-transport",
                response_contract="text",
                provider_status_code=403,
                provider_retryable=False,
            )
            raise error

    report = audit_live_character_authoring(
        CharacterDesignRequest("PROMPT_SECRET brief", request_id="latency_fail_001"),
        model=FailingModel(),
        reference_loader=_grounding_loader(clock),
        clock=clock,
    )

    assert report["status"] == "failed"
    assert report["failure"]["category"] == "provider_failure"
    assert report["invocations"][0]["network_attempts"] == 2
    assert report["invocations"][0]["provider_status_code"] == 403
    assert report["invocations"][0]["provider_retryable"] is False
    assert "error_message" not in report["invocations"][0]
    assert report["pipeline"]["provider_latency_known"] is False
    assert report["pipeline"]["known_provider_latency_ms"] == 0.0
    assert report["pipeline"]["provider_latency_ms"] is None
    assert report["pipeline"]["local_orchestration_remainder_ms"] is None
    serialized = json.dumps(report, ensure_ascii=False)
    for sentinel in ("API_KEY_SECRET", "PROMPT_SECRET", "raw provider response"):
        assert sentinel not in serialized


def test_deterministic_retrieval_completes_with_scripted_model_and_is_recorded() -> None:
    clock = FakeClock()
    model = ScriptedModel(
        clock,
        [(ModelTurn(structured_output=_payload()), 7, 0)],
    )

    report = audit_live_character_authoring(
        CharacterDesignRequest("设计一个完全原创的辅助角色。", request_id="latency_deterministic_001"),
        model=model,
        reference_loader=_grounding_loader(clock),
        clock=clock,
        retrieval_strategy="deterministic",
    )

    assert report["status"] == "passed"
    assert report["retrieval_strategy"] == "deterministic"
    assert [item["classification"] for item in report["invocations"]] == ["finalization"]
    assert len(model.prompts) == 1


def test_cli_forwards_retrieval_strategy(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, Any] = {}

    def fake_audit(request: CharacterDesignRequest, **kwargs: Any) -> dict[str, Any]:
        captured["request"] = request
        captured.update(kwargs)
        return {"status": "passed", "retrieval_strategy": kwargs["retrieval_strategy"]}

    monkeypatch.setattr(_SCRIPT_MODULE, "audit_live_character_authoring", fake_audit)

    assert _SCRIPT_MODULE.main(
        ["--brief", "设计一个角色。", "--retrieval-strategy", "deterministic"]
    ) == 0

    assert captured["retrieval_strategy"] == "deterministic"
    assert json.loads(capsys.readouterr().out)["retrieval_strategy"] == "deterministic"


def test_invalid_api_retrieval_strategy_fails_before_model_or_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    model_calls = 0
    provider_calls = 0

    class ExplodingModel:
        def generate(self, prompt: Any) -> ModelTurn:
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("model must not be called")

    def fail_provider(**kwargs: Any) -> Any:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider factory must not be called")

    monkeypatch.setattr(_SCRIPT_MODULE, "character_model_from_environment", fail_provider)

    report = audit_live_character_authoring(
        CharacterDesignRequest("非法策略输入", request_id="latency_invalid_strategy_001"),
        model=ExplodingModel(),
        reference_loader=lambda _brief: (_ for _ in ()).throw(
            AssertionError("reference loader must not be called")
        ),
        clock=clock,
        retrieval_strategy="provider_secret_strategy",
    )

    assert report["status"] == "failed"
    assert report["failure"]["category"] == "orchestration_failure"
    assert report["retrieval_strategy"] is None
    assert model_calls == 0
    assert provider_calls == 0
    assert "provider_secret_strategy" not in json.dumps(report, ensure_ascii=False)
