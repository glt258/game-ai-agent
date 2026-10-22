from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.knowledge_baseline import (
    BaselineError,
    baseline_branch_mismatch,
    baseline_path,
    capture_baseline,
    load_baseline,
    task_delta,
)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Baseline Test")
    (tmp_path / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.py")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def test_capture_records_existing_dirty_tracked_file_without_raw_content(tmp_path: Path) -> None:
    root = repo(tmp_path)
    secret = "TOP_SECRET_VALUE_DO_NOT_SERIALIZE"
    (root / "tracked.py").write_text(f"SECRET = {secret!r}\n", encoding="utf-8")

    path, document = capture_baseline(root, captured_at="2026-09-01T12:00:00+08:00")
    text = path.read_text(encoding="utf-8")

    assert document["working_tree_files"][0]["status"] == "M"
    assert document["working_tree_files"][0]["fingerprint"].startswith("sha256:")
    assert secret not in text
    assert "SECRET" not in text


def test_unchanged_dirty_and_untracked_files_are_excluded_from_delta(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "existing.txt").write_text("existing\n", encoding="utf-8")
    _, baseline = capture_baseline(root, captured_at="fixed")

    assert task_delta(root, baseline) == []


def test_staging_preexisting_untracked_file_without_content_change_is_excluded(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    target = root / "existing.txt"
    target.write_text("existing\n", encoding="utf-8")
    _, baseline = capture_baseline(root, captured_at="fixed")
    git(root, "add", "existing.txt")

    assert task_delta(root, baseline) == []


@pytest.mark.parametrize(
    "filename,initial,updated",
    [("tracked.py", "VALUE = 2\n", "VALUE = 3\n"), ("existing.txt", "existing\n", "changed\n")],
)
def test_preexisting_file_modified_again_is_task_delta(
    tmp_path: Path, filename: str, initial: str, updated: str
) -> None:
    root = repo(tmp_path)
    target = root / filename
    target.write_text(initial, encoding="utf-8")
    _, baseline = capture_baseline(root, captured_at="fixed")
    target.write_text(updated, encoding="utf-8")

    delta = task_delta(root, baseline)
    expected_status = "M" if filename == "tracked.py" else "??"
    assert [(item.status, item.path) for item in delta] == [(expected_status, filename)]


def test_new_and_deleted_files_are_task_delta(tmp_path: Path) -> None:
    root = repo(tmp_path)
    _, baseline = capture_baseline(root, captured_at="fixed")
    (root / "new.py").write_text("VALUE = 3\n", encoding="utf-8")
    (root / "tracked.py").unlink()

    delta = task_delta(root, baseline)
    assert {(item.status, item.path) for item in delta} == {("??", "new.py"), ("D", "tracked.py")}


def test_baseline_serialization_is_deterministic(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    path, first = capture_baseline(root, captured_at="fixed")
    first_bytes = path.read_bytes()
    _, second = capture_baseline(root, captured_at="fixed")

    assert first == second
    assert first_bytes == path.read_bytes()


def test_missing_baseline_is_explicit(tmp_path: Path) -> None:
    root = repo(tmp_path)
    with pytest.raises(BaselineError, match="TASK_BASELINE_NOT_FOUND"):
        load_baseline(root)


def test_branch_mismatch_is_visible_in_baseline_metadata(tmp_path: Path) -> None:
    root = repo(tmp_path)
    _, baseline = capture_baseline(root, captured_at="fixed")
    baseline["branch"] = "another-branch"
    assert baseline_branch_mismatch(baseline, "main")


def test_baseline_path_is_git_local(tmp_path: Path) -> None:
    root = repo(tmp_path)
    path = baseline_path(root)
    raw_git_dir = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--git-dir"], text=True
    ).strip()
    git_dir = (root / raw_git_dir).resolve()
    assert path.is_relative_to(git_dir)
