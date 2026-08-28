"""Provider-free dry-run for the aligned Hybrid Semantic IR configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from character_intelligence.hybrid_ir import (  # noqa: E402
    HybridSemanticIRRunner,
    build_authoritative_support_case,
)


def main() -> int:
    case = build_authoritative_support_case()
    result = HybridSemanticIRRunner(ROOT, case.generation_context()).dry_run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
