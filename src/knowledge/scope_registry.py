from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import REGISTERED_EVALUATORS
from .errors import KnowledgeConfigurationError


SCOPE_TYPES = frozenset(
    {
        "responsibility",
        "assignment",
        "project",
        "case",
        "incident",
        "authorization",
        "role_assignment",
        "artist_team",
    }
)
MATCH_MODES = frozenset({"any", "all"})
EXTERNAL_SCOPE_TYPES = frozenset(
    {"project", "case", "incident", "authorization", "artist_team", "role_assignment"}
)


@dataclass(frozen=True)
class ScopeBinding:
    id: str
    rule_id: str
    lore_id: str | None
    condition: str
    evaluator: str
    status: str
    scope_type: str
    match: str
    values: tuple[str, ...]
    notes: str = ""
    unresolved_reason: str | None = None

    def required_scope(self) -> dict[str, Any]:
        return {"type": self.scope_type, "match": self.match, "values": list(self.values)}


class ConditionScopeRegistry:
    """Deterministic binding from a rule condition to concrete scope IDs."""

    def __init__(
        self,
        data: Any | None = None,
        *,
        rules: list[dict[str, Any]],
        lore_ids: set[str],
        condition_types: Mapping[str, Any],
        vocabulary: Mapping[str, Any],
        canonical_registries: Mapping[str, Any] | None = None,
    ) -> None:
        document = self._document(data)
        legacy_registries = document.get("registries", {})
        if not isinstance(legacy_registries, Mapping):
            raise KnowledgeConfigurationError("condition scope registries must be a mapping")
        external_registries = dict(legacy_registries)
        if canonical_registries is not None:
            external_registries.update(
                {key: list(values) for key, values in canonical_registries.items()}
            )
        bindings = document.get("bindings", [])
        if not isinstance(bindings, list):
            raise KnowledgeConfigurationError("condition scope bindings must be a list")
        self.bindings: dict[tuple[str, str], ScopeBinding] = {}
        rule_by_id = {rule.get("id"): rule for rule in rules}
        for raw in bindings:
            binding = self._parse(
                raw, rule_by_id, lore_ids, condition_types, vocabulary, external_registries
            )
            key = (binding.rule_id, binding.condition)
            if key in self.bindings:
                raise KnowledgeConfigurationError(
                    f"duplicate condition scope binding: {binding.rule_id} + {binding.condition}"
                )
            self.bindings[key] = binding

    @staticmethod
    def _document(data: Any | None) -> dict[str, Any]:
        if data is None:
            return {"bindings": []}
        if isinstance(data, Mapping):
            return dict(data)
        raise KnowledgeConfigurationError("condition scope registry must be a mapping")

    @classmethod
    def _parse(
        cls,
        raw: Any,
        rule_by_id: Mapping[str, dict[str, Any]],
        lore_ids: set[str],
        condition_types: Mapping[str, Any],
        vocabulary: Mapping[str, Any],
        external_registries: Mapping[str, Any],
    ) -> ScopeBinding:
        if not isinstance(raw, Mapping):
            raise KnowledgeConfigurationError("every condition scope binding must be a mapping")
        binding_id = raw.get("id")
        rule_id = raw.get("rule_id")
        condition = raw.get("condition")
        if not all(isinstance(value, str) and value for value in (binding_id, rule_id, condition)):
            raise KnowledgeConfigurationError("scope binding requires id, rule_id, and condition")
        rule = rule_by_id.get(rule_id)
        if rule is None:
            raise KnowledgeConfigurationError(f"{binding_id}: unknown rule_id {rule_id}")
        lore_id = raw.get("lore_id", rule.get("lore_id"))
        if lore_id not in lore_ids:
            raise KnowledgeConfigurationError(f"{binding_id}: unknown lore_id {lore_id}")
        if lore_id != rule.get("lore_id"):
            raise KnowledgeConfigurationError(f"{binding_id}: lore_id does not match rule")
        rule_conditions = [condition_name for grant in rule.get("grants", []) for condition_name in grant.get("conditions", [])]
        if condition not in rule_conditions:
            raise KnowledgeConfigurationError(f"{binding_id}: condition is not used by rule {rule_id}")
        definition = condition_types.get(condition)
        evaluator = raw.get("evaluator")
        if not isinstance(definition, Mapping) or evaluator != definition.get("evaluator"):
            raise KnowledgeConfigurationError(f"{binding_id}: evaluator mismatch for {rule_id} + {condition}")
        if evaluator not in REGISTERED_EVALUATORS:
            raise KnowledgeConfigurationError(f"{binding_id}: unsupported evaluator {evaluator}")
        status = raw.get("status")
        if status not in {"resolved", "unresolved"}:
            raise KnowledgeConfigurationError(f"{binding_id}: invalid status {status!r}")
        scope = raw.get("scope") or {}
        scope_type = scope.get("type")
        match = scope.get("match", "any")
        values = scope.get("values", [])
        if scope_type not in SCOPE_TYPES:
            raise KnowledgeConfigurationError(f"{binding_id}: unknown scope type {scope_type!r}")
        if match not in MATCH_MODES:
            raise KnowledgeConfigurationError(f"{binding_id}: unknown match mode {match!r}")
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise KnowledgeConfigurationError(f"{binding_id}: scope values must be strings")
        if status == "resolved" and not values:
            raise KnowledgeConfigurationError(f"{binding_id}: resolved binding requires scope values")
        if status == "resolved" and scope_type in EXTERNAL_SCOPE_TYPES:
            registered_values = external_registries.get(scope_type)
            if not isinstance(registered_values, list):
                raise KnowledgeConfigurationError(f"{binding_id}: resolved {scope_type} scope requires a canonical registry")
            unknown = set(values) - set(registered_values)
            if unknown:
                raise KnowledgeConfigurationError(
                    f"{binding_id}: unknown {scope_type} registry value in canonical registry: {sorted(unknown)}"
                )
        unresolved_reason = raw.get("unresolved_reason")
        if status == "unresolved" and values:
            raise KnowledgeConfigurationError(f"{binding_id}: unresolved binding must have empty scope values")
        if status == "unresolved" and (not isinstance(unresolved_reason, str) or not unresolved_reason.strip()):
            raise KnowledgeConfigurationError(f"{binding_id}: unresolved binding requires unresolved_reason")
        cls._validate_vocabulary_values(binding_id, scope_type, values, vocabulary)
        return ScopeBinding(
            id=binding_id,
            rule_id=rule_id,
            lore_id=lore_id,
            condition=condition,
            evaluator=evaluator,
            status=status,
            scope_type=scope_type,
            match=match,
            values=tuple(values),
            notes=str(raw.get("notes", "")),
            unresolved_reason=unresolved_reason,
        )

    @staticmethod
    def _validate_vocabulary_values(
        binding_id: str, scope_type: str, values: list[str], vocabulary: Mapping[str, Any]
    ) -> None:
        key = {
            "responsibility": "responsibility_types",
            "assignment": "assignment_types",
            "role_assignment": "role_types",
        }.get(scope_type)
        if key is None:
            return
        registered = vocabulary.get(key, {})
        unknown = set(values) - set(registered)
        if unknown:
            raise KnowledgeConfigurationError(
                f"{binding_id}: invalid value(s) {sorted(unknown)}; expected vocabulary {key}"
            )

    def get(self, rule_id: str, condition: str) -> ScopeBinding | None:
        return self.bindings.get((rule_id, condition))

    def inventory(self, rules: list[dict[str, Any]], condition_types: Mapping[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for rule in rules:
            for grant in rule.get("grants", []):
                for condition in grant.get("conditions", []):
                    key = (rule["id"], condition)
                    if key in seen:
                        continue
                    seen.add(key)
                    binding = self.get(rule["id"], condition)
                    status = "missing" if binding is None else binding.status
                    reason = "missing condition scope binding" if binding is None else binding.unresolved_reason
                    result.append(
                        {
                            "binding_id": binding.id if binding else None,
                            "rule_id": rule["id"],
                            "lore_id": rule["lore_id"],
                            "condition": condition,
                            "evaluator": condition_types[condition]["evaluator"],
                            "status": status,
                            "gap_type": _gap_type(binding, condition_types[condition]["evaluator"], reason),
                            "reason": reason,
                        }
                    )
        return result


def _gap_type(binding: ScopeBinding | None, evaluator: str, reason: str | None) -> str | None:
    if binding is None:
        return {
            "assignment_match": "missing_project_registry",
            "case_assignment_match": "missing_case_registry",
            "incident_assignment_match": "missing_incident_registry",
            "explicit_authorization": "missing_authorization_registry",
            "artist_team_match": "missing_artist_team_registry",
            "active_role_assignment": "missing_role_assignment_registry",
            "has_relevant_responsibility": "missing_responsibility_vocabulary",
        }.get(evaluator, "other")
    if binding.status != "unresolved":
        return None
    if binding.condition == "authorized_for_dataset":
        return "missing_dataset_registry"
    if reason and "responsibility vocabulary" in reason.lower():
        return "insufficient_responsibility_vocabulary"
    return {
        "project": "missing_project_registry",
        "case": "missing_case_registry",
        "incident": "missing_incident_registry",
        "authorization": "missing_authorization_registry",
        "artist_team": "missing_artist_team_registry",
        "role_assignment": "missing_role_assignment_registry",
        "responsibility": "insufficient_responsibility_vocabulary",
        "assignment": "missing_assignment_vocabulary",
    }.get(binding.scope_type, "other")
