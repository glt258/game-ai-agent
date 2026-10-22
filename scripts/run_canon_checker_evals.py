"""Offline deterministic Canon Checker v0.1 eval suite."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents import (
    CanonCheckStatus,
    CanonChecker,
    CanonFindingCode,
    CharacterDesignRequest,
    CharacterDraft,
    StoryLink,
)


FIXTURES = ROOT / "evals" / "fixtures"


def load_case(name: str) -> tuple[CharacterDraft, CharacterDesignRequest]:
    payload = json.loads(
        (FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8")
    )
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(
        **payload["request"]
    )


def main() -> int:
    checker = CanonChecker()
    good, good_request = load_case("good")
    subtle, subtle_request = load_case("shenzhao")
    bad, bad_request = load_case("bad")
    good_report = checker.check(good, request=good_request)
    subtle_report = checker.check(subtle, request=subtle_request)
    bad_report = checker.check(bad, request=bad_request)

    fake_faction = checker.check(replace(good, faction_id="faction_999"))
    fake_story = checker.check(
        replace(good, story_link=StoryLink("incident_not_exist", status="proposed"))
    )
    authority = checker.check(replace(good, occupation="城市警务总指挥"))
    knowledge = checker.check(
        replace(good, knowledge_scope="可访问全城所有能力者档案。")
    )
    forbidden = checker.check(
        replace(good, background="她领导秘密政府能力监管机构。")
    )
    story_role = checker.check(
        replace(
            subtle,
            story_hook="她领导整个南栈事故处置并最终解决事件。",
        )
    )
    age = checker.check(replace(good, age=31), request=good_request)
    proposed_relationship = checker.check(
        replace(
            good,
            relationships=(
                {"target_id": "char_launch_001", "status": "proposed"},
            ),
        )
    )
    canon_relationship = checker.check(
        replace(
            good,
            relationships=(
                {"target_id": "char_launch_001", "status": "canon_backed"},
            ),
        )
    )

    def has(report, code: CanonFindingCode) -> bool:
        return any(item.code == code for item in report.findings)

    checks = [
        good_report.status == CanonCheckStatus.PASS,
        has(fake_faction, CanonFindingCode.INVALID_CANON_REFERENCE),
        has(fake_story, CanonFindingCode.INVALID_CANON_REFERENCE),
        has(subtle_report, CanonFindingCode.PROPOSAL_PRESENTED_AS_CANON),
        has(authority, CanonFindingCode.AUTHORITY_OVERREACH),
        has(knowledge, CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH),
        has(forbidden, CanonFindingCode.FORBIDDEN_PATTERN),
        has(story_role, CanonFindingCode.STORY_ROLE_OVERREACH),
        has(age, CanonFindingCode.HARD_CONSTRAINT_VIOLATION),
        not good_report.findings,
        proposed_relationship.status == CanonCheckStatus.PASS,
        has(canon_relationship, CanonFindingCode.UNSUPPORTED_CANON_CLAIM),
        subtle_report.status == CanonCheckStatus.WARN,
        bad_report.status == CanonCheckStatus.FAIL,
    ]
    passed = sum(checks)
    failed = len(checks) - passed
    print(f"Canon Checker evals: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
