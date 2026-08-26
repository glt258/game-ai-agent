"""Reproducible, sanitized CS-S2 shadow-evidence runner.

The runner deliberately keeps the provider seam smaller than the legacy
authoring seam.  Legacy generation is always deterministic in this module;
only the independent ``character_skill_kit`` call is delegated to the
injected model.  The default entry point is a dry-run and never constructs a
provider factory or writes an evidence result.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.character_generation import (  # noqa: E402
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
)
from agents.model_factory import character_model_from_environment  # noqa: E402
from agents.models import (  # noqa: E402
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    SkillShadowConfig,
)
from character_skill import (  # noqa: E402
    SkillValidationContext,
    evaluate,
)
from character_skill.errors import (  # noqa: E402
    CANONICAL_ROOT_FIELDS,
    SHAPE_DIAGNOSTIC_ERROR_CODES,
    SHAPE_DIAGNOSTIC_MAX_ERRORS,
    SHAPE_DIAGNOSTIC_MAX_FIELDS,
    SHAPE_DIAGNOSTIC_MAX_KEYS,
    SHAPE_DIAGNOSTIC_STAGES,
    SkillKitShapeDiagnostic,
)
from combat_semantics import CombatRoleProfile  # noqa: E402

PROTOCOL_VERSION = "0.2.1"
MANIFEST_SCHEMA_VERSION = "character-skill-s2-shadow-evidence-manifest/0.2.1"
EVIDENCE_SCHEMA_VERSION = "character-skill-s2-shadow-evidence/0.2.1"
RETRY_SCHEMA_VERSION = "character-skill-s2-shadow-retry-unavailable/0.1.0"
RETRY_COHORT_TYPE = "retry_unavailable"
RETRY_LINEAGE_POLICY = "one_retry_per_unavailable_source_observation"
PROVIDER_NAME = "opencode_go"
MODEL_REQUESTED = "deepseek-v4-flash"
TRANSPORT = "openai_chat_completions"
STRUCTURED_OUTPUT_MODE = "json_object"
RESPONSE_CONTRACT = "character_skill_kit"
CANDIDATE_SCHEMA_VERSION = "skill-kit-candidate/0.1.1"
TIMEOUT_SECONDS = 30
MAX_TRANSPORT_RETRIES = 2
SMOKE_CASES = ("case_01", "case_13", "case_19")
CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 20))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CASE_RE = re.compile(r"^case_(?:0[1-9]|1[0-9])$")
_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-deepseek-v0\.2\.1-[0-9a-f]{40}-[0-9a-f]{12}-run-0[1-3]$"
)
_RETRY_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-deepseek-retry-unavailable-v0\.2\.1-[0-9a-f]{40}-[0-9a-f]{12}-cohort-01$"
)
_SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_FAILURE_STAGES = {None, "context", "provider", "json", "shape", "validation", "runner"}
_FAILURE_CODES = {
    None,
    "CONTEXT_INVALID",
    "PROVIDER_INVOCATION_FAILED",
    "RESPONSE_JSON_INVALID",
    "CANDIDATE_SHAPE_REJECTED",
    "EVALUATION_FAILED",
    "RUNNER_FAILURE",
}

MANIFEST_RELATIVE_PATH = (
    "evals/fixtures/character_skill_s2_shadow_evidence_manifest_v0.2.1.json"
)
OUTPUT_SCHEMA_RELATIVE_PATH = (
    "evals/fixtures/character_skill_s2_shadow_evidence_output_schema_v0.2.1.json"
)
RESULT_RELATIVE_TEMPLATE = (
    "evals/results/character_skill_s2_shadow_deepseek_run_{repeat:02d}_v0.2.1.json"
)
TEMP_RELATIVE_TEMPLATE = (
    "evals/results/.character_skill_s2_shadow_deepseek_run_{repeat:02d}_v0.2.1.json.tmp"
)
RETRY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_deepseek_retry_unavailable_run_01_v0.2.1.json"
)
RETRY_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_deepseek_retry_unavailable_run_01_v0.2.1.json.tmp"
)
DIAGNOSTIC_SCHEMA_VERSION = "character-skill-s2-shadow-shape-diagnostic/0.1.0"
DIAGNOSTIC_COHORT_TYPE = "shape_diagnostic"
DIAGNOSTIC_LINEAGE_POLICY = "diagnoses_retry_observation_without_replacement"
DIAGNOSTIC_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_shape_diagnostic_case_13_run_01_v0.1.0.json"
)
DIAGNOSTIC_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_shape_diagnostic_case_13_run_01_v0.1.0.json.tmp"
)
_DIAGNOSTIC_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-deepseek-shape-diagnostic-v0\.1\.0-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)


class EvidenceRunnerError(RuntimeError):
    """Stable, user-facing runner failure without raw provider material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvidenceContractError(EvidenceRunnerError):
    """Evidence bundle or resume data violates the closed contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_mapping(value: Mapping[str, object]) -> str:
    return _digest_bytes(_canonical_json(value).encode("utf-8"))


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise EvidenceRunnerError("FIXTURE_UNAVAILABLE") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceRunnerError("FIXTURE_JSON_INVALID") from error
    if not isinstance(payload, dict):
        raise EvidenceRunnerError("FIXTURE_ROOT_NOT_OBJECT")
    return payload, raw


def _exact_keys(value: Mapping[str, object], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise EvidenceContractError(code)


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _safe_model_name(value: object) -> str | None:
    if isinstance(value, str) and _SAFE_MODEL_RE.fullmatch(value):
        return value
    return None


def _safe_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise EvidenceRunnerError("INPUT_PATH_INVALID")
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise EvidenceRunnerError("INPUT_PATH_OUTSIDE_REPOSITORY")
    return candidate


@dataclass(frozen=True)
class ShadowEvidenceManifest:
    protocol_version: str
    raw_digest: str
    input_files: tuple[dict[str, str], ...]
    output_schema_path: str
    output_schema_digest: str
    provider: dict[str, object]
    case_order: tuple[str, ...]
    smoke_cases: tuple[str, ...]
    repeat_count: int


@dataclass(frozen=True)
class ShadowEvidenceCase:
    case_id: str
    brief: str
    hard_constraints: tuple[str, ...]
    forbidden_elements: tuple[str, ...]
    combat_role_profile: CombatRoleProfile | None
    context: SkillValidationContext

    def request(self) -> CharacterDesignRequest:
        return CharacterDesignRequest(
            self.brief,
            hard_constraints=self.hard_constraints,
            forbidden_elements=self.forbidden_elements,
            request_id=f"s2_{self.case_id}",
            combat_role_profile=self.combat_role_profile,
        )


@dataclass(frozen=True)
class _ShadowProjectionView:
    """Four-field view used by the remote candidate seam."""

    brief: str
    hard_constraints: tuple[str, ...]
    forbidden_elements: tuple[str, ...]
    combat_role_profile: Mapping[str, object] | None


def _role_mapping(profile: object) -> dict[str, object] | None:
    if profile is None:
        return None
    if isinstance(profile, CombatRoleProfile):
        return profile.to_dict()
    if isinstance(profile, Mapping):
        return dict(profile)
    to_dict = getattr(profile, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, Mapping):
            return dict(value)
    raise EvidenceRunnerError("ROLE_PROJECTION_INVALID")


class ShadowEvidenceModelRouter:
    """Route legacy prompts locally and sanitize the independent shadow seam.

    Only the last shadow invocation audit and a derived shape boolean are
    retained.  Model turns, text, candidates, and provider payloads are never
    cached by the router.
    """

    __slots__ = (
        "legacy_model",
        "shadow_model",
        "_shadow_invocation",
        "_shadow_response_compliant",
    )

    def __init__(self, shadow_model: Any, *, legacy_model: Any | None = None) -> None:
        if shadow_model is None or not callable(getattr(shadow_model, "generate", None)):
            raise TypeError("shadow_model must provide generate(prompt)")
        self.legacy_model = legacy_model or DeterministicCharacterGenerationModel()
        self.shadow_model = shadow_model
        self._shadow_invocation: ModelInvocationAudit | None = None
        self._shadow_response_compliant = False

    @property
    def shadow_invocation(self) -> ModelInvocationAudit | None:
        return self._shadow_invocation

    @property
    def shadow_response_compliant(self) -> bool:
        return self._shadow_response_compliant

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        if (
            prompt.invocation_purpose != "character_skill_shadow"
            or prompt.response_format != RESPONSE_CONTRACT
        ):
            return self.legacy_model.generate(prompt)

        self._shadow_invocation = None
        self._shadow_response_compliant = False
        projection = self._rebuild_shadow_prompt(prompt)
        try:
            turn = self.shadow_model.generate(projection)
        except Exception as error:
            audit = getattr(error, "audit", None)
            self._shadow_invocation = (
                audit if isinstance(audit, ModelInvocationAudit) else None
            )
            raise
        invocation = getattr(turn, "invocation", None)
        self._shadow_invocation = (
            invocation if isinstance(invocation, ModelInvocationAudit) else None
        )
        self._shadow_response_compliant = getattr(turn, "structured_output", None) is not None
        return turn

    @staticmethod
    def _rebuild_shadow_prompt(prompt: AgentPrompt) -> AgentPrompt:
        runtime = prompt.runtime
        projection = {
            "brief": str(getattr(runtime, "brief", "")),
            "hard_constraints": list(getattr(runtime, "hard_constraints", ())),
            "forbidden_elements": list(getattr(runtime, "forbidden_elements", ())),
            "combat_role_profile": _role_mapping(
                getattr(runtime, "combat_role_profile", None)
            ),
        }
        view = _ShadowProjectionView(
            projection["brief"],
            tuple(projection["hard_constraints"]),
            tuple(projection["forbidden_elements"]),
            projection["combat_role_profile"],
        )
        message = ConversationMessage(
            "user",
            _canonical_json(projection),
        )
        return AgentPrompt(
            "Return one direct Character SkillKit candidate root JSON object.",
            view,
            view,
            (message,),
            (),
            "cs-s2-shadow",
            1,
            response_format=RESPONSE_CONTRACT,
            authoring_payload=projection,
            invocation_purpose="character_skill_shadow",
        )


def _validate_manifest_payload(
    payload: Mapping[str, object], root: Path, raw: bytes, schema_payload: Mapping[str, object]
) -> ShadowEvidenceManifest:
    expected_keys = {
        "schema_version",
        "protocol_version",
        "input_files",
        "output_schema",
        "provider",
        "case_order",
        "smoke_cases",
        "repeat_count",
    }
    _exact_keys(payload, expected_keys, "MANIFEST_KEYS_INVALID")
    if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise EvidenceRunnerError("MANIFEST_SCHEMA_VERSION_MISMATCH")
    if payload["protocol_version"] != PROTOCOL_VERSION:
        raise EvidenceRunnerError("MANIFEST_PROTOCOL_VERSION_MISMATCH")

    input_files_raw = payload["input_files"]
    if not isinstance(input_files_raw, list) or not input_files_raw:
        raise EvidenceRunnerError("MANIFEST_INPUTS_INVALID")
    input_files: list[dict[str, str]] = []
    for item in input_files_raw:
        if not isinstance(item, Mapping):
            raise EvidenceRunnerError("MANIFEST_INPUTS_INVALID")
        _exact_keys(item, {"path", "sha256", "role"}, "MANIFEST_INPUT_ENTRY_INVALID")
        path = item["path"]
        digest = item["sha256"]
        role = item["role"]
        if (
            not isinstance(path, str)
            or not _is_sha(digest)
            or role not in {"provider", "evaluator"}
        ):
            raise EvidenceRunnerError("MANIFEST_INPUT_ENTRY_INVALID")
        file_path = _safe_path(root, path)
        if not file_path.is_file():
            raise EvidenceRunnerError("INPUT_DIGEST_MISMATCH")
        try:
            file_digest = _digest_bytes(file_path.read_bytes())
        except OSError as error:
            raise EvidenceRunnerError("INPUT_DIGEST_MISMATCH") from error
        if file_digest != digest:
            raise EvidenceRunnerError("INPUT_DIGEST_MISMATCH")
        input_files.append({"path": path, "sha256": digest, "role": role})

    if len(input_files) != 2 or {item["role"] for item in input_files} != {
        "provider",
        "evaluator",
    }:
        raise EvidenceRunnerError("MANIFEST_INPUT_ROLES_INVALID")

    schema_raw = payload["output_schema"]
    if not isinstance(schema_raw, Mapping):
        raise EvidenceRunnerError("MANIFEST_OUTPUT_SCHEMA_INVALID")
    _exact_keys(schema_raw, {"path", "sha256"}, "MANIFEST_OUTPUT_SCHEMA_INVALID")
    schema_path = schema_raw["path"]
    schema_digest = schema_raw["sha256"]
    if not isinstance(schema_path, str) or not _is_sha(schema_digest):
        raise EvidenceRunnerError("MANIFEST_OUTPUT_SCHEMA_INVALID")
    schema_file = _safe_path(root, schema_path)
    if not schema_file.is_file():
        raise EvidenceRunnerError("SCHEMA_DIGEST_MISMATCH")
    try:
        schema_file_digest = _digest_bytes(schema_file.read_bytes())
    except OSError as error:
        raise EvidenceRunnerError("SCHEMA_DIGEST_MISMATCH") from error
    if schema_file_digest != schema_digest:
        raise EvidenceRunnerError("SCHEMA_DIGEST_MISMATCH")
    if schema_payload.get("$id") != EVIDENCE_SCHEMA_VERSION:
        raise EvidenceRunnerError("SCHEMA_ID_MISMATCH")

    provider_raw = payload["provider"]
    if not isinstance(provider_raw, Mapping):
        raise EvidenceRunnerError("MANIFEST_PROVIDER_INVALID")
    _exact_keys(
        provider_raw,
        {
            "name",
            "model_requested",
            "transport",
            "structured_output_mode",
            "response_contract",
            "candidate_schema_version",
            "timeout_seconds",
            "max_transport_retries",
        },
        "MANIFEST_PROVIDER_INVALID",
    )
    provider = dict(provider_raw)
    locked_provider = {
        "name": PROVIDER_NAME,
        "model_requested": MODEL_REQUESTED,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_transport_retries": MAX_TRANSPORT_RETRIES,
    }
    if provider != locked_provider:
        raise EvidenceRunnerError("PROVIDER_PROFILE_MISMATCH")

    case_order = payload["case_order"]
    smoke_cases = payload["smoke_cases"]
    repeat_count = payload["repeat_count"]
    expected_order = SMOKE_CASES + tuple(item for item in CASE_IDS if item not in SMOKE_CASES)
    if (
        not isinstance(case_order, list)
        or tuple(case_order) != expected_order
        or not isinstance(smoke_cases, list)
        or tuple(smoke_cases) != SMOKE_CASES
        or isinstance(repeat_count, bool)
        or repeat_count != 3
    ):
        raise EvidenceRunnerError("MANIFEST_COHORT_INVALID")
    return ShadowEvidenceManifest(
        protocol_version=PROTOCOL_VERSION,
        raw_digest=_digest_bytes(raw),
        input_files=tuple(input_files),
        output_schema_path=schema_path,
        output_schema_digest=schema_digest,
        provider=provider,
        case_order=tuple(case_order),
        smoke_cases=tuple(smoke_cases),
        repeat_count=repeat_count,
    )


def load_manifest(
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> ShadowEvidenceManifest:
    root = Path(repo_root or ROOT).resolve()
    path = Path(manifest_path) if manifest_path is not None else root / MANIFEST_RELATIVE_PATH
    if not path.is_absolute():
        path = root / path
    payload, raw = _load_json(path)
    schema_path = root / OUTPUT_SCHEMA_RELATIVE_PATH
    if isinstance(payload.get("output_schema"), Mapping):
        candidate = payload["output_schema"].get("path")
        if isinstance(candidate, str):
            schema_path = _safe_path(root, candidate)
    schema_payload, _ = _load_json(schema_path)
    return _validate_manifest_payload(payload, root, raw, schema_payload)


def _load_cases(root: Path, manifest: ShadowEvidenceManifest) -> dict[str, ShadowEvidenceCase]:
    by_role = {item["role"]: item["path"] for item in manifest.input_files}
    provider_path = by_role.get("provider")
    evaluator_path = by_role.get("evaluator")
    if provider_path is None or evaluator_path is None:
        raise EvidenceRunnerError("MANIFEST_CASE_INPUT_ROLES_INVALID")
    provider_payload, _ = _load_json(_safe_path(root, provider_path))
    evaluator_payload, _ = _load_json(_safe_path(root, evaluator_path))
    provider_cases = provider_payload.get("cases")
    evaluator_cases = evaluator_payload.get("cases")
    if not isinstance(provider_cases, list) or not isinstance(evaluator_cases, list):
        raise EvidenceRunnerError("CASE_FIXTURES_INVALID")
    provider_by_id = {item.get("case_id"): item for item in provider_cases if isinstance(item, Mapping)}
    evaluator_by_id = {item.get("case_id"): item for item in evaluator_cases if isinstance(item, Mapping)}
    if (
        len(provider_cases) != len(CASE_IDS)
        or len(evaluator_cases) != len(CASE_IDS)
        or set(provider_by_id) != set(CASE_IDS)
        or set(evaluator_by_id) != set(CASE_IDS)
    ):
        raise EvidenceRunnerError("CASE_FIXTURE_IDS_INVALID")
    cases: dict[str, ShadowEvidenceCase] = {}
    for case_id in CASE_IDS:
        provider_case = provider_by_id[case_id]
        evaluator_case = evaluator_by_id[case_id]
        request = provider_case.get("request")
        context_raw = evaluator_case.get("context")
        if not isinstance(request, Mapping) or not isinstance(context_raw, Mapping):
            raise EvidenceRunnerError("CASE_PROJECTION_INVALID")
        required_request = {"brief", "hard_constraints", "forbidden_elements", "combat_role_profile"}
        if set(request) != required_request:
            raise EvidenceRunnerError("CASE_REQUEST_KEYS_INVALID")
        brief = request["brief"]
        hard = request["hard_constraints"]
        forbidden = request["forbidden_elements"]
        if (
            not isinstance(brief, str)
            or not isinstance(hard, list)
            or not all(isinstance(item, str) for item in hard)
            or not isinstance(forbidden, list)
            or not all(isinstance(item, str) for item in forbidden)
        ):
            raise EvidenceRunnerError("CASE_REQUEST_TYPES_INVALID")
        role_raw = request["combat_role_profile"]
        try:
            role = None if role_raw is None else CombatRoleProfile.from_mapping(role_raw)
        except (TypeError, ValueError) as error:
            raise EvidenceRunnerError("CASE_ROLE_PROFILE_INVALID") from error
        try:
            context = SkillValidationContext.from_mapping(context_raw)
        except Exception as error:
            raise EvidenceRunnerError("CASE_CONTEXT_INVALID") from error
        cases[case_id] = ShadowEvidenceCase(
            case_id,
            brief,
            tuple(hard),
            tuple(forbidden),
            role,
            context,
        )
    return cases


def _failure_code(stage: str | None) -> str | None:
    return {
        None: None,
        "context": "CONTEXT_INVALID",
        "provider": "PROVIDER_INVOCATION_FAILED",
        "json": "RESPONSE_JSON_INVALID",
        "shape": "CANDIDATE_SHAPE_REJECTED",
        "validation": "EVALUATION_FAILED",
        "runner": "RUNNER_FAILURE",
    }.get(stage, "SHADOW_FAILURE")


def _normalize_field_path(path: object) -> str:
    if not isinstance(path, str) or not path:
        return "/"
    if path.startswith("/"):
        return path
    if path.startswith("context."):
        return "/context/" + path[len("context.") :].replace(".", "/")
    return "/" + path.replace(".", "/")


def _token_usage(invocation: ModelInvocationAudit | None) -> dict[str, int | None]:
    usage = invocation.usage if invocation is not None else None
    return {
        "input": getattr(usage, "input_tokens", None),
        "output": getattr(usage, "output_tokens", None),
        "total": getattr(usage, "total_tokens", None),
    }


def _bounded_latency(invocation: ModelInvocationAudit | None) -> float | int | None:
    value = getattr(invocation, "latency_ms", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return value
    return None


def _record_digest(record_body: Mapping[str, object]) -> str:
    return _digest_mapping(record_body)


def _record_from_result(
    case: ShadowEvidenceCase,
    run_id: str,
    repeat: int,
    result: Any,
    router: ShadowEvidenceModelRouter,
) -> dict[str, object]:
    shadow = result.skill_shadow
    context_digest = case.context.digest
    observation_id = f"{run_id}:{case.case_id}:repeat-{repeat:02d}"
    if shadow is None:
        observation = {
            "observation_id": observation_id,
            "case_id": case.case_id,
            "repeat": repeat,
            "draft_id": f"draft_s2_{case.case_id}",
            "transport_outcome": "failure",
            "failure_stage": "runner",
            "failure_code": "RUNNER_FAILURE",
            "shape_compliant": False,
            "parse_outcome": "not_attempted",
            "outcome": "UNAVAILABLE",
            "finding_codes": [],
            "candidate_digest": None,
            "context_digest": context_digest,
            "report_digest": None,
            "renderer_comparison": {
                "performed": False,
                "matches_legacy": None,
                "summary_code": "not_authoritative",
            },
            "legacy_impact": False,
        }
        invocation = router.shadow_invocation
        record = {
            "observation": observation,
            "audit": _audit_mapping(case.case_id, invocation, None),
            "sanitization": _sanitization_mapping(),
        }
        return {"record_digest": _record_digest(record), **record}

    report = shadow.validation_report
    findings = []
    if report is not None:
        findings = [
            {"code": item.code, "path": _normalize_field_path(item.field_path)}
            for item in report.findings
        ]
        repeated = evaluate(shadow.candidate, case.context) if shadow.candidate is not None else None
        if repeated is None or repeated.to_mapping() != report.to_mapping():
            raise EvidenceRunnerError("EVALUATION_NOT_REPRODUCIBLE")
    failure_stage = shadow.failure_stage
    invocation = router.shadow_invocation
    if invocation is None:
        audit_value = shadow.audit
        provider_outcome = getattr(audit_value, "outcome", None)
        transport_outcome = "failure" if failure_stage == "provider" else "success"
    else:
        provider_outcome = invocation.outcome
        transport_outcome = "success" if provider_outcome == "success" else "failure"
    parse_outcome = (
        "parsed"
        if shadow.candidate is not None
        else "rejected"
        if failure_stage in {"json", "shape"}
        else "not_attempted"
    )
    observation = {
        "observation_id": observation_id,
        "case_id": case.case_id,
        "repeat": repeat,
        "draft_id": shadow.draft_id,
        "transport_outcome": transport_outcome,
        "failure_stage": failure_stage,
        "failure_code": _failure_code(failure_stage),
        "shape_compliant": bool(shadow.response_compliant),
        "parse_outcome": parse_outcome,
        "outcome": report.outcome if report is not None else "UNAVAILABLE",
        "finding_codes": findings,
        "candidate_digest": report.candidate_digest if report is not None else None,
        "context_digest": context_digest,
        "report_digest": report.report_digest if report is not None else None,
        "renderer_comparison": {
            "performed": False,
            "matches_legacy": None,
            "summary_code": "not_authoritative",
        },
        "legacy_impact": False,
    }
    if shadow.shape_diagnostic is not None:
        observation["shape_diagnostic"] = shadow.shape_diagnostic.to_dict()
    record = {
        "observation": observation,
        "audit": _audit_mapping(case.case_id, invocation, provider_outcome),
        "sanitization": _sanitization_mapping(),
    }
    return {"record_digest": _record_digest(record), **record}


def _audit_mapping(
    case_id: str,
    invocation: ModelInvocationAudit | None,
    provider_outcome: object,
) -> dict[str, object]:
    request_digest = _digest_bytes(f"s2_{case_id}".encode("utf-8"))[:16]
    return {
        "redacted_request_id": f"redacted:{request_digest}",
        "retry_count": (
            invocation.retry_count
            if isinstance(getattr(invocation, "retry_count", None), int)
            else 0
        ),
        "latency_ms": _bounded_latency(invocation),
        "token_usage": _token_usage(invocation),
    }


def _sanitization_mapping() -> dict[str, bool]:
    return {
        "raw_prompt_stored": False,
        "raw_response_stored": False,
        "secrets_detected": False,
    }


def validate_evidence_bundle(bundle: Mapping[str, object]) -> None:
    """Validate the closed runtime evidence contract without jsonschema."""

    top_keys = {
        "schema_version",
        "run_id",
        "protocol_version",
        "source_commit",
        "input_manifest_digest",
        "inputs",
        "provider",
        "observations",
    }
    _exact_keys(bundle, top_keys, "BUNDLE_KEYS_INVALID")
    if bundle["schema_version"] != EVIDENCE_SCHEMA_VERSION or bundle["protocol_version"] != PROTOCOL_VERSION:
        raise EvidenceContractError("BUNDLE_VERSION_INVALID")
    if not isinstance(bundle["run_id"], str) or not _RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("BUNDLE_ID_INVALID")
    for key in ("source_commit", "input_manifest_digest"):
        if not isinstance(bundle[key], str) or not bundle[key]:
            raise EvidenceContractError("BUNDLE_ID_INVALID")
    if not _GIT_SHA_RE.fullmatch(bundle["source_commit"]) or not _is_sha(bundle["input_manifest_digest"]):
        raise EvidenceContractError("BUNDLE_DIGEST_INVALID")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise EvidenceContractError("BUNDLE_INPUTS_INVALID")
    input_roles: set[str] = set()
    for item in inputs:
        if not isinstance(item, Mapping):
            raise EvidenceContractError("BUNDLE_INPUT_ENTRY_INVALID")
        _exact_keys(item, {"path", "sha256", "role"}, "BUNDLE_INPUT_ENTRY_INVALID")
        if (
            not isinstance(item["path"], str)
            or not _is_sha(item["sha256"])
            or item["role"] not in {"provider", "evaluator"}
        ):
            raise EvidenceContractError("BUNDLE_INPUT_ENTRY_INVALID")
        input_roles.add(item["role"])
    if input_roles != {"provider", "evaluator"}:
        raise EvidenceContractError("BUNDLE_INPUT_ROLES_INVALID")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping):
        raise EvidenceContractError("BUNDLE_PROVIDER_INVALID")
    _exact_keys(
        provider,
        {
            "name",
            "model_requested",
            "model_reported",
            "transport",
            "structured_output_mode",
            "response_contract",
            "candidate_schema_version",
            "timeout_seconds",
            "max_transport_retries",
        },
        "BUNDLE_PROVIDER_INVALID",
    )
    if provider["name"] != PROVIDER_NAME or provider["model_requested"] != MODEL_REQUESTED:
        raise EvidenceContractError("BUNDLE_PROVIDER_INVALID")
    if provider["model_reported"] is not None and _safe_model_name(provider["model_reported"]) is None:
        raise EvidenceContractError("BUNDLE_REPORTED_MODEL_INVALID")
    if provider["transport"] != TRANSPORT or provider["structured_output_mode"] != STRUCTURED_OUTPUT_MODE:
        raise EvidenceContractError("BUNDLE_PROVIDER_INVALID")
    if provider["response_contract"] != RESPONSE_CONTRACT or provider["candidate_schema_version"] != CANDIDATE_SCHEMA_VERSION:
        raise EvidenceContractError("BUNDLE_PROVIDER_INVALID")
    if provider["timeout_seconds"] != TIMEOUT_SECONDS or provider["max_transport_retries"] != MAX_TRANSPORT_RETRIES:
        raise EvidenceContractError("BUNDLE_PROVIDER_INVALID")
    observations = bundle["observations"]
    if not isinstance(observations, list):
        raise EvidenceContractError("BUNDLE_OBSERVATIONS_INVALID")
    seen: set[str] = set()
    for record in observations:
        _validate_record(record)
        observation = record["observation"]
        observation_id = observation["observation_id"]
        if observation_id in seen:
            raise EvidenceContractError("BUNDLE_DUPLICATE_OBSERVATION")
        seen.add(observation_id)


def _validate_record(record: object) -> None:
    if not isinstance(record, Mapping):
        raise EvidenceContractError("RECORD_INVALID")
    _exact_keys(record, {"record_digest", "observation", "audit", "sanitization"}, "RECORD_KEYS_INVALID")
    if not _is_sha(record["record_digest"]):
        raise EvidenceContractError("RECORD_DIGEST_INVALID")
    body = {"observation": record["observation"], "audit": record["audit"], "sanitization": record["sanitization"]}
    if _record_digest(body) != record["record_digest"]:
        raise EvidenceContractError("RECORD_DIGEST_MISMATCH")
    observation = record["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("OBSERVATION_INVALID")
    observation_keys = {
            "observation_id",
            "case_id",
            "repeat",
            "draft_id",
            "transport_outcome",
            "failure_stage",
            "failure_code",
            "shape_compliant",
            "parse_outcome",
            "outcome",
            "finding_codes",
            "candidate_digest",
            "context_digest",
            "report_digest",
            "renderer_comparison",
            "legacy_impact",
        }
    actual_observation_keys = set(observation)
    if actual_observation_keys != observation_keys and actual_observation_keys != observation_keys | {"shape_diagnostic"}:
        raise EvidenceContractError("OBSERVATION_KEYS_INVALID")
    if "shape_diagnostic" in observation:
        _validate_shape_diagnostic(observation["shape_diagnostic"])
    if not isinstance(observation["observation_id"], str) or not observation["observation_id"]:
        raise EvidenceContractError("OBSERVATION_ID_INVALID")
    if not isinstance(observation["case_id"], str) or not _CASE_RE.fullmatch(observation["case_id"]):
        raise EvidenceContractError("OBSERVATION_CASE_INVALID")
    if isinstance(observation["repeat"], bool) or observation["repeat"] not in {1, 2, 3}:
        raise EvidenceContractError("OBSERVATION_REPEAT_INVALID")
    if not isinstance(observation["draft_id"], str) or not observation["draft_id"]:
        raise EvidenceContractError("OBSERVATION_DRAFT_ID_INVALID")
    if observation["transport_outcome"] not in {"success", "failure"}:
        raise EvidenceContractError("OBSERVATION_TRANSPORT_INVALID")
    failure_stage = observation["failure_stage"]
    failure_code = observation["failure_code"]
    if (
        failure_stage not in _FAILURE_STAGES
        or failure_code not in _FAILURE_CODES
        or (failure_stage is None and failure_code is not None)
        or (failure_stage is not None and failure_code != _failure_code(failure_stage))
    ):
        raise EvidenceContractError("OBSERVATION_FAILURE_INVALID")
    if not isinstance(observation["shape_compliant"], bool) or observation["parse_outcome"] not in {"parsed", "rejected", "not_attempted"}:
        raise EvidenceContractError("OBSERVATION_PARSE_INVALID")
    if observation["outcome"] not in {"PASS", "REPAIR", "FAIL", "UNAVAILABLE"}:
        raise EvidenceContractError("OBSERVATION_OUTCOME_INVALID")
    if not isinstance(observation["finding_codes"], list):
        raise EvidenceContractError("OBSERVATION_FINDINGS_INVALID")
    for finding in observation["finding_codes"]:
        if not isinstance(finding, Mapping):
            raise EvidenceContractError("OBSERVATION_FINDING_INVALID")
        _exact_keys(finding, {"code", "path"}, "OBSERVATION_FINDING_INVALID")
        if not isinstance(finding["code"], str) or not isinstance(finding["path"], str) or not finding["path"].startswith("/"):
            raise EvidenceContractError("OBSERVATION_FINDING_INVALID")
    for key in ("candidate_digest", "context_digest", "report_digest"):
        if not (observation[key] is None or _is_sha(observation[key])):
            raise EvidenceContractError("OBSERVATION_DIGEST_INVALID")
    renderer = observation["renderer_comparison"]
    if not isinstance(renderer, Mapping):
        raise EvidenceContractError("OBSERVATION_RENDERER_INVALID")
    _exact_keys(renderer, {"performed", "matches_legacy", "summary_code"}, "OBSERVATION_RENDERER_INVALID")
    if renderer["performed"] is not False or renderer["matches_legacy"] is not None or renderer["summary_code"] != "not_authoritative":
        raise EvidenceContractError("OBSERVATION_RENDERER_INVALID")
    if observation["legacy_impact"] is not False:
        raise EvidenceContractError("OBSERVATION_LEGACY_IMPACT")

    audit = record["audit"]
    if not isinstance(audit, Mapping):
        raise EvidenceContractError("AUDIT_INVALID")
    _exact_keys(audit, {"redacted_request_id", "retry_count", "latency_ms", "token_usage"}, "AUDIT_KEYS_INVALID")
    if not isinstance(audit["redacted_request_id"], str) or not audit["redacted_request_id"].startswith("redacted:"):
        raise EvidenceContractError("AUDIT_REQUEST_ID_INVALID")
    if isinstance(audit["retry_count"], bool) or not isinstance(audit["retry_count"], int) or not 0 <= audit["retry_count"] <= MAX_TRANSPORT_RETRIES:
        raise EvidenceContractError("AUDIT_RETRY_INVALID")
    if audit["latency_ms"] is not None and (not isinstance(audit["latency_ms"], (int, float)) or isinstance(audit["latency_ms"], bool) or not math.isfinite(audit["latency_ms"]) or audit["latency_ms"] < 0):
        raise EvidenceContractError("AUDIT_LATENCY_INVALID")
    usage = audit["token_usage"]
    if not isinstance(usage, Mapping):
        raise EvidenceContractError("AUDIT_USAGE_INVALID")
    _exact_keys(usage, {"input", "output", "total"}, "AUDIT_USAGE_INVALID")
    for value in usage.values():
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise EvidenceContractError("AUDIT_USAGE_INVALID")

    sanitization = record["sanitization"]
    if not isinstance(sanitization, Mapping):
        raise EvidenceContractError("SANITIZATION_INVALID")
    _exact_keys(sanitization, {"raw_prompt_stored", "raw_response_stored", "secrets_detected"}, "SANITIZATION_KEYS_INVALID")
    if any(value is not False for value in sanitization.values()):
        raise EvidenceContractError("SANITIZATION_FAILURE")


def _validate_shape_diagnostic(value: object) -> None:
    if not isinstance(value, Mapping):
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_INVALID")
    expected = {
        "parsed_top_level_type",
        "key_count",
        "key_count_truncated",
        "expected_top_level_type",
        "wrapper_detected",
        "missing_required_count",
        "missing_required_fields",
        "unknown_key_count",
        "parser_error_code",
        "parser_error_path",
        "json_extraction_stage",
        "validation_error_count",
    }
    if set(value) != expected:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_KEYS_INVALID")
    fields = value["missing_required_fields"]
    if not isinstance(fields, list) or len(fields) > SHAPE_DIAGNOSTIC_MAX_FIELDS:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_FIELDS_INVALID")
    if any(field not in CANONICAL_ROOT_FIELDS for field in fields):
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_FIELDS_INVALID")
    for key in ("missing_required_count", "unknown_key_count", "validation_error_count"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= SHAPE_DIAGNOSTIC_MAX_ERRORS:
            raise EvidenceContractError("SHAPE_DIAGNOSTIC_COUNT_INVALID")
    key_count = value["key_count"]
    if key_count is not None and (
        isinstance(key_count, bool)
        or not isinstance(key_count, int)
        or not 0 <= key_count <= SHAPE_DIAGNOSTIC_MAX_KEYS
    ):
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_KEY_COUNT_INVALID")
    if not isinstance(value["key_count_truncated"], bool):
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_KEY_COUNT_INVALID")
    if value["expected_top_level_type"] != "object":
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_TYPE_INVALID")
    if value["wrapper_detected"] is not None and not isinstance(value["wrapper_detected"], bool):
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_WRAPPER_INVALID")
    if value["parser_error_code"] not in SHAPE_DIAGNOSTIC_ERROR_CODES:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_CODE_INVALID")
    if value["parser_error_path"] is not None:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_PATH_INVALID")
    if value["json_extraction_stage"] not in SHAPE_DIAGNOSTIC_STAGES:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_STAGE_INVALID")
    try:
        SkillKitShapeDiagnostic(
            parsed_top_level_type=value["parsed_top_level_type"],
            key_count=value["key_count"],
            key_count_truncated=value["key_count_truncated"],
            expected_top_level_type=value["expected_top_level_type"],
            wrapper_detected=value["wrapper_detected"],
            missing_required_count=value["missing_required_count"],
            missing_required_fields=tuple(fields),
            unknown_key_count=value["unknown_key_count"],
            parser_error_code=value["parser_error_code"],
            parser_error_path=None,
            json_extraction_stage=value["json_extraction_stage"],
            validation_error_count=value["validation_error_count"],
        )
    except (TypeError, ValueError) as error:
        raise EvidenceContractError("SHAPE_DIAGNOSTIC_INVALID") from error


def _retry_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-shadow-deepseek-retry-unavailable-v0.2.1-"
        f"{source_commit}-{manifest_digest[:12]}-cohort-01"
    )


def _retry_observation_id(retry_run_id: str, source_observation_id: str) -> str:
    source_digest = _digest_bytes(source_observation_id.encode("utf-8"))[:16]
    return f"{retry_run_id}:source-{source_digest}"


def _retry_record(
    record: Mapping[str, object],
    retry_run_id: str,
    *,
    supersedes: str | None = None,
) -> dict[str, object]:
    source_observation = record["observation"]
    source_id = supersedes or source_observation["observation_id"]
    body_observation = dict(source_observation)
    body_observation["observation_id"] = _retry_observation_id(retry_run_id, source_id)
    body_observation["supersedes"] = source_id
    body = {
        "observation": body_observation,
        "audit": dict(record["audit"]),
        "sanitization": dict(record["sanitization"]),
    }
    return {"record_digest": _record_digest(body), **body}


def _validate_retry_record(record: object) -> None:
    if not isinstance(record, Mapping):
        raise EvidenceContractError("RETRY_RECORD_INVALID")
    _exact_keys(record, {"record_digest", "observation", "audit", "sanitization"}, "RETRY_RECORD_KEYS_INVALID")
    observation = record.get("observation")
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("RETRY_OBSERVATION_INVALID")
    retry_observation_keys = {
        "observation_id",
        "case_id",
        "repeat",
        "draft_id",
        "transport_outcome",
        "failure_stage",
        "failure_code",
        "shape_compliant",
        "parse_outcome",
        "outcome",
        "finding_codes",
        "candidate_digest",
        "context_digest",
        "report_digest",
        "renderer_comparison",
        "legacy_impact",
        "supersedes",
    }
    actual_retry_keys = set(observation)
    if actual_retry_keys != retry_observation_keys and actual_retry_keys != retry_observation_keys | {"shape_diagnostic"}:
        raise EvidenceContractError("RETRY_OBSERVATION_KEYS_INVALID")
    if "shape_diagnostic" in observation:
        _validate_shape_diagnostic(observation["shape_diagnostic"])
    supersedes = observation["supersedes"]
    if not isinstance(supersedes, str) or not supersedes:
        raise EvidenceContractError("RETRY_SUPERSEDES_INVALID")
    if supersedes == observation["observation_id"]:
        raise EvidenceContractError("RETRY_SUPERSEDES_SELF_REFERENCE")
    base_observation = dict(observation)
    del base_observation["supersedes"]
    base = {
        "record_digest": _record_digest(
            {
                "observation": base_observation,
                "audit": record["audit"],
                "sanitization": record["sanitization"],
            }
        ),
        "observation": base_observation,
        "audit": record["audit"],
        "sanitization": record["sanitization"],
    }
    _validate_record(base)
    # The normal validator above intentionally does not know the lineage field;
    # validate the retry digest over the complete retry observation separately.
    if not _is_sha(record["record_digest"]):
        raise EvidenceContractError("RETRY_RECORD_DIGEST_INVALID")
    complete_body = {
        "observation": observation,
        "audit": record["audit"],
        "sanitization": record["sanitization"],
    }
    if _record_digest(complete_body) != record["record_digest"]:
        raise EvidenceContractError("RETRY_RECORD_DIGEST_MISMATCH")


def validate_retry_evidence_bundle(bundle: Mapping[str, object]) -> None:
    """Validate the independent retry-unavailable cohort contract."""

    _exact_keys(
        bundle,
        {
            "schema_version",
            "run_id",
            "protocol_version",
            "cohort_type",
            "source_run_id",
            "source_bundle_sha256",
            "source_manifest_digest",
            "input_manifest_digest",
            "inputs",
            "provider",
            "lineage_policy",
            "observations",
        },
        "RETRY_BUNDLE_KEYS_INVALID",
    )
    if bundle["schema_version"] != RETRY_SCHEMA_VERSION or bundle["protocol_version"] != PROTOCOL_VERSION:
        raise EvidenceContractError("RETRY_BUNDLE_VERSION_INVALID")
    if not isinstance(bundle["run_id"], str) or not _RETRY_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("RETRY_BUNDLE_ID_INVALID")
    if bundle["cohort_type"] != RETRY_COHORT_TYPE or bundle["lineage_policy"] != RETRY_LINEAGE_POLICY:
        raise EvidenceContractError("RETRY_COHORT_METADATA_INVALID")
    if not isinstance(bundle["source_run_id"], str) or not _RUN_ID_RE.fullmatch(bundle["source_run_id"]):
        raise EvidenceContractError("RETRY_SOURCE_RUN_INVALID")
    for key in ("source_bundle_sha256", "source_manifest_digest", "input_manifest_digest"):
        if not _is_sha(bundle[key]):
            raise EvidenceContractError("RETRY_DIGEST_INVALID")
    if bundle["source_manifest_digest"] != bundle["input_manifest_digest"]:
        raise EvidenceContractError("RETRY_MANIFEST_MISMATCH")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise EvidenceContractError("RETRY_INPUTS_INVALID")
    input_roles: set[str] = set()
    for item in inputs:
        if not isinstance(item, Mapping):
            raise EvidenceContractError("RETRY_INPUT_ENTRY_INVALID")
        _exact_keys(item, {"path", "sha256", "role"}, "RETRY_INPUT_ENTRY_INVALID")
        if not isinstance(item["path"], str) or not _is_sha(item["sha256"]) or item["role"] not in {"provider", "evaluator"}:
            raise EvidenceContractError("RETRY_INPUT_ENTRY_INVALID")
        input_roles.add(item["role"])
    if input_roles != {"provider", "evaluator"}:
        raise EvidenceContractError("RETRY_INPUT_ROLES_INVALID")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping):
        raise EvidenceContractError("RETRY_PROVIDER_INVALID")
    _exact_keys(
        provider,
        {
            "name",
            "model_requested",
            "model_reported",
            "transport",
            "structured_output_mode",
            "response_contract",
            "candidate_schema_version",
            "timeout_seconds",
            "max_transport_retries",
        },
        "RETRY_PROVIDER_INVALID",
    )
    if provider != _bundle_provider(provider["model_reported"]):
        raise EvidenceContractError("RETRY_PROVIDER_INVALID")
    observations = bundle["observations"]
    if not isinstance(observations, list):
        raise EvidenceContractError("RETRY_OBSERVATIONS_INVALID")
    seen: set[str] = set()
    superseded: set[str] = set()
    for record in observations:
        _validate_retry_record(record)
        observation = record["observation"]
        observation_id = observation["observation_id"]
        source_id = observation["supersedes"]
        if observation_id in seen:
            raise EvidenceContractError("RETRY_DUPLICATE_OBSERVATION")
        if source_id in superseded:
            raise EvidenceContractError("RETRY_DUPLICATE_SUPERSEDE")
        seen.add(observation_id)
        superseded.add(source_id)


def _source_commit(root: Path) -> str:
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise EvidenceRunnerError("SOURCE_COMMIT_UNAVAILABLE") from error
    if not _GIT_SHA_RE.fullmatch(value):
        raise EvidenceRunnerError("SOURCE_COMMIT_INVALID")
    return value


def _dirty_paths(root: Path) -> tuple[str, ...]:
    try:
        output = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        raise EvidenceRunnerError("SOURCE_STATUS_UNAVAILABLE") from error
    paths: list[str] = []
    for line in output:
        if len(line) < 4:
            raise EvidenceRunnerError("SOURCE_STATUS_INVALID")
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.replace("\\", "/"))
    return tuple(paths)


def _allowed_live_dirty(path: str) -> bool:
    for repeat in range(1, 4):
        if path in {RESULT_RELATIVE_TEMPLATE.format(repeat=repeat), TEMP_RELATIVE_TEMPLATE.format(repeat=repeat)}:
            return True
    return False


def assert_live_tree_clean(root: Path) -> None:
    dirty = tuple(path for path in _dirty_paths(root) if not _allowed_live_dirty(path))
    if dirty:
        raise EvidenceRunnerError("LIVE_DIRTY_TREE")


def _selection(case_order: Sequence[str], case_id: str | Sequence[str] | None) -> tuple[str, ...]:
    if case_id is None:
        return tuple(case_order)
    requested = (case_id,) if isinstance(case_id, str) else tuple(case_id)
    if not requested or any(item not in case_order for item in requested) or len(set(requested)) != len(requested):
        raise EvidenceRunnerError("CASE_SELECTION_INVALID")
    return tuple(item for item in case_order if item in requested)


def _run_id(source_commit: str, manifest_digest: str, repeat: int) -> str:
    return f"cs-s2-shadow-deepseek-v{PROTOCOL_VERSION}-{source_commit}-{manifest_digest[:12]}-run-{repeat:02d}"


def _default_result_path(root: Path, repeat: int) -> Path:
    return root / RESULT_RELATIVE_TEMPLATE.format(repeat=repeat)


def _bundle_provider(reported_model: str | None) -> dict[str, object]:
    return {
        "name": PROVIDER_NAME,
        "model_requested": MODEL_REQUESTED,
        "model_reported": reported_model,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_transport_retries": MAX_TRANSPORT_RETRIES,
    }


def _validate_invocation_profile(invocation: ModelInvocationAudit | None) -> None:
    if invocation is None:
        return
    if invocation.provider != PROVIDER_NAME:
        raise EvidenceRunnerError("PROVIDER_PROFILE_DRIFT")
    if invocation.transport not in {None, TRANSPORT}:
        raise EvidenceRunnerError("PROVIDER_TRANSPORT_DRIFT")


class ShadowEvidenceRunner:
    """Run a selected, deterministic CS-S2 shadow evidence cohort."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        manifest_path: Path | str | None = None,
    ) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def dry_run(
        self,
        *,
        repeat: int = 1,
        case_id: str | Sequence[str] | None = None,
    ) -> dict[str, object]:
        selected = self._validate_selection(repeat, case_id)
        source_commit = _source_commit(self.root)
        run_id = _run_id(source_commit, self.manifest.raw_digest, repeat)
        return {
            "status": "dry_run",
            "run_id": run_id,
            "protocol_version": PROTOCOL_VERSION,
            "source_commit": source_commit,
            "input_manifest_digest": self.manifest.raw_digest,
            "repeat": repeat,
            "case_ids": list(selected),
            "smoke_first": list(self.manifest.smoke_cases),
            "result_path": None,
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_count": 0,
        }

    def run(
        self,
        *,
        live: bool = False,
        repeat: int = 1,
        case_id: str | Sequence[str] | None = None,
        resume: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        candidate_model: Any | None = None,
        enforce_clean_tree: bool = True,
        model_factory: Callable[[], Any] | None = None,
    ) -> dict[str, object]:
        if not live:
            if resume or output_path is not None or shadow_model is not None or candidate_model is not None:
                raise EvidenceRunnerError("DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(repeat=repeat, case_id=case_id)
        selected = self._validate_selection(repeat, case_id)
        if enforce_clean_tree:
            assert_live_tree_clean(self.root)
        if shadow_model is not None and candidate_model is not None:
            raise EvidenceRunnerError("SHADOW_MODEL_ARGUMENTS_INVALID")
        source_commit = _source_commit(self.root)
        run_id = _run_id(source_commit, self.manifest.raw_digest, repeat)
        destination = (
            Path(output_path)
            if output_path is not None
            else _default_result_path(self.root, repeat)
        )
        existing: list[dict[str, object]] = []
        existing_bundle: dict[str, Any] | None = None
        if resume:
            if not destination.is_file():
                raise EvidenceRunnerError("RESUME_RESULT_MISSING")
            existing_bundle, _ = _load_json(destination)
            validate_evidence_bundle(existing_bundle)
            self._validate_bundle_identity(existing_bundle, run_id, source_commit)
            existing = list(existing_bundle["observations"])
        elif destination.exists():
            raise EvidenceRunnerError("RESULT_EXISTS_WITHOUT_RESUME")
        provider_model = (
            shadow_model if shadow_model is not None else candidate_model
        )
        if provider_model is None:
            try:
                if model_factory is not None:
                    provider_model = model_factory()
                else:
                    environment = {
                        "NPC_AGENT_MODEL": "live",
                        "NPC_LLM_PROVIDER": PROVIDER_NAME,
                        "NPC_LLM_MODEL": MODEL_REQUESTED,
                        "NPC_LLM_TRANSPORT": TRANSPORT,
                        "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                        "NPC_LLM_TIMEOUT_SECONDS": str(TIMEOUT_SECONDS),
                        "NPC_LLM_MAX_RETRIES": str(MAX_TRANSPORT_RETRIES),
                    }
                    api_key = os.environ.get("NPC_LLM_API_KEY")
                    if api_key:
                        environment["NPC_LLM_API_KEY"] = api_key
                    provider_model = character_model_from_environment(
                        environment=environment,
                        mode_override="live",
                    )
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
            if provider_model is None:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED")
        existing_by_id = self._validate_existing_records(existing, run_id, repeat)
        existing_reported_model = None
        if existing_bundle is not None:
            provider = existing_bundle.get("provider")
            if isinstance(provider, Mapping):
                existing_reported_model = _safe_model_name(provider.get("model_reported"))
        router = ShadowEvidenceModelRouter(provider_model)
        agent = CharacterGenerationAgent(
            router,
            shadow_config=SkillShadowConfig(enabled=True),
            retrieval_strategy="deterministic",
        )
        records = list(existing)
        reported_models = {existing_reported_model} if existing_reported_model else set()
        for case_id_value in selected:
            observation_id = f"{run_id}:{case_id_value}:repeat-{repeat:02d}"
            if observation_id in existing_by_id:
                continue
            case = self.cases[case_id_value]
            try:
                result = agent.generate(
                    case.request(),
                    skill_shadow_context=case.context,
                )
                record = _record_from_result(case, run_id, repeat, result, router)
            except EvidenceRunnerError:
                raise
            except Exception:
                record = self._runner_failure_record(case, run_id, repeat)
            _validate_invocation_profile(router.shadow_invocation)
            records.append(record)
            reported = _safe_model_name(
                router.shadow_invocation.model if router.shadow_invocation is not None else None
            )
            if reported is not None:
                if reported_models and reported not in reported_models:
                    raise EvidenceRunnerError("PROVIDER_MODEL_DRIFT")
                reported_models.add(reported)
            bundle = self._bundle(
                run_id,
                source_commit,
                records,
                next(iter(reported_models)) if len(reported_models) == 1 else None,
            )
            _write_bundle(destination, bundle, resume=resume or destination.exists())
            existing_by_id[observation_id] = record
        final_reported = next(iter(reported_models)) if len(reported_models) == 1 else None
        bundle = self._bundle(run_id, source_commit, records, final_reported)
        validate_evidence_bundle(bundle)
        return bundle

    def _validate_selection(
        self,
        repeat: int,
        case_id: str | Sequence[str] | None,
    ) -> tuple[str, ...]:
        if isinstance(repeat, bool) or repeat not in range(1, self.manifest.repeat_count + 1):
            raise EvidenceRunnerError("REPEAT_INVALID")
        return _selection(self.manifest.case_order, case_id)

    def _validate_bundle_identity(
        self,
        bundle: Mapping[str, object],
        run_id: str,
        source_commit: str,
    ) -> None:
        if (
            bundle.get("run_id") != run_id
            or bundle.get("source_commit") != source_commit
            or bundle.get("input_manifest_digest") != self.manifest.raw_digest
            or bundle.get("protocol_version") != PROTOCOL_VERSION
        ):
            raise EvidenceRunnerError("RESUME_IDENTITY_MISMATCH")
        if bundle.get("inputs") != list(self.manifest.input_files):
            raise EvidenceRunnerError("RESUME_INPUT_DIGEST_MISMATCH")

    def _validate_existing_records(
        self,
        records: Sequence[Mapping[str, object]],
        run_id: str,
        repeat: int,
    ) -> dict[str, Mapping[str, object]]:
        result: dict[str, Mapping[str, object]] = {}
        for record in records:
            observation = record["observation"]
            observation_id = observation["observation_id"]
            expected = f"{run_id}:{observation['case_id']}:repeat-{repeat:02d}"
            if (
                observation["case_id"] not in self.cases
                or observation_id != expected
                or observation_id in result
                or observation["repeat"] != repeat
            ):
                raise EvidenceRunnerError("RESUME_OBSERVATION_ID_MISMATCH")
            context = self.cases[observation["case_id"]].context.digest
            if observation["context_digest"] != context:
                raise EvidenceRunnerError("RESUME_CONTEXT_DIGEST_MISMATCH")
            result[observation_id] = record
        return result

    def _runner_failure_record(
        self,
        case: ShadowEvidenceCase,
        run_id: str,
        repeat: int,
    ) -> dict[str, object]:
        observation_id = f"{run_id}:{case.case_id}:repeat-{repeat:02d}"
        body = {
            "observation": {
                "observation_id": observation_id,
                "case_id": case.case_id,
                "repeat": repeat,
                "draft_id": f"draft_s2_{case.case_id}",
                "transport_outcome": "failure",
                "failure_stage": "runner",
                "failure_code": "RUNNER_FAILURE",
                "shape_compliant": False,
                "parse_outcome": "not_attempted",
                "outcome": "UNAVAILABLE",
                "finding_codes": [],
                "candidate_digest": None,
                "context_digest": case.context.digest,
                "report_digest": None,
                "renderer_comparison": {
                    "performed": False,
                    "matches_legacy": None,
                    "summary_code": "not_authoritative",
                },
                "legacy_impact": False,
            },
            "audit": _audit_mapping(case.case_id, None, "failure"),
            "sanitization": _sanitization_mapping(),
        }
        return {"record_digest": _record_digest(body), **body}

    def _bundle(
        self,
        run_id: str,
        source_commit: str,
        records: Sequence[Mapping[str, object]],
        reported_model: str | None,
    ) -> dict[str, object]:
        bundle = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "run_id": run_id,
            "protocol_version": PROTOCOL_VERSION,
            "source_commit": source_commit,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _bundle_provider(reported_model),
            "observations": [dict(record) for record in records],
        }
        validate_evidence_bundle(bundle)
        return bundle


