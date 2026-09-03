"""Portable paths shared by the installed runtime and local Studio tools."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_DATA_DIRECTORY_NAME = "game-ai-agent"
DEFAULT_DATABASE_FILENAME = "studio.db"


class RuntimePathError(RuntimeError):
    """Raised when a required user-facing runtime path cannot be resolved."""


def _home_directory(home: Path | None) -> Path:
    if home is not None:
        return Path(home)
    try:
        return Path.home()
    except (OSError, RuntimeError) as error:
        raise RuntimePathError("Unable to resolve the current user's home directory") from error


def resolve_app_data_directory(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the app-data directory without creating it.

    ``platform``, ``environ`` and ``home`` are injectable for portable tests;
    production callers use the current process values.
    """

    environment = os.environ if environ is None else environ
    platform_name = (platform or sys.platform).lower()
    if platform_name in {"win32", "windows"}:
        root = environment.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_DATA_DIRECTORY_NAME
        return _home_directory(home) / "AppData" / "Local" / APP_DATA_DIRECTORY_NAME
    if platform_name == "darwin":
        return _home_directory(home) / "Library" / "Application Support" / APP_DATA_DIRECTORY_NAME

    root = environment.get("XDG_DATA_HOME")
    if root:
        return Path(root) / APP_DATA_DIRECTORY_NAME
    return _home_directory(home) / ".local" / "share" / APP_DATA_DIRECTORY_NAME


def resolve_database_path(
    value: str | Path | None = None,
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the SQLite path using explicit override, env, then app data.

    Explicit paths retain native ``Path`` semantics: relative values are
    relative to the process CWD, ``~`` is not expanded, and shell-style
    environment expansion is not performed.
    """

    if value is not None:
        return Path(value)
    environment = os.environ if environ is None else environ
    configured = environment.get("GAME_AI_AGENT_DB_PATH")
    if configured:
        return Path(configured)
    return (
        resolve_app_data_directory(
            platform=platform,
            environ=environment,
            home=home,
        )
        / DEFAULT_DATABASE_FILENAME
    )


__all__ = [
    "APP_DATA_DIRECTORY_NAME",
    "DEFAULT_DATABASE_FILENAME",
    "RuntimePathError",
    "resolve_app_data_directory",
    "resolve_database_path",
]
