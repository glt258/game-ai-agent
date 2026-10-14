"""Deterministic parser for the first Character Intelligence Layer alpha."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from typing import Any, Mapping

from along_street_resources import data_resource
from combat_semantics import CombatRoleProfile
from knowledge.resolver import KnowledgeResolver
from reference_corpus.loader import load_combat_vocabulary

from .schema import (
    CharacterDesignIntent,
    ExplicitAgeRequirement,
    ExplicitGenderRequirement,
)


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
    (r"main[_\s-]*(?:dps|damage)(?:\s*dealer)?|primary[_\s-]*(?:dps|damage)|主\s*[cC]|主输出|核心输出", True, False),
    (r"sub[_\s-]*(?:dps|damage)(?:\s*dealer)?|secondary[_\s-]*(?:dps|damage)|off[_\s-]*field[_\s-]*dps|副\s*[cC]|副输出", False, False),
    (r"healing[_\s-]*support|healer|治疗|奶妈", False, False),
    (r"team[_\s-]*support|support|辅助|增益(?!位)", False, False),
    (r"defense|tank|defender|frontline[_\s-]*defender|坦克|前排|承伤|防御", False, False),
    (r"control|控制|控场", False, False),
    (r"(?<![a-z_])dps(?![a-z_])", False, True),
)

_NON_ROLE_COMBAT_PATTERNS = (
    (r"高?爆发(?:型|输出)?|burst", "burst"),
    (r"持续输出|持续伤害|站场|sustain", "sustain"),
    (r"hybrid|混合定位|混合型", "hybrid"),
    (r"buffer|增益位", "buffer"),
    (r"enabler|反应位", "enabler"),
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

_GENDER_UNSPECIFIED_PATTERNS = (
    r"(?:角色|人物|主角)?(?:的)?性别\s*(?:(?:必须|应当|应该|要)\s*)?(?:保持|维持)?\s*(?:未指定|未定|未知|不明|不确定|不明确)",
    r"(?:性别|gender)\s*(?:must\s+remain|should\s+remain|remains?|is|must\s+be|should\s+be)?\s*(?:unspecified|undetermined|unknown|not\s+specified|unassigned)",
    r"(?:leave|keep|maintain)\s+(?:the\s+)?(?:character['’]s\s+)?gender\s+(?:as\s+)?(?:unspecified|undetermined|unknown)",
    r"character\s+of\s+(?:unspecified|undetermined|unknown)\s+gender",
)

_GENDER_NEGATION_PATTERNS = (
    re.compile(
        r"(?:不要|禁止|不得|避免|不能|不可|不应|不可以)\s*(?:(?:把|将)\s*)?"
        r"(?:(?:角色|人物|主角)(?:的)?(?:性别)?\s*)?(?:(?:设定|塑造|设计)\s*)?"
        r"(?:为|成|是)?\s*(?P<value>女性|男性)(?:角色|人物)?"
    ),
    re.compile(
        r"(?:角色|人物|主角)(?:的)?(?:性别)?\s*(?:不是|并非|不能|不得|不应|不可)\s*"
        r"(?:设定为|为|是)?\s*(?P<value>女性|男性)"
    ),
    re.compile(
        r"(?:do\s+not|don't|must\s+not|should\s+not|avoid|never)\s+"
        r"(?:(?:make\s+)?(?:the\s+)?character\s+(?:a\s+)?)?"
        r"(?P<value>female|male|woman|man)(?:\s+(?:playable\s+)?character)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcharacter(?:['’]s)?\s+gender\s+(?:must\s+not\s+be|should\s+not\s+be|"
        r"is\s+not|mustn't\s+be|shouldn't\s+be)\s*(?P<value>female|male|woman|man)\b",
        re.IGNORECASE,
    ),
)

_GENDER_POSITIVE_PATTERNS = (
    re.compile(r"(?P<value>女性|男性)(?:可抽|可玩|游戏)?(?:角色|人物|主角)"),
    re.compile(
        r"(?:角色|人物|主角)(?:的)?性别\s*(?:(?:必须|应当|应该|要)\s*)?"
        r"(?:设定为|为|是|[:：])\s*(?P<value>女性|男性)"
    ),
    re.compile(r"性别\s*(?:(?:必须|应当|应该|要)\s*)?(?:设定为|为|是|[:：])\s*(?P<value>女性|男性)"),
    re.compile(
        r"(?:角色|人物|主角)(?:的)?\s*(?:必须|应当|应该|要)\s*"
        r"(?:设定为|是|为)?\s*(?P<value>女性|男性)"
    ),
    re.compile(
        r"\b(?:(?:the|this|that)\s+)?(?:character|protagonist|hero|unit)\s+"
        r"(?:must|should)\s+be\s+(?:a\s+)?(?P<value>female|male|woman|man)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>female|male)\s+(?:(?:playable|game)\s+)?"
        r"(?:character|protagonist|hero|unit)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<value>female|male)(?:\s+[a-z][a-z-]*){1,3}\s+"
        r"(?:character|protagonist|hero|unit)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>woman|man)\s+(?:character|protagonist|hero)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:a|an)\s+(?P<value>woman|man)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:the\s+)?character(?:['’]s)?\s+gender\s+"
        r"(?:must\s+be|should\s+be|is|=|:|set\s+to)\s*"
        r"(?P<value>[A-Za-z][A-Za-z-]{0,23})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgender\s*(?:must\s+be|should\s+be|is|=|:|set\s+to)\s*"
        r"(?P<value>[A-Za-z][A-Za-z-]{0,23})\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<value>非二元(?:性别)?|性别流动|无性别)(?:的)?(?:角色|人物|主角)"),
    re.compile(
        r"(?P<value>non[- ]?binary|agender|gender[- ]?fluid|intersex)\s+"
        r"(?:character|protagonist|hero)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:而是|而为|but\s+(?:rather\s+)?(?:is\s+)?)\s*"
        r"(?P<value>女性|男性|female|male|woman|man)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?m)^\s*[-*•]\s*(?P<value>女性|男性|female|male)\s*$", re.IGNORECASE),
)

_GENDER_ALIASES = {
    "女": "女性",
    "女性": "女性",
    "女人": "女性",
    "女生": "女性",
    "female": "女性",
    "woman": "女性",
    "women": "女性",
    "girl": "女性",
    "girls": "女性",
    "男": "男性",
    "男性": "男性",
    "男人": "男性",
    "男生": "男性",
    "male": "男性",
    "man": "男性",
    "men": "男性",
    "boy": "男性",
    "boys": "男性",
}

_APPROXIMATE_AGE_PATTERNS = (
    re.compile(r"(?P<age>\d{1,3})\s*岁\s*(?:左右|上下|附近|前后)"),
    re.compile(
        r"(?:about|around|approximately|roughly)\s*(?P<age>\d{1,3})"
        r"\s*(?:years?\s*old|yo)?",
        re.IGNORECASE,
    ),
)
_EXACT_AGE_PATTERNS = (
    re.compile(r"(?:年龄|年纪)\s*(?:是|为|[:：])?\s*(?P<age>\d{1,3})\s*岁?"),
    re.compile(r"(?P<age>\d{1,3})\s*岁(?!\s*(?:左右|上下|附近|前后))"),
    re.compile(r"age\s*(?:is|=|:)\s*(?P<age>\d{1,3})", re.IGNORECASE),
)


def parse_explicit_age_requirement(text: str) -> ExplicitAgeRequirement | None:
    """Parse one exact or approximate age request without inventing an age."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = unicodedata.normalize("NFKC", text)
    matches: list[tuple[int, int, bool]] = []
    for pattern in _APPROXIMATE_AGE_PATTERNS:
        matches.extend((int(item.group("age")), 2, True) for item in pattern.finditer(normalized))
    for pattern in _EXACT_AGE_PATTERNS:
        matches.extend((int(item.group("age")), 0, False) for item in pattern.finditer(normalized))
    if not matches:
        return None
    requested_ages = {age for age, _tolerance, _approximate in matches}
    if len(requested_ages) != 1:
        raise ValueError("request contains conflicting explicit character ages")
    preferred_age = next(iter(requested_ages))
    approximate = any(item[2] for item in matches)
    tolerance = 2 if approximate else 0
    return ExplicitAgeRequirement(
        preferred_age=preferred_age,
        minimum_age=max(0, preferred_age - tolerance),
        maximum_age=min(150, preferred_age + tolerance),
        approximate=approximate,
    )


