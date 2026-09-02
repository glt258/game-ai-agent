from __future__ import annotations

from typing import Literal

from .common import WebModel

CanonEntityType = Literal[
    "faction",
    "lore",
    "character",
    "project",
    "case",
    "incident",
    "story",
]


class CanonEntitySummaryDTO(WebModel):
    entity_id: str
    entity_type: CanonEntityType
    name: str
    aliases: list[str]
    summary: str
    tags: list[str]
    relation_count: int
    visibility: Literal["public"]


class CanonEntityListDTO(WebModel):
    schema_version: Literal["web-canon-entity-list/0.1"]
    entities: list[CanonEntitySummaryDTO]
    entity_types: list[CanonEntityType]
    total: int


class CanonTextDTO(WebModel):
    description: str | None


class CanonMemberProfileDTO(WebModel):
    typical_roles: list[str]
    recruitment_description: str | None
    culture: str | None


class CanonFactionSectionDTO(WebModel):
    display_name: str
    aliases: list[str]
    faction_type: str | None
    status: str | None
    core_function: CanonTextDTO
    public_identity: CanonTextDTO
    public_reputation: CanonTextDTO
    member_profile: CanonMemberProfileDTO
    tags: list[str]


class CanonTemporalDTO(WebModel):
    status: str | None
    since: str | None
    until: str | None


class CanonLoreSectionDTO(WebModel):
    title: str
    statement: str
    category: str | None
    truth_status: bool | None
    sensitivity: Literal["public"]
    canon_level: str | None
    temporal: CanonTemporalDTO
    tags: list[str]


class CanonCharacterSectionDTO(WebModel):
    display_name: str
    aliases: list[str]
    occupation: str | None
    faction_id: str | None
    first_impression: str | None
    combat_role: str | None
    public_reputation: str | None
    tags: list[str]


class CanonRegistrySectionDTO(WebModel):
    name: str
    description: str | None
    status: str | None


class CanonStorySectionDTO(WebModel):
    title: str
    canon_status: str | None
    premise: str
    city_id: str | None
    district_name: str | None
    objective_facts: list[str]


class CanonSectionsDTO(WebModel):
    faction: CanonFactionSectionDTO | None = None
    lore: CanonLoreSectionDTO | None = None
    character: CanonCharacterSectionDTO | None = None
    project: CanonRegistrySectionDTO | None = None
    case: CanonRegistrySectionDTO | None = None
    incident: CanonRegistrySectionDTO | None = None
    story: CanonStorySectionDTO | None = None


class CanonRelationshipDTO(WebModel):
    source_entity_id: str
    target_entity_id: str
    target_entity_type: str
    target_name: str
    relation_type: str
    direction: Literal["outgoing"]
    status: str | None
    description: str | None
    available: bool


class CanonProvenanceDTO(WebModel):
    source_type: str
    references: list[str]


class CanonEntityDetailDTO(WebModel):
    schema_version: Literal["web-canon-entity/0.1"]
    entity_id: str
    entity_type: CanonEntityType
    name: str
    aliases: list[str]
    summary: str
    tags: list[str]
    visibility: Literal["public"]
    sections: CanonSectionsDTO
    relationships: list[CanonRelationshipDTO]
    provenance: list[CanonProvenanceDTO]


__all__ = ["CanonEntityDetailDTO", "CanonEntityListDTO", "CanonEntityType"]
