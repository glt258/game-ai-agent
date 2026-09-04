from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from runtime_paths import resolve_database_path

DEFAULT_STARTUP_TIMEOUTS = {"backend": 30.0, "frontend": 60.0}


class StudioError(RuntimeError):
    """Raised for a clear, user-actionable Studio startup failure."""


@dataclass(frozen=True)
class StudioConfig:
    repository_root: Path
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 3000
    db_path: str | Path | None = None
    no_browser: bool = False


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, port))
        except OSError:
            return False
    return True


def find_npm_executable() -> str | None:
    return shutil.which("npm") or shutil.which("npm.cmd")


def build_backend_command(config: StudioConfig) -> list[str]:
    return [sys.executable, "-m", "uvicorn", "web.app:create_app", "--factory", "--host", config.backend_host, "--port", str(config.backend_port)]


def build_frontend_command(config: StudioConfig, npm_executable: str) -> list[str]:
    return [npm_executable, "run", "start", "--", "--hostname", config.frontend_host, "--port", str(config.frontend_port)]


def build_child_environment(config: StudioConfig) -> dict[str, str]:
    environment = os.environ.copy()
    environment["BACKEND_API_URL"] = f"http://{config.backend_host}:{config.backend_port}"
    if config.db_path is not None:
        environment["GAME_AI_AGENT_DB_PATH"] = str(config.db_path)
    source_root = str(config.repository_root / "src")
    environment["PYTHONPATH"] = os.pathsep.join(path for path in (source_root, environment.get("PYTHONPATH")) if path)
    return environment


def _popen(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            shell=False,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(command, cwd=cwd, env=environment, shell=False, start_new_session=True)


def _wait_for_url(process: subprocess.Popen[bytes], url: str, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise StudioError(f"{label} exited before readiness with code {exit_code}.")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise StudioError(f"Timed out waiting for {label} readiness at {url}: {last_error}")


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            killpg = getattr(os, "killpg")
            killpg(process.pid, signal.SIGTERM)
    except (OSError, ValueError):
        process.terminate()
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            process.kill()
        else:
            killpg = getattr(os, "killpg")
            killpg(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except (OSError, ValueError):
        process.kill()
    process.wait(timeout=5)


def _shutdown_children(frontend: subprocess.Popen[bytes] | None, backend: subprocess.Popen[bytes] | None) -> None:
    _terminate(frontend)
    _terminate(backend)


def run_studio(config: StudioConfig) -> int:
    root = config.repository_root.resolve()
    web_root = root / "web"
    if not ((root / "pyproject.toml").is_file() and (root / "src").is_dir() and (web_root / "package.json").is_file()):
        raise StudioError("Studio frontend is not available in this installation. Run this command from a full game-ai-agent source checkout.")
    if not (web_root / ".next").is_dir():
        raise StudioError("Frontend production build is missing. Run: cd web; npm ci; npm run build")
    npm = find_npm_executable()
    if npm is None:
        raise StudioError("npm is required for Studio. Install Node.js >=20.9.0 and npm, then retry.")
    for host, port, label in ((config.backend_host, config.backend_port, "backend"), (config.frontend_host, config.frontend_port, "frontend")):
        if not is_port_available(host, port):
            raise StudioError(f"Studio {label} port is already in use: {host}:{port}")

    backend_url = f"http://{config.backend_host}:{config.backend_port}"
    frontend_url = f"http://{config.frontend_host}:{config.frontend_port}"
    environment = build_child_environment(config)
    db_path = resolve_database_path(config.db_path)
    backend = None
    frontend = None
    print(f"Backend: {' '.join(build_backend_command(config))}")
    print(f"Frontend: {' '.join(build_frontend_command(config, npm))}")
    print(f"Backend URL: {backend_url}")
    print(f"Frontend URL: {frontend_url}")
    print(f"DB path: {db_path}")
    shutdown_requested = False
    sigbreak = getattr(signal, "SIGBREAK", None) if os.name == "nt" else None
    previous_sigbreak = None

    def request_shutdown(_signum, _frame) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True

    try:
        if sigbreak is not None:
            previous_sigbreak = signal.signal(sigbreak, request_shutdown)
        print("Startup: starting backend")
        try:
            backend = _popen(build_backend_command(config), cwd=root, environment=environment)
        except OSError as error:
            raise StudioError(f"Backend failed to start: {error}") from error
        _wait_for_url(backend, f"{backend_url}/api/system/health", DEFAULT_STARTUP_TIMEOUTS["backend"], "Backend")
        print("Startup: backend ready")
        print("Startup: starting frontend")
        try:
            frontend = _popen(build_frontend_command(config, npm), cwd=web_root, environment=environment)
        except OSError as error:
            raise StudioError(f"Frontend failed to start: {error}") from error
        _wait_for_url(frontend, frontend_url, DEFAULT_STARTUP_TIMEOUTS["frontend"], "Frontend")
        print("Startup: frontend ready")
        if not config.no_browser:
            webbrowser.open(frontend_url)
        print("Studio running. Press Ctrl+C to stop.")
        while True:
            if shutdown_requested:
                print("Shutdown: interrupt received")
                return 0
            backend_exit = backend.poll()
            frontend_exit = frontend.poll()
            if backend_exit is not None:
                raise StudioError(f"Backend child exited unexpectedly with code {backend_exit}.")
            if frontend_exit is not None:
                raise StudioError(f"Frontend child exited unexpectedly with code {frontend_exit}.")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Shutdown: interrupt received")
        return 0
    except StudioError as error:
        print(f"Studio blocked: {error}", file=sys.stderr)
        return 1
    finally:
        if sigbreak is not None and previous_sigbreak is not None:
            signal.signal(sigbreak, previous_sigbreak)
        print("Shutdown: stopping frontend and backend")
        _shutdown_children(frontend, backend)
        print("Shutdown: complete")


def main(*, backend_host: str, backend_port: int, frontend_host: str, frontend_port: int, db_path: str | Path | None, no_browser: bool) -> int:
    from .doctor import find_source_checkout

    repository_root = find_source_checkout()
    if repository_root is None:
        print("Studio frontend is not available in this installation. Run this command from a full game-ai-agent source checkout.", file=sys.stderr)
        return 1
    try:
        return run_studio(StudioConfig(repository_root, backend_host, backend_port, frontend_host, frontend_port, db_path, no_browser))
    except StudioError as error:
        print(f"Studio blocked: {error}", file=sys.stderr)
        return 1
