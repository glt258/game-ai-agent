from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from character_intelligence.hybrid_ir.runner import (
    FakeProvider,
    HybridProviderInvocationError,
)
from web.app import create_app
from web.services.live_jobs import LiveJobRegistry
from web.services.skill_playground import SkillPlaygroundApplication

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(case_id: str) -> dict[str, object]:
    filename = (
        "hybrid_final_coverage_v2_goldens.json"
        if case_id in {
            "generalization_sub_dps_v1",
            "character_alignment_support_v1",
        }
        else "hybrid_multi_case_generalization_goldens.json"
    )
    values = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return values[case_id]


class DelayedProvider:
    def __init__(self, inner: object, delay_seconds: float) -> None:
        self._inner = inner
        self._delay_seconds = delay_seconds

    def complete(self, request_text: str) -> object:
        time.sleep(self._delay_seconds)
        return self._inner.complete(request_text)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class TimeoutProvider:
    calls = 0
    transport_attempts = 1
    latency_ms = 1.0
    outcome = "TIMEOUT"

    def complete(self, _request_text: str) -> object:
        self.calls += 1
        raise HybridProviderInvocationError("TIMEOUT")


def _client(
    provider: object,
    registry: LiveJobRegistry | None = None,
) -> TestClient:
    service = SkillPlaygroundApplication(provider_factory=lambda _model: provider)
    return TestClient(
        create_app(
            skill_playground_service=service,
            live_job_registry=registry
            or LiveJobRegistry(max_workers=1, max_in_flight=2, timeout_seconds=2, ttl_seconds=2),
        )
    )


def _payload() -> dict[str, object]:
    return {
        "family": "sub_dps",
        "mode": "active",
        "brief": "设计一个在队友行动后追加输出的辅助技能。",
        "constraints": [],
        "language": "zh-CN",
        "model": "deepseek-v4-pro",
        "execution_mode": "live",
        "provider": "opencode_go",
    }


