"""Provider-free Hybrid Semantic IR pipeline, diagnostics, and dry-run identity."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from character_skill.contract import parse_candidate
from character_skill.evaluation import evaluate
from character_skill.models import ProtocolSkillKitCandidate, SkillValidationReport

from ..compiler import (
    DEFAULT_MAPPING_REGISTRY,
    SemanticMappingRegistry,
    SkillKitCompilerError,
    compile_skill_semantic_ir,
    validate_reference_integrity,
)
from ..semantic_ir import (
    SemanticIRShapeError,
    SemanticIRValidationError,
    ValidatedSkillSemanticIR,
    parse_semantic_ir,
    validate_skill_semantic_ir,
)
from .contract import ModelFacingRequest, build_model_facing_request
from .projection import HybridGenerationContext

HYBRID_EVIDENCE_VERSION = "character-skill-s2-hybrid-ir-shadow/0.1.0"
HYBRID_EXPERIMENT = "character_skill_s2_hybrid_semantic_ir"
FIRST_FAILURE_LAYERS = (
    "PROVIDER",
    "JSON",
    "IR_PARSE",
    "IR_VALIDATION",
    "COMPILER",
    "CANONICAL_PARSER",
    "REFERENCE_INTEGRITY",
    "EVALUATOR",
)


@dataclass(frozen=True)
class HybridExperimentIdentity:
    experiment: str
    source_commit: str
    ir_schema_version: str = "semantic-skill-plan-ir/0.1.0"
    model_facing_contract_version: str = "semantic-skill-plan-ir-contract/0.1.0"
    model_facing_contract_digest: str = ""
    compiler_version: str = "skillkit-compiler/0.1.0"
    canonical_schema_version: str = "skill-kit-candidate/0.1.1"
    provider: str = "opencode_go"
    model: str = "deepseek-v4-pro"
    case_id: str = "case_13"
    timeout_seconds: int = 60
    max_transport_retries: int = 0
    target_sample_count: int = 1
    response_mode: str = "json_object"
    feature_flag: str = "OFF"
    record_only: bool = True

    def to_mapping(self) -> dict[str, object]:
        return {
            "experiment": self.experiment,
            "source_commit": self.source_commit,
            "ir_schema_version": self.ir_schema_version,
            "model_facing_contract_version": self.model_facing_contract_version,
            "model_facing_contract_digest": self.model_facing_contract_digest,
            "compiler_version": self.compiler_version,
            "canonical_schema_version": self.canonical_schema_version,
            "provider": self.provider,
            "model": self.model,
            "case_id": self.case_id,
            "timeout_seconds": self.timeout_seconds,
            "max_transport_retries": self.max_transport_retries,
            "target_sample_count": self.target_sample_count,
            "response_mode": self.response_mode,
            "feature_flag": self.feature_flag,
            "record_only": self.record_only,
        }


@dataclass(frozen=True)
class SafeIRDiagnostics:
    object_count: int = 0
    field_count: int = 0
    nesting_depth: int = 0
    semantic_enum_field_count: int = 0
    free_text_field_count: int = 0
    missing_required_count: int = 0
    unknown_field_count: int = 0
    wrong_type_count: int = 0
    invalid_semantic_value_count: int = 0
    relationship_failure_category: str | None = None

    def to_mapping(self) -> dict[str, object]:
        return {
            "object_count": self.object_count,
            "field_count": self.field_count,
            "nesting_depth": self.nesting_depth,
            "semantic_enum_field_count": self.semantic_enum_field_count,
            "free_text_field_count": self.free_text_field_count,
            "missing_required_count": self.missing_required_count,
            "unknown_field_count": self.unknown_field_count,
            "wrong_type_count": self.wrong_type_count,
            "invalid_semantic_value_count": self.invalid_semantic_value_count,
            "relationship_failure_category": self.relationship_failure_category,
        }


@dataclass(frozen=True)
class HybridEvidence:
    identity: HybridExperimentIdentity
    request_metrics: Mapping[str, int]
    first_failure_layer: str | None
    failure_code: str | None
    principal_verdict: str
    fake_provider_called: bool
    fake_transport_attempts: int
    parser_invoked: bool
    evaluator_invoked: bool
    evaluator_outcome: str
    semantic_ir_digest: str | None
    candidate_digest: str | None
    diagnostics: SafeIRDiagnostics
    raw_ir_stored: bool = False
    raw_prompt_stored: bool = False
    raw_response_stored: bool = False
    secrets_detected: bool = False

    def to_mapping(self) -> dict[str, object]:
        """Serialize a positive allowlist only; never dump internal objects."""

        return {
            "evidence_version": HYBRID_EVIDENCE_VERSION,
            "identity": self.identity.to_mapping(),
            "request_metrics": dict(self.request_metrics),
            "first_failure_layer": self.first_failure_layer,
            "failure_code": self.failure_code,
            "principal_verdict": self.principal_verdict,
            "fake_provider_called": self.fake_provider_called,
            "fake_transport_attempts": self.fake_transport_attempts,
            "parser_invoked": self.parser_invoked,
            "evaluator_invoked": self.evaluator_invoked,
            "evaluator_outcome": self.evaluator_outcome,
            "semantic_ir_digest": self.semantic_ir_digest,
            "candidate_digest": self.candidate_digest,
            "diagnostics": self.diagnostics.to_mapping(),
            "sanitization": {
                "raw_ir_stored": self.raw_ir_stored,
                "raw_prompt_stored": self.raw_prompt_stored,
                "raw_response_stored": self.raw_response_stored,
                "secrets_detected": self.secrets_detected,
            },
        }


@dataclass(frozen=True)
class FakePipelineResult:
    evidence: HybridEvidence
    candidate: ProtocolSkillKitCandidate | None = field(default=None, repr=False)
    report: SkillValidationReport | None = field(default=None, repr=False)


class FakeProvider:
    """An in-memory adapter; construction/calls are never real provider calls."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = 0

    def complete(self, request_text: str) -> object:
        del request_text
        self.calls += 1
        return self.response


