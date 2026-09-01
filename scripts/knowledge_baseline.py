"""Git-local, content-free task baseline support."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASELINE_SCHEMA_VERSION = "engineering-task-baseline/0.1"
BASELINE_RELATIVE_PATH = "game-ai-agent/engineering-preflight-baseline.json"


class BaselineError(ValueError):
    """Raised when a task baseline is missing or invalid."""


@dataclass(frozen=True)
class BaselineFile:
    status: str
    path: str
    fingerprint: str
    old_path: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {
            "status": self.status,
            "path": self.path,
            "fingerprint": self.fingerprint,
        }
        if self.old_path:
            result["old_path"] = self.old_path
        return result


def _decode(value: bytes | str) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _run_git(root: Path, args: list[str], runner: Callable[..., Any]) -> str:
    result = runner(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    output = result.stdout if hasattr(result, "stdout") else result
    return _decode(output).strip("\0\r\n")


def baseline_path(root: Path, runner: Callable[..., Any] = subprocess.run) -> Path:
    """Resolve the baseline through Git, including worktree-aware repositories."""

    raw_path = _run_git(root, ["rev-parse", "--git-path", BASELINE_RELATIVE_PATH], runner)
    if not raw_path:
        raise BaselineError("Git did not return a baseline path")
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def _status_code(status: str) -> str:
    if "R" in status:
        return "R"
    if "D" in status:
        return "D"
    if "?" in status:
        return "??"
    return "A" if "A" in status else "M"


def parse_status_z(output: str) -> list[BaselineFile]:
    tokens = [token for token in output.split("\0") if token]
    records: list[BaselineFile] = []
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
                raise BaselineError(f"Malformed Git status record: {raw!r}")
            path = tokens[index]
            index += 1
        if status == "R":
            if index >= len(tokens):
                raise BaselineError(f"Malformed Git rename record: {raw!r}")
            new_path = tokens[index]
            index += 1
            records.append(BaselineFile(status, new_path, "", old_path=path))
        else:
            records.append(BaselineFile(status, path, ""))
    return records


def fingerprint_file(root: Path, relative_path: str) -> str:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise BaselineError(f"Baseline path escapes repository: {relative_path}") from exc
    if not path.is_file():
        return "deleted"
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def current_files(root: Path, runner: Callable[..., Any] = subprocess.run) -> list[BaselineFile]:
    raw = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        runner,
    )
    return [
        BaselineFile(
            record.status,
            record.path,
            fingerprint_file(root, record.path),
            old_path=record.old_path,
        )
        for record in parse_status_z(raw)
    ]


def capture_baseline(
    root: Path,
    *,
    captured_at: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[Path, dict[str, Any]]:
    files = sorted(current_files(root, runner), key=lambda item: (item.path, item.old_path or ""))
    document: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "captured_at": captured_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "branch": _run_git(root, ["branch", "--show-current"], runner) or "detached",
        "head": _run_git(root, ["rev-parse", "HEAD"], runner),
        "working_tree": "dirty" if files else "clean",
        "working_tree_files": [item.as_dict() for item in files],
    }
    path = baseline_path(root, runner)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path, document


def load_baseline(
    root: Path, runner: Callable[..., Any] = subprocess.run
) -> tuple[Path, dict[str, Any]]:
    path = baseline_path(root, runner)
    if not path.is_file():
        raise BaselineError(f"TASK_BASELINE_NOT_FOUND: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"Invalid task baseline: {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise BaselineError(f"Unsupported task baseline schema: {path}")
    if not isinstance(document.get("working_tree_files"), list):
        raise BaselineError(f"Task baseline files must be a list: {path}")
    return path, document


def clear_baseline(root: Path, runner: Callable[..., Any] = subprocess.run) -> Path:
    path = baseline_path(root, runner)
    if path.exists():
        path.unlink()
    return path


def task_delta(
    root: Path,
    baseline: dict[str, Any],
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> list[BaselineFile]:
    """Return only files whose Git status or current fingerprint differs from baseline."""

    baseline_files = {
        item["path"]: BaselineFile(
            item["status"],
            item["path"],
            item["fingerprint"],
            old_path=item.get("old_path"),
        )
        for item in baseline["working_tree_files"]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    current = current_files(root, runner)
    delta: list[BaselineFile] = []
    for item in current:
        previous = baseline_files.get(item.path)
        same_fingerprint = previous and previous.fingerprint == item.fingerprint
        staging_only_status_change = previous and {previous.status, item.status} <= {"A", "??"}
        if (
            previous
            and previous.old_path == item.old_path
            and (
                previous.status == item.status or (same_fingerprint and staging_only_status_change)
            )
            and same_fingerprint
        ):
            continue
        delta.append(item)
    for path, previous in baseline_files.items():
        if not any(item.path == path for item in current):
            delta.append(BaselineFile("D", path, "deleted", old_path=previous.old_path))
    return sorted(delta, key=lambda item: (item.path, item.old_path or ""))


def baseline_branch_mismatch(baseline: dict[str, Any], current_branch: str) -> bool:
    return baseline.get("branch") != current_branch
