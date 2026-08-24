"""Run or plan the CS-S2 shadow evidence cohort."""

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

from evals.character_skill_s2_shadow_evidence import (  # noqa: E402
    EvidenceRunnerError,
    ShadowEvidenceRunner,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproducible CS-S2 SkillKit shadow evidence runner (dry-run by default)"
    )
    parser.add_argument("--live", action="store_true", help="opt into the bounded provider run")
    parser.add_argument("--dry-run", action="store_true", help="explicitly request the default plan-only mode")
    parser.add_argument("--repeat", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--resume", action="store_true", help="resume an existing append-only result bundle")
    parser.add_argument("--output", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.live and args.dry_run:
        print(json.dumps({"status": "error", "error_code": "MODE_ARGUMENTS_INVALID"}))
        return 2
    try:
        runner = ShadowEvidenceRunner(ROOT, manifest_path=args.manifest)
        result = runner.run(
            live=args.live,
            repeat=args.repeat,
            case_id=args.case_ids,
            resume=args.resume,
            output_path=args.output,
        )
    except EvidenceRunnerError as error:
        print(json.dumps({"status": "blocked", "error_code": error.code}, ensure_ascii=False))
        return 2
    except Exception:
        # The CLI is an evidence boundary: never print provider or environment
        # exception text, even when an integration seam fails unexpectedly.
        print(json.dumps({"status": "blocked", "error_code": "RUNNER_INTERNAL_FAILURE"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
