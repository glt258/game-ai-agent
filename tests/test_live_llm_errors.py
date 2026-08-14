from __future__ import annotations

from collections import deque
from typing import Any

import pytest

from agents import (
    LiveLLMAdapter,
    ModelAuthenticationError,
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
            ProviderCompletion(text="恢复成功", request_id="req_retry"),
        ],
        sleep=delays.append,
    )

    response = agent.chat(session, state, "你好")

    assert response.text == "恢复成功"
    assert client.call_count == 2 and delays == [0.5]
    assert response.model_invocations[0].retry_count == 1


def test_timeout_exhaustion_is_bounded_and_turn_local():
    failures = [ProviderClientError("timeout", retryable=True) for _ in range(3)]
    agent, client, session, state = run_live(failures, max_retries=2)

    with pytest.raises(ModelTimeoutError, match="bounded retries"):
        agent.chat(session, state, "你好")

    assert client.call_count == 3
    assert session.messages == [] and session.model_audit == []


def test_rate_limit_retries_are_bounded():
    failures = [
        ProviderClientError("rate_limit", retryable=True, status_code=429)
        for _ in range(2)
    ]
    agent, client, session, state = run_live(failures, max_retries=1)

    with pytest.raises(ModelRateLimitError):
        agent.chat(session, state, "你好")

    assert client.call_count == 2


def test_authentication_failure_is_not_retried_or_leaked():
    secret = "unit-test-secret-value"
    agent, client, session, state = run_live(
        [ProviderClientError("authentication", retryable=False, status_code=401)]
    )

    with pytest.raises(ModelAuthenticationError) as captured:
        agent.chat(session, state, secret)

    assert client.call_count == 1
    assert secret not in str(captured.value)


def test_provider_5xx_exhaustion_is_normalized():
    failures = [
        ProviderClientError("provider", retryable=True, status_code=500)
        for _ in range(2)
    ]
    agent, _, session, state = run_live(failures, max_retries=1)

    with pytest.raises(ModelProviderError):
        agent.chat(session, state, "你好")


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
    agent, _, session, state = run_live([ProviderCompletion(text="正常回复")])

    with caplog.at_level("INFO", logger="agents.live_llm"):
        agent.chat(session, state, secret)

    logs = caplog.text
    assert "provider=openai" in logs and "model=test-model" in logs
    assert "outcome=success" in logs and "latency_ms=" in logs
    assert secret not in logs
