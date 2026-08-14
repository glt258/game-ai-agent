from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import UnknownLoreError

from .errors import AgentToolError
from .models import LoreFact, ToolAuditEntry


@dataclass(frozen=True)
class ToolExecution:
    observation: Mapping[str, Any]
    audit: ToolAuditEntry
    allowed_lore_ids: frozenset[str]


class KnowledgeToolbox:
    """The only Lore-content boundary exposed to NPC orchestration."""

    allowed_tools = frozenset({"search_lore", "get_lore"})

    def __init__(self, resolver: KnowledgeResolver) -> None:
        self._resolver = resolver

    def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        character_id: str,
        context: KnowledgeContext,
        round_number: int,
    ) -> ToolExecution:
        if tool_name not in self.allowed_tools:
            raise AgentToolError(f"Unknown or forbidden tool: {tool_name}")
        if tool_name == "get_lore":
            return self._get_lore(arguments, character_id, context, round_number)
        return self._search_lore(arguments, character_id, context, round_number)

    def _get_lore(
        self,
        arguments: Mapping[str, Any],
        character_id: str,
        context: KnowledgeContext,
        round_number: int,
    ) -> ToolExecution:
        if set(arguments) != {"lore_id"}:
            raise AgentToolError("get_lore accepts only lore_id")
        lore_id = arguments.get("lore_id")
        if not isinstance(lore_id, str) or not re.fullmatch(r"lore(?:_secret)?_[A-Za-z0-9]+", lore_id):
            raise AgentToolError("get_lore requires a valid lore_id")
        try:
            decision = self._resolver.resolve(character_id, lore_id, context)
        except UnknownLoreError as error:
            raise AgentToolError(str(error)) from error
        if decision.decision == "deny":
            observation = {
                "status": "denied",
                "reason_code": "knowledge_access_denied",
                "lore_id": lore_id,
            }
            audit = ToolAuditEntry(
                round_number,
                "get_lore",
                {"lore_id": lore_id},
                "denied",
                denied_requested_ids=(lore_id,),
                resolver_reason_code=decision.reason_code,
            )
            return ToolExecution(observation, audit, frozenset())
        fact = self._fact(lore_id)
        observation = {"status": "ok", "result": fact.to_model_dict()}
        audit = ToolAuditEntry(
            round_number,
            "get_lore",
            {"lore_id": lore_id},
            "allowed",
            allowed_lore_ids=(lore_id,),
            resolver_reason_code=decision.reason_code,
        )
        return ToolExecution(observation, audit, frozenset({lore_id}))

    def _search_lore(
        self,
        arguments: Mapping[str, Any],
        character_id: str,
        context: KnowledgeContext,
        round_number: int,
    ) -> ToolExecution:
        if not set(arguments) <= {"query", "limit"} or "query" not in arguments:
            raise AgentToolError("search_lore accepts query and optional limit")
        query = arguments.get("query")
        limit = arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip():
            raise AgentToolError("search_lore query must be a non-empty string")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise AgentToolError("search_lore limit must be an integer from 1 to 10")

        # Permission filtering deliberately happens before text scoring. Denied
        # titles, statements, counts, and rankings never enter the search corpus.
        allowed: list[tuple[LoreFact, str]] = []
        for lore_id in sorted(self._resolver.lore):
            decision = self._resolver.resolve(character_id, lore_id, context)
            if decision.decision == "allow":
                fact = self._fact(lore_id)
                allowed.append((fact, f"{fact.title} {fact.statement}"))
        ranked = sorted(
            (
                (self._score(query, text), fact.lore_id, fact)
                for fact, text in allowed
            ),
            key=lambda item: (-item[0], item[1]),
        )
        results = [fact for score, _, fact in ranked if score > 0][:limit]
        result_ids = tuple(fact.lore_id for fact in results)
        observation = {
            "status": "ok",
            "results": [fact.to_model_dict() for fact in results],
        }
        audit = ToolAuditEntry(
            round_number,
            "search_lore",
            {"query": query, "limit": limit},
            "allowed",
            allowed_lore_ids=result_ids,
        )
        return ToolExecution(observation, audit, frozenset(result_ids))

    def _fact(self, lore_id: str) -> LoreFact:
        record = self._resolver.lore[lore_id]
        return LoreFact(
            lore_id,
            record.get("title", ""),
            record.get("statement", "").strip(),
            record.get("category"),
        )

    @classmethod
    def _score(cls, query: str, text: str) -> int:
        query_norm, text_norm = cls._normalize(query), cls._normalize(text)
        if not query_norm:
            return 0
        score = 20 if query_norm in text_norm else 0
        query_units = cls._units(query_norm)
        text_units = cls._units(text_norm)
        return score + sum(2 if len(unit) > 1 else 1 for unit in query_units & text_units)

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(character.lower() for character in value if character.isalnum())

    @staticmethod
    def _units(value: str) -> set[str]:
        units = set(re.findall(r"[a-z0-9]+", value))
        chinese = [character for character in value if "\u4e00" <= character <= "\u9fff"]
        units.update(chinese)
        units.update("".join(chinese[index : index + 2]) for index in range(len(chinese) - 1))
        return units
