"""Provider-free Hybrid Semantic IR pipeline, diagnostics, and dry-run identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Protocol, runtime_checkable

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
from .contract import (
    MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED,
    ModelFacingRequest,
    build_model_facing_request,
)
from .diagnostics import SafeEvaluatorDiagnostics, adapt_skill_validation_report
from .projection import (
    CONTEXT_PROJECTION_VERSION,
    HybridGenerationContext,
)

HYBRID_EVIDENCE_VERSION_V020 = "character-skill-s2-hybrid-ir-shadow/0.2.0"
HYBRID_EVIDENCE_VERSION = "character-skill-s2-hybrid-ir-shadow/0.3.0"
HYBRID_EXPERIMENT = "character_skill_s2_hybrid_semantic_ir"
HYBRID_RUN_ID_PREFIX = "cs-s2-hybrid-semantic-ir-v1"
HYBRID_REPLICATION_COHORT_PURPOSE = "same-config-replication"
HYBRID_DEFAULT_EVIDENCE_RELATIVE_PATH = "evals/results/character_skill_s2_hybrid_ir_run_01_v0.3.0.json"
HYBRID_DEFAULT_TEMP_RELATIVE_PATH = "evals/results/.character_skill_s2_hybrid_ir_run_01_v0.3.0.json.tmp"
HYBRID_FROZEN_REQUEST_CHARS = 1032
HYBRID_FROZEN_REQUEST_BYTES = 1032
HYBRID_FROZEN_CONTRACT_DIGEST = "8716a5770d4b1d12c92c546990b5274d7de4f95528cbd06445540a404efa806b"
_RUN_ID_RE = re.compile(rf"^{re.escape(HYBRID_RUN_ID_PREFIX)}-sample-\d{{2,}}-[0-9a-f]{{64}}$")
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
    context_projection_version: str = ""
    context_projection_digest: str = ""
    timeout_seconds: int = 60
    max_transport_retries: int = 0
    target_sample_count: int = 1
    response_mode: str = "json_object"
    feature_flag: str = "OFF"
    record_only: bool = True
    # Optional cohort discriminator.  It is omitted from legacy identities so
    # v0.2/v0.3 historical evidence keeps its original serialized shape.
    cohort_purpose: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "HybridExperimentIdentity":
        base_expected = {
            "experiment", "source_commit", "ir_schema_version",
            "model_facing_contract_version", "model_facing_contract_digest",
            "compiler_version", "canonical_schema_version", "provider", "model",
            "case_id", "timeout_seconds", "max_transport_retries", "target_sample_count",
            "response_mode", "feature_flag", "record_only",
        }
        context_expected = {"context_projection_version", "context_projection_digest"}
        cohort_expected = {"cohort_purpose"}
        allowed_shapes = {
            frozenset(base_expected),
            frozenset(base_expected | context_expected),
            frozenset(base_expected | cohort_expected),
            frozenset(base_expected | context_expected | cohort_expected),
        }
        if not isinstance(payload, Mapping) or frozenset(payload) not in allowed_shapes:
            raise ValueError("HYBRID_IDENTITY_SCHEMA_INVALID")
        values = dict(payload)
        if "context_projection_version" not in values:
            values.update(context_projection_version="", context_projection_digest="")
        if "cohort_purpose" not in values:
            values["cohort_purpose"] = ""
        for key in (set(values) - {"timeout_seconds", "max_transport_retries", "target_sample_count", "record_only"}):
            if not isinstance(values[key], str):
                raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if bool(values["context_projection_version"]) != bool(values["context_projection_digest"]):
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if values["context_projection_digest"] and not re.fullmatch(
            r"[0-9a-f]{64}", values["context_projection_digest"]
        ):
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        for key in ("timeout_seconds", "max_transport_retries", "target_sample_count"):
            if isinstance(values[key], bool) or not isinstance(values[key], int):
                raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if values["target_sample_count"] < 1:
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if not isinstance(values["record_only"], bool):
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if not isinstance(values["cohort_purpose"], str):
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        return cls(**values)

    def to_mapping(self) -> dict[str, object]:
        payload = {
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
        if self.context_projection_version or self.context_projection_digest:
            if not self.context_projection_version or not self.context_projection_digest:
                raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
            payload["context_projection_version"] = self.context_projection_version
            payload["context_projection_digest"] = self.context_projection_digest
        if not isinstance(self.cohort_purpose, str):
            raise ValueError("HYBRID_IDENTITY_FIELD_INVALID")
        if self.cohort_purpose:
            payload["cohort_purpose"] = self.cohort_purpose
        return payload


@runtime_checkable
class HybridProvider(Protocol):
    """Provider adapter seam consumed by the formal Hybrid executor."""

    calls: int
    transport_attempts: int
    latency_ms: float | None
    outcome: str

    def complete(self, request_text: str) -> object: ...


class HybridProviderInvocationError(RuntimeError):
    """Safe provider failure with no raw transport details."""

    def __init__(self, outcome: str) -> None:
        if outcome not in {"TIMEOUT", "TRANSPORT_FAILURE"}:
            raise ValueError("unsupported Hybrid provider outcome")
        self.outcome = outcome
        super().__init__(outcome)


class OpenCodeGoHybridProvider:
    """Shared OpenAI-compatible transport adapter for the Hybrid seam."""

    def __init__(self, client: object, *, model: str, timeout_seconds: int) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds
        self.calls = 0
        self.transport_attempts = 0
        self.latency_ms: float | None = None
        self.outcome = "NOT_CALLED"

    def complete(self, request_text: str) -> object:
        from agents.provider_protocol import (
            NegotiatedResponseContract,
            ProviderClientError,
            ResponseMode,
        )

        self.calls += 1
        self.transport_attempts += 1
        started = time.monotonic()
        try:
            response = self._client.complete(
                model=self._model,
                messages=({"role": "user", "content": request_text},),
                tools=(),
                timeout_seconds=self._timeout_seconds,
                response_contract=NegotiatedResponseContract("hybrid_semantic_ir", ResponseMode.JSON_OBJECT),
            )
        except ProviderClientError as error:
            self.latency_ms = (time.monotonic() - started) * 1000
            self.outcome = "TIMEOUT" if error.kind == "timeout" else "TRANSPORT_FAILURE"
            raise HybridProviderInvocationError(self.outcome) from None
        self.latency_ms = (time.monotonic() - started) * 1000
        self.outcome = "SUCCESS"
        return response.text


@dataclass(frozen=True)
class HybridLiveResult:
    """Safe result for one formal Hybrid execution or pre-provider block."""

    status: str
    consumed: bool
    provider_factory_constructed: bool
    provider_called: bool
    transport_attempts: int
    latency_ms: float | None
    provider_outcome: str
    first_failure_layer: str | None
    stages: Mapping[str, str]
    evidence: HybridEvidence | None = None
    evidence_path: Path | None = None
    candidate: ProtocolSkillKitCandidate | None = field(default=None, repr=False)
    report: SkillValidationReport | None = field(default=None, repr=False)

def _canonical_identity_payload(identity: HybridExperimentIdentity, sample_index: int) -> dict[str, object]:
    if isinstance(sample_index, bool) or not isinstance(sample_index, int) or sample_index < 1:
        raise ValueError("HYBRID_SAMPLE_INDEX_INVALID")
    return {**identity.to_mapping(), "sample_index": sample_index}


def build_hybrid_run_id(identity: HybridExperimentIdentity, *, sample_index: int) -> str:
    """Build the sole deterministic Hybrid observation identity."""

    if not isinstance(identity, HybridExperimentIdentity):
        raise TypeError("identity must be HybridExperimentIdentity")
    canonical = json.dumps(
        _canonical_identity_payload(identity, sample_index),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return f"{HYBRID_RUN_ID_PREFIX}-sample-{sample_index:02d}-{digest}"


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
    sample_index: int
    run_id: str
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
    evaluator_diagnostics: SafeEvaluatorDiagnostics | None = None
    raw_ir_stored: bool = False
    raw_prompt_stored: bool = False
    raw_response_stored: bool = False
    secrets_detected: bool = False

    def to_mapping(self) -> dict[str, object]:
        """Serialize a positive allowlist only; never dump internal objects."""

        return {
            "evidence_version": HYBRID_EVIDENCE_VERSION,
            "identity": self.identity.to_mapping(),
            "sample_index": self.sample_index,
            "run_id": self.run_id,
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
            "evaluator_diagnostics": (
                self.evaluator_diagnostics.to_mapping()
                if self.evaluator_diagnostics is not None
                else None
            ),
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
        self.transport_attempts = 0
        self.latency_ms: float | None = 0.0
        self.outcome = "NOT_CALLED"

    def complete(self, request_text: str) -> object:
        del request_text
        self.calls += 1
        self.transport_attempts += 1
        self.outcome = "SUCCESS"
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


def _identity(
    repo_root: Path,
    contract_digest: str,
    case_id: str = "case_13",
    contract_version: str = "semantic-skill-plan-ir-contract/0.1.0",
    context_projection_version: str = "",
    context_projection_digest: str = "",
    target_sample_count: int = 1,
    cohort_purpose: str = "",
) -> HybridExperimentIdentity:
    source_commit = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
    ).strip()
    return HybridExperimentIdentity(
        HYBRID_EXPERIMENT,
        source_commit,
        model_facing_contract_version=contract_version,
        model_facing_contract_digest=contract_digest,
        case_id=case_id,
        context_projection_version=context_projection_version,
        context_projection_digest=context_projection_digest,
        target_sample_count=target_sample_count,
        cohort_purpose=cohort_purpose,
    )


def _parse_json(response: object) -> object:
    if isinstance(response, str):
        return json.loads(response)
    if isinstance(response, Mapping):
        return json.loads(json.dumps(response, ensure_ascii=False))
    raise ValueError("response must be a JSON object")


def _failure(
    identity: HybridExperimentIdentity,
    request: ModelFacingRequest,
    provider: HybridProvider,
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
    sample_index: int = 1,
) -> FakePipelineResult:
    if layer not in FIRST_FAILURE_LAYERS:
        raise ValueError("unknown first failure layer")
    if relationship_failure_category is not None:
        diagnostics = SafeIRDiagnostics(**{**diagnostics.to_mapping(), "relationship_failure_category": relationship_failure_category})
    evidence = HybridEvidence(
        identity,
        sample_index,
        build_hybrid_run_id(identity, sample_index=sample_index),
        _request_metrics(request),
        layer,
        code,
        principal_verdict,
        provider.calls > 0,
        provider.transport_attempts,
        parser_invoked,
        evaluator_invoked,
        evaluator_outcome,
        semantic_ir_digest,
        candidate_digest,
        diagnostics,
    )
    return FakePipelineResult(evidence)


def _run_pipeline(
    provider: HybridProvider,
    context: HybridGenerationContext,
    evaluation_context: Mapping[str, object],
    *,
    repo_root: Path | str,
    compiler_registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
    sample_index: int = 1,
    target_sample_count: int = 1,
    cohort_purpose: str = "",
    identity: HybridExperimentIdentity | None = None,
) -> FakePipelineResult:
    """Run every Hybrid layer after a provider adapter has been selected."""

    request = build_model_facing_request(context)
    resolved_identity = identity or _identity(
        Path(repo_root),
        request.contract.digest,
        context.case_id,
        request.contract.version,
        context.context_projection_version,
        context.context_projection_digest,
        target_sample_count,
        cohort_purpose,
    )
    run_id = build_hybrid_run_id(resolved_identity, sample_index=sample_index)
    try:
        response = provider.complete(request.text)
    except HybridProviderInvocationError as error:
        return _failure(
            resolved_identity,
            request,
            provider,
            "PROVIDER",
            "PROVIDER_TIMEOUT" if error.outcome == "TIMEOUT" else "PROVIDER_TRANSPORT_FAILURE",
            SafeIRDiagnostics(),
            principal_verdict="UNAVAILABLE",
            sample_index=sample_index,
        )
    try:
        payload = _parse_json(response)
    except (ValueError, json.JSONDecodeError):
        return _failure(resolved_identity, request, provider, "JSON", "JSON_MALFORMED", SafeIRDiagnostics(), sample_index=sample_index)
    diagnostics = _shape_diagnostics(payload)
    try:
        ir = parse_semantic_ir(payload)
    except SemanticIRShapeError as error:
        code = {
            "MISSING_FIELD": "IR_MISSING_REQUIRED_FIELD",
            "UNKNOWN_FIELD": "IR_UNKNOWN_FIELD",
            "IR_INVALID": "IR_WRONG_TYPE",
        }.get(error.code, "IR_OTHER_PARSE_FAILURE")
        return _failure(resolved_identity, request, provider, "IR_PARSE", code, diagnostics, sample_index=sample_index)
    try:
        validated = validate_skill_semantic_ir(ir)
    except SemanticIRValidationError as error:
        code = {
            "UNSUPPORTED_SEMANTIC_MAPPING": "IR_UNSUPPORTED_MAPPING",
            "IR_INVALID": "IR_INVALID_SEMANTIC_VALUE",
        }.get(error.code, "IR_OTHER_VALIDATION_FAILURE")
        relationship = "INVALID_RELATIONSHIP" if "feedback" in error.path and "actor" in error.path else None
        return _failure(
            resolved_identity,
            request,
            provider,
            "IR_VALIDATION",
            code,
            diagnostics,
            relationship_failure_category=relationship,
            sample_index=sample_index,
        )
    assert isinstance(validated, ValidatedSkillSemanticIR)
    try:
        compiled = compile_skill_semantic_ir(validated, registry=compiler_registry)
    except SkillKitCompilerError as error:
        return _failure(resolved_identity, request, provider, "COMPILER", error.code, diagnostics, semantic_ir_digest=validated.digest, sample_index=sample_index)
    candidate_digest = compiled.candidate_digest
    try:
        parsed = parse_candidate(compiled.candidate.to_mapping())
    except Exception:
        return _failure(
            resolved_identity,
            request,
            provider,
            "CANONICAL_PARSER",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
            sample_index=sample_index,
        )
    if not isinstance(parsed, ProtocolSkillKitCandidate):
        return _failure(
            resolved_identity,
            request,
            provider,
            "CANONICAL_PARSER",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
            sample_index=sample_index,
        )
    try:
        validate_reference_integrity(parsed)
    except SkillKitCompilerError:
        return _failure(
            resolved_identity,
            request,
            provider,
            "REFERENCE_INTEGRITY",
            "COMPILER_DEFECT",
            diagnostics,
            parser_invoked=True,
            semantic_ir_digest=validated.digest,
            candidate_digest=candidate_digest,
            sample_index=sample_index,
        )
    report = evaluate(parsed, evaluation_context)
    verdict = "PASS" if report.outcome == "PASS" else "EVALUATOR_" + report.outcome
    return FakePipelineResult(
        HybridEvidence(
            resolved_identity,
            sample_index,
            run_id,
            _request_metrics(request),
            "EVALUATOR" if report.outcome != "PASS" else None,
            None if report.outcome == "PASS" else report.outcome,
            verdict,
            provider.calls > 0,
            provider.transport_attempts,
            True,
            True,
            report.outcome,
            validated.digest,
            candidate_digest,
            diagnostics,
            evaluator_diagnostics=adapt_skill_validation_report(report),
        ),
        parsed,
        report,
    )


def run_fake_pipeline(
    provider: FakeProvider,
    context: HybridGenerationContext,
    evaluation_context: Mapping[str, object],
    *,
    repo_root: Path | str,
    compiler_registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
    sample_index: int = 1,
    target_sample_count: int = 1,
    cohort_purpose: str = "",
) -> FakePipelineResult:
    """Run the formal pipeline with an in-memory provider adapter."""

    return _run_pipeline(
        provider,
        context,
        evaluation_context,
        repo_root=repo_root,
        compiler_registry=compiler_registry,
        sample_index=sample_index,
        target_sample_count=target_sample_count,
        cohort_purpose=cohort_purpose,
    )


def validate_hybrid_evidence(payload: Mapping[str, object]) -> None:
    """Validate either the frozen v0.2.0 or the diagnostic v0.3.0 shape."""

    if not isinstance(payload, Mapping):
        raise ValueError("HYBRID_EVIDENCE_SCHEMA_INVALID")
    version = payload.get("evidence_version")
    if version == HYBRID_EVIDENCE_VERSION_V020:
        _validate_hybrid_evidence_v020(payload)
        return
    if version == HYBRID_EVIDENCE_VERSION:
        _validate_hybrid_evidence_v030(payload)
        return
    raise ValueError("HYBRID_EVIDENCE_SCHEMA_INVALID")


def _validate_hybrid_evidence_common(payload: Mapping[str, object], required: set[str]) -> None:
    """Validate fields shared by both evidence schema versions."""

    if set(payload) != required:
        raise ValueError("HYBRID_EVIDENCE_SCHEMA_INVALID")
    identity = HybridExperimentIdentity.from_mapping(payload["identity"])
    sample_index = payload["sample_index"]
    if isinstance(sample_index, bool) or not isinstance(sample_index, int) or sample_index < 1:
        raise ValueError("HYBRID_SAMPLE_INDEX_INVALID")
    if not isinstance(payload["run_id"], str) or not _RUN_ID_RE.fullmatch(payload["run_id"]):
        raise ValueError("HYBRID_RUN_ID_INVALID")
    if payload["run_id"] != build_hybrid_run_id(identity, sample_index=sample_index):
        raise ValueError("HYBRID_IDENTITY_MISMATCH")
    for key in ("fake_provider_called", "parser_invoked", "evaluator_invoked"):
        if not isinstance(payload[key], bool):
            raise ValueError("HYBRID_BOOLEAN_FIELD_INVALID")
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


def _validate_hybrid_evidence_v020(payload: Mapping[str, object]) -> None:
    required = {
        "evidence_version", "identity", "sample_index", "run_id", "request_metrics",
        "first_failure_layer", "failure_code", "principal_verdict", "fake_provider_called",
        "fake_transport_attempts", "parser_invoked", "evaluator_invoked", "evaluator_outcome",
        "semantic_ir_digest", "candidate_digest", "diagnostics", "sanitization",
    }
    _validate_hybrid_evidence_common(payload, required)


def _validate_hybrid_evidence_v030(payload: Mapping[str, object]) -> None:
    required = {
        "evidence_version", "identity", "sample_index", "run_id", "request_metrics",
        "first_failure_layer", "failure_code", "principal_verdict", "fake_provider_called",
        "fake_transport_attempts", "parser_invoked", "evaluator_invoked", "evaluator_outcome",
        "semantic_ir_digest", "candidate_digest", "diagnostics", "evaluator_diagnostics",
        "sanitization",
    }
    _validate_hybrid_evidence_common(payload, required)
    diagnostic = payload["evaluator_diagnostics"]
    if payload["evaluator_invoked"]:
        if payload["evaluator_outcome"] not in {"PASS", "REPAIR", "FAIL"}:
            raise ValueError("HYBRID_EVALUATOR_OUTCOME_INVALID")
        if not isinstance(diagnostic, Mapping):
            raise ValueError("HYBRID_EVALUATOR_DIAGNOSTICS_REQUIRED")
        try:
            parsed = SafeEvaluatorDiagnostics.from_mapping(diagnostic)
        except (TypeError, ValueError):
            raise ValueError("HYBRID_EVALUATOR_DIAGNOSTICS_INVALID") from None
        if payload["evaluator_outcome"] == "PASS" and parsed.finding_count != 0:
            raise ValueError("HYBRID_PASS_DIAGNOSTICS_INVALID")
    elif diagnostic is not None:
        raise ValueError("HYBRID_EVALUATOR_DIAGNOSTICS_UNEXPECTED")
    elif payload["evaluator_outcome"] != "NOT_RUN":
        raise ValueError("HYBRID_EVALUATOR_OUTCOME_INVALID")


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


def _stage_statuses(first_failure_layer: str | None) -> Mapping[str, str]:
    if first_failure_layer is None:
        return MappingProxyType({layer.lower(): "PASS" for layer in FIRST_FAILURE_LAYERS})
    failed = FIRST_FAILURE_LAYERS.index(first_failure_layer)
    return MappingProxyType(
        {
            layer.lower(): ("PASS" if index < failed else "FAIL" if index == failed else "NOT_REACHED")
            for index, layer in enumerate(FIRST_FAILURE_LAYERS)
        }
    )


def _live_status(evidence: HybridEvidence) -> str:
    if evidence.first_failure_layer == "PROVIDER":
        return "HYBRID_SEMANTIC_IR_UNAVAILABLE"
    if evidence.first_failure_layer == "JSON":
        return "HYBRID_SEMANTIC_IR_JSON_REJECTED"
    if evidence.first_failure_layer in {"IR_PARSE", "IR_VALIDATION"}:
        return "HYBRID_SEMANTIC_IR_IR_REJECTED"
    if evidence.first_failure_layer == "COMPILER":
        return "HYBRID_COMPILER_FAILURE"
    if evidence.first_failure_layer == "CANONICAL_PARSER":
        return "HYBRID_POST_COMPILE_CANONICAL_DEFECT"
    if evidence.first_failure_layer == "REFERENCE_INTEGRITY":
        return "HYBRID_POST_COMPILE_REFERENCE_DEFECT"
    if evidence.first_failure_layer == "EVALUATOR":
        return (
            "HYBRID_SEMANTIC_IR_EVALUATOR_REPAIR"
            if evidence.evaluator_outcome == "REPAIR"
            else "HYBRID_SEMANTIC_IR_EVALUATOR_REJECTED"
        )
    return "HYBRID_SEMANTIC_IR_END_TO_END_PASS"


def _blocked_live_result(status: str) -> HybridLiveResult:
    return HybridLiveResult(
        status=status,
        consumed=False,
        provider_factory_constructed=False,
        provider_called=False,
        transport_attempts=0,
        latency_ms=None,
        provider_outcome="NOT_CALLED",
        first_failure_layer=None,
        stages=MappingProxyType({layer.lower(): "NOT_REACHED" for layer in FIRST_FAILURE_LAYERS}),
    )


def _default_hybrid_provider_factory() -> HybridProvider:
    from agents.model_factory import LiveLLMSettings
    from agents.openai_provider import OpenAIChatClient

    api_key = os.environ.get("NPC_LLM_API_KEY", "").strip()
    environment = {
        "NPC_AGENT_MODEL": "live",
        "NPC_LLM_PROVIDER": "opencode_go",
        "NPC_LLM_MODEL": "deepseek-v4-pro",
        "NPC_LLM_TRANSPORT": "openai_chat_completions",
        "NPC_LLM_STRUCTURED_OUTPUT": "json_object",
        "NPC_LLM_TIMEOUT_SECONDS": "60",
        "NPC_LLM_MAX_RETRIES": "0",
        "NPC_LLM_API_KEY": api_key,
    }
    settings = LiveLLMSettings.from_environment(environment)
    client = OpenAIChatClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        request_options=settings.profile.provider_options,
    )
    return OpenCodeGoHybridProvider(
        client,
        model=settings.model,
        timeout_seconds=int(settings.timeout_seconds),
    )


def _normalize_cohort_indexes(
    indexes: tuple[int, ...] | list[int] | tuple[object, ...],
    *,
    target_sample_count: int,
) -> tuple[int, ...]:
    """Validate the contiguous, append-only state of a cohort."""

    values = tuple(indexes)
    if any(isinstance(index, bool) or not isinstance(index, int) for index in values):
        raise ValueError("HYBRID_COHORT_SAMPLE_INDEX_INVALID")
    if any(index < 1 or index > target_sample_count for index in values):
        raise ValueError("HYBRID_COHORT_SAMPLE_INDEX_INVALID")
    if values != tuple(sorted(values)) or len(set(values)) != len(values):
        raise ValueError("HYBRID_COHORT_STATE_INVALID")
    expected = tuple(range(1, len(values) + 1))
    if values != expected:
        raise ValueError("HYBRID_COHORT_STATE_INVALID")
    return values


def _discover_cohort_indexes(
    evidence_paths: tuple[Path, ...],
    *,
    expected_identity: HybridExperimentIdentity,
) -> tuple[int, ...]:
    """Load explicitly supplied evidence and retain only exact cohort members.

    Evidence files are never selected by filename.  Every existing path must
    validate and carry the exact identity (including target and purpose) of the
    runner's cohort, otherwise the fail-closed mismatch is surfaced before a
    provider factory can be constructed.
    """

    indexes: list[int] = []
    for path in evidence_paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate_hybrid_evidence(payload)
            identity = HybridExperimentIdentity.from_mapping(payload["identity"])
            sample_index = payload["sample_index"]
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
            raise ValueError("HYBRID_COHORT_EVIDENCE_INVALID") from None
        if identity != expected_identity:
            raise ValueError("HYBRID_COHORT_IDENTITY_MISMATCH")
        if isinstance(sample_index, bool) or not isinstance(sample_index, int):
            raise ValueError("HYBRID_COHORT_SAMPLE_INDEX_INVALID")
        indexes.append(sample_index)
    return _normalize_cohort_indexes(indexes, target_sample_count=expected_identity.target_sample_count)


class HybridSemanticIRRunner:
    """Formal cohort planner with a provider-free dry-run seam.

    A runner invocation still consumes exactly one observation.  The cohort
    state only controls which deterministic sample index is legal next and
    whether the provider may be constructed at all.
    """

    def __init__(
        self,
        repo_root: Path | str,
        context: HybridGenerationContext,
        *,
        target_sample_count: int = 1,
        existing_sample_indexes: tuple[int, ...] = (),
        existing_evidence_paths: tuple[Path | str, ...] = (),
        cohort_purpose: str = "",
    ) -> None:
        if isinstance(target_sample_count, bool) or not isinstance(target_sample_count, int) or target_sample_count < 1:
            raise ValueError("HYBRID_TARGET_SAMPLE_COUNT_INVALID")
        if not isinstance(cohort_purpose, str):
            raise ValueError("HYBRID_COHORT_PURPOSE_INVALID")
        self.repo_root = Path(repo_root)
        self.context = context
        self.target_sample_count = target_sample_count
        self.cohort_purpose = cohort_purpose
        self.existing_evidence_paths = tuple(Path(path).resolve() for path in existing_evidence_paths)

        request = build_model_facing_request(self.context)
        self._identity = _identity(
            self.repo_root,
            request.contract.digest,
            self.context.case_id,
            request.contract.version,
            self.context.context_projection_version,
            self.context.context_projection_digest,
            target_sample_count=self.target_sample_count,
            cohort_purpose=self.cohort_purpose,
        )
        explicit_indexes = _normalize_cohort_indexes(
            existing_sample_indexes,
            target_sample_count=self.target_sample_count,
        )
        discovered_indexes = _discover_cohort_indexes(
            self.existing_evidence_paths,
            expected_identity=self._identity,
        )
        if explicit_indexes and discovered_indexes and explicit_indexes != discovered_indexes:
            raise ValueError("HYBRID_COHORT_STATE_MISMATCH")
        self.existing_sample_indexes = discovered_indexes or explicit_indexes

    @property
    def cohort_identity(self) -> HybridExperimentIdentity:
        """Return the identity bound to this cohort, without provider access."""

        return self._identity

    def _next_sample_index(self) -> int:
        return len(self.existing_sample_indexes) + 1

    def dry_run(self) -> dict[str, object]:
        existing = len(self.existing_sample_indexes)
        next_index = self._next_sample_index()
        remaining = max(self.target_sample_count - existing, 0)
        sample_index = next_index
        return {
            "status": "dry_run_hybrid_semantic_ir",
            "identity": self._identity.to_mapping(),
            "sample_index": sample_index,
            "run_id": build_hybrid_run_id(self._identity, sample_index=sample_index),
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

    def run_live(
        self,
        evaluation_context: Mapping[str, object],
        *,
        provider_factory: Callable[[], HybridProvider] | None = None,
        output_path: Path | str | None = None,
        expected_run_id: str | None = None,
        sample_index: int | None = None,
        enforce_clean_tree: bool = True,
        compiler_registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
    ) -> HybridLiveResult:
        """Execute exactly one observation after all safety gates pass.

        The default factory is intentionally resolved only after pre-provider
        checks. Tests inject an adapter at this seam; production remains
        RECORD_ONLY and never activates the character-generation path.
        """

        if self.existing_sample_indexes and self._next_sample_index() > self.target_sample_count:
            return _blocked_live_result("COHORT_ALREADY_COMPLETE")
        next_index = self._next_sample_index()
        if sample_index is None:
            sample_index = next_index
        if isinstance(sample_index, bool) or not isinstance(sample_index, int):
            return _blocked_live_result("BLOCKED_INVALID_HYBRID_COHORT_STATE")
        if sample_index != next_index or sample_index > self.target_sample_count:
            return _blocked_live_result(
                "COHORT_ALREADY_COMPLETE"
                if next_index > self.target_sample_count
                else "BLOCKED_INVALID_HYBRID_COHORT_STATE"
            )
        request = build_model_facing_request(self.context)
        metrics = request.metrics.to_mapping()
        if self.context.contract_profile == "frozen_h3" and (
            metrics["total_chars"] != HYBRID_FROZEN_REQUEST_CHARS
            or metrics["total_bytes"] != HYBRID_FROZEN_REQUEST_BYTES
            or request.contract.digest != HYBRID_FROZEN_CONTRACT_DIGEST
        ):
            return _blocked_live_result("BLOCKED_HYBRID_REQUEST_DRIFT")
        if self.context.contract_profile == "aligned_v1" and (
            request.contract.version != MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED
            or self.context.context_projection_version != CONTEXT_PROJECTION_VERSION
            or not self.context.context_projection_digest
        ):
            return _blocked_live_result("BLOCKED_CONTEXT_IDENTITY")
        if enforce_clean_tree:
            dirty = subprocess.check_output(
                ["git", "-C", str(self.repo_root), "status", "--porcelain", "--untracked-files=no"],
                text=True,
            ).strip()
            if dirty:
                return _blocked_live_result("BLOCKED_SOURCE_BASELINE_DRIFT")
        identity = self._identity
        current_identity = _identity(
            self.repo_root,
            request.contract.digest,
            self.context.case_id,
            request.contract.version,
            self.context.context_projection_version,
            self.context.context_projection_digest,
            target_sample_count=self.target_sample_count,
            cohort_purpose=self.cohort_purpose,
        )
        if current_identity != identity:
            return _blocked_live_result("BLOCKED_HYBRID_IDENTITY_DRIFT")
        run_id = build_hybrid_run_id(identity, sample_index=sample_index)
        if expected_run_id is not None and expected_run_id != run_id:
            return _blocked_live_result("BLOCKED_HYBRID_IDENTITY_DRIFT")
        destination = (Path(output_path) if output_path is not None else self.repo_root / HYBRID_DEFAULT_EVIDENCE_RELATIVE_PATH).resolve()
        if destination.exists():
            return _blocked_live_result("COHORT_SAMPLE_ALREADY_RECORDED")
        if not os.environ.get("NPC_LLM_API_KEY", "").strip():
            return _blocked_live_result("BLOCKED_PROVIDER_CREDENTIAL_MISSING")
        factory = provider_factory or _default_hybrid_provider_factory
        try:
            provider = factory()
        except Exception:
            return _blocked_live_result("BLOCKED_PROVIDER_CONFIGURATION")
        if not isinstance(provider, HybridProvider):
            raise TypeError("provider_factory must return a HybridProvider")
        pipeline = _run_pipeline(
            provider,
            self.context,
            evaluation_context,
            repo_root=self.repo_root,
            compiler_registry=compiler_registry,
            sample_index=sample_index,
            target_sample_count=self.target_sample_count,
            cohort_purpose=self.cohort_purpose,
            identity=identity,
        )
        evidence_path = write_evidence_atomic(pipeline.evidence, destination)
        evidence = pipeline.evidence
        self.existing_sample_indexes = tuple((*self.existing_sample_indexes, sample_index))
        if destination not in self.existing_evidence_paths:
            self.existing_evidence_paths = (*self.existing_evidence_paths, destination)
        return HybridLiveResult(
            status=_live_status(evidence),
            consumed=provider.calls > 0,
            provider_factory_constructed=True,
            provider_called=provider.calls > 0,
            transport_attempts=provider.transport_attempts,
            latency_ms=provider.latency_ms,
            provider_outcome=provider.outcome,
            first_failure_layer=evidence.first_failure_layer,
            stages=_stage_statuses(evidence.first_failure_layer),
            evidence=evidence,
            evidence_path=evidence_path,
            candidate=pipeline.candidate,
            report=pipeline.report,
        )


__all__ = [
    "FIRST_FAILURE_LAYERS",
    "HYBRID_DEFAULT_EVIDENCE_RELATIVE_PATH",
    "FakePipelineResult",
    "FakeProvider",
    "HYBRID_EVIDENCE_VERSION",
    "HYBRID_EVIDENCE_VERSION_V020",
    "HYBRID_EXPERIMENT",
    "HYBRID_RUN_ID_PREFIX",
    "HYBRID_REPLICATION_COHORT_PURPOSE",
    "HybridEvidence",
    "HybridExperimentIdentity",
    "HybridLiveResult",
    "HybridProvider",
    "HybridProviderInvocationError",
    "HybridSemanticIRRunner",
    "OpenCodeGoHybridProvider",
    "SafeIRDiagnostics",
    "build_hybrid_run_id",
    "run_fake_pipeline",
    "validate_hybrid_evidence",
    "write_evidence_atomic",
]