def _shape_diagnostics(value: object) -> SafeIRDiagnostics:
    objects = fields = depth = enum_fields = free_text = 0

    def visit(node: object, level: int) -> None:
        nonlocal objects, fields, depth, enum_fields, free_text
        depth = max(depth, level)
        if isinstance(node, dict):
            objects += 1
            fields += len(node)
            for key, child in node.items():
                if key in {"actor", "event", "intent", "relation", "mode", "role", "centrality"}:
                    enum_fields += 1
                if key in {"ability_name", "summary", "description", "qualifier"}:
                    free_text += 1
                visit(child, level + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, level + 1)

    if isinstance(value, (dict, list)):
        visit(value, 1)
    return SafeIRDiagnostics(objects, fields, depth, enum_fields, free_text)


def _request_metrics(request: ModelFacingRequest) -> Mapping[str, int]:
    return MappingProxyType(request.metrics.to_mapping())


def _identity(repo_root: Path, contract_digest: str) -> HybridExperimentIdentity:
    source_commit = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
    ).strip()
    return HybridExperimentIdentity(HYBRID_EXPERIMENT, source_commit, model_facing_contract_digest=contract_digest)


def _parse_json(response: object) -> object:
    if isinstance(response, str):
        return json.loads(response)
    if isinstance(response, Mapping):
        return json.loads(json.dumps(response, ensure_ascii=False))
    raise ValueError("response must be a JSON object")


