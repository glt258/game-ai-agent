from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _source_checkout_python() -> str:
    """Prefer the repository venv so an installed package cannot mask startup."""

    return str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))


def _source_checkout_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _run_script(relative_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_source_checkout_python(), str(ROOT / relative_path), *args],
        cwd=ROOT,
        env=_source_checkout_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _probe_top_level_import(relative_path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _source_checkout_python(),
            "-c",
            "import runpy, sys; runpy.run_path(sys.argv[1], run_name='startup_probe')",
            str(ROOT / relative_path),
        ],
        cwd=ROOT,
        env=_source_checkout_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _failure_details(result: subprocess.CompletedProcess[str]) -> str:
    return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_character_generation_demo_starts_from_source_checkout_as_json() -> None:
    result = _run_script(
        "scripts/demo_character_generation_v0_1.py",
        "--model",
        "offline",
        "--json",
    )

    assert result.returncode == 0, _failure_details(result)
    payload = json.loads(result.stdout)
    assert payload["status"] == "draft"
    assert payload["draft_id"]


@pytest.mark.parametrize(
    ("script", "args"),
    (
        (
            "scripts/demo_canon_checker_v0_1.py",
            ("--case", "good", "--json"),
        ),
        (
            "scripts/demo_character_generation_v0_1.py",
            ("--model", "offline", "--json"),
        ),
        (
            "scripts/demo_character_repair_v0_1.py",
            ("--case", "pass", "--model", "offline", "--json"),
        ),
        ("scripts/run_canon_checker_evals.py", ()),
        ("scripts/run_canon_checker_live_language_evals.py", ()),
        ("scripts/run_canon_checker_redteam.py", ()),
        ("scripts/run_character_generation_evals.py", ()),
        ("scripts/run_character_repair_evals.py", ()),
        ("scripts/run_character_repair_redteam.py", ()),
        ("scripts/run_character_skill_s2_shadow_evidence.py", ()),
    ),
)
def test_problem_scripts_bootstrap_before_top_level_business_imports(
    script: str,
    args: tuple[str, ...],
) -> None:
    del args
    source = (ROOT / script).read_text(encoding="utf-8")
    business_imports = tuple(
        offset
        for package in ("agents", "knowledge", "story", "evals")
        for marker in (f"from {package}", f"import {package}")
        if (offset := source.find(marker)) >= 0
    )
    assert business_imports, f"{script} has no recognized business import"
    assert source.find('ROOT / "src"') < min(business_imports)
    assert source.find("sys.path.insert") < min(business_imports)

    result = _probe_top_level_import(script)

    assert result.returncode == 0, _failure_details(result)


def test_pyproject_registers_only_the_production_character_authoring_cli() -> None:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"] == {
        "along-street-character-author": "agents.official_character_authoring:main",
    }
