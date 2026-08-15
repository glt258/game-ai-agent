from __future__ import annotations

from dataclasses import replace

from agents import CanonChecker
from evals.canon_checker_redteam import redteam_cases


def _codes(report):
    return {finding.code for finding in report.findings}


def test_all_hermes_redteam_cases_are_formal_regressions():
    checker = CanonChecker()
    for case, draft, request in redteam_cases():
        report = checker.check(draft, request=request)
        if case.known_limitation:
            assert report.status.value == "fail", case.case_id
            continue
        assert report.status == case.expected_status, (case.case_id, report.to_dict())
        assert case.expected_codes <= _codes(report), (case.case_id, report.to_dict())
        assert not case.forbidden_codes & _codes(report), (case.case_id, report.to_dict())
        if case.severity:
            actual = {finding.code: finding.severity.value for finding in report.findings}
            for code, severity in case.severity.items():
                assert actual.get(code) == severity, (case.case_id, report.to_dict())


def test_hedge_is_clause_local_and_does_not_hide_an_accomplished_fact():
    checker = CanonChecker()
    case = next(item for item in redteam_cases() if item[0].case_id == "G9")
    draft = case[1]
    changed = replace(draft, story_hook="她已经参与南栈事故复盘，未来可能继续负责其他项目。")
    report = checker.check(changed)
    assert any(item.code.value == "PROPOSAL_PRESENTED_AS_CANON" for item in report.findings)


def test_secret_unpublished_research_project_is_not_rule_008():
    base = next(item for item in redteam_cases() if item[0].case_id == "A")[1]
    report = CanonChecker().check(
        replace(base, background="研究中心有一个尚未公开发表结果的研究项目。")
    )
    assert not any(item.code.value == "WORLD_RULE_VIOLATION" for item in report.findings)


def test_quantifier_without_sensitive_knowledge_is_not_overreach():
    base = next(item for item in redteam_cases() if item[0].case_id == "A")[1]
    report = CanonChecker().check(
        replace(base, knowledge_scope="她认识实验室里的每位同学。")
    )
    assert not any(item.code.value == "KNOWLEDGE_SCOPE_OVERREACH" for item in report.findings)
