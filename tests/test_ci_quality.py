from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def _toml() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _yaml(path: str) -> dict:
    return yaml.load(
        (ROOT / path).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def _steps(job: dict) -> list[dict]:
    return job["steps"]


def _step_with_name(job: dict, name: str) -> dict:
    return next(step for step in _steps(job) if step.get("name") == name)


def _has_import(nodes: list[ast.AST], module: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(alias.name == "Traversable" for alias in node.names)
        for node in nodes
    )


def test_pyproject_has_explicit_p2_quality_boundaries() -> None:
    project = _toml()
    dev_dependencies = set(project["project"]["optional-dependencies"]["dev"])
    for package in (
        "pytest",
        "pytest-cov",
        "coverage[toml]",
        "ruff",
        "mypy",
        "pre-commit",
        "build",
        "twine",
        "tomli",
        "uvicorn",
    ):
        assert any(item.startswith(f"{package}") for item in dev_dependencies)

    ruff = project["tool"]["ruff"]
    assert set(ruff["include"]) == {
        "src/along_street_resources/**/*.py",
        "src/agents/official_character_authoring.py",
        "src/knowledge/loader.py",
        "src/reference_corpus/loader.py",
        "src/persistence/**/*.py",
        "src/runtime_paths/**/*.py",
        "scripts/ci/**/*.py",
        "tests/test_ci_quality.py",
        "tests/test_cli_startup.py",
        "tests/test_game_ai_agent_cli.py",
        "tests/test_web_api.py",
        "tests/test_persistence_foundation.py",
        "tests/test_runtime_paths.py",
        "src/web/**/*.py",
    }
    assert {"E4", "E7", "E9", "F", "I"} <= set(ruff["lint"]["select"])

    mypy = project["tool"]["mypy"]
    assert mypy["python_version"] == "3.10"
    assert mypy["mypy_path"] == "src"
    assert mypy["follow_imports"] == "skip"
    assert "ignore_missing_imports" not in mypy
    assert "files" not in mypy
    assert "overrides" not in project["tool"]["mypy"]

    coverage = project["tool"]["coverage"]["report"]
    assert isinstance(coverage["fail_under"], (int, float))
    assert not isinstance(coverage["fail_under"], bool)
    assert coverage["fail_under"] == 81
    assert set(project["tool"]["coverage"]["run"]["source"]) == {
        "along_street_resources",
        "knowledge",
        "reference_corpus",
        "story",
    }


def test_workflow_has_gated_cross_platform_matrix_and_installed_smoke() -> None:
    workflow = _yaml(".github/workflows/ci.yml")
    triggers = workflow.get("on") or workflow.get(True)
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] in {True, "true"}

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "quality",
        "ekl-portability",
        "test",
        "platform-smoke",
        "frontend",
        "frontend-platform-smoke",
        "build",
        "installed-smoke",
        "browser-e2e",
        "studio-startup-smoke",
        "final-platform-acceptance",
        "ci-success",
    }

    quality = jobs["quality"]
    quality_uses = [step.get("uses", "") for step in _steps(quality)]
    assert "actions/checkout@v6" in quality_uses
    assert "actions/setup-python@v6" in quality_uses
    assert quality["timeout-minutes"] == "15"
    assert any("cache" in step.get("with", {}) for step in _steps(quality))
    assert any("pre_commit run --all-files" in step.get("run", "") for step in _steps(quality))

    ekl = jobs["ekl-portability"]
    assert ekl["runs-on"] == "ubuntu-latest"
    assert any(step.get("with", {}).get("python-version") == "3.13" for step in _steps(ekl))
    ekl_text = "\n".join(step.get("run", "") for step in _steps(ekl))
    for marker in (
        "tests/test_project_graph.py",
        "tests/test_project_preflight.py",
        "tests/test_project_postflight.py",
        "--capture-baseline",
        "--from-baseline",
    ):
        assert marker in ekl_text
    assert "python -m pytest" in ekl_text
    assert "Run full test suite" not in ekl_text

    test_job = jobs["test"]
    assert test_job["needs"] == "quality"
    assert test_job["strategy"]["matrix"]["python-version"] == ["3.10", "3.13", "3.14"]
    assert test_job["env"]["NPC_RUN_LIVE_SMOKE"] == "0"
    assert test_job["env"]["NPC_LLM_API_KEY"] == ""
    coverage_step = _step_with_name(test_job, "Run runtime boundary coverage on Python 3.13")
    assert "matrix.python-version == '3.13'" in coverage_step["if"]
    assert "--cov=knowledge" in coverage_step["run"]
    assert "--cov=reference_corpus" in coverage_step["run"]
    assert "tests/test_runtime_resources.py" in coverage_step["run"]
    plain_step = _step_with_name(test_job, "Run full test suite")
    assert "if" not in plain_step
    assert plain_step["run"] == "python -m pytest"

    platform_smoke = jobs["platform-smoke"]
    assert platform_smoke["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    ]
    assert any(
        step.get("with", {}).get("python-version") == "3.13" for step in _steps(platform_smoke)
    )
    platform_text = "\n".join(step.get("run", "") for step in _steps(platform_smoke))
    assert "scripts/ci/platform_smoke.py" in platform_text
    assert "platform.machine" in platform_text
    assert platform_smoke["env"]["NPC_RUN_LIVE_SMOKE"] == "0"

    frontend = jobs["frontend"]
    frontend_uses = [step.get("uses", "") for step in _steps(frontend)]
    assert "actions/setup-node@v6" in frontend_uses
    node_setup = next(
        step for step in _steps(frontend) if step.get("uses") == "actions/setup-node@v6"
    )
    assert node_setup["with"]["node-version"] == "22"
    assert node_setup["with"]["cache-dependency-path"] == "web/package-lock.json"
    frontend_text = "\n".join(step.get("run", "") for step in _steps(frontend))
    for command in ("npm ci", "npm test", "npm run typecheck", "npm run lint", "npm run build"):
        assert command in frontend_text
    assert frontend["defaults"]["run"]["working-directory"] == "web"

    frontend_platform = jobs["frontend-platform-smoke"]
    assert frontend_platform["strategy"]["matrix"]["os"] == ["windows-latest", "macos-latest"]
    assert frontend_platform["defaults"]["run"]["working-directory"] == "web"
    frontend_platform_text = "\n".join(step.get("run", "") for step in _steps(frontend_platform))
    assert "npm ci" in frontend_platform_text
    assert "npm run build" in frontend_platform_text

    build = jobs["build"]
    assert set(build["needs"]) == {"quality", "test"}
    assert any("python -m build" in step.get("run", "") for step in _steps(build))
    assert any("twine check dist/*" in step.get("run", "") for step in _steps(build))
    upload = next(
        step for step in _steps(build) if step.get("uses") == "actions/upload-artifact@v7"
    )

    smoke = jobs["installed-smoke"]
    assert smoke["needs"] == "build"
    assert smoke["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    ]
    download = next(
        step for step in _steps(smoke) if step.get("uses") == "actions/download-artifact@v8"
    )
    assert download["with"]["name"] == upload["with"]["name"] == "python-dist"
    smoke_text = "\n".join(step.get("run", "") for step in _steps(smoke))
    assert "scripts/ci/run_installed_smoke.py" in smoke_text
    assert "dist/*.whl" not in smoke_text
    assert 'cd "$smoke_cwd"' not in smoke_text

    browser = jobs["browser-e2e"]
    assert browser["needs"] == "frontend"
    assert browser["runs-on"] == "ubuntu-latest"
    browser_uses = [step.get("uses", "") for step in _steps(browser)]
    assert "actions/setup-node@v6" in browser_uses
    browser_text = "\n".join(step.get("run", "") for step in _steps(browser))
    assert "npm ci" in browser_text
    assert "playwright install --with-deps chromium" in browser_text
    assert "npm run e2e" in browser_text
    assert browser["env"]["NPC_RUN_LIVE_SMOKE"] == "0"
    assert "GAME_AI_AGENT_DB_PATH" not in browser["env"]
    browser_flow = _step_with_name(browser, "Run offline browser flow")
    assert browser_flow["env"]["GAME_AI_AGENT_DB_PATH"] == "${{ runner.temp }}/s5c-browser.db"

    startup = jobs["studio-startup-smoke"]
    assert startup["needs"] == "frontend"
    assert startup["runs-on"] == "ubuntu-latest"
    startup_text = "\n".join(step.get("run", "") for step in _steps(startup))
    assert "npm ci" in startup_text
    assert "npm run build" in startup_text
    assert "scripts/ci/studio_startup_smoke.py" in startup_text

    acceptance = jobs["final-platform-acceptance"]
    assert acceptance["needs"] == "quality"
    assert acceptance["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    ]
    assert acceptance["timeout-minutes"] == "20"
    assert acceptance["env"]["NPC_RUN_LIVE_SMOKE"] == "0"
    acceptance_text = "\n".join(step.get("run", "") for step in _steps(acceptance))
    assert 'python-version: "3.13"' not in acceptance_text
    assert "scripts/ci/final_platform_acceptance.py" in acceptance_text
    assert any(
        step.get("with", {}).get("node-version") == "22"
        for step in _steps(acceptance)
        if step.get("uses") == "actions/setup-node@v6"
    )

    success = jobs["ci-success"]
    assert "always()" in success["if"]
    required_jobs = {
        "quality",
        "ekl-portability",
        "test",
        "platform-smoke",
        "frontend",
        "frontend-platform-smoke",
        "build",
        "installed-smoke",
        "browser-e2e",
        "studio-startup-smoke",
        "final-platform-acceptance",
    }
    assert set(success["needs"]) == required_jobs
    success_text = "\n".join(step.get("if", "") for step in _steps(success))
    for job_name in required_jobs:
        assert f"needs.{job_name}.result" in success_text
    assert "!= 'success'" in success_text


def test_traversable_import_has_python_310_compatibility_fallback() -> None:
    paths = (
        "src/along_street_resources/__init__.py",
        "src/knowledge/loader.py",
        "src/reference_corpus/loader.py",
        "src/agents/official_character_authoring.py",
        "scripts/ci/validate_runtime.py",
    )

    for relative_path in paths:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        compatibility_blocks = [
            node
            for node in tree.body
            if isinstance(node, ast.Try)
            and _has_import(node.body, "importlib.resources.abc")
            and any(
                isinstance(handler.type, ast.Name)
                and handler.type.id == "ModuleNotFoundError"
                and _has_import(handler.body, "importlib.abc")
                for handler in node.handlers
            )
        ]
        assert len(compatibility_blocks) == 1, relative_path

        compatibility_block = compatibility_blocks[0]
        fallback_imports = [
            node
            for handler in compatibility_block.handlers
            if isinstance(handler.type, ast.Name) and handler.type.id == "ModuleNotFoundError"
            for node in ast.walk(handler)
            if isinstance(node, ast.ImportFrom) and node.module == "importlib.abc"
        ]
        all_legacy_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "importlib.abc"
        ]
        assert len(fallback_imports) == 1, relative_path
        assert all_legacy_imports == fallback_imports, relative_path


def test_test_job_checkout_fetches_full_history_for_provenance() -> None:
    workflow = _yaml(".github/workflows/ci.yml")
    checkout = _step_with_name(workflow["jobs"]["test"], "Check out repository")
    assert checkout["uses"] == "actions/checkout@v6"
    assert checkout["with"]["fetch-depth"] == "0"


def test_pre_commit_is_scoped_and_runs_offline_local_guards() -> None:
    config = _yaml(".pre-commit-config.yaml")
    repos = config["repos"]
    hooks_repo = next(
        repo for repo in repos if repo["repo"] == "https://github.com/pre-commit/pre-commit-hooks"
    )
    assert hooks_repo["rev"] == "v6.0.0"
    assert {hook["id"] for hook in hooks_repo["hooks"]} >= {
        "check-ast",
        "check-toml",
        "check-yaml",
    }

    ruff_repo = next(repo for repo in repos if "ruff-pre-commit" in repo["repo"])
    assert ruff_repo["rev"] == "v0.16.4"
    ruff_hook = next(hook for hook in ruff_repo["hooks"] if hook["id"] == "ruff-check")
    assert re.search(
        r"src/along_street_resources.*official_character_authoring.*knowledge/loader"
        r".*reference_corpus/loader.*scripts/ci.*ci_quality.*cli_startup",
        ruff_hook["files"],
    )

    local = next(repo for repo in repos if repo["repo"] == "local")
    local_hooks = {hook["id"]: hook for hook in local["hooks"]}
    assert "src/along_street_resources scripts/ci" in local_hooks["mypy-ci-scope"]["entry"]
    assert local_hooks["mypy-ci-scope"]["language"] == "python"
    assert local_hooks["mypy-ci-scope"]["additional_dependencies"] == [
        "mypy>=1.13,<2",
        "fastapi>=0.115,<1",
    ]
    assert "scripts/ci/validate_runtime.py" in local_hooks["runtime-data-validation"]["entry"]
    assert local_hooks["runtime-data-validation"]["language"] == "python"
    assert "--model', 'offline" in local_hooks["offline-cli-source-smoke"]["entry"]
    assert "sys.path.insert" in local_hooks["offline-cli-source-smoke"]["entry"]
    assert local_hooks["offline-cli-source-smoke"]["language"] == "python"
    assert "pytest" not in (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")


def test_ci_scripts_lock_runtime_and_wheel_smoke_contracts() -> None:
    runtime = (ROOT / "scripts/ci/validate_runtime.py").read_text(encoding="utf-8")
    for marker in (
        "load_canon",
        "load_story_repository",
        "load_reference_grounding",
        "load_corpus_manifest",
        'EXPECTED_MANIFEST_BASELINE = "reference-corpus-v0.5"',
        "EXPECTED_RECORD_COUNT = 16",
        "data_root()",
    ):
        assert marker in runtime

    smoke = (ROOT / "scripts/ci/installed_smoke.py").read_text(encoding="utf-8")
    assert "sysconfig.get_path" in smoke
    assert "Path(sys.executable).resolve().parent" not in smoke
    for marker in (
        "from validate_runtime import validate_runtime",
        "relative_to(SOURCE_ROOT)",
        "--help",
        "--scenario",
        "console_script_offline",
        "TemporaryDirectory",
        "outside the repository checkout",
        "game-ai-agent",
        "doctor",
        "unified_cli",
    ):
        assert marker in smoke


def test_installed_smoke_finds_console_script_in_installation_scripts_directory(
    tmp_path, monkeypatch
) -> None:
    smoke_path = ROOT / "scripts/ci/installed_smoke.py"
    spec = importlib.util.spec_from_file_location("installed_smoke", smoke_path)
    assert spec is not None
    assert spec.loader is not None
    installed_smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installed_smoke)

    base_interpreter_dir = tmp_path / "base-interpreter"
    scripts_dir = tmp_path / "venv" / "Scripts"
    base_interpreter_dir.mkdir()
    scripts_dir.mkdir(parents=True)
    base_interpreter = base_interpreter_dir / "python"
    console_script = scripts_dir / "along-street-character-author"
    console_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(installed_smoke.sys, "executable", str(base_interpreter))
    monkeypatch.setattr(installed_smoke.sysconfig, "get_path", lambda name: str(scripts_dir))

    assert installed_smoke._console_command() == [str(console_script)]
