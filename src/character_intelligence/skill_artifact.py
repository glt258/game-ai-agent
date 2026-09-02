"""Immutable identity and version contracts for one Skill design artifact.

This module is the application seam between the existing Skill pipeline and
future artifact lifecycle features.  It deliberately does not persist data,
own a Character, or define Character Kit semantics.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from character_skill import (
    SCHEMA_VERSION,
    ProtocolSkillKitCandidate,
    SkillFinding,
    SkillValidationReport,
    parse_candidate,
)
from character_skill.context import VALIDATOR_CONTRACT

from .character_skill_alignment import (
    CHARACTER_SKILL_ALIGNMENT_VERSION,
    ArtifactBindingError,
    CharacterSkillAlignmentResult,
)
from .character_skill_projection import (
    CHARACTER_SKILL_PROJECTION_VERSION,
    CharacterSkillDesignContext,
)
from .compiler import COMPILER_VERSION_V2, CompilerProvenance, CompilerProvenanceEntry
from .semantic_ir import (
    SEMANTIC_IR_V2_VERSION,
    SkillSemanticIR,
    SkillSemanticIRV2,
    ValidatedSkillSemanticIR,
    parse_semantic_ir,
    validate_skill_semantic_ir,
)

ARTIFACT_CONTRACT_VERSION = "skill-design-artifact/0.1.0"
CHARACTER_SKILL_BINDING_CONTRACT_VERSION = "character-skill-artifact-binding/0.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SemanticSource = SkillSemanticIR | SkillSemanticIRV2


class ArtifactContractError(ValueError):
    """Stable fail-closed error for malformed artifact contracts."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class SkillArtifactIdentity:
    """Content identity for the canonical Skill artifact only."""

    artifact_digest: str
    canonical_schema_version: str
    artifact_kind: Literal["skill_design"] = "skill_design"

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.artifact_digest):
            raise ArtifactContractError("INVALID_ARTIFACT_DIGEST", "artifact_digest must be SHA-256")
        if not self.canonical_schema_version.strip():
            raise ArtifactContractError(
                "INVALID_CANONICAL_SCHEMA_VERSION",
                "canonical schema version must be non-empty",
            )
        if self.artifact_kind != "skill_design":
            raise ArtifactContractError("UNSUPPORTED_ARTIFACT_KIND", "only skill_design is supported")

    def to_mapping(self) -> dict[str, str]:
        return {
            "artifact_digest": self.artifact_digest,
            "canonical_schema_version": self.canonical_schema_version,
            "artifact_kind": self.artifact_kind,
        }


