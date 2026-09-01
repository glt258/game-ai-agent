"""Deterministic engineering context preflight with optional task-baseline capture."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from .knowledge_baseline import BaselineError, capture_baseline
except ImportError:  # pragma: no cover - exercised by direct CLI invocation.
    from knowledge_baseline import BaselineError, capture_baseline  # type: ignore[no-redef]

try:  # Direct execution puts scripts/ on sys.path; tests import scripts as a namespace package.
    from .query_project_graph import (
        GraphValidationError,
        build_query_result,
        git_state,
        load_yaml,
        snapshot_warnings,
        validate_graph,
    )
except ImportError:  # pragma: no cover - exercised by the direct CLI invocation.
    from query_project_graph import (  # type: ignore[no-redef]
        GraphValidationError,
        build_query_result,
        git_state,
        load_yaml,
        snapshot_warnings,
        validate_graph,
    )


def normalize(value: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return " ".join(spaced.lower().replace("_", " ").replace("-", " ").split())


def load_aliases(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream) or {}
    aliases = document.get("aliases")
    if not isinstance(aliases, dict):
        raise GraphValidationError("topic aliases must contain an aliases mapping")
    result: dict[str, list[str]] = {}
    for topic, values in aliases.items():
        if not isinstance(topic, str) or not isinstance(values, list):
            raise GraphValidationError("topic aliases must map topic names to lists")
        result[topic] = [topic, *(value for value in values if isinstance(value, str))]
    return result


def resolve_topics(
    *,
    graph: dict[str, Any],
    aliases: dict[str, list[str]],
    task: str | None = None,
    explicit_topics: list[str] | None = None,
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Resolve explicit topics or reliable task aliases without semantic guessing."""

    if explicit_topics:
        resolved: list[str] = []
        matched: dict[str, list[str]] = {}
        for topic in explicit_topics:
            canonical = next(
                (
                    key
                    for key, values in aliases.items()
                    if normalize(topic) in {normalize(value) for value in values}
                ),
                topic,
            )
            result = build_query_result(graph, [canonical])
            node_ids = [node["id"] for node in result["matches"]]
            if node_ids:
                resolved.append(canonical)
                matched[canonical] = node_ids
        return list(dict.fromkeys(resolved)), matched, []

    if task is None:
        return [], {}, []
    normalized_task = normalize(task)
    resolved = []
    matched = {}
    for topic, values in aliases.items():
        if any(normalize(alias) in normalized_task for alias in values):
            result = build_query_result(graph, [topic])
            node_ids = [node["id"] for node in result["matches"]]
            if node_ids:
                resolved.append(topic)
                matched[topic] = node_ids
    candidates = sorted(
        node["id"]
        for node in graph["nodes"]
        if node["id"] not in {node_id for ids in matched.values() for node_id in ids}
    )
    return resolved, matched, candidates


def _context_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result["matches"] + result["related_nodes"]


def _evidence_paths(items: list[dict[str, Any]]) -> list[str]:
    return sorted({evidence["path"] for item in items for evidence in item.get("evidence", [])})


def _frozen_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in _context_nodes(result) if node.get("status") == "frozen"]


def _legacy_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node for node in _context_nodes(result) if node.get("status") in {"legacy", "deprecated"}
    ]


