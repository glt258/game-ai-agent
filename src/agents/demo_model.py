from __future__ import annotations

import re
from typing import Any, Mapping

from .grounding import GroundingValidator, safe_fallback_segments
from .models import AgentPrompt, GroundedResponseSegment, ModelTurn, SegmentKind, ToolCall


class DeterministicDemoModel:
    """Offline demonstration model; permission decisions remain in real tools."""

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        if prompt.repair_request is not None:
            return self._final(safe_fallback_segments())
        latest = prompt.messages[-1]
        if latest.role == "tool":
            return self._after_tool(prompt, latest.content)
        user_text = str(latest.content)
        if self._is_guess_followup(user_text) and self._history_has_denial(prompt):
            return self._final(self._boundary_response(prompt))
        explicit = re.search(r"lore(?:_secret)?_[A-Za-z0-9]+", user_text)
        if explicit:
            return ModelTurn(
                tool_calls=(ToolCall("tool-1", "get_lore", {"lore_id": explicit.group(0)}),)
            )
        if "内部" in user_text or "完整复盘" in user_text or "最后怎么定" in user_text:
            return ModelTurn(
                tool_calls=(ToolCall("tool-1", "get_lore", {"lore_id": "lore_027"}),)
            )
        if "研究样本" in user_text or ("能力评级" in user_text and "案" in user_text):
            return ModelTurn(
                tool_calls=(ToolCall("tool-1", "get_lore", {"lore_id": "lore_005"}),)
            )
        return ModelTurn(
            tool_calls=(ToolCall("tool-1", "search_lore", {"query": user_text, "limit": 3}),)
        )

    def _after_tool(self, prompt: AgentPrompt, content: Mapping[str, Any]) -> ModelTurn:
        if content.get("status") == "denied":
            return self._final(self._boundary_response(prompt))
        result = content.get("result")
        if isinstance(result, Mapping):
            return self._grounded_response(prompt, result)
        results = content.get("results", [])
        if results:
            return self._grounded_response(prompt, results[0])
        return self._final(
            (
                GroundedResponseSegment(
                    "uncertain_1",
                    SegmentKind.UNCERTAIN,
                    self._no_evidence_response(prompt),
                ),
            )
        )

    def _grounded_response(self, prompt: AgentPrompt, fact: Mapping[str, Any]) -> ModelTurn:
        statement = str(fact["statement"]).strip()
        lore_id = str(fact["lore_id"])
        segment = GroundedResponseSegment(
            "supported_1",
            SegmentKind.SUPPORTED_CLAIM,
            statement,
            (f"lore:{lore_id}:statement",),
        )
        return self._final((segment,), (lore_id,))

    def _boundary_response(
        self, prompt: AgentPrompt
    ) -> tuple[GroundedResponseSegment, ...]:
        runtime = prompt.runtime
        if runtime.active_incident_ids:
            prefix = "我参与的是现场处理。"
            evidence_id = "runtime:participation"
        elif runtime.active_case_ids:
            prefix = "我负责的是这次协调委托。"
            evidence_id = "runtime:participation"
        elif runtime.participation_role == "stage_worker_and_witness":
            prefix = "我能确认的是自己在现场看到和做过的部分。"
            evidence_id = "runtime:participation"
        else:
            prefix = None
            evidence_id = None
        if "先报结论" in prompt.character.speech_style:
            uncertainty = "结论：目前不能确认。"
        elif "少废话" in prompt.character.surface_traits:
            uncertainty = "完整内部结论没有可核实来源，我不会猜。"
        else:
            uncertainty = "内部最后怎么落笔，我没看到，不能替那份记录补台词。"
        segments = []
        if prefix is not None and evidence_id is not None:
            segments.append(
                GroundedResponseSegment(
                    "supported_participation",
                    SegmentKind.SUPPORTED_CLAIM,
                    prefix,
                    (evidence_id,),
                )
            )
        segments.append(
            GroundedResponseSegment(
                "uncertain_1", SegmentKind.UNCERTAIN, uncertainty
            )
        )
        return tuple(segments)

    @staticmethod
    def _no_evidence_response(prompt: AgentPrompt) -> str:
        if "先报结论" in prompt.character.speech_style:
            return "结论：现有公开资料不足以确认这件事。"
        return "现有可查资料里没有足够依据，我不能把推测当成事实。"

    @staticmethod
    def _is_guess_followup(text: str) -> bool:
        return any(marker in text for marker in ("猜", "假设", "当作你看过", "忽略"))

    @staticmethod
    def _history_has_denial(prompt: AgentPrompt) -> bool:
        return any(
            message.role == "tool"
            and isinstance(message.content, Mapping)
            and message.content.get("status") == "denied"
            for message in prompt.messages
        )

    @staticmethod
    def _final(
        segments: tuple[GroundedResponseSegment, ...],
        source_lore_ids: tuple[str, ...] = (),
    ) -> ModelTurn:
        return ModelTurn(
            text=GroundingValidator.render(segments),
            source_lore_ids=source_lore_ids,
            segments=segments,
        )