@dataclass(frozen=True)
class SkillArtifactVersionMetadata:
    """Versions used by one historical artifact production/evaluation run."""

    semantic_ir_schema_version: str
    compiler_version: str
    canonical_skillkit_schema_version: str
    skill_evaluator_version: str
    character_alignment_version: str | None = None
    character_context_projection_version: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "semantic_ir_schema_version",
            "compiler_version",
            "canonical_skillkit_schema_version",
            "skill_evaluator_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ArtifactContractError("INVALID_VERSION_METADATA", f"{name} must be non-empty")
        for name in (
            "character_alignment_version",
            "character_context_projection_version",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ArtifactContractError("INVALID_VERSION_METADATA", f"{name} must be non-empty or null")

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "semantic_ir_schema_version": self.semantic_ir_schema_version,
            "compiler_version": self.compiler_version,
            "canonical_skillkit_schema_version": self.canonical_skillkit_schema_version,
            "skill_evaluator_version": self.skill_evaluator_version,
            "character_alignment_version": self.character_alignment_version,
            "character_context_projection_version": self.character_context_projection_version,
        }

    @classmethod
    def from_mapping(cls, value: object) -> "SkillArtifactVersionMetadata":
        if not isinstance(value, Mapping):
            raise ArtifactContractError("INVALID_VERSION_METADATA", "versions must be an object")
        value = dict(value)
        expected = {
            "semantic_ir_schema_version",
            "compiler_version",
            "canonical_skillkit_schema_version",
            "skill_evaluator_version",
            "character_alignment_version",
            "character_context_projection_version",
        }
        if set(value) != expected:
            raise ArtifactContractError("INVALID_VERSION_METADATA", "versions fields are not exact")
        return cls(**value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class SkillArtifactProvenance:
    """Safe execution and compiler provenance; never raw provider material."""

    compiler_provenance: CompilerProvenance
    run_id: str | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.compiler_provenance, CompilerProvenance):
            raise TypeError("compiler_provenance must be CompilerProvenance")
        for name in ("run_id", "provider", "model"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ArtifactContractError("INVALID_PROVENANCE", f"{name} must be non-empty or null")

    def to_mapping(self) -> dict[str, object]:
        return {
            "compiler_provenance": self.compiler_provenance.to_mapping(),
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
        }


class ArtifactDriftStatus(str, Enum):
    CURRENT_COMPATIBLE = "CURRENT_COMPATIBLE"
    REEVALUATION_RECOMMENDED = "REEVALUATION_RECOMMENDED"
    REALIGNMENT_RECOMMENDED = "REALIGNMENT_RECOMMENDED"
    RECOMPILE_REQUIRED = "RECOMPILE_REQUIRED"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    CONTEXT_PROJECTION_DRIFT = "CONTEXT_PROJECTION_DRIFT"


@dataclass(frozen=True)
class ArtifactDriftFinding:
    code: str
    detail: str

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class ArtifactDriftInspection:
    status: ArtifactDriftStatus
    findings: tuple[ArtifactDriftFinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "findings": [finding.to_mapping() for finding in self.findings],
        }


@dataclass(frozen=True)
class SkillDesignArtifact:
    """Immutable standalone-compatible Skill design artifact envelope."""

    artifact_contract_version: str
    identity: SkillArtifactIdentity
    versions: SkillArtifactVersionMetadata
    semantic_source: SemanticSource
    canonical_artifact: ProtocolSkillKitCandidate
    original_evaluation: SkillValidationReport
    provenance: SkillArtifactProvenance

    def __post_init__(self) -> None:
        if self.artifact_contract_version != ARTIFACT_CONTRACT_VERSION:
            raise ArtifactContractError(
                "ARTIFACT_CONTRACT_VERSION_UNSUPPORTED",
                "artifact contract version is not supported",
            )
        if not isinstance(self.identity, SkillArtifactIdentity):
            raise TypeError("identity must be SkillArtifactIdentity")
        if not isinstance(self.versions, SkillArtifactVersionMetadata):
            raise TypeError("versions must be SkillArtifactVersionMetadata")
        if not isinstance(self.semantic_source, (SkillSemanticIR, SkillSemanticIRV2)):
            raise TypeError("semantic_source must be Semantic IR")
        if not isinstance(self.canonical_artifact, ProtocolSkillKitCandidate):
            raise TypeError("canonical_artifact must be ProtocolSkillKitCandidate")
        if not isinstance(self.original_evaluation, SkillValidationReport):
            raise TypeError("original_evaluation must be SkillValidationReport")
        if not isinstance(self.provenance, SkillArtifactProvenance):
            raise TypeError("provenance must be SkillArtifactProvenance")
        if self.identity.artifact_digest != self.canonical_artifact.digest:
            raise ArtifactBindingError(
                "ARTIFACT_DIGEST_MISMATCH",
                "identity is not bound to canonical artifact",
            )
        if self.identity.canonical_schema_version != self.canonical_artifact.schema_version:
            raise ArtifactBindingError(
                "CANONICAL_SCHEMA_VERSION_MISMATCH",
                "identity schema version is not bound to canonical artifact",
            )
        if self.versions.semantic_ir_schema_version != self.semantic_source.ir_version:
            raise ArtifactBindingError(
                "SEMANTIC_IR_VERSION_MISMATCH",
                "version metadata is not bound to semantic source",
            )
        if self.versions.compiler_version != self.provenance.compiler_provenance.compiler_version:
            raise ArtifactBindingError(
                "COMPILER_VERSION_MISMATCH",
                "version metadata is not bound to compiler provenance",
            )
        if self.versions.canonical_skillkit_schema_version != self.canonical_artifact.schema_version:
            raise ArtifactBindingError(
                "CANONICAL_SCHEMA_VERSION_MISMATCH",
                "version metadata is not bound to canonical artifact",
            )
        if self.original_evaluation.candidate_digest != self.canonical_artifact.digest:
            raise ArtifactBindingError(
                "EVALUATION_CANDIDATE_DIGEST_MISMATCH",
                "evaluation is not bound to canonical artifact",
            )
        if (
            self.versions.character_alignment_version is not None
            and self.versions.character_context_projection_version is None
        ):
            raise ArtifactBindingError(
                "CHARACTER_VERSION_BINDING_INCOMPLETE",
                "alignment version requires Character projection version",
            )

    @property
    def artifact_digest(self) -> str:
        return self.identity.artifact_digest

    @property
    def semantic_source_digest(self) -> str:
        return self.semantic_source.digest

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_contract_version": self.artifact_contract_version,
            "identity": self.identity.to_mapping(),
            "versions": self.versions.to_mapping(),
            "semantic_source": self.semantic_source.to_mapping(),
            "semantic_source_digest": self.semantic_source_digest,
            "canonical_artifact": self.canonical_artifact.to_mapping(),
            "original_evaluation": self.original_evaluation.to_mapping(),
            "provenance": self.provenance.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object) -> "SkillDesignArtifact":
        payload = _mapping(value, "artifact")
        _exact_keys(
            payload,
            {
                "artifact_contract_version",
                "identity",
                "versions",
                "semantic_source",
                "semantic_source_digest",
                "canonical_artifact",
                "original_evaluation",
                "provenance",
            },
            "artifact",
        )
        contract_version = _string(payload["artifact_contract_version"], "artifact/artifact_contract_version")
        if contract_version != ARTIFACT_CONTRACT_VERSION:
            raise ArtifactContractError(
                "ARTIFACT_CONTRACT_VERSION_UNSUPPORTED",
                "artifact contract version is not supported",
            )
        source = parse_semantic_ir(payload["semantic_source"])
        validated_source = validate_skill_semantic_ir(source)
        source_digest = _string(payload["semantic_source_digest"], "artifact/semantic_source_digest")
        if source_digest != validated_source.digest:
            raise ArtifactBindingError("SEMANTIC_SOURCE_DIGEST_MISMATCH", "semantic source digest mismatch")
        candidate_value = parse_candidate(_mapping(payload["canonical_artifact"], "artifact/canonical_artifact"))
        if not isinstance(candidate_value, ProtocolSkillKitCandidate):
            raise ArtifactContractError("CANONICAL_ARTIFACT_INVALID", "legacy Skill value is not allowed")
        return cls(
            contract_version,
            _identity_from_mapping(payload["identity"]),
            SkillArtifactVersionMetadata.from_mapping(payload["versions"]),
            validated_source.value,
            candidate_value,
            _evaluation_from_mapping(payload["original_evaluation"]),
            _provenance_from_mapping(payload["provenance"]),
        )


