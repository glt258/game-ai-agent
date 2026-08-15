"""Run offline regressions derived from the Hermes Live acceptance language."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import CanonChecker  # noqa: E402
from evals.canon_checker_live_language import live_language_cases  # noqa: E402


def main() -> int:
    checker = CanonChecker()
    total = correct = false_positives = false_negatives = 0
    for case in live_language_cases():
        total += 1
        report = checker.check(case.draft, request=case.request)
        actual_codes = {finding.code for finding in report.findings}
        status_ok = report.status == case.expected_status
        codes_ok = case.expected_codes <= actual_codes and not case.forbidden_codes & actual_codes
        if status_ok and codes_ok:
            correct += 1
            verdict = "CORRECT"
        elif case.expected_status.value == "pass":
            false_positives += 1
            verdict = "FALSE POSITIVE"
        else:
            false_negatives += 1
            verdict = "FALSE NEGATIVE"
        codes = ",".join(sorted(item.value for item in actual_codes)) or "-"
        print(f"{case.case_id:32} | {verdict:15} | {codes}")
    print()
    print(f"Total: {total}")
    print(f"Correct: {correct}")
    print(f"False positives: {false_positives}")
    print(f"False negatives: {false_negatives}")
    return 0 if correct == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
