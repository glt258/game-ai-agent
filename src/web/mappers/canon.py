from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..schemas.canon import (
    CanonCharacterSectionDTO,
    CanonEntityDetailDTO,
    CanonEntityListDTO,
    CanonEntitySummaryDTO,
    CanonEntityType,
    CanonFactionSectionDTO,
    CanonLoreSectionDTO,
    CanonMemberProfileDTO,
    CanonProvenanceDTO,
    CanonRegistrySectionDTO,
    CanonRelationshipDTO,
    CanonSectionsDTO,
    CanonStorySectionDTO,
    CanonTemporalDTO,
    CanonTextDTO,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def _description(value: Any) -> str | None:
    return _text(_mapping(value).get("description"))


def _common_kwargs(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": summary["entity_id"],
        "entity_type": summary["entity_type"],
        "name": summary["name"],
        "aliases": list(summary["aliases"]),
        "summary": summary["summary"],
        "tags": list(summary["tags"]),
        "visibility": "public",
    }


def _faction(data: Mapping[str, Any]) -> CanonFactionSectionDTO:
    member = _mapping(data.get("member_profile"))
    return CanonFactionSectionDTO(
        display_name=_text(data.get("name")) or "",
        aliases=_strings(data.get("aliases")),
        faction_type=_text(data.get("type")),
        status=_text(data.get("status")),
        core_function=CanonTextDTO(description=_description(data.get("core_function"))),
        public_identity=CanonTextDTO(description=_description(data.get("public_identity"))),
        public_reputation=CanonTextDTO(description=_description(data.get("public_reputation"))),
        member_profile=CanonMemberProfileDTO(
            typical_roles=_strings(member.get("typical_roles")),
            recruitment_description=_description(member.get("recruitment")),
            culture=_description(member.get("culture")),
        ),
        tags=_strings(data.get("tags")),
    )


def _lore(data: Mapping[str, Any]) -> CanonLoreSectionDTO:
    temporal = _mapping(data.get("temporal"))
    truth_status = data.get("truth_status")
    return CanonLoreSectionDTO(
        title=_text(data.get("title")) or "",
        statement=_text(data.get("statement")) or "",
        category=_text(data.get("category")),
        truth_status=truth_status if isinstance(truth_status, bool) else None,
        sensitivity="public",
        canon_level=_text(data.get("canon_level")),
        temporal=CanonTemporalDTO(
            status=_text(temporal.get("status")),
            since=_text(temporal.get("since")),
            until=_text(temporal.get("until")),
        ),
        tags=_strings(data.get("tags")),
    )


def _character(data: Mapping[str, Any]) -> CanonCharacterSectionDTO:
    name = _mapping(data.get("name"))
    basic_profile = _mapping(data.get("basic_profile"))
    identity = _mapping(data.get("identity"))
    hook = _mapping(data.get("character_hook"))
    social_identity = _mapping(data.get("social_identity"))
    combat = _mapping(data.get("combat"))
    return CanonCharacterSectionDTO(
        display_name=_text(name.get("display_name")) or "",
        aliases=_strings(name.get("aliases")),
        occupation=_text(basic_profile.get("occupation")),
        faction_id=_text(identity.get("faction_id")),
        first_impression=_text(hook.get("first_impression")),
        combat_role=_text(combat.get("tentative_role")),
        public_reputation=_text(social_identity.get("public_reputation")),
        tags=_strings(data.get("tags")),
    )


def _registry(data: Mapping[str, Any]) -> CanonRegistrySectionDTO:
    return CanonRegistrySectionDTO(
        name=_text(data.get("name")) or "",
        description=_text(data.get("description")),
        status=_text(data.get("status")),
    )


def _story(data: Mapping[str, Any]) -> CanonStorySectionDTO:
    setting = _mapping(data.get("setting"))
    return CanonStorySectionDTO(
        title=_text(data.get("title")) or "",
        canon_status=_text(data.get("canon_status")),
        premise=_text(data.get("premise")) or "",
        city_id=_text(setting.get("city_id")),
        district_name=_text(setting.get("district_name")),
        objective_facts=_strings(data.get("objective_facts")),
    )


def _sections(entity_type: CanonEntityType, data: Mapping[str, Any]) -> CanonSectionsDTO:
    values: dict[str, Any] = {}
    if entity_type == "faction":
        values["faction"] = _faction(data)
    elif entity_type == "lore":
        values["lore"] = _lore(data)
    elif entity_type == "character":
        values["character"] = _character(data)
    elif entity_type in {"project", "case", "incident"}:
        values[entity_type] = _registry(data)
    elif entity_type == "story":
        values["story"] = _story(data)
    return CanonSectionsDTO(**values)


def to_canon_list(
    summaries: list[dict[str, Any]],
    entity_types: list[CanonEntityType],
) -> CanonEntityListDTO:
    return CanonEntityListDTO(
        schema_version="web-canon-entity-list/0.1",
        entities=[CanonEntitySummaryDTO(**summary) for summary in summaries],
        entity_types=entity_types,
        total=len(summaries),
    )


def to_canon_detail(
    record: Any,
    summary: Mapping[str, Any],
    relationships: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
) -> CanonEntityDetailDTO:
    return CanonEntityDetailDTO(
        schema_version="web-canon-entity/0.1",
        **_common_kwargs(summary),
        sections=_sections(record.entity_type, _mapping(record.data)),
        relationships=[CanonRelationshipDTO(**item) for item in relationships],
        provenance=[CanonProvenanceDTO(**item) for item in provenance],
    )


__all__ = ["to_canon_detail", "to_canon_list"]