def _failure(
    identity: HybridExperimentIdentity,
    request: ModelFacingRequest,
    provider: FakeProvider,
    layer: str,
    code: str,
    diagnostics: SafeIRDiagnostics,
    *,
    parser_invoked: bool = False,
    evaluator_invoked: bool = False,
    evaluator_outcome: str = "NOT_RUN",
    semantic_ir_digest: str | None = None,
    candidate_digest: str | None = None,
    principal_verdict: str = "FAIL",
    relationship_failure_category: str | None = None,
) -> FakePipelineResult:
    if layer not in FIRST_FAILURE_LAYERS:
        raise ValueError("unknown first failure layer")
    if relationship_failure_category is not None:
        diagnostics = SafeIRDiagnostics(**{**diagnostics.to_mapping(), "relationship_failure_category": relationship_failure_category})
    evidence = HybridEvidence(
        identity,
        _request_metrics(request),
        layer,
        code,
        principal_verdict,
        provider.calls > 0,
        provider.calls,
        parser_invoked,
        evaluator_invoked,
        evaluator_outcome,
        semantic_ir_digest,
        candidate_digest,
        diagnostics,
    )
    return FakePipelineResult(evidence)


def run_fake_pipeline(
    provider: FakeProvider,
    context: HybridGenerationContext,
    evaluation_context: Mapping[str, object],
    *,
    repo_root: Path | str,
    compiler_registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
) -> FakePipelineResult:
    """Run every H3 layer using an in-memory provider and safe evidence only."""

    request = build_model_facing_request(context)
    identity = _identity(Path(repo_root), request.contract.digest)
    response = provider.complete(request.text)
    try:
        payload = _parse_json(response)
    except (ValueError, json.JSONDecodeError):
        return _failure(identity, request, provider, "JSON", "JSON_MALFORMED", SafeIRDiagnostics())
    diagnostics = _shape_diagnostics(payload)
    try:
        ir = parse_semantic_ir(payload)
    except SemanticIRShapeError as error:
        code = {
            "MISSING_FIELD": "IR_MISSING_REQUIRED_FIELD",
            "UNKNOWN_FIELD": "IR_UNKNOWN_FIELD",
            "IR_INVALID": "IR_WRONG_TYPE",
        }.get(error.code, "IR_OTHER_PARSE_FAILURE")
        return _failure(identity, request, provider, "IR_PARSE", code, diagnostics)
    try:
        validated = validate_skill_semantic_ir(ir)
    except SemanticIRValidationError as error:
        code = {
            "UNSUPPORTED_SEMANTIC_MAPPING": "IR_UNSUPPORTED_MAPPING",
            "IR_INVALID": "IR_INVALID_SEMANTIC_VALUE",
        }.get(error.code, "IR_OTHER_VALIDATION_FAILURE")
        relationship = "INVALID_RELATIONSHIP" if "feedback" in error.path and "actor" in error.path else None
        return _failure(
            identity,
            request,
            provider,
            "IR_VALIDATION",
            code,
            diagnostics,
            relationship_failure_category=relationship,
        )
    assert isinstance(validated, ValidatedSkillSemanticIR)
    try:
        compiled = compile_skill_semantic_ir(validated, registry=compiler_registry)
    except SkillKitCompilerError as error:
        return _failure(identity, request, provider, "COMPILER", error.code, diagnostics, semantic_ir_digest=validated.digest)
    candidate_digest = compiled.candidate_digest
    try:
        parsed = parse_candidate(compiled.candidate.to_mapping())
    except Exception:
        return _failure(
            identity,
            request,
            provider,
            "CANONICAL_PARSER",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
        )
    if not isinstance(parsed, ProtocolSkillKitCandidate):
        return _failure(
            identity,
            request,
            provider,
            "CANONICAL_PARSER",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
        )
    try:
        validate_reference_integrity(parsed)
    except SkillKitCompilerError:
        return _failure(
            identity,
            request,
            provider,
            "REFERENCE_INTEGRITY",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
        )
    report = evaluate(parsed, evaluation_context)
    verdict = "PASS" if report.outcome == "PASS" else "EVALUATOR_" + report.outcome
    return FakePipelineResult(
        HybridEvidence(
            identity,
            _request_metrics(request),
            "EVALUATOR" if report.outcome != "PASS" else None,
            None if report.outcome == "PASS" else report.outcome,
            verdict,
            provider.calls > 0,
            provider.calls,
            True,
            True,
            report.outcome,
            validated.digest,
            candidate_digest,
            diagnostics,
        ),
        parsed,
        report,
    )


