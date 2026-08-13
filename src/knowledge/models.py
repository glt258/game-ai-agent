from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeDecision:
    decision: str
    character_id: str
    lore_id: str
    reason_code: str
    reason: str
    matched_rule_id: str | None = None
    matched_subject: str | None = None
    acquisition_channel: str | None = None
    evaluated_conditions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    trace: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.decision not in {"allow", "deny"}:
            raise ValueError(f"Invalid decision: {self.decision}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "character_id": self.character_id,
            "lore_id": self.lore_id,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "matched_rule_id": self.matched_rule_id,
            "matched_subject": self.matched_subject,
            "acquisition_channel": self.acquisition_channel,
            "evaluated_conditions": [dict(item) for item in self.evaluated_conditions],
            "trace": [dict(item) for item in self.trace],
        }

