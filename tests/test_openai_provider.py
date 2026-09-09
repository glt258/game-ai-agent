from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from agents import (
    ModelConfigurationError,
    NegotiatedResponseContract,
    OpenAIChatClient,
    ProviderClientError,
    ResponseMode,
    default_invocation_context,
)


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.requests = []

    def create(self, **request):
        self.request = request
        self.requests.append(request)
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


def test_openai_client_translates_structured_json_intent_to_official_json_mode():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content='{"segments":[]}', tool_calls=None),
            )
        ],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    client.complete(
        model="configured-model",
        messages=[{"role": "system", "content": "Output JSON."}],
        tools=[],
        timeout_seconds=30,
        response_mode="structured_json",
    )

    assert completions.request["response_format"] == {"type": "json_object"}


def test_openai_client_translates_negotiated_strict_json_schema():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content='{"value":"ok"}', tool_calls=None),
            )
        ],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }

    client.complete(
        model="configured-model",
        messages=[{"role": "system", "content": "Output JSON."}],
        tools=[],
        timeout_seconds=30,
        response_contract=NegotiatedResponseContract(
            "test_contract", ResponseMode.JSON_SCHEMA, schema
        ),
    )

    assert completions.request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "test_contract",
            "strict": True,
            "schema": schema,
        },
    }


def test_openai_client_keeps_text_tool_round_without_response_format():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(content=None, tool_calls=[]),
            )
        ],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    client.complete(
        model="configured-model",
        messages=[{"role": "user", "content": "查资料"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        timeout_seconds=30,
        response_mode="text",
    )

    assert "response_format" not in completions.request


def test_openai_client_keeps_authoring_action_tool_round_without_response_format():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(content=None, tool_calls=[]),
            )
        ],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    client.complete(
        model="configured-model",
        messages=[{"role": "system", "content": "Retrieve evidence."}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        timeout_seconds=30,
        response_contract=NegotiatedResponseContract(
            "character_authoring_action", ResponseMode.TEXT
        ),
    )

    assert completions.request["tools"]
    assert "response_format" not in completions.request


def test_deepseek_compatible_request_disables_thinking_only_via_extra_body():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="普通模式回复", tool_calls=None),
            )
        ],
        usage=None,
        _request_id="deepseek-request",
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        base_url="https://api.deepseek.com",
        request_options={"extra_body": {"thinking": {"type": "disabled"}}},
        sdk_client=SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        ),
    )
    messages = [{"role": "user", "content": "你好"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_lore",
                "parameters": {"type": "object"},
            },
        }
    ]

    client.complete(
        model="configured-deepseek-model",
        messages=messages,
        tools=tools,
        timeout_seconds=20,
    )

    assert completions.request["model"] == "configured-deepseek-model"
    assert completions.request["messages"] == messages
    assert completions.request["tools"] == tools
    assert completions.request["timeout"] == 20
    assert completions.request["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert client.base_url == "https://api.deepseek.com"


def test_deepseek_structured_request_combines_json_mode_with_disabled_thinking():
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content='{"segments":[]}', tool_calls=None),
            )
        ],
        usage=None,
        _request_id="deepseek-json-request",
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        base_url="https://api.deepseek.com",
        request_options={"extra_body": {"thinking": {"type": "disabled"}}},
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    client.complete(
        model="configured-deepseek-model",
        messages=[{"role": "system", "content": "Output JSON."}],
        tools=[],
        timeout_seconds=20,
        response_mode="structured_json",
    )

    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_provider_request_options_cannot_override_core_fields():
    with pytest.raises(ValueError, match="core request fields"):
        OpenAIChatClient(
            api_key="placeholder-test-key",
            request_options={"model": "unsafe-override"},
            sdk_client=SimpleNamespace(),
        )


def test_opencode_go_adds_server_session_header_from_parent_context():
    sdk_response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok", tool_calls=None))],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        provider="opencode_go",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    with default_invocation_context(budget_seconds=30.0):
        client.complete(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            timeout_seconds=10,
        )

    assert completions.request["extra_headers"]["x-opencode-session"]
    assert len(completions.request["extra_headers"]["x-opencode-session"]) == 32
    assert "provider_session_id" not in completions.request


