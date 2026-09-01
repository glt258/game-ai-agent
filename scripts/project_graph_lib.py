"""Shared path classification for Engineering Knowledge tooling."""

from __future__ import annotations

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
