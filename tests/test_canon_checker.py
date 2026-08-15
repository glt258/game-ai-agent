from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

from agents import (
    CanonBasisEntry,
    CanonCheckStatus,
    CanonChecker,
    CanonFindingCode,
    CharacterDesignRequest,
    CharacterDraft,
    StoryLink,
)
from knowledge import KnowledgeResolver


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _case(name: str) -> tuple[CharacterDraft, CharacterDesignRequest]:
    payload = json.loads(
        (FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8")
    )
    return CharacterDraft.from_mapping(payload["draft"]), CharacterDesignRequest(
        **payload["request"]
    )


def _codes(report) -> set[CanonFindingCode]:
    return {finding.code for finding in report.findings}


def test_valid_draft_passes():
    draft, request = _case("good")
    report = CanonChecker().check(draft, request=request)
    assert report.status == CanonCheckStatus.PASS
    assert report.findings == ()


def test_fake_faction_reference_fails():
    draft, _ = _case("good")
    report = CanonChecker().check(replace(draft, faction_id="faction_999"))
    assert report.status == CanonCheckStatus.FAIL
    assert CanonFindingCode.INVALID_CANON_REFERENCE in _codes(report)


def test_fake_lore_reference_fails():
    draft, _ = _case("good")
    changed = replace(
        draft,
        canon_basis=(*draft.canon_basis, CanonBasisEntry("lore_999", ("background",))),
    )
    report = CanonChecker().check(changed)
    assert CanonFindingCode.INVALID_CANON_REFERENCE in _codes(report)


def test_fake_story_link_fails():
    draft, _ = _case("good")
    changed = replace(draft, story_link=StoryLink("incident_not_exist", status="proposed"))
    report = CanonChecker().check(changed)
    assert CanonFindingCode.INVALID_CANON_REFERENCE in _codes(report)


def test_proposal_presented_as_canon_warns():
    draft, request = _case("shenzhao")
    report = CanonChecker().check(draft, request=request)
    assert report.status == CanonCheckStatus.WARN
    assert _codes(report) == {CanonFindingCode.PROPOSAL_PRESENTED_AS_CANON}
    assert {item.field_path for item in report.findings} == {"background", "story_hook"}


def test_world_rule_violation_fails():
    draft, _ = _case("good")
    changed = replace(draft, ability_concept="无需专业训练即可直接完成急救和专业诊断。")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.WORLD_RULE_VIOLATION in _codes(report)


def test_forbidden_pattern_fails():
    draft, _ = _case("good")
    changed = replace(draft, background="她建立了秘密政府能力监管机构。")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.FORBIDDEN_PATTERN in _codes(report)


def test_authority_overreach_fails():
    draft, _ = _case("good")
    changed = replace(draft, occupation="临洲大学研究中心城市警务总指挥")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.AUTHORITY_OVERREACH in _codes(report)
    assert CanonFindingCode.INVALID_FACTION_ROLE in _codes(report)


def test_knowledge_scope_overreach_fails():
    draft, _ = _case("good")
    changed = replace(draft, knowledge_scope="可访问全城所有能力者档案。")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH in _codes(report)


def test_non_public_lore_requires_authorization():
    draft, _ = _case("good")
    changed = replace(draft, knowledge_scope="她知道 lore_secret_001 的完整内容。")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH in _codes(report)


def test_story_role_overreach_fails():
    draft, _ = _case("shenzhao")
    changed = replace(draft, story_hook="她全权指挥并最终解决了南栈事故。")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.STORY_ROLE_OVERREACH in _codes(report)


def test_hard_age_constraint_fails():
    draft, request = _case("good")
    report = CanonChecker().check(replace(draft, age=31), request=request)
    assert CanonFindingCode.HARD_CONSTRAINT_VIOLATION in _codes(report)


def test_soft_preference_does_not_fail():
    draft, _ = _case("good")
    request = CharacterDesignRequest(
        "设计角色", soft_preferences=("性格最好外向",), request_id="soft_only"
    )
    assert CanonChecker().check(draft, request=request).status == CanonCheckStatus.PASS


def test_proposed_relationship_allowed():
    draft, _ = _case("good")
    changed = replace(
        draft,
        relationships=(
            {"target_id": "char_launch_001", "description": "拟议合作", "status": "proposed"},
        ),
    )
    assert CanonChecker().check(changed).status == CanonCheckStatus.PASS


def test_false_canon_relationship_fails():
    draft, _ = _case("good")
    changed = replace(
        draft,
        relationships=(
            {"target_id": "char_launch_001", "description": "老友", "status": "canon_backed"},
        ),
    )
    report = CanonChecker().check(changed)
    assert CanonFindingCode.UNSUPPORTED_CANON_CLAIM in _codes(report)


def test_story_target_existing_does_not_make_relation_canon():
    draft, _ = _case("good")
    changed = replace(
        draft,
        story_link=StoryLink(
            "incident_nanzhan_postshow_route_conflict_001",
            relation="indirect_connection",
            status="canon_backed",
        ),
    )
    report = CanonChecker().check(changed)
    assert CanonFindingCode.INVALID_STORY_LINK in _codes(report)


def test_checker_does_not_mutate_draft():
    draft, request = _case("shenzhao")
    before = copy.deepcopy(draft.to_dict())
    CanonChecker().check(draft, request=request)
    assert draft.to_dict() == before


def test_checker_does_not_mutate_canon():
    resolver = KnowledgeResolver()
    before = copy.deepcopy(
        {
            "characters": resolver.characters,
            "factions": resolver.factions,
            "lore": resolver.lore,
            "cases": resolver.cases,
            "incidents": resolver.incidents,
        }
    )
    draft, request = _case("bad")
    CanonChecker(resolver=resolver).check(draft, request=request)
    assert before == {
        "characters": resolver.characters,
        "factions": resolver.factions,
        "lore": resolver.lore,
        "cases": resolver.cases,
        "incidents": resolver.incidents,
    }


def test_findings_are_deterministic():
    draft, request = _case("bad")
    checker = CanonChecker()
    assert checker.check(draft, request=request) == checker.check(draft, request=request)


def test_duplicate_findings_are_removed():
    draft, request = _case("bad")
    checker = CanonChecker()
    checker._rules = (*checker._rules, checker._check_world_rules)
    report = checker.check(draft, request=request)
    keys = [(item.code, item.field_path, item.evidence_ids) for item in report.findings]
    assert len(keys) == len(set(keys))


def test_shenzhao_regression():
    draft, request = _case("shenzhao")
    report = CanonChecker().check(draft, request=request)
    assert report.status == CanonCheckStatus.WARN
    assert report.summary.errors == 0
    assert report.summary.warnings == 2


def test_blatantly_invalid_character_regression():
    draft, request = _case("bad")
    report = CanonChecker().check(draft, request=request)
    required = {
        CanonFindingCode.AUTHORITY_OVERREACH,
        CanonFindingCode.FORBIDDEN_PATTERN,
        CanonFindingCode.HARD_CONSTRAINT_VIOLATION,
        CanonFindingCode.KNOWLEDGE_SCOPE_OVERREACH,
        CanonFindingCode.STORY_ROLE_OVERREACH,
        CanonFindingCode.WORLD_RULE_VIOLATION,
    }
    assert report.status == CanonCheckStatus.FAIL
    assert required <= _codes(report)


def test_invalid_draft_status_and_canonical_id_fail():
    draft, _ = _case("good")
    changed = replace(draft, status="approved", canonical_character_id="char_launch_004")
    report = CanonChecker().check(changed)
    assert CanonFindingCode.INVALID_DRAFT_STATUS in _codes(report)
    assert CanonFindingCode.EXISTING_CHARACTER_CONFLICT in _codes(report)


def test_negative_polarity_does_not_support_positive_claim():
    draft, _ = _case("good")
    changed = replace(
        draft,
        faction_id="faction_005",
        occupation="安全协调员",
        canon_basis=(
            CanonBasisEntry("world_rules", ("world_rules",)),
            CanonBasisEntry("faction_005", ("独立行政机关",)),
        ),
    )
    report = CanonChecker().check(changed)
    assert CanonFindingCode.UNSUPPORTED_CANON_CLAIM in _codes(report)


def test_unsupported_canon_support_label_fails():
    draft, _ = _case("good")
    changed = replace(
        draft,
        canon_basis=(
            CanonBasisEntry("world_rules", ("world_rules",)),
            CanonBasisEntry("faction_002", ("all_city_admin_power",)),
        ),
    )
    report = CanonChecker().check(changed)
    assert CanonFindingCode.UNSUPPORTED_CANON_CLAIM in _codes(report)
