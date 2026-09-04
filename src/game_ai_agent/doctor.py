from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from runtime_paths import resolve_database_path

CheckStatus = Literal["pass", "warn", "fail", "info"]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    message: str
    scope: Literal["core", "studio", "info"]

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "message": self.message}


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]
    core_ready: bool
    studio_ready: bool

    @property
    def status(self) -> str:
        if not self.core_ready:
            return "blocked"
        if self.studio_ready and not any(check.status == "warn" for check in self.checks):
            return "ready"
        return "ready_with_warnings"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "core_ready": self.core_ready,
            "studio_ready": self.studio_ready,
            "checks": [check.as_dict() for check in self.checks],
        }


def find_source_checkout(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "web" / "package.json").is_file()
            and (candidate / "src").is_dir()
        ):
            return candidate
    return None


def _check_python() -> DoctorCheck:
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        return DoctorCheck("python", "fail", f"Python {current} is unsupported; Python >= 3.10 is required.", "core")
    return DoctorCheck("python", "pass", f"Python {current} is supported.", "core")


def _check_runtime_resources() -> DoctorCheck:
    try:
        from along_street_resources import data_resource
        from reference_corpus.loader import load_corpus_manifest

        manifest = load_corpus_manifest(
            data_resource("reference_corpus", "characters", "_catalog", "corpus_manifest.yaml")
        )
        return DoctorCheck(
            "runtime_resources",
            "pass",
            f"Runtime resources are available ({manifest.record_count} reference records).",
            "core",
        )
    except Exception as error:
        return DoctorCheck("runtime_resources", "fail", f"Runtime resources unavailable: {error}", "core")


def _check_sqlite() -> DoctorCheck:
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("select 1")
        return DoctorCheck("sqlite", "pass", "SQLite can create, write and close a temporary database.", "core")
    except Exception as error:
        return DoctorCheck("sqlite", "fail", f"SQLite unavailable: {error}", "core")


def _check_database_path() -> DoctorCheck:
    try:
        database_path = resolve_database_path()
        parent = database_path.parent
        probe = parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        if not probe.is_dir() or not os.access(probe, os.W_OK):
            return DoctorCheck("database_path", "fail", f"Database parent is not writable or creatable: {parent}", "core")
        return DoctorCheck("database_path", "pass", f"Database path is writable or creatable: {database_path}", "core")
    except Exception as error:
        return DoctorCheck("database_path", "fail", f"Database path cannot be resolved: {error}", "core")


def _check_import(name: str, label: str, scope: Literal["core", "studio"]) -> DoctorCheck:
    try:
        importlib.import_module(name)
        return DoctorCheck(name.replace(".", "_"), "pass", f"{label} import is available.", scope)
    except Exception as error:
        return DoctorCheck(name.replace(".", "_"), "fail", f"{label} import failed: {error}", scope)


