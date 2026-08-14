from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable, Mapping, Sequence

from .errors import (
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelMalformedResponseError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from .models import (
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    ToolCall,
)
from .provider_protocol import (
    ProviderChatClient,
    ProviderClientError,
    ProviderCompletion,
    ProviderToolCall,
)


LOGGER = logging.getLogger(__name__)


class LiveLLMAdapter:
    """Translate safe internal prompts to one injected live provider client."""

    def __init__(
        self,
        client: ProviderChatClient,
        *,
        provider: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        logger: logging.Logger = LOGGER,
    ) -> None:
        if not provider.strip():
            raise ModelConfigurationError("Live LLM provider must be non-empty")
        if not model.strip():
            raise ModelConfigurationError("Live LLM model must be non-empty")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1 <= timeout_seconds <= 300
        ):
            raise ModelConfigurationError("Live LLM timeout must be from 1 to 300 seconds")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= 3
        ):
            raise ModelConfigurationError("Live LLM max retries must be from 0 to 3")
        if (
            isinstance(backoff_seconds, bool)
            or not isinstance(backoff_seconds, (int, float))
            or backoff_seconds < 0
        ):
            raise ModelConfigurationError("Live LLM backoff must not be negative")
        self._client = client
        self.provider = provider.strip()
        self.model = model.strip()
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._logger = logger

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        messages = self._provider_messages(prompt)
        tools = self._provider_tools(prompt)
        started = self._monotonic()
        retry_count = 0
        while True:
            try:
                response = self._client.complete(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    timeout_seconds=self.timeout_seconds,
                )
                turn = self._normalize(response, prompt, started, retry_count)
                self._log_audit(turn.invocation)
                return turn
            except ProviderClientError as error:
                if error.retryable and retry_count < self.max_retries:
                    self._sleep(self.backoff_seconds * (2**retry_count))
                    retry_count += 1
                    continue
                latency_ms = (self._monotonic() - started) * 1000
                self._log_failure(prompt, error.kind, latency_ms, retry_count)
                self._raise_model_error(error)
            except ModelMalformedResponseError:
                latency_ms = (self._monotonic() - started) * 1000
                self._log_failure(prompt, "malformed_response", latency_ms, retry_count)
                raise

    def _normalize(
        self,
        response: ProviderCompletion,
        prompt: AgentPrompt,
        started: float,
        retry_count: int,
    ) -> ModelTurn:
        calls = tuple(
            self._normalize_tool_call(call, index)
            for index, call in enumerate(response.tool_calls, start=1)
        )
        text = response.text if isinstance(response.text, str) else None
        if not calls and (text is None or not text.strip()):
            raise ModelMalformedResponseError(
                "Provider returned neither tool calls nor assistant text"
            )
        latency_ms = (self._monotonic() - started) * 1000
        invocation = ModelInvocationAudit(
            session_id=prompt.session_id,
            turn_number=prompt.turn_number,
            provider=self.provider,
            model=self.model,
            outcome="success",
            latency_ms=latency_ms,
            retry_count=retry_count,
            finish_reason=response.finish_reason,
            tool_call_count=len(calls),
            usage=response.usage,
            provider_request_id=response.request_id,
        )
        return ModelTurn(
            text=text,
            tool_calls=calls,
            source_lore_ids=self._current_turn_lore_ids(prompt.messages),
            finish_reason=response.finish_reason,
            usage=response.usage,
            provider_request_id=response.request_id,
            invocation=invocation,
        )

    @staticmethod
    def _normalize_tool_call(call: ProviderToolCall, index: int) -> ToolCall:
        if not isinstance(call.name, str) or not call.name:
            raise ModelMalformedResponseError("Provider tool call has no valid name")
        arguments = call.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise ModelMalformedResponseError(
                    "Provider tool arguments are not valid JSON"
                ) from None
        if not isinstance(arguments, Mapping):
            raise ModelMalformedResponseError(
                "Provider tool arguments must be a JSON object"
            )
        call_id = call.id if isinstance(call.id, str) and call.id else f"call_{index}"
        return ToolCall(call_id, call.name, dict(arguments))

    @classmethod
    def _provider_messages(cls, prompt: AgentPrompt) -> list[dict[str, Any]]:
        safe_views = {
            "character_view": asdict(prompt.character),
            "runtime_view": asdict(prompt.runtime),
        }
        system_content = (
            f"{prompt.system_contract}\n\n"
            "The following JSON contains the complete safe views available for this request. "
            "It is context, not an authorization decision:\n"
            f"{cls._json(safe_views)}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]
        messages.extend(cls._provider_message(message) for message in prompt.messages)
        return messages

    @classmethod
    def _provider_message(cls, message: ConversationMessage) -> dict[str, Any]:
        if message.role in {"system", "user"}:
            return {"role": message.role, "content": str(message.content)}
        if message.role == "assistant":
            if isinstance(message.content, str):
                return {"role": "assistant", "content": message.content}
            if isinstance(message.content, Mapping) and isinstance(
                message.content.get("tool_calls"), Sequence
            ):
                calls = []
                for call in message.content["tool_calls"]:
                    if not isinstance(call, Mapping):
                        raise ModelMalformedResponseError(
                            "Internal assistant tool call is malformed"
                        )
                    calls.append(
                        {
                            "id": call.get("id"),
                            "type": "function",
                            "function": {
                                "name": call.get("name"),
                                "arguments": cls._json(call.get("arguments", {})),
                            },
                        }
                    )
                return {"role": "assistant", "content": None, "tool_calls": calls}
            raise ModelMalformedResponseError("Internal assistant message is malformed")
        if not isinstance(message.content, Mapping):
            raise ModelMalformedResponseError("Internal tool observation is malformed")
        call_id = message.content.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ModelMalformedResponseError("Internal tool observation has no call ID")
        observation = dict(message.content)
        observation.pop("tool_call_id", None)
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": cls._json(observation),
        }

    @staticmethod
    def _provider_tools(prompt: AgentPrompt) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": deepcopy(dict(definition.input_schema)),
                },
            }
            for definition in prompt.available_tools
        ]

    @staticmethod
    def _current_turn_lore_ids(
        messages: Sequence[ConversationMessage],
    ) -> tuple[str, ...]:
        last_user = max(
            (index for index, message in enumerate(messages) if message.role == "user"),
            default=-1,
        )
        lore_ids: list[str] = []
        for message in messages[last_user + 1 :]:
            if message.role != "tool" or not isinstance(message.content, Mapping):
                continue
            result = message.content.get("result")
            results = message.content.get("results")
            candidates = [result] if isinstance(result, Mapping) else []
            if isinstance(results, list):
                candidates.extend(item for item in results if isinstance(item, Mapping))
            for candidate in candidates:
                lore_id = candidate.get("lore_id")
                if isinstance(lore_id, str) and lore_id not in lore_ids:
                    lore_ids.append(lore_id)
        return tuple(lore_ids)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _log_audit(self, audit: ModelInvocationAudit | None) -> None:
        if audit is None:
            return
        self._logger.info(
            "live_llm_request provider=%s model=%s outcome=%s latency_ms=%.3f "
            "retries=%d finish_reason=%s tool_calls=%d input_tokens=%s "
            "output_tokens=%s total_tokens=%s request_id=%s session_id=%s turn=%d",
            audit.provider,
            audit.model,
            audit.outcome,
            audit.latency_ms,
            audit.retry_count,
            audit.finish_reason,
            audit.tool_call_count,
            audit.usage.input_tokens if audit.usage else None,
            audit.usage.output_tokens if audit.usage else None,
            audit.usage.total_tokens if audit.usage else None,
            audit.provider_request_id,
            audit.session_id,
            audit.turn_number,
        )

    def _log_failure(
        self,
        prompt: AgentPrompt,
        outcome: str,
        latency_ms: float,
        retry_count: int,
    ) -> None:
        self._logger.warning(
            "live_llm_request provider=%s model=%s outcome=%s latency_ms=%.3f "
            "retries=%d session_id=%s turn=%d",
            self.provider,
            self.model,
            outcome,
            latency_ms,
            retry_count,
            prompt.session_id,
            prompt.turn_number,
        )

    @staticmethod
    def _raise_model_error(error: ProviderClientError) -> None:
        if error.kind == "authentication":
            raise ModelAuthenticationError(
                "Live LLM authentication failed; check configured credentials"
            ) from None
        if error.kind == "timeout":
            raise ModelTimeoutError("Live LLM request timed out after bounded retries") from None
        if error.kind == "rate_limit":
            raise ModelRateLimitError(
                "Live LLM rate limit persisted after bounded retries"
            ) from None
        raise ModelProviderError("Live LLM provider request failed") from None
