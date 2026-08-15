"""Human-readable and JSON demo for Canon Checker v0.1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents import CanonChecker, CharacterDesignRequest, CharacterDraft


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def load_case(name: str) -> tuple[CharacterDraft, CharacterDesignRequest]:
    fixture_name = "shenzhao" if name == "subtle" else name
    payload = json.loads(
        (FIXTURES / f"canon_checker_{fixture_name}.json").read_text(encoding="utf-8")
    )
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(
        **payload["request"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Canon Checker v0.1 demo")
    parser.add_argument("--case", choices=("good", "subtle", "bad"), default="good")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    draft, request = load_case(args.case)
    report = CanonChecker().check(draft, request=request)
    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("Canon Check")
    print("===========")
    print(f"Draft: {report.draft_id}")
    print(f"Status: {report.status.value.upper()}")
    print("\nFindings:")
    if not report.findings:
        print("- none")
    for finding in report.findings:
        print(f"\n[{finding.severity.value.upper()}] {finding.code.value}")
        print(f"Field: {finding.field_path}")
        print(f"Evidence: {list(finding.evidence_ids)}")
        print(f"Message: {finding.message}")
    print("\nSummary:")
    print(
        f"errors={report.summary.errors} "
        f"warnings={report.summary.warnings} infos={report.summary.infos}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
