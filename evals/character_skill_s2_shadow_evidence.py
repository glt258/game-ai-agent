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
import tempfile
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
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
from agents.errors import ModelError  # noqa: E402
from agents.live_llm import LiveLLMAdapter  # noqa: E402
from agents.model_factory import character_model_from_environment  # noqa: E402
from agents.models import (  # noqa: E402
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    NpcCharacterView,
    NpcRuntimeView,
    SkillShadowConfig,
)
from agents.openai_provider import OpenAIChatClient  # noqa: E402
from agents.provider_protocol import (  # noqa: E402
    NegotiatedResponseContract,
    ProviderCompletion,
    ResponseMode,
)
from agents.response_contracts import character_skill_kit_prompt_contract  # noqa: E402
from character_skill import (  # noqa: E402
    SkillKitShapeError,
    SkillValidationContext,
    evaluate,
    parse_candidate,
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
COMPLIANCE_SCHEMA_VERSION = "character-skill-s2-shadow-contract-compliance/0.1.0"
COMPLIANCE_COHORT_TYPE = "contract_compliance"
COMPLIANCE_LINEAGE_POLICY = "diagnoses_shape_observation_without_replacement"
COMPLIANCE_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_contract_compliance_case_13_run_01_v0.1.0.json"
)
COMPLIANCE_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_contract_compliance_case_13_run_01_v0.1.0.json.tmp"
)
_COMPLIANCE_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-deepseek-contract-compliance-v0\.1\.0-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)
FIXED_COMPLIANCE_SCHEMA_VERSION = (
    "character-skill-s2-shadow-contract-compliance-cohort/0.2.0"
)
FIXED_COMPLIANCE_COHORT_TYPE = "contract_compliance"
FIXED_COMPLIANCE_LINEAGE_POLICY = "baseline_plus_parallel_samples"
FIXED_COMPLIANCE_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_contract_compliance_cohort_run_01_v0.2.0.json"
)
FIXED_COMPLIANCE_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_contract_compliance_cohort_run_01_v0.2.0.json.tmp"
)
MAX_FIXED_COHORT_SAMPLES = 16
DEFAULT_FIXED_COHORT_TARGET = 3
FIXED_COMPLIANCE_FROZEN_CONFIG = {
    "timeout_seconds": TIMEOUT_SECONDS,
    "max_transport_retries": MAX_TRANSPORT_RETRIES,
    "retrieval_strategy": "deterministic",
    "feature_mode": "record_only",
    "repair_enabled": False,
}
_FIXED_COMPLIANCE_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-deepseek-contract-compliance-cohort-v0\.2\.0-"
    r"[0-9a-f]{40}-[0-9a-f]{12}-n[0-9]+-run-01$"
)
TIMEOUT_SUITABILITY_SCHEMA_VERSION = (
    "character-skill-s2-shadow-timeout-suitability/0.1.0"
)
TIMEOUT_SUITABILITY_EXPERIMENT_TYPE = "timeout_suitability"
TIMEOUT_SUITABILITY_PROVIDER = "opencode_go"
TIMEOUT_SUITABILITY_MODEL = "deepseek-v4-flash"
TIMEOUT_SUITABILITY_TRANSPORT = "openai_chat_completions"
TIMEOUT_SUITABILITY_STRUCTURED_OUTPUT_MODE = "json_object"
TIMEOUT_SUITABILITY_TIMEOUT_SECONDS = 60
TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES = 2
TIMEOUT_SUITABILITY_TARGET = 1
TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_timeout_suitability_flash_60s_case_13_run_01_v0.1.0.json"
)
TIMEOUT_SUITABILITY_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_timeout_suitability_flash_60s_case_13_run_01_v0.1.0.json.tmp"
)
_TIMEOUT_SUITABILITY_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-timeout-suitability-v0\.1\.0-opencode_go-deepseek-v4-flash-"
    r"case_13-t60-r2-n1-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)
TIMEOUT_SUITABILITY_BASELINE_SHA256 = (
    "99bd6f48e04c1262292468b64ded78c4eb9c6160f94ddba9386bea580d76e46d"
)
TIMEOUT_SUITABILITY_HISTORICAL_SHA256 = {
    "original": "b84bba6063f2b9bb77c0b9d88ba36a3d0f92a5e23a2b022b87d67d55f117b7a3",
    "retry": "7722165cae52cb858078ad9725a516d5ac04cdb8d41824e8d71826eea4989a31",
    "shape": "89b44f5413ab92a418958d2659880b69635ca0bc7a135123afd5579af8898215",
    "compliance": "5ef5fde8fe677d634eedd017948e84c50802f04603df1144dc6360a7f8176803",
    "fixed": TIMEOUT_SUITABILITY_BASELINE_SHA256,
}
MODEL_SUITABILITY_SCHEMA_VERSION = "character-skill-s2-shadow-model-suitability/0.1.0"
MODEL_SUITABILITY_EXPERIMENT_TYPE = "model_suitability"
MODEL_SUITABILITY_PROVIDER = "opencode_go"
MODEL_SUITABILITY_MODEL = "deepseek-v4-pro"
MODEL_SUITABILITY_TRANSPORT = "openai_chat_completions"
MODEL_SUITABILITY_STRUCTURED_OUTPUT_MODE = "json_object"
MODEL_SUITABILITY_TIMEOUT_SECONDS = 60
MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES = 2
MODEL_SUITABILITY_TARGET = 1
MODEL_SUITABILITY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_model_suitability_pro_60s_case_13_run_01_v0.1.0.json"
)
MODEL_SUITABILITY_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_model_suitability_pro_60s_case_13_run_01_v0.1.0.json.tmp"
)
_MODEL_SUITABILITY_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-model-suitability-v0\.1\.0-opencode_go-deepseek-v4-pro-"
    r"case_13-t60-r2-n1-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)
MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256 = (
    "d15389fa338cfbf1773f4c76360c216ef9fd164ee879adf40f309eac6c07dd17"
)
MINIMAL_TRANSPORT_SANITY_SCHEMA_VERSION = (
    "character-skill-s2-shadow-minimal-transport-sanity/0.1.0"
)
MINIMAL_TRANSPORT_SANITY_EXPERIMENT_TYPE = "minimal_transport_sanity"
MINIMAL_TRANSPORT_SANITY_PROVIDER = "opencode_go"
MINIMAL_TRANSPORT_SANITY_MODEL = "deepseek-v4-pro"
MINIMAL_TRANSPORT_SANITY_TRANSPORT = "openai_chat_completions"
MINIMAL_TRANSPORT_SANITY_STRUCTURED_OUTPUT_MODE = "json_object"
MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS = 60
MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES = 0
MINIMAL_TRANSPORT_SANITY_TARGET = 1
MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION = "minimal-status-object/0.1.0"
MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_minimal_transport_sanity_opencode_go_pro_run_01_v0.1.0.json"
)
MINIMAL_TRANSPORT_SANITY_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_minimal_transport_sanity_opencode_go_pro_run_01_v0.1.0.json.tmp"
)
_MINIMAL_TRANSPORT_SANITY_RUN_ID_RE = re.compile(
    r"^cs-s2-minimal-transport-sanity-v0\.1\.0-opencode_go-deepseek-v4-pro-"
    r"t60-r0-n1-[0-9a-f]{40}-run-01$"
)
FULL_INPUT_TINY_OUTPUT_SCHEMA_VERSION = "character-skill-s2-shadow-full-input-tiny-output/0.1.0"
FULL_INPUT_TINY_OUTPUT_EXPERIMENT_TYPE = "full_input_tiny_output"
FULL_INPUT_TINY_OUTPUT_PROVIDER = "opencode_go"
FULL_INPUT_TINY_OUTPUT_MODEL = "deepseek-v4-pro"
FULL_INPUT_TINY_OUTPUT_TIMEOUT_SECONDS = 60
FULL_INPUT_TINY_OUTPUT_MAX_TRANSPORT_RETRIES = 0
FULL_INPUT_TINY_OUTPUT_TARGET = 1
FULL_INPUT_TINY_OUTPUT_INPUT_CONTRACT_VERSION = EVIDENCE_SCHEMA_VERSION
FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION = MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION
FULL_INPUT_TINY_OUTPUT_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_full_input_tiny_output_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
FULL_INPUT_TINY_OUTPUT_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_full_input_tiny_output_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
FULL_INPUT_TINY_OUTPUT_HISTORICAL_CHARS = 5157
FULL_INPUT_TINY_OUTPUT_HISTORICAL_BYTES = 5281
FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION = (
    'For this diagnostic probe only, do not generate a SkillKit. Return exactly one JSON object with exactly one field: "status": "ok". Do not include any other fields, prose, Markdown, code fences, explanations, or SkillKit content.'
)
_FULL_INPUT_TINY_OUTPUT_RUN_ID_RE = re.compile(
    r"^cs-s2-full-input-tiny-output-v0\.1\.0-opencode_go-deepseek-v4-pro-"
    r"case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)

# Diagnostic-only L1 enum step-down probe.  This deliberately lives beside the
# evidence runner rather than in the production response-contract builder.
ENUM_STEPOWDOWN_SCHEMA_VERSION = "character-skill-s2-shadow-enum-expansion-stepdown/0.1.0"
ENUM_STEPOWDOWN_EXPERIMENT_TYPE = "enum_expansion_stepdown"
ENUM_STEPOWDOWN_LEVEL = "L1_NO_ENUM_EXPANSION"
ENUM_STEPOWDOWN_CONTRACT_VERSION = "skillkit-latency-contract-l1-no-enum/0.1.0"
ENUM_STEPOWDOWN_PROVIDER = "opencode_go"
ENUM_STEPOWDOWN_MODEL = "deepseek-v4-pro"
ENUM_STEPOWDOWN_TIMEOUT_SECONDS = 60
ENUM_STEPOWDOWN_MAX_TRANSPORT_RETRIES = 0
ENUM_STEPOWDOWN_TARGET = 1
ENUM_STEPOWDOWN_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_enum_expansion_stepdown_l1_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
ENUM_STEPOWDOWN_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_enum_expansion_stepdown_l1_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
ENUM_STEPOWDOWN_L0_CHARS = 5617
ENUM_STEPOWDOWN_L0_BYTES = 5741
ENUM_STEPOWDOWN_L1_CHARS = 2131
ENUM_STEPOWDOWN_L1_BYTES = 2255
_ENUM_STEPOWDOWN_RUN_ID_RE = re.compile(
    r"^cs-s2-enum-expansion-stepdown-v0\.1\.0-L1_NO_ENUM_EXPANSION-"
    r"opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)
NESTED_SHAPE_STEPOWDOWN_SCHEMA_VERSION = "character-skill-s2-shadow-nested-shape-stepdown/0.1.0"
NESTED_SHAPE_STEPOWDOWN_EXPERIMENT_TYPE = "nested_shape_stepdown"
NESTED_SHAPE_STEPOWDOWN_LEVEL = "L2_ROOT_PLUS_MINIMAL_SHAPE"
NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION = "skillkit-latency-contract-l2-root-minimal-shape/0.1.0"
NESTED_SHAPE_STEPOWDOWN_PROVIDER = "opencode_go"
NESTED_SHAPE_STEPOWDOWN_MODEL = "deepseek-v4-pro"
NESTED_SHAPE_STEPOWDOWN_TIMEOUT_SECONDS = 60
NESTED_SHAPE_STEPOWDOWN_MAX_TRANSPORT_RETRIES = 0
NESTED_SHAPE_STEPOWDOWN_TARGET = 1
NESTED_SHAPE_STEPOWDOWN_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_nested_shape_stepdown_l2_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
NESTED_SHAPE_STEPOWDOWN_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_nested_shape_stepdown_l2_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
NESTED_SHAPE_STEPOWDOWN_L2_CHARS = 1351
NESTED_SHAPE_STEPOWDOWN_L2_BYTES = 1475
_NESTED_SHAPE_STEPOWDOWN_RUN_ID_RE = re.compile(
    r"^cs-s2-nested-shape-stepdown-v0\.1\.0-L2_ROOT_PLUS_MINIMAL_SHAPE-"
    r"opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-run-01$"
)

# Compact model-facing Contract V2-A is deliberately isolated from the frozen
# production contract and all prior diagnostic ladders.  This stage exposes a
# deterministic dry-run only; a live call is an explicit protocol violation.
COMPACT_V2_SCHEMA_VERSION = "character-skill-s2-shadow-compact-contract-v2-a/0.1.0"
COMPACT_V2_EXPERIMENT_TYPE = "compact_contract_v2_latency"
COMPACT_V2_CONTRACT_VERSION = "compact-skillkit-contract-v2-a/0.1.0"
COMPACT_V2_PROVIDER = "opencode_go"
COMPACT_V2_MODEL = "deepseek-v4-pro"
COMPACT_V2_TIMEOUT_SECONDS = 60
COMPACT_V2_MAX_TRANSPORT_RETRIES = 0
COMPACT_V2_TARGET = 1
COMPACT_V2_CASE_ID = "case_13"
COMPACT_V2_TINY_OUTPUT_CONTRACT_VERSION = MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION
COMPACT_V2_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_a_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
COMPACT_V2_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_a_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
_COMPACT_V2_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-compact-contract-v2-a-v0\.1\.0-opencode_go-deepseek-v4-pro-"
    r"case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-[0-9a-f]{12}-run-01$"
)
COMPACT_V2_L0_CHARS = 5617
COMPACT_V2_L0_BYTES = 5741
COMPACT_V2_L1_CHARS = 2131
COMPACT_V2_L1_BYTES = 2255
COMPACT_V2_L2_CHARS = 1351
COMPACT_V2_L2_BYTES = 1475
MINIMAL_SKILLKIT_SCHEMA_VERSION = "character-skill-s2-shadow-compact-contract-v2-minimal-skillkit/0.1.0"
MINIMAL_SKILLKIT_EXPERIMENT_TYPE = "compact_contract_v2_minimal_skillkit"
MINIMAL_SKILLKIT_OUTPUT_CONTRACT_VERSION = "minimal-skillkit-output-contract/0.1.0"
MINIMAL_SKILLKIT_PROVIDER = "opencode_go"
MINIMAL_SKILLKIT_MODEL = "deepseek-v4-pro"
MINIMAL_SKILLKIT_TIMEOUT_SECONDS = 60
MINIMAL_SKILLKIT_MAX_TRANSPORT_RETRIES = 0
MINIMAL_SKILLKIT_TARGET = 1
MINIMAL_SKILLKIT_CASE_ID = "case_13"
MINIMAL_SKILLKIT_RESPONSE_MODE = "json_object"
MINIMAL_SKILLKIT_PARSER_CONTRACT_VERSION = "skill-kit-validator/0.1.1"
MINIMAL_SKILLKIT_EVALUATOR_CONTEXT_VERSION = "skill-kit-evaluator-context/0.1.1"
MINIMAL_SKILLKIT_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_minimal_skillkit_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
MINIMAL_SKILLKIT_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_minimal_skillkit_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
_MINIMAL_SKILLKIT_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-compact-contract-v2-minimal-skillkit-v0\.1\.0-opencode_go-deepseek-v4-pro-"
    r"case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-[0-9a-f]{12}-run-01$"
)
O1_ROOT_ONLY_SCHEMA_VERSION = "character-skill-s2-shadow-compact-contract-v2-output-stepdown/0.1.0"
O1_ROOT_ONLY_EXPERIMENT_TYPE = "compact_contract_v2_output_stepdown"
O1_ROOT_ONLY_LEVEL = "O1_ROOT_ONLY"
O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION = "v2-output-stepdown-o1-root-only/0.2.0"
O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION = "v2-output-stepdown-o1-root-only-schema-guided/0.3.0"
O1_ROOT_ONLY_PROVIDER = "opencode_go"
O1_ROOT_ONLY_MODEL = "deepseek-v4-pro"
O1_ROOT_ONLY_TIMEOUT_SECONDS = 60
O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES = 0
O1_ROOT_ONLY_TARGET = 1
O1_ROOT_ONLY_CASE_ID = "case_13"
O1_ROOT_ONLY_RESPONSE_MODE = "json_object"
O1_ROOT_ONLY_PARSER_CONTRACT_VERSION = "skill-kit-validator/0.1.1"
O1_ROOT_ONLY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_o1_root_only_opencode_go_pro_case_13_run_01_v0.2.0.json"
)
O1_ROOT_ONLY_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_output_stepdown_o1_root_only_opencode_go_pro_case_13_run_01_v0.2.0.json.tmp"
)
O1_ROOT_ONLY_GUIDED_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_diagnostic_o1_root_only_schema_guided_opencode_go_pro_case_13_run_01_v0.3.0.json"
)
O1_ROOT_ONLY_GUIDED_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_output_stepdown_diagnostic_o1_root_only_schema_guided_opencode_go_pro_case_13_run_01_v0.3.0.json.tmp"
)
O2_LOCAL_STRUCTURE_SCHEMA_VERSION = "character-skill-s2-shadow-o2-local-structure/0.1.0"
O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE = "compact_contract_v2_output_stepdown_o2_local_structure"
O2_LOCAL_STRUCTURE_LEVEL = "O2_LOCAL_STRUCTURE"
O2_LOCAL_STRUCTURE_OUTPUT_CONTRACT_VERSION = "v2-output-stepdown-o2-local-structure/0.1.0"
O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION = "v2-output-stepdown-o2-local-structure-compact/0.2.0"
O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION = "v2-output-stepdown-o1.5-entry-only/0.3.0"
O2_LOCAL_STRUCTURE_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_o2_local_structure_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
O2_LOCAL_STRUCTURE_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_output_stepdown_o2_local_structure_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
O2_LOCAL_STRUCTURE_COMPACT_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_o2_local_structure_compact_opencode_go_pro_case_13_run_01_v0.2.0.json"
)
O2_ENTRY_ONLY_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_o1_5_entry_only_opencode_go_pro_case_13_run_01_v0.3.0.json"
)
_O2_LOCAL_STRUCTURE_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-compact-contract-v2-output-stepdown-o2-local-structure-v0\.1\.0-"
    r"opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-[0-9a-f]{12}-run-01$"
)
_O1_ROOT_ONLY_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-compact-contract-v2-output-stepdown-o1-root-only-v0\.2\.0-opencode_go-deepseek-v4-pro-"
    r"case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-[0-9a-f]{12}-run-01$"
)
O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION = "character-skill-s2-shadow-o1-safe-diagnostic/0.1.0"
O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE = "compact_contract_v2_output_stepdown_diagnostic"
O1_SAFE_DIAGNOSTIC_RESULT_RELATIVE_PATH = (
    "evals/results/character_skill_s2_shadow_compact_contract_v2_output_stepdown_diagnostic_o1_root_only_opencode_go_pro_case_13_run_01_v0.1.0.json"
)
O1_SAFE_DIAGNOSTIC_TEMP_RELATIVE_PATH = (
    "evals/results/.character_skill_s2_shadow_compact_contract_v2_output_stepdown_diagnostic_o1_root_only_opencode_go_pro_case_13_run_01_v0.1.0.json.tmp"
)
_O1_SAFE_DIAGNOSTIC_RUN_ID_RE = re.compile(
    r"^cs-s2-shadow-compact-contract-v2-output-stepdown-diagnostic-o1-root-only-v0\.1\.0-"
    r"opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-[0-9a-f]{40}-[0-9a-f]{12}-[0-9a-f]{12}-run-01$"
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
            character_skill_kit_prompt_contract(),
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


def _historical_source_commit(bundle: Mapping[str, object]) -> str:
    """Return a validated source commit frozen into an evidence bundle."""

    value = bundle.get("source_commit")
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise EvidenceContractError("HISTORICAL_SOURCE_COMMIT_INVALID")
    return value


def _historical_identity(
    bundle: Mapping[str, object],
    identity_builder: Callable[[str], str],
) -> str:
    """Rebuild an existing run identity from its historical source commit."""

    return identity_builder(_historical_source_commit(bundle))


def _validate_historical_bundle_identity(
    bundle: Mapping[str, object],
    *,
    current_manifest_digest: str,
    identity_builder: Callable[[str, str], str],
    mismatch_code: str,
) -> None:
    """Validate a completed bundle against its frozen, not current, identity."""

    try:
        source_commit = _historical_source_commit(bundle)
        manifest_digest = bundle.get("manifest_digest")
        if not isinstance(manifest_digest, str) or not _is_sha(manifest_digest):
            raise EvidenceContractError("HISTORICAL_MANIFEST_DIGEST_INVALID")
        expected = identity_builder(source_commit, manifest_digest)
    except (EvidenceContractError, TypeError, ValueError) as error:
        raise EvidenceRunnerError(mismatch_code) from error
    if manifest_digest != current_manifest_digest or bundle.get("run_id") != expected:
        raise EvidenceRunnerError(mismatch_code)


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
            self._validate_bundle_identity(existing_bundle, repeat=repeat)
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
        *,
        repeat: int,
    ) -> None:
        try:
            historical_run_id = _historical_identity(
                bundle,
                lambda frozen_source: _run_id(
                    frozen_source,
                    str(bundle["input_manifest_digest"]),
                    repeat,
                ),
            )
        except (EvidenceContractError, KeyError, TypeError, ValueError) as error:
            raise EvidenceRunnerError("RESUME_IDENTITY_MISMATCH") from error
        if (
            bundle.get("run_id") != historical_run_id
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


def _compliance_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-shadow-deepseek-contract-compliance-v0.1.0-"
        f"{source_commit}-{manifest_digest[:12]}-run-01"
    )


def validate_contract_compliance_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "cohort_type",
        "lineage_policy", "baseline_observation_id", "source_run_id",
        "source_bundle_sha256", "source_manifest_digest", "input_manifest_digest",
        "inputs", "provider", "observations",
    }
    _exact_keys(bundle, expected, "COMPLIANCE_BUNDLE_KEYS_INVALID")
    if bundle["schema_version"] != COMPLIANCE_SCHEMA_VERSION or bundle["protocol_version"] != PROTOCOL_VERSION:
        raise EvidenceContractError("COMPLIANCE_BUNDLE_VERSION_INVALID")
    if bundle["cohort_type"] != COMPLIANCE_COHORT_TYPE or bundle["lineage_policy"] != COMPLIANCE_LINEAGE_POLICY:
        raise EvidenceContractError("COMPLIANCE_COHORT_INVALID")
    if not isinstance(bundle["run_id"], str) or not _COMPLIANCE_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("COMPLIANCE_RUN_ID_INVALID")
    for key in ("baseline_observation_id", "source_run_id"):
        if not isinstance(bundle[key], str) or not bundle[key]:
            raise EvidenceContractError("COMPLIANCE_LINEAGE_INVALID")
    if not (_RETRY_RUN_ID_RE.fullmatch(bundle["source_run_id"]) or _DIAGNOSTIC_RUN_ID_RE.fullmatch(bundle["source_run_id"])):
        raise EvidenceContractError("COMPLIANCE_SOURCE_RUN_INVALID")
    for key in ("source_bundle_sha256", "source_manifest_digest", "input_manifest_digest"):
        if not _is_sha(bundle[key]):
            raise EvidenceContractError("COMPLIANCE_DIGEST_INVALID")
    if bundle["source_manifest_digest"] != bundle["input_manifest_digest"]:
        raise EvidenceContractError("COMPLIANCE_MANIFEST_MISMATCH")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping) or provider != _bundle_provider(provider.get("model_reported")):
        raise EvidenceContractError("COMPLIANCE_PROVIDER_INVALID")
    observations = bundle["observations"]
    if not isinstance(observations, list) or len(observations) != 1:
        raise EvidenceContractError("COMPLIANCE_OBSERVATIONS_INVALID")
    record = observations[0]
    if not isinstance(record, Mapping):
        raise EvidenceContractError("COMPLIANCE_RECORD_INVALID")
    observation = record.get("observation")
    if not isinstance(observation, Mapping) or observation.get("baseline_observation_id") != bundle["baseline_observation_id"]:
        raise EvidenceContractError("COMPLIANCE_LINEAGE_INVALID")
    base_observation = dict(observation)
    del base_observation["baseline_observation_id"]
    body = {"observation": observation, "audit": record["audit"], "sanitization": record["sanitization"]}
    if not _is_sha(record.get("record_digest")) or _record_digest(body) != record["record_digest"]:
        raise EvidenceContractError("COMPLIANCE_RECORD_DIGEST_INVALID")
    base_body = {"observation": base_observation, "audit": record["audit"], "sanitization": record["sanitization"]}
    _validate_record({"record_digest": _record_digest(base_body), **base_body})


