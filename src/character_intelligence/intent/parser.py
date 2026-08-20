"""Deterministic parser for the first Character Intelligence Layer alpha."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .schema import CharacterDesignIntent


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _first_match(text: str, patterns: Iterable[tuple[str, str]]) -> str | None:
    for pattern, value in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return value
    return None


_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_ELEMENT_PATTERNS = (
    (r"火属性|火元素|火系|pyro|fire", "fire"),
    (r"水属性|水元素|水系|hydro|water", "water"),
    (r"冰属性|冰元素|冰系|cryo|ice", "ice"),
    (r"雷属性|雷元素|雷系|electro|thunder|lightning", "electro"),
    (r"风属性|风元素|风系|anemo|wind", "wind"),
    (r"岩属性|岩元素|岩系|geo|earth", "geo"),
    (r"草属性|草元素|草系|dendro|nature", "nature"),
)

_ROLE_TYPE_PATTERNS = (
    (r"少女|女孩子|young\s*girl|girl", "少女"),
    (r"少年|男孩子|young\s*boy|boy", "少年"),
    (r"女性角色|成年女性|female\s*character|woman", "女性"),
    (r"男性角色|成年男性|male\s*character|man", "男性"),
    (r"npc|非玩家角色", "npc"),
)

_COMBAT_ROLE_PATTERNS = (
    (r"主\s*[cC]|main\s*(?:dps|damage)|主输出|核心输出", "dps"),
    (r"副\s*[cC]|sub\s*(?:dps|damage)|副输出", "sub_dps"),
    (r"辅助|support|增益|治疗|奶妈|healer", "support"),
    (r"坦克|前排|承伤|防御|tank", "defense"),
    (r"控制|control|控场", "control"),
    (r"爆发型|爆发输出|burst", "burst"),
    (r"持续输出|持续伤害|站场|sustain", "sustain"),
)

_TARGET_PATTERNS = (
    (r"女性向|面向女性|female[- ]?oriented", "female_players"),
    (r"男性向|面向男性|male[- ]?oriented", "male_players"),
    (r"儿童|小朋友|children|kids", "children"),
    (r"青少年|年轻玩家|teen(?:s|agers)?", "teen_players"),
    (r"核心玩家|硬核玩家|core\s*players", "core_players"),
    (r"二次元玩家|anime\s*players", "anime_players"),
)

_PERSONALITY_PATTERNS = (
    (r"隐藏压力|隐性压力|压抑感|hidden\s*pressure", "隐藏压力"),
    (r"外向|开朗|热情|outgoing|extrovert(?:ed)?", "外向"),
    (r"内向|introvert(?:ed)?", "内向"),
    (r"冷静|沉着|calm", "冷静"),
    (r"温柔|体贴|gentle|kind", "温柔"),
    (r"坚强|坚韧|strong-willed|resilient", "坚强"),
    (r"神秘|mysterious", "神秘"),
    (r"理性|理智|rational", "理性"),
    (r"乐观|optimistic", "乐观"),
    (r"谨慎|小心|cautious", "谨慎"),
    (r"叛逆|rebellious", "叛逆"),
    (r"幽默|humorous|funny", "幽默"),
    (r"忠诚|loyal", "忠诚"),
)


class DeterministicCharacterDesignIntentParser:
    """Parse common design phrases without an LLM or network request."""

    def parse(self, request: str) -> CharacterDesignIntent:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("character design request must be a non-empty string")
        text = request.strip()

        rarity = self._parse_rarity(text)
        element = _first_match(text, _ELEMENT_PATTERNS)
        combat_role = _first_match(text, _COMBAT_ROLE_PATTERNS) or "unspecified"
        role_type = _first_match(text, _ROLE_TYPE_PATTERNS) or "character"
        target_audience = _first_match(text, _TARGET_PATTERNS) or "general"

        personality: list[str] = []
        for pattern, keyword in _PERSONALITY_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                _append_once(personality, keyword)

        design_goals: list[str] = []
        if element is not None:
            _append_once(design_goals, element)
            _append_once(design_goals, f"element:{element}")
        if re.search(r"爆发|高爆发|burst", text, flags=re.IGNORECASE):
            _append_once(design_goals, "burst")
        if re.search(r"高辨识度|有辨识度|distinctive|recognizable", text, flags=re.IGNORECASE):
            _append_once(design_goals, "distinctive")
        if re.search(r"易上手|容易上手|beginner[- ]?friendly", text, flags=re.IGNORECASE):
            _append_once(design_goals, "beginner_friendly")

        forbidden = self._parse_forbidden_patterns(text)
        return CharacterDesignIntent(
            role_type=role_type,
            combat_role=combat_role,
            rarity=rarity,
            target_audience=target_audience,
            personality_keywords=tuple(personality),
            design_goals=tuple(design_goals),
            forbidden_patterns=forbidden,
            element=element,
            raw_request=text,
        )

    @staticmethod
    def _parse_rarity(text: str) -> int | None:
        arabic = re.search(r"(?:稀有度|星级|rarity\s*[:=]?)\s*([1-9][0-9]?)|([1-9][0-9]?)\s*[- ]?星", text, flags=re.IGNORECASE)
        if arabic:
            value = arabic.group(1) or arabic.group(2)
            return int(value)
        for marker, value in _CHINESE_NUMBERS.items():
            if re.search(rf"{marker}\s*星|星级\s*{marker}", text):
                return value
        if re.search(r"five[- ]?star", text, flags=re.IGNORECASE):
            return 5
        return None

    @staticmethod
    def _parse_forbidden_patterns(text: str) -> tuple[str, ...]:
        values: list[str] = []
        pattern = re.compile(
            r"(?:不要|避免|禁止|不希望|拒绝|不得|不能)\s*(?:有|出现|包含|加入|设计)?\s*([^，。；;,.!?！？\n]{1,32})"
        )
        for match in pattern.finditer(text):
            value = match.group(1).strip(" ：:、 ")
            if value:
                _append_once(values, value)
        return tuple(values)


def parse_character_design_intent(request: str) -> CharacterDesignIntent:
    """Convenience function for the default deterministic parser."""

    return DeterministicCharacterDesignIntentParser().parse(request)


# Short aliases keep the first public API easy to discover while retaining a
# descriptive implementation name for future parser strategies.
CharacterDesignIntentParser = DeterministicCharacterDesignIntentParser
parse_intent = parse_character_design_intent
