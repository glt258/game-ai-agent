"""One-shot, report-authorized SkillKit repair.

This module is a deliberately small public seam.  It accepts only the
request-owned domain values and re-runs the production evaluator after an
atomic RFC 6901 patch; provider-specific repair scopes are not part of it.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from .context import SkillValidationContext
from .errors import SkillKitShapeError
from .evaluation import _coerce_context, evaluate
from .models import (
    ProtocolSkillKitCandidate,
    SkillValidationReport,
)
from .contract import parse_candidate


class SkillKitPatchError(ValueError):
    """Stable failure for an ineligible, malformed, or ineffective patch."""

    code = "PATCH_INVALID"


@dataclass(frozen=True)
class SkillKitPatch:
    """A strict, digest-bound collection of add/replace operations."""

    base_digest: str
    report_digest: str
    operations: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))

    def to_mapping(self) -> dict[str, object]:
        return {
            "base_digest": self.base_digest,
            "report_digest": self.report_digest,
            "operations": [copy.deepcopy(dict(operation)) for operation in self.operations],
        }


@dataclass(frozen=True)
class SkillKitRepairRequest:
    """Minimal structured input made available to one patch provider call."""

    candidate: ProtocolSkillKitCandidate
    context: SkillValidationContext
    finding_codes: tuple[str, ...]
    authorized_paths: tuple[str, ...]
    base_digest: str
    report_digest: str
    context_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_codes", tuple(self.finding_codes))
        object.__setattr__(self, "authorized_paths", tuple(self.authorized_paths))

    def to_mapping(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.to_mapping(),
            "context": self.context.to_mapping(),
            "finding_codes": list(self.finding_codes),
            "authorized_paths": list(self.authorized_paths),
            "base_digest": self.base_digest,
            "report_digest": self.report_digest,
            "context_digest": self.context_digest,
        }


@dataclass(frozen=True)
class SkillKitRepairResult:
    """Successful result of exactly one bounded repair attempt."""

    candidate: ProtocolSkillKitCandidate
    report: SkillValidationReport
    attempts: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.to_mapping(),
            "report": self.report.to_mapping(),
            "attempts": self.attempts,
        }


def _reject(detail: str) -> SkillKitPatchError:
    # Keep provider-controlled text out of the stable error surface.
    return SkillKitPatchError(detail)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _reject("patch must be an object")
    if any(not isinstance(key, str) for key in value):
        raise _reject("patch keys must be strings")
    return value


def _string(value: object, detail: str) -> str:
    if not isinstance(value, str):
        raise _reject(detail)
    return value


def _coerce_patch(value: object) -> SkillKitPatch:
    if isinstance(value, SkillKitPatch):
        operations = value.operations
        base_digest = _string(value.base_digest, "patch base_digest must be a string")
        report_digest = _string(
            value.report_digest, "patch report_digest must be a string"
        )
    else:
        payload = _mapping(value)
        if set(payload) != {"base_digest", "report_digest", "operations"}:
            raise _reject("patch keys are not exact")
        base_digest = _string(payload["base_digest"], "patch base_digest must be a string")
        report_digest = _string(
            payload["report_digest"], "patch report_digest must be a string"
        )
        raw_operations = payload["operations"]
        if (
            not isinstance(raw_operations, Sequence)
            or isinstance(raw_operations, (str, bytes, bytearray, Mapping))
        ):
            raise _reject("patch operations must be an array")
        operations = tuple(raw_operations)

    normalized: list[Mapping[str, object]] = []
    for operation in operations:
        row = _mapping(operation)
        if set(row) != {"op", "path", "value"}:
            raise _reject("patch operation keys are not exact")
        op = _string(row["op"], "patch operation op must be a string")
        path = _string(row["path"], "patch operation path must be a string")
        if op not in {"add", "replace"}:
            raise _reject("patch operation is not allowed")
        if not path.startswith("/") or path == "/":
            raise _reject("patch path must be a non-root RFC 6901 pointer")
        # Validate escape sequences now, before any operation can mutate a copy.
        _pointer_parts(path)
        normalized.append({"op": op, "path": path, "value": copy.deepcopy(row["value"])})
    return SkillKitPatch(base_digest, report_digest, tuple(normalized))


def _pointer_parts(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise _reject("patch path must be a non-root RFC 6901 pointer")
    parts: list[str] = []
    for raw in path[1:].split("/"):
        decoded: list[str] = []
        index = 0
        while index < len(raw):
            char = raw[index]
            if char != "~":
                decoded.append(char)
                index += 1
                continue
            if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
                raise _reject("patch path has an invalid RFC 6901 escape")
            decoded.append("~" if raw[index + 1] == "0" else "/")
            index += 2
        parts.append("".join(decoded))
    return parts


def _apply_operation(document: object, operation: Mapping[str, object]) -> None:
    parts = _pointer_parts(operation["path"])
    cursor = document
    for part in parts[:-1]:
        if isinstance(cursor, list):
            if not part.isdigit() or int(part) >= len(cursor):
                raise _reject("patch path does not resolve")
            cursor = cursor[int(part)]
        elif isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            raise _reject("patch path does not resolve")

    leaf = parts[-1]
    op = operation["op"]
    value = copy.deepcopy(operation["value"])
    if isinstance(cursor, list):
        if op == "add" and leaf == "-":
            cursor.append(value)
            return
        if not leaf.isdigit():
            raise _reject("patch list path is not authorized")
        index = int(leaf)
        if op == "add" and index <= len(cursor):
            cursor.insert(index, value)
            return
        if op == "replace" and index < len(cursor):
            cursor[index] = value
            return
        raise _reject("patch list path is not authorized")
    if isinstance(cursor, dict):
        if op == "add":
            cursor[leaf] = value
            return
        if op == "replace" and leaf in cursor:
            cursor[leaf] = value
            return
    raise _reject("patch path does not resolve")


def repair_once(
    candidate: ProtocolSkillKitCandidate,
    report: SkillValidationReport,
    context: SkillValidationContext | Mapping[str, object],
    patch_provider: Callable[[SkillKitRepairRequest], object],
) -> SkillKitRepairResult:
    """Call one provider at most once and accept only a complete improvement."""

    if not isinstance(candidate, ProtocolSkillKitCandidate):
        raise TypeError("repair_once expects a ProtocolSkillKitCandidate")
    if not isinstance(report, SkillValidationReport):
        raise TypeError("repair_once expects a SkillValidationReport")
    if not callable(patch_provider):
        raise TypeError("patch_provider must be callable")

    try:
        context_value = _coerce_context(context)
        current = evaluate(candidate, context_value)
    except Exception as exc:
        if isinstance(exc, SkillKitShapeError):
            raise
        raise _reject("candidate or context cannot be evaluated") from None

    if (
        report != current
        or report.candidate_digest != candidate.digest
        or report.context_digest != current.context_digest
        or report.report_digest != current.report_digest
    ):
        raise _reject("report digest binding does not match candidate and context")
    if (
        report.outcome != "REPAIR"
        or not report.repair_allowed
        or not report.findings
        or any(not finding.repairable or not finding.authorized_paths for finding in report.findings)
    ):
        raise _reject("report is not eligible for bounded repair")

    authorized_paths = tuple(
        sorted({path for finding in report.findings for path in finding.authorized_paths})
    )
    request = SkillKitRepairRequest(
        candidate=candidate,
        context=context_value,
        finding_codes=tuple(finding.code for finding in report.findings),
        authorized_paths=authorized_paths,
        base_digest=candidate.digest,
        report_digest=report.report_digest,
        context_digest=report.context_digest,
    )
    try:
        supplied_patch = patch_provider(request)
    except Exception:
        raise _reject("patch provider failed") from None

    patch = _coerce_patch(supplied_patch)
    if patch.base_digest != candidate.digest or patch.report_digest != report.report_digest:
        raise _reject("patch digest binding does not match candidate and report")
    authorized = set(authorized_paths)
    document = copy.deepcopy(candidate.to_mapping())
    for operation in patch.operations:
        path = operation["path"]
        if path not in authorized:
            raise _reject("patch path is not authorized by report")
        _apply_operation(document, operation)

    try:
        patched = parse_candidate(document)
    except Exception:
        raise _reject("patch produced an invalid candidate") from None
    if not isinstance(patched, ProtocolSkillKitCandidate):
        raise _reject("patch produced a legacy candidate")
    result = evaluate(patched, context_value)
    original_keys = {(finding.code, finding.field_path) for finding in report.findings}
    result_keys = {(finding.code, finding.field_path) for finding in result.findings}
    if not result_keys.issubset(original_keys):
        raise _reject("patch introduced a new finding")
    if result_keys & original_keys:
        raise _reject("patch did not remove all original findings")
    if result.outcome != "PASS":
        raise _reject("patch outcome did not strictly improve to PASS")
    return SkillKitRepairResult(patched, result, attempts=1)


__all__ = [
    "SkillKitPatch",
    "SkillKitPatchError",
    "SkillKitRepairRequest",
    "SkillKitRepairResult",
    "repair_once",
]