class ContractComplianceCohortRunner:
    """Run one independent case_13 compliance sample from the shape baseline."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _source(self, source_path: Path | str) -> tuple[dict[str, Any], bytes, Mapping[str, object]]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise EvidenceRunnerError("COMPLIANCE_SOURCE_MISSING")
        bundle, raw = _load_json(source)
        validate_shape_diagnostic_bundle(bundle)
        if bundle["input_manifest_digest"] != self.manifest.raw_digest:
            raise EvidenceRunnerError("COMPLIANCE_SOURCE_MANIFEST_MISMATCH")
        record = bundle["observations"][0]
        if record["observation"]["case_id"] != "case_13":
            raise EvidenceRunnerError("COMPLIANCE_CASE_INVALID")
        return bundle, raw, record

    def dry_run(self, *, source_path: Path | str) -> dict[str, object]:
        source_bundle, raw, source_record = self._source(source_path)
        return {
            "status": "dry_run_contract_compliance",
            "run_id": _compliance_run_id(_source_commit(self.root), self.manifest.raw_digest),
            "cohort_type": COMPLIANCE_COHORT_TYPE,
            "baseline_observation_id": source_record["observation"]["observation_id"],
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
        model_factory: Callable[[], Any] | None = None,
        enforce_clean_tree: bool = True,
    ) -> dict[str, object]:
        source_bundle, source_raw, source_record = self._source(source_path)
        if not live:
            if output_path is not None or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("COMPLIANCE_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(source_path=source_path)
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {COMPLIANCE_RESULT_RELATIVE_PATH, COMPLIANCE_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = (Path(output_path) if output_path is not None else self.root / COMPLIANCE_RESULT_RELATIVE_PATH).resolve()
        if destination == Path(source_path).resolve():
            raise EvidenceRunnerError("COMPLIANCE_OUTPUT_EQUALS_SOURCE")
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("COMPLIANCE_MODEL_ARGUMENTS_INVALID")
        with tempfile.TemporaryDirectory(prefix="cs-s2-compliance-") as temp_dir:
            temp_output = Path(temp_dir) / "shadow.json"
            regular = ShadowEvidenceRunner(self.root).run(
                live=True,
                case_id="case_13",
                output_path=temp_output,
                shadow_model=shadow_model,
                model_factory=model_factory,
                enforce_clean_tree=False,
            )
        run_id = _compliance_run_id(_source_commit(self.root), self.manifest.raw_digest)
        record = dict(regular["observations"][0])
        observation = dict(record["observation"])
        observation["observation_id"] = f"{run_id}:case_13:compliance-01"
        observation["baseline_observation_id"] = source_record["observation"]["observation_id"]
        body = {"observation": observation, "audit": dict(record["audit"]), "sanitization": dict(record["sanitization"])}
        compliance = {
            "schema_version": COMPLIANCE_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "cohort_type": COMPLIANCE_COHORT_TYPE,
            "lineage_policy": COMPLIANCE_LINEAGE_POLICY,
            "baseline_observation_id": source_record["observation"]["observation_id"],
            "source_run_id": source_bundle["run_id"],
            "source_bundle_sha256": _digest_bytes(source_raw),
            "source_manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": regular["provider"],
            "observations": [{"record_digest": _record_digest(body), **body}],
        }
        validate_contract_compliance_bundle(compliance)
        _write_bundle(destination, compliance, resume=False)
        return compliance


def _fixed_compliance_run_id(
    source_commit: str, manifest_digest: str, target_sample_count: int
) -> str:
    return (
        "cs-s2-shadow-deepseek-contract-compliance-cohort-v0.2.0-"
        f"{source_commit}-{manifest_digest[:12]}-n{target_sample_count}-run-01"
    )


def _timeout_suitability_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-shadow-timeout-suitability-v0.1.0-opencode_go-deepseek-v4-flash-"
        f"case_13-t60-r2-n1-{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _fixed_compliance_record(record: Mapping[str, object], sample_index: int) -> dict[str, object]:
    return {"sample_index": sample_index, **deepcopy(dict(record))}


def _fixed_compliance_bundle_digest(bundle: Mapping[str, object]) -> str:
    body = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    return _digest_mapping(body)


def _fixed_compliance_frozen_config() -> dict[str, object]:
    return dict(FIXED_COMPLIANCE_FROZEN_CONFIG)


def validate_fixed_contract_compliance_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version",
        "protocol_version",
        "run_id",
        "cohort_type",
        "lineage_policy",
        "case_id",
        "target_sample_count",
        "complete",
        "baseline_observation_id",
        "source_run_id",
        "source_compliance_bundle_sha256",
        "source_manifest_digest",
        "input_manifest_digest",
        "inputs",
        "provider",
        "frozen_config",
        "source_observation_id",
        "observations",
        "bundle_digest",
    }
    _exact_keys(bundle, expected, "FIXED_COHORT_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != FIXED_COMPLIANCE_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["cohort_type"] != FIXED_COMPLIANCE_COHORT_TYPE
        or bundle["lineage_policy"] != FIXED_COMPLIANCE_LINEAGE_POLICY
    ):
        raise EvidenceContractError("FIXED_COHORT_VERSION_INVALID")
    if not isinstance(bundle["run_id"], str) or not _FIXED_COMPLIANCE_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("FIXED_COHORT_RUN_ID_INVALID")
    target = bundle["target_sample_count"]
    if isinstance(target, bool) or not isinstance(target, int) or not 0 < target <= MAX_FIXED_COHORT_SAMPLES:
        raise EvidenceContractError("COHORT_TARGET_INVALID")
    if not isinstance(bundle["case_id"], str) or not _CASE_RE.fullmatch(bundle["case_id"]):
        raise EvidenceContractError("FIXED_COHORT_CASE_INVALID")
    if not isinstance(bundle["complete"], bool):
        raise EvidenceContractError("FIXED_COHORT_COMPLETE_INVALID")
    for key in (
        "baseline_observation_id",
        "source_run_id",
        "source_observation_id",
    ):
        if not isinstance(bundle[key], str) or not bundle[key]:
            raise EvidenceContractError("FIXED_COHORT_LINEAGE_INVALID")
    if not (
        _COMPLIANCE_RUN_ID_RE.fullmatch(bundle["source_run_id"])
        or _RETRY_RUN_ID_RE.fullmatch(bundle["source_run_id"])
        or _DIAGNOSTIC_RUN_ID_RE.fullmatch(bundle["source_run_id"])
    ):
        raise EvidenceContractError("FIXED_COHORT_SOURCE_RUN_INVALID")
    for key in (
        "source_compliance_bundle_sha256",
        "source_manifest_digest",
        "input_manifest_digest",
        "bundle_digest",
    ):
        if not _is_sha(bundle[key]):
            raise EvidenceContractError("FIXED_COHORT_DIGEST_INVALID")
    if bundle["source_manifest_digest"] != bundle["input_manifest_digest"]:
        raise EvidenceContractError("FIXED_COHORT_MANIFEST_MISMATCH")
    if _fixed_compliance_bundle_digest(bundle) != bundle["bundle_digest"]:
        raise EvidenceContractError("FIXED_COHORT_BUNDLE_DIGEST_INVALID")
    inputs = bundle["inputs"]
    if (
        not isinstance(inputs, list)
        or not inputs
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"path", "sha256", "role"}
            or not isinstance(item["path"], str)
            or not isinstance(item["role"], str)
            or not _is_sha(item["sha256"])
            for item in inputs
        )
    ):
        raise EvidenceContractError("FIXED_COHORT_INPUTS_INVALID")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping) or provider != _bundle_provider(provider.get("model_reported")):
        raise EvidenceContractError("FIXED_COHORT_PROVIDER_INVALID")
    if bundle["frozen_config"] != _fixed_compliance_frozen_config():
        raise EvidenceContractError("FIXED_COHORT_CONFIG_INVALID")
    observations = bundle["observations"]
    if not isinstance(observations, list) or not 0 < len(observations) <= target:
        raise EvidenceContractError("FIXED_COHORT_OBSERVATIONS_INVALID")
    indexes: list[int] = []
    observation_ids: set[str] = set()
    for item in observations:
        if not isinstance(item, Mapping):
            raise EvidenceContractError("FIXED_COHORT_RECORD_INVALID")
        _exact_keys(item, {"sample_index", "record_digest", "observation", "audit", "sanitization"}, "FIXED_COHORT_RECORD_KEYS_INVALID")
        index = item["sample_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= target:
            raise EvidenceContractError("FIXED_COHORT_SAMPLE_INDEX_INVALID")
        if index in indexes:
            raise EvidenceContractError("FIXED_COHORT_DUPLICATE_SAMPLE_INDEX")
        indexes.append(index)
        observation = item["observation"]
        if "supersedes" in observation or observation["case_id"] != bundle["case_id"]:
            raise EvidenceContractError("FIXED_COHORT_LINEAGE_INVALID")
        if index == 1:
            if observation.get("baseline_observation_id") != bundle["baseline_observation_id"]:
                raise EvidenceContractError("FIXED_COHORT_LINEAGE_INVALID")
        elif "baseline_observation_id" in observation:
            raise EvidenceContractError("FIXED_COHORT_LINEAGE_INVALID")
        full_body = {
            "observation": observation,
            "audit": item["audit"],
            "sanitization": item["sanitization"],
        }
        if not _is_sha(item["record_digest"]) or _record_digest(full_body) != item["record_digest"]:
            raise EvidenceContractError("FIXED_COHORT_RECORD_DIGEST_INVALID")
        base_observation = dict(observation)
        base_observation.pop("baseline_observation_id", None)
        base_body = {
            "observation": base_observation,
            "audit": item["audit"],
            "sanitization": item["sanitization"],
        }
        _validate_record({"record_digest": _record_digest(base_body), **base_body})
        if observation["observation_id"] in observation_ids:
            raise EvidenceContractError("FIXED_COHORT_DUPLICATE_OBSERVATION")
        observation_ids.add(observation["observation_id"])
        if index == 1:
            if observation["observation_id"] != bundle["source_observation_id"]:
                raise EvidenceContractError("FIXED_COHORT_LEGACY_SAMPLE_INVALID")
        else:
            expected_id = f"{bundle['run_id']}:{bundle['case_id']}:sample-{index:02d}"
            if observation["observation_id"] != expected_id:
                raise EvidenceContractError("FIXED_COHORT_OBSERVATION_ID_INVALID")
    if sorted(indexes) != list(range(1, len(indexes) + 1)):
        raise EvidenceContractError("FIXED_COHORT_SAMPLE_INDEX_GAP")
    if bundle["complete"] is not (len(indexes) == target):
        raise EvidenceContractError("FIXED_COHORT_COMPLETE_INVALID")
    if not isinstance(bundle["baseline_observation_id"], str):
        raise EvidenceContractError("FIXED_COHORT_LINEAGE_INVALID")


def _timeout_suitability_provider(model_reported: str | None) -> dict[str, object]:
    return {
        "name": TIMEOUT_SUITABILITY_PROVIDER,
        "model_requested": TIMEOUT_SUITABILITY_MODEL,
        "model_reported": model_reported,
        "transport": TIMEOUT_SUITABILITY_TRANSPORT,
        "structured_output_mode": TIMEOUT_SUITABILITY_STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
        "max_transport_retries": TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
    }


def _timeout_suitability_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def _model_suitability_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-shadow-model-suitability-v0.1.0-opencode_go-deepseek-v4-pro-"
        f"case_13-t60-r2-n1-{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _model_suitability_provider(model_reported: str | None) -> dict[str, object]:
    return {
        "name": MODEL_SUITABILITY_PROVIDER,
        "model_requested": MODEL_SUITABILITY_MODEL,
        "model_reported": model_reported,
        "transport": MODEL_SUITABILITY_TRANSPORT,
        "structured_output_mode": MODEL_SUITABILITY_STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": MODEL_SUITABILITY_TIMEOUT_SECONDS,
        "max_transport_retries": MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
    }


def _model_suitability_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def validate_model_suitability_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type",
        "source_commit", "manifest_digest", "input_manifest_digest", "inputs",
        "provider", "case_id", "target_sample_count", "complete", "baseline",
        "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "MODEL_SUITABILITY_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != MODEL_SUITABILITY_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != MODEL_SUITABILITY_EXPERIMENT_TYPE
    ):
        raise EvidenceContractError("MODEL_SUITABILITY_VERSION_INVALID")
    source_commit = bundle["source_commit"]
    if not isinstance(source_commit, str) or not _GIT_SHA_RE.fullmatch(source_commit):
        raise EvidenceContractError("MODEL_SUITABILITY_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("MODEL_SUITABILITY_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _MODEL_SUITABILITY_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("MODEL_SUITABILITY_RUN_ID_INVALID")
    if bundle["case_id"] != "case_13" or bundle["target_sample_count"] != MODEL_SUITABILITY_TARGET:
        raise EvidenceContractError("MODEL_SUITABILITY_TARGET_INVALID")
    if bundle["sample_index"] != 1 or bundle["complete"] is not True:
        raise EvidenceContractError("MODEL_SUITABILITY_COMPLETE_INVALID")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or not inputs or any(
        not isinstance(item, Mapping)
        or set(item) != {"path", "sha256", "role"}
        or not isinstance(item["path"], str)
        or not isinstance(item["role"], str)
        or not _is_sha(item["sha256"])
        for item in inputs
    ):
        raise EvidenceContractError("MODEL_SUITABILITY_INPUTS_INVALID")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping) or provider != _model_suitability_provider(provider.get("model_reported")):
        raise EvidenceContractError("MODEL_SUITABILITY_PROVIDER_INVALID")
    baseline = bundle["baseline"]
    if (
        not isinstance(baseline, Mapping)
        or set(baseline) != {"experiment_type", "model", "timeout_seconds", "bundle_sha256"}
        or baseline["experiment_type"] != TIMEOUT_SUITABILITY_EXPERIMENT_TYPE
        or baseline["model"] != TIMEOUT_SUITABILITY_MODEL
        or baseline["timeout_seconds"] != MODEL_SUITABILITY_TIMEOUT_SECONDS
        or baseline["bundle_sha256"] != MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256
    ):
        raise EvidenceContractError("MODEL_SUITABILITY_BASELINE_INVALID")
    record = bundle["observation"]
    if not isinstance(record, Mapping):
        raise EvidenceContractError("MODEL_SUITABILITY_OBSERVATION_INVALID")
    _validate_record(record)
    observation = record["observation"]
    if observation.get("observation_id") != f"{bundle['run_id']}:case_13:sample-01":
        raise EvidenceContractError("MODEL_SUITABILITY_OBSERVATION_ID_INVALID")
    if bundle["bundle_digest"] != _model_suitability_bundle_digest(bundle):
        raise EvidenceContractError("MODEL_SUITABILITY_BUNDLE_DIGEST_INVALID")


def _minimal_transport_sanity_run_id(source_commit: str) -> str:
    return (
        "cs-s2-minimal-transport-sanity-v0.1.0-opencode_go-deepseek-v4-pro-"
        f"t60-r0-n1-{source_commit}-run-01"
    )


def _minimal_transport_sanity_provider() -> dict[str, object]:
    return {
        "name": MINIMAL_TRANSPORT_SANITY_PROVIDER,
        "model_requested": MINIMAL_TRANSPORT_SANITY_MODEL,
        "model_reported": MINIMAL_TRANSPORT_SANITY_MODEL,
        "transport": MINIMAL_TRANSPORT_SANITY_TRANSPORT,
        "structured_output_mode": MINIMAL_TRANSPORT_SANITY_STRUCTURED_OUTPUT_MODE,
        "timeout_seconds": MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS,
        "max_transport_retries": MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES,
    }


def _minimal_transport_sanity_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def validate_minimal_transport_sanity_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type",
        "source_commit", "manifest_digest", "input_manifest_digest", "inputs",
        "provider", "timeout_seconds", "max_transport_retries", "target_sample_count",
        "complete", "tiny_contract_version", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "MINIMAL_TRANSPORT_SANITY_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != MINIMAL_TRANSPORT_SANITY_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != MINIMAL_TRANSPORT_SANITY_EXPERIMENT_TYPE
        or bundle["timeout_seconds"] != MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS
        or bundle["max_transport_retries"] != MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES
        or bundle["target_sample_count"] != MINIMAL_TRANSPORT_SANITY_TARGET
        or bundle["tiny_contract_version"] != MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION
    ):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_CONFIG_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _MINIMAL_TRANSPORT_SANITY_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_RUN_ID_INVALID")
    if bundle["sample_index"] != 1 or bundle["complete"] is not True:
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_COMPLETE_INVALID")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or not inputs or any(
        not isinstance(item, Mapping)
        or set(item) != {"path", "sha256", "role"}
        or not isinstance(item["path"], str)
        or not isinstance(item["role"], str)
        or not _is_sha(item["sha256"])
        for item in inputs
    ):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_INPUTS_INVALID")
    if bundle["provider"] != _minimal_transport_sanity_provider():
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_OBSERVATION_INVALID")
    _exact_keys(
        observation,
        {"observation_id", "provider_outcome", "transport_attempts", "latency_ms", "json_extraction_outcome", "tiny_contract_outcome", "parsed_top_level_type", "expected_key_count", "actual_key_count", "failure_stage", "failure_code", "sanitization"},
        "MINIMAL_TRANSPORT_SANITY_OBSERVATION_KEYS_INVALID",
    )
    if observation["observation_id"] != f"{bundle['run_id']}:sample-01":
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_OBSERVATION_ID_INVALID")
    if observation["provider_outcome"] not in {"success", "failure"}:
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_OBSERVATION_INVALID")
    if observation["transport_attempts"] != 1:
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_ATTEMPTS_INVALID")
    if observation["tiny_contract_outcome"] not in {"TRANSPORT_SUCCESS_CONTRACT_PASS", "TRANSPORT_SUCCESS_CONTRACT_REJECTED", "TRANSPORT_UNAVAILABLE"}:
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_OUTCOME_INVALID")
    if observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_SANITIZATION_INVALID")
    if bundle["bundle_digest"] != _minimal_transport_sanity_bundle_digest(bundle):
        raise EvidenceContractError("MINIMAL_TRANSPORT_SANITY_BUNDLE_DIGEST_INVALID")


def validate_timeout_suitability_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type",
        "source_commit", "manifest_digest", "input_manifest_digest", "inputs",
        "provider", "case_id", "target_sample_count", "complete", "baseline",
        "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "TIMEOUT_SUITABILITY_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != TIMEOUT_SUITABILITY_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != TIMEOUT_SUITABILITY_EXPERIMENT_TYPE
    ):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_VERSION_INVALID")
    source_commit = bundle["source_commit"]
    if not isinstance(source_commit, str) or not _GIT_SHA_RE.fullmatch(source_commit):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_SOURCE_COMMIT_INVALID")
    if (
        bundle["manifest_digest"] != bundle["input_manifest_digest"]
        or not _is_sha(bundle["manifest_digest"])
    ):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _TIMEOUT_SUITABILITY_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_RUN_ID_INVALID")
    if bundle["case_id"] != "case_13" or bundle["target_sample_count"] != TIMEOUT_SUITABILITY_TARGET:
        raise EvidenceContractError("TIMEOUT_SUITABILITY_TARGET_INVALID")
    if bundle["sample_index"] != 1:
        raise EvidenceContractError("TIMEOUT_SUITABILITY_SAMPLE_INDEX_INVALID")
    if not isinstance(bundle["complete"], bool):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_COMPLETE_INVALID")
    inputs = bundle["inputs"]
    if not isinstance(inputs, list) or not inputs or any(
        not isinstance(item, Mapping)
        or set(item) != {"path", "sha256", "role"}
        or not isinstance(item["path"], str)
        or not isinstance(item["role"], str)
        or not _is_sha(item["sha256"])
        for item in inputs
    ):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_INPUTS_INVALID")
    provider = bundle["provider"]
    if not isinstance(provider, Mapping):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_PROVIDER_INVALID")
    if provider != _timeout_suitability_provider(provider.get("model_reported")):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_PROVIDER_INVALID")
    baseline = bundle["baseline"]
    if (
        not isinstance(baseline, Mapping)
        or set(baseline) != {"experiment_type", "timeout_seconds", "bundle_sha256"}
        or baseline["experiment_type"] != FIXED_COMPLIANCE_COHORT_TYPE
        or baseline["timeout_seconds"] != TIMEOUT_SECONDS
        or baseline["bundle_sha256"] != TIMEOUT_SUITABILITY_BASELINE_SHA256
    ):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_BASELINE_INVALID")
    record = bundle["observation"]
    if not isinstance(record, Mapping):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_OBSERVATION_INVALID")
    _validate_record(record)
    observation = record["observation"]
    if observation.get("observation_id") != f"{bundle['run_id']}:case_13:sample-01":
        raise EvidenceContractError("TIMEOUT_SUITABILITY_OBSERVATION_ID_INVALID")
    if bundle["complete"] is not True:
        raise EvidenceContractError("TIMEOUT_SUITABILITY_COMPLETE_INVALID")
    if bundle["bundle_digest"] != _timeout_suitability_bundle_digest(bundle):
        raise EvidenceContractError("TIMEOUT_SUITABILITY_BUNDLE_DIGEST_INVALID")


class FixedContractComplianceCohortRunner:
    """Append one deterministic sample at a time to a frozen cohort."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _legacy_source(self, source_path: Path | str) -> tuple[Path, dict[str, Any], bytes, str, Mapping[str, object]]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise EvidenceRunnerError("FIXED_COHORT_SOURCE_MISSING")
        bundle, raw = _load_json(source)
        validate_contract_compliance_bundle(bundle)
        if (
            bundle["input_manifest_digest"] != self.manifest.raw_digest
            or bundle["inputs"] != list(self.manifest.input_files)
        ):
            raise EvidenceRunnerError("FIXED_COHORT_SOURCE_MANIFEST_MISMATCH")
        records = bundle["observations"]
        source_record = records[0]
        if source_record["observation"]["case_id"] != "case_13":
            raise EvidenceRunnerError("FIXED_COHORT_CASE_INVALID")
        return source, bundle, raw, _digest_bytes(raw), source_record

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / FIXED_COMPLIANCE_RESULT_RELATIVE_PATH).resolve()

    def _new_bundle(self, source_bundle: Mapping[str, object], source_digest: str, source_record: Mapping[str, object], target: int) -> dict[str, object]:
        run_id = _fixed_compliance_run_id(_source_commit(self.root), self.manifest.raw_digest, target)
        observations = [_fixed_compliance_record(source_record, 1)]
        bundle = {
            "schema_version": FIXED_COMPLIANCE_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "cohort_type": FIXED_COMPLIANCE_COHORT_TYPE,
            "lineage_policy": FIXED_COMPLIANCE_LINEAGE_POLICY,
            "case_id": "case_13",
            "target_sample_count": target,
            "complete": False,
            "baseline_observation_id": source_bundle["baseline_observation_id"],
            "source_run_id": source_bundle["run_id"],
            "source_compliance_bundle_sha256": source_digest,
            "source_manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": dict(source_bundle["provider"]),
            "frozen_config": _fixed_compliance_frozen_config(),
            "source_observation_id": source_record["observation"]["observation_id"],
            "observations": observations,
        }
        bundle["complete"] = len(observations) == target
        bundle["bundle_digest"] = _fixed_compliance_bundle_digest(bundle)
        return bundle

    def _load_or_initialize(self, source_path: Path | str, destination: Path, target: int) -> tuple[Path, bytes, dict[str, Any], list[dict[str, object]], str]:
        source, source_bundle, source_raw, source_digest, source_record = self._legacy_source(source_path)
        if destination == source:
            raise EvidenceRunnerError("FIXED_COHORT_OUTPUT_EQUALS_SOURCE")
        if destination.exists():
            existing, _ = _load_json(destination)
            validate_fixed_contract_compliance_bundle(existing)
            if existing["target_sample_count"] != target:
                raise EvidenceRunnerError("COHORT_TARGET_MISMATCH")
            if (
                existing["run_id"] != _fixed_compliance_run_id(_source_commit(self.root), self.manifest.raw_digest, target)
                or existing["source_run_id"] != source_bundle["run_id"]
                or existing["source_compliance_bundle_sha256"] != source_digest
                or existing["baseline_observation_id"] != source_bundle["baseline_observation_id"]
            ):
                raise EvidenceRunnerError("FIXED_COHORT_IDENTITY_MISMATCH")
            return source, source_raw, existing, list(existing["observations"]), source_digest
        return source, source_raw, self._new_bundle(source_bundle, source_digest, source_record, target), [_fixed_compliance_record(source_record, 1)], source_digest

    def dry_run(self, *, source_path: Path | str, target_sample_count: int = DEFAULT_FIXED_COHORT_TARGET, output_path: Path | str | None = None) -> dict[str, object]:
        target = _validate_fixed_target(target_sample_count)
        destination = self._destination(output_path)
        source, source_raw, bundle, observations, _ = self._load_or_initialize(source_path, destination, target)
        del source_raw
        indexes = [item["sample_index"] for item in observations]
        next_index = len(indexes) + 1 if len(indexes) < target else None
        return {
            "status": "cohort_complete" if next_index is None else "dry_run_fixed_contract_compliance",
            "schema_version": FIXED_COMPLIANCE_SCHEMA_VERSION,
            "run_id": bundle["run_id"],
            "cohort_type": FIXED_COMPLIANCE_COHORT_TYPE,
            "target_sample_count": target,
            "existing_sample_count": len(indexes),
            "existing_sample_indexes": sorted(indexes),
            "remaining_sample_count": target - len(indexes),
            "next_sample_index": next_index,
            "case_ids": ["case_13"],
            "source_bundle_sha256": bundle["source_compliance_bundle_sha256"],
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_path": destination.as_posix() if destination.exists() else None,
            "source_path": source.as_posix(),
        }

    def run(
        self,
        *,
        source_path: Path | str,
        live: bool = False,
        target_sample_count: int = DEFAULT_FIXED_COHORT_TARGET,
        resume: bool = False,
        append_next_sample: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        model_factory: Callable[[], Any] | None = None,
        enforce_clean_tree: bool = True,
    ) -> dict[str, object]:
        target = _validate_fixed_target(target_sample_count)
        destination = self._destination(output_path)
        if not live:
            if resume or append_next_sample or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("FIXED_COHORT_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(source_path=source_path, target_sample_count=target, output_path=output_path)
        if not (resume or append_next_sample):
            raise EvidenceRunnerError("FIXED_COHORT_APPEND_REQUIRED")
        if resume and not destination.exists():
            raise EvidenceRunnerError("FIXED_COHORT_RESUME_MISSING")
        source, source_raw, existing_bundle, observations, source_digest = self._load_or_initialize(source_path, destination, target)
        if len(observations) >= target:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {FIXED_COMPLIANCE_RESULT_RELATIVE_PATH, FIXED_COMPLIANCE_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("FIXED_COHORT_MODEL_ARGUMENTS_INVALID")
        next_index = len(observations) + 1
        run_id = existing_bundle["run_id"]
        with tempfile.TemporaryDirectory(prefix="cs-s2-fixed-cohort-") as temp_dir:
            regular = ShadowEvidenceRunner(self.root).run(
                live=True,
                case_id="case_13",
                output_path=Path(temp_dir) / "shadow.json",
                shadow_model=shadow_model,
                model_factory=model_factory,
                enforce_clean_tree=False,
            )
        if regular["provider"] != existing_bundle["provider"]:
            raise EvidenceRunnerError("FIXED_COHORT_PROVIDER_DRIFT")
        record = deepcopy(regular["observations"][0])
        record["observation"]["observation_id"] = f"{run_id}:case_13:sample-{next_index:02d}"
        record_body = {
            "observation": record["observation"],
            "audit": record["audit"],
            "sanitization": record["sanitization"],
        }
        record["record_digest"] = _record_digest(record_body)
        observations.append(_fixed_compliance_record(record, next_index))
        bundle = deepcopy(existing_bundle)
        bundle["observations"] = observations
        bundle["complete"] = len(observations) == target
        bundle["bundle_digest"] = _fixed_compliance_bundle_digest({key: value for key, value in bundle.items() if key != "bundle_digest"})
        validate_fixed_contract_compliance_bundle(bundle)
        if source.read_bytes() != source_raw:
            raise EvidenceRunnerError("FIXED_COHORT_SOURCE_MODIFIED")
        _write_bundle(destination, bundle, resume=destination.exists())
        del source_digest
        return bundle


class TimeoutSuitabilityProbeRunner:
    """Run one isolated 60-second timeout-suitability observation."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        specs = (
            ("original", RESULT_RELATIVE_TEMPLATE.format(repeat=1), validate_evidence_bundle),
            ("retry", RETRY_RESULT_RELATIVE_PATH, validate_retry_evidence_bundle),
            ("shape", DIAGNOSTIC_RESULT_RELATIVE_PATH, validate_shape_diagnostic_bundle),
            ("compliance", COMPLIANCE_RESULT_RELATIVE_PATH, validate_contract_compliance_bundle),
            ("fixed", FIXED_COMPLIANCE_RESULT_RELATIVE_PATH, validate_fixed_contract_compliance_bundle),
        )
        for name, relative, validator in specs:
            path = self.root / relative
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise EvidenceRunnerError("TIMEOUT_SUITABILITY_HISTORY_MISSING") from error
            if _digest_bytes(raw) != TIMEOUT_SUITABILITY_HISTORICAL_SHA256[name]:
                raise EvidenceRunnerError("TIMEOUT_SUITABILITY_HISTORY_MUTATED")
            bundle, _ = _load_json(path)
            try:
                validator(bundle)
            except EvidenceContractError as error:
                raise EvidenceRunnerError("TIMEOUT_SUITABILITY_HISTORY_INVALID") from error

    def _identity(self, source_commit: str) -> str:
        return _timeout_suitability_run_id(source_commit, self.manifest.raw_digest)

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        try:
            validate_timeout_suitability_bundle(bundle)
        except EvidenceContractError as error:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_EXISTING_INVALID") from error
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _timeout_suitability_run_id(source, manifest),
            mismatch_code="TIMEOUT_SUITABILITY_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(
        self,
        *,
        timeout_seconds: int = TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
        max_transport_retries: int = TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
        target_sample_count: int = TIMEOUT_SUITABILITY_TARGET,
        output_path: Path | str | None = None,
    ) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (
            TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
            TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
            TIMEOUT_SUITABILITY_TARGET,
        ):
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        existing_count = 1 if existing is not None else 0
        return {
            "status": "cohort_complete" if existing is not None else "dry_run_timeout_suitability",
            "experiment_type": TIMEOUT_SUITABILITY_EXPERIMENT_TYPE,
            "schema_version": TIMEOUT_SUITABILITY_SCHEMA_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": TIMEOUT_SUITABILITY_PROVIDER,
            "model": TIMEOUT_SUITABILITY_MODEL,
            "transport": TIMEOUT_SUITABILITY_TRANSPORT,
            "structured_output_mode": TIMEOUT_SUITABILITY_STRUCTURED_OUTPUT_MODE,
            "case_id": "case_13",
            "timeout_seconds": TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
            "max_transport_retries": TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
            "target_sample_count": TIMEOUT_SUITABILITY_TARGET,
            "existing_sample_count": existing_count,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_path": destination.as_posix() if existing is not None else None,
        }

    def run(
        self,
        *,
        live: bool = False,
        timeout_seconds: int = TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
        max_transport_retries: int = TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
        target_sample_count: int = TIMEOUT_SUITABILITY_TARGET,
        expected_source_commit: str | None = None,
        resume: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        model_factory: Callable[[], Any] | None = None,
        enforce_clean_tree: bool = True,
    ) -> dict[str, object]:
        if not live:
            if resume or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("TIMEOUT_SUITABILITY_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_sample_count,
                output_path=output_path,
            )
        if (timeout_seconds, max_transport_retries, target_sample_count) != (
            TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
            TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
            TIMEOUT_SUITABILITY_TARGET,
        ):
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        if enforce_clean_tree:
            dirty = tuple(
                path
                for path in _dirty_paths(self.root)
                if path not in {TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH, TIMEOUT_SUITABILITY_TEMP_RELATIVE_PATH}
            )
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        if existing is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_RESULT_EXISTS")
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_MODEL_ARGUMENTS_INVALID")
        provider_model = shadow_model
        if provider_model is None:
            try:
                if model_factory is not None:
                    provider_model = model_factory()
                else:
                    environment = {
                        "NPC_AGENT_MODEL": "live",
                        "NPC_LLM_PROVIDER": TIMEOUT_SUITABILITY_PROVIDER,
                        "NPC_LLM_MODEL": TIMEOUT_SUITABILITY_MODEL,
                        "NPC_LLM_TRANSPORT": TIMEOUT_SUITABILITY_TRANSPORT,
                        "NPC_LLM_STRUCTURED_OUTPUT": TIMEOUT_SUITABILITY_STRUCTURED_OUTPUT_MODE,
                        "NPC_LLM_TIMEOUT_SECONDS": str(TIMEOUT_SUITABILITY_TIMEOUT_SECONDS),
                        "NPC_LLM_MAX_RETRIES": str(TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES),
                        **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
                    }
                    provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        if provider_model is None:
            raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED")
        router = ShadowEvidenceModelRouter(provider_model)
        agent = CharacterGenerationAgent(
            router,
            shadow_config=SkillShadowConfig(enabled=True),
            retrieval_strategy="deterministic",
        )
        case = self.cases["case_13"]
        try:
            result = agent.generate(case.request(), skill_shadow_context=case.context)
            record = _record_from_result(case, run_id, 1, result, router)
        except EvidenceRunnerError:
            raise
        except Exception:
            record = ShadowEvidenceRunner(self.root)._runner_failure_record(case, run_id, 1)
        invocation = router.shadow_invocation
        _validate_invocation_profile(invocation)
        if invocation is not None and invocation.model != TIMEOUT_SUITABILITY_MODEL:
            raise EvidenceRunnerError("TIMEOUT_SUITABILITY_MODEL_DRIFT")
        record["observation"]["observation_id"] = f"{run_id}:case_13:sample-01"
        record_body = {
            "observation": record["observation"],
            "audit": record["audit"],
            "sanitization": record["sanitization"],
        }
        record["record_digest"] = _record_digest(record_body)
        reported_model = _safe_model_name(invocation.model if invocation is not None else None)
        bundle = {
            "schema_version": TIMEOUT_SUITABILITY_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": TIMEOUT_SUITABILITY_EXPERIMENT_TYPE,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _timeout_suitability_provider(reported_model),
            "case_id": "case_13",
            "target_sample_count": TIMEOUT_SUITABILITY_TARGET,
            "sample_index": 1,
            "complete": True,
            "baseline": {
                "experiment_type": FIXED_COMPLIANCE_COHORT_TYPE,
                "timeout_seconds": TIMEOUT_SECONDS,
                "bundle_sha256": TIMEOUT_SUITABILITY_BASELINE_SHA256,
            },
            "observation": record,
        }
        bundle["bundle_digest"] = _timeout_suitability_bundle_digest(bundle)
        validate_timeout_suitability_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


class ModelSuitabilityProbeRunner:
    """Run one isolated DeepSeek V4 Pro model-suitability observation."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / MODEL_SUITABILITY_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        specs = (
            ("original", RESULT_RELATIVE_TEMPLATE.format(repeat=1), validate_evidence_bundle),
            ("retry", RETRY_RESULT_RELATIVE_PATH, validate_retry_evidence_bundle),
            ("shape", DIAGNOSTIC_RESULT_RELATIVE_PATH, validate_shape_diagnostic_bundle),
            ("compliance", COMPLIANCE_RESULT_RELATIVE_PATH, validate_contract_compliance_bundle),
            ("fixed", FIXED_COMPLIANCE_RESULT_RELATIVE_PATH, validate_fixed_contract_compliance_bundle),
            ("flash_timeout", TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH, validate_timeout_suitability_bundle),
        )
        expected_sha = {
            **TIMEOUT_SUITABILITY_HISTORICAL_SHA256,
            "flash_timeout": MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256,
        }
        for name, relative, validator in specs:
            path = self.root / relative
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise EvidenceRunnerError("MODEL_SUITABILITY_HISTORY_MISSING") from error
            if _digest_bytes(raw) != expected_sha[name]:
                raise EvidenceRunnerError("MODEL_SUITABILITY_HISTORY_MUTATED")
            bundle, _ = _load_json(path)
            try:
                validator(bundle)
            except EvidenceContractError as error:
                raise EvidenceRunnerError("MODEL_SUITABILITY_HISTORY_INVALID") from error

    def _identity(self, source_commit: str) -> str:
        return _model_suitability_run_id(source_commit, self.manifest.raw_digest)

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        try:
            validate_model_suitability_bundle(bundle)
        except EvidenceContractError as error:
            raise EvidenceRunnerError("MODEL_SUITABILITY_EXISTING_INVALID") from error
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _model_suitability_run_id(source, manifest),
            mismatch_code="MODEL_SUITABILITY_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(
        self,
        *,
        timeout_seconds: int = MODEL_SUITABILITY_TIMEOUT_SECONDS,
        max_transport_retries: int = MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
        target_sample_count: int = MODEL_SUITABILITY_TARGET,
        output_path: Path | str | None = None,
    ) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (
            MODEL_SUITABILITY_TIMEOUT_SECONDS,
            MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
            MODEL_SUITABILITY_TARGET,
        ):
            raise EvidenceRunnerError("MODEL_SUITABILITY_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        return {
            "status": "cohort_complete" if existing is not None else "dry_run_model_suitability",
            "experiment_type": MODEL_SUITABILITY_EXPERIMENT_TYPE,
            "schema_version": MODEL_SUITABILITY_SCHEMA_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": MODEL_SUITABILITY_PROVIDER,
            "model": MODEL_SUITABILITY_MODEL,
            "transport": MODEL_SUITABILITY_TRANSPORT,
            "structured_output_mode": MODEL_SUITABILITY_STRUCTURED_OUTPUT_MODE,
            "case_id": "case_13",
            "timeout_seconds": MODEL_SUITABILITY_TIMEOUT_SECONDS,
            "max_transport_retries": MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
            "target_sample_count": MODEL_SUITABILITY_TARGET,
            "existing_sample_count": 1 if existing is not None else 0,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "provider_factory_constructed": False,
            "provider_called": False,
            "result_path": destination.as_posix() if existing is not None else None,
        }

    def run(
        self,
        *,
        live: bool = False,
        timeout_seconds: int = MODEL_SUITABILITY_TIMEOUT_SECONDS,
        max_transport_retries: int = MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
        target_sample_count: int = MODEL_SUITABILITY_TARGET,
        expected_source_commit: str | None = None,
        resume: bool = False,
        output_path: Path | str | None = None,
        shadow_model: Any | None = None,
        model_factory: Callable[[], Any] | None = None,
        enforce_clean_tree: bool = True,
    ) -> dict[str, object]:
        if not live:
            if resume or shadow_model is not None or model_factory is not None:
                raise EvidenceRunnerError("MODEL_SUITABILITY_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_sample_count,
                output_path=output_path,
            )
        if (timeout_seconds, max_transport_retries, target_sample_count) != (
            MODEL_SUITABILITY_TIMEOUT_SECONDS,
            MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
            MODEL_SUITABILITY_TARGET,
        ):
            raise EvidenceRunnerError("MODEL_SUITABILITY_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("MODEL_SUITABILITY_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("MODEL_SUITABILITY_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        if enforce_clean_tree:
            dirty = tuple(
                path for path in _dirty_paths(self.root)
                if path not in {MODEL_SUITABILITY_RESULT_RELATIVE_PATH, MODEL_SUITABILITY_TEMP_RELATIVE_PATH}
            )
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        if existing is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("MODEL_SUITABILITY_RESULT_EXISTS")
        if shadow_model is not None and model_factory is not None:
            raise EvidenceRunnerError("MODEL_SUITABILITY_MODEL_ARGUMENTS_INVALID")
        provider_model = shadow_model
        if provider_model is None:
            try:
                if model_factory is not None:
                    provider_model = model_factory()
                else:
                    environment = {
                        "NPC_AGENT_MODEL": "live",
                        "NPC_LLM_PROVIDER": MODEL_SUITABILITY_PROVIDER,
                        "NPC_LLM_MODEL": MODEL_SUITABILITY_MODEL,
                        "NPC_LLM_TRANSPORT": MODEL_SUITABILITY_TRANSPORT,
                        "NPC_LLM_STRUCTURED_OUTPUT": MODEL_SUITABILITY_STRUCTURED_OUTPUT_MODE,
                        "NPC_LLM_TIMEOUT_SECONDS": str(MODEL_SUITABILITY_TIMEOUT_SECONDS),
                        "NPC_LLM_MAX_RETRIES": str(MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES),
                        **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
                    }
                    provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        if provider_model is None:
            raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED")
        router = ShadowEvidenceModelRouter(provider_model)
        agent = CharacterGenerationAgent(
            router,
            shadow_config=SkillShadowConfig(enabled=True),
            retrieval_strategy="deterministic",
        )
        case = self.cases["case_13"]
        try:
            result = agent.generate(case.request(), skill_shadow_context=case.context)
            record = _record_from_result(case, run_id, 1, result, router)
        except EvidenceRunnerError:
            raise
        except Exception:
            record = ShadowEvidenceRunner(self.root)._runner_failure_record(case, run_id, 1)
        invocation = router.shadow_invocation
        _validate_invocation_profile(invocation)
        if invocation is not None and invocation.model != MODEL_SUITABILITY_MODEL:
            raise EvidenceRunnerError("MODEL_SUITABILITY_MODEL_DRIFT")
        record["observation"]["observation_id"] = f"{run_id}:case_13:sample-01"
        record_body = {
            "observation": record["observation"],
            "audit": record["audit"],
            "sanitization": record["sanitization"],
        }
        record["record_digest"] = _record_digest(record_body)
        reported_model = _safe_model_name(invocation.model if invocation is not None else None)
        bundle = {
            "schema_version": MODEL_SUITABILITY_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": MODEL_SUITABILITY_EXPERIMENT_TYPE,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _model_suitability_provider(reported_model),
            "case_id": "case_13",
            "target_sample_count": MODEL_SUITABILITY_TARGET,
            "sample_index": 1,
            "complete": True,
            "baseline": {
                "experiment_type": TIMEOUT_SUITABILITY_EXPERIMENT_TYPE,
                "model": TIMEOUT_SUITABILITY_MODEL,
                "timeout_seconds": MODEL_SUITABILITY_TIMEOUT_SECONDS,
                "bundle_sha256": MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256,
            },
            "observation": record,
        }
        bundle["bundle_digest"] = _model_suitability_bundle_digest(bundle)
        validate_model_suitability_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


class _MinimalTransportAdapter(LiveLLMAdapter):
    """LiveLLMAdapter variant that keeps the tiny diagnostic contract isolated."""

    @classmethod
    def _provider_messages(cls, prompt: AgentPrompt) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": "Return exactly one JSON object with one field, status, whose value is exactly ok. Return no prose, Markdown, code fence, or additional fields.",
            },
            {"role": "user", "content": "{}"},
        ]

    def _response_contract(self, prompt: AgentPrompt) -> NegotiatedResponseContract:
        if not self.profile.capabilities.supports_json_object:
            raise RuntimeError("minimal transport contract requires JSON Object capability")
        return NegotiatedResponseContract("minimal_transport_sanity", ResponseMode.JSON_OBJECT)

    def _normalize(
        self,
        response: ProviderCompletion,
        prompt: AgentPrompt,
        started: float,
        retry_count: int,
    ) -> ModelTurn:
        latency_ms = (self._monotonic() - started) * 1000
        invocation = ModelInvocationAudit(
            session_id=prompt.session_id,
            turn_number=prompt.turn_number,
            provider=self.provider,
            model=self.model,
            outcome="success",
            latency_ms=latency_ms,
            retry_count=retry_count,
            finish_reason=response.finish_reason,
            usage=response.usage,
            provider_request_id=response.request_id,
            transport=self.transport,
            response_contract=ResponseMode.JSON_OBJECT.value,
            purpose=prompt.invocation_purpose,
        )
        return ModelTurn(
            text=response.text,
            finish_reason=response.finish_reason,
            usage=response.usage,
            provider_request_id=response.request_id,
            invocation=invocation,
        )


