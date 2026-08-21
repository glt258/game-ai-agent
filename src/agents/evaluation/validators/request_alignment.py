"""Deterministic alignment checks between design intent and a draft."""

from __future__ import annotations

from collections.abc import Iterable

from ...character_generation import CharacterDraft
from ..context import EvaluationContext
from ..models import EvaluationFinding


_DRAFT_COMBAT_ROLES = frozenset(
    {"support", "control", "defense", "burst", "sustain", "flex", "none"}
)


class RequestAlignmentValidator:
    """Check explicitly requested role signals against generated values."""

    validator_id = "request_alignment"
    dimension = "request_alignment"

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        draft = context.draft
        intent = context.intent
        findings: list[EvaluationFinding] = []

        if intent is not None and intent.combat_role in _DRAFT_COMBAT_ROLES:
            if not isinstance(draft, CharacterDraft):
                raise TypeError("context.draft must be a CharacterDraft")
            generated = draft.combat_role
            if intent.combat_role != generated:
                findings.append(
                    EvaluationFinding(
                        validator_id=self.validator_id,
                        code="REQUEST_COMBAT_ROLE_MISMATCH",
                        severity="ERROR",
                        blocking=True,
                        stage="request_alignment",
                        field_path="combat_role",
                        message=(
                            f"Requested combat_role {intent.combat_role!r} does not match "
                            f"generated combat_role {generated!r}."
                        ),
                    )
                )

        return findings


__all__ = ["RequestAlignmentValidator"]
