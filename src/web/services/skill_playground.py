from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from character_intelligence.hybrid_ir.playground import (
    BASIC_PASSIVE_FAMILY,
    FAMILY_CHOICES,
    MODE_CHOICES,
    execute_playground,
    resolve_family,
    run_playground_context_pipeline,
)
from character_intelligence.hybrid_ir.projection import HybridGenerationContext
from character_intelligence.hybrid_ir.runner import (
    FakeProvider,
    HybridProvider,
    HybridProviderInvocationError,
    live_hybrid_provider_from_environment,
)
from character_intelligence.skill_artifact import (
    SkillDesignArtifact,
    build_skill_design_artifact_from_pipeline_result,
    current_skill_artifact_versions,
    inspect_skill_artifact_compatibility,
)

from ..errors import WebApplicationError
from ..schemas.common import PipelineStepDTO
from ..schemas.skills import (
    SkillEvaluationDTO,
    SkillFamilyOptionDTO,
    SkillPlaygroundMetaDTO,
    SkillPlaygroundRequestDTO,
    SkillPlaygroundResponseDTO,
    SkillProviderDTO,
)
from .live_jobs import LiveJobRegistry, LiveJobSnapshot

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_PRESETS = {
    "support": "generalization_support_alternate_v1",
    "main_dps": "generalization_dps_v1",
    "control": "generalization_control_v1",
    "healer": "generalization_reaction_heal_v1",
    "sub_dps": "generalization_sub_dps_v1",
    "defense": "generalization_defense_v1",
    "basic_passive": "generalization_basic_passive_v1",
    "alignment_support": "character_alignment_support_v1",
    "alignment_main_dps": "character_alignment_main_dps_v1",
    "alignment_control": "character_alignment_control_v1",
}
_CONTROLLED_PRESETS = {
    "character_support_skill_v1": "character_alignment_support_v1",
    "character_defense_skill_v1": "generalization_defense_v1",
    "character_basic_passive_skill_v1": "generalization_basic_passive_v1",
}
_FINAL_PRESET_IDS = frozenset(
    {
        "generalization_sub_dps_v1",
        "generalization_defense_v1",
        "generalization_basic_passive_v1",
        "character_alignment_support_v1",
        "character_alignment_main_dps_v1",
        "character_alignment_control_v1",
    }
)
_FAMILY_LABELS = {
    "main_dps": ("Main DPS", "direct output and enemy pressure"),
    "sub_dps": ("Sub-DPS", "follow-up output after allied actions"),
    "support": ("Support", "ally enablement and team utility"),
    "healer": ("Reaction / Healer", "recover or mitigate ally damage"),
    "control": ("Control", "control enemy actions"),
    "defense": ("Defense", "protect allies and manage threats"),
    "basic_passive": ("Basic Passive", "always-on passive utility"),
}


