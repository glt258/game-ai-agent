"""Wait until local HTTP endpoints are ready for a smoke test."""

from __future__ import annotations

import sys
import time
import urllib.request


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        raise SystemExit("usage: wait_for_urls.py URL [URL ...]")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if all(_ready(url) for url in urls):
            return 0
        time.sleep(1)
    return 1


def _ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
