"""Character Evaluation Layer v0.6.1-A contract and runner foundation."""

from .context import EvaluationContext, EvaluationSubject
from .models import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationFinding,
    EvaluationOutcome,
    EvaluationResult,
)
from .runner import EvaluationRunner, EvaluationValidator
from .validators import (
    IdentityCoherenceValidator,
    RepresentationCompletenessValidator,
    RequestAlignmentValidator,
)

__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "IdentityCoherenceValidator",
    "EvaluationFinding",
    "EvaluationContext",
    "EvaluationOutcome",
    "EvaluationResult",
    "EvaluationRunner",
    "RepresentationCompletenessValidator",
    "RequestAlignmentValidator",
    "EvaluationSubject",
    "EvaluationValidator",
]
