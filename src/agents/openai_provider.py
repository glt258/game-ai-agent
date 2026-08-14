from __future__ import annotations

from typing import Any, Mapping, Sequence

import openai

from .models import ModelUsage
from .provider_protocol import (
    ProviderChatClient,
    ProviderClientError,
    ProviderCompletion,
    ProviderToolCall,
)


class OpenAIChatClient(ProviderChatClient):
    """OpenAI Chat Completions transport with SDK retries disabled."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        sdk_client: Any | None = None,
    ) -> None:
        if sdk_client is not None:
            self._client = sdk_client
            return
        options: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": 0,
            "timeout": timeout_seconds,
        }
        if base_url is not None:
            options["base_url"] = base_url
        self._client = openai.OpenAI(**options)

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
    ) -> ProviderCompletion:
        request: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "timeout": timeout_seconds,
        }
        if tools:
            request["tools"] = list(tools)
        try:
            completion = self._client.chat.completions.create(**request)
        except openai.AuthenticationError:
            raise ProviderClientError(
                "authentication", retryable=False, status_code=401
            ) from None
        except openai.APITimeoutError:
            raise ProviderClientError("timeout", retryable=True) from None
        except openai.RateLimitError:
            raise ProviderClientError(
                "rate_limit", retryable=True, status_code=429
            ) from None
        except openai.APIConnectionError:
            raise ProviderClientError("provider", retryable=True) from None
        except openai.APIStatusError as error:
            status_code = error.status_code
            if status_code == 401:
                kind = "authentication"
            elif status_code == 429:
                kind = "rate_limit"
            else:
                kind = "provider"
            raise ProviderClientError(
                kind,
                retryable=status_code == 429 or status_code >= 500,
                status_code=status_code,
            ) from None
        except openai.OpenAIError:
            raise ProviderClientError("provider", retryable=False) from None

        if not completion.choices:
            return ProviderCompletion(request_id=getattr(completion, "_request_id", None))
        choice = completion.choices[0]
        message = choice.message
        calls = tuple(
            ProviderToolCall(
                id=getattr(call, "id", None),
                name=getattr(call.function, "name", None),
                arguments=getattr(call.function, "arguments", None),
            )
            for call in (message.tool_calls or ())
        )
        sdk_usage = completion.usage
        usage = None
        if sdk_usage is not None:
            usage = ModelUsage(
                input_tokens=getattr(sdk_usage, "prompt_tokens", None),
                output_tokens=getattr(sdk_usage, "completion_tokens", None),
                total_tokens=getattr(sdk_usage, "total_tokens", None),
            )
        return ProviderCompletion(
            text=message.content,
            tool_calls=calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            request_id=getattr(completion, "_request_id", None),
        )
