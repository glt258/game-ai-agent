from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .models import (
    ClaimGroundingStatus,
    ClaimValidation,
    ConversationMessage,
    GroundedResponseSegment,
    GroundingEvidence,
    GroundingEvidenceType,
    GroundingReport,
    NpcCharacterView,
    NpcRuntimeView,
    SegmentKind,
)


SAFE_FALLBACK_TEXT = (
    "我目前能确认的信息不足以支持更具体的结论。"
    "涉及你问到的细节，我不能在没有依据的情况下补充。"
)

ALLOWED_UNCERTAINTY_TEXTS = frozenset(
    {
        SAFE_FALLBACK_TEXT,
        "我目前无法确认事故最终内部定性。",
        "我目前能确认的信息不足以还原完整内部复盘。",
        "对于最终事故结论、具体处置时间线和个人责任认定，我无法依据当前信息确认。",
        "完整内部结论没有可核实来源，我不会猜。",
        "内部最后怎么落笔，我没看到，不能替那份记录补台词。",
        "缺少可核实来源，我不能替内部记录下判断。",
        "我没有这部分可核实的资料。",
        "现有可查资料里没有足够依据，我不能把推测当成事实。",
        "结论：现有公开资料不足以确认这件事。",
        "结论：目前不能确认。",
    }
)

ALLOWED_NON_FACTUAL_TEXTS = frozenset(
    {
        "如果你需要正式结论，最好查看有权限的内部复盘材料。",
        "如果需要，我可以说明目前有依据的部分。",
        "这件事值得继续核实。",
    }
)


class GroundingEvidenceBuilder:
    """Build request-local evidence exclusively from already-safe inputs."""

    def build(
        self,
        character: NpcCharacterView,
        runtime: NpcRuntimeView,
        messages: Sequence[ConversationMessage],
    ) -> tuple[GroundingEvidence, ...]:
        evidence = [
            GroundingEvidence(
                "character:display_name",
                GroundingEvidenceType.CHARACTER_FACT,
                f"我的名字是{character.display_name}。",
            ),
            GroundingEvidence(
                "runtime:story",
                GroundingEvidenceType.RUNTIME_FACT,
                f"当前故事是《{runtime.story_title}》。",
            ),
        ]
        if character.occupation.strip():
            evidence.append(
                GroundingEvidence(
                    "character:occupation",
                    GroundingEvidenceType.CHARACTER_FACT,
                    f"我的职业是{character.occupation}。",
                )
            )
        participation = self._participation_text(runtime)
        if participation is not None:
            evidence.append(
                GroundingEvidence(
                    "runtime:participation",
                    GroundingEvidenceType.RUNTIME_FACT,
                    participation,
                )
            )
        for case_id in runtime.active_case_ids:
            evidence.append(
                GroundingEvidence(
                    f"runtime:case:{case_id}",
                    GroundingEvidenceType.RUNTIME_FACT,
                    f"我当前关联的协调委托是{case_id}。",
                )
            )
        for incident_id in runtime.active_incident_ids:
            evidence.append(
                GroundingEvidence(
                    f"runtime:incident:{incident_id}",
                    GroundingEvidenceType.RUNTIME_FACT,
                    f"我当前关联的现场事件是{incident_id}。",
                )
            )
        evidence.extend(self._tool_evidence(messages))
        return tuple(evidence)

    @staticmethod
    def _participation_text(runtime: NpcRuntimeView) -> str | None:
        if runtime.active_incident_ids:
            return "我参与的是现场处理。"
        if runtime.active_case_ids:
            return "我负责的是这次协调委托。"
        if runtime.participation_role == "stage_worker_and_witness":
            return "我能确认的是自己在现场看到和做过的部分。"
        if runtime.participation_role:
            return f"我在当前故事中的参与身份是{runtime.participation_role}。"
        return None

    @classmethod
    def _tool_evidence(
        cls, messages: Sequence[ConversationMessage]
    ) -> list[GroundingEvidence]:
        evidence: list[GroundingEvidence] = []
        for message in messages:
            if message.role != "tool" or not isinstance(message.content, Mapping):
                continue
            if message.content.get("status") != "ok":
                continue
            result = message.content.get("result")
            results = message.content.get("results")
            candidates: list[Mapping[str, Any]] = []
            if isinstance(result, Mapping):
                candidates.append(result)
            if isinstance(results, list):
                candidates.extend(item for item in results if isinstance(item, Mapping))
            for candidate in candidates:
                lore_id = candidate.get("lore_id")
                statement = candidate.get("statement")
                if not isinstance(lore_id, str) or not isinstance(statement, str):
                    continue
                statement = statement.strip()
                if not statement:
                    continue
                evidence.append(
                    GroundingEvidence(
                        f"lore:{lore_id}:statement",
                        GroundingEvidenceType.TOOL_LORE,
                        statement,
                        lore_id,
                    )
                )
        return evidence


