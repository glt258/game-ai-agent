from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict
from typing import Any

import pytest

from agents import (
    SAFE_FALLBACK_TEXT,
    LiveLLMAdapter,
    ModelAuthenticationError,
    ModelInvocationAudit,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    NpcConversationAgent,
    ProviderClientError,
    ProviderCompletion,
)
from story import StoryRuntime

STORY_ID = "story_after_the_show_001"


def grounded_json() -> str:
    return json.dumps(
        {
            "segments": [
                {
                    "segment_id": "safe",
                    "kind": "uncertain",
                    "text": "我没有这部分可核实的资料。",
                    "evidence_ids": [],
                }
            ]
        },
        ensure_ascii=False,
    )


class ErrorFakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = deque(outcomes)
        self.call_count = 0

    def complete(self, **_: Any) -> ProviderCompletion:
        self.call_count += 1
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def run_live(outcomes: list[Any], *, max_retries: int = 2, sleep=None):
    runtime = StoryRuntime()
    state = runtime.initial_state(STORY_ID)
    client = ErrorFakeClient(outcomes)
    adapter = LiveLLMAdapter(
        client,
        provider="openai",
        model="test-model",
        max_retries=max_retries,
        sleep=sleep or (lambda _: None),
    )
    agent = NpcConversationAgent(adapter, story_repository=runtime.repository)
    session = agent.create_session("error-session", "char_launch_004", STORY_ID)
    return agent, client, session, state


def test_timeout_retries_once_then_succeeds_with_audit():
    delays: list[float] = []
    agent, client, session, state = run_live(
        [
            ProviderClientError("timeout", retryable=True),
            ProviderCompletion(text=grounded_json(), request_id="req_retry"),
        ],
        sleep=delays.append,
    )

    response = agent.chat(session, state, "你好")

    assert response.text == "我没有这部分可核实的资料。"
    assert client.call_count == 2 and delays == [0.5]
    assert response.model_invocations[0].retry_count == 1
    assert response.model_invocations[0].provider_status_code is None
    assert response.model_invocations[0].provider_retryable is None


def test_timeout_exhaustion_is_bounded_and_turn_local():
    failures = [ProviderClientError("timeout", retryable=True) for _ in range(3)]
    agent, client, session, state = run_live(failures, max_retries=2)

    with pytest.raises(ModelTimeoutError, match="bounded retries"):
        agent.chat(session, state, "你好")

    assert client.call_count == 3
    assert session.messages == []
    assert len(session.model_audit) == 1
    failure = session.model_audit[0]
    assert failure.outcome == "timeout"
    assert failure.retry_count == 2
    assert failure.provider == "openai" and failure.model == "test-model"
    assert failure.finish_reason is None and failure.usage is None
    assert failure.error_message == "Live LLM request timed out after bounded retries"
    assert failure.provider_status_code is None
    assert failure.provider_retryable is True


def test_rate_limit_retries_are_bounded():
    failures = [
        ProviderClientError("rate_limit", retryable=True, status_code=429)
        for _ in range(2)
    ]
    agent, client, session, state = run_live(failures, max_retries=1)

    with pytest.raises(ModelRateLimitError):
        agent.chat(session, state, "你好")

    assert client.call_count == 2
    assert session.model_audit[0].provider_status_code == 429
    assert session.model_audit[0].provider_retryable is True


def test_authentication_failure_is_not_retried_or_leaked():
    secret = "unit-test-secret-value"
    agent, client, session, state = run_live(
        [ProviderClientError("authentication", retryable=False, status_code=401)]
    )

    with pytest.raises(ModelAuthenticationError) as captured:
        agent.chat(session, state, secret)

    assert client.call_count == 1
    assert secret not in str(captured.value)
    assert session.model_audit[0].provider_status_code == 401
    assert session.model_audit[0].provider_retryable is False


