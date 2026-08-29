"""Committed, sanitized historical evidence fixtures for hermetic tests."""

from __future__ import annotations

from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "historical_evidence"


def historical_fixture_path(relative_or_name: str | Path) -> Path:
    """Resolve a historical evidence name into the committed fixture namespace.

    Callers may pass the old ``evals/results/...`` relative path so migration
    remains mechanical, but production evidence discovery never uses this
    helper.  The fixture directory contains only sanitized evidence metadata.
    """

    name = Path(relative_or_name).name
    path = FIXTURE_ROOT / name
    if not path.is_file():
        raise FileNotFoundError(f"committed historical fixture is missing: {name}")
    return path
