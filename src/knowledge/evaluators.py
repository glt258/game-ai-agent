from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import KnowledgeContext
from .errors import KnowledgeConfigurationError
from .scope_registry import ScopeBinding


@dataclass(frozen=True)
class ConditionEvaluation:
    condition: str
    evaluator: str
    result: bool
    reason_code: str
    reason: str
    required_scope: dict[str, Any]
    actual_scope: dict[str, Any]
    matched_values: tuple[str, ...] = ()
    binding_id: str | None = None
    binding_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "evaluator": self.evaluator,
            "binding_id": self.binding_id,
            "binding_status": self.binding_status,
            "required_scope": dict(self.required_scope),
            "actual_scope": dict(self.actual_scope),
            "matched_values": list(self.matched_values),
            "result": self.result,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


_EXPECTED_SCOPE_TYPES = {
    "has_relevant_responsibility": {"responsibility"},
    "assignment_match": {"assignment", "project"},
    "case_assignment_match": {"case"},
    "explicit_authorization": {"authorization"},
    "active_role_assignment": {"role_assignment"},
    "artist_team_match": {"artist_team"},
    "incident_assignment_match": {"incident"},
}


def validate_evaluator_scope(evaluator: str, scope_type: str) -> None:
    if scope_type not in _EXPECTED_SCOPE_TYPES.get(evaluator, set()):
        raise KnowledgeConfigurationError(
            f"evaluator {evaluator} cannot evaluate scope type {scope_type}"
        )


def evaluate(
    *,
    character: Mapping[str, Any],
    context: KnowledgeContext,
    binding: ScopeBinding,
    condition: str,
    evaluator: str,
) -> ConditionEvaluation:
    validate_evaluator_scope(evaluator, binding.scope_type)
    if binding.status != "resolved":
        return ConditionEvaluation(
            condition=condition,
            evaluator=evaluator,
            result=False,
            reason_code="condition_scope_unresolved",
            reason="The registry binding is explicitly unresolved.",
            required_scope=binding.required_scope(),
            actual_scope={"values": []},
            binding_id=binding.id,
            binding_status=binding.status,
        )

    identity = character.get("identity", {})
    actual_values = _actual_values(evaluator, binding.scope_type, identity, context)
    required = set(binding.values)
    actual = set(actual_values)
    matched = required & actual
    if binding.match == "all":
        result = bool(required) and required <= actual
    else:
        result = bool(matched)
    reason_code = "condition_not_satisfied"
    if not actual:
        reason_code = "condition_context_missing"
        reason = "Runtime context did not provide concrete IDs for the required scope."
    else:
        reason = "Required scope IDs matched runtime context." if result else "No required scope ID matched runtime context."
    return ConditionEvaluation(
        condition=condition,
        evaluator=evaluator,
        result=result,
        reason_code=reason_code,
        reason=reason,
        required_scope=binding.required_scope(),
        actual_scope={"values": sorted(actual)},
        matched_values=tuple(sorted(matched)),
        binding_id=binding.id,
        binding_status=binding.status,
    )


def _actual_values(
    evaluator: str,
    scope_type: str,
    identity: Mapping[str, Any],
    context: KnowledgeContext,
) -> set[str]:
    if evaluator == "has_relevant_responsibility":
        return set(identity.get("responsibilities", [])) | set(context.active_responsibilities)
    if evaluator == "assignment_match":
        if scope_type == "project":
            return set(context.active_projects)
        return set(identity.get("assignments", [])) | set(context.active_assignments)
    if evaluator == "case_assignment_match":
        return set(context.active_cases)
    if evaluator == "explicit_authorization":
        return {
            value.get("grant_id", value.get("id", value.get("name")))
            if isinstance(value, Mapping)
            else value
            for value in identity.get("explicit_grants", [])
        } | set(context.authorizations)
    if evaluator == "active_role_assignment":
        return set(context.active_roles)
    if evaluator == "artist_team_match":
        return set(identity.get("artist_teams", [])) | set(context.artist_teams)
    if evaluator == "incident_assignment_match":
        return set(context.active_incidents)
    raise KnowledgeConfigurationError(f"unsupported evaluator: {evaluator}")
