"""Stable shape errors for the public Character Skill contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SHAPE_DIAGNOSTIC_MAX_KEYS = 64
SHAPE_DIAGNOSTIC_MAX_FIELDS = 16
SHAPE_DIAGNOSTIC_MAX_ERRORS = 16
CANONICAL_ROOT_FIELDS = (
    "display_summary",
    "entries",
    "feedback_relations",
    "resources",
    "role_evidence",
    "schema_version",
    "states",
    "summons",
)
SHAPE_DIAGNOSTIC_ERROR_CODES = frozenset(
    {
        "INVALID_TOP_LEVEL_TYPE",
        "WRAPPER_NOT_ALLOWED",
        "MISSING_REQUIRED_FIELD",
        "UNKNOWN_FIELD",
        "INVALID_FIELD_TYPE",
        "INVALID_ENUM",
        "INVALID_NESTED_SHAPE",
        "NULL_NOT_ALLOWED",
        "MULTIPLE_CANDIDATES_NOT_ALLOWED",
        "INVALID_ROOT_SHAPE",
        "OTHER_SHAPE_ERROR",
    }
)
SHAPE_DIAGNOSTIC_STAGES = frozenset(
    {
        "provider_normalized_json",
        "shadow_root_check",
        "candidate_parser",
        "candidate_model_validation",
        "unavailable",
    }
)


def _top_level_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "other"


@dataclass(frozen=True)
class SkillKitShapeDiagnostic:
    """Content-free, bounded metadata for one rejected candidate shape."""

    parsed_top_level_type: str
    key_count: int | None
    key_count_truncated: bool
    expected_top_level_type: str = "object"
    wrapper_detected: bool | None = None
    missing_required_count: int = 0
    missing_required_fields: tuple[str, ...] = ()
    unknown_key_count: int = 0
    parser_error_code: str = "OTHER_SHAPE_ERROR"
    parser_error_path: str | None = None
    json_extraction_stage: str = "candidate_parser"
    validation_error_count: int = 1

    def __post_init__(self) -> None:
        if self.parsed_top_level_type not in {
            "object", "array", "string", "number", "boolean", "null", "other", "unavailable"
        }:
            raise ValueError("invalid parsed_top_level_type")
        if self.expected_top_level_type != "object":
            raise ValueError("invalid expected_top_level_type")
        if self.key_count is not None and (
            isinstance(self.key_count, bool)
            or not isinstance(self.key_count, int)
            or not 0 <= self.key_count <= SHAPE_DIAGNOSTIC_MAX_KEYS
        ):
            raise ValueError("invalid key_count")
        if not isinstance(self.key_count_truncated, bool):
            raise TypeError("key_count_truncated must be boolean")
        if self.wrapper_detected is not None and not isinstance(self.wrapper_detected, bool):
            raise TypeError("wrapper_detected must be boolean or None")
        for name, value in (
            ("missing_required_count", self.missing_required_count),
            ("unknown_key_count", self.unknown_key_count),
            ("validation_error_count", self.validation_error_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= SHAPE_DIAGNOSTIC_MAX_ERRORS:
                raise ValueError(f"invalid {name}")
        if len(self.missing_required_fields) > SHAPE_DIAGNOSTIC_MAX_FIELDS:
            raise ValueError("too many missing_required_fields")
        if any(field not in CANONICAL_ROOT_FIELDS for field in self.missing_required_fields):
            raise ValueError("non-canonical missing field")
        if self.parser_error_code not in SHAPE_DIAGNOSTIC_ERROR_CODES:
            raise ValueError("invalid parser_error_code")
        if self.parser_error_path is not None:
            raise ValueError("parser_error_path must be null for content-free diagnostics")
        if self.json_extraction_stage not in SHAPE_DIAGNOSTIC_STAGES:
            raise ValueError("invalid json_extraction_stage")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parsed_top_level_type": self.parsed_top_level_type,
            "key_count": self.key_count,
            "key_count_truncated": self.key_count_truncated,
            "expected_top_level_type": self.expected_top_level_type,
            "wrapper_detected": self.wrapper_detected,
            "missing_required_count": self.missing_required_count,
            "missing_required_fields": list(self.missing_required_fields),
            "unknown_key_count": self.unknown_key_count,
            "parser_error_code": self.parser_error_code,
            "parser_error_path": self.parser_error_path,
            "json_extraction_stage": self.json_extraction_stage,
            "validation_error_count": self.validation_error_count,
        }


def build_shape_diagnostic(
    payload: object,
    error: "SkillKitShapeError | None" = None,
    *,
    extraction_stage: str = "candidate_parser",
    wrapper_detected: bool | None = None,
) -> SkillKitShapeDiagnostic:
    """Build bounded diagnostics without retaining arbitrary provider content."""

    parsed_type = _top_level_type(payload) if payload is not _UNAVAILABLE else "unavailable"
    is_object = parsed_type == "object"
    key_count = None
    key_count_truncated = False
    missing_fields: tuple[str, ...] = ()
    unknown_count = 0
    if is_object:
        keys = tuple(payload.keys())  # type: ignore[union-attr]
        actual_count = len(keys)
        key_count = min(actual_count, SHAPE_DIAGNOSTIC_MAX_KEYS)
        key_count_truncated = actual_count > SHAPE_DIAGNOSTIC_MAX_KEYS
        markers = {"skill_kit", "ability_concept", "candidate"}
        detected = any(key in markers for key in keys)
        if wrapper_detected is None:
            wrapper_detected = detected
        if not detected:
            missing_fields = tuple(sorted(set(CANONICAL_ROOT_FIELDS) - set(keys)))[:SHAPE_DIAGNOSTIC_MAX_FIELDS]
            unknown_count = min(
                len(set(keys) - set(CANONICAL_ROOT_FIELDS)), SHAPE_DIAGNOSTIC_MAX_ERRORS
            )
    code = "OTHER_SHAPE_ERROR"
    if error is not None:
        if error.code == "TYPE_MISMATCH":
            code = "INVALID_TOP_LEVEL_TYPE" if error.field_path == "/" else "INVALID_NESTED_SHAPE"
        elif error.code == "MISSING_FIELD":
            code = "MISSING_REQUIRED_FIELD"
        elif error.code == "UNKNOWN_FIELD":
            code = "UNKNOWN_FIELD"
            unknown_count = max(unknown_count, 1)
        elif error.code == "UNSUPPORTED_SCHEMA_VERSION":
            code = "INVALID_ROOT_SHAPE"
        elif error.code == "UNSUPPORTED_VALUE":
            code = "WRAPPER_NOT_ALLOWED" if wrapper_detected else "INVALID_ENUM"
        elif error.code in {"INVALID_ID", "DUPLICATE_ID"}:
            code = "INVALID_NESTED_SHAPE"
    if code == "MISSING_REQUIRED_FIELD" and not missing_fields:
        missing_fields = tuple(
            field for field in CANONICAL_ROOT_FIELDS
            if error is not None and error.field_path.rstrip("/").split("/")[-1] == field
        )
    missing_count = len(missing_fields)
    if error is not None and error.code == "MISSING_FIELD":
        missing_count = max(missing_count, 1)
    validation_count = max(1, min(SHAPE_DIAGNOSTIC_MAX_ERRORS, missing_count or unknown_count or 1))
    return SkillKitShapeDiagnostic(
        parsed_top_level_type=parsed_type,
        key_count=key_count,
        key_count_truncated=key_count_truncated,
        wrapper_detected=wrapper_detected,
        missing_required_count=missing_count,
        missing_required_fields=missing_fields,
        unknown_key_count=unknown_count,
        parser_error_code=code,
        parser_error_path=None,
        json_extraction_stage=extraction_stage if extraction_stage in SHAPE_DIAGNOSTIC_STAGES else "unavailable",
        validation_error_count=validation_count,
    )


_UNAVAILABLE = object()


class SkillKitShapeError(ValueError):
    """Raised when a candidate violates the frozen provider shape contract."""

    def __init__(
        self,
        code: str,
        field_path: str,
        detail: str,
        *,
        diagnostic: SkillKitShapeDiagnostic | None = None,
    ) -> None:
        self.code = code
        self.field_path = field_path
        self.detail = detail
        self.message = detail
        self.diagnostic = diagnostic
        super().__init__(f"{code} at {field_path}: {detail}")

    def attach_diagnostic(self, diagnostic: SkillKitShapeDiagnostic) -> "SkillKitShapeError":
        self.diagnostic = diagnostic
        return self

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "message": self.message,
            "detail": self.detail,
        }


__all__ = [
    "CANONICAL_ROOT_FIELDS",
    "SkillKitShapeDiagnostic",
    "SkillKitShapeError",
    "build_shape_diagnostic",
]
