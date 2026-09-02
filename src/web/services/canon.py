from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from knowledge import KnowledgeResolver
from story import StoryRepository, load_story_repository

from ..mappers.canon import to_canon_detail, to_canon_list
from ..schemas.canon import CanonEntityDetailDTO, CanonEntityListDTO, CanonEntityType

CANON_ENTITY_TYPES: tuple[CanonEntityType, ...] = (
    "faction",
    "lore",
    "character",
    "project",
    "case",
    "incident",
    "story",
)


class CanonEntityNotFoundError(LookupError):
    """Raised when an entity is unavailable to the Web-safe Canon index."""


@dataclass(frozen=True)
class _CanonRecord:
    entity_id: str
    entity_type: CanonEntityType
    data: Mapping[str, Any]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class CanonReadApplication:
    """Read-only Web seam over the existing Canon resolver and story loader."""

    def __init__(
        self,
        resolver: KnowledgeResolver | None = None,
        story_repository: StoryRepository | None = None,
    ) -> None:
        self.resolver = resolver or KnowledgeResolver()
        self.story_repository = story_repository or load_story_repository()
        self._records = self._build_public_index()

    @property
    def entity_types(self) -> list[CanonEntityType]:
        return [
            entity_type
            for entity_type in CANON_ENTITY_TYPES
            if any(record.entity_type == entity_type for record in self._records.values())
        ]

    def list(
        self,
        *,
        query: str | None = None,
        entity_type: CanonEntityType | None = None,
        limit: int = 100,
    ) -> CanonEntityListDTO:
        records = list(self._records.values())
        if entity_type is not None:
            records = [record for record in records if record.entity_type == entity_type]
        if query:
            needle = _text(query).casefold()
            records = [record for record in records if needle in self._search_text(record)]
        records.sort(
            key=lambda record: (CANON_ENTITY_TYPES.index(record.entity_type), record.entity_id)
        )
        summaries = [self._summary(record) for record in records[:limit]]
        return to_canon_list(summaries, self.entity_types)

    def get(self, entity_id: str) -> CanonEntityDetailDTO:
        record = self._records.get(entity_id)
        if record is None:
            raise CanonEntityNotFoundError(entity_id)
        return to_canon_detail(
            record,
            self._summary(record),
            self._relationships(record),
            self._provenance(record),
        )

    def _build_public_index(self) -> dict[str, _CanonRecord]:
        records: dict[str, _CanonRecord] = {}

        def add(entity_type: CanonEntityType, values: Mapping[str, Mapping[str, Any]]) -> None:
            for entity_id, data in values.items():
                records[entity_id] = _CanonRecord(entity_id, entity_type, data)

        add("faction", self.resolver.factions)
        add(
            "lore",
            {
                entity_id: data
                for entity_id, data in self.resolver.lore.items()
                if data.get("sensitivity") == "public"
            },
        )
        add("character", self.resolver.characters)
        add("project", self.resolver.projects)
        add("case", self.resolver.cases)
        add("incident", self.resolver.incidents)
        add("story", self.story_repository.canon)
        return records

    def _summary(self, record: _CanonRecord) -> dict[str, Any]:
        name = self._name(record)
        aliases = self._aliases(record)
        summary = self._summary_text(record)
        tags = self._tags(record)
        return {
            "entity_id": record.entity_id,
            "entity_type": record.entity_type,
            "name": name,
            "aliases": aliases,
            "summary": summary or name,
            "tags": tags,
            "relation_count": len(self._relationships(record)),
            "visibility": "public",
        }

    def _name(self, record: _CanonRecord) -> str:
        data = record.data
        if record.entity_type == "story":
            return _text(data.get("title")) or record.entity_id
        if record.entity_type == "character":
            return _text(data.get("name", {}).get("display_name")) or record.entity_id
        return _text(data.get("name")) or _text(data.get("title")) or record.entity_id

    def _aliases(self, record: _CanonRecord) -> list[str]:
        if record.entity_type == "faction":
            return [item for item in record.data.get("aliases", []) if isinstance(item, str)]
        if record.entity_type == "character":
            name = record.data.get("name", {})
            return [item for item in name.get("aliases", []) if isinstance(item, str)]
        return []

    def _summary_text(self, record: _CanonRecord) -> str:
        data = record.data
        if record.entity_type == "faction":
            return _text(data.get("core_function", {}).get("description"))
        if record.entity_type == "lore":
            return _text(data.get("statement"))
        if record.entity_type == "character":
            hook = data.get("character_hook", {})
            return _text(hook.get("first_impression")) or _text(
                data.get("basic_profile", {}).get("occupation")
            )
        if record.entity_type == "story":
            return _text(data.get("premise"))
        return _text(data.get("description"))

    def _tags(self, record: _CanonRecord) -> list[str]:
        tags = record.data.get("tags", [])
        return [item for item in tags if isinstance(item, str)]

    def _search_text(self, record: _CanonRecord) -> str:
        summary = self._summary(record)
        values = [
            summary["entity_id"],
            summary["entity_type"],
            summary["name"],
            *summary["aliases"],
            summary["summary"],
            *summary["tags"],
        ]
        return " ".join(values).casefold()

    def _relationship(
        self,
        source: _CanonRecord,
        target_id: str,
        target_type: str,
        relation_type: str,
        *,
        status: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        target = self._records.get(target_id)
        return {
            "source_entity_id": source.entity_id,
            "target_entity_id": target_id,
            "target_entity_type": target.entity_type if target else target_type,
            "target_name": self._name(target) if target else target_id,
            "relation_type": relation_type,
            "direction": "outgoing",
            "status": status,
            "description": description,
            "available": target is not None,
        }

    def _relationships(self, record: _CanonRecord) -> list[dict[str, Any]]:
        data = record.data
        relationships: list[dict[str, Any]] = []
        if record.entity_type == "faction":
            for target_id, value in data.get("relationship", {}).items():
                relationships.append(
                    self._relationship(
                        record,
                        target_id,
                        "faction",
                        "relationship",
                        status=_text(value.get("status")),
                        description=_text(value.get("description")),
                    )
                )
        elif record.entity_type == "lore":
            for target_type, target_ids in data.get("related_entities", {}).items():
                normalized_type = target_type[:-1] if target_type.endswith("s") else target_type
                for target_id in target_ids:
                    relationships.append(
                        self._relationship(record, target_id, normalized_type, "related_to")
                    )
        elif record.entity_type == "character":
            faction_id = data.get("identity", {}).get("faction_id")
            if isinstance(faction_id, str):
                relationships.append(self._relationship(record, faction_id, "faction", "member_of"))
        elif record.entity_type == "project":
            self._append_id_relation(
                relationships, record, data.get("faction_id"), "faction", "owned_by"
            )
            self._append_ids_relation(
                relationships, record, data.get("lore_refs"), "lore", "references"
            )
        elif record.entity_type == "case":
            self._append_id_relation(
                relationships, record, data.get("faction_id"), "faction", "owned_by"
            )
            self._append_ids_relation(
                relationships, record, data.get("lore_refs"), "lore", "references"
            )
            self._append_ids_relation(
                relationships, record, data.get("story_refs"), "story", "featured_in"
            )
            self._append_ids_relation(
                relationships, record, data.get("related_incident_ids"), "incident", "related_to"
            )
            self._append_ids_relation(
                relationships, record, data.get("related_project_ids"), "project", "related_to"
            )
        elif record.entity_type == "incident":
            self._append_ids_relation(
                relationships, record, data.get("faction_ids"), "faction", "involves"
            )
            self._append_ids_relation(
                relationships, record, data.get("lore_refs"), "lore", "references"
            )
            self._append_ids_relation(
                relationships, record, data.get("story_refs"), "story", "featured_in"
            )
            self._append_ids_relation(
                relationships, record, data.get("related_case_ids"), "case", "related_to"
            )
        elif record.entity_type == "story":
            self._append_ids_relation(
                relationships, record, data.get("involved_faction_ids"), "faction", "involves"
            )
            self._append_ids_relation(
                relationships, record, data.get("featured_character_ids"), "character", "features"
            )
        return relationships

    def _append_id_relation(
        self,
        target: list[dict[str, Any]],
        source: _CanonRecord,
        target_id: Any,
        target_type: str,
        relation_type: str,
    ) -> None:
        if isinstance(target_id, str):
            target.append(self._relationship(source, target_id, target_type, relation_type))

    def _append_ids_relation(
        self,
        target: list[dict[str, Any]],
        source: _CanonRecord,
        target_ids: Any,
        target_type: str,
        relation_type: str,
    ) -> None:
        if isinstance(target_ids, list):
            target.extend(
                self._relationship(source, target_id, target_type, relation_type)
                for target_id in target_ids
                if isinstance(target_id, str)
            )

    def _provenance(self, record: _CanonRecord) -> list[dict[str, Any]]:
        if record.entity_type == "lore":
            source = record.data.get("source", {})
            references = [
                item
                for item in source.get("references", [])
                if isinstance(item, str) and "knowledge_boundary" not in item
            ]
            return [{"source_type": _text(source.get("type")) or "canon", "references": references}]
        source_types = {
            "faction": "faction_registry",
            "character": "character_registry",
            "project": "project_registry",
            "case": "case_registry",
            "incident": "incident_registry",
            "story": "story_canon",
        }
        return [{"source_type": source_types[record.entity_type], "references": []}]


__all__ = ["CanonEntityNotFoundError", "CanonReadApplication"]
