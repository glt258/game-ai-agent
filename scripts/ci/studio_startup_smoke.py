"""Exercise the real source-checkout Studio launcher and its shutdown path."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _console_command() -> list[str]:
    if os.name == "nt":
        return [sys.executable, "-m", "game_ai_agent"]
    scripts_dir = Path(sysconfig.get_path("scripts"))
    for candidate in (
        scripts_dir / "game-ai-agent",
        scripts_dir / "game-ai-agent.exe",
        scripts_dir / "game-ai-agent.cmd",
    ):
        if candidate.is_file():
            if candidate.suffix.lower() == ".cmd":
                return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(candidate)]
            return [str(candidate)]
    executable = shutil.which("game-ai-agent")
    if executable:
        return [executable]
    raise RuntimeError(f"game-ai-agent console script not found in {scripts_dir}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_url(process: subprocess.Popen[str], url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Studio exited before {url} became ready: {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


def main() -> int:
    backend_port = _free_port()
    frontend_port = _free_port()
    environment = os.environ.copy()
    for key in ("NPC_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        environment.pop(key, None)
    environment["NPC_RUN_LIVE_SMOKE"] = "0"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix="game-ai-agent studio 测试-") as temp_name:
        db_path = Path(temp_name) / "中文 data" / "studio.db"
        command = [
            *_console_command(),
            "studio",
            "--no-browser",
            "--backend-port",
            str(backend_port),
            "--frontend-port",
            str(frontend_port),
            "--db-path",
            str(db_path),
        ]
        log_path = Path(temp_name) / "studio.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="strict",
                shell=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            try:
                _wait_for_url(process, f"http://127.0.0.1:{backend_port}/api/system/health", 30)
                _wait_for_url(process, f"http://127.0.0.1:{frontend_port}/", 60)
                if process.poll() is not None:
                    raise RuntimeError(f"Studio exited after readiness: {process.returncode}")
            finally:
                _stop(process)
        output = log_path.read_text(encoding="utf-8")

    if process.returncode != 0:
        raise RuntimeError(f"Studio did not shut down cleanly ({process.returncode}):\n{output}")
    if "Traceback" in output:
        raise RuntimeError(f"Studio emitted a traceback:\n{output}")
    for port in (backend_port, frontend_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Studio left port {port} occupied")
    required_markers = ("Startup: backend ready", "Startup: frontend ready", "Shutdown: complete")
    missing = [marker for marker in required_markers if marker not in output]
    if missing:
        raise RuntimeError(f"Studio output omitted {missing}:\n{output}")
    print(
        f"studio startup smoke passed: backend={backend_port} frontend={frontend_port} "
        "children cleaned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