def _minimal_top_level_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "unknown"


def _minimal_contract_result(text: object) -> dict[str, object]:
    if not isinstance(text, str):
        return {
            "json_extraction_outcome": "failed",
            "tiny_contract_outcome": "TRANSPORT_SUCCESS_CONTRACT_REJECTED",
            "parsed_top_level_type": "invalid",
            "actual_key_count": None,
        }
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {
            "json_extraction_outcome": "failed",
            "tiny_contract_outcome": "TRANSPORT_SUCCESS_CONTRACT_REJECTED",
            "parsed_top_level_type": "invalid",
            "actual_key_count": None,
        }
    top_level = _minimal_top_level_type(parsed)
    key_count = len(parsed) if isinstance(parsed, dict) else None
    passed = isinstance(parsed, dict) and set(parsed) == {"status"} and parsed.get("status") == "ok"
    return {
        "json_extraction_outcome": "parsed",
        "tiny_contract_outcome": "TRANSPORT_SUCCESS_CONTRACT_PASS" if passed else "TRANSPORT_SUCCESS_CONTRACT_REJECTED",
        "parsed_top_level_type": top_level,
        "actual_key_count": key_count,
    }


class MinimalTransportSanityRunner:
    """Run one diagnostic-only tiny JSON request through the existing stack."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        specs = (
            (RESULT_RELATIVE_TEMPLATE.format(repeat=1), validate_evidence_bundle, "b84bba6063f2b9bb77c0b9d88ba36a3d0f92a5e23a2b022b87d67d55f117b7a3"),
            (RETRY_RESULT_RELATIVE_PATH, validate_retry_evidence_bundle, "7722165cae52cb858078ad9725a516d5ac04cdb8d41824e8d71826eea4989a31"),
            (DIAGNOSTIC_RESULT_RELATIVE_PATH, validate_shape_diagnostic_bundle, "89b44f5413ab92a418958d2659880b69635ca0bc7a135123afd5579af8898215"),
            (COMPLIANCE_RESULT_RELATIVE_PATH, validate_contract_compliance_bundle, "5ef5fde8fe677d634eedd017948e84c50802f04603df1144dc6360a7f8176803"),
            (FIXED_COMPLIANCE_RESULT_RELATIVE_PATH, validate_fixed_contract_compliance_bundle, "99bd6f48e04c1262292468b64ded78c4eb9c6160f94ddba9386bea580d76e46d"),
            (TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH, validate_timeout_suitability_bundle, MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256),
            (MODEL_SUITABILITY_RESULT_RELATIVE_PATH, validate_model_suitability_bundle, "b96e1a822af9af6f4f805e12c9d38750fecbb0eb76b488f183fe14005a7fdcbb"),
        )
        for relative, validator, expected_sha in specs:
            path = self.root / relative
            try:
                raw = path.read_bytes()
                bundle, _ = _load_json(path)
                validator(bundle)
            except (OSError, EvidenceRunnerError) as error:
                raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_HISTORY_INVALID") from error
            if _digest_bytes(raw) != expected_sha:
                raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_HISTORY_MUTATED")

    def _identity(self, source_commit: str) -> str:
        return _minimal_transport_sanity_run_id(source_commit)

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        try:
            validate_minimal_transport_sanity_bundle(bundle)
        except EvidenceContractError as error:
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_EXISTING_INVALID") from error
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _minimal_transport_sanity_run_id(source),
            mismatch_code="MINIMAL_TRANSPORT_SANITY_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        return {
            "status": "cohort_complete" if existing is not None else "dry_run_minimal_transport_sanity",
            "experiment_type": MINIMAL_TRANSPORT_SANITY_EXPERIMENT_TYPE,
            "schema_version": MINIMAL_TRANSPORT_SANITY_SCHEMA_VERSION,
            "tiny_contract_version": MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": MINIMAL_TRANSPORT_SANITY_PROVIDER,
            "model": MINIMAL_TRANSPORT_SANITY_MODEL,
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "existing_sample_count": 1 if existing is not None else 0,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "provider_factory_constructed": False,
            "provider_called": False,
            "output_path": destination.as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH, MINIMAL_TRANSPORT_SANITY_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        if self._load_existing(destination, run_id) is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("MINIMAL_TRANSPORT_SANITY_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live",
                "NPC_LLM_PROVIDER": MINIMAL_TRANSPORT_SANITY_PROVIDER,
                "NPC_LLM_MODEL": MINIMAL_TRANSPORT_SANITY_MODEL,
                "NPC_LLM_TRANSPORT": MINIMAL_TRANSPORT_SANITY_TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": MINIMAL_TRANSPORT_SANITY_STRUCTURED_OUTPUT_MODE,
                "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            settings = __import__("agents.model_factory", fromlist=["LiveLLMSettings"]).LiveLLMSettings.from_environment(environment)
            client = OpenAIChatClient(api_key=settings.api_key, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds, request_options=settings.profile.provider_options)
            provider_model = _MinimalTransportAdapter(client, provider=settings.provider, model=settings.model, profile=settings.profile, timeout_seconds=settings.timeout_seconds, max_retries=settings.max_retries)
        prompt = AgentPrompt(
            "minimal_transport_sanity",
            NpcCharacterView("diagnostic", "diagnostic", "diagnostic", (), (), "neutral", "neutral", (), "neutral", "diagnostic"),
            NpcRuntimeView("diagnostic", "diagnostic", None, (), ()),
            (ConversationMessage("user", "{}"),),
            (),
            "cs-s2-minimal-transport-sanity",
            1,
            response_format="minimal_transport_sanity",
            invocation_purpose="minimal_transport_sanity",
        )
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_result = {"json_extraction_outcome": "not_attempted", "tiny_contract_outcome": "TRANSPORT_UNAVAILABLE", "parsed_top_level_type": None, "actual_key_count": None}
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(prompt)
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = _minimal_contract_result(turn.text)
            failure_stage = None
            failure_code = None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
        observation = {
            "observation_id": f"{run_id}:sample-01",
            "provider_outcome": provider_outcome,
            "transport_attempts": attempts,
            "latency_ms": latency_ms,
            "json_extraction_outcome": json_result["json_extraction_outcome"],
            "tiny_contract_outcome": json_result["tiny_contract_outcome"],
            "parsed_top_level_type": json_result["parsed_top_level_type"],
            "expected_key_count": 1,
            "actual_key_count": json_result["actual_key_count"],
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": MINIMAL_TRANSPORT_SANITY_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": MINIMAL_TRANSPORT_SANITY_EXPERIMENT_TYPE,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _minimal_transport_sanity_provider(),
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "complete": True,
            "tiny_contract_version": MINIMAL_TRANSPORT_SANITY_TINY_CONTRACT_VERSION,
            "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _minimal_transport_sanity_bundle_digest(bundle)
        validate_minimal_transport_sanity_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _full_input_projection(case: ShadowEvidenceCase) -> dict[str, object]:
    return {
        "brief": case.brief,
        "hard_constraints": list(case.hard_constraints),
        "forbidden_elements": list(case.forbidden_elements),
        "combat_role_profile": _role_mapping(case.combat_role_profile),
    }


def _full_input_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"],
        tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]),
        projection["combat_role_profile"],
    )
    return AgentPrompt(
        character_skill_kit_prompt_contract()
        + "\n\n"
        + FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION,
        view,
        view,
        (ConversationMessage("user", _canonical_json(projection)),),
        (),
        "cs-s2-full-input-tiny-output",
        1,
        response_format=RESPONSE_CONTRACT,
        authoring_payload=projection,
        invocation_purpose="full_input_tiny_output",
    )


def _message_metrics(messages: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_role: dict[str, dict[str, int]] = {}
    for message in messages:
        role = str(message.get("role", "unknown"))
        content = message.get("content", "")
        text = content if isinstance(content, str) else str(content)
        by_role[role] = {
            "chars": len(text),
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n") + 1,
        }
    return {
        "message_count": len(messages),
        "chars": sum(item["chars"] for item in by_role.values()),
        "bytes": sum(item["bytes"] for item in by_role.values()),
        "by_role": by_role,
    }


def _historical_full_input_metrics(case: ShadowEvidenceCase) -> dict[str, object]:
    messages = LiveLLMAdapter._provider_messages(
        ShadowEvidenceModelRouter._rebuild_shadow_prompt(_full_input_prompt(case))
    )
    return _message_metrics(messages)


class _FullInputTinyOutputAdapter(_MinimalTransportAdapter):
    @classmethod
    def _provider_messages(cls, prompt: AgentPrompt) -> list[dict[str, Any]]:
        contract = prompt.system_contract
        system = (
            f"{contract}\n\n"
            "Return only the requested Character SkillKit candidate root JSON object.\n\n"
            f"{FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION}"
        )
        projection = prompt.authoring_payload or {}
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": _canonical_json(dict(projection))},
        ]


def _full_input_tiny_output_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-full-input-tiny-output-v0.1.0-opencode_go-deepseek-v4-pro-case_13-"
        f"t60-r0-n1-{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _full_input_tiny_output_provider() -> dict[str, object]:
    return {
        "name": FULL_INPUT_TINY_OUTPUT_PROVIDER,
        "model_requested": FULL_INPUT_TINY_OUTPUT_MODEL,
        "model_reported": FULL_INPUT_TINY_OUTPUT_MODEL,
        "transport": "openai_chat_completions",
        "structured_output_mode": "json_object",
        "timeout_seconds": FULL_INPUT_TINY_OUTPUT_TIMEOUT_SECONDS,
        "max_transport_retries": FULL_INPUT_TINY_OUTPUT_MAX_TRANSPORT_RETRIES,
    }


def _full_input_tiny_output_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def validate_full_input_tiny_output_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "source_commit",
        "manifest_digest", "input_manifest_digest", "inputs", "provider", "case_id",
        "timeout_seconds", "max_transport_retries", "target_sample_count", "complete",
        "input_contract_version", "tiny_output_contract_version", "historical_full_input",
        "request_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "FULL_INPUT_TINY_OUTPUT_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != FULL_INPUT_TINY_OUTPUT_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != FULL_INPUT_TINY_OUTPUT_EXPERIMENT_TYPE
        or bundle["case_id"] != "case_13"
        or bundle["timeout_seconds"] != 60
        or bundle["max_transport_retries"] != 0
        or bundle["target_sample_count"] != 1
        or bundle["complete"] is not True
        or bundle["input_contract_version"] != FULL_INPUT_TINY_OUTPUT_INPUT_CONTRACT_VERSION
        or bundle["tiny_output_contract_version"] != FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION
    ):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_CONFIG_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _FULL_INPUT_TINY_OUTPUT_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_RUN_ID_INVALID")
    if bundle["sample_index"] != 1:
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_SAMPLE_INVALID")
    for key in ("historical_full_input", "request_metrics"):
        value = bundle[key]
        if not isinstance(value, Mapping):
            raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_METRICS_INVALID")
    provider = bundle["provider"]
    if provider != _full_input_tiny_output_provider():
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_OBSERVATION_INVALID")
    _exact_keys(
        observation,
        {"observation_id", "provider_outcome", "transport_attempts", "latency_ms", "json_extraction_outcome", "tiny_contract_outcome", "parsed_top_level_type", "expected_key_count", "actual_key_count", "failure_stage", "failure_code", "sanitization"},
        "FULL_INPUT_TINY_OUTPUT_OBSERVATION_KEYS_INVALID",
    )
    if observation["observation_id"] != f"{bundle['run_id']}:sample-01" or observation["transport_attempts"] != 1:
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_OBSERVATION_INVALID")
    if observation["tiny_contract_outcome"] not in {"FULL_INPUT_TINY_OUTPUT_PASS", "PROVIDER_SUCCESS_TINY_CONTRACT_REJECTED", "FULL_INPUT_TINY_OUTPUT_UNAVAILABLE"}:
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_OUTCOME_INVALID")
    if observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_SANITIZATION_INVALID")
    if bundle["bundle_digest"] != _full_input_tiny_output_bundle_digest(bundle):
        raise EvidenceContractError("FULL_INPUT_TINY_OUTPUT_BUNDLE_DIGEST_INVALID")


class FullInputTinyOutputRunner:
    """Probe the full SkillKit input with a tiny diagnostic completion."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / FULL_INPUT_TINY_OUTPUT_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        specs = (
            (RESULT_RELATIVE_TEMPLATE.format(repeat=1), validate_evidence_bundle, "b84bba6063f2b9bb77c0b9d88ba36a3d0f92a5e23a2b022b87d67d55f117b7a3"),
            (RETRY_RESULT_RELATIVE_PATH, validate_retry_evidence_bundle, "7722165cae52cb858078ad9725a516d5ac04cdb8d41824e8d71826eea4989a31"),
            (DIAGNOSTIC_RESULT_RELATIVE_PATH, validate_shape_diagnostic_bundle, "89b44f5413ab92a418958d2659880b69635ca0bc7a135123afd5579af8898215"),
            (COMPLIANCE_RESULT_RELATIVE_PATH, validate_contract_compliance_bundle, "5ef5fde8fe677d634eedd017948e84c50802f04603df1144dc6360a7f8176803"),
            (FIXED_COMPLIANCE_RESULT_RELATIVE_PATH, validate_fixed_contract_compliance_bundle, "99bd6f48e04c1262292468b64ded78c4eb9c6160f94ddba9386bea580d76e46d"),
            (TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH, validate_timeout_suitability_bundle, MODEL_SUITABILITY_FLASH_TIMEOUT_SHA256),
            (MODEL_SUITABILITY_RESULT_RELATIVE_PATH, validate_model_suitability_bundle, "b96e1a822af9af6f4f805e12c9d38750fecbb0eb76b488f183fe14005a7fdcbb"),
            (MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH, validate_minimal_transport_sanity_bundle, "791c886de9ecbfe2e29893effb57f625d21d6f7670bdc7e1f0d0b038f03cbda0"),
        )
        for relative, validator, expected_sha in specs:
            path = self.root / relative
            try:
                raw = path.read_bytes()
                bundle, _ = _load_json(path)
                validator(bundle)
            except (OSError, EvidenceRunnerError) as error:
                raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_HISTORY_INVALID") from error
            if _digest_bytes(raw) != expected_sha:
                raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_HISTORY_MUTATED")

    def _identity(self, source_commit: str) -> str:
        return _full_input_tiny_output_run_id(source_commit, self.manifest.raw_digest)

    def _metrics(self) -> tuple[dict[str, object], dict[str, object]]:
        case = self.cases["case_13"]
        historical = _historical_full_input_metrics(case)
        prompt = _full_input_prompt(case)
        messages = _FullInputTinyOutputAdapter._provider_messages(prompt)
        metrics = _message_metrics(messages)
        if metrics["chars"] < FULL_INPUT_TINY_OUTPUT_HISTORICAL_CHARS * 0.9:
            raise EvidenceRunnerError("BLOCKED_FULL_INPUT_NOT_PRESERVED")
        return historical, metrics

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        try:
            validate_full_input_tiny_output_bundle(bundle)
        except EvidenceContractError as error:
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_EXISTING_INVALID") from error
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _full_input_tiny_output_run_id(source, manifest),
            mismatch_code="FULL_INPUT_TINY_OUTPUT_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        historical, metrics = self._metrics()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        existing = self._load_existing(destination, run_id)
        return {
            "status": "cohort_complete" if existing is not None else "dry_run_full_input_tiny_output",
            "experiment_type": FULL_INPUT_TINY_OUTPUT_EXPERIMENT_TYPE,
            "schema_version": FULL_INPUT_TINY_OUTPUT_SCHEMA_VERSION,
            "input_contract_version": FULL_INPUT_TINY_OUTPUT_INPUT_CONTRACT_VERSION,
            "tiny_output_contract_version": FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": FULL_INPUT_TINY_OUTPUT_PROVIDER,
            "model": FULL_INPUT_TINY_OUTPUT_MODEL,
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "historical_full_input": historical,
            "request_metrics": metrics,
            "existing_sample_count": 1 if existing is not None else 0,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "input_preservation_ratio": metrics["chars"] / FULL_INPUT_TINY_OUTPUT_HISTORICAL_CHARS,
            "provider_factory_constructed": False,
            "provider_called": False,
            "output_path": destination.as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        historical, metrics = self._metrics()
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {FULL_INPUT_TINY_OUTPUT_RESULT_RELATIVE_PATH, FULL_INPUT_TINY_OUTPUT_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = self._identity(source_commit)
        if self._load_existing(destination, run_id) is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("FULL_INPUT_TINY_OUTPUT_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live",
                "NPC_LLM_PROVIDER": FULL_INPUT_TINY_OUTPUT_PROVIDER,
                "NPC_LLM_MODEL": FULL_INPUT_TINY_OUTPUT_MODEL,
                "NPC_LLM_TRANSPORT": "openai_chat_completions",
                "NPC_LLM_STRUCTURED_OUTPUT": "json_object",
                "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            settings = __import__("agents.model_factory", fromlist=["LiveLLMSettings"]).LiveLLMSettings.from_environment(environment)
            client = OpenAIChatClient(api_key=settings.api_key, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds, request_options=settings.profile.provider_options)
            provider_model = _FullInputTinyOutputAdapter(client, provider=settings.provider, model=settings.model, profile=settings.profile, timeout_seconds=settings.timeout_seconds, max_retries=settings.max_retries)
        case = self.cases["case_13"]
        prompt = _full_input_prompt(case)
        try:
            turn = provider_model.generate(prompt)
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = _minimal_contract_result(turn.text)
            if json_result["tiny_contract_outcome"] == "TRANSPORT_SUCCESS_CONTRACT_PASS":
                contract_outcome = "FULL_INPUT_TINY_OUTPUT_PASS"
            else:
                contract_outcome = "PROVIDER_SUCCESS_TINY_CONTRACT_REJECTED"
            failure_stage = None
            failure_code = None
        except ModelError as error:
            invocation = error.audit
            provider_outcome = "failure"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = {"json_extraction_outcome": "not_attempted", "tiny_contract_outcome": "TRANSPORT_UNAVAILABLE", "parsed_top_level_type": None, "actual_key_count": None}
            contract_outcome = "FULL_INPUT_TINY_OUTPUT_UNAVAILABLE"
            failure_stage = "provider"
            failure_code = "PROVIDER_INVOCATION_FAILED"
        observation = {
            "observation_id": f"{run_id}:sample-01",
            "provider_outcome": provider_outcome,
            "transport_attempts": attempts,
            "latency_ms": latency_ms,
            "json_extraction_outcome": json_result["json_extraction_outcome"],
            "tiny_contract_outcome": contract_outcome,
            "parsed_top_level_type": json_result["parsed_top_level_type"],
            "expected_key_count": 1,
            "actual_key_count": json_result["actual_key_count"],
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": FULL_INPUT_TINY_OUTPUT_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": FULL_INPUT_TINY_OUTPUT_EXPERIMENT_TYPE,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _full_input_tiny_output_provider(),
            "case_id": "case_13",
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "complete": True,
            "input_contract_version": FULL_INPUT_TINY_OUTPUT_INPUT_CONTRACT_VERSION,
            "tiny_output_contract_version": FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION,
            "historical_full_input": historical,
            "request_metrics": metrics,
            "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _full_input_tiny_output_bundle_digest(bundle)
        validate_full_input_tiny_output_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _enum_stepdown_contract() -> str:
    """Build the diagnostic L1 contract without changing production output."""

    full = character_skill_kit_prompt_contract()
    prefix, marker, enum_section = full.partition("\nClosed enum vocabulary:\n")
    if not marker or len(full) != 4889 or len(enum_section.splitlines()) != 58:
        raise EvidenceRunnerError("ENUM_STEPDOWN_CONTRACT_SOURCE_INVALID")
    return prefix + "\n\nUse only valid canonical enum values defined by the SkillKit contract."


def _enum_stepdown_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"],
        tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]),
        projection["combat_role_profile"],
    )
    return AgentPrompt(
        _enum_stepdown_contract() + "\n\n" + FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION,
        view,
        view,
        (ConversationMessage("user", _canonical_json(projection)),),
        (),
        "cs-s2-enum-expansion-stepdown",
        1,
        response_format=RESPONSE_CONTRACT,
        authoring_payload=projection,
        invocation_purpose=ENUM_STEPOWDOWN_EXPERIMENT_TYPE,
    )


def _enum_stepdown_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-enum-expansion-stepdown-v0.1.0-L1_NO_ENUM_EXPANSION-"
        "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-"
        f"{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _enum_stepdown_provider() -> dict[str, object]:
    return {
        "name": ENUM_STEPOWDOWN_PROVIDER,
        "model_requested": ENUM_STEPOWDOWN_MODEL,
        "model_reported": ENUM_STEPOWDOWN_MODEL,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "timeout_seconds": ENUM_STEPOWDOWN_TIMEOUT_SECONDS,
        "max_transport_retries": ENUM_STEPOWDOWN_MAX_TRANSPORT_RETRIES,
    }


def _enum_stepdown_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def validate_enum_stepdown_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "level",
        "contract_variant_version", "source_commit", "manifest_digest", "input_manifest_digest",
        "inputs", "provider", "case_id", "timeout_seconds", "max_transport_retries",
        "target_sample_count", "complete", "input_contract_version", "tiny_output_contract_version",
        "l0_request_metrics", "l1_request_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "ENUM_STEPDOWN_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != ENUM_STEPOWDOWN_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != ENUM_STEPOWDOWN_EXPERIMENT_TYPE
        or bundle["level"] != ENUM_STEPOWDOWN_LEVEL
        or bundle["contract_variant_version"] != ENUM_STEPOWDOWN_CONTRACT_VERSION
        or bundle["case_id"] != "case_13"
        or bundle["timeout_seconds"] != ENUM_STEPOWDOWN_TIMEOUT_SECONDS
        or bundle["max_transport_retries"] != ENUM_STEPOWDOWN_MAX_TRANSPORT_RETRIES
        or bundle["target_sample_count"] != ENUM_STEPOWDOWN_TARGET
        or bundle["complete"] is not True
        or bundle["input_contract_version"] != ENUM_STEPOWDOWN_CONTRACT_VERSION
        or bundle["tiny_output_contract_version"] != FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION
        or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("ENUM_STEPDOWN_CONFIG_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("ENUM_STEPDOWN_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("ENUM_STEPDOWN_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _ENUM_STEPOWDOWN_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("ENUM_STEPDOWN_RUN_ID_INVALID")
    if bundle["provider"] != _enum_stepdown_provider():
        raise EvidenceContractError("ENUM_STEPDOWN_PROVIDER_INVALID")
    for key in ("l0_request_metrics", "l1_request_metrics"):
        if not isinstance(bundle[key], Mapping):
            raise EvidenceContractError("ENUM_STEPDOWN_METRICS_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("ENUM_STEPDOWN_OBSERVATION_INVALID")
    _exact_keys(
        observation,
        {
            "observation_id", "provider_outcome", "transport_attempts", "latency_ms",
            "json_extraction_outcome", "tiny_contract_outcome", "parsed_top_level_type",
            "expected_key_count", "actual_key_count", "failure_stage", "failure_code", "sanitization",
        },
        "ENUM_STEPDOWN_OBSERVATION_KEYS_INVALID",
    )
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01":
        raise EvidenceContractError("ENUM_STEPDOWN_OBSERVATION_ID_INVALID")
    if observation["transport_attempts"] != 1:
        raise EvidenceContractError("ENUM_STEPDOWN_ATTEMPT_INVALID")
    if observation["tiny_contract_outcome"] not in {
        "L1_ENUM_STEPDOWN_PASS",
        "L1_ENUM_STEPDOWN_TRANSPORT_REACHABLE_CONTRACT_REJECTED",
        "L1_ENUM_STEPDOWN_UNAVAILABLE",
    }:
        raise EvidenceContractError("ENUM_STEPDOWN_OUTCOME_INVALID")
    if observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("ENUM_STEPDOWN_SANITIZATION_INVALID")
    if bundle["bundle_digest"] != _enum_stepdown_bundle_digest(bundle):
        raise EvidenceContractError("ENUM_STEPDOWN_BUNDLE_DIGEST_INVALID")


class EnumExpansionStepdownRunner:
    """Run the single, diagnostic-only L1 no-enum probe."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / ENUM_STEPOWDOWN_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        FullInputTinyOutputRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        path = self.root / FULL_INPUT_TINY_OUTPUT_RESULT_RELATIVE_PATH
        try:
            raw = path.read_bytes()
            bundle, _ = _load_json(path)
            validate_full_input_tiny_output_bundle(bundle)
        except (OSError, EvidenceRunnerError) as error:
            raise EvidenceRunnerError("ENUM_STEPDOWN_HISTORY_INVALID") from error
        if _digest_bytes(raw) != "2810ea531ed4a1da501a95d946185d4201f926ee9ac7d6ed70bebcf1957ff9d9":
            raise EvidenceRunnerError("ENUM_STEPDOWN_HISTORY_MUTATED")

    def _metrics(self) -> tuple[dict[str, object], dict[str, object]]:
        case = self.cases["case_13"]
        l0 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_full_input_prompt(case)))
        l1 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_enum_stepdown_prompt(case)))
        if (l0["chars"], l0["bytes"]) != (ENUM_STEPOWDOWN_L0_CHARS, ENUM_STEPOWDOWN_L0_BYTES):
            raise EvidenceRunnerError("BLOCKED_L0_DIAGNOSTIC_DRIFT")
        if (l1["chars"], l1["bytes"]) != (ENUM_STEPOWDOWN_L1_CHARS, ENUM_STEPOWDOWN_L1_BYTES):
            raise EvidenceRunnerError("BLOCKED_L1_CONSTRUCTION_DRIFT")
        if not l1["chars"] < l0["chars"] * 0.5 or not l1["chars"] > 1000:
            raise EvidenceRunnerError("BLOCKED_L1_REDUCTION_INSUFFICIENT")
        system = _enum_stepdown_prompt(case).system_contract
        if "Closed enum vocabulary:" in system or "Use only valid canonical enum values defined by the SkillKit contract." not in system:
            raise EvidenceRunnerError("ENUM_STEPDOWN_STRUCTURE_INVALID")
        return l0, l1

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        validate_enum_stepdown_bundle(bundle)
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _enum_stepdown_run_id(source, manifest),
            mismatch_code="ENUM_STEPDOWN_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(
        self,
        *,
        timeout_seconds: int = 60,
        max_transport_retries: int = 0,
        target_sample_count: int = 1,
        output_path: Path | str | None = None,
    ) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("ENUM_STEPDOWN_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        l0, l1 = self._metrics()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = _enum_stepdown_run_id(source_commit, self.manifest.raw_digest)
        existing = self._load_existing(destination, run_id)
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing is not None else "dry_run_enum_expansion_stepdown",
            "experiment_type": ENUM_STEPOWDOWN_EXPERIMENT_TYPE,
            "level": ENUM_STEPOWDOWN_LEVEL,
            "contract_variant_version": ENUM_STEPOWDOWN_CONTRACT_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": ENUM_STEPOWDOWN_PROVIDER,
            "model": ENUM_STEPOWDOWN_MODEL,
            "case_id": "case_13",
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "l0_request_metrics": l0,
            "l1_request_metrics": l1,
            "l0_chars": l0["chars"],
            "l0_bytes": l0["bytes"],
            "l1_chars": l1["chars"],
            "l1_bytes": l1["bytes"],
            "char_reduction": l0["chars"] - l1["chars"],
            "byte_reduction": l0["bytes"] - l1["bytes"],
            "l1_l0_char_ratio": l1["chars"] / l0["chars"],
            "l1_l0_byte_ratio": l1["bytes"] / l0["bytes"],
            "enum_expansion_included": False,
            "enum_semantic_guidance_reduced": True,
            "nested_shape_included": True,
            "existing_sample_count": 1 if existing is not None else 0,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "provider_factory_constructed": False,
            "provider_called": False,
            "output_path": destination.as_posix(),
        }

    def run(
        self,
        *,
        live: bool = False,
        timeout_seconds: int = 60,
        max_transport_retries: int = 0,
        target_sample_count: int = 1,
        expected_source_commit: str | None = None,
        resume: bool = False,
        output_path: Path | str | None = None,
        model_factory: Callable[[], Any] | None = None,
        enforce_clean_tree: bool = True,
    ) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("ENUM_STEPDOWN_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("ENUM_STEPDOWN_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("ENUM_STEPDOWN_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("ENUM_STEPDOWN_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        l0, l1 = self._metrics()
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {ENUM_STEPOWDOWN_RESULT_RELATIVE_PATH, ENUM_STEPOWDOWN_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = _enum_stepdown_run_id(source_commit, self.manifest.raw_digest)
        if self._load_existing(destination, run_id) is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("ENUM_STEPDOWN_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live",
                "NPC_LLM_PROVIDER": ENUM_STEPOWDOWN_PROVIDER,
                "NPC_LLM_MODEL": ENUM_STEPOWDOWN_MODEL,
                "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            settings = __import__("agents.model_factory", fromlist=["LiveLLMSettings"]).LiveLLMSettings.from_environment(environment)
            client = OpenAIChatClient(api_key=settings.api_key, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds, request_options=settings.profile.provider_options)
            provider_model = _FullInputTinyOutputAdapter(client, provider=settings.provider, model=settings.model, profile=settings.profile, timeout_seconds=settings.timeout_seconds, max_retries=settings.max_retries)
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_result = {"json_extraction_outcome": "not_attempted", "tiny_contract_outcome": "TRANSPORT_UNAVAILABLE", "parsed_top_level_type": None, "actual_key_count": None}
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(_enum_stepdown_prompt(self.cases["case_13"]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = _minimal_contract_result(turn.text)
            contract_outcome = (
                "L1_ENUM_STEPDOWN_PASS"
                if json_result["tiny_contract_outcome"] == "TRANSPORT_SUCCESS_CONTRACT_PASS"
                else "L1_ENUM_STEPDOWN_TRANSPORT_REACHABLE_CONTRACT_REJECTED"
            )
            failure_stage = None
            failure_code = None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            contract_outcome = "L1_ENUM_STEPDOWN_UNAVAILABLE"
        observation = {
            "observation_id": f"{run_id}:case_13:sample-01",
            "provider_outcome": provider_outcome,
            "transport_attempts": attempts,
            "latency_ms": latency_ms,
            "json_extraction_outcome": json_result["json_extraction_outcome"],
            "tiny_contract_outcome": contract_outcome,
            "parsed_top_level_type": json_result["parsed_top_level_type"],
            "expected_key_count": 1,
            "actual_key_count": json_result["actual_key_count"],
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": ENUM_STEPOWDOWN_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": ENUM_STEPOWDOWN_EXPERIMENT_TYPE,
            "level": ENUM_STEPOWDOWN_LEVEL,
            "contract_variant_version": ENUM_STEPOWDOWN_CONTRACT_VERSION,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _enum_stepdown_provider(),
            "case_id": "case_13",
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "complete": True,
            "input_contract_version": ENUM_STEPOWDOWN_CONTRACT_VERSION,
            "tiny_output_contract_version": FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION,
            "l0_request_metrics": l0,
            "l1_request_metrics": l1,
            "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _enum_stepdown_bundle_digest(bundle)
        validate_enum_stepdown_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _nested_shape_stepdown_contract() -> str:
    """Build the diagnostic L2 root-plus-minimal-shape contract from schema."""

    from agents.response_contracts import CHARACTER_SKILL_KIT_JSON_SCHEMA

    required = tuple(CHARACTER_SKILL_KIT_JSON_SCHEMA["required"])
    properties = CHARACTER_SKILL_KIT_JSON_SCHEMA["properties"]
    types = "; ".join(f"{name}={properties[name]['type']}" for name in required)
    lines = [
        "Return exactly one SkillKit candidate JSON object, directly at the root.",
        "The root object must contain exactly these 8 required keys (all required):",
        *[f"- {name}" for name in required],
        f"Root field types: {types}.",
        "Array-valued sections may be empty; do not omit their keys.",
        "Do not add any other root keys or wrap the object.",
        "Return JSON only: no prose, Markdown, code fences, explanations, or reasoning.",
    ]
    return "\n".join(lines)


def _nested_shape_stepdown_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"],
        tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]),
        projection["combat_role_profile"],
    )
    return AgentPrompt(
        _nested_shape_stepdown_contract() + "\n\n" + FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION,
        view,
        view,
        (ConversationMessage("user", _canonical_json(projection)),),
        (),
        "cs-s2-nested-shape-stepdown",
        1,
        response_format=RESPONSE_CONTRACT,
        authoring_payload=projection,
        invocation_purpose=NESTED_SHAPE_STEPOWDOWN_EXPERIMENT_TYPE,
    )


def _nested_shape_stepdown_run_id(source_commit: str, manifest_digest: str) -> str:
    return (
        "cs-s2-nested-shape-stepdown-v0.1.0-L2_ROOT_PLUS_MINIMAL_SHAPE-"
        "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-"
        f"{source_commit}-{manifest_digest[:12]}-run-01"
    )


def _nested_shape_stepdown_provider() -> dict[str, object]:
    return {
        "name": NESTED_SHAPE_STEPOWDOWN_PROVIDER,
        "model_requested": NESTED_SHAPE_STEPOWDOWN_MODEL,
        "model_reported": NESTED_SHAPE_STEPOWDOWN_MODEL,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "timeout_seconds": NESTED_SHAPE_STEPOWDOWN_TIMEOUT_SECONDS,
        "max_transport_retries": NESTED_SHAPE_STEPOWDOWN_MAX_TRANSPORT_RETRIES,
    }


def _nested_shape_stepdown_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def validate_nested_shape_stepdown_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "level",
        "contract_variant_version", "source_commit", "manifest_digest", "input_manifest_digest",
        "inputs", "provider", "case_id", "timeout_seconds", "max_transport_retries",
        "target_sample_count", "complete", "input_contract_version", "tiny_output_contract_version",
        "l0_request_metrics", "l1_request_metrics", "l2_request_metrics", "sample_index",
        "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "NESTED_SHAPE_STEPDOWN_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != NESTED_SHAPE_STEPOWDOWN_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != NESTED_SHAPE_STEPOWDOWN_EXPERIMENT_TYPE
        or bundle["level"] != NESTED_SHAPE_STEPOWDOWN_LEVEL
        or bundle["contract_variant_version"] != NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION
        or bundle["case_id"] != "case_13"
        or bundle["timeout_seconds"] != 60
        or bundle["max_transport_retries"] != 0
        or bundle["target_sample_count"] != 1
        or bundle["complete"] is not True
        or bundle["input_contract_version"] != NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION
        or bundle["tiny_output_contract_version"] != FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION
        or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_CONFIG_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _NESTED_SHAPE_STEPOWDOWN_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_RUN_ID_INVALID")
    if bundle["provider"] != _nested_shape_stepdown_provider():
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_PROVIDER_INVALID")
    for key in ("l0_request_metrics", "l1_request_metrics", "l2_request_metrics"):
        if not isinstance(bundle[key], Mapping):
            raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_METRICS_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_OBSERVATION_INVALID")
    _exact_keys(
        observation,
        {
            "observation_id", "provider_outcome", "transport_attempts", "latency_ms",
            "json_extraction_outcome", "tiny_contract_outcome", "parsed_top_level_type",
            "expected_key_count", "actual_key_count", "failure_stage", "failure_code", "sanitization",
        },
        "NESTED_SHAPE_STEPDOWN_OBSERVATION_KEYS_INVALID",
    )
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01":
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_OBSERVATION_ID_INVALID")
    if observation["transport_attempts"] != 1:
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_ATTEMPT_INVALID")
    if observation["tiny_contract_outcome"] not in {
        "L2_SHAPE_STEPDOWN_PASS",
        "L2_SHAPE_STEPDOWN_TRANSPORT_REACHABLE_CONTRACT_REJECTED",
        "L2_SHAPE_STEPDOWN_UNAVAILABLE",
    }:
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_OUTCOME_INVALID")
    if observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_SANITIZATION_INVALID")
    if bundle["bundle_digest"] != _nested_shape_stepdown_bundle_digest(bundle):
        raise EvidenceContractError("NESTED_SHAPE_STEPDOWN_BUNDLE_DIGEST_INVALID")


class NestedShapeStepdownRunner:
    """Run the single, diagnostic-only L2 root-plus-minimal-shape probe."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / NESTED_SHAPE_STEPOWDOWN_RESULT_RELATIVE_PATH).resolve()

    def _assert_historical_integrity(self) -> None:
        EnumExpansionStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        path = self.root / ENUM_STEPOWDOWN_RESULT_RELATIVE_PATH
        try:
            raw = path.read_bytes()
            bundle, _ = _load_json(path)
            validate_enum_stepdown_bundle(bundle)
        except (OSError, EvidenceRunnerError) as error:
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_HISTORY_INVALID") from error
        if _digest_bytes(raw) != "2ada4b1edade77a050de346701defcba60bf9155564589a07442a0eda16a6a3f":
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_HISTORY_MUTATED")

    def _metrics(self) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        case = self.cases["case_13"]
        l0 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_full_input_prompt(case)))
        l1 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_enum_stepdown_prompt(case)))
        l2 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_nested_shape_stepdown_prompt(case)))
        if (l0["chars"], l0["bytes"]) != (5617, 5741):
            raise EvidenceRunnerError("BLOCKED_L0_DIAGNOSTIC_DRIFT")
        if (l1["chars"], l1["bytes"]) != (2131, 2255):
            raise EvidenceRunnerError("BLOCKED_L1_DIAGNOSTIC_DRIFT")
        if (l2["chars"], l2["bytes"]) != (NESTED_SHAPE_STEPOWDOWN_L2_CHARS, NESTED_SHAPE_STEPOWDOWN_L2_BYTES):
            raise EvidenceRunnerError("BLOCKED_L2_CONSTRUCTION_DRIFT")
        if not l2["chars"] < l1["chars"] or l2["chars"] > l1["chars"] * 0.75:
            raise EvidenceRunnerError("BLOCKED_L2_REDUCTION_INSUFFICIENT")
        if l2["chars"] < 1102 * 1.10:
            raise EvidenceRunnerError("BLOCKED_L2_L3_BOUNDARY_COLLAPSED")
        system = _nested_shape_stepdown_prompt(case).system_contract
        required_markers = (
            "directly at the root", "exactly these 8 required keys", "Root field types:",
            "Array-valued sections may be empty", "Do not add any other root keys",
            "Return JSON only:",
        )
        if any(marker not in system for marker in required_markers):
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_STRUCTURE_INVALID")
        if "Closed enum vocabulary:" in system or "Nested shape summary" in system:
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_STRUCTURE_INVALID")
        return l0, l1, l2

    def _load_existing(self, destination: Path, run_id: str) -> dict[str, Any] | None:
        if not destination.exists():
            return None
        bundle, _ = _load_json(destination)
        validate_nested_shape_stepdown_bundle(bundle)
        _validate_historical_bundle_identity(
            bundle,
            current_manifest_digest=self.manifest.raw_digest,
            identity_builder=lambda source, manifest: _nested_shape_stepdown_run_id(source, manifest),
            mismatch_code="NESTED_SHAPE_STEPDOWN_IDENTITY_MISMATCH",
        )
        return bundle

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_VARIABLE_MISMATCH")
        self._assert_historical_integrity()
        l0, l1, l2 = self._metrics()
        source_commit = _source_commit(self.root)
        destination = self._destination(output_path)
        run_id = _nested_shape_stepdown_run_id(source_commit, self.manifest.raw_digest)
        existing = self._load_existing(destination, run_id)
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing is not None else "dry_run_nested_shape_stepdown",
            "experiment_type": NESTED_SHAPE_STEPOWDOWN_EXPERIMENT_TYPE,
            "level": NESTED_SHAPE_STEPOWDOWN_LEVEL,
            "contract_variant_version": NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION,
            "run_id": run_id,
            "source_commit": source_commit,
            "provider": NESTED_SHAPE_STEPOWDOWN_PROVIDER,
            "model": NESTED_SHAPE_STEPOWDOWN_MODEL,
            "case_id": "case_13",
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "l0_chars": l0["chars"], "l0_bytes": l0["bytes"],
            "l1_chars": l1["chars"], "l1_bytes": l1["bytes"],
            "l2_chars": l2["chars"], "l2_bytes": l2["bytes"],
            "l2_l1_char_ratio": l2["chars"] / l1["chars"],
            "l2_l1_byte_ratio": l2["bytes"] / l1["bytes"],
            "l2_l0_char_ratio": l2["chars"] / l0["chars"],
            "l2_l0_byte_ratio": l2["bytes"] / l0["bytes"],
            "enum_expansion_included": False,
            "detailed_nested_shape_included": False,
            "root_type_summary_included": True,
            "tiny_output": True,
            "l0_request_metrics": l0, "l1_request_metrics": l1, "l2_request_metrics": l2,
            "existing_sample_count": 1 if existing is not None else 0,
            "existing_sample_indexes": [1] if existing is not None else [],
            "next_sample_index": None if existing is not None else 1,
            "remaining_sample_count": 0 if existing is not None else 1,
            "provider_factory_constructed": False,
            "provider_called": False,
            "output_path": destination.as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_SOURCE_COMMIT_MISMATCH")
        self._assert_historical_integrity()
        l0, l1, l2 = self._metrics()
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {NESTED_SHAPE_STEPOWDOWN_RESULT_RELATIVE_PATH, NESTED_SHAPE_STEPOWDOWN_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = self._destination(output_path)
        run_id = _nested_shape_stepdown_run_id(source_commit, self.manifest.raw_digest)
        if self._load_existing(destination, run_id) is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if destination.exists() and not resume:
            raise EvidenceRunnerError("NESTED_SHAPE_STEPDOWN_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live",
                "NPC_LLM_PROVIDER": NESTED_SHAPE_STEPOWDOWN_PROVIDER,
                "NPC_LLM_MODEL": NESTED_SHAPE_STEPOWDOWN_MODEL,
                "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            settings = __import__("agents.model_factory", fromlist=["LiveLLMSettings"]).LiveLLMSettings.from_environment(environment)
            client = OpenAIChatClient(api_key=settings.api_key, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds, request_options=settings.profile.provider_options)
            provider_model = _FullInputTinyOutputAdapter(client, provider=settings.provider, model=settings.model, profile=settings.profile, timeout_seconds=settings.timeout_seconds, max_retries=settings.max_retries)
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_result = {"json_extraction_outcome": "not_attempted", "tiny_contract_outcome": "TRANSPORT_UNAVAILABLE", "parsed_top_level_type": None, "actual_key_count": None}
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(_nested_shape_stepdown_prompt(self.cases["case_13"]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = _minimal_contract_result(turn.text)
            contract_outcome = (
                "L2_SHAPE_STEPDOWN_PASS"
                if json_result["tiny_contract_outcome"] == "TRANSPORT_SUCCESS_CONTRACT_PASS"
                else "L2_SHAPE_STEPDOWN_TRANSPORT_REACHABLE_CONTRACT_REJECTED"
            )
            failure_stage = None
            failure_code = None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            contract_outcome = "L2_SHAPE_STEPDOWN_UNAVAILABLE"
        observation = {
            "observation_id": f"{run_id}:case_13:sample-01",
            "provider_outcome": provider_outcome,
            "transport_attempts": attempts,
            "latency_ms": latency_ms,
            "json_extraction_outcome": json_result["json_extraction_outcome"],
            "tiny_contract_outcome": contract_outcome,
            "parsed_top_level_type": json_result["parsed_top_level_type"],
            "expected_key_count": 1,
            "actual_key_count": json_result["actual_key_count"],
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": NESTED_SHAPE_STEPOWDOWN_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "experiment_type": NESTED_SHAPE_STEPOWDOWN_EXPERIMENT_TYPE,
            "level": NESTED_SHAPE_STEPOWDOWN_LEVEL,
            "contract_variant_version": NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION,
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _nested_shape_stepdown_provider(),
            "case_id": "case_13",
            "timeout_seconds": 60,
            "max_transport_retries": 0,
            "target_sample_count": 1,
            "complete": True,
            "input_contract_version": NESTED_SHAPE_STEPOWDOWN_CONTRACT_VERSION,
            "tiny_output_contract_version": FULL_INPUT_TINY_OUTPUT_TINY_CONTRACT_VERSION,
            "l0_request_metrics": l0,
            "l1_request_metrics": l1,
            "l2_request_metrics": l2,
            "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _nested_shape_stepdown_bundle_digest(bundle)
        validate_nested_shape_stepdown_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


_COMPACT_V2_DEFINITION_ALIASES = (
    ("typed_ref", "Ref"),
    ("subject_object", "Subject"),
    ("ability", "Entry"),
    ("protocol", "Protocol"),
    ("trigger_object", "Trigger"),
    ("effect", "Effect"),
    ("feedback", "Feedback"),
    ("resource", "Resource"),
    ("state", "State"),
    ("summon", "Summon"),
    ("role_evidence", "RoleEvidence"),
)


def _compact_v2_ref_alias(ref: object) -> str | None:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return None
    definition = ref.rsplit("/", 1)[-1]
    for canonical_name, alias in _COMPACT_V2_DEFINITION_ALIASES:
        if definition == canonical_name:
            return alias
    return definition


def _compact_v2_field_token(field: str, field_schema: Mapping[str, object]) -> str:
    field_type = field_schema.get("type")
    if field_type == "array":
        item = field_schema.get("items")
        alias = _compact_v2_ref_alias(item.get("$ref")) if isinstance(item, Mapping) else None
        return f"{field}:{alias}[]" if alias is not None else f"{field}[]"
    alias = _compact_v2_ref_alias(field_schema.get("$ref"))
    return f"{field}:{alias}" if alias is not None else field


def _compact_v2_contract() -> str:
    """Render compact grammar from canonical schema definitions."""

    from agents.response_contracts import CHARACTER_SKILL_KIT_JSON_SCHEMA

    schema = CHARACTER_SKILL_KIT_JSON_SCHEMA
    properties = schema["properties"]
    required = tuple(schema["required"])
    root_types = ",".join(f"{name}:{properties[name]['type']}" for name in required)
    lines = [
        "Root JSON object (direct; no wrapper/extras; JSON only): required " + root_types + "; arrays may be empty.",
    ]
    definitions = schema["$defs"]
    for definition_name, alias in _COMPACT_V2_DEFINITION_ALIASES:
        definition = definitions.get(definition_name)
        if not isinstance(definition, Mapping):
            raise EvidenceRunnerError("COMPACT_V2_CANONICAL_DEFINITION_MISSING")
        if definition_name == "typed_ref":
            tokens = ("kind", "id")
        else:
            canonical_required = tuple(definition.get("required", ()))
            field_properties = definition.get("properties", {})
            if not isinstance(field_properties, Mapping):
                raise EvidenceRunnerError("COMPACT_V2_CANONICAL_FIELDS_INVALID")
            # Field names remain canonical-derived; compact type annotations are
            # intentionally omitted here because the root and Ref/edge rules
            # already carry the generation-critical type information.
            tokens = canonical_required
        lines.append(f"{alias}{{{','.join(tokens)}}}")
    lines.append("Edges: Trigger→Effect→Feedback; *_ref(s) are Ref(kind,id).")
    lines.append("RoleEvidence.effect_refs link effects; centrality marks combat-role support.")
    lines.append("Canonical enum values only; validator enforces legality.")
    return " ".join(lines)


def build_compact_skillkit_contract_v2() -> str:
    """Public deterministic renderer for the experimental V2-A contract."""

    return _compact_v2_contract()


MINIMAL_SKILLKIT_OUTPUT_INSTRUCTION = (
    "For this compliance probe, return one canonical CharacterSkillKit JSON object with the smallest legal content: "
    "exactly 1 entry, exactly 3 protocols (trigger, feedback, support), exactly 3 effects, exactly 1 feedback relation, "
    "and exactly 1 core role_evidence; resources, states, and summons must be empty arrays. Keep display_summary short. "
    "Include every required field, use canonical enum values, make every typed reference resolve, add no root keys, and return JSON only."
)


def _minimal_skillkit_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + MINIMAL_SKILLKIT_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-minimal-skillkit", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=MINIMAL_SKILLKIT_EXPERIMENT_TYPE,
    )


def _minimal_skillkit_output_contract_digest() -> str:
    return _digest_bytes(MINIMAL_SKILLKIT_OUTPUT_INSTRUCTION.encode("utf-8"))


def _minimal_skillkit_run_id(source_commit: str, manifest_digest: str, output_digest: str) -> str:
    return (
        "cs-s2-shadow-compact-contract-v2-minimal-skillkit-v0.1.0-opencode_go-deepseek-v4-pro-"
        f"case_13-t60-r0-n1-{source_commit}-{manifest_digest[:12]}-{output_digest[:12]}-run-01"
    )


def _minimal_skillkit_provider() -> dict[str, object]:
    return {
        "name": MINIMAL_SKILLKIT_PROVIDER,
        "model_requested": MINIMAL_SKILLKIT_MODEL,
        "model_reported": MINIMAL_SKILLKIT_MODEL,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": MINIMAL_SKILLKIT_TIMEOUT_SECONDS,
        "max_transport_retries": MINIMAL_SKILLKIT_MAX_TRANSPORT_RETRIES,
    }


def _minimal_skillkit_failure_categories(error: BaseException) -> tuple[str, ...]:
    code = getattr(error, "code", "")
    return {
        "MISSING_FIELD": ("MISSING_REQUIRED_FIELD",),
        "UNKNOWN_FIELD": ("UNKNOWN_FIELD",),
        "TYPE_MISMATCH": ("WRONG_TYPE",),
        "UNSUPPORTED_VALUE": ("INVALID_ENUM",),
        "INVALID_ID": ("NESTED_SHAPE_FAILURE",),
    }.get(code, ("OTHER_CANONICAL_REJECTION",))


def _minimal_skillkit_observation_keys() -> set[str]:
    return {
        "observation_id", "provider_outcome", "transport_attempts", "latency_ms",
        "json_extraction_outcome", "parsed_top_level_type", "parser_invoked", "parser_outcome",
        "parser_failure_categories", "parser_failure_counts", "reference_validation_invoked",
        "reference_validation_result", "evaluator_invoked", "evaluator_outcome", "evaluator_finding_codes",
        "principal_verdict", "repair_calls", "failure_stage", "failure_code", "sanitization",
    }


def _minimal_skillkit_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def _minimal_skillkit_shape_ok(candidate: Any) -> bool:
    entries = getattr(candidate, "entries", ())
    if len(entries) != 1:
        return False
    entry = entries[0]
    protocols = getattr(entry, "protocols", ())
    if len(protocols) != 3 or {getattr(item, "protocol_id", None) for item in protocols} != {"trigger", "feedback", "support"}:
        return False
    if sum(len(getattr(item, "causes", ())) for item in protocols) != 3:
        return False
    if len(getattr(candidate, "feedback_relations", ())) != 1 or len(getattr(candidate, "role_evidence", ())) != 1:
        return False
    return not any(getattr(candidate, name, ()) for name in ("resources", "states", "summons"))


def validate_minimal_skillkit_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "contract_version",
        "contract_digest", "minimal_output_contract_version", "minimal_output_contract_digest",
        "parser_contract_version", "evaluator_context_version", "source_commit", "manifest_digest",
        "input_manifest_digest", "inputs", "provider", "case_id", "timeout_seconds",
        "max_transport_retries", "target_sample_count", "complete", "request_metrics",
        "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "MINIMAL_SKILLKIT_BUNDLE_KEYS_INVALID")
    if bundle["schema_version"] != MINIMAL_SKILLKIT_SCHEMA_VERSION or bundle["protocol_version"] != PROTOCOL_VERSION or bundle["experiment_type"] != MINIMAL_SKILLKIT_EXPERIMENT_TYPE or bundle["contract_version"] != COMPACT_V2_CONTRACT_VERSION or bundle["minimal_output_contract_version"] != MINIMAL_SKILLKIT_OUTPUT_CONTRACT_VERSION or bundle["parser_contract_version"] != MINIMAL_SKILLKIT_PARSER_CONTRACT_VERSION or bundle["case_id"] != MINIMAL_SKILLKIT_CASE_ID or bundle["timeout_seconds"] != 60 or bundle["max_transport_retries"] != 0 or bundle["target_sample_count"] != 1 or bundle["complete"] is not True or bundle["sample_index"] != 1:
        raise EvidenceContractError("MINIMAL_SKILLKIT_CONFIG_INVALID")
    if not _is_sha(bundle["contract_digest"]) or not _is_sha(bundle["minimal_output_contract_digest"]) or not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("MINIMAL_SKILLKIT_IDENTITY_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("MINIMAL_SKILLKIT_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _MINIMAL_SKILLKIT_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("MINIMAL_SKILLKIT_RUN_ID_INVALID")
    if bundle["provider"] != _minimal_skillkit_provider():
        raise EvidenceContractError("MINIMAL_SKILLKIT_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("MINIMAL_SKILLKIT_OBSERVATION_INVALID")
    _exact_keys(observation, _minimal_skillkit_observation_keys(), "MINIMAL_SKILLKIT_OBSERVATION_KEYS_INVALID")
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01" or observation["repair_calls"] != 0 or observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("MINIMAL_SKILLKIT_OBSERVATION_INVALID")
    if observation["principal_verdict"] not in {
        "V2_A_MINIMAL_SKILLKIT_STRUCTURAL_PASS",
        "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED",
        "V2_A_MINIMAL_SKILLKIT_MALFORMED",
        "V2_A_MINIMAL_SKILLKIT_UNAVAILABLE",
    }:
        raise EvidenceContractError("MINIMAL_SKILLKIT_VERDICT_INVALID")
    if bundle["bundle_digest"] != _minimal_skillkit_bundle_digest(bundle):
        raise EvidenceContractError("MINIMAL_SKILLKIT_BUNDLE_DIGEST_INVALID")


O1_ROOT_ONLY_OUTPUT_INSTRUCTION = (
    "Root-only structural diagnostic: emit a canonical CharacterSkillKit root; use canonical schema_version, "
    "keep all collections empty, use the shortest legal display_summary, and emit no nested content. JSON only."
)
O1_ROOT_ONLY_GUIDED_OUTPUT_INSTRUCTION = (
    "Root-only structural diagnostic: emit a canonical CharacterSkillKit root; set schema_version exactly to "
    "skill-kit-candidate/0.1.1; keep all collections empty, use the shortest legal display_summary, and emit no "
    "nested content. JSON only."
)
O2_LOCAL_STRUCTURE_OUTPUT_INSTRUCTION = (
    "Local-structure diagnostic: emit exactly one canonical CharacterSkillKit root with schema_version exactly "
    "skill-kit-candidate/0.1.1. Include exactly one entry containing exactly one protocol with exactly one effect; "
    "use protocol_id=trigger and effect_id=emit, set operation=direct_output, and use null for optional subjects, "
    "object_ref, and trigger. Keep feedback_relations, resources, states, summons, and role_evidence empty. Keep "
    "display_summary short, add no extra fields, and return JSON only. Do not create typed references."
)
O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_INSTRUCTION = (
    "JSON only: schema_version=skill-kit-candidate/0.1.1; use the exact 8 root keys; entries has one ability with "
    "one trigger protocol causing one direct_output effect; all other arrays are empty; optional refs are null; no "
    "typed refs or extra fields; display_summary is an empty string."
)
O2_ENTRY_ONLY_OUTPUT_INSTRUCTION = (
    "JSON only: schema_version=skill-kit-candidate/0.1.1; use the exact 8 root keys; entries has one ability with "
    "protocols=[]; all other arrays are empty; display_summary is an empty string; no extra fields."
)


def build_o1_root_only_fixture() -> dict[str, object]:
    """Return the deterministic legal root-only fixture used by offline tests."""

    return {
        "schema_version": "skill-kit-candidate/0.1.1",
        "entries": [],
        "feedback_relations": [],
        "resources": [],
        "states": [],
        "summons": [],
        "role_evidence": [],
        "display_summary": "",
    }


def _o1_root_only_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + O1_ROOT_ONLY_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-output-stepdown-o1-root-only", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=O1_ROOT_ONLY_EXPERIMENT_TYPE,
    )


def _o1_root_only_guided_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + O1_ROOT_ONLY_GUIDED_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-output-stepdown-o1-root-only-schema-guided", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE,
    )


def _o2_local_structure_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + O2_LOCAL_STRUCTURE_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-output-stepdown-o2-local-structure", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE,
    )


def _o2_local_structure_compact_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-output-stepdown-o2-local-structure-compact", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE,
    )


def _o2_entry_only_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + O2_ENTRY_ONLY_OUTPUT_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-output-stepdown-o1-5-entry-only", 1,
        response_format=RESPONSE_CONTRACT, authoring_payload=projection,
        invocation_purpose=O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE,
    )
def _o1_root_only_output_contract_digest() -> str:
    return _digest_bytes(O1_ROOT_ONLY_OUTPUT_INSTRUCTION.encode("utf-8"))


def _o1_root_only_guided_output_contract_digest() -> str:
    return _digest_bytes(O1_ROOT_ONLY_GUIDED_OUTPUT_INSTRUCTION.encode("utf-8"))


def _o2_local_structure_output_contract_digest() -> str:
    return _digest_bytes(O2_LOCAL_STRUCTURE_OUTPUT_INSTRUCTION.encode("utf-8"))


def _o2_local_structure_compact_output_contract_digest() -> str:
    return _digest_bytes(O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_INSTRUCTION.encode("utf-8"))


def _o2_entry_only_output_contract_digest() -> str:
    return _digest_bytes(O2_ENTRY_ONLY_OUTPUT_INSTRUCTION.encode("utf-8"))


def _o2_local_structure_run_id(source_commit: str, manifest_digest: str, output_digest: str) -> str:
    return (
        "cs-s2-shadow-compact-contract-v2-output-stepdown-o2-local-structure-v0.1.0-"
        "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-"
        f"{source_commit}-{manifest_digest[:12]}-{output_digest[:12]}-run-01"
    )


def build_o2_local_structure_fixture() -> dict[str, object]:
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "entries": [{
            "ability_id": "pulse", "name": "Pulse", "mode": "active",
            "protocols": [{
                "protocol_id": "trigger", "when": None, "causes": [{
                    "effect_id": "emit", "subject": None, "operation": "direct_output",
                    "object_ref": None, "description": "",
                }],
            }], "display_text": "",
        }],
        "feedback_relations": [], "resources": [], "states": [], "summons": [],
        "role_evidence": [], "display_summary": "",
    }