class SkillPlaygroundApplication:
    """Web-safe adapter over the shared Skill Design v1 application seam."""

    def __init__(
        self,
        *,
        provider_factory: Callable[[str], HybridProvider] | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.repo_root = Path(repo_root) if repo_root is not None else _discover_repo_root()

    def meta(self) -> SkillPlaygroundMetaDTO:
        families = []
        for family in FAMILY_CHOICES:
            label, description = _FAMILY_LABELS[family]
            role, mode = resolve_family(
                family, "passive" if family == BASIC_PASSIVE_FAMILY else "active"
            )
            families.append(
                SkillFamilyOptionDTO(
                    id=family,
                    label=label,
                    description=description,
                    role=role,
                    default_mode=mode,
                )
            )
        return SkillPlaygroundMetaDTO(
            schema_version="web-skill-playground-meta/0.1",
            families=families,
            modes=list(MODE_CHOICES),
            examples=[*_PRESETS.values(), *_CONTROLLED_PRESETS],
            provider_mode="injected" if self.provider_factory else "offline_fixture",
        )

    def run(self, request: SkillPlaygroundRequestDTO) -> SkillPlaygroundResponseDTO:
        try:
            provider_mode = self._provider_mode(request)
            provider = self.provider_for(request)
            requirement = _requirement(request)
            execution = execute_playground(
                provider,
                request.family,
                request.mode,
                requirement,
                model=request.model,
                language=request.language,
                repo_root=self.repo_root,
            )
        except WebApplicationError:
            raise
        except HybridProviderInvocationError as error:
            raise WebApplicationError(
                "PROVIDER_TIMEOUT" if error.outcome == "TIMEOUT" else "PROVIDER_CONNECTION_FAILURE",
                "The model provider timed out after its bounded provider budget."
                if error.outcome == "TIMEOUT"
                else "The model provider could not be reached.",
                status_code=504 if error.outcome == "TIMEOUT" else 503,
                stage="provider",
                retryable=True,
            ) from None
        except Exception as error:
            raise WebApplicationError(
                "SKILL_PLAYGROUND_UNAVAILABLE",
                "The Skill Playground provider could not complete the request.",
                status_code=503,
                stage="provider",
                retryable=True,
            ) from error
        return self.response_from_result(request, execution.final, provider, provider_mode)

    def submit_live_job(
        self,
        request: SkillPlaygroundRequestDTO,
        registry: LiveJobRegistry,
    ) -> LiveJobSnapshot:
        if request.execution_mode != "live":
            raise WebApplicationError(
                "LIVE_EXECUTION_MODE_REQUIRED",
                "Live jobs require execution_mode=live.",
                status_code=422,
                stage="live_execution",
                retryable=False,
            )
        return registry.submit(
            kind="skill_playground",
            provider=request.provider,
            model=request.model,
            work=lambda: self.run(request),
        )

    def run_context(
        self,
        request: SkillPlaygroundRequestDTO,
        context: HybridGenerationContext,
        evaluation_context: Mapping[str, object],
    ) -> SkillPlaygroundResponseDTO:
        """Run a caller-built context through the same Skill pipeline."""

        try:
            provider_mode = self._provider_mode(request)
            provider = self.provider_for(request)
            result = run_playground_context_pipeline(
                provider,
                context,
                dict(evaluation_context),
                model=request.model,
                language=request.language,
                repo_root=self.repo_root,
            )
        except WebApplicationError:
            raise
        except Exception as error:
            raise WebApplicationError(
                "SKILL_PLAYGROUND_UNAVAILABLE",
                "The Skill Playground provider could not complete the request.",
                status_code=503,
                stage="provider",
                retryable=True,
            ) from error
        return self.response_from_result(request, result, provider, provider_mode)

    def provider_for(self, request: SkillPlaygroundRequestDTO) -> HybridProvider:
        """Resolve the configured Web provider without exposing fixture details."""

        if request.execution_mode == "live":
            if self.provider_factory is not None:
                return self.provider_factory(request.model)
            try:
                return live_hybrid_provider_from_environment(
                    provider=request.provider,
                    model=request.model,
                )
            except Exception as error:
                raise WebApplicationError(
                    "SKILL_PLAYGROUND_LIVE_CONFIGURATION_INVALID",
                    "The backend live provider is not configured for this request.",
                    status_code=503,
                    stage="provider",
                    retryable=False,
                ) from error
        return (
            self.provider_factory(request.model)
            if self.provider_factory is not None
            else _fixture_provider(request.preset_id, self.repo_root)
        )

    def _provider_mode(self, request: SkillPlaygroundRequestDTO) -> str:
        if request.execution_mode == "live":
            return "live"
        return "injected" if self.provider_factory is not None else "offline_fixture"

    @staticmethod
    def response_from_result(
        request: SkillPlaygroundRequestDTO,
        result: Any,
        provider: HybridProvider,
        provider_mode: str,
        artifact: SkillDesignArtifact | None = None,
    ) -> SkillPlaygroundResponseDTO:
        """Project one shared pipeline result into the existing Web contract."""

        evidence = result.evidence
        if evidence.first_failure_layer == "PROVIDER":
            failure_code = evidence.failure_code
            provider_error_kind = getattr(provider, "provider_error_kind", None)
            if failure_code == "PROVIDER_TIMEOUT" or provider_error_kind == "timeout":
                raise WebApplicationError(
                    "PROVIDER_TIMEOUT",
                    "The model provider timed out after its bounded provider budget.",
                    status_code=504,
                    stage="provider",
                    retryable=True,
                    details={
                        key: value
                        for key, value in {
                            "provider": getattr(provider, "provider", None),
                            "model": getattr(provider, "model", None),
                        }.items()
                        if isinstance(value, str) and value
                    },
                )
            if provider_error_kind == "rate_limit":
                raise WebApplicationError(
                    "PROVIDER_RATE_LIMITED",
                    "The model provider rate-limited the request.",
                    status_code=503,
                    stage="provider",
                    retryable=True,
                )
            if provider_error_kind == "provider":
                raise WebApplicationError(
                    "PROVIDER_CONNECTION_FAILURE",
                    "The model provider could not be reached.",
                    status_code=503,
                    stage="provider",
                    retryable=True,
                )
            raise WebApplicationError(
                "SKILL_PLAYGROUND_PROVIDER_FAILURE",
                "The Skill Playground provider did not return a usable result.",
                status_code=503,
                stage="provider",
                retryable=True,
            )
        if artifact is None and result.candidate and result.report and result.validated_ir:
            artifact = build_skill_design_artifact_from_pipeline_result(result)
        report = artifact.original_evaluation if artifact is not None else result.report
        semantic_ir = (
            artifact.semantic_source.to_mapping()
            if artifact is not None
            else (result.validated_ir.value.to_mapping() if result.validated_ir else None)
        )
        skillkit = (
            artifact.canonical_artifact.to_mapping()
            if artifact is not None
            else (result.candidate.to_mapping() if result.candidate else None)
        )
        evaluation = SkillEvaluationDTO(
            outcome=report.outcome if report else "NOT_RUN",
            blocking=report.blocking if report else True,
            repair_allowed=report.repair_allowed if report else False,
            findings=[_finding(item) for item in report.findings] if report else [],
            candidate_digest=(
                artifact.artifact_digest
                if artifact is not None
                else (report.candidate_digest if report else evidence.candidate_digest)
            ),
            report_digest=report.report_digest if report else None,
            diagnostics=(
                evidence.evaluator_diagnostics.to_mapping()
                if evidence.evaluator_diagnostics is not None
                else None
            ),
        )
        compatibility = (
            inspect_skill_artifact_compatibility(
                artifact.versions,
                current_skill_artifact_versions(),
            ).status.value
            if artifact is not None
            else None
        )
        return SkillPlaygroundResponseDTO(
            schema_version="web-skill-playground/0.1",
            status="completed" if evaluation.outcome == "PASS" else "failed",
            input=request,
            semantic_ir=semantic_ir,
            skillkit=skillkit,
            evaluation=evaluation,
            pipeline=_pipeline(evidence.first_failure_layer),
            provider=SkillProviderDTO(
                mode=provider_mode,
                called=evidence.fake_provider_called,
                outcome=(
                    getattr(provider, "outcome", "SUCCESS")
                    if provider_mode == "live"
                    else (
                        evidence.identity.provider
                        if not evidence.fake_provider_called
                        else "SUCCESS"
                    )
                ),
                transport_attempts=evidence.fake_transport_attempts,
                latency_ms=getattr(provider, "latency_ms", None),
            ),
            evidence=_safe_evidence(evidence.to_mapping()),
            artifact_versions=(artifact.versions.to_mapping() if artifact is not None else None),
            artifact_compatibility=compatibility,
        )


def _requirement(request: SkillPlaygroundRequestDTO) -> str:
    constraints = "\n".join(f"- {item}" for item in request.constraints)
    return request.brief if not constraints else f"{request.brief}\n\nConstraints:\n{constraints}"


def _discover_repo_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json").is_file():
            return candidate
    return _PACKAGE_ROOT


def _fixture_provider(preset_id: str | None, repo_root: Path) -> HybridProvider:
    fixture_id = _CONTROLLED_PRESETS.get(preset_id, preset_id)
    if fixture_id not in _PRESETS.values():
        raise WebApplicationError(
            "SKILL_PLAYGROUND_UNAVAILABLE",
            "Select an offline fixture preset or configure an injected provider.",
            status_code=503,
            stage="provider",
            retryable=False,
        )
    filename = (
        "hybrid_final_coverage_v2_goldens.json"
        if fixture_id in _FINAL_PRESET_IDS
        else "hybrid_multi_case_generalization_goldens.json"
    )
    path = repo_root / "tests" / "fixtures" / filename
    values = json.loads(path.read_text(encoding="utf-8"))
    return FakeProvider(values[fixture_id])


def _finding(finding: Any) -> dict[str, Any]:
    return {
        "code": finding.code,
        "field_path": finding.field_path,
        "blocking": finding.blocking,
        "repairable": finding.repairable,
        "evidence_refs": list(finding.evidence_refs),
        "priority": finding.priority,
    }


def _pipeline(first_failure: str | None) -> list[PipelineStepDTO]:
    layers = (
        ("provider", "Provider"),
        ("json", "JSON parse"),
        ("ir_parse", "Semantic IR parse"),
        ("ir_validation", "IR validation"),
        ("compiler", "Deterministic compiler"),
        ("canonical_parser", "Canonical parser"),
        ("reference_integrity", "Reference integrity"),
        ("evaluator", "Evaluator"),
    )
    failed_index = None
    if first_failure:
        names = [name.upper() for name, _label in layers]
        normalized = first_failure.lower()
        normalized = "ir_parse" if normalized == "ir_parse" else normalized
        failed_index = names.index(first_failure) if first_failure in names else None
    steps = []
    for index, (step_id, label) in enumerate(layers):
        if failed_index is None:
            status = "passed"
        elif index < failed_index:
            status = "passed"
        elif index == failed_index:
            status = "failed"
        else:
            status = "skipped"
        steps.append(PipelineStepDTO(id=step_id, label=label, status=status, detail=None))
    return steps


def _safe_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    identity = value.get("identity", {})
    safe_identity = {
        key: identity[key]
        for key in (
            "experiment",
            "ir_schema_version",
            "model_facing_contract_version",
            "compiler_version",
            "canonical_schema_version",
            "model",
        )
        if key in identity
    }
    return {
        "run_id": value.get("run_id"),
        "first_failure_layer": value.get("first_failure_layer"),
        "failure_code": value.get("failure_code"),
        "principal_verdict": value.get("principal_verdict"),
        "semantic_ir_digest": value.get("semantic_ir_digest"),
        "candidate_digest": value.get("candidate_digest"),
        "diagnostics": value.get("diagnostics"),
        "evaluator_diagnostics": value.get("evaluator_diagnostics"),
        "identity": safe_identity,
    }


__all__ = ["SkillPlaygroundApplication"]