def _canonical_gender_value(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value).strip().strip("\"'“”‘’「」『』")
    compact = re.sub(r"[\s_-]+", "", cleaned).casefold()
    return _GENDER_ALIASES.get(compact, cleaned)


def parse_explicit_gender_requirement(text: str) -> ExplicitGenderRequirement | None:
    """Extract only direct gender requirements about the character being designed.

    This parser is intentionally separate from the advisory legacy Intent
    parser. V2 opts into the result at its request-to-context boundary, so
    adding this constraint does not alter Legacy prompt payloads.
    """

    if not isinstance(text, str):
        raise TypeError("gender requirement text must be a string")
    normalized = unicodedata.normalize("NFKC", text).strip()
    if not normalized:
        return None

    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in _GENDER_UNSPECIFIED_PATTERNS):
        has_other_mention = any(
            match
            for pattern in (*_GENDER_NEGATION_PATTERNS, *_GENDER_POSITIVE_PATTERNS)
            for match in pattern.finditer(normalized)
        )
        has_conflicting_requirement = bool(
            re.search(
                r"(?:性别未定|性别未指定|gender\s+(?:remains?\s+)?unspecified)"
                r".{0,32}(?:但|但是|but)\s*(?:必须|应当|应该|must|should)\s*"
                r"(?:是|为|be)?\s*(?:女性|男性|female|male)",
                normalized,
                flags=re.IGNORECASE,
            )
        )
        if has_other_mention or has_conflicting_requirement:
            return None
        return ExplicitGenderRequirement(remain_unspecified=True)

    # Mentions in a negated span must not be reinterpreted by a positive pattern.
    negative_matches = [
        match
        for pattern in _GENDER_NEGATION_PATTERNS
        for match in pattern.finditer(normalized)
    ]
    forbidden = {
        _canonical_gender_value(match.group("value")) for match in negative_matches
    }
    positive: set[str] = set()
    for pattern in _GENDER_POSITIVE_PATTERNS:
        for match in pattern.finditer(normalized):
            if any(
                match.start() < negative.end() and negative.start() < match.end()
                for negative in negative_matches
            ):
                continue
            positive.add(_canonical_gender_value(match.group("value")))

    # A list of alternatives, modal wording, or conflicting statements does not
    # establish one reliable hard value.
    if re.search(
        r"女性\s*(?:或|或者|和)\s*男性|男性\s*(?:或|或者|和)\s*女性|"
        r"\b(?:female\s+or\s+male|male\s+or\s+female|either\s+female\s+or\s+male)\b|"
        r"(?:可能|或许|也许)\s*(?:是|为)?\s*(?:女性|男性)|"
        r"\b(?:may|might|could|possibly)\s+be\s+(?:female|male)\b|"
        r"女性向|偏女性气质|female-coded|gender\s+is\s+open|性别不限|不限性别",
        normalized,
        flags=re.IGNORECASE,
    ):
        return None

    if len(positive) > 1:
        remaining_positive = positive - forbidden
        if len(remaining_positive) != 1:
            return None
        positive = remaining_positive
    if positive & forbidden:
        return None
    if not positive and not forbidden:
        return None

    required_value = next(iter(positive)) if positive else None
    return ExplicitGenderRequirement(
        required_value=required_value,
        forbidden_values=tuple(sorted(forbidden)),
    )


