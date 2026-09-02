"""Deterministic alignment between a Character role profile and one Skill artifact.

This module owns the Character ↔ Skill seam.  It consumes only the immutable
Character Skill projection, the canonical SkillKit candidate, and the existing
Skill Evaluation report.  It never calls a provider and never changes the
Skill evaluator's internal validity decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from character_skill import ProtocolSkillKitCandidate, SkillValidationReport
from combat_semantics import CombatRole, CombatRoleProfile

from .character_skill_projection import CharacterSkillDesignContext

CHARACTER_SKILL_ALIGNMENT_VERSION = "character-skill-alignment/0.1.0"
AlignmentStatus = Literal["PASS", "FAIL", "PARTIAL", "NOT_EVALUATED"]
AlignmentCoverage = Literal["primary", "secondary", "none", "not_evaluated"]
FindingKind = Literal[
    "supporting_evidence",
    "missing_evidence",
    "direct_contradiction",
    "not_evaluated",
]


class ArtifactBindingError(ValueError):
    """Stable fail-closed error for mismatched Character-Skill identities."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


# These are canonical compiler operations, not free-text labels.  One
# operation can provide evidence for more than one Character role.
_OPERATION_ROLES: Mapping[str, tuple[CombatRole, ...]] = {
    "ally_enablement": ("support",),
    "enemy_action_control": ("control",),
    "recover_or_mitigate": ("healer", "defense"),
    "threat_protection": ("support", "defense"),
    "direct_output": ("main_dps",),
    "follow_up_output": ("sub_dps",),
}


@dataclass(frozen=True)
class CharacterSkillEvidence:
    """Safe structured evidence extracted from one canonical Skill artifact."""

    role: CombatRole
    operation: str
    family: str
    mode: str
    artifact_paths: tuple[str, ...]
    centrality: str | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "role": self.role,
            "operation": self.operation,
            "family": self.family,
            "mode": self.mode,
            "artifact_paths": list(self.artifact_paths),
            "centrality": self.centrality,
        }


@dataclass(frozen=True)
class CharacterSkillAlignmentFinding:
    """One safe, auditable reason for an alignment result."""

    code: str
    kind: FindingKind
    blocking: bool
    character_role: CombatRole | None
    skill_evidence: tuple[CharacterSkillEvidence, ...]
    field_path: str
    artifact_path: str | None
    message: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "code": self.code,
            "kind": self.kind,
            "blocking": self.blocking,
            "character_role": self.character_role,
            "skill_evidence": [item.to_mapping() for item in self.skill_evidence],
            "field_path": self.field_path,
            "artifact_path": self.artifact_path,
            "message": self.message,
        }


@dataclass(frozen=True)
class CharacterSkillAlignmentContext:
    """Small immutable interface consumed by the alignment implementation."""

    character_context: CharacterSkillDesignContext
    skill_family: str
    skill_mode: str
    candidate: ProtocolSkillKitCandidate | None
    skill_evaluation: SkillValidationReport | None
    artifact_digest: str | None
    source_context_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.character_context, CharacterSkillDesignContext):
            raise TypeError("character_context must be a CharacterSkillDesignContext")
        if not isinstance(self.source_context_fingerprint, str) or not self.source_context_fingerprint:
            raise ValueError("source_context_fingerprint must be non-empty")
        if self.source_context_fingerprint != self.character_context.source_context_fingerprint:
            raise ArtifactBindingError(
                "SOURCE_CONTEXT_FINGERPRINT_MISMATCH",
                "provided fingerprint does not match CharacterSkillDesignContext",
            )
        if self.candidate is not None and not isinstance(self.candidate, ProtocolSkillKitCandidate):
            raise TypeError("candidate must be a ProtocolSkillKitCandidate or None")
        if self.candidate is not None:
            if self.artifact_digest is None:
                raise ArtifactBindingError(
                    "ARTIFACT_DIGEST_MISSING",
                    "a canonical candidate requires an artifact digest",
                )
            if self.artifact_digest != self.candidate.digest:
                raise ArtifactBindingError(
                    "ARTIFACT_DIGEST_MISMATCH",
                    "provided digest does not match canonical candidate",
                )
        if self.skill_evaluation is not None and not isinstance(self.skill_evaluation, SkillValidationReport):
            raise TypeError("skill_evaluation must be a SkillValidationReport or None")
        if (
            self.candidate is not None
            and self.skill_evaluation is not None
            and self.skill_evaluation.candidate_digest != self.candidate.digest
        ):
            raise ArtifactBindingError(
                "EVALUATION_CANDIDATE_DIGEST_MISMATCH",
                "evaluation report is not bound to canonical candidate",
            )


