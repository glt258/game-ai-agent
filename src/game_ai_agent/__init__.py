"""Unified CLI for the installable runtime and source-checkout Studio."""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    from .__main__ import main as cli_main

    return cli_main(argv)

__all__ = ["main"]