def validate_hybrid_evidence(payload: Mapping[str, object]) -> None:
    """Validate the safe positive-allowlist evidence shape."""

    required = {
        "evidence_version",
        "identity",
        "request_metrics",
        "first_failure_layer",
        "failure_code",
        "principal_verdict",
        "fake_provider_called",
        "fake_transport_attempts",
        "parser_invoked",
        "evaluator_invoked",
        "evaluator_outcome",
        "semantic_ir_digest",
        "candidate_digest",
        "diagnostics",
        "sanitization",
    }
    if set(payload) != required:
        raise ValueError("HYBRID_EVIDENCE_SCHEMA_INVALID")
    if payload["evidence_version"] != HYBRID_EVIDENCE_VERSION:
        raise ValueError("HYBRID_EVIDENCE_VERSION_INVALID")
    layer = payload["first_failure_layer"]
    if layer is not None and layer not in FIRST_FAILURE_LAYERS:
        raise ValueError("HYBRID_FIRST_FAILURE_LAYER_INVALID")
    if payload["fake_transport_attempts"] not in {0, 1}:
        raise ValueError("HYBRID_TRANSPORT_ATTEMPTS_INVALID")
    sanitization = payload["sanitization"]
    if not isinstance(sanitization, Mapping) or sanitization != {
        "raw_ir_stored": False,
        "raw_prompt_stored": False,
        "raw_response_stored": False,
        "secrets_detected": False,
    }:
        raise ValueError("HYBRID_SANITIZATION_INVALID")


def write_evidence_atomic(evidence: HybridEvidence | Mapping[str, object], path: Path | str) -> Path:
    """Validate then atomically write one safe evidence document."""

    payload = evidence.to_mapping() if isinstance(evidence, HybridEvidence) else dict(evidence)
    validate_hybrid_evidence(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


class HybridSemanticIRRunner:
    """Independent H3 cohort planner with a provider-free dry-run seam."""

    def __init__(
        self,
        repo_root: Path | str,
        context: HybridGenerationContext,
        *,
        target_sample_count: int = 1,
        existing_sample_indexes: tuple[int, ...] = (),
    ) -> None:
        if target_sample_count != 1:
            raise ValueError("H2 dry-run only supports independent N=1")
        self.repo_root = Path(repo_root)
        self.context = context
        self.target_sample_count = target_sample_count
        self.existing_sample_indexes = tuple(sorted(existing_sample_indexes))

    def dry_run(self) -> dict[str, object]:
        contract = build_model_facing_request(self.context).contract
        existing = len(self.existing_sample_indexes)
        next_index = (self.existing_sample_indexes[-1] + 1) if self.existing_sample_indexes else 1
        remaining = max(self.target_sample_count - existing, 0)
        identity = _identity(self.repo_root, contract.digest)
        return {
            "status": "dry_run_hybrid_semantic_ir",
            "identity": identity.to_mapping(),
            "target_sample_count": self.target_sample_count,
            "existing_sample_count": existing,
            "existing_sample_indexes": list(self.existing_sample_indexes),
            "next_sample_index": next_index,
            "remaining_sample_count": remaining,
            "complete": remaining == 0,
            "provider_factory_constructed": False,
            "provider_called": False,
            "transport_attempts": 0,
        }


__all__ = [
    "FIRST_FAILURE_LAYERS",
    "FakePipelineResult",
    "FakeProvider",
    "HYBRID_EVIDENCE_VERSION",
    "HYBRID_EXPERIMENT",
    "HybridEvidence",
    "HybridExperimentIdentity",
    "HybridSemanticIRRunner",
    "SafeIRDiagnostics",
    "run_fake_pipeline",
    "validate_hybrid_evidence",
    "write_evidence_atomic",
]
