"""Deterministic CharacterDraft representation-completeness checks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from character_intelligence.field_authorization import (
    CharacterGenerationField,
    FieldAuthorizationState,
)

from ...character_generation import CharacterDraft
from ..context import EvaluationContext
from ..models import EvaluationFinding


class RepresentationCompletenessValidator:
    """Report missing design representation without judging semantic quality."""

    validator_id = "representation_completeness"
    dimension = "representation"

    _FIELDS: tuple[
        tuple[str, str, tuple[str, ...], CharacterGenerationField | None], ...
    ] = (
        (
            "design_pitch",
            "MISSING_CHARACTER_DESCRIPTION",
            ("design_pitch",),
            CharacterGenerationField.DESIGN_PITCH,
        ),
        (
            "personality",
            "MISSING_PERSONALITY",
            ("personality",),
            CharacterGenerationField.PERSONALITY,
        ),
        (
            "background",
            "MISSING_BACKGROUND",
            ("background",),
            CharacterGenerationField.BACKGROUND,
        ),
        ("combat_role_profile", "MISSING_COMBAT_ROLE", ("combat_role_profile",), None),
        (
            "ability_concept",
            "MISSING_ABILITIES",
            ("ability_concept",),
            CharacterGenerationField.ABILITY_CONCEPT,
        ),
    )

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        findings: list[EvaluationFinding] = []
        policy = context.subject.field_authorization_policy
        for field_path, code, candidates, governed_field in self._FIELDS:
            if (
                policy is not None
                and governed_field is not None
                and policy.for_field(governed_field).state
                is FieldAuthorizationState.UNAUTHORIZED
            ):
                continue
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