class RetryUnavailableCohortRunner:
    """Plan and run an immutable retry cohort for UNAVAILABLE observations."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        manifest_path: Path | str | None = None,
    ) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _source(
        self, source_path: Path | str
    ) -> tuple[Path, dict[str, Any], bytes, str, list[Mapping[str, object]]]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise EvidenceRunnerError("RETRY_SOURCE_MISSING")
        if source == (self.root / RETRY_RESULT_RELATIVE_PATH).resolve():
            raise EvidenceRunnerError("RETRY_SOURCE_IS_RETRY_OUTPUT")
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise EvidenceRunnerError("RETRY_SOURCE_UNREADABLE") from error
        try:
            bundle = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceRunnerError("RETRY_SOURCE_JSON_INVALID") from error
        if not isinstance(bundle, dict):
            raise EvidenceRunnerError("RETRY_SOURCE_NOT_OBJECT")
        try:
            validate_evidence_bundle(bundle)
        except EvidenceContractError as error:
            raise EvidenceRunnerError("RETRY_SOURCE_BUNDLE_INVALID") from error
        if bundle["input_manifest_digest"] != self.manifest.raw_digest:
            raise EvidenceRunnerError("RETRY_SOURCE_MANIFEST_MISMATCH")
        if bundle["inputs"] != list(self.manifest.input_files):
            raise EvidenceRunnerError("RETRY_SOURCE_INPUT_MISMATCH")
        eligible: list[Mapping[str, object]] = []
        for record in bundle["observations"]:
            observation = record["observation"]
            if observation["outcome"] != "UNAVAILABLE":
                continue
            if (
                observation["candidate_digest"] is not None
                or observation["report_digest"] is not None
                or observation["parse_outcome"] == "parsed"
            ):
                raise EvidenceRunnerError("RETRY_SOURCE_TARGET_INVALID")
            eligible.append(record)
        return source, bundle, raw, _digest_bytes(raw), eligible

    @staticmethod
    def _selected(
        eligible: Sequence[Mapping[str, object]],
        case_ids: str | Sequence[str] | None,
    ) -> tuple[Mapping[str, object], ...]:
        by_case = {record["observation"]["case_id"]: record for record in eligible}
        if case_ids is None:
            return tuple(eligible)
        requested = (case_ids,) if isinstance(case_ids, str) else tuple(case_ids)
        if not requested or len(set(requested)) != len(requested):
            raise EvidenceRunnerError("RETRY_CASE_SELECTION_INVALID")
        missing = [case_id for case_id in requested if case_id not in by_case]
        if missing:
            raise EvidenceRunnerError("RETRY_TARGET_INELIGIBLE")
        return tuple(by_case[case_id] for case_id in requested)

    def dry_run(
        self,
        *,
        source_path: Path | str,
        case_id: str | Sequence[str] | None = None,
    ) -> dict[str, object]:
        source, bundle, raw, source_digest, eligible = self._source(source_path)
        selected = self._selected(eligible, case_id)
        try:
            if source.read_bytes() != raw:
                raise EvidenceRunnerError("RETRY_SOURCE_MODIFIED")
        except OSError as error:
            raise EvidenceRunnerError("RETRY_SOURCE_UNREADABLE") from error
        retry_run_id = _retry_run_id(bundle["source_commit"], self.manifest.raw_digest)
        return {
            "status": "dry_run_retry_unavailable",
            "run_id": retry_run_id,
            "cohort_type": RETRY_COHORT_TYPE,
            "source_run_id": bundle["run_id"],
            "source_bundle_path": source.as_posix(),
            "source_bundle_sha256": source_digest,
            "source_bundle_bytes": len(raw),
            "eligible_count": len(eligible),
            "skipped_count": len(eligible) - len(selected),
            "retry_target_count": len(selected),
            "retry_observation_ids": [
                _retry_observation_id(retry_run_id, record["observation"]["observation_id"])
                for record in selected
            ],
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_path": None,
        }

    def _bundle(
        self,
        *,
        run_id: str,
        source_bundle: Mapping[str, object],
        source_digest: str,
        records: Sequence[Mapping[str, object]],
        reported_model: str | None,
    ) -> dict[str, object]:
        bundle = {
            "schema_version": RETRY_SCHEMA_VERSION,
            "run_id": run_id,
            "protocol_version": PROTOCOL_VERSION,
            "cohort_type": RETRY_COHORT_TYPE,
            "source_run_id": source_bundle["run_id"],
            "source_bundle_sha256": source_digest,
            "source_manifest_digest": source_bundle["input_manifest_digest"],
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _bundle_provider(reported_model),
            "lineage_policy": RETRY_LINEAGE_POLICY,
            "observations": [dict(record) for record in records],
        }
        validate_retry_evidence_bundle(bundle)
        return bundle

    def run(
        self,
        *,
        source_path: Path | str,
        live: bool = False,
        case_id: str | Sequence[str] | None = None,
        resume: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        enforce_clean_tree: bool = True,
        model_factory: Callable[[], Any] | None = None,
    ) -> dict[str, object]:
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("RETRY_MODEL_ARGUMENTS_INVALID")
        source, source_bundle, source_raw, source_digest, eligible = self._source(source_path)
        selected = self._selected(eligible, case_id)
        run_id = _retry_run_id(source_bundle["source_commit"], self.manifest.raw_digest)
        destination = (Path(output_path) if output_path is not None else self.root / RETRY_RESULT_RELATIVE_PATH).resolve()
        if destination == source:
            raise EvidenceRunnerError("RETRY_OUTPUT_EQUALS_SOURCE")
        if not live:
            if resume or output_path is not None or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("RETRY_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(source_path=source, case_id=case_id)
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {RETRY_RESULT_RELATIVE_PATH, RETRY_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        existing: list[dict[str, object]] = []
        if resume:
            if not destination.is_file():
                raise EvidenceRunnerError("RETRY_RESUME_RESULT_MISSING")
            existing_bundle, _ = _load_json(destination)
            try:
                validate_retry_evidence_bundle(existing_bundle)
            except EvidenceContractError as error:
                raise EvidenceRunnerError("RETRY_RESUME_BUNDLE_INVALID") from error
            if (
                existing_bundle["run_id"] != run_id
                or existing_bundle["source_run_id"] != source_bundle["run_id"]
                or existing_bundle["source_bundle_sha256"] != source_digest
                or existing_bundle["input_manifest_digest"] != self.manifest.raw_digest
            ):
                raise EvidenceRunnerError("RETRY_RESUME_IDENTITY_MISMATCH")
            existing = list(existing_bundle["observations"])
        elif destination.exists():
            raise EvidenceRunnerError("RETRY_RESULT_EXISTS_WITHOUT_RESUME")
        eligible_by_id = {record["observation"]["observation_id"]: record for record in eligible}
        existing_by_source: dict[str, Mapping[str, object]] = {}
        for record in existing:
            source_id = record["observation"]["supersedes"]
            if source_id not in eligible_by_id or source_id in existing_by_source:
                raise EvidenceRunnerError("RETRY_DUPLICATE_SUPERSEDE")
            existing_by_source[source_id] = record
        provider_model = shadow_model
        if provider_model is None:
            try:
                if model_factory is not None:
                    provider_model = model_factory()
                else:
                    environment = {
                        "NPC_AGENT_MODEL": "live",
                        "NPC_LLM_PROVIDER": PROVIDER_NAME,
                        "NPC_LLM_MODEL": MODEL_REQUESTED,
                        "NPC_LLM_TRANSPORT": TRANSPORT,
                        "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                        "NPC_LLM_TIMEOUT_SECONDS": str(TIMEOUT_SECONDS),
                        "NPC_LLM_MAX_RETRIES": str(MAX_TRANSPORT_RETRIES),
                    }
                    api_key = os.environ.get("NPC_LLM_API_KEY")
                    if api_key:
                        environment["NPC_LLM_API_KEY"] = api_key
                    provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        if provider_model is None:
            raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED")
        router = ShadowEvidenceModelRouter(provider_model)
        agent = CharacterGenerationAgent(router, shadow_config=SkillShadowConfig(enabled=True), retrieval_strategy="deterministic")
        records = list(existing)
        reported_models: set[str] = set()
        if resume:
            existing_provider = existing_bundle["provider"]
            existing_reported = _safe_model_name(existing_provider["model_reported"])
            if existing_reported is not None:
                reported_models.add(existing_reported)
        for source_record in selected:
            source_id = source_record["observation"]["observation_id"]
            if source_id in existing_by_source:
                continue
            observation = source_record["observation"]
            case = self.cases[observation["case_id"]]
            try:
                result = agent.generate(case.request(), skill_shadow_context=case.context)
                record = _retry_record(
                    _record_from_result(case, run_id, observation["repeat"], result, router),
                    run_id,
                    supersedes=source_id,
                )
            except EvidenceRunnerError:
                raise
            except Exception:
                record = _retry_record(
                    ShadowEvidenceRunner(self.root)._runner_failure_record(case, run_id, observation["repeat"]),
                    run_id,
                    supersedes=source_id,
                )
            _validate_invocation_profile(router.shadow_invocation)
            records.append(record)
            reported = _safe_model_name(router.shadow_invocation.model if router.shadow_invocation is not None else None)
            if reported is not None:
                reported_models.add(reported)
            bundle = self._bundle(
                run_id=run_id,
                source_bundle=source_bundle,
                source_digest=source_digest,
                records=records,
                reported_model=next(iter(reported_models)) if len(reported_models) == 1 else None,
            )
            _write_bundle(destination, bundle, resume=resume or destination.exists())
            existing_by_source[source_id] = record
        try:
            if source.read_bytes() != source_raw:
                raise EvidenceRunnerError("RETRY_SOURCE_MODIFIED")
        except OSError as error:
            raise EvidenceRunnerError("RETRY_SOURCE_UNREADABLE") from error
        final_reported = next(iter(reported_models)) if len(reported_models) == 1 else None
        bundle = self._bundle(
            run_id=run_id,
            source_bundle=source_bundle,
            source_digest=source_digest,
            records=records,
            reported_model=final_reported,
        )
        validate_retry_evidence_bundle(bundle)
        return bundle


def _diagnostic_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-shadow-deepseek-shape-diagnostic-v0.1.0-"
        f"{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _diagnostic_record(
    record: Mapping[str, object],
    *,
    run_id: str,
    diagnosed_observation_id: str,
) -> dict[str, object]:
    observation = dict(record["observation"])
    observation["observation_id"] = f"{run_id}:case_13:diagnostic-01"
    observation["diagnoses_observation_id"] = diagnosed_observation_id
    body = {
        "observation": observation,
        "audit": dict(record["audit"]),
        "sanitization": dict(record["sanitization"]),
    }
    return {"record_digest": _record_digest(body), **body}


def _validate_diagnostic_record(record: object, *, diagnosed_observation_id: str) -> None:
    if not isinstance(record, Mapping):
        raise EvidenceContractError("DIAGNOSTIC_RECORD_INVALID")
    if set(record) != {"record_digest", "observation", "audit", "sanitization"}:
        raise EvidenceContractError("DIAGNOSTIC_RECORD_KEYS_INVALID")
    observation = record["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("DIAGNOSTIC_OBSERVATION_INVALID")
    if observation.get("diagnoses_observation_id") != diagnosed_observation_id:
        raise EvidenceContractError("DIAGNOSTIC_LINEAGE_INVALID")
    base_observation = dict(observation)
    del base_observation["diagnoses_observation_id"]
    base = {
        "record_digest": record["record_digest"],
        "observation": base_observation,
        "audit": record["audit"],
        "sanitization": record["sanitization"],
    }
    body = {
        "observation": observation,
        "audit": record["audit"],
        "sanitization": record["sanitization"],
    }
    if not _is_sha(record["record_digest"]) or _record_digest(body) != record["record_digest"]:
        raise EvidenceContractError("DIAGNOSTIC_RECORD_DIGEST_INVALID")
    # Validate the shared observation contract after removing only diagnostic lineage.
    _validate_record(
        {
            "record_digest": _record_digest(
                {
                    "observation": base_observation,
                    "audit": base["audit"],
                    "sanitization": base["sanitization"],
                }
            ),
            "observation": base_observation,
            "audit": base["audit"],
            "sanitization": base["sanitization"],
        }
    )


def validate_shape_diagnostic_bundle(bundle: Mapping[str, object]) -> None:
    """Validate the independent one-case diagnostic cohort contract."""

    expected = {
        "schema_version",
        "protocol_version",
        "run_id",
        "cohort_type",
        "lineage_policy",
        "diagnoses_observation_id",
        "source_run_id",
        "source_bundle_sha256",
        "source_manifest_digest",
        "input_manifest_digest",
        "inputs",
        "provider",
        "observations",
    }
    _exact_keys(bundle, expected, "DIAGNOSTIC_BUNDLE_KEYS_INVALID")
    if bundle["schema_version"] != DIAGNOSTIC_SCHEMA_VERSION or bundle["protocol_version"] != PROTOCOL_VERSION:
        raise EvidenceContractError("DIAGNOSTIC_BUNDLE_VERSION_INVALID")
    if bundle["cohort_type"] != DIAGNOSTIC_COHORT_TYPE or bundle["lineage_policy"] != DIAGNOSTIC_LINEAGE_POLICY:
        raise EvidenceContractError("DIAGNOSTIC_COHORT_INVALID")
    if not isinstance(bundle["run_id"], str) or not _DIAGNOSTIC_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("DIAGNOSTIC_RUN_ID_INVALID")
    if not isinstance(bundle["diagnoses_observation_id"], str) or not bundle["diagnoses_observation_id"]:
        raise EvidenceContractError("DIAGNOSTIC_LINEAGE_INVALID")
    if not isinstance(bundle["source_run_id"], str) or not _RETRY_RUN_ID_RE.fullmatch(bundle["source_run_id"]):
        raise EvidenceContractError("DIAGNOSTIC_SOURCE_RUN_INVALID")
    for key in ("source_bundle_sha256", "source_manifest_digest", "input_manifest_digest"):
        if not _is_sha(bundle[key]):
            raise EvidenceContractError("DIAGNOSTIC_DIGEST_INVALID")
    if bundle["source_manifest_digest"] != bundle["input_manifest_digest"]:
        raise EvidenceContractError("DIAGNOSTIC_MANIFEST_MISMATCH")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping) or provider != _bundle_provider(provider.get("model_reported")):
        raise EvidenceContractError("DIAGNOSTIC_PROVIDER_INVALID")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise EvidenceContractError("DIAGNOSTIC_INPUTS_INVALID")
    for item in inputs:
        if not isinstance(item, Mapping):
            raise EvidenceContractError("DIAGNOSTIC_INPUTS_INVALID")
        _exact_keys(item, {"path", "sha256", "role"}, "DIAGNOSTIC_INPUTS_INVALID")
        if not isinstance(item["path"], str) or not _is_sha(item["sha256"]) or item["role"] not in {"provider", "evaluator"}:
            raise EvidenceContractError("DIAGNOSTIC_INPUTS_INVALID")
    observations = bundle["observations"]
    if not isinstance(observations, list) or len(observations) != 1:
        raise EvidenceContractError("DIAGNOSTIC_OBSERVATIONS_INVALID")
    _validate_diagnostic_record(observations[0], diagnosed_observation_id=bundle["diagnoses_observation_id"])


class ShapeDiagnosticCohortRunner:
    """Run exactly one case_13 observation diagnosing the retry cohort sample."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _source(self, source_path: Path | str) -> tuple[dict[str, Any], bytes, Mapping[str, object]]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise EvidenceRunnerError("DIAGNOSTIC_SOURCE_MISSING")
        raw = source.read_bytes()
        bundle, _ = _load_json(source)
        validate_retry_evidence_bundle(bundle)
        if bundle["input_manifest_digest"] != self.manifest.raw_digest:
            raise EvidenceRunnerError("DIAGNOSTIC_SOURCE_MANIFEST_MISMATCH")
        records = [item for item in bundle["observations"] if item["observation"]["case_id"] == "case_13"]
        if len(records) != 1:
            raise EvidenceRunnerError("DIAGNOSTIC_CASE13_SOURCE_INVALID")
        source_record = records[0]
        if source_record["observation"]["outcome"] != "UNAVAILABLE":
            raise EvidenceRunnerError("DIAGNOSTIC_SOURCE_NOT_UNAVAILABLE")
        return bundle, raw, source_record

    def dry_run(self, *, source_path: Path | str) -> dict[str, object]:
        source_bundle, raw, source_record = self._source(source_path)
        run_id = _diagnostic_run_id(_source_commit(self.root), self.manifest.raw_digest)
        return {
            "status": "dry_run_shape_diagnostic",
            "run_id": run_id,
            "cohort_type": DIAGNOSTIC_COHORT_TYPE,
            "diagnoses_observation_id": source_record["observation"]["observation_id"],
            "source_run_id": source_bundle["run_id"],
            "source_bundle_sha256": _digest_bytes(raw),
            "case_ids": ["case_13"],
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_path": None,
        }

    def run(
        self,
        *,
        source_path: Path | str,
        live: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        enforce_clean_tree: bool = True,
        model_factory: Callable[[], Any] | None = None,
    ) -> dict[str, object]:
        source_bundle, source_raw, source_record = self._source(source_path)
        if not live:
            if output_path is not None or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("DIAGNOSTIC_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(source_path=source_path)
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {DIAGNOSTIC_RESULT_RELATIVE_PATH, DIAGNOSTIC_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("DIAGNOSTIC_MODEL_ARGUMENTS_INVALID")
        provider_model = shadow_model
        if provider_model is None:
            try:
                provider_model = model_factory() if model_factory is not None else character_model_from_environment(
                    environment={
                        "NPC_AGENT_MODEL": "live",
                        "NPC_LLM_PROVIDER": PROVIDER_NAME,
                        "NPC_LLM_MODEL": MODEL_REQUESTED,
                        "NPC_LLM_TRANSPORT": TRANSPORT,
                        "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                        "NPC_LLM_TIMEOUT_SECONDS": str(TIMEOUT_SECONDS),
                        "NPC_LLM_MAX_RETRIES": str(MAX_TRANSPORT_RETRIES),
                        **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
                    },
                    mode_override="live",
                )
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        if provider_model is None:
            raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED")
        run_id = _diagnostic_run_id(_source_commit(self.root), self.manifest.raw_digest)
        destination = (Path(output_path) if output_path is not None else self.root / DIAGNOSTIC_RESULT_RELATIVE_PATH).resolve()
        if destination == Path(source_path).resolve():
            raise EvidenceRunnerError("DIAGNOSTIC_OUTPUT_EQUALS_SOURCE")
        router = ShadowEvidenceModelRouter(provider_model)
        agent = CharacterGenerationAgent(router, shadow_config=SkillShadowConfig(enabled=True), retrieval_strategy="deterministic")
        case = self.cases["case_13"]
        try:
            result = agent.generate(case.request(), skill_shadow_context=case.context)
            record = _diagnostic_record(
                _record_from_result(case, run_id, 1, result, router),
                run_id=run_id,
                diagnosed_observation_id=source_record["observation"]["observation_id"],
            )
        except EvidenceRunnerError:
            raise
        except Exception:
            record = _diagnostic_record(
                ShadowEvidenceRunner(self.root)._runner_failure_record(case, run_id, 1),
                run_id=run_id,
                diagnosed_observation_id=source_record["observation"]["observation_id"],
            )
        _validate_invocation_profile(router.shadow_invocation)
        reported_model = _safe_model_name(router.shadow_invocation.model if router.shadow_invocation is not None else None)
        bundle = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "cohort_type": DIAGNOSTIC_COHORT_TYPE,
            "lineage_policy": DIAGNOSTIC_LINEAGE_POLICY,
            "diagnoses_observation_id": source_record["observation"]["observation_id"],
            "source_run_id": source_bundle["run_id"],
            "source_bundle_sha256": _digest_bytes(source_raw),
            "source_manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _bundle_provider(reported_model),
            "observations": [record],
        }
        validate_shape_diagnostic_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _write_bundle(path: Path, bundle: Mapping[str, object], *, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not resume:
        raise EvidenceRunnerError("RESULT_EXISTS_WITHOUT_RESUME")
    tmp = path.with_name("." + path.name + ".tmp")
    if tmp.exists():
        raise EvidenceRunnerError("RESULT_TEMP_EXISTS")
    payload = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except EvidenceRunnerError:
        raise
    except OSError as error:
        raise EvidenceRunnerError("RESULT_ATOMIC_WRITE_FAILED") from error


def run_shadow_evidence(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    repeat: int = 1,
    case_id: str | Sequence[str] | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    shadow_model: Any | None = None,
    candidate_model: Any | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    """Small functional seam used by the CLI and integration tests."""

    return ShadowEvidenceRunner(repo_root).run(
        live=live,
        repeat=repeat,
        case_id=case_id,
        resume=resume,
        output_path=output_path,
        shadow_model=shadow_model,
        candidate_model=candidate_model,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


def run_retry_unavailable(
    *,
    source_path: Path | str,
    repo_root: Path | str | None = None,
    live: bool = False,
    case_id: str | Sequence[str] | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    shadow_model: Any | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return RetryUnavailableCohortRunner(repo_root).run(
        source_path=source_path,
        live=live,
        case_id=case_id,
        resume=resume,
        output_path=output_path,
        shadow_model=shadow_model,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


__all__ = [
    "CASE_IDS",
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceContractError",
    "EvidenceRunnerError",
    "RETRY_SCHEMA_VERSION",
    "RetryUnavailableCohortRunner",
    "ShapeDiagnosticCohortRunner",
    "ShadowEvidenceModelRouter",
    "ShadowEvidenceRunner",
    "load_manifest",
    "run_retry_unavailable",
    "run_shadow_evidence",
    "validate_retry_evidence_bundle",
    "validate_shape_diagnostic_bundle",
    "validate_evidence_bundle",
]
