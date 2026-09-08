from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from agents.canon_checker import CanonChecker
from agents.character_generation import CharacterGenerationAgent
from agents.character_repair import CharacterRepairAgent, DeterministicCharacterRepairModel
from agents.errors import ModelProviderError
from agents.models import ModelAttemptAudit, ModelInvocationAudit
from web.app import create_app
from web.errors import map_generation_exception
from web.services.character_generation import CharacterGenerationApplication
from web.services.live_jobs import LiveJobRegistry


class ProviderFailureModel:
    def generate(self, prompt):
        error = ModelProviderError("S1E_PROVIDER_FAILURE_SUPER_SECRET")
        error.audit = ModelInvocationAudit(
            session_id=prompt.session_id,
            turn_number=prompt.turn_number,
            provider="opencode_go",
            model="deepseek-v4-flash",
            outcome="provider",
            latency_ms=2875.0,
            retry_count=0,
            transport="openai_chat_completions",
            response_contract="json_object",
            error_message="provider request failed",
            provider_status_code=400,
            provider_retryable=None,
            upstream_status=400,
            upstream_error_type="invalid_request_error",
            upstream_error_code="unsupported_tool_schema",
            upstream_error_param="tools",
            provider_request_id="req-f3-safe",
            attempts=(
                ModelAttemptAudit(
                    attempt_number=1,
                    outcome="provider",
                    latency_ms=2875.0,
                    error_code="provider",
                ),
            ),
        )
        raise error


def _terminal(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        body = client.get(f"/api/characters/generate/jobs/{job_id}").json()
        if body["status"] in {"SUCCEEDED", "FAILED"}:
            return body
        time.sleep(0.01)
    raise AssertionError("character job did not reach a terminal state")


def test_model_provider_error_maps_to_typed_safe_web_failure() -> None:
    error = ModelProviderError("S1E_PROVIDER_FAILURE_SUPER_SECRET")
    mapped = map_generation_exception(error)

    assert mapped.code == "PROVIDER_FAILURE"
    assert mapped.status_code == 502
    assert mapped.stage == "generation_provider_invocation"
    assert mapped.retryable is False
    assert "S1E_PROVIDER_FAILURE_SUPER_SECRET" not in mapped.message


def test_model_provider_error_preserves_known_retryability() -> None:
    error = ModelProviderError("provider request failed")
    error.audit = ModelInvocationAudit(
        session_id="retryable-provider-failure",
        turn_number=1,
        provider="opencode_go",
        model="deepseek-v4-flash",
        outcome="provider",
        latency_ms=5.0,
        retry_count=1,
        provider_retryable=True,
    )

    mapped = map_generation_exception(error)

    assert mapped.retryable is True
    assert mapped.details["provider_retryable"] is True


def test_unknown_provider_retryability_stays_unknown_in_safe_details() -> None:
    error = ModelProviderError("provider request failed")
    error.audit = ModelInvocationAudit(
        session_id="unknown-provider-retryability",
        turn_number=1,
        provider="opencode_go",
        model="deepseek-v4-flash",
        outcome="provider",
        latency_ms=5.0,
        retry_count=0,
        provider_retryable=None,
    )

    mapped = map_generation_exception(error)

    assert mapped.retryable is False
    assert mapped.details["provider_retryable"] is None


def test_failed_character_job_preserves_safe_provider_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("NPC_LLM_PROVIDER", "opencode_go")
    monkeypatch.setenv("NPC_LLM_MODEL", "deepseek-v4-flash")
    checker = CanonChecker()
    registry = LiveJobRegistry(
        max_workers=1,
        max_in_flight=1,
        timeout_seconds=2,
        ttl_seconds=2,
    )
    client = TestClient(
        create_app(
            generation_service=CharacterGenerationApplication(
                generation_mode="live",
                generation_agent=CharacterGenerationAgent(ProviderFailureModel()),
                repair_agent=CharacterRepairAgent(
                    DeterministicCharacterRepairModel(),
                    checker=checker,
                ),
                checker=checker,
            ),
            live_job_registry=registry,
        )
    )
    try:
        accepted = client.post(
            "/api/characters/generate/jobs",
            json={"brief": "设计一名辅助角色。", "request_id": "provider_failure_fixture"},
        )
        assert accepted.status_code == 202

        failed = _terminal(client, accepted.json()["job_id"])
        assert failed["status"] == "FAILED"
        error = failed["error"]
        assert error["code"] == "PROVIDER_FAILURE"
        assert error["message"] == "模型服务调用失败，请稍后重试。"
        assert error["stage"] == "generation_provider_invocation"
        assert error["retryable"] is False
        assert error["details"] == {
            "provider": "opencode_go",
            "model": "deepseek-v4-flash",
            "upstream_status": 400,
            "upstream_error_type": "invalid_request_error",
            "upstream_error_code": "unsupported_tool_schema",
            "upstream_error_param": "tools",
            "provider_request_id": "req-f3-safe",
            "provider_status_code": 400,
            "provider_retryable": None,
            "attempt_count": 1,
            "retry_count": 0,
        }
        audit = error["audit"]["model_invocations"][0]
        assert audit["provider"] == "opencode_go"
        assert audit["model"] == "deepseek-v4-flash"
        assert audit["outcome"] == "provider"
        assert audit["attempts"][0]["attempt_number"] == 1
        assert audit["attempts"][0]["outcome"] == "provider"
        assert audit["usage"] is None
        assert audit["provider_status_code"] == 400
        assert audit["provider_retryable"] is None
        assert audit["upstream_status"] == 400
        assert audit["upstream_error_type"] == "invalid_request_error"
        assert audit["upstream_error_code"] == "unsupported_tool_schema"
        assert audit["upstream_error_param"] == "tools"
        assert audit["provider_request_id"] == "req-f3-safe"
        assert "S1E_PROVIDER_FAILURE_SUPER_SECRET" not in json.dumps(failed)
    finally:
        registry.shutdown()
