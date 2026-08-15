from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

import openai

from .models import ModelUsage
from .provider_protocol import (
    NegotiatedResponseContract,
    ProviderChatClient,
    ProviderClientError,
    ProviderCompletion,
    ProviderToolCall,
    ResponseMode,
    TEXT_NEGOTIATED_RESPONSE,
)


class OpenAIChatClient(ProviderChatClient):
    """OpenAI-compatible Chat Completions transport with SDK retries disabled."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        request_options: Mapping[str, Any] | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self.base_url = base_url
        self.request_options = deepcopy(dict(request_options or {}))
        reserved = {"model", "messages", "tools", "timeout", "response_format"}
        if reserved & set(self.request_options):
            raise ValueError(
                "Provider request options cannot override core request fields"
            )
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
        response_contract: NegotiatedResponseContract = TEXT_NEGOTIATED_RESPONSE,
        response_mode: str | None = None,
    ) -> ProviderCompletion:
        # Preserve the v0.2 client API for direct callers while the runtime now
        # uses the richer negotiated contract.
        if response_mode is not None:
            legacy_modes = {
                "text": TEXT_NEGOTIATED_RESPONSE,
                "structured_json": NegotiatedResponseContract(
                    "structured_json", ResponseMode.JSON_OBJECT
                ),
            }
            try:
                response_contract = legacy_modes[response_mode]
            except KeyError:
                raise ValueError(
                    f"Unsupported provider response mode: {response_mode}"
                ) from None
        request: dict[str, Any] = deepcopy(self.request_options)
        request.update(
            {
                "model": model,
                "messages": list(messages),
                "timeout": timeout_seconds,
            }
        )
        if tools:
            request["tools"] = list(tools)
        if response_contract.mode is ResponseMode.JSON_OBJECT:
            request["response_format"] = {"type": "json_object"}
        elif response_contract.mode is ResponseMode.JSON_SCHEMA:
            if response_contract.json_schema is None:
                raise ValueError("JSON Schema response contract requires a schema")
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_contract.name,
                    "strict": True,
                    "schema": deepcopy(dict(response_contract.json_schema)),
                },
            }
        elif response_contract.mode is not ResponseMode.TEXT:
            raise ValueError(
                f"Unsupported provider response mode: {response_contract.mode}"
            )
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
