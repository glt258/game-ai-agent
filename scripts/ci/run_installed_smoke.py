"""Install the built wheel in a native virtualenv and run installed_smoke."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    environment = os.environ.copy()
    environment.update(NPC_RUN_LIVE_SMOKE="0", NPC_LLM_API_KEY="", OPENAI_API_KEY="")
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    wheels = sorted(
        (repository_root / "dist").glob("*.whl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not wheels:
        raise RuntimeError("expected a wheel in dist")
    with tempfile.TemporaryDirectory(prefix="along-street-installed-") as temp_name:
        temp_root = Path(temp_name)
        venv = temp_root / "venv"
        _run([sys.executable, "-m", "venv", str(venv)])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        _run([str(python), "-m", "pip", "install", str(wheels[0])])
        smoke_cwd = temp_root / "outside-checkout-测试"
        smoke_cwd.mkdir()
        _run([str(python), str(repository_root / "scripts/ci/installed_smoke.py")], cwd=smoke_cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
