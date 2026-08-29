"""Example-free model-facing contract for direct Semantic IR generation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType

from .projection import (
    HybridGenerationContext,
    SemanticEnumProjection,
    project_semantic_enums,
)

MODEL_FACING_IR_CONTRACT_VERSION = "semantic-skill-plan-ir-contract/0.1.0"
MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED = "semantic-skill-plan-ir-contract/0.4.0"
MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION = "semantic-skill-plan-ir-contract/0.6.0"
FORBIDDEN_MODEL_TOKENS = (
    "schema_version",
    "ability_id",
    "protocol_id",
    "effect_id",
    "relation_id",
    "feedback_relation_id",
    "source_ref",
    "effect_refs",
    "ref_kind",
    "TypedRef",
    "response_effect_family",
    "allowed_response_effect_families",
)

# These are the only Semantic IR paths that may be rendered as schema-like
# enum constraints.  Projection domain names are intentionally not paths:
# several domains (for example actor and intent) apply at more than one IR
# location, while evaluator-only classifications have no entry at all.
MODEL_FACING_SCHEMA_PATHS = MappingProxyType(
    {
        "actor": (
            "mechanic.trigger.actor",
            "mechanic.effect.actor",
            "mechanic.feedback.response_trigger.actor",
            "mechanic.feedback.response_effect.actor",
            "role_path.trigger.actor",
            "role_path.effect.actor",
        ),
        "trigger_event": (
            "mechanic.trigger.event",
            "mechanic.feedback.response_trigger.event",
            "role_path.trigger.event",
        ),
        "feedback_event": ("mechanic.feedback.event",),
        "feedback_relation": ("mechanic.feedback.relation",),
        "mode": ("mode",),
        "role": ("role",),
        "centrality": ("centrality",),
        "intent": (
            "mechanic.effect.intent",
            "mechanic.feedback.response_effect.intent",
            "role_path.effect.intent",
        ),
    }
)
_SCHEMA_LIKE_ASSIGNMENT = re.compile(r"(?<![\w.])([a-z][a-z0-9_.]*)\s*=\s*\[")
_CONTINUATION_GUIDANCE = MappingProxyType(
    {
        "support": "support/team-enablement-oriented",
        "damage": "offensive/damage-oriented",
        "control": "control-oriented",
        "recovery": "recovery/mitigation-oriented",
    }
)


@dataclass(frozen=True)
class RequestSectionMetrics:
    base_chars: int
    base_bytes: int
    enum_chars: int
    enum_bytes: int
    case_chars: int
    case_bytes: int
    suffix_chars: int
    suffix_bytes: int
    separator_chars: int
    separator_bytes: int
    total_chars: int
    total_bytes: int

    def to_mapping(self) -> dict[str, int]:
        return {
            "base_chars": self.base_chars,
            "base_bytes": self.base_bytes,
            "enum_chars": self.enum_chars,
            "enum_bytes": self.enum_bytes,
            "case_chars": self.case_chars,
            "case_bytes": self.case_bytes,
            "suffix_chars": self.suffix_chars,
            "suffix_bytes": self.suffix_bytes,
            "separator_chars": self.separator_chars,
            "separator_bytes": self.separator_bytes,
            "total_chars": self.total_chars,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True)
class ModelFacingContract:
    version: str
    ir_version: str
    base_text: str
    enum_text: str
    suffix_text: str
    projection: SemanticEnumProjection
    digest: str

    @property
    def text(self) -> str:
        return "\n\n".join((self.base_text, self.enum_text, self.suffix_text))

    def to_mapping(self) -> dict[str, object]:
        return {
            "version": self.version,
            "ir_version": self.ir_version,
            "base_text": self.base_text,
            "enum_text": self.enum_text,
            "suffix_text": self.suffix_text,
            "projection": self.projection.to_mapping(),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ModelFacingRequest:
    contract: ModelFacingContract
    case_text: str
    text: str
    metrics: RequestSectionMetrics


def _base_text(*, aligned: bool = False) -> str:
    text = (
        "Output exactly one JSON object for the semantic skill plan. Required root keys: "
        "ir_version, ability_name, summary, mode, role, centrality, mechanic, role_path. "
        "mechanic requires trigger, effect, feedback; feedback requires event, relation, "
        "response_trigger, response_effect; role_path requires trigger and effect. "
        "A trigger has actor, event, qualifier; an effect has actor, intent, description."
    )
    if aligned:
        text += (
            " Semantic guidance: the trigger describes what starts a mechanic and the effect "
            "describes its immediate gameplay consequence. Feedback describes downstream "
            "continuation enabled or modified by the preceding mechanic; its response trigger "
            "and response effect describe that continuation, and the response trigger actor "
            "must use feedback_received and match the mechanic effect actor. The role path "
            "must provide a matching trigger/effect proof for the selected canonical role, "
            "while centrality distinguishes core from secondary evidence."
        )
    return text


def _legacy_enum_text(projection: SemanticEnumProjection) -> str:
    lines = ["Use only these projected semantic values:"]
    for item in projection.domains:
        lines.append(f"{item.domain}=[{','.join(item.values)}]")
    return " ".join(lines)


def _enum_text(projection: SemanticEnumProjection) -> str:
    lines = ["Use only these projected semantic values:"]
    for item in projection.domains:
        paths = MODEL_FACING_SCHEMA_PATHS.get(item.domain)
        if paths is None:
            raise ValueError(f"MODEL_FACING_DOMAIN_WITHOUT_IR_PATH: {item.domain}")
        rendered_paths = ", ".join(paths)
        values = ", ".join(item.values)
        lines.append(f"Allowed values for {rendered_paths}: {values}.")
    return " ".join(lines)


def validate_model_facing_schema_surface(text: str) -> None:
    """Reject schema-like labels that are not real Semantic IR paths."""

    if not isinstance(text, str):
        raise TypeError("model-facing text must be a string")
    allowed_paths = {
        path for paths in MODEL_FACING_SCHEMA_PATHS.values() for path in paths
    }
    invalid = sorted(
        label
        for label in _SCHEMA_LIKE_ASSIGNMENT.findall(text)
        if label not in allowed_paths
    )
    if invalid:
        raise ValueError(f"MODEL_FACING_NON_SCHEMA_FIELD: {invalid[0]}")


def _suffix_text() -> str:
    return (
        "Use IR version semantic-skill-plan-ir/0.1.0. Keep qualifier null when absent. "
        "Names, summaries, descriptions, and qualifiers are strings of at most 512 characters; "
        "required narrative fields are non-empty. Return JSON only with no wrapper, commentary, "
        "or extra keys."
    )


def _continuation_requirement(context: HybridGenerationContext) -> str:
    families = context.allowed_response_effect_families
    if not families:
        return ""
    guidance = tuple(_CONTINUATION_GUIDANCE[family] for family in families)
    if len(guidance) == 1:
        wording = guidance[0]
    else:
        wording = " or ".join(guidance)
    return f" Continuation constraint: the downstream response effect must remain {wording}."


def _contract_digest(version: str, ir_version: str, base: str, enum: str, suffix: str, projection: SemanticEnumProjection) -> str:
    payload = {
        "version": version,
        "ir_version": ir_version,
        "base": base,
        "enum": enum,
        "suffix": suffix,
        "projection": projection.to_mapping(),
        "restrictions": ["json_object_only", "exact_keys", "bounded_text", "no_extra_keys"],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_model_facing_contract(context: HybridGenerationContext) -> ModelFacingContract:
    """Build an example-free contract from public request/plan context."""

    projection = project_semantic_enums(context)
    aligned = context.contract_profile in {"aligned_v1", "generalization_v1"}
    if context.contract_profile == "generalization_v1":
        version = MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION
    else:
        version = MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED if aligned else MODEL_FACING_IR_CONTRACT_VERSION
    base = _base_text(aligned=aligned)
    enum = (
        _enum_text(projection)
        if context.contract_profile == "generalization_v1"
        else _legacy_enum_text(projection)
    )
    suffix = _suffix_text()
    contract = ModelFacingContract(
        version,
        "semantic-skill-plan-ir/0.1.0",
        base,
        enum,
        suffix,
        projection,
        _contract_digest(
            version,
            "semantic-skill-plan-ir/0.1.0",
            base,
            enum,
            suffix,
            projection,
        ),
    )
    leaked = [token for token in FORBIDDEN_MODEL_TOKENS if token in contract.text]
    if leaked:
        raise ValueError("model-facing contract contains compiler responsibility")
    if context.contract_profile == "generalization_v1":
        validate_model_facing_schema_surface(contract.text)
    return contract


def build_model_facing_request(
    context: HybridGenerationContext,
    contract: ModelFacingContract | None = None,
) -> ModelFacingRequest:
    """Compose the contract and public request projection with exact accounting."""

    selected = contract or build_model_facing_contract(context)
    plan_line = ""
    if context.plan is not None:
        profile = context.plan.combat_role_profile
        constraints = ";".join(context.plan.generation_constraints)
        traits = ";".join(context.plan.recommended_traits)
        plan_line = f" Upstream plan role={profile.primary_role}; constraints=[{constraints}]; traits=[{traits}]."
    continuation = (
        _continuation_requirement(context)
        if context.contract_profile == "generalization_v1"
        else ""
    )
    case_text = (
        f"Task brief: {context.brief}{plan_line} Generate one minimal semantic skill plan."
        f"{continuation}"
    )
    sections = (selected.base_text, selected.enum_text, case_text, selected.suffix_text)
    text = "\n\n".join(sections)
    separator_chars = len("\n\n") * (len(sections) - 1)
    separator_bytes = len("\n\n".encode("utf-8")) * (len(sections) - 1)
    metrics = RequestSectionMetrics(
        len(selected.base_text),
        len(selected.base_text.encode("utf-8")),
        len(selected.enum_text),
        len(selected.enum_text.encode("utf-8")),
        len(case_text),
        len(case_text.encode("utf-8")),
        len(selected.suffix_text),
        len(selected.suffix_text.encode("utf-8")),
        separator_chars,
        separator_bytes,
        len(text),
        len(text.encode("utf-8")),
    )
    return ModelFacingRequest(selected, case_text, text, metrics)


__all__ = [
    "FORBIDDEN_MODEL_TOKENS",
    "MODEL_FACING_SCHEMA_PATHS",
    "MODEL_FACING_IR_CONTRACT_VERSION",
    "MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED",
    "MODEL_FACING_IR_CONTRACT_VERSION_GENERALIZATION",
    "ModelFacingContract",
    "ModelFacingRequest",
    "RequestSectionMetrics",
    "build_model_facing_contract",
    "build_model_facing_request",
    "validate_model_facing_schema_surface",
]
