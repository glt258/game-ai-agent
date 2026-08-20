"""Deterministic alignment checks between design intent and a draft."""

from __future__ import annotations

from collections.abc import Iterable

from ..context import EvaluationContext
from ..models import EvaluationFinding


class RequestAlignmentValidator:
    """Check explicitly requested role signals against generated values."""

    validator_id = "request_alignment"
    dimension = "request_alignment"

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        intent = context.intent
        draft = context.draft
        findings: list[EvaluationFinding] = []

        if intent.combat_role != "unspecified":
            generated = getattr(draft, "combat_role", None)
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

        if intent.rarity is not None:
            generated = getattr(draft, "rarity", None)
            if intent.rarity != generated:
                findings.append(
                    EvaluationFinding(
                        validator_id=self.validator_id,
                        code="REQUEST_RARITY_MISMATCH",
                        severity="WARNING",
                        blocking=False,
                        stage="request_alignment",
                        field_path="rarity",
                        message=(
                            f"Requested rarity {intent.rarity!r} does not match "
                            f"generated rarity {generated!r}."
                        ),
                    )
                )

        if intent.role_type != "character":
            generated = getattr(draft, "role_type", "character")
            if intent.role_type != generated:
                findings.append(
                    EvaluationFinding(
                        validator_id=self.validator_id,
                        code="REQUEST_ROLE_TYPE_MISMATCH",
                        severity="ERROR",
                        blocking=True,
                        stage="request_alignment",
                        field_path="role_type",
                        message=(
                            f"Requested role_type {intent.role_type!r} does not match "
                            f"generated role_type {generated!r}."
                        ),
                    )
                )

        return findings


__all__ = ["RequestAlignmentValidator"]