def _node_version() -> tuple[int, int] | None:
    executable = shutil.which("node")
    if executable is None:
        return None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=3, check=False)
        value = result.stdout.strip().lstrip("v").split(".")
        return int(value[0]), int(value[1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def _check_node() -> DoctorCheck:
    executable = shutil.which("node")
    if executable is None:
        return DoctorCheck("node", "warn", "Node.js is unavailable; Studio cannot start.", "studio")
    parsed = _node_version()
    if parsed is None or parsed < (20, 9):
        return DoctorCheck("node", "warn", "Node.js is older than the supported >= 20.9.0 contract.", "studio")
    version_text = f"{parsed[0]}.{parsed[1]}"
    if parsed[0] != 22:
        return DoctorCheck("node", "warn", f"Node.js {version_text} is supported; 22.x is recommended.", "studio")
    return DoctorCheck("node", "pass", f"Node.js {version_text} is supported and recommended.", "studio")


def _check_npm() -> DoctorCheck:
    executable = shutil.which("npm") or shutil.which("npm.cmd")
    if executable is None:
        return DoctorCheck("npm", "warn", "npm is unavailable; Studio cannot start.", "studio")
    return DoctorCheck("npm", "pass", f"npm executable is available: {executable}", "studio")


def _check_frontend(repository_root: Path | None) -> DoctorCheck:
    if repository_root is None:
        return DoctorCheck("frontend", "warn", "Studio frontend is not included in this Python installation.", "studio")
    return DoctorCheck("frontend", "pass", f"Source-checkout frontend is present: {repository_root / 'web'}", "studio")


def _check_frontend_build(repository_root: Path | None) -> DoctorCheck:
    if repository_root is None:
        return DoctorCheck("frontend_build", "warn", "Frontend production build is unavailable outside a source checkout.", "studio")
    build_path = repository_root / "web" / ".next"
    if not build_path.is_dir():
        return DoctorCheck("frontend_build", "warn", "Frontend production build is missing. Run: cd web; npm ci; npm run build", "studio")
    return DoctorCheck("frontend_build", "pass", "Frontend production build is present.", "studio")


def _check_git_and_graph(repository_root: Path | None) -> tuple[DoctorCheck, DoctorCheck]:
    if repository_root is None:
        return (
            DoctorCheck("git", "info", "Git is not required for installed core runtime.", "info"),
            DoctorCheck("project_graph", "info", "Project Graph is only checked inside a source checkout.", "info"),
        )
    git_check = (
        DoctorCheck("git", "pass", "Git is available for repository tooling.", "info")
        if shutil.which("git")
        else DoctorCheck("git", "warn", "Git is unavailable; repository tooling is limited.", "info")
    )
    graph_path = repository_root / "knowledge" / "project_graph.yaml"
    try:
        from scripts.query_project_graph import load_yaml, validate_graph

        validate_graph(load_yaml(graph_path), graph_path)
        graph_check = DoctorCheck("project_graph", "pass", "Project Graph exists and validates.", "info")
    except Exception as error:
        graph_check = DoctorCheck("project_graph", "warn", f"Project Graph validation unavailable: {error}", "info")
    return git_check, graph_check


def _check_provider() -> DoctorCheck:
    configured = any(os.environ.get(key) for key in ("OPENAI_API_KEY", "NPC_LLM_API_KEY", "DEEPSEEK_API_KEY"))
    message = "Provider configuration is configured." if configured else "Provider configuration is not configured; offline mode remains available."
    return DoctorCheck("provider", "info", message, "info")


def _check_ports(repository_root: Path | None) -> DoctorCheck:
    if repository_root is None:
        return DoctorCheck("ports", "info", "Studio ports are not required for core runtime.", "info")
    from .studio import is_port_available

    occupied = [
        f"{host}:{port}"
        for host, port in (("127.0.0.1", 8000), ("127.0.0.1", 3000))
        if not is_port_available(host, port)
    ]
    if occupied:
        return DoctorCheck("ports", "warn", f"Studio port(s) already in use: {', '.join(occupied)}", "studio")
    return DoctorCheck("ports", "pass", "Studio default ports 127.0.0.1:8000 and 127.0.0.1:3000 are available.", "studio")


def run_doctor() -> DoctorReport:
    repository_root = find_source_checkout()
    checks = [
        _check_python(),
        _check_runtime_resources(),
        _check_sqlite(),
        _check_database_path(),
        _check_import("fastapi", "FastAPI", "core"),
        _check_import("web.app", "FastAPI backend", "core"),
        _check_node(),
        _check_npm(),
        _check_frontend(repository_root),
        _check_frontend_build(repository_root),
    ]
    git_check, graph_check = _check_git_and_graph(repository_root)
    checks.extend((git_check, graph_check, _check_provider(), _check_ports(repository_root)))
    core_ready = not any(check.scope == "core" and check.status == "fail" for check in checks)
    studio_ready = (
        core_ready
        and repository_root is not None
        and all(check.status == "pass" for check in checks if check.name in {"node", "npm", "frontend", "frontend_build", "ports"})
    )
    return DoctorReport(tuple(checks), core_ready=core_ready, studio_ready=studio_ready)


def main(*, json_output: bool = False) -> int:
    try:
        report = run_doctor()
    except Exception as error:
        if json_output:
            print(json.dumps({"status": "blocked", "core_ready": False, "studio_ready": False, "checks": [], "error": str(error)}))
        else:
            print(f"Doctor failed: {error}", file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print("Game AI Agent Doctor")
        for check in report.checks:
            print(f"[{check.status.upper()}] {check.name}: {check.message}")
        print(f"Core runtime: {'READY' if report.core_ready else 'BLOCKED'}")
        print(f"Studio: {'READY' if report.studio_ready else 'NOT READY'}")
        print(f"Result: {report.status.upper()}")
    return 0 if report.core_ready else 1
