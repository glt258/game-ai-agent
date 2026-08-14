from __future__ import annotations

import os

import pytest

from agents import (
    LiveLLMAdapter,
    NpcConversationAgent,
    model_from_environment,
)
from story import StoryRuntime


RUN_LIVE = os.getenv("NPC_RUN_LIVE_SMOKE") == "1"
HAS_KEY = bool(os.getenv("NPC_LLM_API_KEY"))


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE or not HAS_KEY,
    reason="Set NPC_RUN_LIVE_SMOKE=1 and live LLM environment variables; may incur cost",
)
def test_optional_live_grounding_pipeline_smoke():
    model = model_from_environment(mode_override="live")
    assert isinstance(model, LiveLLMAdapter)
    story_runtime = StoryRuntime()
    state = story_runtime.initial_state("story_after_the_show_001")
    agent = NpcConversationAgent(
        model,
        story_repository=story_runtime.repository,
    )
    session = agent.create_session(
        "live-smoke", "char_launch_004", "story_after_the_show_001"
    )

    response = agent.chat(session, state, "你好。请只使用当前证据回答。")

    assert response.text.strip()
    assert response.grounding is not None
    assert session.messages[-1].content == response.text
    assert response.model_invocations
    assert response.model_invocations[0].provider == os.getenv(
        "NPC_LLM_PROVIDER", "openai"
    ).lower()
