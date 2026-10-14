"""Deterministic, read-only assembly for the Character Planning Context v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from combat_semantics import CombatRoleProfile

from ..planner.character_plan import CharacterDesignPlan
from ..planner.character_plan_v2 import CharacterDesignPlanV2, project_character_plan_v2
from .schema import (
    CHARACTER_PLANNING_CONTEXT_V2_SCHEMA,
    AcceptanceState,
    CanonContextItem,
    CharacterPlanningContextV2,
    CombatPlanningContext,
    ContextAssemblyLimits,
    ContextAuthority,
    ContextGap,
    ContextGapCode,
    ContextSource,
    CoverageLevel,
    DraftContextItem,
    ReferencePrecedentContext,
    RelationshipContextItem,
    RelationshipVocabularyEntry,
    RosterCharacterContext,
    RosterDesignSignatureV2,
    RosterMembershipStatus,
    RosterMetadataCoverage,
    RosterOverlapEvidence,
    RosterSourceClass,
    StoryContextItem,
    WorldCharacterStatus,
)

_PRODUCTION_RELATIONSHIP_VOCABULARY = (
    ("relationship", (("faction", "faction"),)),
    ("related_to", (("lore", "*"), ("case", "incident"), ("case", "project"), ("incident", "case"))),
    ("member_of", (("character", "faction"),)),
    ("owned_by", (("project", "faction"), ("case", "faction"))),
    ("references", (("project", "lore"), ("case", "lore"), ("incident", "lore"))),
    ("featured_in", (("case", "story"), ("incident", "story"))),
    ("involves", (("incident", "faction"), ("story", "faction"))),
    ("features", (("story", "character"),)),
)


def _value(record: object, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _nested(record: object, *keys: str) -> Any:
    current = record
    for key in keys:
        current = _value(current, key)
        if current is None:
            return None
    return current


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _text_list(*values: object) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            values_iter = (value,)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, str)):
            values_iter = value
        else:
            continue
        for item in values_iter:
            if isinstance(item, str) and item.strip() and item.strip() not in result:
                result.append(item.strip())
    return tuple(result)


def _sorted_records(records: Mapping[str, Any] | Sequence[Any]) -> list[tuple[str, Any]]:
    if isinstance(records, Mapping):
        return sorted(((str(key), value) for key, value in records.items()), key=lambda item: item[0])
    result: list[tuple[str, Any]] = []
    for record in records:
        identifier = _first_text(
            _value(record, "id"),
            _value(record, "reference_id"),
            _value(record, "draft_id"),
            _value(record, "source_id"),
            _value(record, "relation_id"),
        )
        if identifier is not None:
            result.append((identifier, record))
    return sorted(result, key=lambda item: item[0])


def _source(source_id: str, source_type: str, authority: ContextAuthority, reason: str) -> ContextSource:
    return ContextSource(source_id, source_type, authority, reason)


def _canon_item(entity_id: str, record: Any, entity_type: str, reason: str) -> CanonContextItem:
    return CanonContextItem(
        entity_id=entity_id,
        entity_type=entity_type,
        display_name=_first_text(
            _nested(record, "name", "display_name"),
            _value(record, "name"),
            _value(record, "title"),
        ),
        summary=_first_text(_value(record, "summary"), _value(record, "premise"), _value(record, "description")),
        source=_source(entity_id, f"canon_{entity_type}", ContextAuthority.PROJECT_CANON, reason),
    )


def _role_profile(record: Any) -> CombatRoleProfile | None:
    profile = _value(record, "combat_role_profile") or _nested(record, "combat", "combat_role_profile")
    if isinstance(profile, CombatRoleProfile):
        return profile
    if isinstance(profile, Mapping):
        return CombatRoleProfile.from_mapping(profile)
    return None


def _relationship_items(
    records: Sequence[Mapping[str, Any]], authority: ContextAuthority
) -> tuple[RelationshipContextItem, ...]:
    result: list[RelationshipContextItem] = []
    for record in records:
        source_id = _first_text(_value(record, "source_entity_id"), _value(record, "source_id"), _value(record, "source"))
        target_id = _first_text(_value(record, "target_entity_id"), _value(record, "target_id"), _value(record, "target"))
        relation_type = _first_text(_value(record, "relation_type"), _value(record, "type"))
        relation_id = _first_text(_value(record, "relation_id"), _value(record, "id"))
        if source_id and target_id and relation_type and relation_id:
            result.append(
                RelationshipContextItem(
                    relation_id,
                    source_id,
                    target_id,
                    relation_type,
                    authority,
                    _first_text(_value(record, "description"), _value(record, "description_summary")),
                )
            )
    return tuple(result)


def _resolver_relationships(resolver: Any, story_repository: Any | None) -> tuple[RelationshipContextItem, ...]:
    """Reuse the production Canon read projection without changing its Web seam."""

    try:
        from web.services.canon import CanonEntityNotFoundError, CanonReadApplication

        application = CanonReadApplication(resolver=resolver, story_repository=story_repository)
        ids = set()
        for registry_name in ("factions", "lore", "characters", "projects", "cases", "incidents"):
            registry = getattr(resolver, registry_name, {})
            if isinstance(registry, Mapping):
                ids.update(str(item) for item in registry)
        if story_repository is not None and isinstance(getattr(story_repository, "canon", None), Mapping):
            ids.update(str(item) for item in story_repository.canon)
        records: list[Mapping[str, Any]] = []
        for entity_id in sorted(ids):
            try:
                detail = application.get(entity_id)
            except CanonEntityNotFoundError:
                continue
            records.extend(
                {
                    "relation_id": f"{detail.entity_id}:{index}:{relation.relation_type}",
                    "source_entity_id": relation.source_entity_id,
                    "target_entity_id": relation.target_entity_id,
                    "relation_type": relation.relation_type,
                    "description": relation.description,
                }
                for index, relation in enumerate(detail.relationships)
            )
        return _relationship_items(records, ContextAuthority.PROJECT_CANON)
    except (ImportError, AttributeError, KeyError, TypeError, ValueError):
        return ()


def _relationship_vocabulary() -> tuple[RelationshipVocabularyEntry, ...]:
    source = _source(
        "canon-read-relationship-projection",
        "production_canon_relationship_projection",
        ContextAuthority.PROJECT_CANON,
        "existing CanonReadApplication relationship projection",
    )
    return tuple(
        RelationshipVocabularyEntry(
            relation_id=relation_id,
            directionality="DIRECTED",
            inverse_relation_id=None,
            symmetric=None,
            applicable_entity_types=entity_types,
            production_status="PRODUCTION",
            source=source,
        )
        for relation_id, entity_types in _PRODUCTION_RELATIONSHIP_VOCABULARY
    )


def _overlap(signatures: Sequence[RosterDesignSignatureV2]) -> tuple[RosterOverlapEvidence, ...]:
    result: list[RosterOverlapEvidence] = []
    eligible = [item for item in signatures if item.membership_status.value == "IN_PROJECT_ROSTER"]
    for index, left in enumerate(eligible):
        for right in eligible[index + 1 :]:
            dimensions: list[str] = []
            if left.faction_id and left.faction_id == right.faction_id:
                dimensions.append("FACTION_OVERLAP")
            if set(left.combat_roles) & set(right.combat_roles):
                dimensions.append("COMBAT_ROLE_OVERLAP")
            if set(left.personality) & set(right.personality):
                dimensions.append("EXPLICIT_PERSONALITY_OVERLAP")
            if set(left.narrative) & set(right.narrative):
                dimensions.append("EXPLICIT_NARRATIVE_OVERLAP")
            if set(left.visual) & set(right.visual):
                dimensions.append("EXPLICIT_VISUAL_OVERLAP")
            if dimensions:
                result.append(RosterOverlapEvidence(left.character_id, right.character_id, tuple(dimensions)))
    return tuple(result)


def _allowed_project_roster_record(record: Any) -> bool:
    source_class = _value(record, "source_class")
    return source_class not in {
        RosterSourceClass.GENERATED_DRAFT.value,
        RosterSourceClass.REFERENCE_CHARACTER.value,
        RosterSourceClass.TEST_FIXTURE.value,
        RosterSourceClass.BENCHMARK_ONLY.value,
    }


def _roster_item(
    character_id: str,
    record: Any,
    origin: str,
    authority: ContextAuthority,
    *,
    combat_profile: CombatRoleProfile | None = None,
    combat_source: ContextSource | None = None,
) -> RosterCharacterContext:
    profile = _role_profile(record) or combat_profile
    personality = _nested(record, "personality")
    narrative = _nested(record, "basic_profile")
    visual = _nested(record, "phenotype")
    product = _nested(record, "product")
    release = _nested(record, "release")
    story = _nested(record, "story")
    source_class = _value(record, "source_class")
    try:
        source_class = RosterSourceClass(source_class) if source_class is not None else RosterSourceClass.CANON_PROJECT_CHARACTER
    except ValueError:
        source_class = RosterSourceClass.UNKNOWN
    membership = _value(record, "membership_status") or _value(record, "roster_membership_status")
    try:
        membership = RosterMembershipStatus(membership) if membership is not None else (
            RosterMembershipStatus.IN_PROJECT_ROSTER if authority == ContextAuthority.PROJECT_ROSTER else RosterMembershipStatus.UNKNOWN
        )
    except ValueError:
        membership = RosterMembershipStatus.UNKNOWN
    acceptance = _value(record, "acceptance_state")
    try:
        acceptance = AcceptanceState(acceptance) if acceptance is not None else AcceptanceState.ACCEPTANCE_STATE_UNKNOWN
    except ValueError:
        acceptance = AcceptanceState.ACCEPTANCE_STATE_UNKNOWN
    if acceptance is AcceptanceState.ACCEPTED:
        source_class = RosterSourceClass.ACCEPTED_PROJECT_CHARACTER
        membership = RosterMembershipStatus.IN_PROJECT_ROSTER
    world_status = _value(record, "world_status")
    try:
        world_status = WorldCharacterStatus(world_status) if world_status is not None else (
            WorldCharacterStatus.PROJECT_ROSTER_CHARACTER if membership is RosterMembershipStatus.IN_PROJECT_ROSTER else WorldCharacterStatus.PROJECT_WORLD_CHARACTER
        )
    except ValueError:
        world_status = WorldCharacterStatus.UNKNOWN
    item = RosterCharacterContext(
        character_id=character_id,
        display_name=_first_text(_nested(record, "name", "display_name"), _value(record, "name"), _value(record, "display_name")),
        origin=origin,
        source=_source(character_id, "canon_character" if authority == ContextAuthority.PROJECT_CANON else "project_roster", authority, "bounded project roster inventory"),
        source_class=source_class,
        membership_status=membership,
        world_status=world_status,
        acceptance_state=acceptance,
        faction_id=_first_text(_nested(record, "identity", "faction_id"), _value(record, "faction_id")),
        combat_role_profile=profile,
        combat_source=combat_source or (_source(character_id, "explicit_combat_evidence", ContextAuthority.DETERMINISTIC_SEMANTICS, "explicit combat profile evidence") if profile is not None else None),
        personality=_text_list(_nested(personality, "surface_traits"), _nested(personality, "underlying_traits"), _nested(personality, "values")),
        narrative=_text_list(_value(narrative, "occupation"), _value(record, "summary"), _value(record, "narrative")),
        visual=_text_list(_nested(visual, "visible_traits"), _value(record, "visual_tags")),
        product=_text_list(_value(product, "roster_role"), _value(product, "availability")),
        release=_text_list(_value(release, "version"), _value(release, "date")),
        story_status=_text_list(_value(story, "status"), _value(record, "story_status")),
    )
    return replace(
        item,
        signature=RosterDesignSignatureV2(
            character_id=character_id,
            source_class=item.source_class,
            membership_status=item.membership_status,
            faction_id=item.faction_id,
            combat_roles=(
                tuple(
                    role
                    for role in (
                        item.combat_role_profile.primary_role if item.combat_role_profile else None,
                        *(item.combat_role_profile.secondary_roles if item.combat_role_profile else ()),
                    )
                    if role is not None
                )
            ),
            personality=item.personality,
            narrative=item.narrative,
            visual=item.visual,
        ),
    )


def _coverage(items: Sequence[RosterCharacterContext]) -> RosterMetadataCoverage:
    if not items:
        return RosterMetadataCoverage()

    def level(values: Sequence[object], *, identity: bool = False) -> CoverageLevel:
        count = sum(bool(value) for value in values)
        if count == len(values):
            return CoverageLevel.GOOD
        if count >= max(1, len(values) // 2):
            return CoverageLevel.PARTIAL
        if count:
            return CoverageLevel.SPARSE
        return CoverageLevel.ABSENT

    return RosterMetadataCoverage(
        identity=level([item.display_name for item in items]),
        membership=level([item.membership_status is not RosterMembershipStatus.UNKNOWN for item in items]),
        faction=level([item.faction_id for item in items]),
        combat=level([item.combat_role_profile for item in items]),
        relationships=CoverageLevel.ABSENT,
        personality=level([item.personality for item in items]),
        narrative=level([item.narrative for item in items]),
        visual=level([item.visual for item in items]),
        product=level([item.product for item in items]),
        release=level([item.release for item in items]),
        story_status=level([item.story_status for item in items]),
    )


def _references(
    records: Sequence[Any], limit: int, selector_metadata: Sequence[str]
) -> tuple[ReferencePrecedentContext, ...]:
    result: list[ReferencePrecedentContext] = []
    for reference_id, record in _sorted_records(records)[:limit]:
        facts = _value(record, "facts", record)
        identity = _value(facts, "identity", facts)
        names = _value(identity, "names", identity)
        narrative = _value(facts, "narrative", facts)
        presentation = _value(facts, "presentation", facts)
        analysis = _value(record, "analysis")
        provenance = _value(record, "provenance")
        source_ids = tuple(
            source_id
            for source_id, _ in _sorted_records(_value(provenance, "sources", ()))
        )
        result.append(
            ReferencePrecedentContext(
                reference_id=reference_id,
                display_name=_first_text(_value(names, "canonical"), _value(identity, "name")),
                game_id=_first_text(_value(identity, "game_id")),
                roles=_text_list(_value(analysis, "combat_roles"), _value(analysis, "normalized_roles")),
                narrative=_text_list(_value(narrative, "faction"), _value(narrative, "occupation"), _value(narrative, "affiliations")),
                visual=_text_list(_value(presentation, "official_visual_tags"), _value(presentation, "official_character_keywords")),
                source=_source(reference_id, "reference_corpus_character", ContextAuthority.REFERENCE_PRECEDENT, "precedent-only selector output"),
                source_ids=source_ids,
                selector_metadata=tuple(selector_metadata),
            )
        )
    return tuple(result)


def _story_items(records: Mapping[str, Any] | Sequence[Any], limit: int) -> tuple[StoryContextItem, ...]:
    result: list[StoryContextItem] = []
    for story_id, record in _sorted_records(records)[:limit]:
        result.append(
            StoryContextItem(
                story_id=story_id,
                title=_first_text(_value(record, "title")),
                facts=_text_list(_value(record, "premise"), _value(record, "objective_facts"), _value(record, "exclusions")),
                source=_source(story_id, "story_canon", ContextAuthority.PROJECT_CANON, "current story Canon record"),
            )
        )
    return tuple(result)


def assemble_character_planning_context_v2(
    plan: CharacterDesignPlan,
    *,
    request: Mapping[str, Any] | None = None,
    plan_v2: CharacterDesignPlanV2 | None = None,
    resolver: Any | None = None,
    canon_records: Mapping[str, Any] | None = None,
    project_roster_records: Sequence[Mapping[str, Any]] = (),
    combat_role_profiles: Mapping[str, CombatRoleProfile | Mapping[str, Any]] | None = None,
    relationships: Sequence[Mapping[str, Any]] = (),
    reference_relationships: Sequence[Mapping[str, Any]] = (),
    draft_relationships: Sequence[Mapping[str, Any]] = (),
    evaluation_relationships: Sequence[Mapping[str, Any]] = (),
    relationship_vocabulary: Sequence[str] = (),
    reference_records: Sequence[Any] = (),
    reference_repository: Any | None = None,
    reference_selector_metadata: Sequence[str] = (),
    story_records: Mapping[str, Any] | Sequence[Any] = (),
    story_repository: Any | None = None,
    drafts: Sequence[Mapping[str, Any]] = (),
    limits: ContextAssemblyLimits | None = None,
    snapshot_id: str | None = None,
) -> CharacterPlanningContextV2:
    """Assemble existing evidence only; this function performs no retrieval or writes."""

    if not isinstance(plan, CharacterDesignPlan):
        raise TypeError("plan must be a CharacterDesignPlan")
    limits = limits or ContextAssemblyLimits()
    projected = plan_v2 or project_character_plan_v2(plan, request=request)

    if canon_records is None and resolver is not None:
        canon_records = {}
        for registry_name in ("characters", "factions", "lore", "projects", "cases", "incidents"):
            registry = getattr(resolver, registry_name, {})
            if isinstance(registry, Mapping):
                canon_records.update({str(key): value for key, value in registry.items()})
    canon_records = canon_records or {}
    canon = tuple(
        _canon_item(key, record, "record", "existing resolver/adapter evidence")
        for key, record in _sorted_records(canon_records)[: limits.max_canon_items]
    )

    roster_records: list[tuple[str, Any]] = []
    if resolver is not None and isinstance(getattr(resolver, "characters", None), Mapping):
        roster_records.extend(_sorted_records(resolver.characters))
    roster_records.extend(
        item for item in _sorted_records(project_roster_records) if _allowed_project_roster_record(item[1])
    )
    combat_role_profiles = combat_role_profiles or {}

    def combat_for(character_id: str) -> tuple[CombatRoleProfile | None, ContextSource | None]:
        value = combat_role_profiles.get(character_id)
        if isinstance(value, CombatRoleProfile):
            profile = value
        elif isinstance(value, Mapping):
            profile = CombatRoleProfile.from_mapping(value)
        else:
            return None, None
        return profile, _source(
            character_id,
            "explicit_project_combat_profile",
            ContextAuthority.DETERMINISTIC_SEMANTICS,
            "explicit combat-role evidence supplied to the planning bridge",
        )

    roster = tuple(
        _roster_item(
            key,
            record,
            "PROJECT_CANON" if resolver is not None else "PROJECT_ROSTER",
            ContextAuthority.PROJECT_CANON if resolver is not None else ContextAuthority.PROJECT_ROSTER,
            combat_profile=combat_for(key)[0],
            combat_source=combat_for(key)[1],
        )
        for key, record in roster_records[: limits.max_roster_items]
    )

    canon_relationships = _relationship_items(
        relationships[: limits.max_relationships], ContextAuthority.PROJECT_CANON
    ) if relationships else _resolver_relationships(resolver, story_repository)[: limits.max_relationships]
    reference_relationship_items = _relationship_items(
        reference_relationships[: limits.max_relationships], ContextAuthority.REFERENCE_PRECEDENT
    )
    draft_relationship_items = _relationship_items(
        draft_relationships[: limits.max_relationships], ContextAuthority.GENERATED_DRAFT
    )
    evaluation_relationship_items = _relationship_items(
        evaluation_relationships[: limits.max_relationships], ContextAuthority.EXPERIMENTAL
    )

    requested = tuple(item.target for item in projected.relationship_strategy.requested_relationships)
    known_ids = {item.entity_id for item in canon} | {item.character_id for item in roster}
    unresolved = tuple(target for target in requested if target not in known_ids)

    if not reference_records and reference_repository is not None:
        reference_records = tuple(reference_repository.list_all())
    references = _references(reference_records, limits.max_references, reference_selector_metadata)

    if not story_records and story_repository is not None:
        story_records = getattr(story_repository, "canon", {})
    story = _story_items(story_records, limits.max_story_items)

    draft_items = tuple(
        DraftContextItem(
            draft_id=key,
            display_name=_first_text(_value(record, "display_name"), _nested(record, "name", "display_name"), _value(record, "name")),
            source=_source(key, "generated_draft", ContextAuthority.GENERATED_DRAFT, "explicit draft evidence; excluded from roster"),
        )
        for key, record in _sorted_records(drafts)[: limits.max_drafts]
    )

    gaps: list[ContextGap] = []
    if not canon:
        gaps.append(ContextGap(ContextGapCode.CANON_CONTEXT_UNAVAILABLE, "canon", "No bounded authoritative Canon records were supplied."))
    if not roster:
        gaps.append(ContextGap(ContextGapCode.ROSTER_CONTEXT_UNAVAILABLE, "roster", "No project Canon/roster records were supplied."))
    if not canon_relationships:
        gaps.append(ContextGap(ContextGapCode.RELATIONSHIP_CONTEXT_UNAVAILABLE, "relationships", "No authoritative relationship facts were supplied."))
    if unresolved:
        gaps.append(ContextGap(ContextGapCode.RELATIONSHIP_COVERAGE_INCOMPLETE, "relationships", f"Requested targets remain ungrounded: {', '.join(unresolved)}."))
    vocabulary = _relationship_vocabulary()
    if not story:
        gaps.append(ContextGap(ContextGapCode.STORY_CONTEXT_UNAVAILABLE, "story", "No current story Canon records were supplied."))
    if not references:
        gaps.append(ContextGap(ContextGapCode.REFERENCE_CONTEXT_UNAVAILABLE, "references", "No precedent-only Reference Corpus records were supplied."))
    coverage = _coverage(roster)
    if canon_relationships and roster:
        related_roster_ids = {
            item.character_id
            for item in roster
            if any(
                relation.source_id == item.character_id or relation.target_id == item.character_id
                for relation in canon_relationships
            )
        }
        relationship_level = (
            CoverageLevel.GOOD
            if len(related_roster_ids) == len(roster)
            else CoverageLevel.PARTIAL
            if related_roster_ids
            else CoverageLevel.SPARSE
        )
        coverage = replace(coverage, relationships=relationship_level)
    if coverage.product in {CoverageLevel.ABSENT, CoverageLevel.SPARSE}:
        gaps.append(ContextGap(ContextGapCode.PRODUCT_POSITIONING_UNAVAILABLE, "roster", "Product/release positioning is not authoritative in the current roster records."))
    if coverage.combat in {CoverageLevel.ABSENT, CoverageLevel.SPARSE}:
        gaps.append(ContextGap(ContextGapCode.ROSTER_COMBAT_COVERAGE_INCOMPLETE, "roster", "No explicit combat-role evidence covers the current roster entries."))
    if coverage.story_status in {CoverageLevel.ABSENT, CoverageLevel.SPARSE}:
        gaps.append(ContextGap(ContextGapCode.ROSTER_STORY_STATUS_UNAVAILABLE, "roster", "No structured current-story status covers the current roster entries."))
    if coverage.visual in {CoverageLevel.ABSENT, CoverageLevel.SPARSE}:
        gaps.append(ContextGap(ContextGapCode.ROSTER_METADATA_SPARSE, "roster", "Visual roster metadata is sparse or absent."))
    if roster and coverage.membership is not CoverageLevel.GOOD:
        gaps.append(ContextGap(ContextGapCode.ROSTER_MEMBERSHIP_PARTIALLY_KNOWN, "roster", "World-character records do not establish playable or accepted roster membership."))
    if not any(item.acceptance_state is AcceptanceState.ACCEPTED for item in roster):
        gaps.append(ContextGap(ContextGapCode.HUMAN_ACCEPTANCE_STATE_UNAVAILABLE, "roster", "No auditable human acceptance state is present."))

    requested_profile = projected.gameplay_identity.combat_role_profile or plan.combat_role_profile
    if requested_profile is not None and requested_profile.is_unspecified:
        requested_profile = None
    combat = CombatPlanningContext(
        requested_role_profile=requested_profile,
        semantic_metadata=tuple(plan.selected_patterns),
    )
    identity = snapshot_id
    if identity is None:
        fingerprint = {
            "request_id": projected.request_id,
            "plan_v2": projected.to_dict(),
            "canon": [item.entity_id for item in canon],
            "roster": [item.character_id for item in roster],
            "relationships": [item.relation_id for item in canon_relationships],
            "references": [item.reference_id for item in references],
            "story": [item.story_id for item in story],
        }
        encoded = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        identity = f"planning-context-v2:{hashlib.sha256(encoded).hexdigest()[:16]}"

    return CharacterPlanningContextV2(
        schema_version=CHARACTER_PLANNING_CONTEXT_V2_SCHEMA,
        snapshot_id=identity,
        intent=plan.parsed_intent,
        plan_v1=plan,
        plan_v2=projected,
        canon=canon,
        roster=roster,
        drafts=draft_items,
        canon_relationships=tuple(canon_relationships),
        reference_relationships=reference_relationship_items,
        draft_relationships=draft_relationship_items,
        evaluation_relationships=evaluation_relationship_items,
        requested_relationships=requested,
        unresolved_relationships=unresolved,
        relationship_vocabulary=vocabulary,
        combat=combat,
        references=references,
        story=story,
        gaps=tuple(gaps),
        roster_coverage=coverage,
        roster_signatures=tuple(item.signature for item in roster if item.signature is not None),
        overlap_evidence=_overlap(tuple(item.signature for item in roster if item.signature is not None)),
        limits=limits,
    )