def _o1_root_only_run_id(source_commit: str, manifest_digest: str, output_digest: str) -> str:
    return (
        "cs-s2-shadow-compact-contract-v2-output-stepdown-o1-root-only-v0.2.0-"
        "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-"
        f"{source_commit}-{manifest_digest[:12]}-{output_digest[:12]}-run-01"
    )


def _o1_root_only_provider() -> dict[str, object]:
    return {
        "name": O1_ROOT_ONLY_PROVIDER,
        "model_requested": O1_ROOT_ONLY_MODEL,
        "model_reported": O1_ROOT_ONLY_MODEL,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "response_contract": RESPONSE_CONTRACT,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "timeout_seconds": O1_ROOT_ONLY_TIMEOUT_SECONDS,
        "max_transport_retries": O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES,
    }


def _o1_root_only_failure_categories(error: BaseException) -> tuple[str, ...]:
    code = getattr(error, "code", "")
    return {
        "MISSING_FIELD": ("MISSING_REQUIRED_FIELD",),
        "UNKNOWN_FIELD": ("UNKNOWN_FIELD",),
        "TYPE_MISMATCH": ("WRONG_TYPE",),
        "UNSUPPORTED_SCHEMA_VERSION": ("INVALID_CANONICAL_VALUE",),
        "UNSUPPORTED_VALUE": ("INVALID_CANONICAL_VALUE",),
    }.get(code, ("OTHER_CANONICAL_REJECTION",))


