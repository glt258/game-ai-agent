"""Deterministic cross-field identity checks for explicitly affiliated drafts."""

from __future__ import annotations

from collections.abc import Iterable

from ..context import EvaluationContext
from ..models import EvaluationFinding


class IdentityCoherenceValidator:
    """Check that an affiliated draft carries Canon-derived identity signals."""

    validator_id = "identity_coherence"
    dimension = "identity_coherence"

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if (
            context.draft is None
            or context.expected_affiliation_id is None
            or context.draft.faction_id != context.expected_affiliation_id
        ):
            return ()
        affiliation = context.generation_result.design_plan.affiliation_context if (
            context.generation_result is not None
            and context.generation_result.design_plan is not None
        ) else None
        if affiliation is None or not affiliation.semantic_terms:
            return ()

        identity_text = " ".join(
            (
                context.draft.occupation,
                context.draft.social_role,
                context.draft.background,
                context.draft.design_pitch,
                context.draft.story_hook,
            )
        )
        if any(term in identity_text for term in affiliation.semantic_terms):
            return ()
        return (
            EvaluationFinding(
                validator_id=self.validator_id,
                code="IDENTITY_AFFILIATION_INCONSISTENT",
                severity="ERROR",
                blocking=True,
                stage="identity_coherence",
                field_path="occupation",
                message="Generated identity fields do not reflect the requested affiliation.",
            ),
        )


__all__ = ["IdentityCoherenceValidator"]
