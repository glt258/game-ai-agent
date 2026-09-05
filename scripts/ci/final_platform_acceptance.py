"""Run the fresh-checkout, full-Studio W4-S5E acceptance flow."""

from __future__ import annotations

import json
import os
import platform
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
from typing import Any, TextIO

STAGE_TIMEOUT = 120.0
READY_TIMEOUTS = {"backend": 45.0, "frontend": 90.0}
FAKE_SECRET = "W4-S5E-FAKE-SECRET-DO-NOT-LEAK"


class AcceptanceFailure(RuntimeError):
    def __init__(
        self,
        stage: str,
        command: str,
        exit_code: int | None,
        detail: str,
        log_path: Path | None = None,
    ) -> None:
        self.stage = stage
        self.command = command
        self.exit_code = exit_code
        self.detail = detail
        self.log_path = log_path
        super().__init__(detail)


def _command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command)


def _safe_console_text(value: object, stream: TextIO) -> str:
    text = str(value)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return text.encode(encoding, errors="backslashreplace").decode(encoding)
    except LookupError:
        return text.encode("utf-8", errors="backslashreplace").decode("utf-8")
    return text


def _safe_print(*values: object, sep: str = " ", end: str = "\n", file: TextIO | None = None) -> None:
    stream = file or sys.stdout
    print(
        *(_safe_console_text(value, stream) for value in values),
        sep=sep,
        end=end,
        file=stream,
    )


def _redact(value: str) -> str:
    return value.replace(FAKE_SECRET, "[REDACTED]")


def _console_command() -> list[str]:
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