@dataclass(frozen=True)
class CharacterSkillAlignmentResult:
    """Deterministic single-artifact Character ↔ Skill alignment result."""

    status: AlignmentStatus
    coverage: AlignmentCoverage
    findings: tuple[CharacterSkillAlignmentFinding, ...]
    blocking: bool
    summary: str
    artifact_digest: str | None
    source_context_fingerprint: str
    skill_roles: tuple[CombatRole, ...] = ()
    evidence: tuple[CharacterSkillEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "skill_roles", tuple(self.skill_roles))
        object.__setattr__(self, "evidence", tuple(self.evidence))

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "coverage": self.coverage,
            "findings": [item.to_mapping() for item in self.findings],
            "blocking": self.blocking,
            "summary": self.summary,
            "artifact_digest": self.artifact_digest,
            "source_context_fingerprint": self.source_context_fingerprint,
            "skill_roles": list(self.skill_roles),
            "evidence": [item.to_mapping() for item in self.evidence],
        }


def _effect_index(candidate: ProtocolSkillKitCandidate) -> dict[str, tuple[str, str, object]]:
    index: dict[str, tuple[str, str, object]] = {}
    for entry in candidate.entries:
        for protocol in entry.protocols:
            for effect in protocol.causes:
                path = f"/entries/{entry.ability_id}/protocols/{protocol.protocol_id}/causes/{effect.effect_id}"
                index[f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}"] = (
                    path,
                    protocol.protocol_id,
                    effect,
                )
    return index


def _centrality_by_effect_ref(candidate: ProtocolSkillKitCandidate) -> dict[str, str]:
    return {
        ref.id: evidence.centrality
        for evidence in candidate.role_evidence
        for ref in evidence.effect_refs
    }


def extract_character_skill_evidence(
    candidate: ProtocolSkillKitCandidate | None,
    *,
    skill_family: str,
    skill_mode: str,
) -> tuple[CharacterSkillEvidence, ...]:
    """Extract canonical operation-to-role evidence without evaluating a Skill."""

    if candidate is None:
        return ()
    effects = _effect_index(candidate)
    centrality = _centrality_by_effect_ref(candidate)
    found: dict[tuple[CombatRole, str, tuple[str, ...]], CharacterSkillEvidence] = {}
    for key, (path, _protocol_id, effect) in effects.items():
        operation = effect.operation
        if operation not in _OPERATION_ROLES:
            continue
        refs = tuple(
            evidence_ref.id
            for evidence in candidate.role_evidence
            for evidence_ref in evidence.effect_refs
            if evidence_ref.id == key
        )
        effect_paths = (path,)
        for role in _OPERATION_ROLES[operation]:
            found[(role, operation, effect_paths)] = CharacterSkillEvidence(
                role=role,
                operation=operation,
                family=skill_family,
                mode=skill_mode,
                artifact_paths=effect_paths,
                centrality=centrality.get(refs[0]) if refs else None,
            )
    return tuple(
        found[key]
        for key in sorted(found, key=lambda value: (value[0], value[1], value[2]))
    )


def _extract_evidence(
    context: CharacterSkillAlignmentContext,
) -> tuple[CharacterSkillEvidence, ...]:
    return extract_character_skill_evidence(
        context.candidate,
        skill_family=context.skill_family,
        skill_mode=context.skill_mode,
    )


def _declared_roles(profile: CombatRoleProfile) -> tuple[CombatRole, ...]:
    roles: list[CombatRole] = []
    if profile.primary_role is not None:
        roles.append(profile.primary_role)
    roles.extend(profile.secondary_roles)
    return tuple(roles)


def _role_label(role: CombatRole) -> str:
    return role.replace("_", " ")


