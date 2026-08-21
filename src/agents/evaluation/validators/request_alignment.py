"""Deterministic alignment checks between design intent and a draft."""

from __future__ import annotations

from collections.abc import Iterable

from ..context import EvaluationContext
from ..models import EvaluationFinding


_UNSPECIFIED_LEGACY_VALUES = frozenset({"none", "unspecified"})


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

        if intent is None:
            return findings

        requested = context.intent_role_profile
        generated = context.draft_role_profile
        assert requested is not None and generated is not None

        # Non-role legacy labels must produce an explicit failure rather than
        # disappearing into an unspecified profile and bypassing evaluation.
        if intent.combat_role not in _UNSPECIFIED_LEGACY_VALUES and requested.is_unspecified:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="REQUEST_COMBAT_ROLE_MISMATCH",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="combat_role_profile",
                    message=(
                        f"Requested legacy combat label {intent.combat_role!r} is not a "
                        "canonical combat role."
                    ),
                )
            )
            return findings

        if requested.primary_role is not None and generated.primary_role != requested.primary_role:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="REQUEST_PRIMARY_ROLE_MISMATCH",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="combat_role_profile.primary_role",
                    message=(
                        f"Requested primary role {requested.primary_role!r} does not match "
                        f"generated primary role {generated.primary_role!r}."
                    ),
                )
            )

        missing_secondary = tuple(
            role for role in requested.secondary_roles if role not in generated.secondary_roles
        )
        if missing_secondary:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="REQUEST_SECONDARY_ROLE_MISSING",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="combat_role_profile.secondary_roles",
                    message=(
                        "Generated draft is missing requested secondary role(s): "
                        f"{', '.join(missing_secondary)}."
                    ),
                )
            )

        return findings


__all__ = ["RequestAlignmentValidator"]
