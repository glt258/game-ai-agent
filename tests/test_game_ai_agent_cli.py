from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _environment(*, cwd: Path | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("NPC_LLM_API_KEY", None)
    environment.pop("DEEPSEEK_API_KEY", None)
    return environment


def _run_cli(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, "-m", "game_ai_agent", *args],
        cwd=cwd or ROOT,
        env=env or _environment(cwd=cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def test_help_and_unknown_command_exit_codes() -> None:
    help_result = _run_cli("--help")
    assert help_result.returncode == 0
    assert "doctor" in help_result.stdout
    assert "studio" in help_result.stdout

    unknown_result = _run_cli("unknown")
    assert unknown_result.returncode == 2


def test_doctor_json_distinguishes_core_and_studio_readiness() -> None:
    result = _run_cli("doctor", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["core_ready"] is True
    expected_studio_ready = (ROOT / "web" / ".next").is_dir()
    assert payload["studio_ready"] is expected_studio_ready
    assert payload["status"] in {"ready", "ready_with_warnings"}
    assert {check["name"] for check in payload["checks"]} >= {
        "python",
        "runtime_resources",
        "sqlite",
        "database_path",
        "fastapi",
        "frontend",
        "frontend_build",
        "provider",
    }


def test_doctor_redacts_provider_secret() -> None:
    environment = _environment()
    environment["OPENAI_API_KEY"] = "super-secret-provider-value"
    result = _run_cli("doctor", "--json", env=environment)

    assert result.returncode == 0
    assert "super-secret-provider-value" not in result.stdout
    payload = json.loads(result.stdout)
    provider = next(check for check in payload["checks"] if check["name"] == "provider")
    assert provider["status"] == "info"
    assert provider["message"] == "Provider configuration is configured."


def test_installed_style_doctor_does_not_require_repository(tmp_path: Path) -> None:
    result = _run_cli("doctor", "--json", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["core_ready"] is True
    assert payload["studio_ready"] is False
    assert any(check["name"] == "frontend" and check["status"] == "warn" for check in payload["checks"])


def test_studio_outside_checkout_fails_without_traceback(tmp_path: Path) -> None:
    result = _run_cli("studio", "--no-browser", cwd=tmp_path)

    assert result.returncode == 1
    assert "source checkout" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_port_conflict_is_detected_before_startup() -> None:
    from game_ai_agent.studio import is_port_available

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        host, port = listener.getsockname()
        assert is_port_available(host, port) is False


def test_launcher_uses_portable_commands_and_child_environment(tmp_path: Path) -> None:
    from game_ai_agent.studio import (
        StudioConfig,
        build_backend_command,
        build_child_environment,
        build_frontend_command,
    )

    config = StudioConfig(
        repository_root=tmp_path,
        backend_host="127.0.0.1",
        backend_port=8123,
        frontend_host="127.0.0.1",
        frontend_port=3123,
        db_path=tmp_path / "studio.db",
        no_browser=True,
    )
    backend = build_backend_command(config)
    frontend = build_frontend_command(config, "npm.cmd")

    assert backend[:4] == [sys.executable, "-m", "uvicorn", "web.app:create_app"]
    assert "--reload" not in backend
    assert frontend[:3] == ["npm.cmd", "run", "start"]
    assert frontend[-4:] == ["--hostname", "127.0.0.1", "--port", "3123"]
    environment = build_child_environment(config)
    assert environment["BACKEND_API_URL"] == "http://127.0.0.1:8123"
    assert environment["GAME_AI_AGENT_DB_PATH"] == str(tmp_path / "studio.db")


class _FakeProcess:
    def __init__(self, pid: int = 1) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return None


def _checkout_fixture(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "web" / ".next").mkdir()


def test_launcher_cleans_backend_when_frontend_readiness_fails(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    processes = []
    terminated = []
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(
        studio,
        "_popen",
        lambda command, cwd, environment: processes.append(_FakeProcess(len(processes) + 1)) or processes[-1],
    )

    def readiness(process, url, timeout, label):
        if label == "Frontend":
            raise studio.StudioError("frontend failed")

    monkeypatch.setattr(studio, "_wait_for_url", readiness)
    monkeypatch.setattr(studio, "_terminate", lambda process: terminated.append(process))

    result = studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True))

    assert result == 1
    assert len(processes) == 2
    assert terminated == [processes[1], processes[0]]


def test_launcher_handles_backend_readiness_timeout_without_starting_frontend(
    tmp_path: Path, monkeypatch
) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    processes = []
    terminated = []
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(
        studio,
        "_popen",
        lambda command, cwd, environment: processes.append(_FakeProcess()) or processes[-1],
    )
    monkeypatch.setattr(
        studio,
        "_wait_for_url",
        lambda *args: (_ for _ in ()).throw(studio.StudioError("timeout")),
    )
    monkeypatch.setattr(studio, "_terminate", lambda process: terminated.append(process))

    assert studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True)) == 1
    assert len(processes) == 1
    assert terminated == [None, processes[0]]


def test_launcher_reports_backend_start_failure_without_traceback(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(studio, "_popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing uvicorn")))

    assert studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True)) == 1


