from __future__ import annotations

import os

import pytest

from agents import (
    AgentPrompt,
    ConversationMessage,
    LiveLLMAdapter,
    NpcCharacterView,
    NpcRuntimeView,
    model_from_environment,
)


RUN_LIVE = os.getenv("NPC_RUN_LIVE_SMOKE") == "1"
HAS_KEY = bool(os.getenv("NPC_LLM_API_KEY"))


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE or not HAS_KEY,
    reason="Set NPC_RUN_LIVE_SMOKE=1 and live LLM environment variables; may incur cost",
)
def test_optional_live_adapter_smoke():
    model = model_from_environment(mode_override="live")
    assert isinstance(model, LiveLLMAdapter)
    prompt = AgentPrompt(
        "Use the grounded response protocol and one approved non-factual safe form.",
        NpcCharacterView("smoke", "测试 NPC", "", (), (), "", "", (), "", "测试 NPC"),
        NpcRuntimeView("smoke-story", "Smoke", None, (), ()),
        (ConversationMessage("user", "你好"),),
        (),
        "live-smoke",
        1,
    )

    turn = model.generate(prompt)

    assert isinstance(turn.text, str) and turn.text.strip()
    assert turn.segments
    assert turn.invocation is not None
    assert turn.invocation.provider == os.getenv("NPC_LLM_PROVIDER", "openai").lower()
