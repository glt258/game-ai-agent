"""Safe, bounded diagnostics for Hybrid evaluator reports.

The evaluator remains the acceptance authority.  This module only maps its
internal findings into a small, versioned and JSON-safe observability object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from character_skill.models import SkillFinding, SkillValidationReport

SAFE_EVALUATOR_DIAGNOSTIC_VERSION = "hybrid-safe-evaluator-diagnostics/0.1.0"


class SemanticDimension(str, Enum):
    ROLE_ALIGNMENT = "ROLE_ALIGNMENT"
    ROLE_EVIDENCE = "ROLE_EVIDENCE"
    MECHANIC_SKELETON = "MECHANIC_SKELETON"
    FEEDBACK_EXISTENCE = "FEEDBACK_EXISTENCE"
    FEEDBACK_RELATION = "FEEDBACK_RELATION"
    FEEDBACK_REFERENCE = "FEEDBACK_REFERENCE"
    SUBJECT_AMBIGUITY = "SUBJECT_AMBIGUITY"
    LIFECYCLE = "LIFECYCLE"
    CONSTRAINT = "CONSTRAINT"
    FORBIDDEN_MECHANIC = "FORBIDDEN_MECHANIC"
    REFERENCE_INTEGRITY = "REFERENCE_INTEGRITY"
    REFERENCE_AUTHORITY = "REFERENCE_AUTHORITY"
    REPRESENTATION = "REPRESENTATION"
    OTHER_SEMANTIC = "OTHER_SEMANTIC"


class FindingCategory(str, Enum):
    MISSING_REQUIRED_SEMANTIC = "MISSING_REQUIRED_SEMANTIC"
    SEMANTIC_MISMATCH = "SEMANTIC_MISMATCH"
    RELATIONSHIP_MISMATCH = "RELATIONSHIP_MISMATCH"
    ROLE_EVIDENCE_MISMATCH = "ROLE_EVIDENCE_MISMATCH"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    AMBIGUOUS_SEMANTIC = "AMBIGUOUS_SEMANTIC"
    LIFECYCLE_INCOMPLETE = "LIFECYCLE_INCOMPLETE"
    LIFECYCLE_MISMATCH = "LIFECYCLE_MISMATCH"
    REFERENCE_INTEGRITY = "REFERENCE_INTEGRITY"
    REFERENCE_POLICY = "REFERENCE_POLICY"
    REPRESENTATION_MISSING = "REPRESENTATION_MISSING"
    UNKNOWN = "UNKNOWN"


class Repairability(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REPAIRABLE = "REPAIRABLE"
    NON_REPAIRABLE = "NON_REPAIRABLE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


_M = {
    "HARD_CONSTRAINT_CONFLICT": (SemanticDimension.CONSTRAINT, FindingCategory.CONSTRAINT_VIOLATION),
    "FORBIDDEN_RESOURCE_INTRODUCED": (SemanticDimension.FORBIDDEN_MECHANIC, FindingCategory.CONSTRAINT_VIOLATION),
    "FORBIDDEN_STATE_INTRODUCED": (SemanticDimension.FORBIDDEN_MECHANIC, FindingCategory.CONSTRAINT_VIOLATION),
    "FORBIDDEN_SUMMON_INTRODUCED": (SemanticDimension.FORBIDDEN_MECHANIC, FindingCategory.CONSTRAINT_VIOLATION),
    "MECHANIC_SKELETON_ABSENT": (SemanticDimension.MECHANIC_SKELETON, FindingCategory.MISSING_REQUIRED_SEMANTIC),
    "REQUESTED_MECHANIC_UNREPRESENTED": (SemanticDimension.FEEDBACK_EXISTENCE, FindingCategory.MISSING_REQUIRED_SEMANTIC),
    "FEEDBACK_REFERENCE_DANGLING": (SemanticDimension.FEEDBACK_REFERENCE, FindingCategory.REFERENCE_INTEGRITY),
    "FEEDBACK_RELATION_INVALID": (SemanticDimension.FEEDBACK_RELATION, FindingCategory.RELATIONSHIP_MISMATCH),
    "TRIGGER_SUBJECT_AMBIGUOUS": (SemanticDimension.SUBJECT_AMBIGUITY, FindingCategory.AMBIGUOUS_SEMANTIC),
    "ROLE_EFFECT_MISMATCH": (SemanticDimension.ROLE_EVIDENCE, FindingCategory.ROLE_EVIDENCE_MISMATCH),
    "CROSS_TAXONOMY_ROLE_LABEL": (SemanticDimension.ROLE_ALIGNMENT, FindingCategory.SEMANTIC_MISMATCH),
    "REFERENCE_DANGLING": (SemanticDimension.REFERENCE_INTEGRITY, FindingCategory.REFERENCE_INTEGRITY),
    "REFERENCE_KIND_MISMATCH": (SemanticDimension.REFERENCE_INTEGRITY, FindingCategory.REFERENCE_INTEGRITY),
    "LIFECYCLE_REFERENCE_WRONG_KIND": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_MISMATCH),
    "LIFECYCLE_REFERENCE_DANGLING": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_MISMATCH),
    "LIFECYCLE_OPERATION_MISMATCH": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_MISMATCH),
    "RESOURCE_LOOP_INCOMPLETE": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_INCOMPLETE),
    "MULTI_SKILL_LOOP_INCOHERENT": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_MISMATCH),
    "STATE_EXIT_MISSING": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_INCOMPLETE),
    "SUMMON_LIFECYCLE_INCOMPLETE": (SemanticDimension.LIFECYCLE, FindingCategory.LIFECYCLE_INCOMPLETE),
    "REFERENCE_COPYING": (SemanticDimension.REFERENCE_AUTHORITY, FindingCategory.REFERENCE_POLICY),
}
RAW_FINDING_CODE_MAPPING = MappingProxyType(_M)


@dataclass(frozen=True)
class SafeEvaluatorDiagnostics:
    """Immutable aggregate with no candidate-controlled strings."""

    schema_version: str
    complete: bool
    finding_count: int
    dimensions: tuple[SemanticDimension, ...]
    categories: tuple[FindingCategory, ...]
    counts_by_dimension: Mapping[SemanticDimension, int]
    counts_by_category: Mapping[FindingCategory, int]
    repairability: Repairability

    def __post_init__(self) -> None:
        if self.schema_version != SAFE_EVALUATOR_DIAGNOSTIC_VERSION:
            raise ValueError("SAFE_DIAGNOSTIC_VERSION_INVALID")
        if not isinstance(self.complete, bool):
            raise TypeError("complete must be bool")
        if isinstance(self.finding_count, bool) or not isinstance(self.finding_count, int) or self.finding_count < 0:
            raise ValueError("SAFE_DIAGNOSTIC_FINDING_COUNT_INVALID")
        dimensions = tuple(self.dimensions)
        categories = tuple(self.categories)
        if any(not isinstance(item, SemanticDimension) for item in dimensions):
            raise TypeError("dimensions must contain SemanticDimension values")
        if any(not isinstance(item, FindingCategory) for item in categories):
            raise TypeError("categories must contain FindingCategory values")
        if dimensions != tuple(sorted(set(dimensions), key=lambda item: item.value)):
            raise ValueError("SAFE_DIAGNOSTIC_DIMENSIONS_NOT_CANONICAL")
        if categories != tuple(sorted(set(categories), key=lambda item: item.value)):
            raise ValueError("SAFE_DIAGNOSTIC_CATEGORIES_NOT_CANONICAL")
        dimension_counts = self._freeze_counts(self.counts_by_dimension, SemanticDimension)
        category_counts = self._freeze_counts(self.counts_by_category, FindingCategory)
        if sum(dimension_counts.values()) != self.finding_count:
            raise ValueError("SAFE_DIAGNOSTIC_DIMENSION_COUNTS_INVALID")
        if sum(category_counts.values()) != self.finding_count:
            raise ValueError("SAFE_DIAGNOSTIC_CATEGORY_COUNTS_INVALID")
        if tuple(dimension_counts) != dimensions or tuple(category_counts) != categories:
            raise ValueError("SAFE_DIAGNOSTIC_KEYS_INVALID")
        if not isinstance(self.repairability, Repairability):
            raise TypeError("repairability must be Repairability")
        if not self.complete:
            if FindingCategory.UNKNOWN not in categories or SemanticDimension.OTHER_SEMANTIC not in dimensions:
                raise ValueError("SAFE_DIAGNOSTIC_UNKNOWN_POLICY_INVALID")
            if self.repairability is not Repairability.UNKNOWN:
                raise ValueError("SAFE_DIAGNOSTIC_UNKNOWN_REPAIRABILITY_INVALID")
        elif FindingCategory.UNKNOWN in categories or self.repairability is Repairability.UNKNOWN:
            raise ValueError("SAFE_DIAGNOSTIC_COMPLETE_UNKNOWN_INVALID")
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "counts_by_dimension", dimension_counts)
        object.__setattr__(self, "counts_by_category", category_counts)

    @staticmethod
    def _freeze_counts(values: Mapping[object, object], enum_type: type[Enum]) -> Mapping[Enum, int]:
        if not isinstance(values, Mapping):
            raise TypeError("safe diagnostic counts must be mappings")
        normalized: dict[Enum, int] = {}
        for key, value in values.items():
            if not isinstance(key, enum_type):
                raise ValueError("SAFE_DIAGNOSTIC_COUNT_KEY_INVALID")
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("SAFE_DIAGNOSTIC_COUNT_VALUE_INVALID")
            normalized[key] = value
        return MappingProxyType(dict(sorted(normalized.items(), key=lambda item: item[0].value)))

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "complete": self.complete,
            "finding_count": self.finding_count,
            "dimensions": [item.value for item in self.dimensions],
            "categories": [item.value for item in self.categories],
            "counts_by_dimension": {key.value: value for key, value in self.counts_by_dimension.items()},
            "counts_by_category": {key.value: value for key, value in self.counts_by_category.items()},
            "repairability": self.repairability.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SafeEvaluatorDiagnostics":
        required = {
            "schema_version", "complete", "finding_count", "dimensions", "categories",
            "counts_by_dimension", "counts_by_category", "repairability",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("SAFE_DIAGNOSTIC_SCHEMA_INVALID")
        try:
            dimensions = tuple(SemanticDimension(item) for item in payload["dimensions"])
            categories = tuple(FindingCategory(item) for item in payload["categories"])
            dimension_counts = {
                SemanticDimension(key): value
                for key, value in payload["counts_by_dimension"].items()
            }
            category_counts = {
                FindingCategory(key): value
                for key, value in payload["counts_by_category"].items()
            }
            repairability = Repairability(payload["repairability"])
        except (TypeError, AttributeError, ValueError):
            raise ValueError("SAFE_DIAGNOSTIC_SCHEMA_INVALID") from None
        return cls(
            schema_version=payload["schema_version"],
            complete=payload["complete"],
            finding_count=payload["finding_count"],
            dimensions=dimensions,
            categories=categories,
            counts_by_dimension=dimension_counts,
            counts_by_category=category_counts,
            repairability=repairability,
        )


def _repairability(findings: Sequence[SkillFinding], *, unknown: bool) -> Repairability:
    if unknown:
        return Repairability.UNKNOWN
    if not findings:
        return Repairability.NOT_APPLICABLE
    flags = {finding.repairable for finding in findings}
    if flags == {True}:
        return Repairability.REPAIRABLE
    if flags == {False}:
        return Repairability.NON_REPAIRABLE
    return Repairability.MIXED


def adapt_skill_validation_report(report: SkillValidationReport) -> SafeEvaluatorDiagnostics:
    """Map a report without persisting any raw finding material."""

    if not isinstance(report, SkillValidationReport):
        raise TypeError("report must be a SkillValidationReport")
    dimensions: dict[SemanticDimension, int] = {}
    categories: dict[FindingCategory, int] = {}
    unknown = False
    known_findings: list[SkillFinding] = []
    for finding in report.findings:
        if not isinstance(finding, SkillFinding) or not isinstance(finding.code, str):
            unknown = True
            dimensions[SemanticDimension.OTHER_SEMANTIC] = dimensions.get(SemanticDimension.OTHER_SEMANTIC, 0) + 1
            categories[FindingCategory.UNKNOWN] = categories.get(FindingCategory.UNKNOWN, 0) + 1
            continue
        mapped = RAW_FINDING_CODE_MAPPING.get(finding.code)
        if mapped is None:
            unknown = True
            dimensions[SemanticDimension.OTHER_SEMANTIC] = dimensions.get(SemanticDimension.OTHER_SEMANTIC, 0) + 1
            categories[FindingCategory.UNKNOWN] = categories.get(FindingCategory.UNKNOWN, 0) + 1
            continue
        dimension, category = mapped
        dimensions[dimension] = dimensions.get(dimension, 0) + 1
        categories[category] = categories.get(category, 0) + 1
        known_findings.append(finding)
    return SafeEvaluatorDiagnostics(
        schema_version=SAFE_EVALUATOR_DIAGNOSTIC_VERSION,
        complete=not unknown,
        finding_count=len(report.findings),
        dimensions=tuple(sorted(dimensions, key=lambda item: item.value)),
        categories=tuple(sorted(categories, key=lambda item: item.value)),
        counts_by_dimension=dimensions,
        counts_by_category=categories,
        repairability=_repairability(known_findings, unknown=unknown),
    )


__all__ = [
    "FindingCategory",
    "RAW_FINDING_CODE_MAPPING",
    "Repairability",
    "SAFE_EVALUATOR_DIAGNOSTIC_VERSION",
    "SafeEvaluatorDiagnostics",
    "SemanticDimension",
    "adapt_skill_validation_report",
]
