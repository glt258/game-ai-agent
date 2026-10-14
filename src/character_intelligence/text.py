"""Small shared deterministic text helpers for character-intelligence consumers."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*|[\u4e00-\u9fff]{2,}")


def tokens(value: str) -> set[str]:
    """Return the shared deterministic token view used by intent consumers."""

    return {token for token in _TOKEN_RE.findall(value.casefold()) if token}


__all__ = ["tokens"]