def _wait_for_terminal(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(f"/api/skills/playground/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"SUCCEEDED", "FAILED"}:
            return body
        time.sleep(0.01)
    raise AssertionError("job did not reach a terminal state")


def test_live_job_returns_202_and_reuses_the_normal_skill_result_contract() -> None:
    provider = DelayedProvider(FakeProvider(_fixture("generalization_sub_dps_v1")), 0.02)
    client = _client(provider)

    response = client.post("/api/skills/playground/jobs", json=_payload())

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["schema_version"] == "web-live-skill-job/0.1"
    assert accepted["status"] in {"PENDING", "RUNNING"}
    assert accepted["provider"] == "opencode_go"
    result = _wait_for_terminal(client, accepted["job_id"])
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["schema_version"] == "web-skill-playground/0.1"
    assert result["result"]["evaluation"]["outcome"] == "PASS"
    assert result["error"] is None


def test_live_job_timeout_is_safe_and_late_result_cannot_replace_failure() -> None:
    registry = LiveJobRegistry(
        max_workers=1,
        max_in_flight=2,
        timeout_seconds=0.02,
        ttl_seconds=2,
    )
    provider = DelayedProvider(FakeProvider(_fixture("generalization_sub_dps_v1")), 0.15)
    client = _client(provider, registry)

    accepted = client.post("/api/skills/playground/jobs", json=_payload()).json()
    failed = _wait_for_terminal(client, accepted["job_id"])
    assert failed["status"] == "FAILED"
    assert failed["error"]["code"] == "BACKEND_REQUEST_TIMEOUT"
    assert "secret" not in json.dumps(failed)

    time.sleep(0.2)
    late = client.get(f"/api/skills/playground/jobs/{accepted['job_id']}").json()
    assert late["status"] == "FAILED"
    assert late["error"]["code"] == "BACKEND_REQUEST_TIMEOUT"
    registry.shutdown()


def test_provider_timeout_keeps_provider_stage_classification() -> None:
    client = _client(TimeoutProvider())

    accepted = client.post("/api/skills/playground/jobs", json=_payload()).json()
    failed = _wait_for_terminal(client, accepted["job_id"])

    assert failed["status"] == "FAILED"
    assert failed["error"]["code"] == "PROVIDER_TIMEOUT"
    assert failed["error"]["stage"] == "provider"


def test_unknown_job_and_concurrency_limit_are_safe() -> None:
    registry = LiveJobRegistry(
        max_workers=1,
        max_in_flight=1,
        timeout_seconds=2,
        ttl_seconds=2,
    )
    client = _client(
        DelayedProvider(FakeProvider(_fixture("generalization_sub_dps_v1")), 0.15),
        registry,
    )

    unknown = client.get("/api/skills/playground/jobs/not-a-real-job")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "LIVE_JOB_NOT_FOUND"

    first = client.post("/api/skills/playground/jobs", json=_payload())
    second = client.post("/api/skills/playground/jobs", json=_payload())
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "LIVE_EXECUTION_BUSY"
    registry.shutdown()


def test_finished_job_ttl_cleanup_removes_ephemeral_state() -> None:
    registry = LiveJobRegistry(
        max_workers=1,
        max_in_flight=1,
        timeout_seconds=2,
        ttl_seconds=0.2,
    )
    client = _client(FakeProvider(_fixture("generalization_sub_dps_v1")), registry)

    accepted = client.post("/api/skills/playground/jobs", json=_payload()).json()
    _wait_for_terminal(client, accepted["job_id"])
    time.sleep(0.25)

    expired = client.get(f"/api/skills/playground/jobs/{accepted['job_id']}")
    assert expired.status_code == 404
    assert expired.json()["error"]["code"] == "LIVE_JOB_NOT_FOUND"
    registry.shutdown()


def test_character_skill_live_job_is_a_separate_transport_for_the_same_pipeline() -> None:
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_support_v1")),
    )
    client = TestClient(
        create_app(
            skill_playground_service=service,
            live_job_registry=LiveJobRegistry(timeout_seconds=2, ttl_seconds=2),
        )
    )
    character_response = client.post(
        "/api/characters/generate",
        json={"brief": "设计一名辅助角色。", "request_id": "live_job_character"},
    )
    assert character_response.status_code == 200
    character = character_response.json()

    accepted = client.post(
        "/api/characters/skill-design/jobs",
        json={
            "character": {
                "request": character["request"],
                "draft": character["draft"],
                "plan": character["plan"],
            },
            "skill": {
                **_payload(),
                "preset_id": None,
            },
        },
    )

    assert accepted.status_code == 202
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = client.get(
            f"/api/characters/skill-design/jobs/{accepted.json()['job_id']}"
        )
        assert status.status_code == 200
        body = status.json()
        if body["status"] in {"SUCCEEDED", "FAILED"}:
            assert body["status"] == "SUCCEEDED"
            assert body["result"]["schema_version"] == "web-character-skill-design/0.1"
            assert body["result"]["artifact_digest"]
            return
        time.sleep(0.01)
    raise AssertionError("character job did not reach a terminal state")


def test_web_live_provider_default_matches_the_benchmark_timeout_baseline(monkeypatch) -> None:
    monkeypatch.delenv("NPC_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("NPC_LLM_MAX_RETRIES", raising=False)
    monkeypatch.setenv("NPC_LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("NPC_LLM_PROVIDER", "opencode_go")
    monkeypatch.setenv("NPC_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(
        "agents.openai_provider.OpenAIChatClient",
        lambda **_kwargs: object(),
    )

    from character_intelligence.hybrid_ir.runner import live_hybrid_provider_from_environment

    provider = live_hybrid_provider_from_environment()

    assert provider._timeout_seconds == 60  # noqa: SLF001 - config seam assertion
    assert provider.max_transport_retries == 0
