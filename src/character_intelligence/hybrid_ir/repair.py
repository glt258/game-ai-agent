"""Bounded, model-owned repair for failed Hybrid Semantic IR evaluations.

This module is the Semantic IR repair seam.  It deliberately stays separate
from the canonical SkillKit patch repair module: the repair adapter receives
the in-memory semantic candidate and bounded, human-readable diagnostics, then
the existing Hybrid pipeline revalidates the returned semantic IR end to end.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from ..compiler import DEFAULT_MAPPING_REGISTRY, SemanticMappingRegistry
from ..semantic_ir import (
    SEMANTIC_IR_V2_VERSION,
    SEMANTIC_IR_VERSION,
    SemanticIRShapeError,
    SemanticIRValidationError,
    SkillSemanticIR,
    SkillSemanticIRV2,
    ValidatedSkillSemanticIR,
    parse_semantic_ir,
    validate_skill_semantic_ir,
)
from .contract import ModelFacingRequest, build_model_facing_request
from .diagnostics import (
    SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
    Repairability,
    SafeEvaluatorDiagnostics,
    SemanticDimension,
)
from .language import ensure_output_language, resolve_output_language
from .projection import HybridGenerationContext
from .runner import (
    FIRST_FAILURE_LAYERS,
    FakePipelineResult,
    FakeProvider,
    HybridLiveResult,
    run_fake_pipeline,
)

MAX_REPAIR_ATTEMPTS = 1
SEMANTIC_REPAIR_CONTRACT_VERSION = "semantic-skill-ir-repair-contract/0.2.0"
SEMANTIC_REPAIR_CONTRACT_VERSION_V2_HISTORICAL = "semantic-skill-ir-repair-contract/0.3.0"
SEMANTIC_REPAIR_CONTRACT_VERSION_V2_LEGACY = "semantic-skill-ir-repair-contract/0.3.1"
SEMANTIC_REPAIR_CONTRACT_VERSION_V2_PRIOR = "semantic-skill-ir-repair-contract/0.3.2"
SEMANTIC_REPAIR_CONTRACT_VERSION_V2 = "semantic-skill-ir-repair-contract/0.3.3"
SEMANTIC_REPAIR_EVIDENCE_VERSION = "character-skill-s2-hybrid-ir-semantic-repair/0.1.0"


@dataclass(frozen=True)
class SemanticRepairContract:
    """Compact, generic contract used only by the repair adapter."""

    version: str
    ir_version: str
    text: str
    digest: str

    def __post_init__(self) -> None:
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        valid_pair = {
            (SEMANTIC_REPAIR_CONTRACT_VERSION, SEMANTIC_IR_VERSION),
            (SEMANTIC_REPAIR_CONTRACT_VERSION_V2_HISTORICAL, SEMANTIC_IR_V2_VERSION),
            (SEMANTIC_REPAIR_CONTRACT_VERSION_V2_LEGACY, SEMANTIC_IR_V2_VERSION),
            (SEMANTIC_REPAIR_CONTRACT_VERSION_V2_PRIOR, SEMANTIC_IR_V2_VERSION),
            (SEMANTIC_REPAIR_CONTRACT_VERSION_V2, SEMANTIC_IR_V2_VERSION),
        }
        if (self.version, self.ir_version) not in valid_pair:
            raise ValueError("SEMANTIC_REPAIR_CONTRACT_VERSION_INVALID")
        if self.digest != expected:
            raise ValueError("SEMANTIC_REPAIR_CONTRACT_DIGEST_INVALID")


def build_semantic_repair_contract(
    ir_version: str = SEMANTIC_IR_VERSION,
    *,
    language: str = "en",
) -> SemanticRepairContract:
    ensure_output_language(language)
    if ir_version == SEMANTIC_IR_VERSION:
        version = SEMANTIC_REPAIR_CONTRACT_VERSION
        text = (
            f"Semantic skill IR repair contract {version}. "
            f"Return exactly one JSON object using IR version {ir_version}. "
            "Required root keys: ir_version, ability_name, summary, mode, role, centrality, "
            "mechanic, role_path. Mechanic requires trigger, effect, feedback; feedback "
            "requires event, relation, response_trigger, response_effect; role_path requires "
            "trigger and effect. A trigger has actor, event, qualifier; an effect has actor, "
            "intent, description. Return the full corrected plan, preserve valid semantics, "
            "use only authoritative projected values, and add no wrapper or extra keys."
        )
    elif ir_version == SEMANTIC_IR_V2_VERSION:
        version = SEMANTIC_REPAIR_CONTRACT_VERSION_V2
        text = (
            f"Semantic skill IR repair contract {version}. Return exactly one JSON object using "
            f"IR version {ir_version}. Required root keys: ir_version, ability_name, summary, "
            "mode, role, centrality, mechanic, role_path. A triggered mechanic has exactly "
            "kind, trigger, effect, and feedback; all four keys are required. Gameplay feedback "
            "is optional, so use the JSON field \"feedback\": null when absent and never omit it. "
            "A non-null feedback object has event, relation, response_trigger, and response_effect; "
            "response_trigger has actor, event, qualifier and response_effect has actor, intent, "
            "description. A passive mechanic has exactly kind, persistence, and effect only, "
            "with persistence that must be always_on and no trigger or feedback. Match role_path to the "
            "mechanic variant: triggered has kind, trigger, effect; passive has kind and effect. "
            "A trigger has actor, event, qualifier; an effect has actor, intent, description. "
            "Use exact contract-defined machine-readable field names, discriminators, enums, "
            "and intents; human-readable prose must follow the selected output language. "
            "Return the full corrected plan, preserve valid semantics, "
            "use only authoritative projected values, and add no wrapper or extra keys."
        )
    else:
        raise ValueError("SEMANTIC_REPAIR_IR_VERSION_INVALID")
    return SemanticRepairContract(
        version=version,
        ir_version=ir_version,
        text=text,
        digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


class RepairOutcome(str, Enum):
    NO_REPAIR_NEEDED = "NO_REPAIR_NEEDED"
    REPAIR_SUCCESS = "REPAIR_SUCCESS"
    REPAIR_FAILED_SEMANTIC = "REPAIR_FAILED_SEMANTIC"
    REPAIR_FAILED_STRUCTURAL = "REPAIR_FAILED_STRUCTURAL"
    REPAIR_UNAVAILABLE = "REPAIR_UNAVAILABLE"
    REPAIR_NOT_ELIGIBLE = "REPAIR_NOT_ELIGIBLE"
    REPAIR_BUDGET_EXHAUSTED = "REPAIR_BUDGET_EXHAUSTED"


_DIMENSION_GUIDANCE = {
    SemanticDimension.MODE: "mode mismatch",
    SemanticDimension.CONTINUATION_FAMILY: "continuation semantic family mismatch",
    SemanticDimension.MECHANIC_SKELETON: "mechanic semantic requirement not satisfied",
    SemanticDimension.FEEDBACK_RELATION: "feedback relationship mismatch",
    SemanticDimension.ROLE_EVIDENCE: "role evidence mismatch",
    SemanticDimension.FEEDBACK_EXISTENCE: "required feedback continuation is missing",
    SemanticDimension.FEEDBACK_REFERENCE: "feedback reference integrity mismatch",
    SemanticDimension.ROLE_ALIGNMENT: "role semantic alignment mismatch",
    SemanticDimension.SUBJECT_AMBIGUITY: "subject semantics are ambiguous",
    SemanticDimension.LIFECYCLE: "lifecycle semantics are incomplete or inconsistent",
    SemanticDimension.CONSTRAINT: "a requested semantic constraint is not satisfied",
    SemanticDimension.FORBIDDEN_MECHANIC: "a forbidden mechanic is present",
    SemanticDimension.REFERENCE_INTEGRITY: "reference semantics are not intact",
    SemanticDimension.REFERENCE_AUTHORITY: "reference policy is not satisfied",
    SemanticDimension.REPRESENTATION: "required semantic representation is missing",
    SemanticDimension.OTHER_SEMANTIC: "one or more semantic requirements need correction",
}


@dataclass(frozen=True)
class SemanticRepairRequest:
    """The small interface exposed to one repair adapter call."""

    original_request: ModelFacingRequest
    candidate: SkillSemanticIR | SkillSemanticIRV2
    diagnostics: SafeEvaluatorDiagnostics
    attempt_index: int = 1
    repair_contract: SemanticRepairContract = field(default_factory=build_semantic_repair_contract)

    def __post_init__(self) -> None:
        if not isinstance(self.original_request, ModelFacingRequest):
            raise TypeError("original_request must be a ModelFacingRequest")
        if not isinstance(self.candidate, (SkillSemanticIR, SkillSemanticIRV2)):
            raise TypeError("candidate must be a supported SkillSemanticIR")
        if not isinstance(self.diagnostics, SafeEvaluatorDiagnostics):
            raise TypeError("diagnostics must be SafeEvaluatorDiagnostics")
        if not isinstance(self.repair_contract, SemanticRepairContract):
            raise TypeError("repair_contract must be a SemanticRepairContract")
        if self.attempt_index != 1:
            raise ValueError("SEMANTIC_REPAIR_ATTEMPT_INVALID")

    @property
    def guidance(self) -> tuple[str, ...]:
        return tuple(
            _DIMENSION_GUIDANCE.get(
                dimension,
                "one or more semantic requirements need correction",
            )
            for dimension in self.diagnostics.dimensions
        )

    def to_prompt(self) -> str:
        """Render only generic repair guidance plus the in-memory candidate."""

        guidance = "\n".join(f"- {item}" for item in self.guidance)
        candidate = json.dumps(
            self.candidate.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (
            f"{self.repair_contract.text}\n\n"
            "Authoritative semantic requirement:\n"
            f"{self.original_request.case_text}\n\n"
            "Allowed projected semantic values:\n"
            f"{self.original_request.contract.enum_text}\n\n"
            "Bounded semantic observations:\n"
            f"{guidance}\n"
            "Current in-memory semantic skill plan:\n"
            f"{candidate}"
        )


@dataclass(frozen=True)
class SemanticRepairIdentity:
    """Identity that keeps a repair observation distinct from its generation."""

    source_commit: str
    original_run_id: str
    case_id: str
    generation_contract_digest: str
    context_digest: str
    repair_contract_version: str = SEMANTIC_REPAIR_CONTRACT_VERSION
    repair_attempt_index: int = 1

    def __post_init__(self) -> None:
        for value in (
            self.source_commit,
            self.original_run_id,
            self.case_id,
            self.generation_contract_digest,
            self.context_digest,
            self.repair_contract_version,
        ):
            if not isinstance(value, str) or not value:
                raise ValueError("SEMANTIC_REPAIR_IDENTITY_INVALID")
        if self.repair_attempt_index != 1:
            raise ValueError("SEMANTIC_REPAIR_ATTEMPT_INVALID")

    @classmethod
    def from_initial(
        cls,
        initial: FakePipelineResult | HybridLiveResult,
        context: HybridGenerationContext,
        language: str = "en",
    ) -> "SemanticRepairIdentity":
        if initial.evidence is None:
            raise ValueError("SEMANTIC_REPAIR_INITIAL_EVIDENCE_REQUIRED")
        language = resolve_output_language(language, context.brief)
        request = build_model_facing_request(context, language=language)
        identity = initial.evidence.identity
        if (
            identity.case_id != context.case_id
            or identity.model_facing_contract_digest != request.contract.digest
            or identity.context_projection_digest != context.context_projection_digest
        ):
            raise ValueError("SEMANTIC_REPAIR_GENERATION_IDENTITY_MISMATCH")
        repair_contract_version = (
            SEMANTIC_REPAIR_CONTRACT_VERSION_V2
            if identity.ir_schema_version == SEMANTIC_IR_V2_VERSION
            else SEMANTIC_REPAIR_CONTRACT_VERSION
        )
        return cls(
            source_commit=identity.source_commit,
            original_run_id=initial.evidence.run_id,
            case_id=context.case_id,
            generation_contract_digest=request.contract.digest,
            context_digest=context.context_projection_digest,
            repair_contract_version=repair_contract_version,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "source_commit": self.source_commit,
            "original_run_id": self.original_run_id,
            "case_id": self.case_id,
            "generation_contract_digest": self.generation_contract_digest,
            "context_digest": self.context_digest,
            "repair_contract_version": self.repair_contract_version,
            "repair_attempt_index": self.repair_attempt_index,
        }


@dataclass(frozen=True)
class SemanticRepairEvidence:
    """Safe repair observation; candidates and provider payloads are excluded."""

    identity: SemanticRepairIdentity
    initial_evaluator_outcome: str
    initial_diagnostics: SafeEvaluatorDiagnostics
    repair_attempted: bool
    repair_provider_calls: int
    repair_pipeline_furthest_layer: str | None
    repaired_evaluator_outcome: str
    repaired_diagnostics: SafeEvaluatorDiagnostics | None
    final_outcome: RepairOutcome

    def to_mapping(self) -> dict[str, object]:
        return {
            "evidence_version": SEMANTIC_REPAIR_EVIDENCE_VERSION,
            "identity": self.identity.to_mapping(),
            "initial_evaluator_outcome": self.initial_evaluator_outcome,
            "initial_diagnostics": self.initial_diagnostics.to_mapping(),
            "repair_attempted": self.repair_attempted,
            "repair_provider_calls": self.repair_provider_calls,
            "repair_pipeline_furthest_layer": self.repair_pipeline_furthest_layer,
            "repaired_evaluator_outcome": self.repaired_evaluator_outcome,
            "repaired_diagnostics": (
                self.repaired_diagnostics.to_mapping()
                if self.repaired_diagnostics is not None
                else None
            ),
            "final_outcome": self.final_outcome.value,
            "sanitization": {
                "raw_candidate_stored": False,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
                "secrets_detected": False,
            },
        }


@dataclass(frozen=True)
class SemanticRepairResult:
    """Outcome of one bounded repair session, with raw values kept in memory only."""

    outcome: RepairOutcome
    evidence: SemanticRepairEvidence
    repair_attempts: int
    repaired_ir: SkillSemanticIR | SkillSemanticIRV2 | None = field(default=None, repr=False)
    revalidation: FakePipelineResult | None = field(default=None, repr=False)

    def to_mapping(self) -> dict[str, object]:
        return self.evidence.to_mapping()


def _empty_diagnostics() -> SafeEvaluatorDiagnostics:
    return SafeEvaluatorDiagnostics(
        schema_version=SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
        complete=True,
        finding_count=0,
        dimensions=(),
        categories=(),
        counts_by_dimension={},
        counts_by_category={},
        repairability=Repairability.NOT_APPLICABLE,
    )


def _initial_diagnostics(initial: FakePipelineResult | HybridLiveResult) -> SafeEvaluatorDiagnostics:
    if initial.evidence is None or initial.evidence.evaluator_diagnostics is None:
        return _empty_diagnostics()
    return initial.evidence.evaluator_diagnostics


def _json_payload(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, Mapping):
        return json.loads(json.dumps(value, ensure_ascii=False))
    raise ValueError("SEMANTIC_REPAIR_RESPONSE_INVALID")


def _furthest_layer(result: FakePipelineResult) -> str:
    return result.evidence.first_failure_layer or "EVALUATOR"


class SemanticRepairSession:
    """Deep repair module with one public operation and a hard one-attempt bound."""

    def __init__(
        self,
        initial: FakePipelineResult | HybridLiveResult,
        context: HybridGenerationContext,
        evaluation_context: Mapping[str, object],
        *,
        repo_root: str,
        language: str = "en",
        compiler_registry: SemanticMappingRegistry = DEFAULT_MAPPING_REGISTRY,
    ) -> None:
        if not isinstance(initial, (FakePipelineResult, HybridLiveResult)):
            raise TypeError("initial must be a Hybrid pipeline result")
        if initial.evidence is None:
            raise ValueError("SEMANTIC_REPAIR_INITIAL_EVIDENCE_REQUIRED")
        if not isinstance(context, HybridGenerationContext):
            raise TypeError("context must be a HybridGenerationContext")
        if not isinstance(evaluation_context, Mapping):
            raise TypeError("evaluation_context must be a mapping")
        self.initial = initial
        self.context = context
        self.evaluation_context = evaluation_context
        self.repo_root = repo_root
        self.compiler_registry = compiler_registry
        self.language = resolve_output_language(language, context.brief)
        self.identity = SemanticRepairIdentity.from_initial(initial, context, self.language)
        self._attempts = 0

    def _result(
        self,
        outcome: RepairOutcome,
        *,
        attempted: bool,
        provider_calls: int,
        furthest_layer: str | None = None,
        repaired_evaluator_outcome: str = "NOT_RUN",
        repaired_diagnostics: SafeEvaluatorDiagnostics | None = None,
        repaired_ir: SkillSemanticIR | SkillSemanticIRV2 | None = None,
        revalidation: FakePipelineResult | None = None,
    ) -> SemanticRepairResult:
        evidence = SemanticRepairEvidence(
            identity=self.identity,
            initial_evaluator_outcome=self.initial.evidence.evaluator_outcome,
            initial_diagnostics=_initial_diagnostics(self.initial),
            repair_attempted=attempted,
            repair_provider_calls=provider_calls,
            repair_pipeline_furthest_layer=furthest_layer,
            repaired_evaluator_outcome=repaired_evaluator_outcome,
            repaired_diagnostics=repaired_diagnostics,
            final_outcome=outcome,
        )
        return SemanticRepairResult(
            outcome=outcome,
            evidence=evidence,
            repair_attempts=self._attempts,
            repaired_ir=repaired_ir,
            revalidation=revalidation,
        )

    def run(self, repair_provider: Callable[[SemanticRepairRequest], object]) -> SemanticRepairResult:
        """Attempt repair at most once, then revalidate every existing pipeline layer."""

        if not callable(repair_provider):
            raise TypeError("repair_provider must be callable")
        if self.initial.evidence.evaluator_outcome == "PASS":
            return self._result(RepairOutcome.NO_REPAIR_NEEDED, attempted=False, provider_calls=0)
        if self._attempts >= MAX_REPAIR_ATTEMPTS:
            return self._result(
                RepairOutcome.REPAIR_BUDGET_EXHAUSTED,
                attempted=False,
                provider_calls=0,
            )
        self._attempts += 1
        if (
            self.initial.evidence.first_failure_layer != "EVALUATOR"
            or self.initial.evidence.evaluator_outcome != "FAIL"
            or self.initial.validated_ir is None
            or self.initial.report is None
        ):
            return self._result(RepairOutcome.REPAIR_NOT_ELIGIBLE, attempted=False, provider_calls=0)

        request = SemanticRepairRequest(
            original_request=build_model_facing_request(self.context, language=self.language),
            candidate=self.initial.validated_ir.value,
            diagnostics=_initial_diagnostics(self.initial),
            repair_contract=build_semantic_repair_contract(
                SEMANTIC_IR_V2_VERSION
                if self.context.contract_profile == "generalization_v2"
                else SEMANTIC_IR_VERSION,
                language=self.language,
            ),
        )
        try:
            response = repair_provider(request)
        except Exception:
            return self._result(
                RepairOutcome.REPAIR_UNAVAILABLE,
                attempted=True,
                provider_calls=1,
                furthest_layer="PROVIDER",
            )
        try:
            payload = _json_payload(response)
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._result(
                RepairOutcome.REPAIR_FAILED_STRUCTURAL,
                attempted=True,
                provider_calls=1,
                furthest_layer="JSON",
            )
        try:
            repaired = parse_semantic_ir(payload)
        except (SemanticIRShapeError, TypeError, ValueError):
            return self._result(
                RepairOutcome.REPAIR_FAILED_STRUCTURAL,
                attempted=True,
                provider_calls=1,
                furthest_layer="IR_PARSE",
            )
        try:
            validated = validate_skill_semantic_ir(repaired)
        except (SemanticIRValidationError, TypeError, ValueError):
            return self._result(
                RepairOutcome.REPAIR_FAILED_STRUCTURAL,
                attempted=True,
                provider_calls=1,
                furthest_layer="IR_VALIDATION",
            )
        assert isinstance(validated, ValidatedSkillSemanticIR)

        revalidation = run_fake_pipeline(
            FakeProvider(validated.value.to_mapping()),
            self.context,
            self.evaluation_context,
            repo_root=self.repo_root,
            compiler_registry=self.compiler_registry,
            sample_index=self.initial.evidence.sample_index,
            target_sample_count=self.initial.evidence.identity.target_sample_count,
            cohort_purpose=self.initial.evidence.identity.cohort_purpose,
            experiment=self.initial.evidence.identity.experiment,
        )
        repaired_outcome = revalidation.evidence.evaluator_outcome
        repaired_diagnostics = revalidation.evidence.evaluator_diagnostics
        if revalidation.evidence.first_failure_layer is None:
            outcome = RepairOutcome.REPAIR_SUCCESS
        elif revalidation.evidence.first_failure_layer == "EVALUATOR":
            outcome = RepairOutcome.REPAIR_FAILED_SEMANTIC
        else:
            outcome = RepairOutcome.REPAIR_FAILED_STRUCTURAL
        return self._result(
            outcome,
            attempted=True,
            provider_calls=1,
            furthest_layer=_furthest_layer(revalidation),
            repaired_evaluator_outcome=repaired_outcome,
            repaired_diagnostics=repaired_diagnostics,
            repaired_ir=validated.value,
            revalidation=revalidation,
        )


def validate_semantic_repair_evidence(payload: Mapping[str, object]) -> None:
    """Validate the safe repair evidence allowlist without reading raw material."""

    required = {
        "evidence_version",
        "identity",
        "initial_evaluator_outcome",
        "initial_diagnostics",
        "repair_attempted",
        "repair_provider_calls",
        "repair_pipeline_furthest_layer",
        "repaired_evaluator_outcome",
        "repaired_diagnostics",
        "final_outcome",
        "sanitization",
    }
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise ValueError("SEMANTIC_REPAIR_EVIDENCE_SCHEMA_INVALID")
    identity = payload["identity"]
    if not isinstance(identity, Mapping) or set(identity) != {
        "source_commit",
        "original_run_id",
        "case_id",
        "generation_contract_digest",
        "context_digest",
        "repair_contract_version",
        "repair_attempt_index",
    }:
        raise ValueError("SEMANTIC_REPAIR_IDENTITY_INVALID")
    try:
        SemanticRepairIdentity(**dict(identity))
        initial_diagnostics = SafeEvaluatorDiagnostics.from_mapping(payload["initial_diagnostics"])
        repaired_raw = payload["repaired_diagnostics"]
        repaired_diagnostics = (
            None
            if repaired_raw is None
            else SafeEvaluatorDiagnostics.from_mapping(repaired_raw)
        )
        final_outcome = RepairOutcome(payload["final_outcome"])
    except (TypeError, ValueError):
        raise ValueError("SEMANTIC_REPAIR_EVIDENCE_INVALID") from None
    del initial_diagnostics, repaired_diagnostics
    if payload["evidence_version"] != SEMANTIC_REPAIR_EVIDENCE_VERSION:
        raise ValueError("SEMANTIC_REPAIR_EVIDENCE_VERSION_INVALID")
    if payload["initial_evaluator_outcome"] not in {"PASS", "REPAIR", "FAIL", "NOT_RUN"}:
        raise ValueError("SEMANTIC_REPAIR_OUTCOME_INVALID")
    if payload["repaired_evaluator_outcome"] not in {"PASS", "REPAIR", "FAIL", "NOT_RUN"}:
        raise ValueError("SEMANTIC_REPAIR_OUTCOME_INVALID")
    if not isinstance(payload["repair_attempted"], bool):
        raise ValueError("SEMANTIC_REPAIR_ATTEMPT_INVALID")
    calls = payload["repair_provider_calls"]
    if isinstance(calls, bool) or calls not in {0, 1}:
        raise ValueError("SEMANTIC_REPAIR_CALL_COUNT_INVALID")
    layer = payload["repair_pipeline_furthest_layer"]
    if layer is not None and layer not in FIRST_FAILURE_LAYERS:
        raise ValueError("SEMANTIC_REPAIR_LAYER_INVALID")
    if payload["repair_attempted"] != (calls == 1):
        raise ValueError("SEMANTIC_REPAIR_ATTEMPT_INVALID")
    sanitization = payload["sanitization"]
    if sanitization != {
        "raw_candidate_stored": False,
        "raw_prompt_stored": False,
        "raw_response_stored": False,
        "secrets_detected": False,
    }:
        raise ValueError("SEMANTIC_REPAIR_SANITIZATION_INVALID")
    if final_outcome is RepairOutcome.REPAIR_SUCCESS:
        if payload["repaired_evaluator_outcome"] != "PASS" or payload["repaired_diagnostics"] is None:
            raise ValueError("SEMANTIC_REPAIR_SUCCESS_INVALID")
    if final_outcome is RepairOutcome.NO_REPAIR_NEEDED and payload["repair_attempted"]:
        raise ValueError("SEMANTIC_REPAIR_NOOP_INVALID")


__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "RepairOutcome",
    "SEMANTIC_REPAIR_CONTRACT_VERSION",
    "SEMANTIC_REPAIR_CONTRACT_VERSION_V2",
    "SEMANTIC_REPAIR_CONTRACT_VERSION_V2_HISTORICAL",
    "SEMANTIC_REPAIR_CONTRACT_VERSION_V2_LEGACY",
    "SEMANTIC_REPAIR_CONTRACT_VERSION_V2_PRIOR",
    "SEMANTIC_REPAIR_EVIDENCE_VERSION",
    "SEMANTIC_IR_VERSION",
    "SemanticRepairContract",
    "SemanticRepairEvidence",
    "SemanticRepairIdentity",
    "SemanticRepairRequest",
    "SemanticRepairResult",
    "SemanticRepairSession",
    "build_semantic_repair_contract",
    "validate_semantic_repair_evidence",
]
