"""Bounded naming proposal, ownership, hard validation, and quality observations."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any


class NamingDesignError(ValueError):
    """Raised when a Planner naming proposal cannot be used safely."""


class CharacterNamingOwner(str, Enum):
    PLANNER = "PLANNER"
    USER_SPECIFIED = "USER_SPECIFIED"


class CharacterNameKind(str, Enum):
    PERSONAL_NAME = "PERSONAL_NAME"
    ALIAS = "ALIAS"
    CODENAME = "CODENAME"
    HONORIFIC_TITLE = "HONORIFIC_TITLE"
    OCCUPATION_DESCRIPTION = "OCCUPATION_DESCRIPTION"
    PLACEHOLDER = "PLACEHOLDER"


@dataclass(frozen=True)
class NamingCandidateV1:
    """One proposal whose name is the intended player-facing display form."""

    candidate_id: str
    name: str
    identity_kind: CharacterNameKind
    identity_rationale: str
    naming_style: str
    cultural_inspiration: str
    phonetic_rationale: str
    character_alignment: str
    tradeoffs: str

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            if field_name == "identity_kind":
                continue
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise NamingDesignError(f"candidate {field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        try:
            object.__setattr__(self, "identity_kind", CharacterNameKind(self.identity_kind))
        except (TypeError, ValueError) as error:
            raise NamingDesignError("candidate identity_kind is unsupported") from error

    def to_dict(self) -> dict[str, str]:
        return {
            field_name: (
                getattr(self, field_name).value
                if isinstance(getattr(self, field_name), Enum)
                else getattr(self, field_name)
            )
            for field_name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class NamingCandidateRejectionV1:
    candidate_id: str
    name: str
    reason: str

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise NamingDesignError(f"rejected candidate {field_name} must be non-empty")
            object.__setattr__(self, field_name, value.strip())

    def to_dict(self) -> dict[str, str]:
        return {field_name: getattr(self, field_name) for field_name in self.__dataclass_fields__}


@dataclass(frozen=True)
class NamingQualityObservationV1:
    dimension: str
    status: str
    observation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "observation": self.observation,
        }


@dataclass(frozen=True)
class CharacterNamingDesignV1:
    """Selected display-name authority plus a small audit trail; never a CharacterDraft."""

    candidates: tuple[NamingCandidateV1, ...]
    selected_name: str
    selected_candidate_id: str
    owner: CharacterNamingOwner
    selection_reasons: tuple[str, ...]
    rejected_candidates: tuple[NamingCandidateRejectionV1, ...]
    hard_validation: str
    quality_observations: tuple[NamingQualityObservationV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "rejected_candidates", tuple(self.rejected_candidates))
        object.__setattr__(self, "quality_observations", tuple(self.quality_observations))
        object.__setattr__(self, "owner", CharacterNamingOwner(self.owner))
        if not 3 <= len(self.candidates) <= 5:
            raise NamingDesignError("naming design must retain three to five valid candidates")
        if not self.selected_name.strip() or not self.selected_candidate_id.strip():
            raise NamingDesignError("selected name and candidate identity must be non-empty")
        if self.hard_validation != "PASS":
            raise NamingDesignError("a frozen naming design must pass hard validation")
        object.__setattr__(self, "selection_reasons", _clean_strings(self.selection_reasons))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "selected_name": self.selected_name,
            "selected_candidate_id": self.selected_candidate_id,
            "owner": self.owner.value,
            "selection_reasons": list(self.selection_reasons),
            "rejected_candidates": [item.to_dict() for item in self.rejected_candidates],
            "hard_validation": self.hard_validation,
            "quality_observations": [item.to_dict() for item in self.quality_observations],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CharacterNamingDesignV1":
        allowed = {
            "candidates",
            "selected_name",
            "selected_candidate_id",
            "owner",
            "selection_reasons",
            "rejected_candidates",
            "hard_validation",
            "quality_observations",
        }
        unknown = set(value) - allowed
        if unknown:
            raise NamingDesignError(f"naming design has unknown fields: {sorted(unknown)}")
        candidates = _mapping_sequence(value.get("candidates"), "candidates")
        rejected = _mapping_sequence(value.get("rejected_candidates", ()), "rejected_candidates")
        observations = _mapping_sequence(value.get("quality_observations", ()), "quality_observations")
        return cls(
            candidates=tuple(NamingCandidateV1(**_exact_mapping(item, NamingCandidateV1.__dataclass_fields__)) for item in candidates),
            selected_name=_required_text(value.get("selected_name"), "selected_name"),
            selected_candidate_id=_required_text(value.get("selected_candidate_id"), "selected_candidate_id"),
            owner=CharacterNamingOwner(value.get("owner")),
            selection_reasons=_clean_strings(value.get("selection_reasons")),
            rejected_candidates=tuple(
                NamingCandidateRejectionV1(**_exact_mapping(item, NamingCandidateRejectionV1.__dataclass_fields__))
                for item in rejected
            ),
            hard_validation=_required_text(value.get("hard_validation"), "hard_validation"),
            quality_observations=tuple(
                NamingQualityObservationV1(**_exact_mapping(item, NamingQualityObservationV1.__dataclass_fields__))
                for item in observations
            ),
        )


_PLACEHOLDERS = frozenset(
    {
        "未命名",
        "未命名角色",
        "待定",
        "待命名",
        "角色a",
        "角色1",
        "npc001",
        "npc1",
        "unnamed",
        "unnamedcharacter",
        "character",
        "charactera",
    }
)
_OCCUPATION_TITLES = (
    "女仆长|调查官|调查员|城市协理人|战斗队长|维修工程师|情报人员|情报官|工程师|指挥官|管理员|"
    "教师|医生|医师|侦探|警官|队长|维修员|学者|战士|骑士|护士|技师|官员|将军|秘书|舰长|船长|店长|调查组长|"
    "head maid|maid captain|maid|investigator|city liaison|combat captain|repair engineer|engineer|commander|"
    "administrator|teacher|doctor|detective|officer|captain|mechanic|scholar|warrior|knight|nurse|secret agent"
)
_OCCUPATION_RE = re.compile(_OCCUPATION_TITLES, re.IGNORECASE)
# Only bind a name after a positive naming relation (or a quoted preservation
# request). The connector boundary prevents `角色名字必须...` from matching the
# shorter `角色名` prefix and consuming the remainder as a user-owned name.
_EXPLICIT_PERSON_NAME_MARKERS = (
    re.compile(
        r"(?:角色|人物|主角)(?:的)?(?:姓名|名字|名称|名(?!字))"
        r"(?=\s*(?:是|为|叫(?:做)?|[:：]|[「『“‘\"']))"
        r"\s*(?:是|为|叫(?:做)?|[:：])?",
    ),
    re.compile(r"(?:角色|人物|主角)?名叫(?:做)?\s*"),
    re.compile(r"(?:角色|人物|主角)\s*叫(?:做)?\s*"),
    re.compile(r"(?:姓名|名字|角色名)\s*(?:是|为|叫(?:做)?|[:：])"),
    re.compile(r"(?:角色|人物|主角)?(?:的)?(?:命名为|取名为)\s*"),
    re.compile(
        r"(?:保留|使用|沿用|采用)\s*(?:角色|人物|主角)?(?:的)?(?:姓名|名字|角色名)"
        r"\s*(?:是|为|[:：])?(?=\s*[「『“‘\"'])"
    ),
    re.compile(r"\b(?:character\s+)?name\s*(?:is|[:=])\s*", re.IGNORECASE),
    re.compile(r"\b(?:named|called)\s+", re.IGNORECASE),
)
_EXPLICIT_ALIAS_MARKERS = (
    re.compile(r"(?:角色|人物|主角)(?:的)?(?:代号|代称|别名|呼号)\s*(?:是|为|叫|[:：])"),
    re.compile(r"(?:只)?(?:指定|保留|使用|采用)\s*(?:角色|人物|主角)?(?:的)?(?:代号|代称|别名|呼号)\s*(?=[「『“‘\"'])"),
)
_NAME_QUOTE_PAIRS = {
    "「": "」",
    "『": "』",
    "“": "”",
    "‘": "’",
    "\"": "\"",
    "'": "'",
}
# Unquoted names stop at clear punctuation and common clause starters; a quoted
# value preserves long or unusual forms that contain those characters.
_NAME_TERMINATORS = re.compile(
    r"[，,。；;!?！？、()（）\r\n]|的|作为|并且|同时|但是|而且|以及|"
    r"她|他|其|这位|该角色|\s+(?:is|as|the|a|an|and|with|who|whose|from|for|please)\b",
    re.IGNORECASE,
)
# These are broad naming-form categories, not a list of approved names. Free
# prose after the prefix stays visible for human review; unknown labels remain
# unclassified instead of being guessed into a family.
_NAMING_STYLE_FAMILY_ALIASES = (
    ("中文意象名", ("中文意象名", "中文意象式", "Chinese imagery name")),
    ("自然中文姓名", ("自然中文姓名", "自然中文名", "natural Chinese personal name")),
    ("外语姓名", ("外语姓名", "foreign-language name")),
    ("音译姓名", ("音译姓名", "外语音译姓名", "外语音译式", "transliterated name")),
    ("原创幻想构词", ("原创幻想构词", "原创幻想式", "original fantasy coinage")),
    ("代号式命名", ("代号式命名", "代号式", "codename")),
    ("象征性称号", ("象征性称号", "symbolic title")),
    ("特定文化命名", ("特定文化命名", "culture-specific name")),
)
_STYLE_LABEL_SEPARATORS = " ：:，,-—（(["


def naming_design_schema() -> dict[str, Any]:
    """Return the closed Planner wire schema for Naming Design v1."""

    text = {"type": "string", "minLength": 1, "pattern": r"\S"}
    candidate_fields = (
        "candidate_id",
        "name",
        "identity_kind",
        "identity_rationale",
        "naming_style",
        "cultural_inspiration",
        "phonetic_rationale",
        "character_alignment",
        "tradeoffs",
    )
    rejection_fields = ("candidate_id", "name", "reason")

    def object_schema(fields: Sequence[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                field_name: (
                    {
                        "type": "string",
                        "enum": [kind.value for kind in CharacterNameKind],
                    }
                    if field_name == "identity_kind"
                    else text
                )
                for field_name in fields
            },
            "required": sorted(fields),
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": object_schema(candidate_fields),
            },
            "selected_candidate_id": text,
            "selection_reasons": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": text,
            },
            "rejected_candidates": {
                "type": "array",
                "maxItems": 5,
                "items": object_schema(rejection_fields),
            },
        },
        "required": sorted(
            ["candidates", "selected_candidate_id", "selection_reasons", "rejected_candidates"]
        ),
    }


def validate_character_naming_design(
    value: object,
    *,
    user_texts: Sequence[str],
    canon_names: Sequence[str],
    reference_names: Sequence[str],
    occupation_context: Sequence[str] = (),
) -> CharacterNamingDesignV1:
    """Validate one Planner proposal against user, Canon, and reference ownership."""

    if not isinstance(value, Mapping):
        raise NamingDesignError("character_naming must be an object")
    expected = {"candidates", "selected_candidate_id", "selection_reasons", "rejected_candidates"}
    if set(value) != expected:
        raise NamingDesignError("character_naming has missing or unsupported fields")
    raw_candidates = _mapping_sequence(value["candidates"], "candidates")
    if not 3 <= len(raw_candidates) <= 5:
        raise NamingDesignError("Planner must propose three to five naming candidates")
    raw_rejected = _mapping_sequence(value["rejected_candidates"], "rejected_candidates")
    if len(raw_rejected) > 5:
        raise NamingDesignError("Planner rejected-candidate list exceeds its bound")
    reasons = _clean_strings(value["selection_reasons"])
    if not 1 <= len(reasons) <= 4:
        raise NamingDesignError("selection_reasons must contain one to four concise reasons")

    candidate_values = tuple(
        NamingCandidateV1(**_exact_mapping(item, NamingCandidateV1.__dataclass_fields__))
        for item in raw_candidates
    )
    rejected_values = tuple(
        NamingCandidateRejectionV1(**_exact_mapping(item, NamingCandidateRejectionV1.__dataclass_fields__))
        for item in raw_rejected
    )
    ids = [item.candidate_id for item in candidate_values]
    if len(ids) != len(set(ids)):
        raise NamingDesignError("candidate IDs must be unique")
    selected_id = _required_text(value["selected_candidate_id"], "selected_candidate_id")
    no_valid_candidate_selected = selected_id == "NO_VALID_CANDIDATE"
    if not no_valid_candidate_selected and selected_id not in ids:
        raise NamingDesignError("selected_candidate_id must identify one proposed candidate")

    protected = {_name_key(name) for name in canon_names if isinstance(name, str) and name.strip()}
    references = {_name_key(name) for name in reference_names if isinstance(name, str) and name.strip()}
    occupation_text = " ".join(
        item for item in (*user_texts, *occupation_context) if isinstance(item, str)
    )
    explicit_names = extract_explicit_character_names(user_texts)
    if len({_name_key(name) for name in explicit_names}) > 1:
        raise NamingDesignError("user request contains conflicting explicit character names")
    explicit_name = explicit_names[0] if explicit_names else None
    if explicit_name is not None:
        user_reason = _hard_name_invalid_reason(
            explicit_name,
            identity_kind=None,
            occupation_text=occupation_text,
            canon_keys=protected,
            reference_keys=references,
        )
        if user_reason:
            raise NamingDesignError("explicit user name conflicts with a hard naming rule: " + user_reason)
    valid: list[NamingCandidateV1] = []
    rejected = list(rejected_values)
    selected_reason: str | None = None
    for candidate in candidate_values:
        reason = _hard_name_invalid_reason(
            candidate.name,
            identity_kind=candidate.identity_kind,
            occupation_text=occupation_text,
            canon_keys=protected,
            reference_keys=references,
        )
        if reason:
            rejected.append(NamingCandidateRejectionV1(candidate.candidate_id, candidate.name, reason))
            if candidate.candidate_id == selected_id:
                selected_reason = reason
        else:
            valid.append(candidate)
    if len(valid) < 3:
        raise NamingDesignError("fewer than three valid and distinct naming candidates remain")
    _validate_meaningful_diversity(valid)

    if no_valid_candidate_selected:
        raise NamingDesignError(
            "Planner reported no valid name although three candidates passed hard validation"
        )

    if explicit_name is not None:
        selected_name = explicit_name
        owner = CharacterNamingOwner.USER_SPECIFIED
        selected_id = "USER_SPECIFIED"
        reasons = ("保留用户明确指定的名字。",)
        rejected.append(
            NamingCandidateRejectionV1(
                candidate_id=value["selected_candidate_id"],
                name=next(item.name for item in candidate_values if item.candidate_id == value["selected_candidate_id"]),
                reason="用户已明确指定角色名，Planner 候选不拥有最终命名权。",
            )
        )
    else:
        selected_candidate = next(item for item in candidate_values if item.candidate_id == selected_id)
        if selected_reason is not None:
            raise NamingDesignError("selected Planner name fails hard validation: " + selected_reason)
        selected_name = selected_candidate.name
        owner = CharacterNamingOwner.PLANNER

    selected_valid_candidate = next((item for item in valid if item.name == selected_name), None)
    if owner is CharacterNamingOwner.PLANNER and selected_valid_candidate is None:
        raise NamingDesignError("selected name is absent from the valid candidate set")
    observations = _quality_observations(valid, selected_valid_candidate)
    return CharacterNamingDesignV1(
        candidates=tuple(valid),
        selected_name=selected_name,
        selected_candidate_id=selected_id,
        owner=owner,
        selection_reasons=reasons,
        rejected_candidates=tuple(rejected),
        hard_validation="PASS",
        quality_observations=observations,
    )


def is_occupation_as_name(name: str, occupation: str) -> bool:
    """Detect when a candidate repeats or embeds the current role's job label.

    Matching is scoped to occupation terms present in the supplied role context;
    it is a low-cost role-description check, not a general name-quality test.
    """

    name_key = _name_key(name)
    occupation_key = _name_key(occupation)
    if not name_key or not occupation_key:
        return False
    if name_key == occupation_key:
        return True
    for match in _OCCUPATION_RE.finditer(occupation):
        role_term = match.group(0)
        role_key = _name_key(role_term)
        if not role_key:
            continue
        if role_term.isascii() and role_term.isalpha():
            pattern = rf"(?<![a-z0-9]){re.escape(role_term.casefold())}$"
            if re.search(pattern, name.casefold()):
                return True
        elif name_key.endswith(role_key):
            return True
    return False


def _hard_name_invalid_reason(
    name: str,
    *,
    identity_kind: CharacterNameKind | None,
    occupation_text: str,
    canon_keys: set[str],
    reference_keys: set[str],
) -> str | None:
    key = _name_key(name)
    if not key or not name.strip():
        return "名字为空。"
    if identity_kind is CharacterNameKind.PLACEHOLDER or key in _PLACEHOLDERS or re.fullmatch(
        r"(?:npc|character|角色)[-_# ]*\w+", key
    ):
        return "占位符不能作为正式角色名。"
    if identity_kind is CharacterNameKind.OCCUPATION_DESCRIPTION:
        return "候选被归类为职业或岗位描述，不能作为独立人物名。"
    if is_occupation_as_name(name, occupation_text):
        return "名字仍包含当前职业或岗位称谓；地点、等级、期限或事件修饰不会把岗位描述变成人名。"
    if key in canon_keys:
        return "名字与受保护的现有 Canon 角色标识冲突。"
    if key in reference_keys:
        return "名字与 Reference Corpus 角色重名，不能直接复制。"
    return None


def _validate_meaningful_diversity(candidates: Sequence[NamingCandidateV1]) -> None:
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            left_key = _name_key(left.name)
            right_key = _name_key(right.name)
            if _one_character_or_affix_variant(left_key, right_key):
                raise NamingDesignError("候选名字存在只替换一个字符、前缀或尾音的伪多样性")


def _repeated_candidate_form(
    candidates: Sequence[NamingCandidateV1], *, declared_family_count: int
) -> str | None:
    """Report a strong repeated name shape for human review, never hard-reject it."""

    visible_forms: Counter[tuple[str, int]] = Counter()
    for candidate in candidates:
        form = _visible_name_form(candidate.name)
        if form is not None:
            visible_forms[form] += 1
    if visible_forms:
        form, count = visible_forms.most_common(1)[0]
        # This pool is bounded to three through five entries: require a uniform
        # pattern in small pools or all-but-one repetition in larger pools.
        required_count = len(candidates) if len(candidates) <= 3 else len(candidates) - 1
        if count >= required_count:
            script, letter_count = form
            return (
                f"{count}/{len(candidates)} 个名字都采用{script}书写、"
                f"{letter_count} 个字母/文字的形式"
            )

    if declared_family_count > 1:
        form_descriptions: Counter[str] = Counter()
        for candidate in candidates:
            description = _naming_style_form_description(candidate.naming_style)
            if description is not None:
                form_descriptions[description] += 1
        if form_descriptions:
            description, count = form_descriptions.most_common(1)[0]
            if count == len(candidates):
                return f"不同家族标签重复使用同一形式说明“{description}”"
    return None


def _visible_name_form(name: str) -> tuple[str, int] | None:
    """Describe the written script and length without inferring language or origin."""

    letters = tuple(character for character in name if character.isalpha())
    if not letters:
        return None
    unicode_names = tuple(unicodedata.name(character, "") for character in letters)
    if all(
        "CJK UNIFIED IDEOGRAPH" in unicode_name
        or "CJK COMPATIBILITY IDEOGRAPH" in unicode_name
        for unicode_name in unicode_names
    ):
        script = "汉字"
    elif all("LATIN" in unicode_name for unicode_name in unicode_names):
        script = "拉丁字母"
    else:
        script = "混合或其他文字"
    return script, len(letters)


def _naming_style_form_description(style: str) -> str | None:
    """Return only the text after a recognized family label and separator."""

    value = style.strip()
    folded_value = value.casefold()
    for _, aliases in _NAMING_STYLE_FAMILY_ALIASES:
        for alias in aliases:
            folded_alias = alias.casefold()
            if (
                folded_value.startswith(folded_alias)
                and len(value) > len(alias)
                and value[len(alias)] in _STYLE_LABEL_SEPARATORS
            ):
                description = value[len(alias) + 1 :].strip()
                normalized = _name_key(description)
                return normalized or None
    return None


def _one_character_or_affix_variant(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) == len(right) and len(left) >= 2:
        if left[:-1] == right[:-1] or left[1:] == right[1:]:
            return True
    if min(len(left), len(right)) >= 3 and SequenceMatcher(None, left, right).ratio() >= 0.82:
        return _levenshtein_at_most_one(left, right)
    return False


def _levenshtein_at_most_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    left_index = right_index = differences = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index] == right[right_index]:
            left_index += 1
            right_index += 1
            continue
        differences += 1
        if differences > 1:
            return False
        if len(left) == len(right):
            left_index += 1
        right_index += 1
    return True


def _quality_observations(
    candidates: Sequence[NamingCandidateV1], selected: NamingCandidateV1 | None
) -> tuple[NamingQualityObservationV1, ...]:
    near_pairs = [
        f"{left.name} / {right.name}"
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
        if SequenceMatcher(None, _name_key(left.name), _name_key(right.name)).ratio() >= 0.65
    ]
    distinctiveness = (
        NamingQualityObservationV1(
            "distinctiveness", "REVIEW", "拼写相近的候选需要人工比较：" + "；".join(near_pairs)
        )
        if near_pairs
        else NamingQualityObservationV1(
            "distinctiveness", "CLEAR", "未发现只替换单个字符、前缀或尾音的候选组合。"
        )
    )
    family_labels = tuple(_naming_style_family(item.naming_style) for item in candidates)
    declared_families = tuple(dict.fromkeys(label for label in family_labels if label is not None))
    unclassified_count = sum(label is None for label in family_labels)
    repeated_form = _repeated_candidate_form(
        candidates, declared_family_count=len(declared_families)
    )
    if unclassified_count:
        family_status = "REVIEW_REQUIRED"
        family_summary = (
            f"有 {unclassified_count} 个候选未使用可识别的风格家族标签；"
            "请人工比较名称形式和文化依据。"
        )
        if repeated_form is not None:
            family_summary += " 另有明显重复形式：" + repeated_form + "。"
    elif repeated_form is not None:
        family_status = "REVIEW_REQUIRED"
        family_summary = (
            "候选呈现明显重复形式："
            + repeated_form
            + "。风格标签或灵感理由本身不能证明候选真正多样，需人工判断是否值得保留。"
        )
    elif len(declared_families) == 1:
        family_status = "SINGLE_FAMILY_DECLARED"
        family_summary = f"候选均声明为“{declared_families[0]}”；如范围受设定限制，应核对其具体依据。"
    else:
        family_status = "MULTIPLE_FAMILIES_DECLARED"
        family_summary = "候选声明了不同风格家族：“" + "、".join(declared_families) + "”。"
    family_observation = NamingQualityObservationV1(
        "style_family_diversity",
        family_status,
        "Planner 的 naming_style 家族声明："
        + family_summary
        + "家族标签不能证明名称形式确有差异，也不替代文化适配审阅。",
    )
    return (
        NamingQualityObservationV1(
            "character_alignment",
            "RATIONALE_PROVIDED" if selected is not None and selected.character_alignment else "NOT_ASSESSED",
            "选定候选提供了与角色设定的关联理由；这是可审阅理由，不是客观评分。"
            if selected is not None
            else "用户指定了最终名字；候选契合度仍可人工审阅。",
        ),
        NamingQualityObservationV1(
            "person_identity",
            "REVIEW_REQUIRED",
            "候选类别与人物身份依据来自 Planner 的结构化说明；确定性规则不独立判定称号或代号是否真正属于该人物，需结合角色设定审阅。",
        ),
        distinctiveness,
        family_observation,
        NamingQualityObservationV1(
            "phonetic_quality",
            "REVIEW_REQUIRED",
            "Planner 提供的音韵理由不是质量证明；实际口语自然度、角色辨识度和明显真人谐音仍需人工朗读与审阅，系统也不做穷尽式撞名验证。",
        ),
        NamingQualityObservationV1(
            "worldbuilding_fit",
            "RATIONALE_PROVIDED",
            "文化灵感以 Planner 的简短说明呈现，系统不验证或补造姓名出处。",
        ),
    )


def extract_explicit_character_names(texts: Sequence[str]) -> tuple[str, ...]:
    """Extract only names tied to an explicit naming act and a bounded value.

    Plain naming requirements do not create USER_SPECIFIED ownership. A quoted
    alias or codename is used only when no explicit personal name is present,
    so a supplied name and an honorific can coexist without becoming a conflict.
    """

    personal_names = _extract_names_after_markers(texts, _EXPLICIT_PERSON_NAME_MARKERS)
    if personal_names:
        return personal_names
    return _extract_names_after_markers(texts, _EXPLICIT_ALIAS_MARKERS)


def _extract_names_after_markers(
    texts: Sequence[str], markers: Sequence[re.Pattern[str]]
) -> tuple[str, ...]:
    found: list[str] = []
    for source in texts:
        if not isinstance(source, str):
            continue
        for marker in markers:
            for match in marker.finditer(source):
                if _name_marker_is_negated_or_hypothetical(source, match.start()):
                    continue
                value = _read_bounded_name_value(source, match.end())
                if value and value not in found:
                    found.append(value)
    return tuple(found)


def _name_marker_is_negated_or_hypothetical(source: str, marker_start: int) -> bool:
    """Do not promote a quoted example or a prohibited name into user ownership."""

    separators = ",，。；;!?！？\n"
    clause_start = max(source.rfind(separator, 0, marker_start) for separator in separators)
    preceding_text = source[clause_start + 1 : marker_start]
    # Limit cues to a nearby portion of this clause so an earlier unrelated
    # prohibition or example cannot suppress a later positive name assignment.
    return re.search(
        r"(?:不要|别|禁止|避免|不应|不能|不得|不许|勿|切勿|例如|比如|"
        r"do\s+not|don't|never|avoid|for\s+example|e\.g\.)"
        r"[^，。；;!?！？\n]{0,24}$",
        preceding_text,
        re.IGNORECASE,
    ) is not None


def _read_bounded_name_value(source: str, offset: int) -> str | None:
    """Read one quoted value or an unquoted token ending at a trusted boundary."""

    start = offset
    while start < len(source) and source[start] in " \t\r\n:：":
        start += 1
    if start == len(source):
        return None
    opening = source[start]
    closing = _NAME_QUOTE_PAIRS.get(opening)
    if closing is not None:
        end = source.find(closing, start + 1)
        if end < 0:
            return None
        value = source[start + 1 : end].strip()
        return value or None

    rest = source[start:]
    boundary = _NAME_TERMINATORS.search(rest)
    value = rest[: boundary.start()] if boundary else rest
    value = value.strip(" \t\r\n:：,，。；;.!?！？、()（）")
    return value or None


def _naming_style_family(style: str) -> str | None:
    """Map Planner's broad style label, not its free-form explanation, to a family."""

    value = style.strip().casefold()
    for family, aliases in _NAMING_STYLE_FAMILY_ALIASES:
        for alias in aliases:
            normalized_alias = alias.casefold()
            if value == normalized_alias or (
                value.startswith(normalized_alias)
                and len(value) > len(normalized_alias)
                and value[len(normalized_alias)] in _STYLE_LABEL_SEPARATORS
            ):
                return family
    custom_prefixes = ("其他：", "其他:", "other:")
    for prefix in custom_prefixes:
        if value.startswith(prefix):
            custom_family = re.split(r"[：:—–|｜（(]", value[len(prefix) :], maxsplit=1)[0]
            if custom_family.strip():
                return "其他:" + custom_family.strip()
    return None


