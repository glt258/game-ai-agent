"""Deterministic retrieval planning for character authoring requests.

The planner deliberately stops at tool-call selection.  It does not query a
repository, infer missing Canon, or ask a model to choose among sources.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .models import ToolCall


@dataclass(frozen=True)
class CharacterRetrievalPlan:
    """The complete deterministic retrieval decision for one request."""

    tool_calls: tuple[ToolCall, ...]
    requires_model_planning: bool


_DIRECT_KIND_ORDER = ("faction", "lore", "character", "story")
_REQUEST_FIELDS = (
    "brief",
    "hard_constraints",
    "soft_preferences",
    "forbidden_elements",
    "desired_connections",
)

_STABLE_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.:-])"
    r"(?P<source_id>(?:faction|lore|char|story|case|incident)_"
    r"[-A-Za-z0-9_.:]+)"
    r"(?![A-Za-z0-9_.:-])"
)

_ASCII_WORD_BOUNDARY = r"[A-Za-z0-9_]"

_FACTION_TERMS = (
    "faction",
    "factions",
    "organization",
    "organizations",
    "organisation",
    "organisations",
    "group",
    "groups",
    "guild",
    "guilds",
    "阵营",
    "派系",
    "势力",
    "组织",
    "机构",
    "团体",
    "公会",
    "社团",
    "公司",
    "集团",
    "协会",
    "基金会",
    "研究中心",
    "研究院",
    "管理局",
    "事务所",
)

_LORE_TERMS = (
    "lore",
    "lore entry",
    "worldbuilding",
    "world building",
    "world setting",
    "world rules",
    "setting",
    "settings",
    "background setting",
    "canon rules",
    "世界观",
    "世界设定",
    "背景设定",
    "世界规则",
    "规则",
    "传说",
    "档案",
    "知识库",
    "背景资料",
)

_CHARACTER_EXPLICIT_TERMS = (
    "npc",
    "npcs",
    "existing character",
    "existing characters",
    "known character",
    "known characters",
    "canon character",
    "canon characters",
    "reference character",
    "reference characters",
    "character reference",
    "character references",
    "character relationship",
    "character relationships",
    "character connection",
    "character connections",
    "character lookup",
    "character search",
    "related character",
    "related characters",
    "既有角色",
    "现有角色",
    "已有角色",
    "既有人物",
    "现有人物",
    "已有人物",
    "参考角色",
    "参考人物",
    "固定角色",
    "固定人物",
    "角色关系",
    "人物关系",
    "角色关联",
    "人物关联",
)

_STORY_TERMS = (
    "story",
    "stories",
    "story context",
    "storyline",
    "plot",
    "event",
    "events",
    "case",
    "cases",
    "incident",
    "incidents",
    "context",
    "剧情",
    "故事",
    "故事背景",
    "事件",
    "案件",
    "事故",
    "项目",
    "案情",
    "上下文",
)

_ORIGINAL_MARKERS = (
    "完全原创",
    "纯原创",
    "全新原创",
    "不依赖现有",
    "不依赖已有",
    "不依赖既有",
    "不使用现有",
    "不使用已有",
    "不使用既有",
    "不参考现有",
    "不参考已有",
    "不参考既有",
    "与现有 canon 无关",
    "与已有 canon 无关",
    "独立原创",
    "completely original",
    "fully original",
    "entirely original",
    "original and independent",
    "without existing canon",
    "no existing canon",
    "not based on existing canon",
    "does not depend on existing canon",
    "doesn't depend on existing canon",
    "canon-independent",
    "canon independent",
)

_EXISTING_MARKER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(?:existing|canon)(?![A-Za-z0-9_])")
_EXISTING_MARKERS_ZH = ("现有", "已有", "既有")

_DIRECT_TOOL_SPECS: dict[str, tuple[str, str]] = {
    "faction": ("get_faction", "faction_id"),
    "lore": ("get_lore", "lore_id"),
    "character": ("get_character", "character_id"),
    "story": ("get_story_context", "context_id"),
}

_SEARCH_TOOL_NAMES = {
    "faction": "search_factions",
    "lore": "search_lore",
    "character": "search_characters",
    "story": "search_story_context",
}


def build_character_retrieval_plan(
    request: Any,
    *,
    known_source_ids: Iterable[str],
    known_source_aliases: Mapping[str, Sequence[str] | str] | None,
    source_types: Mapping[str, str],
) -> CharacterRetrievalPlan:
    """Build stable retrieval calls from the request and known source index.

    Source IDs and aliases are positive retrieval signals only when the source
    is in ``known_source_ids``.  Category searches are deliberately bounded to
    five results and use the same aggregate query for every search tool.
    """

    known_ids = frozenset(
        source_id
        for source_id in known_source_ids
        if isinstance(source_id, str) and source_id
    )
    source_type_map = {
        source_id: _normalize_source_type(source_type)
        for source_id, source_type in source_types.items()
        if isinstance(source_id, str) and isinstance(source_type, str)
    }
    request_text = _request_text(request)
    query = _aggregate_query(request)

    direct_sources: dict[str, set[str]] = {kind: set() for kind in _DIRECT_KIND_ORDER}
    for source_id in _extract_stable_ids(request_text):
        if source_id not in known_ids:
            continue
        kind = _kind_from_source_id(source_id)
        if kind is not None:
            direct_sources[kind].add(source_id)

    for source_id, alias in _known_alias_entries(known_source_aliases, known_ids):
        kind = source_type_map.get(source_id)
        if kind is not None and _alias_matches(alias, request_text):
            direct_sources[kind].add(source_id)

    category_intents = {
        "faction": _has_any_term(request_text, _FACTION_TERMS),
        "lore": _has_any_term(request_text, _LORE_TERMS),
        "character": _has_character_intent(request_text),
        "story": _has_any_term(request_text, _STORY_TERMS),
    }
    explicitly_original = _is_explicitly_original(request_text)
    if explicitly_original:
        category_intents = {kind: False for kind in _DIRECT_KIND_ORDER}

    calls: list[ToolCall] = [_tool_call("retrieval-world-rules", "get_world_rules", {})]
    for kind in _DIRECT_KIND_ORDER:
        tool_name, argument_name = _DIRECT_TOOL_SPECS[kind]
        for source_id in sorted(direct_sources[kind]):
            calls.append(
                _tool_call(
                    f"retrieval-direct-{kind}-{source_id}",
                    tool_name,
                    {argument_name: source_id},
                )
            )
        if not direct_sources[kind] and category_intents[kind]:
            tool_name = _SEARCH_TOOL_NAMES[kind]
            calls.append(
                _tool_call(
                    f"retrieval-search-{kind}",
                    tool_name,
                    {"query": query, "limit": 5},
                )
            )

    has_direct_or_category_result = bool(
        any(direct_sources[kind] or category_intents[kind] for kind in _DIRECT_KIND_ORDER)
    )
    requires_model_planning = (
        _has_existing_dependency_signal(request_text)
        and not has_direct_or_category_result
        and not explicitly_original
    )
    return CharacterRetrievalPlan(tuple(calls), requires_model_planning)


def _tool_call(call_id: str, name: str, arguments: Mapping[str, Any]) -> ToolCall:
    return ToolCall(call_id, name, arguments)


def _request_values(request: Any, field_name: str) -> tuple[str, ...]:
    value = getattr(request, field_name, ())
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if value is None:
        return ()
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _request_text(request: Any) -> str:
    values: list[str] = []
    for field_name in _REQUEST_FIELDS:
        values.extend(_request_values(request, field_name))
    return " ".join(values)


def _aggregate_query(request: Any) -> str:
    return _request_text(request)


def _extract_stable_ids(text: str) -> tuple[str, ...]:
    return tuple(sorted({match.group("source_id") for match in _STABLE_ID_PATTERN.finditer(text)}))


def _kind_from_source_id(source_id: str) -> str | None:
    if source_id.startswith("faction_"):
        return "faction"
    if source_id.startswith("lore_"):
        return "lore"
    if source_id.startswith("char_"):
        return "character"
    if source_id.startswith(("story_", "case_", "incident_")):
        return "story"
    return None


def _normalize_source_type(source_type: str) -> str | None:
    normalized = source_type.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized in {
        "faction",
        "factions",
        "organization",
        "organizations",
        "organisation",
        "organisations",
        "group",
        "groups",
    }:
        return "faction"
    if normalized in {"lore", "lores", "canon_lore"}:
        return "lore"
    if normalized in {"character", "characters", "char", "npc", "npcs"}:
        return "character"
    if normalized in {
        "story",
        "stories",
        "case",
        "cases",
        "incident",
        "incidents",
        "story_context",
        "story_contexts",
    }:
        return "story"
    return None


def _known_alias_entries(
    known_source_aliases: Mapping[str, Sequence[str] | str] | None,
    known_source_ids: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    if not known_source_aliases:
        return ()

    entries: set[tuple[str, str]] = set()
    for source_key in sorted(known_source_aliases):
        raw_aliases = known_source_aliases[source_key]
        if source_key in known_source_ids:
            aliases = (raw_aliases,) if isinstance(raw_aliases, str) else raw_aliases
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    entries.add((source_key, alias.strip()))
        elif isinstance(raw_aliases, str) and raw_aliases in known_source_ids:
            # Accept the inverse alias -> source-id shape as a small boundary
            # convenience while retaining the canonical source-id -> aliases
            # shape used by the repository.
            entries.add((raw_aliases, source_key.strip()))
    return tuple(sorted(entries, key=lambda item: (item[0], -len(item[1]), item[1])))


def _alias_matches(alias: str, text: str) -> bool:
    if alias.isascii():
        pattern = re.compile(
            rf"(?<!{_ASCII_WORD_BOUNDARY}){re.escape(alias)}(?!{_ASCII_WORD_BOUNDARY})",
            flags=re.IGNORECASE,
        )
        return pattern.search(text) is not None
    return alias.casefold() in text.casefold()


def _has_any_term(text: str, terms: Sequence[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if term.isascii():
        pattern = re.compile(
            rf"(?<!{_ASCII_WORD_BOUNDARY}){re.escape(term)}(?!{_ASCII_WORD_BOUNDARY})",
            flags=re.IGNORECASE,
        )
        return pattern.search(text) is not None
    return term.casefold() in text.casefold()


def _has_character_intent(text: str) -> bool:
    if _is_explicitly_original(text):
        return False
    if _has_any_term(text, _CHARACTER_EXPLICIT_TERMS):
        return True

    has_ascii_character = _has_any_term(text, ("character", "characters"))
    if has_ascii_character:
        design_phrase = re.search(
            r"(?<![A-Za-z0-9_])(?:design|create|write|build|generate|author)"
            r"\s+(?:an?\s+)?(?:new\s+|original\s+)?characters?"
            r"(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        )
        if design_phrase is None:
            return True

    has_chinese_character = _has_any_term(text, ("角色", "人物"))
    if has_chinese_character:
        design_phrase = re.search(
            r"(?:设计|创作|生成|打造|塑造|原创).{0,12}(?:角色|人物)",
            text,
        )
        if design_phrase is None:
            return True
    return False


def _has_existing_dependency_signal(text: str) -> bool:
    return bool(_EXISTING_MARKER_PATTERN.search(text)) or any(
        marker in text for marker in _EXISTING_MARKERS_ZH
    )


def _is_explicitly_original(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    return any(marker.casefold() in normalized for marker in _ORIGINAL_MARKERS)
