from __future__ import annotations

from collections import deque
from typing import Protocol

from .models import AgentPrompt, ModelTurn


class AgentModel(Protocol):
    """Provider-neutral model boundary. It receives views, never Canon stores."""

    def generate(self, prompt: AgentPrompt) -> ModelTurn: ...


class ScriptedAgentModel:
    """Deterministic model fixture used by tests and evals."""

    def __init__(self, turns: list[ModelTurn]) -> None:
        self._turns = deque(turns)
        self.prompts: list[AgentPrompt] = []

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        self.prompts.append(prompt)
        if not self._turns:
            raise RuntimeError("ScriptedAgentModel has no remaining turns")
        return self._turns.popleft()