def test_provider_5xx_exhaustion_is_normalized():
    failures = [
        ProviderClientError("provider", retryable=True, status_code=500)
        for _ in range(2)
    ]
    agent, client, session, state = run_live(failures, max_retries=1)

    with pytest.raises(ModelProviderError):
        agent.chat(session, state, "你好")

    assert client.call_count == 2
    assert session.model_audit[0].provider_status_code == 500
    assert session.model_audit[0].provider_retryable is True


@pytest.mark.parametrize("status_code", [400, 402, 403, 422])
def test_nonretry_provider_failures_carry_safe_http_status(status_code: int):
    agent, client, session, state = run_live(
        [ProviderClientError("provider", retryable=False, status_code=status_code)]
    )

    with pytest.raises(ModelProviderError):
        agent.chat(session, state, "你好")

    assert client.call_count == 1
    assert session.model_audit[0].provider_status_code == status_code
    assert session.model_audit[0].provider_retryable is False


@pytest.mark.parametrize(
    ("kind", "error_type"),
    [("timeout", ModelTimeoutError), ("provider", ModelProviderError)],
)
def test_statusless_transport_failures_keep_http_status_unknown(kind, error_type):
    agent, client, session, state = run_live(
        [ProviderClientError(kind, retryable=True)], max_retries=0
    )

    with pytest.raises(error_type):
        agent.chat(session, state, "你好")

    assert client.call_count == 1
    assert session.model_audit[0].provider_status_code is None
    assert session.model_audit[0].provider_retryable is True


def test_provider_metadata_sanitizes_invalid_values_without_leaking_content():
    status_sentinel = "HTTP_STATUS_SECRET"
    retryable_sentinel = "RETRYABLE_SECRET"
    raw_response_sentinel = "RAW_PROVIDER_RESPONSE_SECRET"
    error = ProviderClientError(
        "provider",
        retryable=retryable_sentinel,
        status_code=status_sentinel,
    )
    error.response = {"body": raw_response_sentinel}
    agent, client, session, state = run_live([error], max_retries=0)

    with pytest.raises(ModelProviderError):
        agent.chat(session, state, "PROMPT_SECRET")

    assert client.call_count == 1
    failure = session.model_audit[0]
    assert failure.provider_status_code is None
    assert failure.provider_retryable is None
    payload = json.dumps(asdict(failure), ensure_ascii=False)
    assert all(
        sentinel not in payload
        for sentinel in (
            status_sentinel,
            retryable_sentinel,
            raw_response_sentinel,
            "PROMPT_SECRET",
        )
    )


def test_provider_metadata_is_fail_closed_at_audit_construction():
    audit = ModelInvocationAudit(
        session_id="session",
        turn_number=1,
        provider="openai",
        model="test-model",
        outcome="provider",
        latency_ms=1.0,
        retry_count=0,
        provider_status_code=True,
        provider_retryable=1,
    )

    assert audit.provider_status_code is None
    assert audit.provider_retryable is None


@pytest.mark.parametrize(
    "completion",
    [
        ProviderCompletion(),
        ProviderCompletion(text=""),
        ProviderCompletion(text="   "),
    ],
)
def test_malformed_empty_provider_response_is_rejected(completion):
    agent, client, session, state = run_live([completion])

    with pytest.raises(ModelMalformedResponseError, match="neither"):
        agent.chat(session, state, "你好")

    assert client.call_count == 1 and session.messages == []


def test_observability_log_excludes_prompt_and_secret(caplog):
    secret = "unit-test-prompt-secret"
    agent, _, session, state = run_live([ProviderCompletion(text=grounded_json())])

    with caplog.at_level("INFO", logger="agents.live_llm"):
        agent.chat(session, state, secret)

    logs = caplog.text
    assert "provider=openai" in logs and "model=test-model" in logs
    assert "outcome=success" in logs and "latency_ms=" in logs
    assert secret not in logs


