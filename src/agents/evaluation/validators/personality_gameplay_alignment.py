"""Deterministic high-confidence checks for personality/gameplay conflicts."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..context import EvaluationContext
from ..models import EvaluationFinding

_PERSONALITY_SIGNALS = {
    "risk avoidance": (
        r"胆小",
        r"胆怯",
        r"谨慎",
        r"极度回避危险",
        r"回避危险",
        r"害怕危险",
        r"风险厌恶",
        r"risk[- ]averse",
        r"avoid(?:s|ing)? danger",
        r"cautious",
        r"fearful",
    ),
    "confrontation avoidance": (
        r"不愿主动与敌人发生正面冲突",
        r"避免正面冲突",
        r"回避冲突",
        r"不喜欢正面冲突",
        r"不愿正面迎战",
        r"avoid(?:s|ing)? direct confrontation",
        r"shy(?:s|ing)? away from confrontation",
    ),
    "attention avoidance": (
        r"不喜欢成为注意焦点",
        r"不想成为注意焦点",
        r"不愿成为注意焦点",
        r"不想引人注意",
        r"低调",
        r"avoid(?:s|ing)? attention",
        r"does not seek attention",
    ),
    "low initiative": (
        r"不愿主动",
        r"不主动",
        r"被动",
        r"犹豫",
        r"reluctant to initiate",
        r"low initiative",
    ),
}

_GAMEPLAY_SIGNALS = {
    "risk exposure": (
        r"高风险状态",
        r"高风险",
        r"承受伤害换取",
        r"以生命换取",
        r"risk[- ](?:heavy|high|taking)",
        r"trade(?:s|ing)? health for",
    ),
    "direct confrontation": (
        r"主动与敌人(?:发生)?正面冲突",
        r"主动近战",
        r"贴脸",
        r"正面迎战",
        r"近身作战",
        r"冲锋(?:作战|攻击)?",
        r"direct confrontation",
        r"close[- ]quarters combat",
    ),
    "aggro attraction": (
        r"主动吸引敌人攻击",
        r"吸引敌人攻击",
        r"拉仇恨",
        r"嘲讽",
        r"强制敌方攻击自己",
        r"成为敌人焦点",
        r"draw(?:s|ing)? enemy aggro",
        r"taunt(?:s|ing)?",
    ),
    "proactive initiation": (
        r"主动开战",
        r"先手攻击",
        r"主动发起战斗",
        r"不断主动攻击",
        r"proactively initiate(?:s)? combat",
        r"initiate(?:s|ing)? combat",
    ),
}

_BRIDGE_SIGNALS = (
    r"为了保护(?:队友|同伴|某人|目标)",
    r"保护(?:队友|同伴|某人|目标)",
    r"(?:队友|同伴|某人|目标)(?:受到威胁|陷入危险|受伤)",
    r"只有在[^。；;\n]{0,40}(?:时|情况下)",
    r"必要时",
    r"被迫",
    r"安全距离",
    r"远程",
    r"预先(?:布置|准备)",
    r"布置陷阱",
    r"迂回",
    r"only when [^.\n]{0,40}(?:danger|threat|necessary)",
    r"(?:protect|save)s? (?:an? )?(?:ally|friend|target)",
    r"safe distance",
    r"ranged",
    r"prepared burst",
)

_STRICT_CONSISTENCY = (
    r"严格一致",
    r"不得矛盾",
    r"不允许[^。；;\n]{0,20}(?:矛盾|冲突)",
    r"一致性约束",
    r"strict consistency",
    r"must be consistent",
)


def _matches(text: str, patterns: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE)
    )


def _source_matches(
    sources: Iterable[tuple[str, str]], patterns: Iterable[str]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (field, pattern)
        for field, text in sources
        for pattern in _matches(text, patterns)
    )


class PersonalityGameplayAlignmentValidator:
    """Reject only explicit, high-confidence personality/gameplay conflicts."""

    validator_id = "personality_gameplay_alignment"
    dimension = "personality_gameplay_alignment"

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None or context.intent is None:
            return ()

        request_sources = (
            ("request.brief", context.request.brief),
            *(
                (f"request.hard_constraints[{index}]", value)
                for index, value in enumerate(context.request.hard_constraints)
            ),
            ("intent.personality_keywords", "、".join(context.intent.personality_keywords)),
        )
        personality_sources = (
            ("personality", "、".join(context.draft.personality)),
            *request_sources,
        )
        gameplay_sources = tuple(
            (field, getattr(context.draft, field))
            for field in ("design_pitch", "ability_concept", "background", "story_hook")
            if getattr(context.draft, field).strip()
        )
        bridge_sources = (*gameplay_sources, *request_sources)
        strict = bool(_source_matches(request_sources, _STRICT_CONSISTENCY))
        findings: list[EvaluationFinding] = []

        for axis, personality_patterns in _PERSONALITY_SIGNALS.items():
            personality_matches = _source_matches(personality_sources, personality_patterns)
            if not personality_matches:
                continue
            gameplay_axis = {
                "risk avoidance": "risk exposure",
                "confrontation avoidance": "direct confrontation",
                "attention avoidance": "aggro attraction",
                "low initiative": "proactive initiation",
            }[axis]
            gameplay_matches = _source_matches(
                gameplay_sources, _GAMEPLAY_SIGNALS[gameplay_axis]
            )
            if not gameplay_matches:
                continue
            if _source_matches(bridge_sources, _BRIDGE_SIGNALS):
                continue

            personality_evidence = ", ".join(pattern for _, pattern in personality_matches)
            gameplay_evidence = ", ".join(pattern for _, pattern in gameplay_matches)
            gameplay_fields = ", ".join(dict.fromkeys(field for field, _ in gameplay_matches))
            strict_note = "严格一致约束进一步确认该冲突不可接受。" if strict else ""
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="PERSONALITY_GAMEPLAY_CONFLICT",
                    severity="ERROR",
                    blocking=True,
                    stage="personality_gameplay_alignment",
                    field_path=f"personality,{gameplay_fields}",
                    message=(
                        f"性格与玩法在{axis}维度存在高置信冲突：性格命中[{personality_evidence}]，"
                        f"玩法字段[{gameplay_fields}]命中[{gameplay_evidence}]。{strict_note}"
                    ),
                )
            )

        return findings


__all__ = ["PersonalityGameplayAlignmentValidator"]
