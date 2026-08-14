from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from agents import OpenAIChatClient, ProviderClientError


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.request = None

    def create(self, **request):
        self.request = request
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_openai_client_maps_chat_completion_without_sdk_leaking_upward():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="sdk-call",
                            function=SimpleNamespace(
                                name="search_lore",
                                arguments='{"query":"公开资料"}',
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=4,
            total_tokens=14,
        ),
        _request_id="req_sdk",
    )
    completions = FakeCompletions(sdk_response)
    sdk_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=sdk_client,
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_lore",
                "parameters": {"type": "object"},
            },
        }
    ]

    result = client.complete(
        model="configured-model",
        messages=[{"role": "user", "content": "查询"}],
        tools=tools,
        timeout_seconds=12,
    )

    assert result.tool_calls[0].id == "sdk-call"
    assert result.tool_calls[0].name == "search_lore"
    assert result.tool_calls[0].arguments == '{"query":"公开资料"}'
    assert result.finish_reason == "tool_calls"
    assert result.usage is not None and result.usage.total_tokens == 14
    assert result.request_id == "req_sdk"
    assert completions.request == {
        "model": "configured-model",
        "messages": [{"role": "user", "content": "查询"}],
        "timeout": 12,
        "tools": tools,
    }


def test_openai_client_omits_tools_when_runtime_allows_none():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="你好", tool_calls=None),
            )
        ],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        ),
    )

    result = client.complete(
        model="configured-model",
        messages=[{"role": "user", "content": "你好"}],
        tools=[],
        timeout_seconds=30,
    )

    assert result.text == "你好"
    assert "tools" not in completions.request


@pytest.mark.parametrize(
    ("sdk_error", "kind", "retryable"),
    [
        (
            openai.AuthenticationError(
                "credential-secret",
                response=httpx.Response(
                    401, request=httpx.Request("POST", "https://example.test")
                ),
                body=None,
            ),
            "authentication",
            False,
        ),
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://example.test")
            ),
            "timeout",
            True,
        ),
        (
            openai.RateLimitError(
                "limited",
                response=httpx.Response(
                    429, request=httpx.Request("POST", "https://example.test")
                ),
                body=None,
            ),
            "rate_limit",
            True,
        ),
        (
            openai.InternalServerError(
                "provider body",
                response=httpx.Response(
                    500, request=httpx.Request("POST", "https://example.test")
                ),
                body=None,
            ),
            "provider",
            True,
        ),
    ],
)
def test_openai_sdk_errors_are_sanitized(sdk_error, kind, retryable):
    completions = FakeCompletions(sdk_error)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        ),
    )

    with pytest.raises(ProviderClientError) as captured:
        client.complete(
            model="configured-model",
            messages=[{"role": "user", "content": "你好"}],
            tools=[],
            timeout_seconds=30,
        )

    assert captured.value.kind == kind
    assert captured.value.retryable is retryable
    assert "credential-secret" not in str(captured.value)
    assert "provider body" not in str(captured.value)