def _npm_command() -> list[str]:
    executable = shutil.which("npm") or shutil.which("npm.cmd")
    if executable is None:
        raise RuntimeError("npm executable not found")
    if Path(executable).suffix.lower() == ".cmd":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", executable]
    return [executable]


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in (
        "NPC_LLM_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MIMO_API_KEY",
        "AUTHORIZATION",
    ):
        environment.pop(key, None)
    environment.update(
        {
            "NPC_RUN_LIVE_SMOKE": "0",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment


def _run(
    stage: str,
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: float = STAGE_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = _redact((result.stdout + "\n" + result.stderr).strip())[-4000:]
        raise AcceptanceFailure(stage, _command_text(command), result.returncode, detail)
    _safe_print(f"{stage}: PASS")
    return result


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _assert_port_released(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"port {port} was not released: {error}") from error


def _wait_for_url(
    process: subprocess.Popen[str],
    url: str,
    *,
    stage: str,
    timeout: float,
    log_path: Path,
    exact_status: int | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AcceptanceFailure(
                stage,
                url,
                process.returncode,
                _with_log(f"Studio exited before readiness: {process.returncode}", log_path),
                log_path,
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                status_ok = response.status == exact_status if exact_status else 200 <= response.status < 400
                if status_ok:
                    _safe_print(f"{stage}: PASS ({response.status})")
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise AcceptanceFailure(stage, url, None, _with_log(f"timed out: {last_error}", log_path), log_path)


def _start_studio(
    command: list[str], *, cwd: Path, environment: dict[str, str], log_path: Path
) -> subprocess.Popen[str]:
    log = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=(
                int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")) if os.name == "nt" else 0
            ),
            start_new_session=os.name != "nt",
        )
    except OSError:
        log.close()
        raise
    log.close()
    return process


def _stop_studio(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return False
    if os.name == "nt":
        process.send_signal(int(getattr(signal, "CTRL_BREAK_EVENT")))
    else:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=20)
        return False
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return True


def _tail(path: Path) -> str:
    if not path.is_file():
        return "<log unavailable>"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return _redact("\n".join(lines[-80:]))


def _with_log(detail: str, log_path: Path) -> str:
    return f"{detail}\nlauncher log:\n{_tail(log_path)}"


def _request_json(
    base_url: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}: {body}") from error
    if not isinstance(body, dict):
        raise RuntimeError(f"{method} {path} did not return a JSON object (HTTP {status})")
    return body


def _save_payload(generated: dict[str, Any], association: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "web-saved-character-save/0.1",
        "request": generated["request"],
        "draft": generated["draft"],
        "plan": generated["plan"],
        "associations": [association],
    }


def _persist_once(base_url: str) -> dict[str, Any]:
    generated = _request_json(
        base_url,
        "POST",
        "/api/characters/generate",
        {
            "brief": "Design a support character.",
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
            "request_id": "w4_s5e_final_acceptance",
        },
    )
    skill = _request_json(
        base_url,
        "POST",
        "/api/characters/skill-design",
        {
            "character": {
                "request": generated["request"],
                "draft": generated["draft"],
                "plan": generated["plan"],
            },
            "skill": {
                "family": "support",
                "mode": "active",
                "brief": "Protect allies",
                "constraints": [],
                "preset_id": "character_support_skill_v1",
                "execution_mode": "offline",
            },
        },
    )
    association = {
        "association_id": f"session-skill:primary:{skill['artifact_digest']}",
        "artifact": skill["artifact"],
        "binding": skill["binding"],
        "artifact_compatibility": skill["artifact_compatibility"],
        "slot": "primary",
        "order": 0,
        "family": "support",
        "mode": "active",
        "display_summary": "Protect allies",
    }
    saved = _request_json(base_url, "POST", "/api/saved-characters", _save_payload(generated, association))["saved"]
    if not isinstance(saved, dict):
        raise RuntimeError("save response did not contain a saved character")
    for field in ("character_id", "current_revision_id", "current_kit_assignment_id"):
        if not saved.get(field):
            raise RuntimeError(f"save response missing {field}")
    if not saved.get("associations") or not saved.get("kit"):
        raise RuntimeError("save response missing association or CharacterKit")
    return saved


def _verify_open(base_url: str, saved: dict[str, Any]) -> None:
    character_id = saved["character_id"]
    opened = _request_json(base_url, "GET", f"/api/saved-characters/{character_id}")
    if opened.get("character_id") != character_id:
        raise RuntimeError("reopened Character ID changed")
    if opened.get("current_revision_id") != saved["current_revision_id"]:
        raise RuntimeError("reopened current revision changed")
    if opened.get("draft") != saved.get("draft"):
        raise RuntimeError("reopened Character payload changed")
    saved_association = saved["associations"][0]
    opened_association = opened["associations"][0]
    if opened_association.get("association_id") != saved_association.get("association_id"):
        raise RuntimeError("reopened Skill association changed")
    if opened.get("current_kit_assignment_id") != saved["current_kit_assignment_id"]:
        raise RuntimeError("reopened CharacterKit assignment changed")
    if opened.get("kit", {}).get("kit_digest") != saved["kit"].get("kit_digest"):
        raise RuntimeError("reopened CharacterKit digest changed")


def _assert_schema(database_path: Path) -> None:
    from persistence import PersistenceUnitOfWork

    with PersistenceUnitOfWork(database_path) as unit:
        if unit.schema_version != 4:
            raise RuntimeError(f"expected schema v4, got v{unit.schema_version}")


def _start_studio_cycle(
    cycle: int,
    command: list[str],
    *,
    root: Path,
    environment: dict[str, str],
    backend_url: str,
    frontend_url: str,
    log_path: Path,
) -> subprocess.Popen[str]:
    _safe_print(f"studio-start-{cycle}: {_command_text(command)}")
    process = _start_studio(command, cwd=root, environment=environment, log_path=log_path)
    try:
        _wait_for_url(
            process,
            f"{backend_url}/api/system/health",
            stage=f"backend-ready-{cycle}",
            timeout=READY_TIMEOUTS["backend"],
            log_path=log_path,
            exact_status=200,
        )
        _wait_for_url(
            process,
            f"{frontend_url}/",
            stage=f"frontend-ready-{cycle}",
            timeout=READY_TIMEOUTS["frontend"],
            log_path=log_path,
        )
        if process.poll() is not None:
            raise AcceptanceFailure(
                f"studio-start-{cycle}",
                _command_text(command),
                process.returncode,
                _with_log("launcher exited after readiness", log_path),
                log_path,
            )
    except Exception:
        _stop_studio(process)
        raise
    _safe_print(f"studio-start-{cycle}: PASS")
    return process


def _shutdown_studio(
    cycle: int,
    process: subprocess.Popen[str],
    command: list[str],
    ports: tuple[int, int],
    log_path: Path,
) -> None:
    force_fallback = _stop_studio(process)
    _safe_print(f"shutdown-{cycle}: {'FAIL (force fallback)' if force_fallback else 'PASS'}")
    if force_fallback:
        raise AcceptanceFailure(
            f"shutdown-{cycle}",
            _command_text(command),
            process.returncode,
            _with_log("graceful shutdown timed out; force fallback was required", log_path),
            log_path,
        )
    if process.returncode != 0:
        raise AcceptanceFailure(
            f"shutdown-{cycle}",
            _command_text(command),
            process.returncode,
            _with_log("launcher did not exit cleanly", log_path),
            log_path,
        )
    for port in ports:
        try:
            _assert_port_released(port)
        except RuntimeError as error:
            raise AcceptanceFailure(
                f"shutdown-{cycle}",
                _command_text(command),
                process.returncode,
                _with_log(str(error), log_path),
                log_path,
            ) from error


def _accept(root: Path) -> None:
    if not (root / "pyproject.toml").is_file() or not (root / "web" / "package.json").is_file():
        raise RuntimeError("acceptance must run from the repository root")
    environment = _environment()
    environment["OPENAI_API_KEY"] = FAKE_SECRET
    _safe_print(f"platform: {platform.system()}")
    _safe_print(f"architecture: {platform.machine()}")
    _safe_print(f"Python: {sys.version.split()[0]}")
    cli = _console_command()
    _run("cli", [*cli, "--help"], cwd=root, environment=environment)
    _run("cli", [*cli, "--version"], cwd=root, environment=environment)
    doctor = _run("doctor", [*cli, "doctor"], cwd=root, environment=environment)
    if "Core runtime: READY" not in doctor.stdout or FAKE_SECRET in doctor.stdout + doctor.stderr:
        raise RuntimeError("doctor human output was not ready or leaked a secret")
    doctor_json = _run("doctor", [*cli, "doctor", "--json"], cwd=root, environment=environment)
    report = json.loads(doctor_json.stdout)
    if (
        report.get("core_ready") is not True
        or report.get("studio_ready") is not False
        or FAKE_SECRET in doctor_json.stdout + doctor_json.stderr
    ):
        raise RuntimeError(f"doctor JSON is not core-ready or leaked a secret: {report}")
    if (root / "web" / ".next").exists():
        raise RuntimeError("fresh acceptance started with a pre-existing web/.next")
    npm = _npm_command()
    _run("frontend-build", [*npm, "ci", "--no-audit", "--no-fund"], cwd=root / "web", environment=environment)
    _run("frontend-build", [*npm, "run", "build"], cwd=root / "web", environment=environment)
    doctor_after = _run("doctor", [*cli, "doctor"], cwd=root, environment=environment)
    if "Studio: READY" not in doctor_after.stdout:
        raise RuntimeError("doctor after frontend build did not report Studio READY")
    doctor_after_json = _run("doctor", [*cli, "doctor", "--json"], cwd=root, environment=environment)
    after_report = json.loads(doctor_after_json.stdout)
    if after_report.get("core_ready") is not True or after_report.get("studio_ready") is not True:
        raise RuntimeError(f"doctor after build is not fully ready: {after_report}")
    environment.pop("OPENAI_API_KEY", None)
    with tempfile.TemporaryDirectory(prefix="game-ai-agent S5E ") as temp_name:
        temp_root = Path(temp_name) / "游戏 AI Agent S5E"
        temp_root.mkdir()
        database_path = temp_root / "studio.db"
        if database_path.exists():
            raise RuntimeError("acceptance database was not fresh")
        backend_port, frontend_port = _free_port(), _free_port()
        ports = (backend_port, frontend_port)
        environment["GAME_AI_AGENT_DB_PATH"] = str(database_path)
        command = [
            *cli,
            "studio",
            "--no-browser",
            "--backend-host",
            "127.0.0.1",
            "--backend-port",
            str(backend_port),
            "--frontend-host",
            "127.0.0.1",
            "--frontend-port",
            str(frontend_port),
            "--db-path",
            str(database_path),
        ]
        backend_url = f"http://127.0.0.1:{backend_port}"
        frontend_url = f"http://127.0.0.1:{frontend_port}"
        log_1 = Path(temp_name) / "studio-run-1.log"
        process_1 = _start_studio_cycle(1, command, root=root, environment=environment, backend_url=backend_url, frontend_url=frontend_url, log_path=log_1)
        try:
            try:
                saved = _persist_once(backend_url)
            except RuntimeError as error:
                raise AcceptanceFailure(
                    "save", "HTTP persistence API", None, _with_log(str(error), log_1), log_1
                ) from error
            _safe_print("save: PASS (Character + Skill + CharacterKit)")
        finally:
            _shutdown_studio(1, process_1, command, ports, log_1)
        if not database_path.is_file():
            raise RuntimeError("Studio did not create the acceptance database")
        _assert_schema(database_path)
        _safe_print("shutdown-1: PASS (ports released)")
        log_2 = Path(temp_name) / "studio-run-2.log"
        process_2 = _start_studio_cycle(2, command, root=root, environment=environment, backend_url=backend_url, frontend_url=frontend_url, log_path=log_2)
        try:
            try:
                _verify_open(backend_url, saved)
            except RuntimeError as error:
                raise AcceptanceFailure(
                    "verify", "HTTP persistence API", None, _with_log(str(error), log_2), log_2
                ) from error
            _safe_print("open: PASS")
            _safe_print("verify: PASS (Character + revision + Skill association + CharacterKit)")
        finally:
            _shutdown_studio(2, process_2, command, ports, log_2)
        _assert_schema(database_path)
        _safe_print("shutdown-2: PASS (ports released)")
    _safe_print("cleanup: PASS (temporary Unicode DB/log path removed; no orphan launcher)")
    _safe_print(
        json.dumps(
            {
                "acceptance": "W4-S5E",
                "platform": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "schema": 4,
                "live_calls": 0,
                "restart_round_trip": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> int:
    try:
        _accept(Path.cwd().resolve())
    except AcceptanceFailure as error:
        log = _tail(error.log_path) if error.log_path else "<no process log>"
        _safe_print(
            f"FAIL stage={error.stage} platform={platform.system()} command={error.command} "
            f"exit_code={error.exit_code}\n"
            f"backend log: {error.log_path or '<none>'}\n"
            f"frontend log: {error.log_path or '<none>'}\n"
            f"launcher log: {error.log_path or '<none>'}\n"
            f"detail: {_redact(error.detail)}\n{log}",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        _safe_print(
            f"FAIL stage=acceptance platform={platform.system()} command=<internal> exit_code=1\n"
            "backend log: <not started or inherited launcher log>\n"
            "frontend log: <not started or inherited launcher log>\n"
            "launcher log: <not started>\n"
            f"detail: {_redact(str(error))}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