def evaluate_character_skill_alignment(
    context: CharacterSkillAlignmentContext,
) -> CharacterSkillAlignmentResult:
    """Evaluate one valid Skill artifact against the current Character roles.

    The result is deliberately evidence-based and score-free.  A Skill that
    supports either the primary or a declared secondary role can pass; a
    single Skill is never required to cover the whole future Character kit.
    """

    report = context.skill_evaluation
    if report is None or report.outcome != "PASS" or context.candidate is None:
        reason = (
            "Skill Evaluation did not PASS; Character-Skill Alignment was not evaluated."
            if report is None or report.outcome != "PASS"
            else "No canonical Skill artifact was available; Character-Skill Alignment was not evaluated."
        )
        finding = CharacterSkillAlignmentFinding(
            code="SKILL_ALIGNMENT_NOT_EVALUATED",
            kind="not_evaluated",
            blocking=False,
            character_role=None,
            skill_evidence=(),
            field_path="/skill_evaluation",
            artifact_path=None,
            message=reason,
        )
        return CharacterSkillAlignmentResult(
            status="NOT_EVALUATED",
            coverage="not_evaluated",
            findings=(finding,),
            blocking=False,
            summary=reason,
            artifact_digest=context.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
        )

    character_roles = _declared_roles(context.character_context.combat_role_profile)
    evidence = _extract_evidence(context)
    skill_roles = tuple(sorted({item.role for item in evidence}))
    if not character_roles:
        message = "Character combat identity is unspecified; alignment requires a declared combat role."
        finding = CharacterSkillAlignmentFinding(
            code="CHARACTER_COMBAT_ROLE_UNSPECIFIED",
            kind="supporting_evidence",
            blocking=True,
            character_role=None,
            skill_evidence=evidence,
            field_path="/combat_role_profile",
            artifact_path=None,
            message=message,
        )
        return CharacterSkillAlignmentResult(
            status="NOT_EVALUATED",
            coverage="not_evaluated",
            findings=(finding,),
            blocking=True,
            summary=message,
            artifact_digest=context.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
            skill_roles=skill_roles,
            evidence=evidence,
        )

    matched = tuple(role for role in character_roles if role in skill_roles)
    primary = character_roles[0]
    if matched:
        primary_supported = primary in matched
        coverage: AlignmentCoverage = "primary" if primary_supported else "secondary"
        coverage_roles = ", ".join(_role_label(role) for role in matched)
        summary = (
            f"Skill provides structured {coverage_roles} evidence for the Character combat identity."
        )
        finding = CharacterSkillAlignmentFinding(
            code="CHARACTER_ROLE_EVIDENCE_SUPPORTED",
            kind="missing_evidence",
            blocking=False,
            character_role=primary if primary_supported else matched[0],
            skill_evidence=tuple(item for item in evidence if item.role in matched),
            field_path="/combat_role_profile",
            artifact_path=(evidence[0].artifact_paths[0] if evidence else None),
            message=summary,
        )
        return CharacterSkillAlignmentResult(
            status="PASS",
            coverage=coverage,
            findings=(finding,),
            blocking=False,
            summary=summary,
            artifact_digest=context.artifact_digest,
            source_context_fingerprint=context.source_context_fingerprint,
            skill_roles=skill_roles,
            evidence=evidence,
        )

    declared = ", ".join(_role_label(role) for role in character_roles)
    observed = ", ".join(_role_label(role) for role in skill_roles) or "no recognized role"
    message = (
        f"Skill is internally valid, but its structured evidence ({observed}) does not support "
        f"the Character combat identity ({declared})."
    )
    finding = CharacterSkillAlignmentFinding(
        code="SKILL_ROLE_CONTRADICTS_CHARACTER_IDENTITY",
        kind="direct_contradiction",
        blocking=True,
        character_role=primary,
        skill_evidence=evidence,
        field_path="/combat_role_profile",
        artifact_path=(evidence[0].artifact_paths[0] if evidence else None),
        message=message,
    )
    return CharacterSkillAlignmentResult(
        status="FAIL",
        coverage="none",
        findings=(finding,),
        blocking=True,
        summary=message,
        artifact_digest=context.artifact_digest,
        source_context_fingerprint=context.source_context_fingerprint,
        skill_roles=skill_roles,
        evidence=evidence,
    )


__all__ = [
    "ArtifactBindingError",
    "CHARACTER_SKILL_ALIGNMENT_VERSION",
    "AlignmentCoverage",
    "AlignmentStatus",
    "CharacterSkillAlignmentContext",
    "CharacterSkillAlignmentFinding",
    "CharacterSkillAlignmentResult",
    "CharacterSkillEvidence",
    "extract_character_skill_evidence",
    "evaluate_character_skill_alignment",
]
