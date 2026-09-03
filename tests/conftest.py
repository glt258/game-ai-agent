import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def isolate_default_studio_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep default-app tests out of the developer's real app-data directory."""
    monkeypatch.setenv("GAME_AI_AGENT_DB_PATH", str(tmp_path / "studio.db"))
