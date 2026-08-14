from __future__ import annotations

import re
from typing import Any, Mapping

from .errors import KnowledgeConfigurationError


FORBIDDEN_SUFFIXES = ("_context", "_knowledge", "_access", "_permission", "_lore")
DECISIONS = frozenset({"REGISTER", "USE_EXISTING", "KEEP_UNRESOLVED"})


def validate_knowledge_responsibilities(
    *,
    knowledge_rules_data: Mapping[str, Any],
    factions_data: Any,
    characters_data: Any | None = None,
    condition_scopes_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the formal responsibility vocabulary and its boundary bindings."""
    vocabulary = knowledge_rules_data.get("vocabulary", {})
    responsibilities = vocabulary.get("responsibility_types", {})
    if not isinstance(responsibilities, Mapping):
        raise KnowledgeConfigurationError("responsibility_types must be a mapping")
    factions = _records(factions_data, "factions")
    faction_ids = {record.get("id") for record in factions}
    errors: list[str] = []
    seen_semantics: dict[tuple[str, str], str] = {}
    for responsibility_id, definition in responsibilities.items():
        if not isinstance(responsibility_id, str) or not responsibility_id.strip():
            errors.append("responsibility IDs must be non-empty strings")
            continue
        if not isinstance(definition, Mapping):
            errors.append(f"{responsibility_id}: definition must be a mapping")
            continue
        faction_id = definition.get("faction_id")
        if faction_id not in faction_ids:
            errors.append(f"{responsibility_id}: unknown faction_id {faction_id}")
        description = definition.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{responsibility_id}: description must be non-empty")
        if any(responsibility_id.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            errors.append(f"{responsibility_id}: forbidden responsibility naming suffix")
        if isinstance(description, str):
            semantic_key = (str(faction_id), _normalize(description))
            previous = seen_semantics.get(semantic_key)
            if previous and previous != responsibility_id:
                errors.append(f"{responsibility_id}: duplicate responsibility semantics with {previous}")
            seen_semantics[semantic_key] = responsibility_id

    rules = _records(knowledge_rules_data, "rules")
    bindings = {
        (item.get("rule_id"), item.get("condition")): item
        for item in (condition_scopes_data or {}).get("bindings", [])
    }
    for rule in rules:
        rule_id = rule.get("id")
        subject_factions = {
            grant.get("subject", {}).get("faction_id")
            for grant in rule.get("grants", [])
            if grant.get("subject", {}).get("faction_id")
        }
        for grant in rule.get("grants", []):
            subject = grant.get("subject", {})
            if subject.get("type") == "responsibility":
                responsibility_id = subject.get("responsibility")
                definition = responsibilities.get(responsibility_id, {})
                if definition.get("faction_id") != subject.get("faction_id"):
                    errors.append(f"{rule_id}: responsibility faction does not match subject faction")
        condition_names = {
            condition
            for grant in rule.get("grants", [])
            for condition in grant.get("conditions", [])
        }
        for condition_name in condition_names:
            binding = bindings.get((rule_id, condition_name))
            if not binding or binding.get("evaluator") != "has_relevant_responsibility":
                continue
            if binding.get("status") != "resolved":
                continue
            for responsibility_id in binding.get("scope", {}).get("values", []):
                definition = responsibilities.get(responsibility_id)
                if not definition:
                    continue
                if subject_factions and definition.get("faction_id") not in subject_factions:
                    errors.append(
                        f"{rule_id}: responsibility {responsibility_id} crosses faction boundary"
                    )

    if characters_data is not None:
        for character in _records(characters_data, "characters"):
            identity = character.get("identity", {})
            character_faction = identity.get("faction_id")
            for responsibility_id in identity.get("responsibilities", []):
                definition = responsibilities.get(responsibility_id)
                if not definition:
                    errors.append(f"{character.get('id')}: unknown responsibility {responsibility_id}")
                elif character_faction and definition.get("faction_id") != character_faction:
                    errors.append(
                        f"{character.get('id')}: responsibility {responsibility_id} crosses faction boundary"
                    )

    if errors:
        raise KnowledgeConfigurationError("; ".join(errors))
    return {
        "valid": True,
        "responsibility_count": len(responsibilities),
        "faction_count": len(faction_ids),
    }


def _records(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping) and isinstance(data.get(key), list):
        return data[key]
    raise KnowledgeConfigurationError(f"{key} must be a list")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