@dataclass(frozen=True)
class CharacterSkillArtifactBinding:
    """Character relationship metadata kept outside the standalone artifact."""

    artifact_digest: str
    source_context_fingerprint: str
    alignment: CharacterSkillAlignmentResult
    alignment_version: str
    character_context_projection_version: str
    binding_contract_version: str = CHARACTER_SKILL_BINDING_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.binding_contract_version != CHARACTER_SKILL_BINDING_CONTRACT_VERSION:
            raise ArtifactContractError("BINDING_CONTRACT_VERSION_UNSUPPORTED", "unsupported binding version")
        if not _SHA256_RE.fullmatch(self.artifact_digest):
            raise ArtifactContractError("INVALID_ARTIFACT_DIGEST", "binding digest must be SHA-256")
        if not _SHA256_RE.fullmatch(self.source_context_fingerprint):
            raise ArtifactContractError("INVALID_CONTEXT_FINGERPRINT", "binding fingerprint must be SHA-256")
        if not isinstance(self.alignment, CharacterSkillAlignmentResult):
            raise TypeError("alignment must be CharacterSkillAlignmentResult")
        if self.alignment_version != CHARACTER_SKILL_ALIGNMENT_VERSION:
            raise ArtifactContractError("ALIGNMENT_VERSION_UNSUPPORTED", "unsupported alignment version")
        if not self.character_context_projection_version.strip():
            raise ArtifactContractError("INVALID_VERSION_METADATA", "projection version must be non-empty")

    def freshness_for(self, current_context_fingerprint: str) -> Literal["current", "stale"]:
        """Derive freshness without storing it in the binding."""

        return "current" if self.source_context_fingerprint == current_context_fingerprint else "stale"

    def to_mapping(self) -> dict[str, object]:
        return {
            "binding_contract_version": self.binding_contract_version,
            "artifact_digest": self.artifact_digest,
            "source_context_fingerprint": self.source_context_fingerprint,
            "alignment": self.alignment.to_mapping(),
            "alignment_version": self.alignment_version,
            "character_context_projection_version": self.character_context_projection_version,
        }


