from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.character_generation import CharacterDraft
from persistence import PersistenceConfigurationError, PersistenceUnitOfWork
from runtime_paths import RuntimePathError, resolve_app_data_directory, resolve_database_path


def test_explicit_database_override_wins_and_preserves_native_path_semantics(
    tmp_path: Path,
) -> None:
    relative = Path("relative") / "studio.db"
    assert (
        resolve_database_path(relative, environ={"GAME_AI_AGENT_DB_PATH": "ignored.db"}) == relative
    )
    assert resolve_database_path(
        "~/custom/studio.db", environ={"GAME_AI_AGENT_DB_PATH": "ignored.db"}
    ) == Path("~/custom/studio.db")


@pytest.mark.parametrize(
    ("platform", "environ", "home", "expected"),
    (
        (
            "win32",
            {"LOCALAPPDATA": r"C:\Users\测试\AppData\Local"},
            Path(r"C:\Users\Test"),
            Path(r"C:\Users\测试\AppData\Local\game-ai-agent"),
        ),
        (
            "linux",
            {"XDG_DATA_HOME": "/home/test/项目/.data"},
            Path("/home/test/项目"),
            Path("/home/test/项目/.data/game-ai-agent"),
        ),
        (
            "linux",
            {},
            Path("/home/test/项目"),
            Path("/home/test/项目/.local/share/game-ai-agent"),
        ),
        (
            "darwin",
            {"XDG_DATA_HOME": "/ignored"},
            Path("/Users/test/项目"),
            Path("/Users/test/项目/Library/Application Support/game-ai-agent"),
        ),
    ),
)
def test_platform_app_data_contract(
    platform: str,
    environ: dict[str, str],
    home: Path,
    expected: Path,
) -> None:
    assert resolve_app_data_directory(platform=platform, environ=environ, home=home) == expected
    assert resolve_database_path(platform=platform, environ=environ, home=home) == (
        expected / "studio.db"
    )


def test_app_data_resolution_is_pure_and_cwd_independent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    expected = tmp_path.parent / "用户数据" / "game-ai-agent"

    resolved = resolve_app_data_directory(
        platform="linux",
        environ={"XDG_DATA_HOME": str(tmp_path.parent / "用户数据")},
        home=tmp_path / "unused-home",
    )

    assert resolved == expected
    assert not resolved.exists()
    assert Path.cwd() not in resolved.parents


def test_missing_home_fails_without_none_path(monkeypatch) -> None:
    def fail_home() -> Path:
        raise RuntimeError("home unavailable")

    monkeypatch.setattr(Path, "home", fail_home)
    with pytest.raises(RuntimePathError, match="home directory"):
        resolve_app_data_directory(platform="linux", environ={})


def test_unwritable_database_parent_raises_typed_error_without_cwd_fallback(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")

    with pytest.raises(PersistenceConfigurationError):
        PersistenceUnitOfWork(blocked_parent / "studio.db")

    assert not (Path.cwd() / "studio.db").exists()


def test_installed_runtime_path_and_character_round_trip_outside_repository(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database_path = tmp_path / "中文" / "studio.db"
    draft = CharacterDraft(draft_id="draft_runtime", status="draft", name="测试角色")

    with PersistenceUnitOfWork(database_path) as unit:
        created = unit.characters.create(draft)
        assert unit.schema_version == 4

    with PersistenceUnitOfWork(database_path) as unit:
        restored = unit.characters.get_character(created.character_id)

    assert restored.current_revision.draft.name == "测试角色"
    assert (
        json.loads(json.dumps(restored.current_revision.draft.to_dict(), ensure_ascii=False))[
            "name"
        ]
        == "测试角色"
    )
