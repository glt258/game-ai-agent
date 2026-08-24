"""Deterministic CharacterDraft representation-completeness checks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ...character_generation import CharacterDraft
from ..context import EvaluationContext
from ..models import EvaluationFinding


class RepresentationCompletenessValidator:
    """Report missing design representation without judging semantic quality."""

    validator_id = "representation_completeness"
    dimension = "representation"

    _FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("design_pitch", "MISSING_CHARACTER_DESCRIPTION", ("design_pitch",)),
        ("personality", "MISSING_PERSONALITY", ("personality",)),
        ("background", "MISSING_BACKGROUND", ("background",)),
        ("combat_role_profile", "MISSING_COMBAT_ROLE", ("combat_role_profile",)),
        ("ability_concept", "MISSING_ABILITIES", ("ability_concept",)),
    )

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        findings: list[EvaluationFinding] = []
        for field_path, code, candidates in self._FIELDS:
            if self._present(context.draft, candidates):
                continue
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code=code,
                    severity="WARNING",
                    blocking=False,
                    stage="representation",
                    field_path=field_path,
                    message=f"CharacterDraft field {field_path!r} is missing or empty.",
                )
            )
        report = context.skill_validation_report
        if report is not None:
            seen = {
                (finding.code, finding.field_path, finding.severity, finding.blocking)
                for finding in findings
            }
            for skill_finding in report.findings:
                blocking = bool(skill_finding.blocking and not skill_finding.repairable)
                severity = "ERROR" if blocking else "WARNING"
                key = (
                    skill_finding.code,
                    skill_finding.field_path,
                    severity,
                    blocking,
                )
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    EvaluationFinding(
                        validator_id=self.validator_id,
                        code=skill_finding.code,
                        severity=severity,
                        blocking=blocking,
                        stage="representation",
                        field_path=skill_finding.field_path,
                        message=f"SkillKit structural finding {skill_finding.code}.",
                    )
                )
        return findings

    @staticmethod
    def _present(draft: CharacterDraft, candidates: Sequence[str]) -> bool:
        for candidate in candidates:
            value = getattr(draft, candidate)
            if isinstance(value, str):
                if value.strip():
                    return True
            elif isinstance(value, (Sequence, set, frozenset, dict)):
                if len(value) > 0:
                    return True
            elif value is not None:
                return True
        return False


__all__ = ["RepresentationCompletenessValidator"]
