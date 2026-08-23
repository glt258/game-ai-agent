"""Smoke-test a wheel installation from outside the repository checkout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _console_command() -> list[str]:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = (
        executable_dir / "along-street-character-author",
        executable_dir / "along-street-character-author.exe",
        executable_dir / "along-street-character-author.cmd",
    )
    for candidate in candidates:
        if candidate.is_file():
            if candidate.suffix.lower() == ".cmd":
                return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(candidate)]
            return [str(candidate)]
    raise RuntimeError(
        "console script not found beside the smoke interpreter: "
        "along-street-character-author"
    )


def _run_console(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for key in ("NPC_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        environment.pop(key, None)
    environment["NPC_RUN_LIVE_SMOKE"] = "0"
    command = _console_command()
    return subprocess.run(
        [*command, *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
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


def main() -> int:
    if REPOSITORY_ROOT == Path.cwd().resolve() or REPOSITORY_ROOT in Path.cwd().resolve().parents:
        raise RuntimeError("installed smoke must run outside the repository checkout")
    if str(SCRIPT_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_ROOT))

    _assert_installed_module_sources()
    from validate_runtime import validate_runtime

    summary = validate_runtime()
    with tempfile.TemporaryDirectory(prefix="along-street-smoke-cwd-") as smoke_name:
        smoke_cwd = Path(smoke_name).resolve()
        _run_console_smoke(smoke_cwd)
    summary = {
        **summary,
        "console_script_help": True,
        "console_script_offline": True,
        "installed_modules": True,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