class GroundingValidator:
    """Conservative deterministic validator over permission-safe evidence."""

    _NEGATION_PREFIXES = (
        "并非",
        "并未",
        "不是",
        "没有",
        "从未",
        "无法",
        "不能",
        "不会",
        "不可",
        "尚未",
        "未能",
        "不",
        "没",
        "未",
        "无",
    )

    def validate(
        self,
        segments: Sequence[GroundedResponseSegment],
        evidence: Sequence[GroundingEvidence],
    ) -> GroundingReport:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        validations: list[ClaimValidation] = []
        used_lore_ids: list[str] = []
        seen_segment_ids: set[str] = set()
        for segment in segments:
            if not segment.segment_id or segment.segment_id in seen_segment_ids:
                validations.append(
                    ClaimValidation(
                        segment.segment_id or "<missing>",
                        ClaimGroundingStatus.UNSUPPORTED,
                        reason="segment identifier is missing or duplicated",
                    )
                )
                continue
            seen_segment_ids.add(segment.segment_id)
            validation = self._validate_segment(segment, evidence_by_id)
            validations.append(validation)
            if validation.status == ClaimGroundingStatus.SUPPORTED:
                for evidence_id in validation.valid_evidence_ids:
                    item = evidence_by_id[evidence_id]
                    if (
                        item.source_type == GroundingEvidenceType.TOOL_LORE
                        and item.source_lore_id is not None
                        and item.source_lore_id not in used_lore_ids
                    ):
                        used_lore_ids.append(item.source_lore_id)
        passed = bool(validations) and all(
            item.status != ClaimGroundingStatus.UNSUPPORTED for item in validations
        )
        return GroundingReport(tuple(validations), passed, tuple(used_lore_ids))

    def _validate_segment(
        self,
        segment: GroundedResponseSegment,
        evidence_by_id: Mapping[str, GroundingEvidence],
    ) -> ClaimValidation:
        if not isinstance(segment.text, str) or not segment.text.strip():
            return self._unsupported(segment, reason="segment text is empty")
        if segment.kind == SegmentKind.SUPPORTED_CLAIM:
            valid = tuple(
                evidence_id
                for evidence_id in segment.evidence_ids
                if evidence_id in evidence_by_id
            )
            invalid = tuple(
                evidence_id
                for evidence_id in segment.evidence_ids
                if evidence_id not in evidence_by_id
            )
            if not valid or invalid:
                return self._unsupported(
                    segment,
                    valid=valid,
                    invalid=invalid,
                    reason="supporting evidence is unavailable",
                )
            if not any(
                self._extractively_supported(segment.text, evidence_by_id[item].text)
                for item in valid
            ):
                return self._unsupported(
                    segment,
                    valid=valid,
                    reason="available evidence does not contain this asserted fact",
                )
            return ClaimValidation(
                segment.segment_id,
                ClaimGroundingStatus.SUPPORTED,
                valid_evidence_ids=valid,
            )
        if segment.evidence_ids:
            return self._unsupported(
                segment,
                invalid=tuple(segment.evidence_ids),
                reason="this segment kind must not cite evidence",
            )
        if segment.kind == SegmentKind.UNCERTAIN:
            if segment.text.strip() not in ALLOWED_UNCERTAINTY_TEXTS:
                return self._unsupported(
                    segment,
                    reason="uncertainty wording is not an approved abstention",
                )
            return ClaimValidation(
                segment.segment_id, ClaimGroundingStatus.UNCERTAIN
            )
        if segment.kind == SegmentKind.NON_FACTUAL:
            if segment.text.strip() not in ALLOWED_NON_FACTUAL_TEXTS:
                return self._unsupported(
                    segment,
                    reason="non-factual wording is not an approved safe form",
                )
            return ClaimValidation(
                segment.segment_id, ClaimGroundingStatus.NON_FACTUAL
            )
        return self._unsupported(segment, reason="unsupported segment kind")

    @staticmethod
    def _unsupported(
        segment: GroundedResponseSegment,
        *,
        valid: tuple[str, ...] = (),
        invalid: tuple[str, ...] = (),
        reason: str,
    ) -> ClaimValidation:
        return ClaimValidation(
            segment.segment_id,
            ClaimGroundingStatus.UNSUPPORTED,
            valid,
            invalid,
            reason,
        )

    @classmethod
    def _extractively_supported(cls, claim: str, evidence: str) -> bool:
        claim_normalized = cls._normalize(claim)
        evidence_normalized = cls._normalize(evidence)
        if len(claim_normalized) < 4:
            return False
        start = evidence_normalized.find(claim_normalized)
        while start >= 0:
            prefix = evidence_normalized[:start]
            if not any(prefix.endswith(marker) for marker in cls._NEGATION_PREFIXES):
                return True
            start = evidence_normalized.find(claim_normalized, start + 1)
        return False

    @classmethod
    def extractively_supported(cls, claim: str, evidence: str) -> bool:
        """Public, polarity-aware extractive support check for validators.

        Grounding v0.3 originally kept this operation private because only NPC
        response validation used it.  Authoring validators also need the same
        negative-polarity protection, so this small wrapper makes the existing
        deterministic primitive reusable without duplicating its semantics.
        """
        return cls._extractively_supported(claim, evidence)

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text)).lower()

    @staticmethod
    def render(segments: Sequence[GroundedResponseSegment]) -> str:
        return "\n".join(segment.text.strip() for segment in segments).strip()


def safe_fallback_segments() -> tuple[GroundedResponseSegment, ...]:
    return (
        GroundedResponseSegment(
            "fallback_uncertainty",
            SegmentKind.UNCERTAIN,
            SAFE_FALLBACK_TEXT,
        ),
    )
