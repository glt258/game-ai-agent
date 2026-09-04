"""Exercise the bounded cross-platform launcher process lifecycle."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

from game_ai_agent.studio import _popen, _terminate, find_npm_executable


def main() -> int:
    npm = find_npm_executable()
    if npm is None:
        raise RuntimeError("npm executable was not resolved on the platform runner")
    environment = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="along-street-launcher-测试-") as directory:
        process = _popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=Path(directory),
            environment=environment,
        )
        try:
            time.sleep(0.2)
            if process.poll() is not None:
                raise RuntimeError(f"lifecycle child exited early: {process.returncode}")
        finally:
            _terminate(process)
        if process.poll() is None:
            raise RuntimeError("lifecycle child was not cleaned up")
    print(
        json.dumps(
            {
                "launcher_lifecycle": True,
                "machine": platform.machine(),
                "npm": npm,
                "platform": platform.system(),
                "python": platform.python_version(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