def _o1_root_only_observation_keys() -> set[str]:
    return {
        "observation_id", "provider_outcome", "transport_attempts", "latency_ms",
        "json_extraction_outcome", "parsed_top_level_type", "parser_invoked",
        "parser_outcome", "parser_failure_categories", "parser_failure_counts",
        "evaluator_invoked", "evaluator_outcome", "principal_verdict", "repair_calls",
        "failure_stage", "failure_code", "sanitization",
    }


def _o1_root_only_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


O1_SAFE_DIAGNOSTIC_CATEGORIES = frozenset({
    "NO_DIAGNOSTIC", "ROOT_SCHEMA_VERSION_MISMATCH",
    "O1_CONTRACT_NESTED_CONTENT_VIOLATION", "NESTED_INVALID_CANONICAL_VALUE",
    "MULTIPLE_OR_AMBIGUOUS_VIOLATIONS", "ROOT_INVALID_CANONICAL_VALUE_OTHER",
    "INVALID_CANONICAL_VALUE_UNRESOLVED", "SHAPE_FAILURE",
})
O1_SAFE_DIAGNOSTIC_RESOLUTIONS = frozenset({
    "NOT_APPLICABLE", "FIELD_RESOLVED", "PARTIALLY_RESOLVED", "CLASS_ONLY",
})
O1_SAFE_DIAGNOSTIC_FAILURE_CLASSES = frozenset({
    "NONE", "INVALID_CANONICAL_VALUE", "MISSING_REQUIRED_FIELD", "UNKNOWN_FIELD",
    "WRONG_TYPE", "ROOT_SHAPE_FAILURE", "MALFORMED", "UNAVAILABLE",
})
_O1_COLLECTION_FIELDS = (
    "entries", "feedback_relations", "resources", "states", "summons", "role_evidence",
)