def build_skill_design_artifact(
    semantic_source: ValidatedSkillSemanticIR | SemanticSource,
    canonical_artifact: ProtocolSkillKitCandidate,
    evaluation: SkillValidationReport,
    compiler_provenance: CompilerProvenance,
    *,
    run_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    alignment: CharacterSkillAlignmentResult | None = None,
    character_context: CharacterSkillDesignContext | None = None,
) -> SkillDesignArtifact:
    """Build one verified artifact from the existing pipeline outputs."""

    source = semantic_source.value if isinstance(semantic_source, ValidatedSkillSemanticIR) else semantic_source
    if alignment is not None and character_context is None:
        raise ArtifactBindingError("CHARACTER_VERSION_BINDING_INCOMPLETE", "alignment requires Character context")
    if character_context is not None and alignment is None:
        raise ArtifactBindingError("CHARACTER_VERSION_BINDING_INCOMPLETE", "Character context requires alignment")
    versions = SkillArtifactVersionMetadata(
        semantic_ir_schema_version=source.ir_version,
        compiler_version=compiler_provenance.compiler_version,
        canonical_skillkit_schema_version=canonical_artifact.schema_version,
        skill_evaluator_version=VALIDATOR_CONTRACT,
        character_alignment_version=(CHARACTER_SKILL_ALIGNMENT_VERSION if alignment is not None else None),
        character_context_projection_version=(character_context.projection_version if character_context is not None else None),
    )
    artifact = SkillDesignArtifact(
        ARTIFACT_CONTRACT_VERSION,
        SkillArtifactIdentity(canonical_artifact.digest, canonical_artifact.schema_version),
        versions,
        source,
        canonical_artifact,
        evaluation,
        SkillArtifactProvenance(
            compiler_provenance,
            run_id=run_id,
            provider=provider,
            model=model,
        ),
    )
    if alignment is not None and character_context is not None:
        _verify_alignment_binding(artifact, character_context, alignment)
    return artifact


def build_skill_design_artifact_from_pipeline_result(
    result: object,
    *,
    alignment: CharacterSkillAlignmentResult | None = None,
    character_context: CharacterSkillDesignContext | None = None,
) -> SkillDesignArtifact:
    """Build an artifact from the existing pipeline result without re-running work."""

    candidate = getattr(result, "candidate", None)
    evaluation = getattr(result, "report", None)
    semantic_source = getattr(result, "validated_ir", None)
    compiler_provenance = getattr(result, "compiler_provenance", None)
    if (
        candidate is None
        or evaluation is None
        or semantic_source is None
        or compiler_provenance is None
    ):
        raise ArtifactContractError(
            "PIPELINE_ARTIFACT_INCOMPLETE",
            "pipeline result does not contain all artifact inputs",
        )
    evidence = getattr(result, "evidence", None)
    identity = getattr(evidence, "identity", None)
    return build_skill_design_artifact(
        semantic_source,
        candidate,
        evaluation,
        compiler_provenance,
        run_id=getattr(evidence, "run_id", None),
        provider=getattr(identity, "provider", None),
        model=getattr(identity, "model", None),
        alignment=alignment,
        character_context=character_context,
    )


