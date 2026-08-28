"""Provider-free dry-run for the aligned Hybrid Semantic IR configuration."""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Corrected Hybrid Semantic IR runner (dry-run by default)"
    )
    parser.add_argument("--live", action="store_true", help="explicitly execute one corrected observation")
    parser.add_argument("--output", type=Path, default=None, help="local ignored evidence path")
    args = parser.parse_args(argv)
    case = build_authoritative_support_case()
    runner = HybridSemanticIRRunner(ROOT, case.generation_context())
    if not args.live:
        print(json.dumps(runner.dry_run(), ensure_ascii=False, sort_keys=True))
        return 0
    result = runner.run_live(case.evaluation_context(), output_path=args.output)
    print(
        json.dumps(
            {
                "status": result.status,
                "consumed": result.consumed,
                "provider_factory_constructed": result.provider_factory_constructed,
                "provider_called": result.provider_called,
                "transport_attempts": result.transport_attempts,
                "first_failure_layer": result.first_failure_layer,
                "evidence_path": str(result.evidence_path) if result.evidence_path else None,
                "run_id": result.evidence.run_id if result.evidence else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