def build_preflight(
    graph: dict[str, Any],
    *,
    graph_path: Path,
    aliases: dict[str, list[str]],
    task: str | None = None,
    explicit_topics: list[str] | None = None,
    current_git: dict[str, str],
) -> tuple[str, str]:
    resolved, matched_topics, candidates = resolve_topics(
        graph=graph,
        aliases=aliases,
        task=task,
        explicit_topics=explicit_topics,
    )
    result = build_query_result(graph, resolved)
    warnings = snapshot_warnings(
        graph["snapshot"],
        current_git,
        root=Path(graph["snapshot"]["project_root"]).resolve(),
    )
    if not resolved:
        verdict = "INSUFFICIENT_CONTEXT"
    elif warnings:
        verdict = "READY_WITH_WARNINGS"
    else:
        verdict = "READY"

    context_nodes = _context_nodes(result)
    frozen_nodes = _frozen_nodes(result)
    legacy_nodes = _legacy_nodes(result)
    affected_paths = sorted(
        set(result["paths"])
        | set(result["tests"])
        | set(_evidence_paths(context_nodes))
        | set(_evidence_paths(result["constraints"]))
        | {item["path"] for item in context_nodes if item.get("path")}
    )
    inspect_paths = sorted(
        set(result["canonical_sources"])
        | set(result["tests"])
        | {item["path"] for item in result["contracts"] if item.get("path")}
    )

    lines = [
        "# Engineering Preflight",
        "",
        "## Task",
        "",
        f"- {task or ', '.join(explicit_topics or [])}",
        "",
    ]
    lines.extend(["## Snapshot", ""])
    for key in (
        "project",
        "branch",
        "base_head",
        "release_tag",
        "working_tree",
        "snapshot_kind",
        "release_equivalent",
    ):
        lines.append(f"- {key}: `{graph['snapshot'].get(key)}`")
    lines.extend(["", "## Matched Topics", ""])
    if matched_topics:
        for topic in resolved:
            lines.append(f"- `{topic}`: {', '.join(matched_topics[topic])}")
    elif candidates:
        lines.append("- `NO_RELIABLE_TOPIC_MATCH`")
        lines.append("- Available graph candidates: " + ", ".join(candidates[:12]))
    else:
        lines.append("- `NO_RELIABLE_TOPIC_MATCH`")

    if result["matches"]:
        lines.extend(["", "## Relevant Components", ""])
        lines.extend(
            f"- {node['name']} (`{node['id']}`, {node['status']})" for node in result["matches"]
        )
    if result["canonical_sources"]:
        lines.extend(["", "## Canonical Sources", ""])
        lines.append("**CANONICAL SOURCE**")
        lines.extend(f"- `{path}`" for path in result["canonical_sources"])
    if frozen_nodes:
        lines.extend(["", "## Frozen Contracts", ""])
        lines.append("**FROZEN CONTRACT**")
        for node in frozen_nodes:
            lines.append(f"- {node['name']} (`{node['id']}`)")
            if node.get("canonical_source"):
                lines.append(f"  - Owner/source: `{node['canonical_source']}`")
            for test_path in node.get("tests", []):
                lines.append(f"  - Protected by: `{test_path}`")
            for evidence in node.get("evidence", []):
                lines.append(f"  - Evidence: `{evidence['path']}` ({evidence['locator']})")
    if legacy_nodes:
        lines.extend(["", "## Legacy / Compatibility Warnings", ""])
        for node in legacy_nodes:
            lines.append(f"- {node['name']} (`{node['status']}`): **DO NOT TREAT AS CANONICAL**")
    if result["contracts"] and not frozen_nodes:
        lines.extend(["", "## Frozen / Stable Contracts", ""])
        lines.extend(f"- {node['name']} ({node['status']})" for node in result["contracts"])
    if result["related_nodes"]:
        lines.extend(["", "## Related Components", ""])
        lines.extend(f"- {node['name']} (`{node['status']}`)" for node in result["related_nodes"])
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
    if result["constraints"]:
        lines.extend(["", "## Constraints", ""])
        lines.extend(f"- `{item['id']}`: {item['statement']}" for item in result["constraints"])
    if affected_paths:
        lines.extend(
            [
                "",
                "## Potentially Affected Paths",
                "",
                "Graph-derived candidate paths; these are not files that definitely require modification.",
                "",
            ]
        )
        lines.extend(f"- `{path}`" for path in affected_paths)
    if inspect_paths:
        lines.extend(["", "## Recommended files to inspect before editing", ""])
        lines.extend(f"{index}. `{path}`" for index, path in enumerate(inspect_paths, start=1))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    elif not resolved:
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                "- No reliable topic was found; inspect the repository rather than guessing.",
            ]
        )
    lines.extend(["", "## Preflight Verdict", "", verdict, ""])
    return verdict, "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("knowledge/project_graph.yaml"))
    parser.add_argument("--aliases", type=Path, default=Path("knowledge/topic_aliases.yaml"))
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--topic", action="append")
    selector.add_argument("--task")
    parser.add_argument("--format", choices=("markdown",), default="markdown")
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        help="Capture a content-free task baseline in the repository's Git-local metadata.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = args.graph.resolve()
    aliases_path = args.aliases.resolve()
    try:
        graph = load_yaml(graph_path)
        validate_graph(graph, graph_path)
        aliases = load_aliases(aliases_path)
        current_git = git_state(Path(graph["snapshot"]["project_root"]).resolve())
        verdict, output = build_preflight(
            graph,
            graph_path=graph_path,
            aliases=aliases,
            task=args.task,
            explicit_topics=args.topic,
            current_git=current_git,
        )
        if args.capture_baseline:
            root = Path(graph["snapshot"]["project_root"]).resolve()
            baseline_path, baseline = capture_baseline(root)
            output = output.rstrip() + "\n\n## Task Baseline\n\n"
            output += f"- status: `TASK_BASELINE_CAPTURED`\n- path: `{baseline_path}`\n"
            output += f"- branch: `{baseline['branch']}`\n- HEAD: `{baseline['head']}`\n"
            output += (
                f"- pre-existing dirty paths captured: `{len(baseline['working_tree_files'])}`\n"
            )
    except (OSError, GraphValidationError, BaselineError, ValueError) as exc:
        print(
            "# Engineering Preflight\n\n## Preflight Verdict\n\nGRAPH_INVALID\n\n"
            f"## Warnings\n\n- {exc}\n",
            file=sys.stderr,
        )
        return 2
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