def _name_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NamingDesignError(f"{field_name} must be a non-empty string")
    return value.strip()


def _clean_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise NamingDesignError("expected a non-empty array of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise NamingDesignError("string arrays cannot contain empty values")
        cleaned = item.strip()
        if cleaned not in result:
            result.append(cleaned)
    if not result:
        raise NamingDesignError("expected at least one concise string")
    return tuple(result)


def _mapping_sequence(value: object, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise NamingDesignError(f"{field_name} must be an array")
    result = tuple(value)
    if not all(isinstance(item, Mapping) for item in result):
        raise NamingDesignError(f"{field_name} entries must be objects")
    return result


def _exact_mapping(value: Mapping[str, Any], fields: Mapping[str, object]) -> dict[str, Any]:
    expected = set(fields)
    if set(value) != expected:
        raise NamingDesignError("candidate fields do not match the Naming Design contract")
    return dict(value)


__all__ = [
    "CharacterNameKind",
    "CharacterNamingDesignV1",
    "CharacterNamingOwner",
    "NamingCandidateRejectionV1",
    "NamingCandidateV1",
    "NamingDesignError",
    "NamingQualityObservationV1",
    "extract_explicit_character_names",
    "is_occupation_as_name",
    "naming_design_schema",
    "validate_character_naming_design",
]
