"""Deterministic CharacterDraft representation-completeness checks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..context import EvaluationContext
from ..models import EvaluationFinding


class RepresentationCompletenessValidator:
    """Report missing design representation without judging semantic quality."""

    validator_id = "representation_completeness"
    dimension = "representation"

    _FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("description", "MISSING_CHARACTER_DESCRIPTION", ("description",)),
        ("personality", "MISSING_PERSONALITY", ("personality",)),
        ("background", "MISSING_BACKGROUND", ("background",)),
        ("motivation", "MISSING_MOTIVATION", ("motivation",)),
        ("conflict", "MISSING_CONFLICT", ("conflict",)),
        ("combat_role", "MISSING_COMBAT_ROLE", ("combat_role",)),
        ("abilities", "MISSING_ABILITIES", ("abilities",)),
    )

    _ALIASES = {
        "description": ("description", "design_pitch"),
        "abilities": ("abilities", "ability_concept"),
    }

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        findings: list[EvaluationFinding] = []
        for field_path, code, candidates in self._FIELDS:
            aliases = self._ALIASES.get(field_path, candidates)
            if self._present(context.draft, aliases):
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
        return findings

    @staticmethod
    def _present(draft: object, candidates: Sequence[str]) -> bool:
        for candidate in candidates:
            if not hasattr(draft, candidate):
                continue
            value: Any = getattr(draft, candidate)
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
