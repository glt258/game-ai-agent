"""Diagnostic-only authoring feature vocabulary and provenance helpers.

This module deliberately sits beside the frozen selector.  It normalizes a
small, explicit vocabulary for authoring diagnostics, but it never contributes
to reference selection scores.  Unknown values remain absent rather than
being forced into a category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from .provenance import resolve_fact_field_path


FEATURE_VOCABULARY_VERSION = "reference-feature-vocabulary/0.4.1c"

FeatureDomain = Literal[
    "personality",
    "gameplay_fantasy",
    "life_social_identity",
    "life_stage",
    "authority",
    "hook_surface",
    "hook_contrast",
    "hook_behavioral_pattern",
    "visual_behavioral_motif",
]
ProvenanceKind = Literal["brief", "source_fact", "analyst_derivation"]
SupportStatus = Literal[
    "direct_normalization",
    "derived_from_fact",
    "analysis_only",
    "evidence_unavailable",
]


def _canonical_map(**entries: tuple[str, ...]) -> Mapping[str, tuple[str, ...]]:
    return {key: tuple(value) for key, value in entries.items()}


# These are intentionally small.  Terms such as ``aggressive``, ``member``,
# ``smart``, ``young``, and ``support`` are ambiguous outside an explicit
# phrase and are therefore either scoped to a domain or left unmapped.
VOCABULARY: Mapping[FeatureDomain, Mapping[str, tuple[str, ...]]] = {
    "personality": _canonical_map(
        restrained=("restrained", "quiet", "reserved", "克制", "安静"),
        expressive=("expressive", "flamboyant", "showperson", "表现力强", "张扬"),
        practical=("practical", "pragmatic", "务实"),
        idealistic=("idealistic", "理想主义"),
        guarded=("guarded", "防备"),
        warm=("warm", "socially warm", "亲和"),
        confrontational=("confrontational", "对抗性"),
        conciliatory=("conciliatory", "调和"),
        disciplined=("disciplined", "自律"),
        impulsive=("impulsive", "冲动"),
        playful=("playful", "顽皮"),
        serious=("serious", "严肃"),
        socially_embedded=("socially embedded", "community embedded", "嵌入社区"),
        socially_isolated=("socially isolated", "socially detached", "社会孤立"),
    ),
    "gameplay_fantasy": _canonical_map(
        direct_frontline_pressure=(
            "direct frontline pressure",
            "frontline",
            "direct combat",
            "on_field_dps",
            "前线压制",
        ),
        protective_stabilization=(
            "protective stabilization",
            "protective",
            "protection",
            "defensive",
            "healing",
            "healer",
            "shielding",
            "stabilization",
            "防护",
            "稳定",
        ),
        team_enabling=(
            "team enabling",
            "team enablement",
            "team_fed",
            "team buff",
            "团队赋能",
        ),
        battlefield_control=(
            "battlefield control",
            "spatial control",
            "crowd control",
            "area control",
            "control",
            "战场控制",
        ),
        mobility_repositioning=(
            "mobility repositioning",
            "mobility",
            "repositioning",
            "机动",
            "重新定位",
        ),
        information_investigation=(
            "information investigation",
            "information gathering",
            "investigation",
            "investigator",
            "fact checker",
            "information",
            "信息调查",
        ),
        routing_coordination=(
            "routing coordination",
            "crowd routing",
            "route planner",
            "coordination",
            "routing",
            "路径协调",
        ),
        setup_payoff=(
            "setup payoff",
            "setup and payoff",
            "build and spend",
            "setup",
            "payoff",
            "铺垫回收",
        ),
        reactive_support=(
            "reactive support",
            "reactive",
            "support healer",
            "支援反应",
        ),
    ),
    "life_social_identity": _canonical_map(
        formal_professional=(
            "formal professional",
            "professional",
            "magistrate",
            "researcher",
            "正式职业",
        ),
        ordinary_urban_worker=(
            "ordinary urban worker",
            "ordinary worker",
            "urban worker",
            "repair shop",
            "普通都市劳动者",
        ),
        informal_worker=("informal worker", "informal work", "非正式劳动者"),
        independent_operator=(
            "independent operator",
            "independent",
            "works alone",
            "独立行动者",
        ),
        performer=(
            "performer",
            "stage performer",
            "public performer",
            "stage identity",
            "演出者",
        ),
        investigator=(
            "field investigator",
            "investigator",
            "criminal investigation",
            "调查者",
        ),
        organization_member=(
            "organization member",
            "faction member",
            "team member",
            "机构成员",
        ),
        community_embedded_local=(
            "community embedded local",
            "community social role",
            "community",
            "neighbor",
            "local",
            "社区邻里",
        ),
        itinerant_traveler=(
            "itinerant traveler",
            "traveler",
            "courier",
            "旅居者",
        ),
        non_career_identity=(
            "non career identity",
            "non professional",
            "ordinary neighbor",
            "非职业身份",
        ),
    ),
    "life_stage": _canonical_map(
        youthful_presentation=("youthful presentation", "youthful", "年轻呈现"),
        mature_presentation=("mature presentation", "mature", "成熟呈现"),
        older_presentation=("older presentation", "older", "年长呈现"),
        age_ambiguous=(
            "age ambiguous",
            "age-ambiguous",
            "age unspecified",
            "age unknown",
            "年龄模糊",
        ),
        unspecified=("life stage unspecified", "life-stage unspecified", "阶段未说明"),
    ),
    "authority": _canonical_map(
        low_formal_authority=(
            "low formal authority",
            "limited authority",
            "low authority",
            "有限正式权力",
        ),
        ordinary_member=("ordinary member", "普通成员"),
        independent=("independent authority", "independent operator", "独立"),
        operational_responsibility=(
            "operational responsibility",
            "field responsibility",
            "operations responsibility",
            "运营职责",
        ),
        public_social_influence=(
            "public social influence",
            "social influence",
            "influential without office",
            "社会影响力",
        ),
        formal_leadership=(
            "formal leadership",
            "formal leader",
            "governing official",
            "magistrate",
            "正式领导",
        ),
    ),
    "hook_surface": _canonical_map(
        public_performance=("public performance", "public performer", "stage identity", "公开演出"),
        ordinary_work_identity=("ordinary work identity", "ordinary urban worker", "repair shop"),
        formal_role_identity=("formal role identity", "governing official", "magistrate"),
        organization_member_identity=("organization member identity", "faction member"),
    ),
    "hook_contrast": _canonical_map(
        formal_role_personal_action=(
            "formal role personal action",
            "official who fights in person",
            "governing official with personal combat presence",
            "正式身份亲自行动",
        ),
        charisma_without_office=(
            "charisma without office",
            "influential without office",
            "无正式职位的影响力",
        ),
        competence_without_spectacle=(
            "competence without spectacle",
            "low spectacle daily identity",
            "低调日常身份",
        ),
    ),
    "hook_behavioral_pattern": _canonical_map(
        public_performance=("public performance", "stage performer", "public-facing creative"),
        low_spectacle_routine=("low spectacle routine", "low-spectacle daily identity"),
        restraint_for_payoff=("restraint for payoff", "patience stance", "克制后回收"),
        routine_problem_solving=("routine problem solving", "patient problem solving", "日常解决问题"),
    ),
    "visual_behavioral_motif": _canonical_map(
        signature_object=("signature object", "标志性物件"),
        repeated_gesture=("repeated gesture", "recurring gesture", "重复手势"),
        occupational_tool=("occupational tool", "work tool", "职业工具"),
        performance_behavior=("performance behavior", "stage behavior", "演出行为"),
        recurring_spatial_behavior=(
            "recurring spatial behavior",
            "spatial routine",
            "recurring route",
            "空间行为",
        ),
    ),
}


@dataclass(frozen=True)
class FeatureEvidence:
    """Explain where one canonical diagnostic feature came from."""

    domain: FeatureDomain
    canonical_token: str
    provenance_kind: ProvenanceKind
    source_path: str | None = None
    source_ids: tuple[str, ...] = ()
    raw_value: str | None = None
    support_status: SupportStatus = "evidence_unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "canonical_token": self.canonical_token,
            "provenance_kind": self.provenance_kind,
            "source_path": self.source_path,
            "source_ids": list(self.source_ids),
            "raw_value": self.raw_value,
            "support_status": self.support_status,
        }


@dataclass(frozen=True)
class HookFeatures:
    surface_traits: tuple[str, ...] = ()
    contrast_traits: tuple[str, ...] = ()
    behavioral_patterns: tuple[str, ...] = ()

    def any(self) -> bool:
        return bool(self.surface_traits or self.contrast_traits or self.behavioral_patterns)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "surface_traits": list(self.surface_traits),
            "contrast_traits": list(self.contrast_traits),
            "behavioral_patterns": list(self.behavioral_patterns),
        }


@dataclass(frozen=True)
class DiagnosticFeatureProfile:
    personality: tuple[str, ...] = ()
    gameplay_fantasy: tuple[str, ...] = ()
    life_social_identity: tuple[str, ...] = ()
    life_stage: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()
    hook: HookFeatures = HookFeatures()
    visual_behavioral_motifs: tuple[str, ...] = ()
    evidence: tuple[FeatureEvidence, ...] = ()

    def domain_values(self, domain: FeatureDomain) -> tuple[str, ...]:
        if domain == "hook_surface":
            return self.hook.surface_traits
        if domain == "hook_contrast":
            return self.hook.contrast_traits
        if domain == "hook_behavioral_pattern":
            return self.hook.behavioral_patterns
        if domain == "visual_behavioral_motif":
            return self.visual_behavioral_motifs
        return tuple(getattr(self, domain))

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "vocabulary_version": FEATURE_VOCABULARY_VERSION,
            "personality": list(self.personality),
            "gameplay_fantasy": list(self.gameplay_fantasy),
            "life_social_identity": list(self.life_social_identity),
            "life_stage": list(self.life_stage),
            "authority": list(self.authority),
            "hook": self.hook.to_dict(),
            "visual_behavioral_motifs": list(self.visual_behavioral_motifs),
        }
        if include_evidence:
            result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


def _phrase_text(value: str) -> str:
    value = value.lower().replace("_", " ").replace("-", " ")
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _contains_alias(text: str, alias: str) -> bool:
    haystack = _phrase_text(text)
    needle = _phrase_text(alias)
    if not haystack or not needle:
        return False
    if re.search(r"[a-z0-9]", needle):
        return f" {needle} " in f" {haystack} "
    return needle in haystack


def canonical_tokens(domain: FeatureDomain) -> tuple[str, ...]:
    return tuple(VOCABULARY[domain])


def normalize_values(
    domain: FeatureDomain,
    values: Sequence[str],
    *,
    provenance_kind: ProvenanceKind,
    source_path: str | None = None,
    source_ids: Sequence[str] = (),
) -> tuple[tuple[str, ...], tuple[FeatureEvidence, ...]]:
    """Normalize explicit values into bounded tokens with evidence entries."""

    found: list[str] = []
    evidence: list[FeatureEvidence] = []
    clean_source_ids = tuple(sorted(set(str(item) for item in source_ids)))
    for raw_value in values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        for canonical, aliases in VOCABULARY[domain].items():
            if canonical in found:
                continue
            if any(_contains_alias(raw_value, alias) for alias in aliases):
                found.append(canonical)
                status: SupportStatus
                if provenance_kind == "brief":
                    status = "direct_normalization"
                elif provenance_kind == "source_fact":
                    status = "direct_normalization" if clean_source_ids else "evidence_unavailable"
                else:
                    status = "derived_from_fact" if clean_source_ids else "analysis_only"
                evidence.append(
                    FeatureEvidence(
                        domain=domain,
                        canonical_token=canonical,
                        provenance_kind=provenance_kind,
                        source_path=source_path,
                        source_ids=clean_source_ids,
                        raw_value=raw_value,
                        support_status=status,
                    )
                )
    return tuple(found), tuple(evidence)


def _profile_from_parts(
    values_by_domain: Mapping[FeatureDomain, Sequence[tuple[Sequence[str], str | None, ProvenanceKind, Sequence[str]]]],
) -> DiagnosticFeatureProfile:
    values: dict[str, tuple[str, ...]] = {}
    evidence: list[FeatureEvidence] = []
    for domain, parts in values_by_domain.items():
        found: list[str] = []
        for raw_values, source_path, provenance_kind, source_ids in parts:
            normalized, entries = normalize_values(
                domain,
                raw_values,
                provenance_kind=provenance_kind,
                source_path=source_path,
                source_ids=source_ids,
            )
            for item in normalized:
                if item not in found:
                    found.append(item)
            evidence.extend(entries)
        values[domain] = tuple(found)
    return DiagnosticFeatureProfile(
        personality=values.get("personality", ()),
        gameplay_fantasy=values.get("gameplay_fantasy", ()),
        life_social_identity=values.get("life_social_identity", ()),
        life_stage=values.get("life_stage", ()),
        authority=values.get("authority", ()),
        hook=HookFeatures(
            surface_traits=values.get("hook_surface", ()),
            contrast_traits=values.get("hook_contrast", ()),
            behavioral_patterns=values.get("hook_behavioral_pattern", ()),
        ),
        visual_behavioral_motifs=values.get("visual_behavioral_motif", ()),
        evidence=tuple(evidence),
    )


def extract_brief_features(brief: str) -> DiagnosticFeatureProfile:
    """Extract only explicit, bounded authoring terms from an author brief."""

    if not isinstance(brief, str):
        raise TypeError("brief must be a string")
    domains: dict[FeatureDomain, Sequence[tuple[Sequence[str], str | None, ProvenanceKind, Sequence[str]]]] = {
        domain: [((brief,), "brief", "brief", ())] for domain in VOCABULARY
    }
    return _profile_from_parts(domains)


def _field_sources(reference: Any, path: str) -> tuple[str, ...]:
    evidence = getattr(reference.provenance, "field_evidence", {}) or {}
    return tuple(sorted(set(str(item) for item in evidence.get(path, ()))))


def _authoring_feature_sources(block: Any, feature_path: str) -> tuple[str, ...]:
    entries = getattr(block, "evidence", {}).get(feature_path, ())
    return tuple(
        sorted(
            {
                str(entry.source_id)
                for entry in entries
                if getattr(entry, "kind", None) == "source_fact"
                and getattr(entry, "source_id", None)
            }
        )
    )


def reference_feature_profile(reference: Any) -> DiagnosticFeatureProfile:
    """Normalize corpus facts and analysis into diagnostic features.

    The function never mutates the reference or replaces original analysis
    prose.  Analysis values are explicitly marked as analyst derivations;
    missing field-level evidence is represented as ``analysis_only`` rather
    than being upgraded to a fact claim.
    """

    facts = reference.facts
    narrative = facts.narrative
    presentation = facts.presentation
    analysis = reference.analysis
    parts: dict[FeatureDomain, list[tuple[Sequence[str], str | None, ProvenanceKind, Sequence[str]]]] = {
        domain: [] for domain in VOCABULARY
    }

    if analysis is not None:
        character = analysis.character_design
        combat = analysis.combat_design
        product = analysis.product_design
        authoring = getattr(character, "authoring_features", None)
        if authoring is not None:
            for domain, attribute in (
                ("personality", "personality"),
                ("gameplay_fantasy", "gameplay_fantasy"),
                ("life_social_identity", "life_social_identity"),
                ("life_stage", "life_stage"),
                ("authority", "authority"),
                ("visual_behavioral_motif", "visual_behavioral_motifs"),
            ):
                values = getattr(authoring, attribute)
                parts[domain].append(
                    (
                        values,
                        f"analysis.character_design.authoring_features.{attribute}",
                        "analyst_derivation",
                        _authoring_feature_sources(authoring, attribute),
                    )
                )
            if authoring.hook is not None:
                for domain, attribute in (
                    ("hook_surface", "surface_traits"),
                    ("hook_contrast", "contrast_traits"),
                    ("hook_behavioral_pattern", "behavioral_patterns"),
                ):
                    parts[domain].append(
                        (
                            getattr(authoring.hook, attribute),
                            f"analysis.character_design.authoring_features.hook.{attribute}",
                            "analyst_derivation",
                            _authoring_feature_sources(authoring, f"hook.{attribute}"),
                        )
                    )
        parts["personality"].append(
            ((tuple(character.personality_archetypes)), "analysis.character_design.personality_archetypes", "analyst_derivation", ())
        )
        fantasy_values = [
            character.character_fantasy or "",
            *combat.normalized_roles,
            *combat.archetypes,
            *product.gameplay_hooks,
        ]
        parts["gameplay_fantasy"].append(
            (fantasy_values, "analysis.character_design/combat_design/product_design", "analyst_derivation", ())
        )
        hook_values = [
            *character.identity_hooks,
            *character.narrative_hooks,
            *product.gameplay_hooks,
            *product.narrative_hooks,
        ]
        parts["hook_surface"].append(
            (hook_values, "analysis.character_design/product_design.*_hooks", "analyst_derivation", ())
        )
        parts["hook_contrast"].append(
            (hook_values, "analysis.character_design/product_design.*_hooks", "analyst_derivation", ())
        )
        parts["hook_behavioral_pattern"].append(
            (hook_values + [character.character_fantasy or ""], "analysis.character_design/product_design", "analyst_derivation", ())
        )
        parts["visual_behavioral_motif"].append(
            ([*character.visual_motifs, *product.visual_hooks], "analysis.character_design/product_design", "analyst_derivation", ())
        )

    if narrative is not None:
        narrative_values = [
            narrative.occupation or "",
            narrative.faction or "",
            narrative.public_identity or "",
        ]
        fact_paths = ("narrative.occupation", "narrative.faction", "narrative.public_identity")
        for domain in ("life_social_identity", "authority"):
            for value, path in zip(narrative_values, fact_paths):
                parts[domain].append(((value,), f"facts.{path}", "source_fact", _field_sources(reference, path)))

    if presentation is not None:
        presentation_values = [
            *presentation.official_visual_tags,
            *presentation.official_character_keywords,
        ]
        parts["visual_behavioral_motif"].append(
            (presentation_values, "facts.presentation.official_visual_tags/official_character_keywords", "source_fact", ())
        )

    # Life-stage is intentionally empty until an explicit presentation field
    # exists.  Occupation, combat role, rarity, and playability are not age
    # evidence.  Authority receives only explicit office/authority language
    # from narrative facts; combat competence is never consulted.
    return _profile_from_parts(parts)


def diagnostic_overlap(
    brief: DiagnosticFeatureProfile,
    reference: DiagnosticFeatureProfile,
) -> dict[str, Any]:
    """Return explainable feature overlap; this is never a selector score."""

    domains: dict[str, dict[str, list[str]]] = {}
    for domain in (
        "personality",
        "gameplay_fantasy",
        "life_social_identity",
        "life_stage",
        "authority",
        "hook_surface",
        "hook_contrast",
        "hook_behavioral_pattern",
        "visual_behavioral_motif",
    ):
        left = set(brief.domain_values(domain))
        right = set(reference.domain_values(domain))
        domains[domain] = {
            "brief": sorted(left),
            "reference": sorted(right),
            "shared": sorted(left & right),
        }
    return domains


def validate_feature_provenance(
    profile: DiagnosticFeatureProfile,
    *,
    reference: Any | None = None,
) -> None:
    """Validate source IDs and fact paths when corpus context is available."""

    known_source_ids: set[str] = set()
    facts = None
    if reference is not None:
        known_source_ids = {
            str(item.source_id) for item in reference.provenance.sources
        }
        facts = reference.facts
    for item in profile.evidence:
        unknown = set(item.source_ids) - known_source_ids
        if unknown:
            raise ValueError(
                f"unknown feature provenance source ID(s): {sorted(unknown)}"
            )
        if item.provenance_kind == "source_fact":
            if not item.source_path or not item.source_path.startswith("facts."):
                raise ValueError("source_fact evidence requires a facts.* source_path")
            if facts is not None:
                resolve_fact_field_path(facts, item.source_path.removeprefix("facts."))
        elif item.provenance_kind == "analyst_derivation":
            if item.source_path and not item.source_path.startswith("analysis."):
                # A future evidence-backed analysis feature may point to facts;
                # it must then be labeled derived_from_fact by its source IDs.
                if not item.source_ids:
                    raise ValueError(
                        "unattributed analyst derivation must use an analysis.* source_path"
                    )


def feature_coverage(
    brief_profiles: Sequence[DiagnosticFeatureProfile],
    reference_profiles: Sequence[DiagnosticFeatureProfile],
) -> dict[str, Any]:
    """Summarize vocabulary coverage without collapsing it into one score."""

    domains: dict[str, dict[str, Any]] = {}
    domain_names = (
        "personality",
        "gameplay_fantasy",
        "life_social_identity",
        "life_stage",
        "authority",
        "hook_surface",
        "hook_contrast",
        "hook_behavioral_pattern",
        "visual_behavioral_motif",
    )
    for domain in domain_names:
        brief_with = sum(bool(profile.domain_values(domain)) for profile in brief_profiles)
        references_with = sum(bool(profile.domain_values(domain)) for profile in reference_profiles)
        shared_cases = sum(
            any(
                set(brief.domain_values(domain)) & set(reference.domain_values(domain))
                for reference in reference_profiles
            )
            for brief in brief_profiles
        )
        domains[domain] = {
            "brief_count": brief_with,
            "brief_total": len(brief_profiles),
            "brief_percent": round(100 * brief_with / len(brief_profiles), 2) if brief_profiles else 0.0,
            "reference_count": references_with,
            "reference_total": len(reference_profiles),
            "reference_percent": round(100 * references_with / len(reference_profiles), 2) if reference_profiles else 0.0,
            "cases_with_shared_feature_count": shared_cases,
            "cases_with_shared_feature_percent": round(100 * shared_cases / len(brief_profiles), 2) if brief_profiles else 0.0,
        }
    return {
        "vocabulary_version": FEATURE_VOCABULARY_VERSION,
        "case_count": len(brief_profiles),
        "reference_count": len(reference_profiles),
        "domains": domains,
    }


__all__ = [
    "FEATURE_VOCABULARY_VERSION",
    "VOCABULARY",
    "DiagnosticFeatureProfile",
    "FeatureEvidence",
    "HookFeatures",
    "canonical_tokens",
    "diagnostic_overlap",
    "extract_brief_features",
    "feature_coverage",
    "normalize_values",
    "reference_feature_profile",
    "validate_feature_provenance",
]
