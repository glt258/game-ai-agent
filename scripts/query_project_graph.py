"""Deterministic query and validation CLI for Engineering Knowledge Graph v0.1."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

import yaml

try:
    from .project_graph_lib import (
        RepositoryRootError,
        is_architecture_path,
        is_knowledge_tooling_only,
        repository_root_from_graph_path,
    )
except ImportError:  # pragma: no cover - exercised by direct CLI invocation.
    from project_graph_lib import (  # type: ignore[no-redef]
        RepositoryRootError,
        is_architecture_path,
        is_knowledge_tooling_only,
        repository_root_from_graph_path,
    )

ALLOWED_RELATIONS = {
    "owns",
    "canonical_for",
    "implements",
    "depends_on",
    "consumes",
    "produces",
    "validates",
    "evaluates",
    "repairs",
    "compiles",
    "retrieves_from",
    "configured_by",
    "exposes",
    "adapts",
    "tested_by",
    "protected_by",
    "benchmarked_by",
    "supersedes",
    "deprecated_by",
}
ALLOWED_TYPES = {
    "subsystem",
    "component",
    "contract",
    "concept",
    "dataset_boundary",
    "test_suite",
    "limitation",
    "architecture_decision",
}
ALLOWED_STATUSES = {
    "frozen",
    "stable",
    "active",
    "experimental",
    "legacy",
    "deprecated",
    "candidate",
}
ALLOWED_SNAPSHOT_KINDS = {
    "release",
    "clean_head",
    "reviewed_working_tree",
    # Accepted for graph fixtures created by v0.1; new metadata uses the names above.
    "release_snapshot",
    "repository_head",
}


class GraphValidationError(ValueError):
    """Raised when a graph violates the v0.1 semantic validation rules."""


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, dict):
        raise GraphValidationError(f"Graph root must be a mapping: {path}")
    return document


def _relative_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise GraphValidationError(f"Path escapes project root: {value}") from exc
    return resolved


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GraphValidationError(f"{label} must be a mapping")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphValidationError(f"{label} must be a non-empty string")
    return value


def _is_absolute_repository_root(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _validate_evidence(value: Any, root: Path, label: str, check_paths: bool) -> None:
    if not isinstance(value, list):
        raise GraphValidationError(f"{label} must be a list")
    for index, item in enumerate(value):
        evidence = _require_mapping(item, f"{label}[{index}]")
        path = _require_string(evidence.get("path"), f"{label}[{index}].path")
        _require_string(evidence.get("locator"), f"{label}[{index}].locator")
        if check_paths and not _relative_path(root, path).exists():
            raise GraphValidationError(f"Evidence path does not exist: {path}")


def validate_graph(
    graph: dict[str, Any],
    graph_path: Path | None = None,
    *,
    check_paths: bool = True,
) -> None:
    """Validate shape, paths, relations, endpoints and canonical ownership."""

    if graph.get("schema_version") != "engineering-knowledge-graph/0.1":
        raise GraphValidationError("Unsupported or missing graph schema_version")
    snapshot = _require_mapping(graph.get("snapshot"), "snapshot")
    for field in ("project", "project_root", "branch", "working_tree", "snapshot_kind"):
        _require_string(snapshot.get(field), f"snapshot.{field}")
    if snapshot["snapshot_kind"] not in ALLOWED_SNAPSHOT_KINDS:
        raise GraphValidationError(f"Invalid snapshot_kind: {snapshot['snapshot_kind']}")
    if not snapshot.get("base_head") and not snapshot.get("head"):
        raise GraphValidationError("snapshot.base_head must be provided")
    _require_string(snapshot.get("base_head", snapshot.get("head")), "snapshot.base_head")
    if not isinstance(snapshot.get("release_equivalent"), bool):
        raise GraphValidationError("snapshot.release_equivalent must be boolean")

    if _is_absolute_repository_root(snapshot["project_root"]):
        raise GraphValidationError(
            "snapshot.project_root must be repository-relative; machine-local absolute roots are not portable"
        )
    root = repository_root_from_graph_path(graph_path or Path.cwd())

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise GraphValidationError("nodes must be a list")
    node_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_node in enumerate(nodes):
        node = _require_mapping(raw_node, f"nodes[{index}]")
        node_id = _require_string(node.get("id"), f"nodes[{index}].id")
        if node_id in node_by_id:
            raise GraphValidationError(f"Duplicate node ID: {node_id}")
        node_by_id[node_id] = node
        _require_string(node.get("type"), f"nodes[{index}].type")
        if node["type"] not in ALLOWED_TYPES:
            raise GraphValidationError(f"Invalid node type: {node['type']}")
        _require_string(node.get("name"), f"nodes[{index}].name")
        _require_string(node.get("status"), f"nodes[{index}].status")
        if node["status"] not in ALLOWED_STATUSES:
            raise GraphValidationError(f"Invalid node status: {node['status']}")
        _require_string(node.get("responsibility"), f"nodes[{index}].responsibility")
        _validate_evidence(node.get("evidence", []), root, f"nodes[{index}].evidence", check_paths)
        for field in ("path", "canonical_source"):
            if field in node:
                value = _require_string(node[field], f"nodes[{index}].{field}")
                if check_paths and not _relative_path(root, value).exists():
                    raise GraphValidationError(f"{field} does not exist: {value}")
        if "tests" in node:
            if not isinstance(node["tests"], list):
                raise GraphValidationError(f"nodes[{index}].tests must be a list")
            for test_path in node["tests"]:
                test_path = _require_string(test_path, f"nodes[{index}].tests item")
                if check_paths and not _relative_path(root, test_path).exists():
                    raise GraphValidationError(f"Test path does not exist: {test_path}")

    edges = graph.get("edges")
    if not isinstance(edges, list):
        raise GraphValidationError("edges must be a list")
    canonical_targets: dict[str, list[str]] = {}
    for index, raw_edge in enumerate(edges):
        edge = _require_mapping(raw_edge, f"edges[{index}]")
        source = _require_string(edge.get("from"), f"edges[{index}].from")
        target = _require_string(edge.get("to"), f"edges[{index}].to")
        relation = _require_string(edge.get("relation"), f"edges[{index}].relation")
        if source not in node_by_id or target not in node_by_id:
            raise GraphValidationError(f"Dangling edge: {source} -[{relation}]-> {target}")
        if relation not in ALLOWED_RELATIONS:
            raise GraphValidationError(f"Invalid relation: {relation}")
        _validate_evidence(edge.get("evidence", []), root, f"edges[{index}].evidence", check_paths)
        if relation == "canonical_for":
            canonical_targets.setdefault(target, []).append(source)

    for target, sources in canonical_targets.items():
        unique_sources = list(dict.fromkeys(sources))
        if len(unique_sources) <= 1:
            continue
        non_legacy = [
            source
            for source in unique_sources
            if node_by_id[source].get("status") not in {"legacy", "deprecated"}
            and node_by_id[source].get("compatibility") is not True
        ]
        if len(non_legacy) > 1:
            raise GraphValidationError(
                f"Canonical ownership conflict for {target}: {', '.join(non_legacy)}"
            )

    for collection_name in ("constraints", "known_limitations", "architecture_decisions"):
        collection = graph.get(collection_name)
        if not isinstance(collection, list):
            raise GraphValidationError(f"{collection_name} must be a list")
        ids: set[str] = set()
        for index, item in enumerate(collection):
            mapping = _require_mapping(item, f"{collection_name}[{index}]")
            item_id = _require_string(mapping.get("id"), f"{collection_name}[{index}].id")
            if item_id in ids:
                raise GraphValidationError(f"Duplicate {collection_name} ID: {item_id}")
            ids.add(item_id)
            _validate_evidence(
                mapping.get("evidence", []),
                root,
                f"{collection_name}[{index}].evidence",
                check_paths,
            )
            if collection_name == "constraints":
                _require_string(mapping.get("statement"), f"{collection_name}[{index}].statement")
                if mapping.get("severity") not in {"critical", "high", "medium", "low"}:
                    raise GraphValidationError(
                        f"Invalid constraint severity: {mapping.get('severity')}"
                    )
            elif collection_name == "known_limitations":
                _require_string(mapping.get("statement"), f"{collection_name}[{index}].statement")
                if mapping.get("status") not in {"active", "deprecated"}:
                    raise GraphValidationError(
                        f"Invalid limitation status: {mapping.get('status')}"
                    )
            else:
                _require_string(mapping.get("title"), f"{collection_name}[{index}].title")
                _require_string(mapping.get("decision"), f"{collection_name}[{index}].decision")
                _require_string(mapping.get("rationale"), f"{collection_name}[{index}].rationale")
                if mapping.get("status") not in ALLOWED_STATUSES:
                    raise GraphValidationError(f"Invalid decision status: {mapping.get('status')}")


def git_state(root: Path, runner: Callable[..., str] = subprocess.check_output) -> dict[str, str]:
    """Return the small Git state needed for snapshot comparison."""

    def run(*args: str) -> str:
        return runner(
            ["git", "-C", str(root), *args],
            text=True,
            encoding="utf-8",
            errors="strict",
            stderr=subprocess.DEVNULL,
        ).strip()

    branch = run("branch", "--show-current") or "detached"
    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"branch": branch, "head": head, "working_tree": "dirty" if status else "clean"}


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


def matching_nodes(nodes: list[dict[str, Any]], topics: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for node in nodes:
        searchable = " ".join(
            str(node.get(field, ""))
            for field in ("id", "name", "responsibility", "path", "canonical_source")
        ).lower()
        searchable_tokens = _tokens(searchable)
        if any(
            topic.lower() in searchable or _tokens(topic).issubset(searchable_tokens)
            for topic in topics
        ):
            matches.append(node)
    return matches


def _node_label(node: dict[str, Any]) -> str:
    return f"{node['name']} (`{node['id']}`, {node['status']})"


def build_query_result(graph: dict[str, Any], topics: list[str]) -> dict[str, Any]:
    nodes = graph["nodes"]
    by_id = {node["id"]: node for node in nodes}
    matches = matching_nodes(nodes, topics)
    matched_ids = {node["id"] for node in matches}
    edges = graph.get("edges", [])
    related_ids: set[str] = set()
    related_edges: list[dict[str, Any]] = []
    for edge in edges:
        if edge["from"] in matched_ids or edge["to"] in matched_ids:
            related_edges.append(edge)
            related_ids.update({edge["from"], edge["to"]})
    related_ids -= matched_ids
    related_nodes = [by_id[node_id] for node_id in sorted(related_ids) if node_id in by_id]
    context_ids = matched_ids | related_ids

    limitations = [
        limitation
        for limitation in graph.get("known_limitations", [])
        if context_ids.intersection(limitation.get("scope", []))
    ]
    constraints = [
        constraint
        for constraint in graph.get("constraints", [])
        if context_ids.intersection(constraint.get("scope", []))
    ]
    decisions = graph.get("architecture_decisions", [])
    paths: list[str] = []
    tests: list[str] = []
    for node in matches + related_nodes:
        for field in ("path", "canonical_source"):
            if node.get(field):
                paths.append(node[field])
        tests.extend(node.get("tests", []))
    return {
        "snapshot": graph["snapshot"],
        "matches": matches,
        "related_nodes": related_nodes,
        "related_edges": related_edges,
        "canonical_sources": sorted(
            {
                node["canonical_source"]
                for node in matches + related_nodes
                if node.get("canonical_source")
            }
        ),
        "contracts": [
            node
            for node in matches + related_nodes
            if node["type"] == "contract" and node["status"] in {"frozen", "stable"}
        ],
        "tests": sorted(set(tests)),
        "limitations": limitations,
        "constraints": constraints,
        "decisions": decisions,
        "paths": sorted(set(paths)),
    }


def _git_paths_since(root: Path, base_head: str) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(root), "diff", "--name-only", f"{base_head}..HEAD"],
            text=True,
            encoding="utf-8",
            errors="strict",
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def snapshot_warnings(
    snapshot: dict[str, Any],
    current_git: dict[str, str],
    *,
    root: Path | None = None,
    history_paths: list[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    base_head = snapshot.get("base_head", snapshot.get("head"))
    head_changed = base_head != current_git.get("head")
    snapshot_kind = snapshot.get("snapshot_kind")
    if head_changed and snapshot_kind == "reviewed_working_tree":
        paths = history_paths
        if paths is None and root is not None:
            paths = _git_paths_since(root, str(base_head))
        if paths and is_knowledge_tooling_only(paths):
            warnings.append("ENGINEERING KNOWLEDGE TOOLING ADVANCED SINCE BASE")
        elif paths and any(is_architecture_path(path) for path in paths):
            warnings.append("GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE")
        elif paths:
            warnings.append("GRAPH REVIEW BASE HAS UNRELATED ADVANCEMENT")
        else:
            warnings.append("GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE")
    elif head_changed:
        warnings.append(
            f"GRAPH SNAPSHOT MISMATCH: graph HEAD {base_head} differs from current HEAD {current_git.get('head')}."
        )
    if snapshot.get("branch") != current_git.get("branch"):
        warnings.append(
            f"GRAPH BRANCH MISMATCH: graph branch {snapshot.get('branch')} differs from current branch {current_git.get('branch')}."
        )
    if current_git.get("working_tree") == "dirty":
        warnings.append("WORKING TREE WARNING: current working tree is dirty.")
    if snapshot.get("snapshot_kind") == "reviewed_working_tree":
        warnings.append(
            "This graph may include reviewed uncommitted architecture and does not represent the v0.8 release snapshot."
        )
    return warnings


def render_markdown(
    result: dict[str, Any], current_git: dict[str, str], *, root: Path | None = None
) -> str:
    snapshot = result["snapshot"]
    warnings = snapshot_warnings(snapshot, current_git, root=root)

    lines = ["# Engineering Knowledge Graph Query", "", "## Snapshot", ""]
    for key in (
        "project",
        "branch",
        "base_head",
        "release_tag",
        "working_tree",
        "snapshot_kind",
        "release_equivalent",
    ):
        lines.append(f"- {key}: `{snapshot.get(key)}`")
    if result["matches"]:
        lines.extend(["", "## Relevant Components", ""])
        lines.extend(f"- {_node_label(node)}" for node in result["matches"])
    if result["canonical_sources"]:
        lines.extend(["", "## Canonical Sources", ""])
        lines.extend(f"- `{path}`" for path in result["canonical_sources"])
    if result["contracts"]:
        lines.extend(["", "## Frozen / Stable Contracts", ""])
        lines.extend(
            f"- {_node_label(node)}: {node['responsibility']}" for node in result["contracts"]
        )
    if result["related_nodes"]:
        lines.extend(["", "## Related Components", ""])
        lines.extend(f"- {_node_label(node)}" for node in result["related_nodes"])
    if result["related_edges"]:
        lines.extend(["", "## Related Edges", ""])
        lines.extend(
            f"- `{edge['from']}` -[{edge['relation']}]-> `{edge['to']}`"
            for edge in result["related_edges"]
        )
    if result["tests"]:
        lines.extend(["", "## Related Tests", ""])
        lines.extend(f"- `{path}`" for path in result["tests"])
    if result["limitations"]:
        lines.extend(["", "## Known Limitations", ""])
        lines.extend(f"- `{item['id']}`: {item['statement']}" for item in result["limitations"])
    if result["decisions"]:
        lines.extend(["", "## Architecture Decisions", ""])
        lines.extend(
            f"- `{item['id']}`: {item['title']} ({item['status']})" for item in result["decisions"]
        )
    if result["paths"]:
        lines.extend(["", "## Potentially Affected Paths", ""])
        lines.extend(f"- `{path}`" for path in result["paths"])
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--topic", action="append", required=True)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--no-path-check", action="store_true", help="Skip repository path checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = args.graph.resolve()
    try:
        graph = load_yaml(graph_path)
        validate_graph(graph, graph_path, check_paths=not args.no_path_check)
        root = repository_root_from_graph_path(graph_path)
        current_git = git_state(root)
        result = build_query_result(graph, args.topic)
    except (
        OSError,
        GraphValidationError,
        RepositoryRootError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"project graph validation failed: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result, current_git, root=root), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
