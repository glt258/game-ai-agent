"""One-way deterministic rendering for structured SkillKit candidates."""

from __future__ import annotations

from .models import ProtocolSkillKitCandidate


def render_ability_concept(candidate: ProtocolSkillKitCandidate) -> str:
    """Render a stable compatibility summary without parsing legacy prose."""

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("render_ability_concept expects a ProtocolSkillKitCandidate")

    parts: list[str] = []
    if candidate.display_summary.strip():
        parts.append(candidate.display_summary.strip())
    for entry in sorted(candidate.entries, key=lambda item: item.ability_id):
        clauses: list[str] = []
        for protocol in sorted(entry.protocols, key=lambda item: item.protocol_id):
            trigger = "unspecified trigger"
            if protocol.when is not None:
                subject = protocol.when.subject
                if subject is not None:
                    selector = f"/{subject.selector}" if subject.selector else ""
                    trigger = f"{subject.kind}{selector} {protocol.when.event or 'event'}".strip()
                elif protocol.when.event:
                    trigger = protocol.when.event
            operations = ", ".join(
                sorted(effect.operation or "unspecified effect" for effect in protocol.causes)
            ) or "no effects"
            clauses.append(f"{trigger} -> {operations}")
        parts.append(
            f"{entry.name or entry.ability_id}: "
            f"{'; '.join(clauses) if clauses else 'no protocols'}"
        )
    return " ".join(parts) if parts else "SkillKit concept: no ability entries declared."


__all__ = ["render_ability_concept"]