def test_opencode_go_reuses_session_header_for_repeated_calls_and_rotates_per_context():
    sdk_response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok", tool_calls=None))],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        provider="opencode_go",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    with default_invocation_context(budget_seconds=30.0):
        for _ in range(2):
            client.complete(
                model="deepseek-v4-flash",
                messages=[{"role": "user", "content": "hello"}],
                tools=[],
                timeout_seconds=10,
            )
    first, second = (item["extra_headers"]["x-opencode-session"] for item in completions.requests)
    with default_invocation_context(budget_seconds=30.0):
        client.complete(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            timeout_seconds=10,
        )
    third = completions.requests[-1]["extra_headers"]["x-opencode-session"]

    assert first == second
    assert first != third


def test_opencode_go_requires_parent_context_before_network():
    completions = FakeCompletions(
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok", tool_calls=None))],
            usage=None,
            _request_id=None,
        )
    )
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        provider="opencode_go",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    with pytest.raises(ModelConfigurationError, match="parent live invocation context"):
        client.complete(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            timeout_seconds=10,
        )
    assert completions.requests == []


def test_non_opencode_provider_omits_opencode_session_header():
    sdk_response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok", tool_calls=None))],
        usage=None,
        _request_id=None,
    )
    completions = FakeCompletions(sdk_response)
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        provider="deepseek",
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    with default_invocation_context(budget_seconds=30.0):
        client.complete(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            timeout_seconds=10,
        )

    assert "extra_headers" not in completions.request


def test_provider_request_options_cannot_inject_headers():
    with pytest.raises(ValueError, match="core request fields"):
        OpenAIChatClient(
            api_key="placeholder-test-key",
            request_options={"extra_headers": {"x-opencode-session": "unsafe"}},
            sdk_client=SimpleNamespace(),
        )


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


def test_openai_status_error_extracts_only_structured_safe_metadata():
    sdk_error = openai.BadRequestError(
        "F3_SUPER_SECRET_VALUE raw message",
        response=httpx.Response(
            400,
            headers={"x-request-id": "req-f3-safe"},
            request=httpx.Request("POST", "https://example.test"),
        ),
        body={
            "error": {
                "type": "invalid_request_error",
                "code": "unsupported_tool_schema",
                "param": "tools",
                "message": "F3_SUPER_SECRET_VALUE body message",
            },
            "extra": "F3_SUPER_SECRET_VALUE",
        },
    )
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions(sdk_error))
        ),
    )

    with pytest.raises(ProviderClientError) as captured:
        client.complete(
            model="configured-model",
            messages=[{"role": "user", "content": "你好"}],
            tools=[],
            timeout_seconds=30,
        )

    error = captured.value
    assert error.status_code == 400
    assert error.upstream_status == 400
    assert error.upstream_error_type == "invalid_request_error"
    assert error.upstream_error_code == "unsupported_tool_schema"
    assert error.upstream_error_param == "tools"
    assert error.provider_request_id == "req-f3-safe"
    assert "F3_SUPER_SECRET_VALUE" not in repr(error)
    assert "F3_SUPER_SECRET_VALUE" not in repr(vars(error))


def test_openai_status_error_rejects_malicious_structured_metadata():
    sdk_error = openai.BadRequestError(
        "safe",
        response=httpx.Response(
            400, request=httpx.Request("POST", "https://example.test")
        ),
        body={
            "error": {
                "type": "invalid_request_error",
                "code": "abc\nAuthorization: Bearer SECRET",
                "param": "tools",
            }
        },
    )
    client = OpenAIChatClient(
        api_key="placeholder-test-key",
        sdk_client=SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions(sdk_error))
        ),
    )

    with pytest.raises(ProviderClientError) as captured:
        client.complete(
            model="configured-model",
            messages=[{"role": "user", "content": "你好"}],
            tools=[],
            timeout_seconds=30,
        )

    assert captured.value.upstream_error_code is None
    assert captured.value.upstream_error_type == "invalid_request_error"
    assert captured.value.upstream_error_param == "tools"