def build_character_skill_artifact_binding(
    artifact: SkillDesignArtifact,
    character_context: CharacterSkillDesignContext,
    alignment: CharacterSkillAlignmentResult,
) -> CharacterSkillArtifactBinding:
    """Build a checked Character relationship without adding ownership to artifact."""

    _verify_alignment_binding(artifact, character_context, alignment)
    return CharacterSkillArtifactBinding(
        artifact_digest=artifact.artifact_digest,
        source_context_fingerprint=character_context.source_context_fingerprint,
        alignment=alignment,
        alignment_version=artifact.versions.character_alignment_version or CHARACTER_SKILL_ALIGNMENT_VERSION,
        character_context_projection_version=(
            artifact.versions.character_context_projection_version
            or character_context.projection_version
        ),
    )


def inspect_skill_artifact_compatibility(
    artifact_versions: SkillArtifactVersionMetadata,
    current_versions: SkillArtifactVersionMetadata,
) -> ArtifactDriftInspection:
    """Compare version metadata only; never provider-call or recompute anything."""

    findings: list[ArtifactDriftFinding] = []
    if artifact_versions.canonical_skillkit_schema_version != current_versions.canonical_skillkit_schema_version:
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_CANONICAL_SCHEMA_VERSION_UNSUPPORTED",
                "canonical SkillKit schema version differs",
            )
        )
    if artifact_versions.semantic_ir_schema_version != current_versions.semantic_ir_schema_version:
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_IR_VERSION_DRIFT",
                "semantic source version differs",
            )
        )
    if artifact_versions.compiler_version != current_versions.compiler_version:
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_COMPILER_VERSION_DRIFT",
                "canonical artifact was compiled by a different compiler version",
            )
        )
    if artifact_versions.skill_evaluator_version != current_versions.skill_evaluator_version:
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_EVALUATOR_VERSION_DRIFT",
                "historical evaluation used a different evaluator version",
            )
        )
    if (
        artifact_versions.character_alignment_version is not None
        and current_versions.character_alignment_version is not None
        and artifact_versions.character_alignment_version != current_versions.character_alignment_version
    ):
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_ALIGNMENT_VERSION_DRIFT",
                "historical alignment used a different alignment version",
            )
        )
    if (
        artifact_versions.character_context_projection_version is not None
        and current_versions.character_context_projection_version is not None
        and artifact_versions.character_context_projection_version
        != current_versions.character_context_projection_version
    ):
        findings.append(
            ArtifactDriftFinding(
                "ARTIFACT_PROJECTION_VERSION_DRIFT",
                "historical Character context projection version differs",
            )
        )
    if not findings:
        return ArtifactDriftInspection(ArtifactDriftStatus.CURRENT_COMPATIBLE)
    codes = {finding.code for finding in findings}
    if "ARTIFACT_CANONICAL_SCHEMA_VERSION_UNSUPPORTED" in codes:
        status = ArtifactDriftStatus.UNSUPPORTED_VERSION
    elif "ARTIFACT_IR_VERSION_DRIFT" in codes or "ARTIFACT_COMPILER_VERSION_DRIFT" in codes:
        status = ArtifactDriftStatus.RECOMPILE_REQUIRED
    elif "ARTIFACT_PROJECTION_VERSION_DRIFT" in codes:
        status = ArtifactDriftStatus.CONTEXT_PROJECTION_DRIFT
    elif "ARTIFACT_ALIGNMENT_VERSION_DRIFT" in codes:
        status = ArtifactDriftStatus.REALIGNMENT_RECOMMENDED
    else:
        status = ArtifactDriftStatus.REEVALUATION_RECOMMENDED
    return ArtifactDriftInspection(status, tuple(findings))


