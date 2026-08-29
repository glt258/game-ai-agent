"""Safe, deterministic provenance for semantic-to-canonical compilation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
COMPILER_VERSION = "skillkit-compiler/0.1.0"
COMPILER_VERSION_V2 = "skillkit-compiler/0.2.0"
PROVENANCE_SOURCE_KINDS = frozenset(
    {"IR_SEMANTIC", "COMPILER_CONSTANT", "COMPILER_DERIVED", "COMPILER_DEFAULT"}
)


@dataclass(frozen=True)
class CompilerProvenanceEntry:
    """One safe mapping fact; it never stores generated values."""

    canonical_path: str
    source_kind: str
    source_path: str | None = None
    rule_id: str | None = None

    def __post_init__(self) -> None:
        if not self.canonical_path.startswith("/"):
            raise ValueError("canonical_path must be an absolute canonical path")
        if self.source_kind not in PROVENANCE_SOURCE_KINDS:
            raise ValueError("unsupported provenance source kind")
        if self.source_path is not None and not self.source_path.startswith("/"):
            raise ValueError("source_path must be an IR path")
        if self.rule_id is None and self.source_path is None:
            raise ValueError("provenance requires a source path or rule id")

    def to_mapping(self) -> dict[str, str]:
        result = {
            "canonical_path": self.canonical_path,
            "source_kind": self.source_kind,
        }
        if self.source_path is not None:
            result["source_path"] = self.source_path
        if self.rule_id is not None:
            result["rule_id"] = self.rule_id
        return result


@dataclass(frozen=True)
class CompilerProvenance:
    """Ordered, immutable provenance for one compiler result."""

    compiler_version: str = COMPILER_VERSION
    entries: tuple[CompilerProvenanceEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.compiler_version not in {COMPILER_VERSION, COMPILER_VERSION_V2}:
            raise ValueError("unsupported compiler version")
        if not all(isinstance(item, CompilerProvenanceEntry) for item in self.entries):
            raise TypeError("entries must contain CompilerProvenanceEntry values")
        ordered = tuple(sorted(self.entries, key=lambda item: item.canonical_path))
        if ordered != self.entries:
            object.__setattr__(self, "entries", ordered)
        paths = [item.canonical_path for item in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("provenance canonical paths must be unique")

    def to_mapping(self) -> dict[str, object]:
        return {
            "compiler_version": self.compiler_version,
            "entries": [item.to_mapping() for item in self.entries],
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


__all__ = [
    "COMPILER_VERSION",
    "COMPILER_VERSION_V2",
    "CompilerProvenance",
    "CompilerProvenanceEntry",
    "PROVENANCE_SOURCE_KINDS",
]