def test_launcher_does_not_open_browser_in_no_browser_mode(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    process = _FakeProcess()
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(studio, "_popen", lambda command, cwd, environment: process)
    monkeypatch.setattr(studio, "_wait_for_url", lambda *args: None)
    monkeypatch.setattr(studio.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    opened = []
    monkeypatch.setattr(studio.webbrowser, "open", opened.append)
    monkeypatch.setattr(studio, "_terminate", lambda process: None)

    assert studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True)) == 0
    assert opened == []


def test_launcher_converts_windows_ctrl_break_into_controlled_shutdown(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    backend, frontend = _FakeProcess(1), _FakeProcess(2)
    processes = [backend, frontend]
    terminated = []
    signal_calls = []
    previous_handler = object()
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(studio, "_popen", lambda *args, **kwargs: processes.pop(0))
    monkeypatch.setattr(studio, "_wait_for_url", lambda *args: None)
    monkeypatch.setattr(studio, "_terminate", lambda process: terminated.append(process))
    monkeypatch.setattr(studio, "_is_windows", lambda: True)
    monkeypatch.setattr(studio.signal, "SIGBREAK", 21, raising=False)

    def fake_signal(signum, handler):
        signal_calls.append((signum, handler))
        return previous_handler

    monkeypatch.setattr(studio.signal, "signal", fake_signal)

    def trigger_ctrl_break(_seconds):
        assert signal_calls, "the launcher must install a Windows shutdown handler"
        signal_calls[0][1](studio.signal.SIGBREAK, None)

    monkeypatch.setattr(studio.time, "sleep", trigger_ctrl_break)

    assert studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True)) == 0
    assert terminated == [frontend, backend]
    assert len(signal_calls) == 2
    assert signal_calls[1] == (studio.signal.SIGBREAK, previous_handler)


def test_launcher_cleanup_is_idempotent_with_partial_children(monkeypatch) -> None:
    from game_ai_agent import studio

    class StoppableProcess:
        def __init__(self) -> None:
            self.alive = True
            self.signals = []

        def poll(self) -> int | None:
            return None if self.alive else 0

        def send_signal(self, signum: int) -> None:
            self.signals.append(signum)
            self.alive = False

        def wait(self, timeout: float) -> int:
            del timeout
            return 0

    monkeypatch.setattr(studio, "_is_windows", lambda: True)
    monkeypatch.setattr(studio.signal, "CTRL_BREAK_EVENT", 21, raising=False)
    backend = StoppableProcess()

    studio._shutdown_children(None, backend)
    studio._shutdown_children(None, backend)

    assert backend.signals == [21]


def test_launcher_rejects_missing_node_before_startup(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)
    monkeypatch.setattr(studio, "find_npm_executable", lambda: None)
    with pytest.raises(studio.StudioError, match="npm is required"):
        studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True))


def test_launcher_cleans_sibling_when_backend_dies_unexpectedly(tmp_path: Path, monkeypatch) -> None:
    from game_ai_agent import studio

    _checkout_fixture(tmp_path)

    class DyingProcess(_FakeProcess):
        def poll(self) -> int | None:
            return 9

    backend = DyingProcess()
    frontend = _FakeProcess()
    processes = iter((backend, frontend))
    terminated = []
    monkeypatch.setattr(studio, "find_npm_executable", lambda: "npm")
    monkeypatch.setattr(studio, "is_port_available", lambda host, port: True)
    monkeypatch.setattr(studio, "_popen", lambda command, cwd, environment: next(processes))
    monkeypatch.setattr(studio, "_wait_for_url", lambda *args: None)
    monkeypatch.setattr(studio, "_terminate", lambda process: terminated.append(process))

    assert studio.run_studio(studio.StudioConfig(tmp_path, no_browser=True)) == 1
    assert terminated == [frontend, backend]


def test_doctor_distinguishes_old_node_and_missing_npm(monkeypatch) -> None:
    from game_ai_agent import doctor

    monkeypatch.setattr(doctor.shutil, "which", lambda name: "node" if name == "node" else None)
    monkeypatch.setattr(doctor, "_node_version", lambda: (20, 8))
    assert doctor._check_node().status == "warn"
    assert doctor._check_npm().status == "warn"
