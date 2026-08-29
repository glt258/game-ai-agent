"""Example-free model-facing contract for direct Semantic IR generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .projection import (
    HybridGenerationContext,
    SemanticEnumProjection,
    project_semantic_enums,
)

MODEL_FACING_IR_CONTRACT_VERSION = "semantic-skill-plan-ir-contract/0.1.0"
MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED = "semantic-skill-plan-ir-contract/0.3.0"
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
            "must match the mechanic effect actor. The role path provides gameplay "
            "evidence for the selected role, while centrality distinguishes core from secondary "
            "evidence."
        )
    return text


def _enum_text(projection: SemanticEnumProjection) -> str:
    lines = ["Use only these projected semantic values:"]
    for item in projection.domains:
        lines.append(f"{item.domain}=[{','.join(item.values)}]")
    return " ".join(lines)


def _suffix_text() -> str:
    return (
        "Use IR version semantic-skill-plan-ir/0.1.0. Keep qualifier null when absent. "
        "Names, summaries, descriptions, and qualifiers are strings of at most 512 characters; "
        "required narrative fields are non-empty. Return JSON only with no wrapper, commentary, "
        "or extra keys."
    )


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
    aligned = context.contract_profile == "aligned_v1"
    version = MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED if aligned else MODEL_FACING_IR_CONTRACT_VERSION
    base, enum, suffix = _base_text(aligned=aligned), _enum_text(projection), _suffix_text()
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
    case_text = f"Task brief: {context.brief}{plan_line} Generate one minimal semantic skill plan."
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
    "MODEL_FACING_IR_CONTRACT_VERSION",
    "MODEL_FACING_IR_CONTRACT_VERSION_ALIGNED",
    "ModelFacingContract",
    "ModelFacingRequest",
    "RequestSectionMetrics",
    "build_model_facing_contract",
    "build_model_facing_request",
]