class DeterministicCharacterDesignIntentParser:
    """Parse common design phrases without an LLM or network request."""

    def __init__(self, vocabulary=None, factions: Mapping[str, Mapping[str, Any]] | None = None):
        self.vocabulary = vocabulary or self._default_vocabulary()
        self.factions = factions if factions is not None else self._default_factions()

    @staticmethod
    def _default_vocabulary():
        return load_combat_vocabulary(data_resource("reference_corpus", "combat_vocabulary.yaml"))

    @staticmethod
    @lru_cache(maxsize=1)
    def _default_factions():
        return KnowledgeResolver().factions

    @staticmethod
    def _affiliation_context_has_marker(text: str, start: int, end: int) -> bool:
        context = text[max(0, start - 64):min(len(text), end + 64)]
        return bool(re.search(
            r"属于|隶属于|归属于|所属|成员|加入|belongs\s+to|member\s+of|"
            r"affiliated\s+with|part\s+of|works\s+for",
            context,
            flags=re.IGNORECASE,
        ))

    def _parse_requested_affiliation(self, text: str) -> str | None:
        candidates: list[tuple[int, int, str]] = []
        for faction_id, record in self.factions.items():
            aliases = [record.get("name"), record.get("short_name"), faction_id]
            record_aliases = record.get("aliases", ())
            if isinstance(record_aliases, (list, tuple)):
                aliases.extend(record_aliases)
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    continue
                alias = alias.strip()
                pattern = re.escape(alias)
                if re.fullmatch(r"[A-Za-z0-9_.:-]+", alias):
                    pattern = rf"(?<![A-Za-z0-9_.:-]){pattern}(?![A-Za-z0-9_.:-])"
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    if self._affiliation_context_has_marker(text, match.start(), match.end()):
                        candidates.append((match.start(), -(match.end() - match.start()), faction_id))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _combat_role_mentions(self, text: str) -> list[tuple[int, int, str, bool]]:
        matches: list[tuple[int, int, str, bool]] = []
        for pattern, intrinsic_primary, requires_role_context in _COMBAT_ROLE_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                if requires_role_context and not self._bare_dps_has_role_context(
                    text, match.start(), match.end()
                ):
                    continue
                raw = match.group(0)
                try:
                    role = self.vocabulary.normalize_combat_role(raw).canonical_role
                except ValueError:
                    continue
                matches.append((match.start(), match.end(), role, intrinsic_primary))

        # Specific aliases (for example main_dps) contain generic dps. Keep
        # the longest match at an overlapping span so one mention is not
        # counted twice.
        matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        selected: list[tuple[int, int, str, bool]] = []
        for candidate in matches:
            if any(candidate[0] < item[1] and item[0] < candidate[1] for item in selected):
                continue
            selected.append(candidate)
        return sorted(selected, key=lambda item: item[0])

    @staticmethod
    def _has_explicit_primary_marker(text: str, start: int, intrinsic_primary: bool) -> bool:
        if intrinsic_primary:
            return True
        prefix = text[max(0, start - 16):start]
        return bool(
            re.search(
                r"(?:主定位|主职|主要定位|primary(?:\s+(?:role|position))?|main(?:\s+(?:role|position))?)\s*(?:为|是|is|as|:)?\s*$",
                prefix,
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _bare_dps_has_role_context(text: str, start: int, end: int) -> bool:
        context = text[max(0, start - 12):min(len(text), end + 12)]
        return bool(
            re.search(
                r"角色|定位|character|unit|hero|role|position|输出|damage|main|primary|主",
                context,
                flags=re.IGNORECASE,
            )
        )

    def parse(self, request: str) -> CharacterDesignIntent:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("character design request must be a non-empty string")
        text = request.strip()

        rarity = self._parse_rarity(text)
        element = _first_match(text, _ELEMENT_PATTERNS)
        mentions = self._combat_role_mentions(text)
        roles: list[str] = []
        primary_index: int | None = None
        for start, _end, role, intrinsic_primary in mentions:
            if role not in roles:
                roles.append(role)
            if primary_index is None and self._has_explicit_primary_marker(text, start, intrinsic_primary):
                primary_index = roles.index(role)

        if roles:
            if primary_index is None:
                primary_index = 0
            primary = roles[primary_index]
            ordered_roles = [primary, *(role for role in roles if role != primary)]
            profile = CombatRoleProfile(primary_role=ordered_roles[0], secondary_roles=tuple(ordered_roles[1:]))
        else:
            profile = CombatRoleProfile()
        role_type = _first_match(text, _ROLE_TYPE_PATTERNS) or "character"
        target_audience = _first_match(text, _TARGET_PATTERNS) or "general"
        requested_affiliation_id = self._parse_requested_affiliation(text)

        personality: list[str] = []
        for pattern, keyword in _PERSONALITY_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                _append_once(personality, keyword)

        design_goals: list[str] = []
        if element is not None:
            _append_once(design_goals, element)
            _append_once(design_goals, f"element:{element}")
        for pattern, semantic in _NON_ROLE_COMBAT_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                _append_once(design_goals, semantic)
        if re.search(r"高辨识度|有辨识度|distinctive|recognizable", text, flags=re.IGNORECASE):
            _append_once(design_goals, "distinctive")
        if re.search(r"易上手|容易上手|beginner[- ]?friendly", text, flags=re.IGNORECASE):
            _append_once(design_goals, "beginner_friendly")

        forbidden = self._parse_forbidden_patterns(text)
        age_requirement = parse_explicit_age_requirement(text)
        return CharacterDesignIntent(
            role_type=role_type,
            rarity=rarity,
            target_audience=target_audience,
            personality_keywords=tuple(personality),
            design_goals=tuple(design_goals),
            forbidden_patterns=forbidden,
            element=element,
            raw_request=text,
            age_requirement=age_requirement,
            combat_role_profile=profile,
            requested_affiliation_id=requested_affiliation_id,
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


def parse_character_design_intent(request: str, factions: Mapping[str, Mapping[str, Any]] | None = None) -> CharacterDesignIntent:
    """Convenience function for the default deterministic parser."""

    return DeterministicCharacterDesignIntentParser(factions=factions).parse(request)


# Short aliases keep the first public API easy to discover while retaining a
# descriptive implementation name for future parser strategies.
CharacterDesignIntentParser = DeterministicCharacterDesignIntentParser
parse_intent = parse_character_design_intent
