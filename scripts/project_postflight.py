"""Deterministic, read-only audit of Git changes against the engineering graph."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .knowledge_baseline import (
        BaselineError,
        baseline_branch_mismatch,
        clear_baseline,
        load_baseline,
        task_delta,
    )
    from .project_graph_lib import is_architecture_path, is_knowledge_path, normalize_path
except ImportError:  # pragma: no cover - exercised by direct CLI invocation.
    from knowledge_baseline import (  # type: ignore[no-redef]
        BaselineError,
        baseline_branch_mismatch,
        clear_baseline,
        load_baseline,
        task_delta,
    )
    from project_graph_lib import (  # type: ignore[no-redef]
        is_architecture_path,
        is_knowledge_path,
        normalize_path,
    )

try:  # Direct execution puts scripts/ on sys.path; tests import scripts as a namespace package.
    from .query_project_graph import (
        GraphValidationError,
        git_state,
        load_yaml,
        snapshot_warnings,
        validate_graph,
    )
except ImportError:  # pragma: no cover - exercised by the direct CLI invocation.
    from query_project_graph import (  # type: ignore[no-redef]
        GraphValidationError,
        git_state,
        load_yaml,
        snapshot_warnings,
        validate_graph,
    )


SIGNAL_PATTERNS = {
    "class": re.compile(r"\bclass\s+[A-Za-z_]\w*"),
    "enum": re.compile(r"\bEnum\b"),
    "literal": re.compile(r"\bLiteral\b"),
    "canonical_constant": re.compile(r"\bCANONICAL_[A-Z0-9_]+\b"),
    "schema_version": re.compile(r"\bschema_version\b"),
    "protocol": re.compile(r"\bProtocol\b|\bprotocol\b"),
    "validator": re.compile(r"\bvalidator\b|\bvalidate\w*\b"),
    "compiler": re.compile(r"\bcompiler\b|\bcompile\w*\b"),
    "contract": re.compile(r"\bcontract\b|\bContract\b"),
    "serialization": re.compile(r"\b(to_dict|from_mapping|model_dump|BaseModel|dataclass)\b"),
}


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str | None = None

    @property
    def is_added(self) -> bool:
        return self.status in {"A", "??"}

    @property
    def is_deleted(self) -> bool:
        return self.status == "D"

    @property
    def is_renamed(self) -> bool:
        return self.status == "R"


class PostflightError(ValueError):
    """Raised when postflight input cannot be safely interpreted."""


def _decode_output(value: bytes | str) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _run_git(root: Path, args: list[str], runner: Callable[..., Any]) -> str:
    result = runner(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return _decode_output(result.stdout if hasattr(result, "stdout") else result).strip("\0\r\n")


def _status_code(status: str) -> str:
    if "R" in status:
        return "R"
    if "D" in status:
        return "D"
    if "A" in status or "?" in status:
        return "A" if "?" not in status else "??"
    return "M"


def parse_porcelain_z(output: str) -> list[Change]:
    tokens = [token for token in output.split("\0") if token]
    changes: list[Change] = []
    index = 0
    while index < len(tokens):
        raw = tokens[index]
        index += 1
        if len(raw) >= 3 and raw[2] == " ":
            status = _status_code(raw[:2])
            path = raw[3:]
        else:
            status = _status_code(raw)
            if index >= len(tokens):
                raise PostflightError(f"Malformed Git status record: {raw!r}")
            path = tokens[index]
            index += 1
        if status == "R":
            if index >= len(tokens):
                raise PostflightError(f"Malformed rename record: {raw!r}")
            changes.append(Change("R", tokens[index], old_path=path))
            index += 1
        else:
            changes.append(Change(status, path))
    return changes


def parse_name_status_z(output: str) -> list[Change]:
    tokens = [token for token in output.split("\0") if token]
    changes: list[Change] = []
    index = 0
    while index < len(tokens):
        raw = tokens[index]
        index += 1
        if "\t" in raw:
            status_raw, path = raw.split("\t", 1)
        else:
            status_raw = raw
            if index >= len(tokens):
                raise PostflightError(f"Malformed Git name-status record: {raw!r}")
            path = tokens[index]
            index += 1
        status = _status_code(status_raw)
        if status == "R":
            if index >= len(tokens):
                raise PostflightError(f"Malformed rename record: {raw!r}")
            changes.append(Change("R", tokens[index], old_path=path))
            index += 1
        else:
            changes.append(Change(status, path))
    return changes


def collect_changes(
    root: Path,
    *,
    staged: bool = False,
    base: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> list[Change]:
    if staged and base:
        raise PostflightError("--staged and --base are mutually exclusive")
    if base:
        output = _run_git(root, ["diff", "--name-status", "-z", base], runner)
        changes = parse_name_status_z(output)
        untracked = _run_git(
            root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner
        )
        changes.extend(change for change in parse_porcelain_z(untracked) if change.is_added)
        return changes
    if staged:
        return parse_name_status_z(
            _run_git(root, ["diff", "--cached", "--name-status", "-z"], runner)
        )
    return parse_porcelain_z(
        _run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner)
    )


def path_matches(changed_path: str, reference_path: str) -> bool:
    changed = normalize_path(changed_path)
    reference = normalize_path(reference_path).rstrip("/")
    return changed == reference or changed.startswith(reference + "/")


def graph_references(graph: dict[str, Any]) -> list[tuple[str, str, str]]:
    references: list[tuple[str, str, str]] = []
    for node in graph["nodes"]:
        node_id = node["id"]
        for field in ("path", "canonical_source"):
            if node.get(field):
                references.append((node_id, field, node[field]))
        for evidence in node.get("evidence", []):
            references.append((node_id, "evidence", evidence["path"]))
        for test_path in node.get("tests", []):
            references.append((node_id, "test", test_path))
    for collection_name in ("constraints", "known_limitations", "architecture_decisions"):
        for item in graph.get(collection_name, []):
            item_id = item["id"]
            for evidence in item.get("evidence", []):
                references.append((item_id, "evidence", evidence["path"]))
    return references


def changed_paths(change: Change) -> tuple[str, ...]:
    return (change.path, change.old_path) if change.old_path else (change.path,)


def referenced_by_change(change: Change, reference: str) -> bool:
    return any(path_matches(path, reference) for path in changed_paths(change))


def current_content(root: Path, path: str) -> str | None:
    file_path = root / path
    if not file_path.is_file():
        return None
    return file_path.read_text(encoding="utf-8", errors="replace")


def git_content(root: Path, spec: str, path: str, runner: Callable[..., Any]) -> str | None:
    try:
        object_path = f":{path}" if spec == ":" else f"{spec}:{path}"
        result = runner(
            ["git", "-C", str(root), "show", object_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    output = result.stdout if hasattr(result, "stdout") else result
    return _decode_output(output)


class _DocstringStripper(ast.NodeTransformer):
    def _strip(self, node: ast.AST) -> ast.AST:
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and _is_docstring(body[0]):
            body.pop(0)
        return self.generic_visit(node)

    visit_Module = _strip
    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip
    visit_ClassDef = _strip


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(getattr(node, "value", None), ast.Constant)
        and isinstance(node.value.value, str)
    )


def _normalized_python(content: str) -> str | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    return ast.dump(_DocstringStripper().visit(tree), include_attributes=False)


def material_change(path: str, old_content: str | None, new_content: str | None) -> bool:
    if old_content is None or new_content is None:
        return old_content != new_content
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        old_tree = _normalized_python(old_content)
        new_tree = _normalized_python(new_content)
        return old_tree is None or new_tree is None or old_tree != new_tree
    if suffix == ".json":
        try:
            return json.loads(old_content) != json.loads(new_content)
        except json.JSONDecodeError:
            return old_content.strip() != new_content.strip()
    if suffix in {".yaml", ".yml"}:
        try:
            return yaml.safe_load(old_content) != yaml.safe_load(new_content)
        except yaml.YAMLError:
            return old_content.strip() != new_content.strip()
    return old_content.strip() != new_content.strip()


def diff_signals(old_content: str | None, new_content: str | None) -> list[str]:
    text = "\n".join(value for value in (old_content, new_content) if value)
    return sorted(name for name, pattern in SIGNAL_PATTERNS.items() if pattern.search(text))


def schema_sensitive(path: str, signals: list[str]) -> bool:
    normalized = normalize_path(path)
    suffix = Path(normalized).suffix
    return (
        suffix in {".json", ".yaml", ".yml"}
        or bool(
            {"schema_version", "serialization", "protocol", "contract", "enum", "literal"}
            & set(signals)
        )
        or any(
            token in normalized
            for token in ("schema", "contract", "response_contract", "models.py")
        )
    )


def _impact(
    category: str,
    severity: str,
    message: str,
    *,
    paths: set[str] | None = None,
    nodes: set[str] | None = None,
    material: bool | None = None,
    signals: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "message": message,
        "paths": sorted(paths or set()),
        "nodes": sorted(nodes or set()),
        "material": material,
        "signals": sorted(signals or set()),
    }


def analyze_changes(
    graph: dict[str, Any],
    changes: list[Change],
    *,
    root: Path,
    old_spec: str = "HEAD",
    staged: bool = False,
    runner: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    references = graph_references(graph)
    nodes = {node["id"]: node for node in graph["nodes"]}
    impacts: list[dict[str, Any]] = []
    has_canonical_change = False
    has_test_change = False
    canonical_nodes_changed: set[str] = set()

    for change in changes:
        path = change.path
        old_path = change.old_path or path
        old_content = git_content(root, old_spec, old_path, runner)
        if change.is_added:
            old_content = None
        if staged:
            new_content = git_content(root, ":", path, runner)
        else:
            new_content = current_content(root, path)
        material = material_change(path, old_content, new_content)
        signals = set(diff_signals(old_content, new_content))

        canonical_refs = [
            (node_id, reference)
            for node_id, kind, reference in references
            if kind == "canonical_source" and referenced_by_change(change, reference)
        ]
        if canonical_refs:
            has_canonical_change = True
            node_ids = {node_id for node_id, _ in canonical_refs}
            canonical_nodes_changed.update(node_ids)
            impacts.append(
                _impact(
                    "K1",
                    "HIGH",
                    "CANONICAL SOURCE CHANGED",
                    paths={path, *(reference for _, reference in canonical_refs)},
                    nodes=node_ids,
                    material=material,
                    signals=signals,
                )
            )

        frozen_refs = [
            (node_id, kind, reference)
            for node_id, kind, reference in references
            if (
                kind != "test"
                and referenced_by_change(change, reference)
                and nodes.get(node_id, {}).get("status") == "frozen"
                and (
                    kind != "evidence"
                    or any(
                        token in normalize_path(reference)
                        for token in ("freeze", "contract", "schema")
                    )
                )
            )
        ]
        if frozen_refs:
            node_ids = {node_id for node_id, _, _ in frozen_refs}
            impacts.append(
                _impact(
                    "K2",
                    "HIGH",
                    "FROZEN CONTRACT MAY HAVE CHANGED",
                    paths={path, *(reference for _, _, reference in frozen_refs)},
                    nodes=node_ids,
                    material=material,
                    signals=signals,
                )
            )

        test_refs = [
            (node_id, reference)
            for node_id, kind, reference in references
            if kind == "test" and referenced_by_change(change, reference)
        ]
        if test_refs:
            has_test_change = True
            impacts.append(
                _impact(
                    "K3",
                    "HIGH" if canonical_refs else "MEDIUM",
                    "ARCHITECTURE PROTECTION TEST CHANGED",
                    paths={path, *(reference for _, reference in test_refs)},
                    nodes={node_id for node_id, _ in test_refs},
                    material=material,
                    signals=signals,
                )
            )

        if change.is_deleted or change.is_renamed:
            stale_refs = [
                (node_id, kind, reference)
                for node_id, kind, reference in references
                if path_matches(change.old_path or change.path, reference)
            ]
            if stale_refs:
                impacts.append(
                    _impact(
                        "K4",
                        "HIGH",
                        "GRAPH REFERENCE STALE",
                        paths={
                            change.old_path or path,
                            path,
                            *(reference for _, _, reference in stale_refs),
                        },
                        nodes={node_id for node_id, _, _ in stale_refs},
                    )
                )

        related_nodes = {
            node_id
            for node_id, _, reference in references
            if referenced_by_change(change, reference)
        }
        if change.is_added and is_architecture_path(path) and not related_nodes:
            impacts.append(
                _impact(
                    "K5",
                    "MEDIUM",
                    "POSSIBLE NEW ARCHITECTURE COMPONENT",
                    paths={path},
                )
            )

        experimental_nodes = {
            node_id
            for node_id, _, reference in references
            if nodes.get(node_id, {}).get("status") == "experimental"
            and referenced_by_change(change, reference)
        }
        experimental_path = any(
            normalize_path(candidate).startswith(
                ("src/web/", "web/", "docs/w4_", "docs/character_kit")
            )
            for candidate in changed_paths(change)
        )
        if experimental_nodes or experimental_path:
            impacts.append(
                _impact(
                    "K6",
                    "MEDIUM",
                    "EXPERIMENTAL ARCHITECTURE CHANGED",
                    paths={path},
                    nodes=experimental_nodes,
                )
            )

        provider_nodes = {
            node_id
            for node_id, _, reference in references
            if referenced_by_change(change, reference)
            and (
                "provider" in node_id.lower()
                or "llm" in node_id.lower()
                or "provider" in str(nodes.get(node_id, {}).get("name", "")).lower()
                or "llm" in str(nodes.get(node_id, {}).get("name", "")).lower()
            )
        }
        if provider_nodes:
            impacts.append(
                _impact(
                    "K7",
                    "MEDIUM",
                    "PROVIDER ARCHITECTURE MAY HAVE CHANGED",
                    paths={path},
                    nodes=provider_nodes,
                    material=material,
                    signals=signals,
                )
            )

        limitation_ids = {
            item["id"]
            for item in graph.get("known_limitations", [])
            if any(
                referenced_by_change(change, evidence["path"])
                for evidence in item.get("evidence", [])
            )
        }
        if limitation_ids:
            impacts.append(
                _impact(
                    "K8",
                    "MEDIUM",
                    "KNOWN LIMITATION REQUIRES REVIEW",
                    paths={path},
                    nodes=limitation_ids,
                )
            )

        adr_ids = {
            item["id"]
            for item in graph.get("architecture_decisions", [])
            if any(
                referenced_by_change(change, evidence["path"])
                for evidence in item.get("evidence", [])
            )
        }
        if adr_ids:
            impacts.append(
                _impact(
                    "K9",
                    "MEDIUM",
                    "ARCHITECTURE DECISION REQUIRES REVIEW",
                    paths={path},
                    nodes=adr_ids,
                )
            )

        if is_knowledge_path(path):
            impacts.append(
                _impact(
                    "KNOWLEDGE_LAYER",
                    "MEDIUM",
                    "ENGINEERING KNOWLEDGE LAYER CHANGED",
                    paths={path},
                )
            )

        if frozen_refs and material and schema_sensitive(path, list(signals)):
            impacts.append(
                _impact(
                    "SCHEMA_CONTRACT",
                    "HIGH",
                    "SCHEMA / CONTRACT REVIEW REQUIRED",
                    paths={path},
                    nodes={node_id for node_id, _, _ in frozen_refs},
                    material=True,
                    signals=signals,
                )
            )

    if has_canonical_change and has_test_change:
        impacts.append(
            _impact(
                "K3_ESCALATION",
                "HIGH",
                "CANONICAL SOURCE AND ARCHITECTURE PROTECTION TEST CHANGED TOGETHER",
                nodes=canonical_nodes_changed,
            )
        )
    return impacts


def dedupe_impacts(impacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for impact in impacts:
        key = json.dumps(
            {
                field: impact[field]
                for field in ("category", "severity", "message", "material", "signals")
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        if key not in grouped:
            grouped[key] = {
                **impact,
                "paths": list(impact["paths"]),
                "nodes": list(impact["nodes"]),
                "signals": list(impact["signals"]),
            }
            continue
        existing = grouped[key]
        existing["paths"] = sorted(set(existing["paths"]) | set(impact["paths"]))
        existing["nodes"] = sorted(set(existing["nodes"]) | set(impact["nodes"]))
        existing["signals"] = sorted(set(existing["signals"]) | set(impact["signals"]))
    return sorted(
        grouped.values(),
        key=lambda item: (item["category"], item["severity"], item["message"], item["paths"]),
    )


def sync_verdict(graph_valid: bool, impacts: list[dict[str, Any]]) -> str:
    if not graph_valid:
        return "GRAPH_INVALID"
    if any(impact["category"] == "K4" for impact in impacts):
        return "KNOWLEDGE_UPDATE_REQUIRED"
    if any(
        impact["category"] in {"K1", "K2", "SCHEMA_CONTRACT"} and impact.get("material") is True
        for impact in impacts
    ):
        return "KNOWLEDGE_UPDATE_REQUIRED"
    if impacts:
        return "REVIEW_RECOMMENDED"
    return "IN_SYNC"


def suggested_actions(graph: dict[str, Any], impacts: list[dict[str, Any]]) -> list[str]:
    actions: set[str] = set()
    node_by_id = {node["id"]: node for node in graph["nodes"]}
    for impact in impacts:
        for node_id in impact.get("nodes", []):
            if node_id in node_by_id:
                actions.add(f"Review node {node_id}")
        if impact["category"] == "K4":
            actions.add("Update stale graph path references before the next release snapshot")
        elif impact["category"] == "K5":
            actions.add("Review whether the new architecture-sensitive file needs a graph node")
        elif impact["category"] == "K6":
            actions.add("Review docs/project_memory/current_state.md")
        elif impact["category"] == "K8":
            actions.add(
                "Review the affected known limitation evidence; do not change status automatically"
            )
        elif impact["category"] == "K9":
            actions.add(
                "Review the affected ADR; decide whether it remains valid or needs supersession"
            )
        elif impact["category"] == "KNOWLEDGE_LAYER":
            actions.add(
                "Validate the changed Engineering Knowledge Layer files and snapshot metadata"
            )
    return sorted(actions)


def changes_from_baseline(root: Path, baseline: dict[str, Any]) -> list[Change]:
    """Convert content-free baseline delta records into the existing audit model."""

    return [
        Change(item.status, item.path, old_path=item.old_path)
        for item in task_delta(root, baseline)
    ]


def render_markdown(
    *,
    graph: dict[str, Any],
    changes: list[Change],
    impacts: list[dict[str, Any]],
    verdict: str,
    current_git: dict[str, str],
    graph_valid: bool = True,
    graph_error: str | None = None,
    warnings: list[str] | None = None,
    baseline_path: Path | None = None,
) -> str:
    impacts = dedupe_impacts(impacts)
    lines = ["# Engineering Knowledge Postflight", "", "## Snapshot", ""]
    snapshot = graph.get("snapshot", {})
    for key in (
        "project",
        "branch",
        "base_head",
        "release_tag",
        "working_tree",
        "snapshot_kind",
        "release_equivalent",
    ):
        lines.append(f"- graph {key}: `{snapshot.get(key)}`")
    for key in ("branch", "head", "working_tree"):
        lines.append(f"- current git {key}: `{current_git.get(key)}`")
    if baseline_path:
        lines.append(f"- task baseline: `{baseline_path}`")
        lines.append("- Postflight analyzes only the Git delta after the captured task baseline.")
    else:
        lines.append("- Postflight analyzes current Git state, not task provenance.")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(["", "## Git Change Summary", ""])
    counts: dict[str, int] = {}
    for change in changes:
        counts[change.status] = counts.get(change.status, 0) + 1
    lines.append(f"- changed paths: `{len(changes)}`")
    lines.extend(f"- status `{status}`: `{counts[status]}`" for status in sorted(counts))
    if changes:
        lines.append("- paths: " + ", ".join(f"`{change.path}`" for change in changes[:30]))
        if len(changes) > 30:
            lines.append(f"- additional paths omitted from summary: `{len(changes) - 30}`")

    lines.extend(["", "## Knowledge Impact Summary", ""])
    if impacts:
        lines.extend(
            f"- `{impact['category']}` [{impact['severity']}]: {impact['message']}"
            for impact in impacts
        )
    else:
        lines.append("- No graph-linked knowledge impact detected.")

    sections = {
        "Canonical Source Changes": {"K1", "K3_ESCALATION"},
        "Frozen Contract Risks": {"K2", "SCHEMA_CONTRACT"},
        "Graph Reference Risks": {"K4"},
        "Experimental Architecture Changes": {"K5", "K6"},
        "Known Limitation Reviews": {"K8"},
        "ADR Reviews": {"K9"},
    }
    for title, categories in sections.items():
        selected = [impact for impact in impacts if impact["category"] in categories]
        if selected:
            lines.extend(["", f"## {title}", ""])
            for impact in selected:
                lines.append(
                    f"- `{impact['category']}` [{impact['severity']}]: {impact['message']}"
                )
                if impact["nodes"]:
                    lines.append(f"  - nodes: {', '.join(f'`{node}`' for node in impact['nodes'])}")
                if impact["signals"]:
                    lines.append(f"  - signals: {', '.join(impact['signals'])}")
                if impact["material"] is not None:
                    lines.append(f"  - material_change: `{impact['material']}`")

    actions = suggested_actions(graph, impacts)
    if actions:
        lines.extend(["", "## Suggested Knowledge Actions", ""])
        lines.extend(f"- {action}" for action in actions)
    lines.extend(["", "## Knowledge Sync Verdict", "", verdict])
    if not graph_valid and graph_error:
        lines.extend(["", "## Graph Validation Error", "", graph_error])
    return "\n".join(lines) + "\n"


def invalid_report(graph: dict[str, Any], error: Exception, current_git: dict[str, str]) -> str:
    return render_markdown(
        graph=graph,
        changes=[],
        impacts=[],
        verdict="GRAPH_INVALID",
        current_git=current_git,
        graph_valid=False,
        graph_error=str(error),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("knowledge/project_graph.yaml"))
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--base")
    mode.add_argument(
        "--from-baseline",
        action="store_true",
        help="Analyze only the delta after the Preflight-captured task baseline.",
    )
    mode.add_argument(
        "--clear-baseline",
        action="store_true",
        help="Delete the active Git-local task baseline.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = args.graph.resolve()
    root = graph_path.parent.parent.resolve()
    if args.clear_baseline:
        try:
            path = clear_baseline(root)
        except (OSError, BaselineError, subprocess.CalledProcessError) as exc:
            print(f"TASK_BASELINE_CLEAR_FAILED: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps({"verdict": "TASK_BASELINE_CLEARED", "path": str(path)}))
        else:
            print(
                "# Engineering Knowledge Postflight\n\n"
                "## Task Baseline\n\n"
                f"- status: `TASK_BASELINE_CLEARED`\n- path: `{path}`\n",
                end="",
            )
        return 0
    try:
        graph = load_yaml(graph_path)
        validate_graph(graph, graph_path)
        current_git = git_state(root)
        baseline_path: Path | None = None
        warnings = snapshot_warnings(graph["snapshot"], current_git, root=root)
        if args.from_baseline:
            baseline_path, baseline = load_baseline(root)
            if baseline_branch_mismatch(baseline, current_git["branch"]):
                raise BaselineError(
                    "TASK_BASELINE_BRANCH_MISMATCH: "
                    f"baseline `{baseline.get('branch')}` vs current `{current_git['branch']}`"
                )
            changes = changes_from_baseline(root, baseline)
            if baseline.get("head") != current_git.get("head"):
                warnings.append("TASK BASELINE HEAD DIFFERS FROM CURRENT HEAD")
        else:
            changes = collect_changes(root, staged=args.staged, base=args.base)
        impacts = dedupe_impacts(
            analyze_changes(
                graph,
                changes,
                root=root,
                old_spec=args.base or "HEAD",
                staged=args.staged,
            )
        )
        verdict = sync_verdict(True, impacts)
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "verdict": verdict,
                        "changed_files": [change.__dict__ for change in changes],
                        "impacts": impacts,
                        "warnings": warnings,
                        "suggested_actions": suggested_actions(graph, impacts),
                        "baseline_path": str(baseline_path) if baseline_path else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(
                render_markdown(
                    graph=graph,
                    changes=changes,
                    impacts=impacts,
                    verdict=verdict,
                    current_git=current_git,
                    warnings=warnings,
                    baseline_path=baseline_path,
                ),
                end="",
            )
        return 0
    except BaselineError as exc:
        if args.format == "json":
            print(json.dumps({"verdict": str(exc).split(":", 1)[0], "error": str(exc)}))
        else:
            print(f"# Engineering Knowledge Postflight\n\n## Knowledge Sync Verdict\n\n{exc}\n")
        return 2
    except (OSError, GraphValidationError, PostflightError, subprocess.CalledProcessError) as exc:
        try:
            graph = load_yaml(graph_path)
        except Exception:
            graph = {"snapshot": {}}
        try:
            current_git = git_state(root)
        except Exception:
            current_git = {"branch": "unknown", "head": "unknown", "working_tree": "unknown"}
        print(invalid_report(graph, exc, current_git), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
