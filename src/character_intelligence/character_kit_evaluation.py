"""Deterministic whole-Kit Character combat-role coverage evaluation.

This module is the independent semantic seam after Kit structural validation.
It deliberately consumes canonical Skill evidence and never invokes a
provider, compiler, Skill evaluator, or LLM.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from combat_semantics import CombatRoleProfile

from .character_kit import CharacterKit, CharacterKitStructuralValidator
from .character_skill_alignment import (
    CharacterSkillEvidence,
    extract_character_skill_evidence,
)
from .skill_artifact import ArtifactDriftStatus, current_skill_artifact_versions

CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION = "character-kit-role-coverage-evaluator/0.1.0"
CHARACTER_KIT_EVALUATION_CONTEXT_VERSION = "character-kit-evaluation-context/0.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EvaluationStatus = Literal["PASS", "PARTIAL", "FAIL", "NOT_EVALUATED"]
FindingKind = Literal[
    "supporting_evidence",
    "missing_evidence",
    "direct_contradiction",
    "not_evaluated",
]


@dataclass(frozen=True)
class CharacterKitEvaluationContext:
    """The minimal immutable Character identity consumed by Kit evaluation."""

    combat_role_profile: CombatRoleProfile
    context_contract_version: str = CHARACTER_KIT_EVALUATION_CONTEXT_VERSION
    context_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.combat_role_profile, CombatRoleProfile):
            raise TypeError("combat_role_profile must be a CombatRoleProfile")
        if self.context_contract_version != CHARACTER_KIT_EVALUATION_CONTEXT_VERSION:
            raise ValueError("unsupported CharacterKit evaluation context version")
        canonical = json.dumps(
            {
                "context_contract_version": self.context_contract_version,
                "combat_role_profile": self.combat_role_profile.to_dict(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(
            self,
            "context_fingerprint",
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    @property
    def evaluation_context_fingerprint(self) -> str:
        """Compatibility name used by the evaluation result contract."""

        return self.context_fingerprint

    @property
    def kit_evaluation_context_fingerprint(self) -> str:
        """Explicit name for the dedicated Kit evaluation identity."""

        return self.context_fingerprint

    def to_mapping(self) -> dict[str, object]:
        return {
            "context_contract_version": self.context_contract_version,
            "combat_role_profile": self.combat_role_profile.to_dict(),
            "context_fingerprint": self.context_fingerprint,
        }

    @classmethod
    def from_mapping(cls, value: object) -> "CharacterKitEvaluationContext":
        if not isinstance(value, Mapping):
            raise ValueError("CharacterKitEvaluationContext must be an object")
        payload = dict(value)
        expected = {
            "context_contract_version",
            "combat_role_profile",
            "context_fingerprint",
        }
        if set(payload) != expected:
            raise ValueError("CharacterKitEvaluationContext fields are not exact")
        context = cls(
            combat_role_profile=CombatRoleProfile.from_mapping(payload["combat_role_profile"]),
            context_contract_version=payload["context_contract_version"],  # type: ignore[arg-type]
        )
        if payload["context_fingerprint"] != context.context_fingerprint:
            raise ValueError("evaluation context fingerprint mismatch")
        return context


@dataclass(frozen=True)
class CharacterKitRoleCoverageEvidence:
    """One traceable role contribution from one Kit association."""

    role: str
    association_id: str
    artifact_digest: str
    operation: str
    artifact_paths: tuple[str, ...]
    centrality: str | None
    family: str
    mode: str

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.artifact_digest):
            raise ValueError("artifact_digest must be SHA-256")
        object.__setattr__(self, "artifact_paths", tuple(self.artifact_paths))

    def to_mapping(self) -> dict[str, object]:
        return {
            "role": self.role,
            "association_id": self.association_id,
            "artifact_digest": self.artifact_digest,
            "operation": self.operation,
            "artifact_paths": list(self.artifact_paths),
            "centrality": self.centrality,
            "family": self.family,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class CharacterKitRoleCoverage:
    role: str
    supported: bool
    evidence: tuple[CharacterKitRoleCoverageEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))

    def to_mapping(self) -> dict[str, object]:
        return {
            "role": self.role,
            "supported": self.supported,
            "evidence": [item.to_mapping() for item in self.evidence],
        }


@dataclass(frozen=True)
class CharacterKitCoverage:
    primary: CharacterKitRoleCoverage
    secondary: tuple[CharacterKitRoleCoverage, ...] = ()
    observed_roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "secondary", tuple(self.secondary))
        object.__setattr__(self, "observed_roles", tuple(self.observed_roles))

    def to_mapping(self) -> dict[str, object]:
        return {
            "primary": self.primary.to_mapping(),
            "secondary": [item.to_mapping() for item in self.secondary],
            "observed_roles": list(self.observed_roles),
        }


@dataclass(frozen=True)
class CharacterKitEvaluationFinding:
    code: str
    kind: FindingKind
    blocking: bool
    character_role: str | None
    artifact_evidence: tuple[CharacterKitRoleCoverageEvidence, ...]
    artifact_digests: tuple[str, ...]
    field_path: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_evidence", tuple(self.artifact_evidence))
        object.__setattr__(self, "artifact_digests", tuple(self.artifact_digests))

    def to_mapping(self) -> dict[str, object]:
        return {
            "code": self.code,
            "kind": self.kind,
            "blocking": self.blocking,
            "character_role": self.character_role,
            "artifact_evidence": [item.to_mapping() for item in self.artifact_evidence],
            "artifact_digests": list(self.artifact_digests),
            "field_path": self.field_path,
            "message": self.message,
        }


@dataclass(frozen=True)
class CharacterKitEvaluationResult:
    """Immutable, score-free whole-Kit role coverage report."""

    status: EvaluationStatus
    kit_digest: str
    evaluation_context_fingerprint: str
    evaluator_version: str
    coverage: CharacterKitCoverage
    findings: tuple[CharacterKitEvaluationFinding, ...]
    report_digest: str
    blocking: bool
    summary: str

    def __post_init__(self) -> None:
        if self.evaluator_version != CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION:
            raise ValueError("unsupported CharacterKit role coverage evaluator version")
        if not _SHA256_RE.fullmatch(self.kit_digest):
            raise ValueError("kit_digest must be SHA-256")
        if not _SHA256_RE.fullmatch(self.evaluation_context_fingerprint):
            raise ValueError("evaluation_context_fingerprint must be SHA-256")
        if not _SHA256_RE.fullmatch(self.report_digest):
            raise ValueError("report_digest must be SHA-256")
        object.__setattr__(self, "findings", tuple(self.findings))

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "kit_digest": self.kit_digest,
            "evaluation_context_fingerprint": self.evaluation_context_fingerprint,
            "evaluator_version": self.evaluator_version,
            "coverage": self.coverage.to_mapping(),
            "findings": [item.to_mapping() for item in self.findings],
            "report_digest": self.report_digest,
            "blocking": self.blocking,
            "summary": self.summary,
        }

    @classmethod
    def from_mapping(cls, value: object) -> "CharacterKitEvaluationResult":
        if not isinstance(value, Mapping):
            raise ValueError("CharacterKitEvaluationResult must be an object")
        payload = dict(value)
        expected = {
            "status",
            "kit_digest",
            "evaluation_context_fingerprint",
            "evaluator_version",
            "coverage",
            "findings",
            "report_digest",
            "blocking",
            "summary",
        }
        if set(payload) != expected:
            raise ValueError("CharacterKitEvaluationResult fields are not exact")
        status = payload["status"]
        if status not in {"PASS", "PARTIAL", "FAIL", "NOT_EVALUATED"}:
            raise ValueError("unsupported CharacterKit evaluation status")
        coverage_payload = payload["coverage"]
        if not isinstance(coverage_payload, Mapping):
            raise ValueError("coverage must be an object")
        coverage = _coverage_from_mapping(coverage_payload)
        findings_payload = payload["findings"]
        if not isinstance(findings_payload, list):
            raise ValueError("findings must be an array")
        findings = tuple(_finding_from_mapping(item) for item in findings_payload)
        result = cls(
            status=status,  # type: ignore[arg-type]
            kit_digest=_string_field(payload["kit_digest"], "kit_digest"),
            evaluation_context_fingerprint=_string_field(
                payload["evaluation_context_fingerprint"],
                "evaluation_context_fingerprint",
            ),
            evaluator_version=_string_field(payload["evaluator_version"], "evaluator_version"),
            coverage=coverage,
            findings=findings,
            report_digest=_string_field(payload["report_digest"], "report_digest"),
            blocking=_bool_field(payload["blocking"], "blocking"),
            summary=_string_field(payload["summary"], "summary"),
        )
        digest_payload = result.to_mapping()
        digest_payload.pop("report_digest")
        if _digest_payload(digest_payload) != result.report_digest:
            raise ValueError("evaluation report digest mismatch")
        return result


def _string_field(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _bool_field(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _evidence_from_mapping(value: object) -> CharacterKitRoleCoverageEvidence:
    if not isinstance(value, Mapping):
        raise ValueError("artifact evidence must be an object")
    payload = dict(value)
    expected = {
        "role",
        "association_id",
        "artifact_digest",
        "operation",
        "artifact_paths",
        "centrality",
        "family",
        "mode",
    }
    if set(payload) != expected:
        raise ValueError("artifact evidence fields are not exact")
    paths = payload["artifact_paths"]
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        raise ValueError("artifact_paths must be an array of strings")
    centrality = payload["centrality"]
    if centrality is not None and not isinstance(centrality, str):
        raise ValueError("centrality must be a string or null")
    return CharacterKitRoleCoverageEvidence(
        role=_string_field(payload["role"], "role"),
        association_id=_string_field(payload["association_id"], "association_id"),
        artifact_digest=_string_field(payload["artifact_digest"], "artifact_digest"),
        operation=_string_field(payload["operation"], "operation"),
        artifact_paths=tuple(paths),
        centrality=centrality,
        family=_string_field(payload["family"], "family"),
        mode=_string_field(payload["mode"], "mode"),
    )


def _coverage_item_from_mapping(value: object) -> CharacterKitRoleCoverage:
    if not isinstance(value, Mapping):
        raise ValueError("role coverage must be an object")
    payload = dict(value)
    if set(payload) != {"role", "supported", "evidence"}:
        raise ValueError("role coverage fields are not exact")
    evidence = payload["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("role coverage evidence must be an array")
    return CharacterKitRoleCoverage(
        role=_string_field(payload["role"], "role"),
        supported=_bool_field(payload["supported"], "supported"),
        evidence=tuple(_evidence_from_mapping(item) for item in evidence),
    )


def _coverage_from_mapping(value: Mapping[str, object]) -> CharacterKitCoverage:
    payload = dict(value)
    if set(payload) != {"primary", "secondary", "observed_roles"}:
        raise ValueError("coverage fields are not exact")
    secondary = payload["secondary"]
    observed_roles = payload["observed_roles"]
    if not isinstance(secondary, list) or not isinstance(observed_roles, list):
        raise ValueError("coverage secondary and observed_roles must be arrays")
    if not all(isinstance(item, str) for item in observed_roles):
        raise ValueError("observed_roles must contain strings")
    return CharacterKitCoverage(
        primary=_coverage_item_from_mapping(payload["primary"]),
        secondary=tuple(_coverage_item_from_mapping(item) for item in secondary),
        observed_roles=tuple(observed_roles),
    )


def _finding_from_mapping(value: object) -> CharacterKitEvaluationFinding:
    if not isinstance(value, Mapping):
        raise ValueError("evaluation finding must be an object")
    payload = dict(value)
    expected = {
        "code",
        "kind",
        "blocking",
        "character_role",
        "artifact_evidence",
        "artifact_digests",
        "field_path",
        "message",
    }
    if set(payload) != expected:
        raise ValueError("evaluation finding fields are not exact")
    evidence = payload["artifact_evidence"]
    digests = payload["artifact_digests"]
    if not isinstance(evidence, list) or not isinstance(digests, list):
        raise ValueError("finding evidence and digests must be arrays")
    if not all(isinstance(item, str) for item in digests):
        raise ValueError("artifact_digests must contain strings")
    role = payload["character_role"]
    if role is not None and not isinstance(role, str):
        raise ValueError("character_role must be a string or null")
    kind = payload["kind"]
    if kind not in {
        "supporting_evidence",
        "missing_evidence",
        "direct_contradiction",
        "not_evaluated",
    }:
        raise ValueError("unsupported evaluation finding kind")
    return CharacterKitEvaluationFinding(
        code=_string_field(payload["code"], "code"),
        kind=kind,  # type: ignore[arg-type]
        blocking=_bool_field(payload["blocking"], "blocking"),
        character_role=role,
        artifact_evidence=tuple(_evidence_from_mapping(item) for item in evidence),
        artifact_digests=tuple(digests),
        field_path=_string_field(payload["field_path"], "field_path"),
        message=_string_field(payload["message"], "message"),
    )


def _declared_roles(context: CharacterKitEvaluationContext) -> tuple[str, ...]:
    profile = context.combat_role_profile
    primary = (profile.primary_role,) if profile.primary_role is not None else ()
    return primary + tuple(profile.secondary_roles)


def _coverage(
    context: CharacterKitEvaluationContext,
    evidence: tuple[CharacterKitRoleCoverageEvidence, ...],
) -> CharacterKitCoverage:
    declared = _declared_roles(context)
    by_role: dict[str, list[CharacterKitRoleCoverageEvidence]] = {}
    for item in evidence:
        by_role.setdefault(item.role, []).append(item)
    primary_role = declared[0] if declared else "unspecified"
    primary = CharacterKitRoleCoverage(
        primary_role,
        bool(by_role.get(primary_role)),
        tuple(by_role.get(primary_role, ())),
    )
    secondary = tuple(
        CharacterKitRoleCoverage(role, bool(by_role.get(role)), tuple(by_role.get(role, ())))
        for role in declared[1:]
    )
    return CharacterKitCoverage(
        primary=primary,
        secondary=secondary,
        observed_roles=tuple(sorted(by_role)),
    )


def _digest_payload(result: dict[str, object]) -> str:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _result(
    *,
    status: EvaluationStatus,
    kit: CharacterKit,
    context: CharacterKitEvaluationContext,
    coverage: CharacterKitCoverage,
    findings: tuple[CharacterKitEvaluationFinding, ...],
    summary: str,
) -> CharacterKitEvaluationResult:
    blocking = any(item.blocking for item in findings)
    payload = {
        "status": status,
        "kit_digest": kit.kit_digest,
        "evaluation_context_fingerprint": context.context_fingerprint,
        "evaluator_version": CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION,
        "coverage": coverage.to_mapping(),
        "findings": [item.to_mapping() for item in findings],
        "blocking": blocking,
        "summary": summary,
    }
    return CharacterKitEvaluationResult(
        status=status,
        kit_digest=kit.kit_digest,
        evaluation_context_fingerprint=context.context_fingerprint,
        evaluator_version=CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION,
        coverage=coverage,
        findings=findings,
        report_digest=_digest_payload(payload),
        blocking=blocking,
        summary=summary,
    )


def _not_evaluated(
    kit: CharacterKit,
    context: CharacterKitEvaluationContext,
    *,
    code: str,
    field_path: str,
    message: str,
    artifact_digests: tuple[str, ...] = (),
) -> CharacterKitEvaluationResult:
    declared = _declared_roles(context)
    primary_role = declared[0] if declared else "unspecified"
    coverage = CharacterKitCoverage(CharacterKitRoleCoverage(primary_role, False), ())
    finding = CharacterKitEvaluationFinding(
        code=code,
        kind="not_evaluated",
        blocking=True,
        character_role=None,
        artifact_evidence=(),
        artifact_digests=artifact_digests,
        field_path=field_path,
        message=message,
    )
    return _result(
        status="NOT_EVALUATED",
        kit=kit,
        context=context,
        coverage=coverage,
        findings=(finding,),
        summary=message,
    )


def _association_evidence(kit: CharacterKit) -> tuple[CharacterKitRoleCoverageEvidence, ...]:
    values: list[CharacterKitRoleCoverageEvidence] = []
    for association in kit.associations:
        extracted: tuple[CharacterSkillEvidence, ...] = extract_character_skill_evidence(
            association.artifact.canonical_artifact,
            skill_family=association.family,
            skill_mode=association.mode,
        )
        values.extend(
            CharacterKitRoleCoverageEvidence(
                role=item.role,
                association_id=association.association_id,
                artifact_digest=association.artifact_digest,
                operation=item.operation,
                artifact_paths=item.artifact_paths,
                centrality=item.centrality,
                family=item.family,
                mode=item.mode,
            )
            for item in extracted
        )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.role,
                item.artifact_digest,
                item.operation,
                item.artifact_paths,
                item.centrality or "",
            ),
        )
    )


def evaluate_character_kit_role_coverage(
    kit: CharacterKit,
    context: CharacterKitEvaluationContext,
    *,
    current_skill_context_fingerprint: str | None = None,
) -> CharacterKitEvaluationResult:
    """Evaluate only whole-Kit combat-role coverage.

    ``current_skill_context_fingerprint`` is an optional application-layer
    freshness check for existing Character-Skill bindings.  It is deliberately
    not stored in ``CharacterKitEvaluationContext`` because that context has a
    different, role-only identity.
    """

    if not isinstance(kit, CharacterKit):
        raise TypeError("kit must be a CharacterKit")
    if not isinstance(context, CharacterKitEvaluationContext):
        raise TypeError("context must be a CharacterKitEvaluationContext")

    structural = CharacterKitStructuralValidator().validate(kit)
    if structural.status != "PASS":
        return _not_evaluated(
            kit,
            context,
            code="KIT_ROLE_COVERAGE_NOT_EVALUATED",
            field_path="/kit",
            message="Kit role coverage was not evaluated because Kit structure is invalid.",
        )

    declared = _declared_roles(context)
    if not declared:
        return _not_evaluated(
            kit,
            context,
            code="KIT_ROLE_PROFILE_UNSPECIFIED",
            field_path="/combat_role_profile",
            message="Kit role coverage requires a declared Character combat role.",
        )
    if not kit.associations:
        return _not_evaluated(
            kit,
            context,
            code="KIT_ROLE_COVERAGE_NOT_EVALUATED",
            field_path="/associations",
            message="Kit role coverage was not evaluated because the authoring Kit has no Skill evidence.",
        )

    current_versions = current_skill_artifact_versions()
    invalid_digests: list[str] = []
    for association in kit.associations:
        artifact = association.artifact
        if artifact.original_evaluation.outcome != "PASS":
            invalid_digests.append(association.artifact_digest)
            continue
        if association.binding.artifact_digest != association.artifact_digest:
            invalid_digests.append(association.artifact_digest)
            continue
        if association.binding.alignment.artifact_digest != association.artifact_digest:
            invalid_digests.append(association.artifact_digest)
            continue
        if (
            association.binding.alignment.source_context_fingerprint
            != association.source_context_fingerprint
        ):
            invalid_digests.append(association.artifact_digest)
            continue
        if (
            current_skill_context_fingerprint is not None
            and association.source_context_fingerprint != current_skill_context_fingerprint
        ):
            invalid_digests.append(association.artifact_digest)
            continue
        compatibility = association.compatibility_for(current_versions)
        if compatibility.status != ArtifactDriftStatus.CURRENT_COMPATIBLE:
            invalid_digests.append(association.artifact_digest)

    if invalid_digests:
        return _not_evaluated(
            kit,
            context,
            code="KIT_ROLE_COVERAGE_NOT_EVALUATED",
            field_path="/associations",
            message="Kit role coverage was not evaluated because one or more Skill bindings are not current and usable.",
            artifact_digests=tuple(sorted(set(invalid_digests))),
        )

    evidence = _association_evidence(kit)
    if not evidence:
        return _not_evaluated(
            kit,
            context,
            code="KIT_ROLE_EVIDENCE_UNAVAILABLE",
            field_path="/associations",
            message="Kit role coverage was not evaluated because no canonical role evidence was recognized.",
        )

    coverage = _coverage(context, evidence)
    primary = coverage.primary
    findings: list[CharacterKitEvaluationFinding] = []
    if primary.supported:
        findings.append(
            CharacterKitEvaluationFinding(
                code="KIT_PRIMARY_ROLE_SUPPORTED",
                kind="supporting_evidence",
                blocking=False,
                character_role=primary.role,
                artifact_evidence=primary.evidence,
                artifact_digests=tuple(sorted({item.artifact_digest for item in primary.evidence})),
                field_path="/combat_role_profile/primary_role",
                message=f"Kit provides canonical evidence for the primary combat role '{primary.role}'.",
            )
        )
    else:
        findings.append(
            CharacterKitEvaluationFinding(
                code="KIT_PRIMARY_ROLE_UNSUPPORTED",
                kind="direct_contradiction",
                blocking=True,
                character_role=primary.role,
                artifact_evidence=evidence,
                artifact_digests=tuple(sorted({item.artifact_digest for item in evidence})),
                field_path="/combat_role_profile/primary_role",
                message=f"Kit has no canonical evidence for the primary combat role '{primary.role}'.",
            )
        )

    for secondary in coverage.secondary:
        findings.append(
            CharacterKitEvaluationFinding(
                code=(
                    "KIT_SECONDARY_ROLE_SUPPORTED"
                    if secondary.supported
                    else "KIT_SECONDARY_ROLE_UNSUPPORTED"
                ),
                kind=("supporting_evidence" if secondary.supported else "missing_evidence"),
                blocking=False,
                character_role=secondary.role,
                artifact_evidence=secondary.evidence,
                artifact_digests=tuple(
                    sorted({item.artifact_digest for item in secondary.evidence})
                ),
                field_path="/combat_role_profile/secondary_roles",
                message=(
                    f"Kit provides canonical evidence for the secondary combat role '{secondary.role}'."
                    if secondary.supported
                    else f"Kit has no canonical evidence for the secondary combat role '{secondary.role}'."
                ),
            )
        )

    declared_set = set(declared)
    unsupported_evidence = tuple(item for item in evidence if item.role not in declared_set)
    if unsupported_evidence and not any(item.role in declared_set for item in evidence):
        findings.append(
            CharacterKitEvaluationFinding(
                code="KIT_UNSUPPORTED_ROLE_DOMINANCE",
                kind="direct_contradiction",
                blocking=True,
                character_role=primary.role,
                artifact_evidence=unsupported_evidence,
                artifact_digests=tuple(
                    sorted({item.artifact_digest for item in unsupported_evidence})
                ),
                field_path="/associations",
                message="All recognized Kit role evidence points outside the Character combat identity.",
            )
        )

    findings_tuple = tuple(findings)
    if not primary.supported:
        status: EvaluationStatus = "FAIL"
        summary = "Kit role coverage contradicts the declared primary combat identity."
    elif any(not item.supported for item in coverage.secondary):
        status = "PARTIAL"
        summary = "Kit covers the primary combat identity but not every declared secondary role."
    else:
        status = "FAIL" if any(item.blocking for item in findings_tuple) else "PASS"
        summary = (
            "Kit covers the declared combat identity."
            if status == "PASS"
            else "Kit evidence contradicts the declared combat identity."
        )
    return _result(
        status=status,
        kit=kit,
        context=context,
        coverage=coverage,
        findings=findings_tuple,
        summary=summary,
    )


evaluate_character_kit = evaluate_character_kit_role_coverage


__all__ = [
    "CHARACTER_KIT_EVALUATION_CONTEXT_VERSION",
    "CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION",
    "CharacterKitCoverage",
    "CharacterKitEvaluationContext",
    "CharacterKitEvaluationFinding",
    "CharacterKitEvaluationResult",
    "CharacterKitRoleCoverage",
    "CharacterKitRoleCoverageEvidence",
    "evaluate_character_kit",
    "evaluate_character_kit_role_coverage",
]