def test_malformed_schema_records_failure_audit_without_commit():
    malformed = (
        '{"segments":[{"segment_id":"1","type":"supported_claim",'
        '"text":"你好","evidence_ids":[]}]}'
    )
    agent, client, session, state = run_live(
        [
            ProviderCompletion(
                text=malformed, finish_reason="stop", request_id="req_malformed"
            )
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match="exact segment schema"):
        agent.chat(session, state, "你好")

    assert client.call_count == 1
    assert session.messages == [] and session.grounding_audit == []
    assert len(session.model_audit) == 1
    failure = session.model_audit[0]
    assert failure.outcome == "malformed_response"
    assert failure.retry_count == 0
    assert failure.finish_reason == "stop"
    assert failure.provider_request_id == "req_malformed"
    assert (
        failure.error_message
        == "Every grounded segment must use the exact segment schema"
    )


def test_malformed_failure_audit_excludes_sensitive_model_content():
    secret = "伪受限内部复盘结论-玩家输入-工具结果-模型幻觉"
    malformed = (
        '{"segments":[{"segment_id":"leak","kind":"leak","text":"'
        + secret
        + '","evidence_ids":[]}]}'
    )
    agent, client, session, state = run_live(
        [ProviderCompletion(text=malformed, request_id="req_leak")]
    )

    with pytest.raises(ModelMalformedResponseError):
        agent.chat(session, state, "你好")

    assert client.call_count == 1
    assert session.grounding_audit == [] and session.messages == []
    assert len(session.model_audit) == 1
    audit_payload = json.dumps(asdict(session.model_audit[0]), ensure_ascii=False)
    assert secret not in audit_payload
    assert session.model_audit[0].error_message == "Grounded segment kind is unsupported"


def test_repair_failure_records_audit_and_falls_back():
    candidate = (
        '{"segments":[{"segment_id":"bad","kind":"supported_claim",'
        '"text":"你好","evidence_ids":["lore:lore_999:statement"]}]}'
    )
    timeout = ProviderClientError("timeout", retryable=True)
    agent, client, session, state = run_live(
        [ProviderCompletion(text=candidate), timeout, timeout],
        max_retries=1,
    )

    response = agent.chat(session, state, "内部报告如何认定？")

    assert response.text == SAFE_FALLBACK_TEXT
    assert client.call_count == 3
    assert [item.outcome for item in session.model_audit] == [
        "success",
        "timeout",
    ]
    assert session.model_audit[1].retry_count == 1
    grounding = session.grounding_audit[0]
    assert grounding.repair_attempted
    assert not grounding.repair_succeeded
    assert grounding.fallback_used


def test_repair_malformed_secret_never_reaches_audit_or_response():
    secret = "伪受限事故内部定性-工具结果-玩家输入"
    candidate = (
        '{"segments":[{"segment_id":"bad","kind":"supported_claim",'
        '"text":"你好","evidence_ids":["lore:lore_999:statement"]}]}'
    )
    malformed_repair = (
        '{"segments":[{"segment_id":"repair","kind":"leak","text":"'
        + secret
        + '","evidence_ids":[]}]}'
    )
    agent, client, session, state = run_live(
        [
            ProviderCompletion(text=candidate),
            ProviderCompletion(text=malformed_repair),
        ]
    )

    response = agent.chat(session, state, "内部报告如何认定？")

    assert response.text == SAFE_FALLBACK_TEXT
    assert client.call_count == 2
    assert [item.outcome for item in session.model_audit] == [
        "success",
        "malformed_response",
    ]
    audit_payload = json.dumps(
        [asdict(item) for item in session.model_audit], ensure_ascii=False
    )
    assert secret not in audit_payload
    grounding_payload = json.dumps(
        [asdict(item) for item in session.grounding_audit], ensure_ascii=False
    )
    assert secret not in grounding_payload
    assert secret not in response.text
    assert all(secret not in str(item.content) for item in session.messages)
    grounding = session.grounding_audit[0]
    assert grounding.repair_attempted
    assert not grounding.repair_succeeded
    assert grounding.fallback_used
