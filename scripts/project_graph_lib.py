"""Shared path classification for Engineering Knowledge tooling."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable


class RepositoryRootError(ValueError):
    """Raised when a graph cannot be associated with a repository checkout."""


ARCHITECTURE_PREFIXES = (
    "src/agents/",
    "src/combat_semantics/",
    "src/character_intelligence/",
    "src/character_skill/",
    "src/reference_corpus/",
    "src/knowledge/",
    "src/story/",
    "src/web/",
)

KNOWLEDGE_PATH_PREFIXES = (
    "knowledge/",
    "docs/project_memory/",
    "docs/decisions/",
)

KNOWLEDGE_TOOLING_EXACT_PATHS = {
    "agents.md",
    "scripts/project_graph_lib.py",
    "scripts/knowledge_baseline.py",
    "scripts/project_preflight.py",
    "scripts/project_postflight.py",
    "scripts/query_project_graph.py",
    "tests/test_project_graph.py",
    "tests/test_project_preflight.py",
    "tests/test_project_postflight.py",
    "tests/test_knowledge_baseline.py",
}


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").lower()


def is_architecture_path(path: str) -> bool:
    return normalize_path(path).startswith(ARCHITECTURE_PREFIXES)


def is_knowledge_path(path: str) -> bool:
    normalized = normalize_path(path)
    return normalized in KNOWLEDGE_TOOLING_EXACT_PATHS or normalized.startswith(
        KNOWLEDGE_PATH_PREFIXES
    )


def is_knowledge_tooling_only(paths: list[str]) -> bool:
    return bool(paths) and all(is_knowledge_path(path) for path in paths)


def repository_root_from_graph_path(
    graph_path: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Derive the checkout root from the graph location or Git, never graph metadata."""

    graph_file = graph_path.resolve()
    start = graph_file.parent if graph_file.suffix else graph_file
    result = runner(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    output = getattr(result, "stdout", result)
    if getattr(result, "returncode", 0) == 0 and output:
        candidate = Path(output.strip()).resolve()
        if candidate.exists():
            return candidate

    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
        if (candidate / "pyproject.toml").is_file() and (candidate / "knowledge").is_dir():
            return candidate
    raise RepositoryRootError(f"Unable to derive repository root from graph path: {graph_path}")