@dataclass(frozen=True)
class O1SafeDiagnosticSnapshot:
    """Bounded, immutable metadata about an O1 candidate; never stores values."""

    root_schema_version_present: bool
    root_schema_version_is_string: bool
    root_schema_version_exact_match: bool
    collection_shape_valid: bool
    nonempty_collection_count: int
    unexpected_nested_content: bool
    display_summary_present: bool
    display_summary_is_string: bool

    def __post_init__(self) -> None:
        for name in (
            "root_schema_version_present", "root_schema_version_is_string",
            "root_schema_version_exact_match", "collection_shape_valid",
            "unexpected_nested_content", "display_summary_present",
            "display_summary_is_string",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if isinstance(self.nonempty_collection_count, bool) or not isinstance(self.nonempty_collection_count, int) or not 0 <= self.nonempty_collection_count <= 6:
            raise ValueError("nonempty_collection_count must be between 0 and 6")

    def to_dict(self) -> dict[str, object]:
        return {
            "root_schema_version_present": self.root_schema_version_present,
            "root_schema_version_is_string": self.root_schema_version_is_string,
            "root_schema_version_exact_match": self.root_schema_version_exact_match,
            "collection_shape_valid": self.collection_shape_valid,
            "nonempty_collection_count": self.nonempty_collection_count,
            "unexpected_nested_content": self.unexpected_nested_content,
            "display_summary_present": self.display_summary_present,
            "display_summary_is_string": self.display_summary_is_string,
        }


def build_o1_safe_diagnostic_snapshot(payload: object) -> O1SafeDiagnosticSnapshot:
    """Read candidate shape without mutation, coercion, or value retention."""

    if not isinstance(payload, Mapping):
        return O1SafeDiagnosticSnapshot(False, False, False, False, 0, False, False, False)
    schema_present = "schema_version" in payload
    schema_is_string = schema_present and isinstance(payload.get("schema_version"), str)
    schema_exact = schema_is_string and payload.get("schema_version") == CANDIDATE_SCHEMA_VERSION
    shape_valid = all(field in payload and isinstance(payload.get(field), list) for field in _O1_COLLECTION_FIELDS)
    nonempty = sum(1 for field in _O1_COLLECTION_FIELDS if isinstance(payload.get(field), list) and len(payload[field]) > 0)
    display_present = "display_summary" in payload
    return O1SafeDiagnosticSnapshot(
        schema_present, schema_is_string, schema_exact, shape_valid, nonempty,
        nonempty > 0, display_present, display_present and isinstance(payload.get("display_summary"), str),
    )


def _o1_safe_parser_failure_class(error: BaseException | None) -> str:
    if error is None:
        return "NONE"
    code = getattr(error, "code", "")
    if code in {"UNSUPPORTED_SCHEMA_VERSION", "UNSUPPORTED_VALUE"}:
        return "INVALID_CANONICAL_VALUE"
    if code == "MISSING_FIELD":
        return "MISSING_REQUIRED_FIELD"
    if code == "UNKNOWN_FIELD":
        return "UNKNOWN_FIELD"
    if code == "TYPE_MISMATCH":
        return "WRONG_TYPE"
    return "ROOT_SHAPE_FAILURE"


def _o1_safe_nested_path(error: BaseException | None) -> bool:
    path = getattr(error, "field_path", None)
    if not isinstance(path, str):
        return False
    return any(path.startswith(f"/{field}/") for field in _O1_COLLECTION_FIELDS)


def classify_o1_safe_diagnostic(
    snapshot: O1SafeDiagnosticSnapshot,
    parser_failure_class: str,
    *,
    parser_error: BaseException | None = None,
) -> tuple[str, str]:
    """Return (predefined category, resolution) without exposing raw values."""

    if parser_failure_class == "NONE":
        return "NO_DIAGNOSTIC", "NOT_APPLICABLE"
    if parser_failure_class != "INVALID_CANONICAL_VALUE":
        return "SHAPE_FAILURE", "CLASS_ONLY"
    if not snapshot.root_schema_version_exact_match and snapshot.unexpected_nested_content:
        return "MULTIPLE_OR_AMBIGUOUS_VIOLATIONS", "PARTIALLY_RESOLVED"
    if not snapshot.root_schema_version_exact_match and not snapshot.unexpected_nested_content:
        return "ROOT_SCHEMA_VERSION_MISMATCH", "FIELD_RESOLVED"
    if snapshot.unexpected_nested_content:
        if _o1_safe_nested_path(parser_error):
            return "NESTED_INVALID_CANONICAL_VALUE", "FIELD_RESOLVED"
        return "O1_CONTRACT_NESTED_CONTENT_VIOLATION", "PARTIALLY_RESOLVED"
    return "ROOT_INVALID_CANONICAL_VALUE_OTHER", "PARTIALLY_RESOLVED"


def validate_o1_root_only_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "level",
        "contract_version", "contract_digest", "output_contract_version", "output_contract_digest",
        "parser_contract_version", "source_commit", "manifest_digest", "input_manifest_digest",
        "inputs", "provider", "model", "case_id", "timeout_seconds", "max_transport_retries",
        "response_mode", "feature_flag", "record_only", "target_sample_count", "complete",
        "request_metrics", "output_fixture_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "O1_ROOT_ONLY_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != O1_ROOT_ONLY_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != O1_ROOT_ONLY_EXPERIMENT_TYPE
        or bundle["level"] != O1_ROOT_ONLY_LEVEL
        or bundle["contract_version"] != COMPACT_V2_CONTRACT_VERSION
        or bundle["case_id"] != O1_ROOT_ONLY_CASE_ID
        or bundle["timeout_seconds"] != O1_ROOT_ONLY_TIMEOUT_SECONDS
        or bundle["max_transport_retries"] != O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES
        or bundle["response_mode"] != O1_ROOT_ONLY_RESPONSE_MODE
        or bundle["feature_flag"] != "OFF"
        or bundle["record_only"] is not True
        or bundle["target_sample_count"] != O1_ROOT_ONLY_TARGET
        or bundle["complete"] is not True
        or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("O1_ROOT_ONLY_CONFIG_INVALID")
    for key in ("contract_digest", "output_contract_digest", "manifest_digest"):
        if not _is_sha(bundle[key]):
            raise EvidenceContractError("O1_ROOT_ONLY_IDENTITY_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"]:
        raise EvidenceContractError("O1_ROOT_ONLY_MANIFEST_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("O1_ROOT_ONLY_SOURCE_COMMIT_INVALID")
    if not isinstance(bundle["run_id"], str) or not _O1_ROOT_ONLY_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("O1_ROOT_ONLY_RUN_ID_INVALID")
    if bundle["provider"] != _o1_root_only_provider() or bundle["model"] != O1_ROOT_ONLY_MODEL:
        raise EvidenceContractError("O1_ROOT_ONLY_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("O1_ROOT_ONLY_OBSERVATION_INVALID")
    _exact_keys(observation, _o1_root_only_observation_keys(), "O1_ROOT_ONLY_OBSERVATION_KEYS_INVALID")
    if (
        observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01"
        or observation["repair_calls"] != 0
        or observation["evaluator_invoked"] is not False
        or observation["evaluator_outcome"] != "NOT_RUN"
        or observation["sanitization"] != _sanitization_mapping()
    ):
        raise EvidenceContractError("O1_ROOT_ONLY_OBSERVATION_INVALID")
    if observation["principal_verdict"] not in {
        "O1_ROOT_ONLY_STRUCTURAL_PASS", "O1_ROOT_ONLY_PARSE_REJECTED",
        "O1_ROOT_ONLY_MALFORMED", "O1_ROOT_ONLY_UNAVAILABLE",
    }:
        raise EvidenceContractError("O1_ROOT_ONLY_VERDICT_INVALID")
    if bundle["bundle_digest"] != _o1_root_only_bundle_digest(bundle):
        raise EvidenceContractError("O1_ROOT_ONLY_BUNDLE_DIGEST_INVALID")


class OutputStepdownRunner:
    """Offline planner and future fake/live harness for the O1 root-only probe."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / O1_ROOT_ONLY_RESULT_RELATIVE_PATH).resolve()

    def _prepare(self, output_path: Path | str | None = None) -> dict[str, object]:
        case = self.cases[O1_ROOT_ONLY_CASE_ID]
        contract = _compact_v2_contract()
        digest = _digest_bytes(contract.encode("utf-8"))
        if digest != "5dd592925cb4cdc0e20cbb564deedba4c64fe74e8fd79bb2925db66cde801bce" or len(contract) != 981 or len(contract.encode("utf-8")) != 985:
            raise EvidenceRunnerError("BLOCKED_V2_CONTRACT_DRIFT")
        tiny = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_compact_v2_prompt(case)))
        minimal = _message_metrics(LiveLLMAdapter._provider_messages(_minimal_skillkit_prompt(case)))
        o1 = _message_metrics(LiveLLMAdapter._provider_messages(_o1_root_only_prompt(case)))
        if (tiny["chars"], tiny["bytes"]) != (1709, 1837) or (minimal["chars"], minimal["bytes"]) != (1724, 1852):
            raise EvidenceRunnerError("BLOCKED_V2_DIAGNOSTIC_DRIFT")
        source_commit = _source_commit(self.root)
        output_digest = _o1_root_only_output_contract_digest()
        run_id = _o1_root_only_run_id(source_commit, self.manifest.raw_digest, output_digest)
        if not _O1_ROOT_ONLY_RUN_ID_RE.fullmatch(run_id):
            raise EvidenceRunnerError("O1_ROOT_ONLY_RUN_ID_INVALID")
        destination = self._destination(output_path)
        existing = None
        if destination.exists():
            payload, _ = _load_json(destination)
            validate_o1_root_only_bundle(payload)
            if payload["run_id"] != run_id:
                raise EvidenceRunnerError("O1_ROOT_ONLY_IDENTITY_MISMATCH")
            existing = payload
        fixture = build_o1_root_only_fixture()
        fixture_metrics = {
            "chars": len(_canonical_json(fixture)),
            "bytes": len(_canonical_json(fixture).encode("utf-8")),
            "objects": 1, "fields": 8, "refs": 0, "enum_decisions": 0,
            "parser_legal": True,
        }
        try:
            parse_candidate(fixture)
        except (SkillKitShapeError, TypeError, ValueError) as error:
            raise EvidenceRunnerError("BLOCKED_O1_NOT_CANONICAL_LEGAL") from error
        return {
            "case": case, "v2_digest": digest, "output_digest": output_digest,
            "run_id": run_id, "source_commit": source_commit, "destination": destination,
            "o1": o1, "tiny": tiny, "minimal": minimal, "fixture_metrics": fixture_metrics,
            "existing": existing,
        }

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("O1_ROOT_ONLY_VARIABLE_MISMATCH")
        NestedShapeStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        prepared = self._prepare(output_path)
        existing = prepared["existing"] is not None
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing else "dry_run_o1_root_only",
            "experiment_type": O1_ROOT_ONLY_EXPERIMENT_TYPE, "level": O1_ROOT_ONLY_LEVEL,
            "schema_version": O1_ROOT_ONLY_SCHEMA_VERSION, "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": prepared["v2_digest"], "output_contract_version": O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION,
            "output_contract_digest": prepared["output_digest"], "parser_contract_version": O1_ROOT_ONLY_PARSER_CONTRACT_VERSION,
            "run_id": prepared["run_id"], "source_commit": prepared["source_commit"],
            "manifest_digest": self.manifest.raw_digest, "provider": O1_ROOT_ONLY_PROVIDER,
            "model": O1_ROOT_ONLY_MODEL, "case_id": O1_ROOT_ONLY_CASE_ID, "timeout_seconds": 60,
            "max_transport_retries": 0, "target_sample_count": 1, "response_mode": O1_ROOT_ONLY_RESPONSE_MODE,
            "feature_flag": "OFF", "record_only": True, "request_metrics": prepared["o1"],
            "v2_tiny_request_metrics": prepared["tiny"], "v2_minimal_request_metrics": prepared["minimal"],
            "output_fixture_metrics": prepared["fixture_metrics"],
            "output_instruction_chars": len(O1_ROOT_ONLY_OUTPUT_INSTRUCTION),
            "output_instruction_bytes": len(O1_ROOT_ONLY_OUTPUT_INSTRUCTION.encode("utf-8")),
            "existing_sample_count": 1 if existing else 0, "existing_sample_indexes": [1] if existing else [],
            "next_sample_index": None if existing else 1, "remaining_sample_count": 0 if existing else 1,
            "provider_factory_constructed": False, "provider_called": False, "evaluator_invoked": False,
            "repair_calls": 0, "output_path": prepared["destination"].as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True, **_: object) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("O1_ROOT_ONLY_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("O1_ROOT_ONLY_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("O1_ROOT_ONLY_SOURCE_COMMIT_REQUIRED")
        if _source_commit(self.root) != expected_source_commit:
            raise EvidenceRunnerError("O1_ROOT_ONLY_SOURCE_COMMIT_MISMATCH")
        prepared = self._prepare(output_path)
        if prepared["existing"] is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree and _dirty_paths(self.root):
            raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = prepared["destination"]
        if destination.exists() and not resume:
            raise EvidenceRunnerError("O1_ROOT_ONLY_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live", "NPC_LLM_PROVIDER": O1_ROOT_ONLY_PROVIDER,
                "NPC_LLM_MODEL": O1_ROOT_ONLY_MODEL, "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE, "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            try:
                provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_outcome = "not_attempted"
        top_level = None
        parser_invoked = False
        parser_outcome = "NOT_REACHED"
        parser_categories: tuple[str, ...] = ()
        parser_counts: dict[str, int] = {}
        principal_verdict = "O1_ROOT_ONLY_UNAVAILABLE"
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(_o1_root_only_prompt(prepared["case"]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            try:
                payload = json.loads(turn.text)
                top_level = _minimal_top_level_type(payload)
            except (TypeError, json.JSONDecodeError):
                json_outcome = "failed"
                failure_stage, failure_code = "json", "RESPONSE_JSON_INVALID"
                principal_verdict = "O1_ROOT_ONLY_MALFORMED"
            else:
                json_outcome = "parsed"
                parser_invoked = True
                try:
                    candidate = parse_candidate(payload)
                    if not hasattr(candidate, "entries"):
                        raise SkillKitShapeError("INVALID_ROOT_SHAPE", "/", "legacy candidate is not canonical root")
                except (SkillKitShapeError, TypeError, ValueError) as error:
                    parser_outcome = "PARSER_REJECTED"
                    parser_categories = _o1_root_only_failure_categories(error)
                    parser_counts = {category: 1 for category in parser_categories}
                    failure_stage, failure_code = "shape", "CANDIDATE_SHAPE_REJECTED"
                    principal_verdict = "O1_ROOT_ONLY_PARSE_REJECTED"
                else:
                    parser_outcome = "PARSER_PASS"
                    principal_verdict = "O1_ROOT_ONLY_STRUCTURAL_PASS"
                    failure_stage, failure_code = None, None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
        observation = {
            "observation_id": f"{prepared['run_id']}:case_13:sample-01", "provider_outcome": provider_outcome,
            "transport_attempts": attempts, "latency_ms": latency_ms, "json_extraction_outcome": json_outcome,
            "parsed_top_level_type": top_level, "parser_invoked": parser_invoked, "parser_outcome": parser_outcome,
            "parser_failure_categories": parser_categories, "parser_failure_counts": parser_counts,
            "evaluator_invoked": False, "evaluator_outcome": "NOT_RUN", "principal_verdict": principal_verdict,
            "repair_calls": 0, "failure_stage": failure_stage, "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": O1_ROOT_ONLY_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
            "run_id": prepared["run_id"], "experiment_type": O1_ROOT_ONLY_EXPERIMENT_TYPE,
            "level": O1_ROOT_ONLY_LEVEL, "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": prepared["v2_digest"], "output_contract_version": O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION,
            "output_contract_digest": prepared["output_digest"], "parser_contract_version": O1_ROOT_ONLY_PARSER_CONTRACT_VERSION,
            "source_commit": _source_commit(self.root), "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest, "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _o1_root_only_provider(), "model": O1_ROOT_ONLY_MODEL, "case_id": O1_ROOT_ONLY_CASE_ID,
            "timeout_seconds": 60, "max_transport_retries": 0, "response_mode": O1_ROOT_ONLY_RESPONSE_MODE,
            "feature_flag": "OFF", "record_only": True, "target_sample_count": 1, "complete": True,
            "request_metrics": prepared["o1"], "output_fixture_metrics": prepared["fixture_metrics"],
            "sample_index": 1, "observation": observation,
        }
        bundle["bundle_digest"] = _o1_root_only_bundle_digest(bundle)
        validate_o1_root_only_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _compact_v2_prompt(case: ShadowEvidenceCase) -> AgentPrompt:
    projection = _full_input_projection(case)
    view = _ShadowProjectionView(
        projection["brief"], tuple(projection["hard_constraints"]),
        tuple(projection["forbidden_elements"]), projection["combat_role_profile"],
    )
    return AgentPrompt(
        _compact_v2_contract() + "\n\n" + FULL_INPUT_TINY_OUTPUT_DIAGNOSTIC_INSTRUCTION,
        view, view, (ConversationMessage("user", _canonical_json(projection)),), (),
        "cs-s2-compact-contract-v2-a", 1, response_format=RESPONSE_CONTRACT,
        authoring_payload=projection, invocation_purpose=COMPACT_V2_EXPERIMENT_TYPE,
    )


def _compact_v2_run_id(source_commit: str, manifest_digest: str, contract_digest: str) -> str:
    return (
        "cs-s2-shadow-compact-contract-v2-a-v0.1.0-opencode_go-deepseek-v4-pro-"
        f"case_13-t60-r0-n1-{source_commit}-{manifest_digest[:12]}-{contract_digest[:12]}-run-01"
    )


def _compact_v2_provider() -> dict[str, object]:
    return {
        "name": COMPACT_V2_PROVIDER,
        "model_requested": COMPACT_V2_MODEL,
        "model_reported": COMPACT_V2_MODEL,
        "transport": TRANSPORT,
        "structured_output_mode": STRUCTURED_OUTPUT_MODE,
        "timeout_seconds": COMPACT_V2_TIMEOUT_SECONDS,
        "max_transport_retries": COMPACT_V2_MAX_TRANSPORT_RETRIES,
    }


def _compact_v2_bundle_digest(bundle: Mapping[str, object]) -> str:
    return _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"})


def _compact_v2_identity_from_bundle(bundle: Mapping[str, object]) -> str:
    manifest_digest = bundle.get("manifest_digest")
    contract_digest = bundle.get("contract_digest")
    if (
        not isinstance(manifest_digest, str)
        or not _is_sha(manifest_digest)
        or not isinstance(contract_digest, str)
        or not _is_sha(contract_digest)
    ):
        raise EvidenceContractError("COMPACT_V2_IDENTITY_INVALID")
    return _historical_identity(
        bundle,
        lambda source_commit: _compact_v2_run_id(source_commit, manifest_digest, contract_digest),
    )


def validate_compact_v2_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "contract_version",
        "contract_digest", "source_commit", "manifest_digest", "input_manifest_digest", "inputs",
        "provider", "model", "case_id", "timeout_seconds", "max_transport_retries",
        "target_sample_count", "complete", "tiny_output_contract_version", "l2_request_metrics",
        "v2_request_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "COMPACT_V2_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != COMPACT_V2_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != COMPACT_V2_EXPERIMENT_TYPE
        or bundle["contract_version"] != COMPACT_V2_CONTRACT_VERSION
        or bundle["case_id"] != COMPACT_V2_CASE_ID
        or bundle["timeout_seconds"] != COMPACT_V2_TIMEOUT_SECONDS
        or bundle["max_transport_retries"] != COMPACT_V2_MAX_TRANSPORT_RETRIES
        or bundle["target_sample_count"] != COMPACT_V2_TARGET
        or bundle["complete"] is not True
        or bundle["tiny_output_contract_version"] != COMPACT_V2_TINY_OUTPUT_CONTRACT_VERSION
        or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("COMPACT_V2_CONFIG_INVALID")
    if not _is_sha(bundle["contract_digest"]):
        raise EvidenceContractError("COMPACT_V2_CONTRACT_DIGEST_INVALID")
    if not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("COMPACT_V2_SOURCE_COMMIT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not _is_sha(bundle["manifest_digest"]):
        raise EvidenceContractError("COMPACT_V2_MANIFEST_INVALID")
    if not isinstance(bundle["run_id"], str) or not _COMPACT_V2_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("COMPACT_V2_RUN_ID_INVALID")
    if bundle["run_id"] != _compact_v2_identity_from_bundle(bundle):
        raise EvidenceContractError("COMPACT_V2_IDENTITY_MISMATCH")
    if bundle["provider"] != _compact_v2_provider() or bundle["model"] != COMPACT_V2_MODEL:
        raise EvidenceContractError("COMPACT_V2_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("COMPACT_V2_OBSERVATION_INVALID")
    _exact_keys(
        observation,
        {"observation_id", "provider_outcome", "transport_attempts", "latency_ms", "json_extraction_outcome", "tiny_contract_outcome", "parsed_top_level_type", "expected_key_count", "actual_key_count", "failure_stage", "failure_code", "sanitization"},
        "COMPACT_V2_OBSERVATION_KEYS_INVALID",
    )
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01":
        raise EvidenceContractError("COMPACT_V2_OBSERVATION_ID_INVALID")
    if observation["transport_attempts"] != 1 or observation["tiny_contract_outcome"] not in {"V2_A_TINY_OUTPUT_PASS", "V2_A_TRANSPORT_REACHABLE_CONTRACT_REJECTED", "V2_A_TINY_OUTPUT_UNAVAILABLE"}:
        raise EvidenceContractError("COMPACT_V2_OBSERVATION_INVALID")
    if observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("COMPACT_V2_SANITIZATION_INVALID")
    if bundle["bundle_digest"] != _compact_v2_bundle_digest(bundle):
        raise EvidenceContractError("COMPACT_V2_BUNDLE_DIGEST_INVALID")


class CompactContractV2Runner:
    """Offline-only V2-A contract gate and future identity planner."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _existing_complete(self, destination: Path, *, contract_digest: str) -> bool:
        if not destination.exists():
            return False
        try:
            payload, _ = _load_json(destination)
        except EvidenceRunnerError as error:
            raise EvidenceRunnerError("COMPACT_V2_EXISTING_INVALID") from error
        if (
            payload.get("complete") is not True
            or payload.get("sample_index") != 1
            or payload.get("manifest_digest") != self.manifest.raw_digest
            or payload.get("contract_digest") != contract_digest
            or payload.get("run_id") != _compact_v2_identity_from_bundle(payload)
        ):
            raise EvidenceRunnerError("COMPACT_V2_IDENTITY_MISMATCH")
        return True

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("COMPACT_V2_VARIABLE_MISMATCH")
        NestedShapeStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        case = self.cases[COMPACT_V2_CASE_ID]
        l0 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_full_input_prompt(case)))
        l1 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_enum_stepdown_prompt(case)))
        l2 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_nested_shape_stepdown_prompt(case)))
        contract = _compact_v2_contract()
        v2 = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_compact_v2_prompt(case)))
        if (l0["chars"], l0["bytes"]) != (COMPACT_V2_L0_CHARS, COMPACT_V2_L0_BYTES):
            raise EvidenceRunnerError("BLOCKED_L0_DIAGNOSTIC_DRIFT")
        if (l1["chars"], l1["bytes"]) != (COMPACT_V2_L1_CHARS, COMPACT_V2_L1_BYTES):
            raise EvidenceRunnerError("BLOCKED_L1_DIAGNOSTIC_DRIFT")
        if (l2["chars"], l2["bytes"]) != (COMPACT_V2_L2_CHARS, COMPACT_V2_L2_BYTES):
            raise EvidenceRunnerError("BLOCKED_L2_CONSTRUCTION_DRIFT")
        digest = _digest_bytes(contract.encode("utf-8"))
        source_commit = _source_commit(self.root)
        run_id = _compact_v2_run_id(source_commit, self.manifest.raw_digest, digest)
        if not _COMPACT_V2_RUN_ID_RE.fullmatch(run_id):
            raise EvidenceRunnerError("COMPACT_V2_RUN_ID_INVALID")
        destination = (Path(output_path) if output_path is not None else self.root / COMPACT_V2_RESULT_RELATIVE_PATH).resolve()
        existing = self._existing_complete(destination, contract_digest=digest)
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing else "dry_run_compact_contract_v2_a", "experiment_type": COMPACT_V2_EXPERIMENT_TYPE,
            "schema_version": COMPACT_V2_SCHEMA_VERSION, "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": digest, "run_id": run_id, "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest, "provider": COMPACT_V2_PROVIDER,
            "model": COMPACT_V2_MODEL, "case_id": COMPACT_V2_CASE_ID, "timeout_seconds": 60,
            "max_transport_retries": 0, "target_sample_count": 1,
            "tiny_output_contract_version": COMPACT_V2_TINY_OUTPUT_CONTRACT_VERSION,
            "l0_request_metrics": l0, "l1_request_metrics": l1, "l2_request_metrics": l2,
            "v2_request_metrics": v2, "v2_contract_chars": len(contract),
            "v2_contract_bytes": len(contract.encode("utf-8")),
            "v2_chars_vs_l2": v2["chars"] / l2["chars"], "v2_chars_vs_l1": v2["chars"] / l1["chars"],
            "v2_chars_vs_l0": v2["chars"] / l0["chars"],
            "semantic_coverage": {"root_contract": "FULL", "nested_structure": "COMPACT", "enum_guidance": "MINIMAL", "relationship_semantics": "COMPACT", "role_evidence": "COMPACT", "cross_refs": "COMPACT", "request_semantics": "FULL", "formatting": "FULL"},
            "full_enum_expansion_included": False, "feature_flag": "OFF", "record_only": True,
            "existing_sample_count": 1 if existing else 0, "existing_sample_indexes": [1] if existing else [], "next_sample_index": None if existing else 1,
            "remaining_sample_count": 0 if existing else 1, "provider_factory_constructed": False, "provider_called": False,
            "output_path": destination.as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True, **_: object) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("COMPACT_V2_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("COMPACT_V2_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("COMPACT_V2_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("COMPACT_V2_SOURCE_COMMIT_MISMATCH")
        planned = self.dry_run(timeout_seconds=60, max_transport_retries=0, target_sample_count=1, output_path=output_path)
        if planned["existing_sample_count"]:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree:
            dirty = tuple(path for path in _dirty_paths(self.root) if path not in {COMPACT_V2_RESULT_RELATIVE_PATH, COMPACT_V2_TEMP_RELATIVE_PATH})
            if dirty:
                raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = Path(planned["output_path"])
        if destination.exists() and not resume:
            raise EvidenceRunnerError("COMPACT_V2_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live",
                "NPC_LLM_PROVIDER": COMPACT_V2_PROVIDER,
                "NPC_LLM_MODEL": COMPACT_V2_MODEL,
                "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            settings = __import__("agents.model_factory", fromlist=["LiveLLMSettings"]).LiveLLMSettings.from_environment(environment)
            client = OpenAIChatClient(api_key=settings.api_key, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds, request_options=settings.profile.provider_options)
            provider_model = _FullInputTinyOutputAdapter(client, provider=settings.provider, model=settings.model, profile=settings.profile, timeout_seconds=settings.timeout_seconds, max_retries=settings.max_retries)
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_result = {"json_extraction_outcome": "not_attempted", "tiny_contract_outcome": "TRANSPORT_UNAVAILABLE", "parsed_top_level_type": None, "actual_key_count": None}
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(_compact_v2_prompt(self.cases[COMPACT_V2_CASE_ID]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_result = _minimal_contract_result(turn.text)
            contract_outcome = "V2_A_TINY_OUTPUT_PASS" if json_result["tiny_contract_outcome"] == "TRANSPORT_SUCCESS_CONTRACT_PASS" else "V2_A_TRANSPORT_REACHABLE_CONTRACT_REJECTED"
            failure_stage = None
            failure_code = None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            contract_outcome = "V2_A_TINY_OUTPUT_UNAVAILABLE"
        observation = {
            "observation_id": f"{planned['run_id']}:case_13:sample-01",
            "provider_outcome": provider_outcome,
            "transport_attempts": attempts,
            "latency_ms": latency_ms,
            "json_extraction_outcome": json_result["json_extraction_outcome"],
            "tiny_contract_outcome": contract_outcome,
            "parsed_top_level_type": json_result["parsed_top_level_type"],
            "expected_key_count": 1,
            "actual_key_count": json_result["actual_key_count"],
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": COMPACT_V2_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "run_id": planned["run_id"],
            "experiment_type": COMPACT_V2_EXPERIMENT_TYPE,
            "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": planned["contract_digest"],
            "source_commit": source_commit,
            "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _compact_v2_provider(),
            "model": COMPACT_V2_MODEL,
            "case_id": COMPACT_V2_CASE_ID,
            "timeout_seconds": COMPACT_V2_TIMEOUT_SECONDS,
            "max_transport_retries": COMPACT_V2_MAX_TRANSPORT_RETRIES,
            "target_sample_count": COMPACT_V2_TARGET,
            "complete": True,
            "tiny_output_contract_version": COMPACT_V2_TINY_OUTPUT_CONTRACT_VERSION,
            "l2_request_metrics": planned["l2_request_metrics"],
            "v2_request_metrics": planned["v2_request_metrics"],
            "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _compact_v2_bundle_digest(bundle)
        validate_compact_v2_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


class MinimalSkillKitRunner:
    """Prepare the independent minimal-SkillKit compliance experiment."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / MINIMAL_SKILLKIT_RESULT_RELATIVE_PATH).resolve()

    def _prepare(self, output_path: Path | str | None = None) -> dict[str, object]:
        case = self.cases[MINIMAL_SKILLKIT_CASE_ID]
        v2_contract = _compact_v2_contract()
        v2_digest = _digest_bytes(v2_contract.encode("utf-8"))
        if v2_digest != "5dd592925cb4cdc0e20cbb564deedba4c64fe74e8fd79bb2925db66cde801bce" or len(v2_contract) != 981 or len(v2_contract.encode("utf-8")) != 985:
            raise EvidenceRunnerError("BLOCKED_V2_CONTRACT_DRIFT")
        v2_tiny = _message_metrics(_FullInputTinyOutputAdapter._provider_messages(_compact_v2_prompt(case)))
        if (v2_tiny["chars"], v2_tiny["bytes"]) != (1709, 1837):
            raise EvidenceRunnerError("BLOCKED_V2_DIAGNOSTIC_DRIFT")
        minimal = _message_metrics(LiveLLMAdapter._provider_messages(_minimal_skillkit_prompt(case)))
        production = _historical_full_input_metrics(case)
        if (production["chars"], production["bytes"]) != (5157, 5281):
            raise EvidenceRunnerError("BLOCKED_PRODUCTION_OR_BASELINE_DRIFT")
        source_commit = _source_commit(self.root)
        output_digest = _minimal_skillkit_output_contract_digest()
        run_id = _minimal_skillkit_run_id(source_commit, self.manifest.raw_digest, output_digest)
        if not _MINIMAL_SKILLKIT_RUN_ID_RE.fullmatch(run_id):
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_RUN_ID_INVALID")
        destination = self._destination(output_path)
        existing = None
        if destination.exists():
            payload, _ = _load_json(destination)
            validate_minimal_skillkit_bundle(payload)
            if payload["run_id"] != run_id:
                raise EvidenceRunnerError("MINIMAL_SKILLKIT_IDENTITY_MISMATCH")
            existing = payload
        return {"case": case, "v2_digest": v2_digest, "output_digest": output_digest, "run_id": run_id, "source_commit": source_commit, "destination": destination, "minimal": minimal, "production": production, "existing": existing}

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_VARIABLE_MISMATCH")
        NestedShapeStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        prepared = self._prepare(output_path)
        existing = prepared["existing"] is not None
        metrics = prepared["minimal"]
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing else "dry_run_minimal_skillkit",
            "experiment_type": MINIMAL_SKILLKIT_EXPERIMENT_TYPE,
            "schema_version": MINIMAL_SKILLKIT_SCHEMA_VERSION,
            "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": prepared["v2_digest"],
            "minimal_output_contract_version": MINIMAL_SKILLKIT_OUTPUT_CONTRACT_VERSION,
            "minimal_output_contract_digest": prepared["output_digest"],
            "parser_contract_version": MINIMAL_SKILLKIT_PARSER_CONTRACT_VERSION,
            "evaluator_context_version": MINIMAL_SKILLKIT_EVALUATOR_CONTEXT_VERSION,
            "run_id": prepared["run_id"], "source_commit": prepared["source_commit"],
            "manifest_digest": self.manifest.raw_digest, "provider": MINIMAL_SKILLKIT_PROVIDER,
            "model": MINIMAL_SKILLKIT_MODEL, "case_id": MINIMAL_SKILLKIT_CASE_ID,
            "timeout_seconds": 60, "max_transport_retries": 0, "target_sample_count": 1,
            "response_mode": MINIMAL_SKILLKIT_RESPONSE_MODE,
            "request_metrics": metrics,
            "production_request_metrics": prepared["production"],
            "minimal_output_instruction_chars": len(MINIMAL_SKILLKIT_OUTPUT_INSTRUCTION),
            "minimal_output_instruction_bytes": len(MINIMAL_SKILLKIT_OUTPUT_INSTRUCTION.encode("utf-8")),
            "existing_sample_count": 1 if existing else 0,
            "existing_sample_indexes": [1] if existing else [],
            "next_sample_index": None if existing else 1,
            "remaining_sample_count": 0 if existing else 1,
            "feature_flag": "OFF", "record_only": True,
            "provider_factory_constructed": False, "provider_called": False,
            "repair_calls": 0, "output_path": prepared["destination"].as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True, **_: object) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("MINIMAL_SKILLKIT_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_VARIABLE_MISMATCH")
        if expected_source_commit is None:
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_SOURCE_COMMIT_REQUIRED")
        source_commit = _source_commit(self.root)
        if source_commit != expected_source_commit:
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_SOURCE_COMMIT_MISMATCH")
        prepared = self._prepare(output_path)
        if prepared["existing"] is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree and _dirty_paths(self.root):
            raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        destination = prepared["destination"]
        if destination.exists() and not resume:
            raise EvidenceRunnerError("MINIMAL_SKILLKIT_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live", "NPC_LLM_PROVIDER": MINIMAL_SKILLKIT_PROVIDER,
                "NPC_LLM_MODEL": MINIMAL_SKILLKIT_MODEL, "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE, "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            try:
                provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        provider_outcome = "failure"
        attempts = 1
        latency_ms = None
        json_outcome = "not_attempted"
        top_level = None
        parser_invoked = False
        parser_outcome = "NOT_REACHED"
        parser_categories: tuple[str, ...] = ()
        parser_counts: dict[str, int] = {}
        ref_invoked = False
        ref_result = "NOT_REACHED"
        evaluator_invoked = False
        evaluator_outcome = "NOT_RUN"
        evaluator_codes: tuple[str, ...] = ()
        principal_verdict = "V2_A_MINIMAL_SKILLKIT_UNAVAILABLE"
        failure_stage = "provider"
        failure_code = "PROVIDER_INVOCATION_FAILED"
        try:
            turn = provider_model.generate(_minimal_skillkit_prompt(prepared["case"]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            json_outcome = "parsed"
            try:
                payload = json.loads(turn.text)
                top_level = _minimal_top_level_type(payload)
            except (TypeError, json.JSONDecodeError):
                json_outcome = "failed"
                failure_stage, failure_code = "json", "RESPONSE_JSON_INVALID"
                principal_verdict = "V2_A_MINIMAL_SKILLKIT_MALFORMED"
            else:
                parser_invoked = True
                try:
                    candidate = parse_candidate(payload)
                except (SkillKitShapeError, TypeError, ValueError) as error:
                    parser_outcome = "PARSER_REJECTED"
                    parser_categories = _minimal_skillkit_failure_categories(error)
                    parser_counts = {category: 1 for category in parser_categories}
                    failure_stage, failure_code = "shape", "CANDIDATE_SHAPE_REJECTED"
                    principal_verdict = "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
                else:
                    parser_outcome = "PARSER_PASS"
                    if not _minimal_skillkit_shape_ok(candidate):
                        parser_outcome = "PARSER_REJECTED"
                        parser_categories = ("MINIMAL_SHAPE_MISMATCH",)
                        parser_counts = {"MINIMAL_SHAPE_MISMATCH": 1}
                        failure_stage, failure_code = "shape", "MINIMAL_SHAPE_REJECTED"
                        principal_verdict = "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
                    else:
                        ref_invoked = True
                        evaluator_invoked = True
                        report = evaluate(candidate, prepared["case"].context)
                        evaluator_outcome = report.outcome
                        evaluator_codes = tuple(report.finding_codes)
                        ref_codes = tuple(
                            code for code in evaluator_codes
                            if "REFERENCE" in code or "DANGLING" in code or code.startswith("FEEDBACK_RELATION")
                        )
                        ref_result = "FAIL" if ref_codes else "PASS"
                        if ref_codes:
                            parser_categories = ("BROKEN_REFERENCE",)
                            parser_counts = {"BROKEN_REFERENCE": len(ref_codes)}
                            principal_verdict = "V2_A_MINIMAL_SKILLKIT_PARSE_REJECTED"
                        else:
                            principal_verdict = "V2_A_MINIMAL_SKILLKIT_STRUCTURAL_PASS"
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            failure_stage, failure_code = "provider", "PROVIDER_INVOCATION_FAILED"
        observation = {
            "observation_id": f"{prepared['run_id']}:case_13:sample-01",
            "provider_outcome": provider_outcome, "transport_attempts": attempts, "latency_ms": latency_ms,
            "json_extraction_outcome": json_outcome, "parsed_top_level_type": top_level,
            "parser_invoked": parser_invoked, "parser_outcome": parser_outcome,
            "parser_failure_categories": parser_categories, "parser_failure_counts": parser_counts,
            "reference_validation_invoked": ref_invoked, "reference_validation_result": ref_result,
            "evaluator_invoked": evaluator_invoked, "evaluator_outcome": evaluator_outcome,
            "evaluator_finding_codes": evaluator_codes, "repair_calls": 0,
            "principal_verdict": principal_verdict,
            "failure_stage": failure_stage, "failure_code": failure_code,
            "sanitization": _sanitization_mapping(),
        }
        bundle = {
            "schema_version": MINIMAL_SKILLKIT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
            "run_id": prepared["run_id"], "experiment_type": MINIMAL_SKILLKIT_EXPERIMENT_TYPE,
            "contract_version": COMPACT_V2_CONTRACT_VERSION, "contract_digest": prepared["v2_digest"],
            "minimal_output_contract_version": MINIMAL_SKILLKIT_OUTPUT_CONTRACT_VERSION,
            "minimal_output_contract_digest": prepared["output_digest"],
            "parser_contract_version": MINIMAL_SKILLKIT_PARSER_CONTRACT_VERSION,
            "evaluator_context_version": MINIMAL_SKILLKIT_EVALUATOR_CONTEXT_VERSION,
            "source_commit": source_commit, "manifest_digest": self.manifest.raw_digest,
            "input_manifest_digest": self.manifest.raw_digest, "inputs": [dict(item) for item in self.manifest.input_files],
            "provider": _minimal_skillkit_provider(), "case_id": MINIMAL_SKILLKIT_CASE_ID,
            "timeout_seconds": 60, "max_transport_retries": 0, "target_sample_count": 1,
            "complete": True, "request_metrics": prepared["minimal"], "sample_index": 1,
            "observation": observation,
        }
        bundle["bundle_digest"] = _minimal_skillkit_bundle_digest(bundle)
        validate_minimal_skillkit_bundle(bundle)
        _write_bundle(destination, bundle, resume=False)
        return bundle


def _o1_safe_diagnostic_fields(snapshot: O1SafeDiagnosticSnapshot, parser_failure_class: str, category: str, resolution: str, *, missing: int = 0, unknown: int = 0, wrong_type: int = 0) -> dict[str, object]:
    return {
        **snapshot.to_dict(),
        "parser_failure_class": parser_failure_class,
        "diagnostic_category": category,
        "diagnostic_resolution": resolution,
        "missing_required_count": missing,
        "unknown_field_count": unknown,
        "wrong_type_count": wrong_type,
    }


def validate_o1_safe_diagnostic_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "level",
        "contract_version", "contract_digest", "output_contract_version", "output_contract_digest",
        "diagnostic_schema_version", "parser_contract_version", "source_commit", "manifest_digest",
        "input_manifest_digest", "inputs", "provider", "model", "case_id", "timeout_seconds",
        "max_transport_retries", "response_mode", "feature_flag", "record_only", "target_sample_count",
        "complete", "request_metrics", "output_fixture_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "O1_SAFE_DIAGNOSTIC_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE
        or bundle["level"] != O1_ROOT_ONLY_LEVEL
        or bundle["contract_version"] != COMPACT_V2_CONTRACT_VERSION
        or bundle["output_contract_version"] not in {O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION, O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION}
        or bundle["parser_contract_version"] != O1_ROOT_ONLY_PARSER_CONTRACT_VERSION
        or bundle["case_id"] != O1_ROOT_ONLY_CASE_ID
        or bundle["timeout_seconds"] != 60
        or bundle["max_transport_retries"] != 0
        or bundle["response_mode"] != O1_ROOT_ONLY_RESPONSE_MODE
        or bundle["feature_flag"] != "OFF"
        or bundle["record_only"] is not True
        or bundle["target_sample_count"] != 1
        or bundle["complete"] is not True
        or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_CONFIG_INVALID")
    expected_output_digest = (
        _o1_root_only_guided_output_contract_digest()
        if bundle["output_contract_version"] == O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION
        else _o1_root_only_output_contract_digest()
    )
    if bundle["output_contract_digest"] != expected_output_digest:
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_OUTPUT_CONTRACT_INVALID")
    for key in ("contract_digest", "output_contract_digest", "diagnostic_schema_version", "manifest_digest"):
        if key == "diagnostic_schema_version":
            if bundle[key] != O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION:
                raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_SCHEMA_INVALID")
        elif not _is_sha(bundle[key]):
            raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_IDENTITY_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_IDENTITY_INVALID")
    if not isinstance(bundle["run_id"], str) or not _O1_SAFE_DIAGNOSTIC_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_RUN_ID_INVALID")
    if bundle["provider"] != _o1_root_only_provider() or bundle["model"] != O1_ROOT_ONLY_MODEL:
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_OBSERVATION_INVALID")
    _exact_keys(observation, _o1_root_only_observation_keys() | {"safe_diagnostics"}, "O1_SAFE_DIAGNOSTIC_OBSERVATION_KEYS_INVALID")
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01" or observation["repair_calls"] != 0 or observation["evaluator_invoked"] is not False or observation["evaluator_outcome"] != "NOT_RUN" or observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_OBSERVATION_INVALID")
    safe = observation["safe_diagnostics"]
    if not isinstance(safe, Mapping):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    expected_safe = set(O1SafeDiagnosticSnapshot(False, False, False, False, 0, False, False, False).to_dict()) | {
        "parser_failure_class", "diagnostic_category", "diagnostic_resolution",
        "missing_required_count", "unknown_field_count", "wrong_type_count",
    }
    _exact_keys(safe, expected_safe, "O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    for key in O1SafeDiagnosticSnapshot(False, False, False, False, 0, False, False, False).to_dict():
        if not isinstance(safe[key], bool) and key != "nonempty_collection_count":
            raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    if isinstance(safe["nonempty_collection_count"], bool) or not isinstance(safe["nonempty_collection_count"], int) or not 0 <= safe["nonempty_collection_count"] <= 6:
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    for key in ("missing_required_count", "unknown_field_count", "wrong_type_count"):
        if isinstance(safe[key], bool) or not isinstance(safe[key], int) or not 0 <= safe[key] <= SHAPE_DIAGNOSTIC_MAX_ERRORS:
            raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    if safe["parser_failure_class"] not in O1_SAFE_DIAGNOSTIC_FAILURE_CLASSES or safe["diagnostic_category"] not in O1_SAFE_DIAGNOSTIC_CATEGORIES or safe["diagnostic_resolution"] not in O1_SAFE_DIAGNOSTIC_RESOLUTIONS:
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_FIELDS_INVALID")
    if observation["principal_verdict"] not in {"O1_ROOT_ONLY_STRUCTURAL_PASS", "O1_ROOT_ONLY_PARSE_REJECTED", "O1_ROOT_ONLY_MALFORMED", "O1_ROOT_ONLY_UNAVAILABLE"}:
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_VERDICT_INVALID")
    if bundle["bundle_digest"] != _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"}):
        raise EvidenceContractError("O1_SAFE_DIAGNOSTIC_BUNDLE_DIGEST_INVALID")


def _o1_safe_diagnostic_run_id(source_commit: str, manifest_digest: str, diagnostic_schema_digest: str) -> str:
    return (
        "cs-s2-shadow-compact-contract-v2-output-stepdown-diagnostic-o1-root-only-v0.1.0-"
        "opencode_go-deepseek-v4-pro-case_13-t60-r0-n1-"
        f"{source_commit}-{manifest_digest[:12]}-{diagnostic_schema_digest[:12]}-run-01"
    )


class O1SafeDiagnosticRunner:
    """Independent O1 diagnostic cohort; model-facing request is byte-identical to O1."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None, guided: bool = False) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)
        self.guided = guided

    def _prompt(self, case: ShadowEvidenceCase) -> AgentPrompt:
        return _o1_root_only_guided_prompt(case) if self.guided else _o1_root_only_prompt(case)

    def _output_contract_version(self) -> str:
        return O1_ROOT_ONLY_GUIDED_OUTPUT_CONTRACT_VERSION if self.guided else O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION

    def _output_contract_digest(self) -> str:
        return _o1_root_only_guided_output_contract_digest() if self.guided else _o1_root_only_output_contract_digest()

    def _identity_digest(self) -> str:
        return self._output_contract_digest() if self.guided else _digest_bytes(O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION.encode("utf-8"))

    def _result_relative_path(self) -> str:
        return O1_ROOT_ONLY_GUIDED_RESULT_RELATIVE_PATH if self.guided else O1_SAFE_DIAGNOSTIC_RESULT_RELATIVE_PATH

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / self._result_relative_path()).resolve()

    def _prepare(self, output_path: Path | str | None = None) -> dict[str, object]:
        historical_destination = self.root / O1_ROOT_ONLY_RESULT_RELATIVE_PATH
        if not historical_destination.exists():
            raise EvidenceRunnerError("BLOCKED_O1_HISTORICAL_EVIDENCE_MISSING")
        historical_payload, _ = _load_json(historical_destination)
        validate_o1_root_only_bundle(historical_payload)
        # The historical O1 bundle is frozen at its original source identity.
        # Prepare the current code's request metrics against an empty temporary
        # destination so the legacy runner cannot reinterpret that bundle as a
        # current-HEAD artifact.
        with tempfile.TemporaryDirectory(prefix="cs-s2-o1-diagnostic-") as temp_dir:
            base = OutputStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._prepare(
                Path(temp_dir) / "legacy-o1-metrics.json"
            )
        if (base["o1"]["chars"], base["o1"]["bytes"]) != (1461, 1589):
            raise EvidenceRunnerError("BLOCKED_DIAGNOSTIC_REQUEST_DRIFT")
        diagnostic_digest = self._output_contract_digest()
        identity_digest = self._identity_digest()
        source_commit = _source_commit(self.root)
        run_id = _o1_safe_diagnostic_run_id(source_commit, self.manifest.raw_digest, identity_digest)
        if not _O1_SAFE_DIAGNOSTIC_RUN_ID_RE.fullmatch(run_id):
            raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_RUN_ID_INVALID")
        destination = self._destination(output_path)
        existing = None
        if destination.exists():
            payload, _ = _load_json(destination)
            validate_o1_safe_diagnostic_bundle(payload)
            if payload["run_id"] != run_id:
                raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_IDENTITY_MISMATCH")
            existing = payload
        base["existing"] = historical_payload
        return {"base": base, "run_id": run_id, "source_commit": source_commit, "diagnostic_digest": diagnostic_digest, "identity_digest": identity_digest, "destination": destination, "existing": existing, "request_metrics": _message_metrics(LiveLLMAdapter._provider_messages(self._prompt(self.cases[O1_ROOT_ONLY_CASE_ID])))}

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_VARIABLE_MISMATCH")
        NestedShapeStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        prepared = self._prepare(output_path)
        old_plan = prepared["base"]
        existing = prepared["existing"] is not None
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing else "dry_run_o1_safe_diagnostic",
            "experiment_type": O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE, "level": O1_ROOT_ONLY_LEVEL,
            "schema_version": O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION, "diagnostic_schema_version": O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION,
            "contract_version": COMPACT_V2_CONTRACT_VERSION, "contract_digest": old_plan["v2_digest"],
            "output_contract_version": self._output_contract_version(), "output_contract_digest": prepared["diagnostic_digest"],
            "parser_contract_version": O1_ROOT_ONLY_PARSER_CONTRACT_VERSION, "run_id": prepared["run_id"],
            "source_commit": prepared["source_commit"], "manifest_digest": self.manifest.raw_digest,
            "provider": O1_ROOT_ONLY_PROVIDER, "model": O1_ROOT_ONLY_MODEL, "case_id": O1_ROOT_ONLY_CASE_ID,
            "timeout_seconds": 60, "max_transport_retries": 0, "response_mode": O1_ROOT_ONLY_RESPONSE_MODE,
            "feature_flag": "OFF", "record_only": True, "target_sample_count": 1,
            "request_metrics": prepared["request_metrics"], "output_fixture_metrics": old_plan["fixture_metrics"],
            "existing_sample_count": 1 if existing else 0, "existing_sample_indexes": [1] if existing else [],
            "next_sample_index": None if existing else 1, "remaining_sample_count": 0 if existing else 1,
            "complete": existing, "provider_factory_constructed": False, "provider_called": False,
            "evaluator_invoked": False, "repair_calls": 0, "old_o1_cohort_complete": old_plan["existing"] is not None,
            "output_path": prepared["destination"].as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True, **_: object) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1) or expected_source_commit is None or _source_commit(self.root) != expected_source_commit:
            raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_SOURCE_OR_VARIABLE_MISMATCH")
        prepared = self._prepare(output_path)
        if prepared["existing"] is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree and _dirty_paths(self.root):
            raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        if prepared["destination"].exists() and not resume:
            raise EvidenceRunnerError("O1_SAFE_DIAGNOSTIC_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live", "NPC_LLM_PROVIDER": O1_ROOT_ONLY_PROVIDER,
                "NPC_LLM_MODEL": O1_ROOT_ONLY_MODEL, "NPC_LLM_TRANSPORT": TRANSPORT,
                "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE, "NPC_LLM_TIMEOUT_SECONDS": "60",
                "NPC_LLM_MAX_RETRIES": "0", **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            try:
                provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        provider_outcome, attempts, latency_ms = "failure", 1, None
        json_outcome, top_level, parser_invoked, parser_outcome = "not_attempted", None, False, "NOT_REACHED"
        parser_categories: tuple[str, ...] = ()
        parser_counts: dict[str, int] = {}
        principal_verdict = "O1_ROOT_ONLY_UNAVAILABLE"
        failure_stage, failure_code = "provider", "PROVIDER_INVOCATION_FAILED"
        safe_snapshot = build_o1_safe_diagnostic_snapshot(None)
        safe_class, safe_category, safe_resolution = "UNAVAILABLE", "INVALID_CANONICAL_VALUE_UNRESOLVED", "CLASS_ONLY"
        try:
            turn = provider_model.generate(self._prompt(self.cases[O1_ROOT_ONLY_CASE_ID]))
            invocation = turn.invocation
            provider_outcome = "success"
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
            try:
                payload = json.loads(turn.text)
                top_level = _minimal_top_level_type(payload)
                json_outcome = "parsed"
            except (TypeError, json.JSONDecodeError):
                json_outcome = "failed"
                principal_verdict, failure_stage, failure_code = "O1_ROOT_ONLY_MALFORMED", "json", "RESPONSE_JSON_INVALID"
                safe_snapshot = build_o1_safe_diagnostic_snapshot(None)
                safe_class, safe_category, safe_resolution = "MALFORMED", "INVALID_CANONICAL_VALUE_UNRESOLVED", "CLASS_ONLY"
            else:
                safe_snapshot = build_o1_safe_diagnostic_snapshot(payload)
                parser_invoked = True
                try:
                    candidate = parse_candidate(payload)
                    if not hasattr(candidate, "entries"):
                        raise SkillKitShapeError("INVALID_ROOT_SHAPE", "/", "legacy candidate is not canonical root")
                except (SkillKitShapeError, TypeError, ValueError) as error:
                    parser_outcome = "PARSER_REJECTED"
                    safe_class = _o1_safe_parser_failure_class(error)
                    safe_category, safe_resolution = classify_o1_safe_diagnostic(safe_snapshot, safe_class, parser_error=error)
                    parser_categories = _o1_root_only_failure_categories(error)
                    parser_counts = {category: 1 for category in parser_categories}
                    principal_verdict, failure_stage, failure_code = "O1_ROOT_ONLY_PARSE_REJECTED", "shape", "CANDIDATE_SHAPE_REJECTED"
                else:
                    parser_outcome = "PARSER_PASS"
                    if safe_snapshot.unexpected_nested_content:
                        safe_class, safe_category, safe_resolution = "INVALID_CANONICAL_VALUE", "O1_CONTRACT_NESTED_CONTENT_VIOLATION", "PARTIALLY_RESOLVED"
                    else:
                        safe_class, safe_category, safe_resolution = "NONE", "NO_DIAGNOSTIC", "NOT_APPLICABLE"
                    principal_verdict, failure_stage, failure_code = "O1_ROOT_ONLY_STRUCTURAL_PASS", None, None
        except ModelError as error:
            invocation = error.audit
            attempts = (invocation.retry_count + 1) if invocation is not None else 1
            latency_ms = _bounded_latency(invocation)
        safe = _o1_safe_diagnostic_fields(
            safe_snapshot, safe_class, safe_category, safe_resolution,
            missing=1 if safe_class == "MISSING_REQUIRED_FIELD" else 0,
            unknown=1 if safe_class == "UNKNOWN_FIELD" else 0,
            wrong_type=1 if safe_class == "WRONG_TYPE" else 0,
        )
        observation = {
            "observation_id": f"{prepared['run_id']}:case_13:sample-01", "provider_outcome": provider_outcome,
            "transport_attempts": attempts, "latency_ms": latency_ms, "json_extraction_outcome": json_outcome,
            "parsed_top_level_type": top_level, "parser_invoked": parser_invoked, "parser_outcome": parser_outcome,
            "parser_failure_categories": parser_categories, "parser_failure_counts": parser_counts,
            "evaluator_invoked": False, "evaluator_outcome": "NOT_RUN", "principal_verdict": principal_verdict,
            "repair_calls": 0, "failure_stage": failure_stage, "failure_code": failure_code,
            "sanitization": _sanitization_mapping(), "safe_diagnostics": safe,
        }
        bundle = {
            "schema_version": O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
            "run_id": prepared["run_id"], "experiment_type": O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE,
            "level": O1_ROOT_ONLY_LEVEL, "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": prepared["base"]["v2_digest"], "output_contract_version": self._output_contract_version(),
            "output_contract_digest": prepared["diagnostic_digest"], "diagnostic_schema_version": O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION,
            "parser_contract_version": O1_ROOT_ONLY_PARSER_CONTRACT_VERSION, "source_commit": prepared["source_commit"],
            "manifest_digest": self.manifest.raw_digest, "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files], "provider": _o1_root_only_provider(),
            "model": O1_ROOT_ONLY_MODEL, "case_id": O1_ROOT_ONLY_CASE_ID, "timeout_seconds": 60,
            "max_transport_retries": 0, "response_mode": O1_ROOT_ONLY_RESPONSE_MODE, "feature_flag": "OFF",
            "record_only": True, "target_sample_count": 1, "complete": True,
            "request_metrics": prepared["request_metrics"], "output_fixture_metrics": prepared["base"]["fixture_metrics"],
            "sample_index": 1, "observation": observation,
        }
        bundle["bundle_digest"] = _digest_mapping(bundle)
        validate_o1_safe_diagnostic_bundle(bundle)
        _write_bundle(prepared["destination"], bundle, resume=False)
        return bundle


def _o2_local_structure_snapshot(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        return {
            "root_schema_version_exact_match": False, "collection_shape_valid": False,
            "entry_count": 0, "protocol_count": 0, "effect_count": 0,
            "typed_ref_count": 0, "local_structure_complete": False,
        }
    collections = ("entries", "feedback_relations", "resources", "states", "summons", "role_evidence")
    shape_valid = all(isinstance(payload.get(name), list) for name in collections)
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    protocols = entries[0].get("protocols") if entries and isinstance(entries[0], Mapping) and isinstance(entries[0].get("protocols"), list) else []
    effects = protocols[0].get("causes") if protocols and isinstance(protocols[0], Mapping) and isinstance(protocols[0].get("causes"), list) else []
    ref_count = 0
    def count_refs(value: object) -> None:
        nonlocal ref_count
        if ref_count >= 2:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"entity_ref", "source_ref", "object_ref"} and item is not None:
                    ref_count += 1
                else:
                    count_refs(item)
                    if ref_count >= 2:
                        return
        elif isinstance(value, list):
            for item in value:
                count_refs(item)
                if ref_count >= 2:
                    return
    count_refs(payload)
    entry_count = min(len(entries), 2)
    protocol_count = min(len(protocols), 2)
    effect_count = min(len(effects), 2)
    local_complete = shape_valid and entry_count == 1 and protocol_count == 1 and effect_count == 1 and ref_count == 0
    return {
        "root_schema_version_exact_match": payload.get("schema_version") == CANDIDATE_SCHEMA_VERSION,
        "collection_shape_valid": shape_valid, "entry_count": entry_count,
        "protocol_count": protocol_count, "effect_count": effect_count,
        "typed_ref_count": min(ref_count, 2), "local_structure_complete": local_complete,
    }


def _o2_local_structure_shape_ok(payload: object) -> bool:
    snapshot = _o2_local_structure_snapshot(payload)
    return snapshot["local_structure_complete"] is True


def validate_o2_local_structure_bundle(bundle: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "protocol_version", "run_id", "experiment_type", "level",
        "contract_version", "contract_digest", "output_contract_version", "output_contract_digest",
        "parser_contract_version", "source_commit", "manifest_digest", "input_manifest_digest",
        "inputs", "provider", "model", "case_id", "timeout_seconds", "max_transport_retries",
        "response_mode", "feature_flag", "record_only", "target_sample_count", "complete",
        "request_metrics", "sample_index", "observation", "bundle_digest",
    }
    _exact_keys(bundle, expected, "O2_LOCAL_STRUCTURE_BUNDLE_KEYS_INVALID")
    if (
        bundle["schema_version"] != O2_LOCAL_STRUCTURE_SCHEMA_VERSION
        or bundle["protocol_version"] != PROTOCOL_VERSION
        or bundle["experiment_type"] != O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE
        or bundle["level"] != O2_LOCAL_STRUCTURE_LEVEL
        or bundle["contract_version"] != COMPACT_V2_CONTRACT_VERSION
        or bundle["output_contract_version"] not in {O2_LOCAL_STRUCTURE_OUTPUT_CONTRACT_VERSION, O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION, O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION}
        or bundle["parser_contract_version"] != O1_ROOT_ONLY_PARSER_CONTRACT_VERSION
        or bundle["case_id"] != "case_13" or bundle["timeout_seconds"] != 60
        or bundle["max_transport_retries"] != 0 or bundle["response_mode"] != "json_object"
        or bundle["feature_flag"] != "OFF" or bundle["record_only"] is not True
        or bundle["target_sample_count"] != 1 or bundle["complete"] is not True or bundle["sample_index"] != 1
    ):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_CONFIG_INVALID")
    if not _is_sha(bundle["contract_digest"]) or not _is_sha(bundle["output_contract_digest"]):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_IDENTITY_INVALID")
    expected_output_digest = (
        _o2_entry_only_output_contract_digest()
        if bundle["output_contract_version"] == O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION
        else _o2_local_structure_compact_output_contract_digest()
        if bundle["output_contract_version"] == O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION
        else _o2_local_structure_output_contract_digest()
    )
    if bundle["output_contract_digest"] != expected_output_digest:
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_OUTPUT_CONTRACT_INVALID")
    if bundle["manifest_digest"] != bundle["input_manifest_digest"] or not isinstance(bundle["source_commit"], str) or not _GIT_SHA_RE.fullmatch(bundle["source_commit"]):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_IDENTITY_INVALID")
    if not isinstance(bundle["run_id"], str) or not _O2_LOCAL_STRUCTURE_RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_RUN_ID_INVALID")
    if bundle["provider"] != _o1_root_only_provider() or bundle["model"] != O1_ROOT_ONLY_MODEL:
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_PROVIDER_INVALID")
    observation = bundle["observation"]
    if not isinstance(observation, Mapping):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_OBSERVATION_INVALID")
    expected_observation = {
        "observation_id", "provider_outcome", "transport_attempts", "latency_ms", "json_extraction_outcome",
        "parsed_top_level_type", "parser_invoked", "parser_outcome", "parser_failure_categories",
        "parser_failure_counts", "evaluator_invoked", "evaluator_outcome", "principal_verdict", "repair_calls",
        "failure_stage", "failure_code", "sanitization", "structural_diagnostics",
    }
    _exact_keys(observation, expected_observation, "O2_LOCAL_STRUCTURE_OBSERVATION_KEYS_INVALID")
    if observation["observation_id"] != f"{bundle['run_id']}:case_13:sample-01" or observation["repair_calls"] != 0 or observation["evaluator_invoked"] is not False or observation["evaluator_outcome"] != "NOT_RUN" or observation["sanitization"] != _sanitization_mapping():
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_OBSERVATION_INVALID")
    structural = observation["structural_diagnostics"]
    if not isinstance(structural, Mapping):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_DIAGNOSTICS_INVALID")
    _exact_keys(structural, {"root_schema_version_exact_match", "collection_shape_valid", "entry_count", "protocol_count", "effect_count", "typed_ref_count", "local_structure_complete"}, "O2_LOCAL_STRUCTURE_DIAGNOSTICS_INVALID")
    for key in ("root_schema_version_exact_match", "collection_shape_valid", "local_structure_complete"):
        if not isinstance(structural[key], bool):
            raise EvidenceContractError("O2_LOCAL_STRUCTURE_DIAGNOSTICS_INVALID")
    for key in ("entry_count", "protocol_count", "effect_count", "typed_ref_count"):
        if isinstance(structural[key], bool) or not isinstance(structural[key], int) or not 0 <= structural[key] <= 2:
            raise EvidenceContractError("O2_LOCAL_STRUCTURE_DIAGNOSTICS_INVALID")
    if observation["principal_verdict"] not in {"O2_LOCAL_STRUCTURE_STRUCTURAL_PASS", "O2_LOCAL_STRUCTURE_PARSE_REJECTED", "O2_LOCAL_STRUCTURE_MALFORMED", "O2_LOCAL_STRUCTURE_UNAVAILABLE"}:
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_VERDICT_INVALID")
    if bundle["bundle_digest"] != _digest_mapping({key: value for key, value in bundle.items() if key != "bundle_digest"}):
        raise EvidenceContractError("O2_LOCAL_STRUCTURE_BUNDLE_DIGEST_INVALID")


class O2LocalStructureRunner:
    """Independent O2 probe: one local protocol/effect, no typed references."""

    def __init__(self, repo_root: Path | str | None = None, *, manifest_path: Path | str | None = None, compact: bool = False, entry_only: bool = False) -> None:
        self.root = Path(repo_root or ROOT).resolve()
        self.manifest = load_manifest(self.root, manifest_path)
        self.cases = _load_cases(self.root, self.manifest)
        self.compact = compact
        self.entry_only = entry_only

    def _prompt(self, case: ShadowEvidenceCase) -> AgentPrompt:
        if self.entry_only:
            return _o2_entry_only_prompt(case)
        return _o2_local_structure_compact_prompt(case) if self.compact else _o2_local_structure_prompt(case)

    def _output_contract_version(self) -> str:
        if self.entry_only:
            return O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION
        return O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION if self.compact else O2_LOCAL_STRUCTURE_OUTPUT_CONTRACT_VERSION

    def _output_contract_digest(self) -> str:
        if self.entry_only:
            return _o2_entry_only_output_contract_digest()
        return _o2_local_structure_compact_output_contract_digest() if self.compact else _o2_local_structure_output_contract_digest()

    def _result_path(self) -> str:
        if self.entry_only:
            return O2_ENTRY_ONLY_RESULT_RELATIVE_PATH
        return O2_LOCAL_STRUCTURE_COMPACT_RESULT_RELATIVE_PATH if self.compact else O2_LOCAL_STRUCTURE_RESULT_RELATIVE_PATH

    def _destination(self, output_path: Path | str | None) -> Path:
        return (Path(output_path) if output_path is not None else self.root / self._result_path()).resolve()

    def _prepare(self, output_path: Path | str | None = None) -> dict[str, object]:
        contract = _compact_v2_contract()
        digest = _digest_bytes(contract.encode("utf-8"))
        if digest != "5dd592925cb4cdc0e20cbb564deedba4c64fe74e8fd79bb2925db66cde801bce" or len(contract) != 981 or len(contract.encode("utf-8")) != 985:
            raise EvidenceRunnerError("BLOCKED_V2_CONTRACT_DRIFT")
        request_metrics = _message_metrics(LiveLLMAdapter._provider_messages(self._prompt(self.cases["case_13"])))
        output_digest = self._output_contract_digest()
        source_commit = _source_commit(self.root)
        run_id = _o2_local_structure_run_id(source_commit, self.manifest.raw_digest, output_digest)
        destination = self._destination(output_path)
        existing = None
        if destination.exists():
            payload, _ = _load_json(destination)
            validate_o2_local_structure_bundle(payload)
            if payload["run_id"] != run_id:
                raise EvidenceRunnerError("O2_LOCAL_STRUCTURE_IDENTITY_MISMATCH")
            existing = payload
        return {"request_metrics": request_metrics, "contract_digest": digest, "output_digest": output_digest, "source_commit": source_commit, "run_id": run_id, "destination": destination, "existing": existing}

    def dry_run(self, *, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, output_path: Path | str | None = None) -> dict[str, object]:
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1):
            raise EvidenceRunnerError("O2_LOCAL_STRUCTURE_VARIABLE_MISMATCH")
        NestedShapeStepdownRunner(self.root, manifest_path=self.root / MANIFEST_RELATIVE_PATH)._assert_historical_integrity()
        prepared = self._prepare(output_path)
        existing = prepared["existing"] is not None
        return {
            "status": "COHORT_ALREADY_COMPLETE" if existing else "dry_run_o2_local_structure",
            "experiment_type": O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE, "level": O2_LOCAL_STRUCTURE_LEVEL,
            "schema_version": O2_LOCAL_STRUCTURE_SCHEMA_VERSION, "contract_version": COMPACT_V2_CONTRACT_VERSION,
            "contract_digest": prepared["contract_digest"], "output_contract_version": self._output_contract_version(),
            "output_contract_digest": prepared["output_digest"], "run_id": prepared["run_id"], "source_commit": prepared["source_commit"],
            "manifest_digest": self.manifest.raw_digest, "provider": O1_ROOT_ONLY_PROVIDER, "model": O1_ROOT_ONLY_MODEL,
            "case_id": "case_13", "timeout_seconds": 60, "max_transport_retries": 0, "target_sample_count": 1,
            "response_mode": "json_object", "feature_flag": "OFF", "record_only": True,
            "request_metrics": prepared["request_metrics"], "existing_sample_count": 1 if existing else 0,
            "existing_sample_indexes": [1] if existing else [], "next_sample_index": None if existing else 1,
            "remaining_sample_count": 0 if existing else 1, "complete": existing,
            "provider_factory_constructed": False, "provider_called": False, "evaluator_invoked": False,
            "repair_calls": 0, "output_path": prepared["destination"].as_posix(),
        }

    def run(self, *, live: bool = False, timeout_seconds: int = 60, max_transport_retries: int = 0, target_sample_count: int = 1, expected_source_commit: str | None = None, resume: bool = False, output_path: Path | str | None = None, model_factory: Callable[[], Any] | None = None, enforce_clean_tree: bool = True, **_: object) -> dict[str, object]:
        if not live:
            if resume or model_factory is not None:
                raise EvidenceRunnerError("O2_LOCAL_STRUCTURE_DRY_RUN_ARGUMENTS_INVALID")
            return self.dry_run(timeout_seconds=timeout_seconds, max_transport_retries=max_transport_retries, target_sample_count=target_sample_count, output_path=output_path)
        if (timeout_seconds, max_transport_retries, target_sample_count) != (60, 0, 1) or expected_source_commit is None or _source_commit(self.root) != expected_source_commit:
            raise EvidenceRunnerError("O2_LOCAL_STRUCTURE_SOURCE_OR_VARIABLE_MISMATCH")
        prepared = self._prepare(output_path)
        if prepared["existing"] is not None:
            raise EvidenceRunnerError("COHORT_ALREADY_COMPLETE")
        if enforce_clean_tree and _dirty_paths(self.root):
            raise EvidenceRunnerError("LIVE_DIRTY_TREE")
        if prepared["destination"].exists() and not resume:
            raise EvidenceRunnerError("O2_LOCAL_STRUCTURE_RESULT_EXISTS")
        if model_factory is not None:
            provider_model = model_factory()
        else:
            environment = {
                "NPC_AGENT_MODEL": "live", "NPC_LLM_PROVIDER": O1_ROOT_ONLY_PROVIDER, "NPC_LLM_MODEL": O1_ROOT_ONLY_MODEL,
                "NPC_LLM_TRANSPORT": TRANSPORT, "NPC_LLM_STRUCTURED_OUTPUT": STRUCTURED_OUTPUT_MODE,
                "NPC_LLM_TIMEOUT_SECONDS": "60", "NPC_LLM_MAX_RETRIES": "0",
                **({"NPC_LLM_API_KEY": os.environ["NPC_LLM_API_KEY"]} if os.environ.get("NPC_LLM_API_KEY") else {}),
            }
            try:
                provider_model = character_model_from_environment(environment=environment, mode_override="live")
            except Exception as error:
                raise EvidenceRunnerError("PROVIDER_FACTORY_FAILED") from error
        provider_outcome, attempts, latency_ms = "failure", 1, None
        json_outcome, top_level, parser_invoked, parser_outcome = "not_attempted", None, False, "NOT_REACHED"
        parser_categories: tuple[str, ...] = ()
        parser_counts: dict[str, int] = {}
        principal_verdict, failure_stage, failure_code = "O2_LOCAL_STRUCTURE_UNAVAILABLE", "provider", "PROVIDER_INVOCATION_FAILED"
        structural = _o2_local_structure_snapshot(None)
        try:
            turn = provider_model.generate(self._prompt(self.cases["case_13"]))
            invocation = turn.invocation
            provider_outcome, attempts, latency_ms = "success", (invocation.retry_count + 1) if invocation is not None else 1, _bounded_latency(invocation)
            try:
                payload = json.loads(turn.text)
                top_level, json_outcome = _minimal_top_level_type(payload), "parsed"
            except (TypeError, json.JSONDecodeError):
                json_outcome, principal_verdict, failure_stage, failure_code = "failed", "O2_LOCAL_STRUCTURE_MALFORMED", "json", "RESPONSE_JSON_INVALID"
            else:
                structural, parser_invoked = _o2_local_structure_snapshot(payload), True
                try:
                    parse_candidate(payload)
                except (SkillKitShapeError, TypeError, ValueError) as error:
                    parser_outcome, parser_categories = "PARSER_REJECTED", _minimal_skillkit_failure_categories(error)
                    parser_counts = {category: 1 for category in parser_categories}
                    principal_verdict, failure_stage, failure_code = "O2_LOCAL_STRUCTURE_PARSE_REJECTED", "shape", "CANDIDATE_SHAPE_REJECTED"
                else:
                    if not self.entry_only and not _o2_local_structure_shape_ok(payload):
                        parser_outcome, parser_categories = "PARSER_REJECTED", ("O2_LOCAL_STRUCTURE_MISMATCH",)
                        parser_counts = {"O2_LOCAL_STRUCTURE_MISMATCH": 1}
                        principal_verdict, failure_stage, failure_code = "O2_LOCAL_STRUCTURE_PARSE_REJECTED", "shape", "LOCAL_STRUCTURE_REJECTED"
                    elif self.entry_only and not (structural["collection_shape_valid"] is True and structural["entry_count"] == 1 and structural["protocol_count"] == 0 and structural["effect_count"] == 0 and structural["typed_ref_count"] == 0):
                        parser_outcome, parser_categories = "PARSER_REJECTED", ("O2_LOCAL_STRUCTURE_MISMATCH",)
                        parser_counts = {"O2_LOCAL_STRUCTURE_MISMATCH": 1}
                        principal_verdict, failure_stage, failure_code = "O2_LOCAL_STRUCTURE_PARSE_REJECTED", "shape", "LOCAL_STRUCTURE_REJECTED"
                    else:
                        parser_outcome, principal_verdict, failure_stage, failure_code = "PARSER_PASS", "O2_LOCAL_STRUCTURE_STRUCTURAL_PASS", None, None
        except ModelError as error:
            invocation = error.audit
            attempts, latency_ms = (invocation.retry_count + 1) if invocation is not None else 1, _bounded_latency(invocation)
        observation = {
            "observation_id": f"{prepared['run_id']}:case_13:sample-01", "provider_outcome": provider_outcome,
            "transport_attempts": attempts, "latency_ms": latency_ms, "json_extraction_outcome": json_outcome,
            "parsed_top_level_type": top_level, "parser_invoked": parser_invoked, "parser_outcome": parser_outcome,
            "parser_failure_categories": parser_categories, "parser_failure_counts": parser_counts,
            "evaluator_invoked": False, "evaluator_outcome": "NOT_RUN", "principal_verdict": principal_verdict,
            "repair_calls": 0, "failure_stage": failure_stage, "failure_code": failure_code,
            "sanitization": _sanitization_mapping(), "structural_diagnostics": structural,
        }
        bundle = {
            "schema_version": O2_LOCAL_STRUCTURE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
            "run_id": prepared["run_id"], "experiment_type": O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE, "level": O2_LOCAL_STRUCTURE_LEVEL,
            "contract_version": COMPACT_V2_CONTRACT_VERSION, "contract_digest": prepared["contract_digest"],
            "output_contract_version": self._output_contract_version(), "output_contract_digest": prepared["output_digest"],
            "parser_contract_version": O1_ROOT_ONLY_PARSER_CONTRACT_VERSION, "source_commit": prepared["source_commit"],
            "manifest_digest": self.manifest.raw_digest, "input_manifest_digest": self.manifest.raw_digest,
            "inputs": [dict(item) for item in self.manifest.input_files], "provider": _o1_root_only_provider(),
            "model": O1_ROOT_ONLY_MODEL, "case_id": "case_13", "timeout_seconds": 60, "max_transport_retries": 0,
            "response_mode": "json_object", "feature_flag": "OFF", "record_only": True, "target_sample_count": 1,
            "complete": True, "request_metrics": prepared["request_metrics"], "sample_index": 1, "observation": observation,
        }
        bundle["bundle_digest"] = _digest_mapping(bundle)
        validate_o2_local_structure_bundle(bundle)
        _write_bundle(prepared["destination"], bundle, resume=False)
        return bundle


def _validate_fixed_target(target: object) -> int:
    if isinstance(target, bool) or not isinstance(target, int) or not 0 < target <= MAX_FIXED_COHORT_SAMPLES:
        raise EvidenceRunnerError("COHORT_TARGET_INVALID")
    return target


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


def run_timeout_suitability(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = TIMEOUT_SUITABILITY_TIMEOUT_SECONDS,
    max_transport_retries: int = TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = TIMEOUT_SUITABILITY_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    shadow_model: Any | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return TimeoutSuitabilityProbeRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        shadow_model=shadow_model,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


def run_model_suitability(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = MODEL_SUITABILITY_TIMEOUT_SECONDS,
    max_transport_retries: int = MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = MODEL_SUITABILITY_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    shadow_model: Any | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return ModelSuitabilityProbeRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        shadow_model=shadow_model,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


def run_minimal_transport_sanity(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS,
    max_transport_retries: int = MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = MINIMAL_TRANSPORT_SANITY_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return MinimalTransportSanityRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


def run_full_input_tiny_output(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = 60,
    max_transport_retries: int = 0,
    target_sample_count: int = 1,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    enforce_clean_tree: bool = True,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return FullInputTinyOutputRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        enforce_clean_tree=enforce_clean_tree,
        model_factory=model_factory,
    )


def run_compact_contract_v2(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = COMPACT_V2_TIMEOUT_SECONDS,
    max_transport_retries: int = COMPACT_V2_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = COMPACT_V2_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
) -> dict[str, object]:
    return CompactContractV2Runner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
    )


def run_minimal_skillkit(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = MINIMAL_SKILLKIT_TIMEOUT_SECONDS,
    max_transport_retries: int = MINIMAL_SKILLKIT_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = MINIMAL_SKILLKIT_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return MinimalSkillKitRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        model_factory=model_factory,
    )


def run_o1_root_only(
    *,
    repo_root: Path | str | None = None,
    live: bool = False,
    timeout_seconds: int = O1_ROOT_ONLY_TIMEOUT_SECONDS,
    max_transport_retries: int = O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES,
    target_sample_count: int = O1_ROOT_ONLY_TARGET,
    expected_source_commit: str | None = None,
    resume: bool = False,
    output_path: Path | str | None = None,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    return OutputStepdownRunner(repo_root).run(
        live=live,
        timeout_seconds=timeout_seconds,
        max_transport_retries=max_transport_retries,
        target_sample_count=target_sample_count,
        expected_source_commit=expected_source_commit,
        resume=resume,
        output_path=output_path,
        model_factory=model_factory,
    )


__all__ = [
    "CASE_IDS",
    "COMPLIANCE_SCHEMA_VERSION",
    "DEFAULT_FIXED_COHORT_TARGET",
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceContractError",
    "EvidenceRunnerError",
    "ContractComplianceCohortRunner",
    "FixedContractComplianceCohortRunner",
    "FIXED_COMPLIANCE_SCHEMA_VERSION",
    "MAX_FIXED_COHORT_SAMPLES",
    "RETRY_SCHEMA_VERSION",
    "RetryUnavailableCohortRunner",
    "ShapeDiagnosticCohortRunner",
    "TimeoutSuitabilityProbeRunner",
    "ModelSuitabilityProbeRunner",
    "MODEL_SUITABILITY_SCHEMA_VERSION",
    "MODEL_SUITABILITY_RESULT_RELATIVE_PATH",
    "MODEL_SUITABILITY_TIMEOUT_SECONDS",
    "MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES",
    "MODEL_SUITABILITY_TARGET",
    "MinimalTransportSanityRunner",
    "MINIMAL_TRANSPORT_SANITY_SCHEMA_VERSION",
    "MINIMAL_TRANSPORT_SANITY_RESULT_RELATIVE_PATH",
    "MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS",
    "MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES",
    "MINIMAL_TRANSPORT_SANITY_TARGET",
    "TIMEOUT_SUITABILITY_SCHEMA_VERSION",
    "TIMEOUT_SUITABILITY_RESULT_RELATIVE_PATH",
    "TIMEOUT_SUITABILITY_TIMEOUT_SECONDS",
    "TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES",
    "TIMEOUT_SUITABILITY_TARGET",
    "ShadowEvidenceModelRouter",
    "ShadowEvidenceRunner",
    "load_manifest",
    "run_retry_unavailable",
    "run_timeout_suitability",
    "run_model_suitability",
    "run_minimal_transport_sanity",
    "run_shadow_evidence",
    "validate_retry_evidence_bundle",
    "validate_shape_diagnostic_bundle",
    "validate_contract_compliance_bundle",
    "validate_fixed_contract_compliance_bundle",
    "validate_timeout_suitability_bundle",
    "validate_model_suitability_bundle",
    "validate_minimal_transport_sanity_bundle",
    "FullInputTinyOutputRunner",
    "EnumExpansionStepdownRunner",
    "NestedShapeStepdownRunner",
    "CompactContractV2Runner",
    "MinimalSkillKitRunner",
    "OutputStepdownRunner",
    "O1SafeDiagnosticRunner",
    "O2LocalStructureRunner",
    "O2_LOCAL_STRUCTURE_COMPACT_OUTPUT_CONTRACT_VERSION",
    "O2_LOCAL_STRUCTURE_COMPACT_RESULT_RELATIVE_PATH",
    "O2_ENTRY_ONLY_OUTPUT_CONTRACT_VERSION",
    "O2_ENTRY_ONLY_RESULT_RELATIVE_PATH",
    "O1SafeDiagnosticSnapshot",
    "build_o1_safe_diagnostic_snapshot",
    "classify_o1_safe_diagnostic",
    "validate_o1_safe_diagnostic_bundle",
    "validate_o2_local_structure_bundle",
    "build_o2_local_structure_fixture",
    "O2_LOCAL_STRUCTURE_SCHEMA_VERSION",
    "O2_LOCAL_STRUCTURE_EXPERIMENT_TYPE",
    "O2_LOCAL_STRUCTURE_LEVEL",
    "O2_LOCAL_STRUCTURE_OUTPUT_CONTRACT_VERSION",
    "O2_LOCAL_STRUCTURE_RESULT_RELATIVE_PATH",
    "O1_SAFE_DIAGNOSTIC_SCHEMA_VERSION",
    "O1_SAFE_DIAGNOSTIC_EXPERIMENT_TYPE",
    "O1_SAFE_DIAGNOSTIC_RESULT_RELATIVE_PATH",
    "O1_ROOT_ONLY_SCHEMA_VERSION",
    "O1_ROOT_ONLY_EXPERIMENT_TYPE",
    "O1_ROOT_ONLY_LEVEL",
    "O1_ROOT_ONLY_OUTPUT_CONTRACT_VERSION",
    "O1_ROOT_ONLY_RESULT_RELATIVE_PATH",
    "O1_ROOT_ONLY_TIMEOUT_SECONDS",
    "O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES",
    "O1_ROOT_ONLY_TARGET",
    "build_o1_root_only_fixture",
    "validate_o1_root_only_bundle",
    "run_o1_root_only",
    "MINIMAL_SKILLKIT_SCHEMA_VERSION",
    "MINIMAL_SKILLKIT_EXPERIMENT_TYPE",
    "MINIMAL_SKILLKIT_RESULT_RELATIVE_PATH",
    "MINIMAL_SKILLKIT_TIMEOUT_SECONDS",
    "MINIMAL_SKILLKIT_MAX_TRANSPORT_RETRIES",
    "MINIMAL_SKILLKIT_TARGET",
    "COMPACT_V2_SCHEMA_VERSION",
    "COMPACT_V2_EXPERIMENT_TYPE",
    "COMPACT_V2_CONTRACT_VERSION",
    "COMPACT_V2_RESULT_RELATIVE_PATH",
    "COMPACT_V2_TIMEOUT_SECONDS",
    "COMPACT_V2_MAX_TRANSPORT_RETRIES",
    "COMPACT_V2_TARGET",
    "build_compact_skillkit_contract_v2",
    "run_compact_contract_v2",
    "validate_minimal_skillkit_bundle",
    "run_minimal_skillkit",
    "FULL_INPUT_TINY_OUTPUT_SCHEMA_VERSION",
    "FULL_INPUT_TINY_OUTPUT_RESULT_RELATIVE_PATH",
    "FULL_INPUT_TINY_OUTPUT_TIMEOUT_SECONDS",
    "FULL_INPUT_TINY_OUTPUT_MAX_TRANSPORT_RETRIES",
    "FULL_INPUT_TINY_OUTPUT_TARGET",
    "run_full_input_tiny_output",
    "validate_enum_stepdown_bundle",
    "validate_nested_shape_stepdown_bundle",
    "validate_evidence_bundle",
]
