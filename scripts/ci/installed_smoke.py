"""Smoke-test a wheel installation from outside the repository checkout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = (REPOSITORY_ROOT / "src").resolve()
SCRIPT_ROOT = Path(__file__).resolve().parent


def _assert_installed_module_sources() -> None:
    import agents.official_character_authoring as authoring
    import along_street_resources as resources
    import character_intelligence.intent.parser as intent_parser
    import knowledge.loader as knowledge_loader
    import reference_corpus.loader as reference_loader
    import story.loader as story_loader

    modules: tuple[tuple[str, ModuleType], ...] = (
        ("agents.official_character_authoring", authoring),
        ("along_street_resources", resources),
        ("character_intelligence.intent.parser", intent_parser),
        ("knowledge.loader", knowledge_loader),
        ("reference_corpus.loader", reference_loader),
        ("story.loader", story_loader),
    )
    for name, module in modules:
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            raise RuntimeError(f"module has no file: {name}")
        resolved_file = Path(module_file).resolve()
        try:
            resolved_file.relative_to(SOURCE_ROOT)
        except ValueError:
            continue
        raise RuntimeError(f"{name} was imported from the repository source tree")


def _console_command(name: str = "along-street-character-author") -> list[str]:
    scripts_dir = Path(sysconfig.get_path("scripts"))
    candidates = (
        scripts_dir / name,
        scripts_dir / f"{name}.exe",
        scripts_dir / f"{name}.cmd",
    )
    for candidate in candidates:
        if candidate.is_file():
            if candidate.suffix.lower() == ".cmd":
                return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(candidate)]
            return [str(candidate)]
    raise RuntimeError(
        "console script not found in installation scripts directory "
        f"{scripts_dir}: {name}"
    )


def _run_console(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for key in ("NPC_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        environment.pop(key, None)
    environment["NPC_RUN_LIVE_SMOKE"] = "0"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    command = _console_command()
    return subprocess.run(
        [*command, *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def _run_unified_console(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for key in ("NPC_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        environment.pop(key, None)
    environment["NPC_RUN_LIVE_SMOKE"] = "0"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [*_console_command("game-ai-agent"), *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def _run_console_smoke(cwd: Path) -> None:
    help_result = _run_console(cwd, "--help")
    if help_result.returncode != 0:
        raise RuntimeError(
            "installed console script --help failed:\n"
            f"stdout={help_result.stdout}\nstderr={help_result.stderr}"
        )
    offline_result = _run_console(
        cwd,
        "--scenario",
        "valid",
        "--model",
        "offline",
        "--json",
    )
    if offline_result.returncode != 0:
        raise RuntimeError(
            "installed console script offline smoke failed:\n"
            f"stdout={offline_result.stdout}\nstderr={offline_result.stderr}"
        )
    payload = json.loads(offline_result.stdout)
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("installed console script returned no JSON object")


def _run_unified_cli_smoke(cwd: Path) -> None:
    help_result = _run_unified_console(cwd, "--help")
    if help_result.returncode != 0:
        raise RuntimeError(f"game-ai-agent --help failed: {help_result.stderr}")
    doctor_result = _run_unified_console(cwd, "doctor", "--json")
    if doctor_result.returncode != 0:
        raise RuntimeError(f"installed game-ai-agent doctor failed: {doctor_result.stderr}")
    payload = json.loads(doctor_result.stdout)
    if payload.get("core_ready") is not True or payload.get("studio_ready") is not False:
        raise RuntimeError(f"unexpected installed doctor readiness: {payload}")
    outside_result = _run_unified_console(cwd, "studio", "--no-browser")
    combined = f"{outside_result.stdout}\n{outside_result.stderr}"
    if outside_result.returncode != 1 or "source checkout" not in combined.lower():
        raise RuntimeError(f"installed Studio boundary check failed: {combined}")
    if "traceback" in combined.lower():
        raise RuntimeError("installed Studio boundary emitted a traceback")


def _run_runtime_persistence_smoke() -> None:
    from agents.character_generation import CharacterDraft
    from persistence import PersistenceUnitOfWork

    with tempfile.TemporaryDirectory(prefix="along-street-runtime-测试-") as target_name:
        database_path = Path(target_name) / "中文" / "studio.db"
        draft = CharacterDraft(draft_id="draft_installed_smoke", status="draft", name="测试角色")
        with PersistenceUnitOfWork(database_path) as unit:
            created = unit.characters.create(draft)
            if unit.schema_version != 4:
                raise RuntimeError("installed runtime did not bootstrap schema v4")
        with PersistenceUnitOfWork(database_path) as unit:
            restored = unit.characters.get_character(created.character_id)
        if restored.current_revision.draft.name != "测试角色":
            raise RuntimeError("installed runtime Character round-trip lost Unicode content")


def main() -> int:
    if REPOSITORY_ROOT == Path.cwd().resolve() or REPOSITORY_ROOT in Path.cwd().resolve().parents:
        raise RuntimeError("installed smoke must run outside the repository checkout")
    if str(SCRIPT_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_ROOT))

    _assert_installed_module_sources()
    from runtime_paths import resolve_database_path

    if (
        resolve_database_path(environ={"GAME_AI_AGENT_DB_PATH": str(Path.cwd() / "explicit.db")})
        != Path.cwd() / "explicit.db"
    ):
        raise RuntimeError("installed runtime database override resolution failed")
    _run_runtime_persistence_smoke()
    from validate_runtime import validate_runtime

    summary = validate_runtime()
    with tempfile.TemporaryDirectory(prefix="along-street-smoke-cwd-") as smoke_name:
        smoke_cwd = Path(smoke_name).resolve()
        _run_console_smoke(smoke_cwd)
        _run_unified_cli_smoke(smoke_cwd)
    summary = {
        **summary,
        "console_script_help": True,
        "console_script_offline": True,
        "unified_cli": True,
        "doctor": True,
        "installed_modules": True,
        "runtime_persistence": True,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
