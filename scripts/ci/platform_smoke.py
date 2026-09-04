"""Run the small source-install portability contract on one CI runner."""

from __future__ import annotations

import json
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from persistence import PersistenceUnitOfWork
from runtime_paths import resolve_app_data_directory
from web.app import create_app


def _expect(response, status_code: int, label: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} did not return a JSON object")
    return payload


def _assert_runtime_path_contract() -> None:
    root = Path(tempfile.mkdtemp(prefix="along-street-platform-测试-"))
    try:
        app_data = resolve_app_data_directory(
            platform=sys.platform,
            environ={
                "LOCALAPPDATA": str(root / "LocalAppData"),
                "XDG_DATA_HOME": str(root / "xdg"),
            },
            home=root / "home",
        )
        platform_name = sys.platform.lower()
        if platform_name == "win32":
            expected = root / "LocalAppData" / "game-ai-agent"
        elif platform_name == "darwin":
            expected = root / "home" / "Library" / "Application Support" / "game-ai-agent"
        else:
            expected = root / "xdg" / "game-ai-agent"
        if app_data != expected:
            raise RuntimeError(f"unexpected app-data path: {app_data} != {expected}")
    finally:
        root.rmdir()


def _save_payload(
    generated: dict[str, object], association: dict[str, object]
) -> dict[str, object]:
    return {
        "schema_version": "web-saved-character-save/0.1",
        "request": generated["request"],
        "draft": generated["draft"],
        "plan": generated["plan"],
        "associations": [association],
    }


def main() -> int:
    _assert_runtime_path_contract()
    with tempfile.TemporaryDirectory(prefix="along-street-platform-测试-") as temp_name:
        database_path = Path(temp_name) / "中文" / "studio.db"
        app = create_app(database_path=database_path, generation_mode="offline")
        with TestClient(app) as client:
            _expect(client.get("/api/system/health"), 200, "health")
            _expect(client.get("/openapi.json"), 200, "OpenAPI")
            generated = _expect(
                client.post(
                    "/api/characters/generate",
                    json={
                        "brief": "Design a support character.",
                        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
                        "request_id": "platform_smoke",
                    },
                ),
                200,
                "character generation",
            )
            skill = _expect(
                client.post(
                    "/api/characters/skill-design",
                    json={
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
                ),
                200,
                "skill design",
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
            saved = _expect(
                client.post("/api/saved-characters", json=_save_payload(generated, association)),
                201,
                "character save",
            )["saved"]
            if not isinstance(saved, dict) or not saved["current_kit_assignment_id"]:
                raise RuntimeError("saved Character did not receive a CharacterKit assignment")

        with PersistenceUnitOfWork(database_path) as unit:
            if unit.schema_version != 4:
                raise RuntimeError("platform smoke did not bootstrap schema v4")

        reopened_app = create_app(database_path=database_path, generation_mode="offline")
        with TestClient(reopened_app) as client:
            opened = _expect(
                client.get(f"/api/saved-characters/{saved['character_id']}"),
                200,
                "character reopen",
            )
            if (
                opened["associations"][0]["association_id"]
                != saved["associations"][0]["association_id"]
            ):
                raise RuntimeError("Character Skill association did not survive reopen")
            if opened["kit"]["kit_digest"] != saved["kit"]["kit_digest"]:
                raise RuntimeError("CharacterKit did not survive reopen")

    print(
        json.dumps(
            {
                "platform": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "schema": 4,
                "character_skill_kit_round_trip": True,
                "temporary_unicode_path_cleanup": True,
                "live_calls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
