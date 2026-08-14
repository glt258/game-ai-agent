from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .context import KnowledgeContext, REGISTERED_EVALUATORS
from .evaluators import ConditionEvaluation, evaluate, validate_evaluator_scope
from .errors import (
    KnowledgeAccessDenied,
    KnowledgeConfigurationError,
    KnowledgeContextValidationError,
    UnknownCharacterError,
    UnknownLoreError,
)
from .loader import index_by_id, load_canon
from .registries import (
    registry_ids,
    validate_authorizations,
    validate_case_incident_relationships,
    validate_cases,
    validate_incidents,
    validate_projects,
)
from .models import KnowledgeDecision
from .scope_registry import ConditionScopeRegistry


class KnowledgeResolver:
    """Resolve access to Lore using only Canon identity, rules, and context."""

    _STATIC_EVALUATORS = {"has_relevant_responsibility", "assignment_match"}

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        characters_data: Any | None = None,
        lore_data: Any | None = None,
        knowledge_rules_data: Any | None = None,
        factions_data: Any | None = None,
        condition_scopes_data: Any | None = None,
        projects_data: Any | None = None,
        cases_data: Any | None = None,
        incidents_data: Any | None = None,
        authorizations_data: Any | None = None,
    ) -> None:
        base_datasets = (characters_data, lore_data, knowledge_rules_data, factions_data)
        if any(value is not None for value in base_datasets):
            if any(value is None for value in base_datasets):
                raise ValueError("Inject all four base datasets together")
            raw = {
                "characters": characters_data,
                "lore": lore_data,
                "knowledge_rules": knowledge_rules_data,
                "factions": factions_data,
                "condition_scopes": condition_scopes_data or {"bindings": []},
                "projects": projects_data or {"version": "0.1", "projects": []},
                "cases": cases_data or {"version": "0.1", "cases": []},
                "incidents": incidents_data or {"version": "0.1", "incidents": []},
                "authorizations": authorizations_data or {"version": "0.1", "authorizations": []},
            }
        else:
            raw = load_canon(data_dir)

        self.characters = index_by_id(self._extract(raw["characters"], "characters"), "character")
        self.lore = index_by_id(self._extract(raw["lore"], "lore"), "lore")
        self.factions = index_by_id(self._extract(raw["factions"], "factions"), "faction")
        rules_document = self._document(raw["knowledge_rules"], "rules")
        self.rules = self._extract(rules_document.get("rules", []), "rules")
        self.policy = rules_document.get("principles", {})
        self.vocabulary = rules_document.get("vocabulary", {})
        self.validation = rules_document.get("validation", {})
        project_document = raw.get("projects", {"version": "0.1", "projects": []})
        case_document = raw.get("cases", {"version": "0.1", "cases": []})
        incident_document = raw.get("incidents", {"version": "0.1", "incidents": []})
        authorization_document = raw.get("authorizations", {"version": "0.1", "authorizations": []})
        self.projects = validate_projects(
            project_document,
            faction_ids=set(self.factions),
            lore_ids=set(self.lore),
            assignment_ids=set(self.vocabulary.get("assignment_types", {})),
        )
        case_ids = registry_ids(case_document, "cases")
        incident_ids = registry_ids(incident_document, "incidents")
        self.cases = validate_cases(
            case_document,
            faction_ids=set(self.factions),
            lore_ids=set(self.lore),
            incident_ids=incident_ids,
            project_ids=set(self.projects),
        )
        self.incidents = validate_incidents(
            incident_document,
            faction_ids=set(self.factions),
            lore_ids=set(self.lore),
            case_ids=case_ids,
        )
        validate_case_incident_relationships(self.cases, self.incidents)
        self.authorizations = validate_authorizations(
            authorization_document,
            faction_ids=set(self.factions),
            target_registries={
                "project": set(self.projects),
                "case": set(self.cases),
                "incident": set(self.incidents),
            },
        )
        canonical_registries = {
            "project": sorted(self.projects),
            "case": sorted(self.cases),
            "incident": sorted(self.incidents),
            "authorization": sorted(self.authorizations),
        }
        self._validate_runtime_registry_ids = not (
            any(value is not None for value in base_datasets)
            and projects_data is None
            and cases_data is None
            and incidents_data is None
            and authorizations_data is None
        )
        # Preserve the old in-memory fixture convention when no registry data
        # was injected. Repository data always supplies the formal registries.
        if projects_data is None and authorizations_data is None and condition_scopes_data is not None:
            legacy = (condition_scopes_data or {}).get("registries", {})
            if not self.authorizations and isinstance(legacy, Mapping) and "authorization" in legacy:
                canonical_registries["authorization"] = list(legacy["authorization"])
        self.scope_registry = ConditionScopeRegistry(
            raw.get("condition_scopes"),
            rules=self.rules,
            lore_ids=set(self.lore),
            condition_types=self.vocabulary.get("condition_types", {}),
            vocabulary=self.vocabulary,
            canonical_registries=canonical_registries,
        )
        self.rules_by_lore_id: dict[str, list[dict[str, Any]]] = {}
        self._validate_configuration()
        for rule in self.rules:
            self.rules_by_lore_id.setdefault(rule["lore_id"], []).append(rule)

    @staticmethod
    def _document(data: Any, list_key: str) -> dict[str, Any]:
        if isinstance(data, Mapping):
            return dict(data)
        if isinstance(data, list):
            return {list_key: data}
        raise ValueError(f"Expected a mapping or list for {list_key}")

    @classmethod
    def _extract(cls, data: Any, key: str) -> list[dict[str, Any]]:
        document = cls._document(data, key)
        records = document.get(key, [])
        if not isinstance(records, list):
            raise ValueError(f"Expected {key} to be a list")
        return records

    def _validate_configuration(self) -> None:
        subject_types = set(self.vocabulary.get("subject_types", []))
        condition_types = self.vocabulary.get("condition_types", {})
        roles = self.vocabulary.get("role_types", {})
        responsibilities = self.vocabulary.get("responsibility_types", {})
        assignments = self.vocabulary.get("assignment_types", {})
        channels = set(self.vocabulary.get("acquisition_channels", []))
        faction_divisions = {
            division.get("id")
            for faction in self.factions.values()
            for division in faction.get("internal_structure", {}).get("divisions", [])
        }
        for rule in self.rules:
            rule_id = rule.get("id")
            lore_id = rule.get("lore_id")
            if not isinstance(rule_id, str) or not rule_id:
                raise KnowledgeConfigurationError("Every knowledge rule needs an id")
            if lore_id not in self.lore:
                raise KnowledgeConfigurationError(f"{rule_id}: unknown lore_id {lore_id}")
            for grant in rule.get("grants", []):
                subject = grant.get("subject", {})
                subject_type = subject.get("type")
                if subject_type not in subject_types:
                    raise KnowledgeConfigurationError(
                        f"{rule_id}: unknown subject type {subject_type!r}"
                    )
                faction_id = subject.get("faction_id")
                if faction_id is not None and faction_id not in self.factions:
                    raise KnowledgeConfigurationError(f"{rule_id}: unknown faction {faction_id}")
                if subject_type == "division" and subject.get("division_id") not in faction_divisions:
                    raise KnowledgeConfigurationError(
                        f"{rule_id}: unknown division {subject.get('division_id')}"
                    )
                if subject_type == "role" and subject.get("role") not in roles:
                    raise KnowledgeConfigurationError(f"{rule_id}: unknown role {subject.get('role')}")
                if subject_type == "responsibility" and subject.get("responsibility") not in responsibilities:
                    raise KnowledgeConfigurationError(
                        f"{rule_id}: unknown responsibility {subject.get('responsibility')}"
                    )
                if subject_type == "assignment" and subject.get("assignment_id") not in assignments:
                    raise KnowledgeConfigurationError(
                        f"{rule_id}: unknown assignment {subject.get('assignment_id')}"
                    )
                for condition in grant.get("conditions", []):
                    definition = condition_types.get(condition)
                    if definition is None:
                        raise KnowledgeConfigurationError(f"{rule_id}: unknown condition {condition}")
                    evaluator = definition.get("evaluator")
                    if evaluator not in REGISTERED_EVALUATORS:
                        raise KnowledgeConfigurationError(
                            f"{rule_id}: unsupported evaluator {evaluator} for {condition}"
                        )
                    binding = self.scope_registry.get(rule_id, condition)
                    if binding is not None:
                        validate_evaluator_scope(evaluator, binding.scope_type)
                for channel in rule.get("acquisition", {}).get("channels", []):
                    if channel not in channels:
                        raise KnowledgeConfigurationError(
                            f"{rule_id}: unregistered acquisition channel {channel}"
                        )

        if self.validation.get("forbid_relevant_prefix_in_roles"):
            if any(name.startswith("relevant_") for name in roles):
                raise KnowledgeConfigurationError("Role vocabulary must not contain relevant_* pseudo-roles")
        if self.validation.get("forbid_ordinary_prefix_in_roles"):
            if any(name.startswith("ordinary_") for name in roles):
                raise KnowledgeConfigurationError("Role vocabulary must not contain ordinary_* pseudo-roles")

    def resolve(
        self,
        character_id: str,
        lore_id: str,
        context: KnowledgeContext | None = None,
    ) -> KnowledgeDecision:
        character = self.characters.get(character_id)
        if character is None:
            raise UnknownCharacterError(character_id)
        lore = self.lore.get(lore_id)
        if lore is None:
            raise UnknownLoreError(lore_id)
        context = context or KnowledgeContext()
        if self._validate_runtime_registry_ids:
            unknown_projects = set(context.active_projects) - set(self.projects)
            if unknown_projects:
                raise KnowledgeContextValidationError("project", unknown_projects)
            unknown_cases = set(context.active_cases) - set(self.cases)
            if unknown_cases:
                raise KnowledgeContextValidationError("case", unknown_cases)
            unknown_incidents = set(context.active_incidents) - set(self.incidents)
            if unknown_incidents:
                raise KnowledgeContextValidationError("incident", unknown_incidents)
            unknown_authorizations = set(context.authorizations) - set(self.authorizations)
            if unknown_authorizations:
                raise KnowledgeContextValidationError("authorization", unknown_authorizations)

        if lore.get("sensitivity") == "public":
            return KnowledgeDecision(
                decision="allow",
                character_id=character_id,
                lore_id=lore_id,
                reason_code="public_lore",
                reason="Lore is explicitly public under the knowledge policy.",
                acquisition_channel="public_information",
                trace=(
                    {
                        "candidate_rule_id": None,
                        "subject": {"type": "everyone", "matched": True},
                        "conditions": [],
                        "final": "allow",
                        "reason_code": "public_lore",
                    },
                ),
            )

        traces: list[dict[str, Any]] = []
        evaluated: list[dict[str, Any]] = []
        successes: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
        # Missing context is only meaningful after a candidate subject matched.
        # A completely unrelated character must remain an ordinary default deny.
        missing_context_seen = False
        rules = self.rules_by_lore_id.get(lore_id, [])
        for rule in rules:
            for grant in rule.get("grants", []):
                subject = grant.get("subject", {})
                matched, subject_trace = self._subject_match(character, subject)
                trace: dict[str, Any] = {
                    "candidate_rule_id": rule.get("id"),
                    "subject": subject_trace,
                    "conditions": [],
                }
                if not matched:
                    trace.update(final="reject", reason_code="subject_mismatch")
                    traces.append(trace)
                    continue
                condition_results: list[dict[str, Any]] = []
                all_conditions_match = True
                for condition in grant.get("conditions", []):
                    definition = self.vocabulary["condition_types"][condition]
                    evaluator = definition["evaluator"]
                    binding = self.scope_registry.get(rule["id"], condition)
                    if binding is None:
                        result = ConditionEvaluation(
                            condition=condition,
                            evaluator=evaluator,
                            result=False,
                            reason_code="condition_scope_missing",
                            reason="No scope binding exists for this rule condition.",
                            required_scope={},
                            actual_scope={"values": []},
                        )
                    else:
                        result = evaluate(
                            character=character,
                            context=context,
                            binding=binding,
                            condition=condition,
                            evaluator=evaluator,
                        )
                    condition_trace = result.to_dict()
                    condition_results.append(condition_trace)
                    evaluated.append({"rule_id": rule.get("id"), **condition_trace})
                    if result.reason_code in {"condition_context_missing", "condition_scope_missing"}:
                        missing_context_seen = True
                    all_conditions_match = all_conditions_match and result.result
                trace["conditions"] = condition_results
                if all_conditions_match:
                    trace.update(final="allow", reason_code="rule_match")
                    successes.append(
                        (
                            self._specificity(subject.get("type")),
                            int(rule.get("priority", 0)),
                            rule,
                            subject,
                        )
                    )
                else:
                    trace.update(final="reject", reason_code="condition_not_satisfied")
                traces.append(trace)

        if successes:
            _, _, rule, subject = max(
                successes,
                key=lambda item: (item[0], item[1], item[2].get("id", "")),
            )
            channels = rule.get("acquisition", {}).get("channels", [])
            return KnowledgeDecision(
                decision="allow",
                character_id=character_id,
                lore_id=lore_id,
                reason_code="knowledge_rule_match",
                reason="A knowledge rule matched the character subject and all required conditions.",
                matched_rule_id=rule.get("id"),
                matched_subject=subject.get("type"),
                acquisition_channel=channels[0] if channels else None,
                evaluated_conditions=tuple(evaluated),
                trace=tuple(traces),
            )

        failure_codes = [
            item.get("reason_code")
            for item in evaluated
            if item.get("reason_code")
        ]
        reason_code = next(
            (code for code in ("condition_scope_missing", "condition_context_missing", "condition_not_satisfied", "condition_scope_unresolved") if code in failure_codes),
            "no_matching_rule" if not rules else "default_deny",
        )
        reason = (
            "Access denied because required runtime context was not explicitly provided."
            if reason_code in {"condition_context_missing", "condition_scope_missing", "condition_scope_unresolved"}
            else "No knowledge rule fully matched; access is denied by default."
        )
        return KnowledgeDecision(
            decision="deny",
            character_id=character_id,
            lore_id=lore_id,
            reason_code=reason_code,
            reason=reason,
            evaluated_conditions=tuple(evaluated),
            trace=tuple(traces),
        )

    @staticmethod
    def _specificity(subject_type: str | None) -> int:
        return {
            "everyone": 0,
            "faction": 1,
            "division": 2,
            "role": 3,
            "responsibility": 3,
            "assignment": 3,
            "explicit_grant": 4,
        }.get(subject_type, -1)

    @staticmethod
    def _identity(character: Mapping[str, Any]) -> Mapping[str, Any]:
        return character.get("identity", {})

    def _subject_match(
        self, character: Mapping[str, Any], subject: Mapping[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        identity = self._identity(character)
        subject_type = subject.get("type")
        required_faction = subject.get("faction_id")
        actual_faction = identity.get("faction_id")
        faction_matches = required_faction is None or actual_faction == required_faction
        actual: Any = None
        required: Any = None
        if subject_type == "everyone":
            matched = True
        elif subject_type == "faction":
            actual, required = identity.get("faction_id"), subject.get("faction_id")
            matched = actual == required
        elif subject_type == "division":
            actual, required = identity.get("division_ids", []), subject.get("division_id")
            matched = faction_matches and required in actual
        elif subject_type == "role":
            actual, required = identity.get("roles", []), subject.get("role")
            matched = faction_matches and required in actual
        elif subject_type == "responsibility":
            actual, required = identity.get("responsibilities", []), subject.get("responsibility")
            matched = faction_matches and required in actual
        elif subject_type == "assignment":
            actual, required = identity.get("assignments", []), subject.get("assignment_id")
            matched = faction_matches and required in actual
        elif subject_type == "explicit_grant":
            actual, required = identity.get("explicit_grants", []), self._required_grant(subject)
            matched = faction_matches and any(self._grant_value(item) == required for item in actual)
        else:
            # Initialization normally prevents reaching this branch. Keeping it fail-closed
            # protects injected data if validation is bypassed in a future refactor.
            matched = False
        return matched, {
            "type": subject_type,
            "required": required,
            "actual": actual,
            "required_faction": required_faction,
            "actual_faction": actual_faction,
            "faction_matched": faction_matches,
            "matched": matched,
        }

    @staticmethod
    def _required_grant(subject: Mapping[str, Any]) -> Any:
        return subject.get("grant_id", subject.get("explicit_grant"))

    @staticmethod
    def _grant_value(value: Any) -> Any:
        if isinstance(value, Mapping):
            return value.get("grant_id", value.get("id", value.get("name")))
        return value

    def can_access(self, character_id: str, lore_id: str, context: KnowledgeContext | None = None) -> bool:
        return self.resolve(character_id, lore_id, context).decision == "allow"

    def require_access(
        self, character_id: str, lore_id: str, context: KnowledgeContext | None = None
    ) -> KnowledgeDecision:
        decision = self.resolve(character_id, lore_id, context)
        if decision.decision == "deny":
            raise KnowledgeAccessDenied(decision)
        return decision


def resolver_from_data_dir(data_dir: Path | None = None) -> KnowledgeResolver:
    """Convenience factory kept small for CLI and future integrations."""
    return KnowledgeResolver(data_dir=data_dir)
