"""Run the Canon Checker v0.1.1 red-team matrix with before/after metrics."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import CanonChecker  # noqa: E402
from evals.canon_checker_redteam import redteam_cases  # noqa: E402


def main() -> int:
    checker = CanonChecker()
    total = correct = false_negatives = false_positives = severity_issues = known_limitations = 0
    print("Case ID | Expected | Actual | Verdict | Finding Codes")
    print("--------|----------|--------|---------|--------------")
    for case, draft, request in redteam_cases():
        total += 1
        report = checker.check(draft, request=request)
        actual_codes = {finding.code for finding in report.findings}
        code_text = ",".join(sorted(code.value for code in actual_codes)) or "-"
        if case.known_limitation:
            known_limitations += 1
            verdict = "KNOWN LIMITATION"
        else:
            status_ok = report.status == case.expected_status
            codes_ok = case.expected_codes <= actual_codes and not case.forbidden_codes & actual_codes
            severity_ok = True
            if case.severity:
                actual_severity = {finding.code: finding.severity.value for finding in report.findings}
                severity_ok = all(actual_severity.get(code) == value for code, value in case.severity.items())
                if not severity_ok:
                    severity_issues += 1
            if status_ok and codes_ok and severity_ok:
                correct += 1
                verdict = "CORRECT"
            elif report.status == case.expected_status and codes_ok:
                correct += 1
                severity_issues += 1
                verdict = "SEVERITY ISSUE"
            elif case.expected_status.value == "fail" and report.status.value != "fail":
                false_negatives += 1
                verdict = "FALSE NEGATIVE"
            else:
                false_positives += 1
                verdict = "FALSE POSITIVE"
        print(f"{case.case_id:7} | {case.expected_status.value:8} | {report.status.value:6} | {verdict:17} | {code_text}")
    print()
    print(f"Total: {total}")
    print(f"Correct: {correct}")
    print(f"False negatives: {false_negatives}")
    print(f"False positives: {false_positives}")
    print(f"Severity issues: {severity_issues}")
    print(f"Known limitations: {known_limitations}")
    return 0 if false_negatives == 0 and false_positives == 0 and severity_issues == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