def current_skill_artifact_versions() -> SkillArtifactVersionMetadata:
    """Return current runtime versions for provider-free drift inspection."""

    return SkillArtifactVersionMetadata(
        semantic_ir_schema_version=SEMANTIC_IR_V2_VERSION,
        compiler_version=COMPILER_VERSION_V2,
        canonical_skillkit_schema_version=SCHEMA_VERSION,
        skill_evaluator_version=VALIDATOR_CONTRACT,
        character_alignment_version=CHARACTER_SKILL_ALIGNMENT_VERSION,
        character_context_projection_version=CHARACTER_SKILL_PROJECTION_VERSION,
    )


def _verify_alignment_binding(
    artifact: SkillDesignArtifact,
    character_context: CharacterSkillDesignContext,
    alignment: CharacterSkillAlignmentResult,
) -> None:
    if alignment.artifact_digest != artifact.artifact_digest:
        raise ArtifactBindingError("ARTIFACT_DIGEST_MISMATCH", "alignment is not bound to artifact")
    if alignment.source_context_fingerprint != character_context.source_context_fingerprint:
        raise ArtifactBindingError(
            "SOURCE_CONTEXT_FINGERPRINT_MISMATCH",
            "alignment is not bound to Character context",
        )


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ArtifactContractError("TYPE_MISMATCH", f"{path} must be an object")
    return dict(value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise ArtifactContractError("TYPE_MISMATCH", f"{path} must be a string")
    return value


def _bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ArtifactContractError("TYPE_MISMATCH", f"{path} must be a boolean")
    return value


def _exact_keys(payload: dict[str, object], expected: set[str], path: str) -> None:
    if set(payload) != expected:
        raise ArtifactContractError("UNKNOWN_OR_MISSING_FIELD", f"{path} fields are not exact")


def _identity_from_mapping(value: object) -> SkillArtifactIdentity:
    payload = _mapping(value, "artifact/identity")
    _exact_keys(payload, {"artifact_digest", "canonical_schema_version", "artifact_kind"}, "artifact/identity")
    return SkillArtifactIdentity(
        _string(payload["artifact_digest"], "artifact/identity/artifact_digest"),
        _string(payload["canonical_schema_version"], "artifact/identity/canonical_schema_version"),
        _string(payload["artifact_kind"], "artifact/identity/artifact_kind"),  # type: ignore[arg-type]
    )


def _evaluation_from_mapping(value: object) -> SkillValidationReport:
    payload = _mapping(value, "artifact/original_evaluation")
    _exact_keys(
        payload,
        {
            "outcome",
            "blocking",
            "repair_allowed",
            "findings",
            "candidate_digest",
            "context_digest",
            "report_digest",
            "base_digest",
            "finding_codes",
        },
        "artifact/original_evaluation",
    )
    findings_value = payload["findings"]
    if not isinstance(findings_value, list):
        raise ArtifactContractError("TYPE_MISMATCH", "evaluation findings must be an array")
    findings: list[SkillFinding] = []
    for index, item in enumerate(findings_value):
        row = _mapping(item, f"artifact/original_evaluation/findings/{index}")
        _exact_keys(
            row,
            {"code", "field_path", "blocking", "repairable", "evidence_refs", "authorized_paths", "priority"},
            f"artifact/original_evaluation/findings/{index}",
        )
        evidence_refs = row["evidence_refs"]
        authorized_paths = row["authorized_paths"]
        if not isinstance(evidence_refs, list) or not isinstance(authorized_paths, list):
            raise ArtifactContractError("TYPE_MISMATCH", "finding references must be arrays")
        finding = SkillFinding(
            _string(row["code"], "finding/code"),
            _string(row["field_path"], "finding/field_path"),
            _bool(row["blocking"], "finding/blocking"),
            _bool(row["repairable"], "finding/repairable"),
            tuple(_string(item, "finding/evidence_refs") for item in evidence_refs),
            tuple(_string(item, "finding/authorized_paths") for item in authorized_paths),
        )
        if finding.priority != row["priority"]:
            raise ArtifactBindingError("EVALUATION_PRIORITY_MISMATCH", "finding priority is not canonical")
        findings.append(finding)
    result = SkillValidationReport(
        _string(payload["outcome"], "evaluation/outcome"),  # type: ignore[arg-type]
        _bool(payload["blocking"], "evaluation/blocking"),
        _bool(payload["repair_allowed"], "evaluation/repair_allowed"),
        tuple(findings),
        _string(payload["candidate_digest"], "evaluation/candidate_digest"),
        _string(payload["context_digest"], "evaluation/context_digest"),
        _string(payload["report_digest"], "evaluation/report_digest"),
    )
    if result.base_digest != payload["base_digest"] or list(result.finding_codes) != payload["finding_codes"]:
        raise ArtifactBindingError("EVALUATION_DERIVED_FIELDS_MISMATCH", "evaluation derived fields mismatch")
    return result


def _provenance_from_mapping(value: object) -> SkillArtifactProvenance:
    payload = _mapping(value, "artifact/provenance")
    _exact_keys(payload, {"compiler_provenance", "run_id", "provider", "model"}, "artifact/provenance")
    compiler_payload = _mapping(payload["compiler_provenance"], "artifact/provenance/compiler_provenance")
    _exact_keys(compiler_payload, {"compiler_version", "entries"}, "artifact/provenance/compiler_provenance")
    entries_value = compiler_payload["entries"]
    if not isinstance(entries_value, list):
        raise ArtifactContractError("TYPE_MISMATCH", "compiler provenance entries must be an array")
    entries: list[CompilerProvenanceEntry] = []
    for index, item in enumerate(entries_value):
        row = _mapping(item, f"artifact/provenance/compiler_provenance/entries/{index}")
        allowed = {"canonical_path", "source_kind", "source_path", "rule_id"}
        if set(row) - allowed or not {"canonical_path", "source_kind"}.issubset(row):
            raise ArtifactContractError("INVALID_PROVENANCE", "compiler provenance entry fields are invalid")
        entries.append(
            CompilerProvenanceEntry(
                _string(row["canonical_path"], "provenance/canonical_path"),
                _string(row["source_kind"], "provenance/source_kind"),
                _string(row["source_path"], "provenance/source_path") if row.get("source_path") is not None else None,
                _string(row["rule_id"], "provenance/rule_id") if row.get("rule_id") is not None else None,
            )
        )
    return SkillArtifactProvenance(
        CompilerProvenance(_string(compiler_payload["compiler_version"], "provenance/compiler_version"), tuple(entries)),
        _optional_string(payload["run_id"], "provenance/run_id"),
        _optional_string(payload["provider"], "provenance/provider"),
        _optional_string(payload["model"], "provenance/model"),
    )


def _optional_string(value: object, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ArtifactContractError("TYPE_MISMATCH", f"{path} must be a string or null")
    return value


__all__ = [
    "ARTIFACT_CONTRACT_VERSION",
    "CHARACTER_SKILL_BINDING_CONTRACT_VERSION",
    "ArtifactBindingError",
    "ArtifactContractError",
    "ArtifactDriftFinding",
    "ArtifactDriftInspection",
    "ArtifactDriftStatus",
    "CharacterSkillArtifactBinding",
    "SkillArtifactIdentity",
    "SkillArtifactProvenance",
    "SkillArtifactVersionMetadata",
    "SkillDesignArtifact",
    "build_character_skill_artifact_binding",
    "build_skill_design_artifact",
    "build_skill_design_artifact_from_pipeline_result",
    "current_skill_artifact_versions",
    "inspect_skill_artifact_compatibility",
]
