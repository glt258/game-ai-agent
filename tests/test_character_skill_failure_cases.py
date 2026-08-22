from __future__ import annotations

import json
import re
from pathlib import Path

from combat_semantics.roles import CANONICAL_COMBAT_ROLES


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "character_skill_failure_cases_v0.1.1.json"
LEGACY_FIXTURE_PATH = ROOT / "evals" / "fixtures" / "character_skill_failure_cases_v0.1.json"
BLIND_FIXTURE_PATH = ROOT / "evals" / "fixtures" / "hermes_character_skill_s0_blind_cases_v0.1.1.json"
SPEC_PATH = ROOT / "docs" / "character_generation" / "character_skill_failure_cases_v0.1.1.md"

SCHEMA_VERSION = "character-skill-failure-cases/0.1.1"
BLIND_SCHEMA_VERSION = "character-skill-blind-review-input/0.1.1"
OUTCOMES = ("PASS", "REPAIR", "FAIL")
ROLE_SET = frozenset(CANONICAL_COMBAT_ROLES)
EXPECTED_CODES = frozenset(
    {
        "RESOURCE_LOOP_INCOMPLETE",
        "FORBIDDEN_RESOURCE_INTRODUCED",
        "STATE_EXIT_MISSING",
        "TRIGGER_SUBJECT_AMBIGUOUS",
        "SUMMON_LIFECYCLE_INCOMPLETE",
        "ROLE_EFFECT_MISMATCH",
        "REQUESTED_MECHANIC_UNREPRESENTED",
        "MECHANIC_SKELETON_ABSENT",
        "CROSS_TAXONOMY_ROLE_LABEL",
        "REFERENCE_COPYING",
        "HARD_CONSTRAINT_CONFLICT",
        "MULTI_SKILL_LOOP_INCOHERENT",
    }
)
EXPECTED_IDS = (
    "skill_s0_01_resource_loop_complete",
    "skill_s0_02_resource_loop_incomplete",
    "skill_s0_03_forbidden_resource",
    "skill_s0_04_state_exit_missing",
    "skill_s0_05_teammate_trigger_ambiguous",
    "skill_s0_06_summon_lifecycle_incomplete",
    "skill_s0_07_main_dps_mismatch",
    "skill_s0_08_sub_dps_mismatch",
    "skill_s0_09_support_mismatch",
    "skill_s0_10_healer_mismatch",
    "skill_s0_11_control_mismatch",
    "skill_s0_12_defense_mismatch",
    "skill_s0_13_requested_mechanic_missing",
    "skill_s0_14_cross_taxonomy_role",
    "skill_s0_15_reference_copying",
    "skill_s0_16_hard_constraint_conflict",
    "skill_s0_17_multi_skill_loop",
    "skill_s0_18_control_near_neighbor_pass",
    "skill_s0_19_requested_mechanic_near_neighbor_repair",
)

CASE_KEYS = {
    "id",
    "title",
    "category",
    "request",
    "candidate_observation",
    "expected",
    "coverage_tags",
    "rationale",
}
REQUEST_KEYS = {
    "brief",
    "hard_constraints",
    "forbidden_elements",
    "combat_role_profile",
}
OBSERVATION_KEYS = {"summary", "declared_facts", "signals"}
EXPECTED_KEYS = {"outcome", "blocking", "repair_allowed", "findings"}
FINDING_KEYS = {"code", "field_path", "blocking", "repairable"}
REQUIRED_CATEGORIES = {
    "resource_loop",
    "state_lifecycle",
    "team_interaction",
    "summon_lifecycle",
    "role_alignment",
    "mechanic_representation",
    "taxonomy_boundary",
    "reference_integrity",
    "constraint_consistency",
    "multi_skill_coherence",
}
REQUIRED_TAGS = {
    "resource_loop",
    "state_lifecycle",
    "team_interaction",
    "summon_lifecycle",
    "role_alignment",
    "mechanic_relation",
    "taxonomy_boundary",
    "reference_integrity",
    "constraint_consistency",
    "multi_skill_coherence",
    "role_mismatch",
    "pass_control",
}

# These are balance-contract words, not ordinary case numbering.  The S0
# observation fixture intentionally does not decide any of these concerns.
FORBIDDEN_BALANCE_TERMS = (
    "damage_multiplier",
    "damage倍率",
    "伤害倍率",
    "frame_count",
    "帧数",
    "exact_cooldown",
    "精确冷却",
    "crit_rate",
    "暴击率",
    "attack_power",
    "攻击力",
)
CORPUS_IDENTIFIER_PATTERNS = (
    re.compile(r"\blore_\d+\b", re.IGNORECASE),
    re.compile(r"\bfaction_\d+\b", re.IGNORECASE),
    re.compile(r"\bcharacter_\d+\b", re.IGNORECASE),
)


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _cases(payload: dict[str, object]) -> list[dict[str, object]]:
    return payload["cases"]  # type: ignore[return-value]


def test_fixture_has_frozen_top_level_contract() -> None:
    payload = _load_fixture()

    assert set(payload) == {"schema_version", "outcomes", "finding_codes", "cases"}
    assert payload["schema_version"] == SCHEMA_VERSION
    assert set(payload["outcomes"]) == set(OUTCOMES)  # type: ignore[arg-type]
    assert set(payload["finding_codes"]) == EXPECTED_CODES  # type: ignore[arg-type]
    assert isinstance(payload["cases"], list)

    for outcome in OUTCOMES:
        assert set(payload["outcomes"][outcome]) == {  # type: ignore[index]
            "blocking",
            "repair_allowed",
        }
        assert isinstance(payload["outcomes"][outcome]["blocking"], bool)  # type: ignore[index]
        assert isinstance(payload["outcomes"][outcome]["repair_allowed"], bool)  # type: ignore[index]
    for code, registry in payload["finding_codes"].items():  # type: ignore[union-attr]
        assert set(registry) == {"meaning", "repairable"}
        assert isinstance(registry["meaning"], str)
        assert isinstance(registry["repairable"], bool)


def test_cases_have_exact_nested_contract() -> None:
    payload = _load_fixture()

    for case in _cases(payload):
        assert set(case) == CASE_KEYS
        assert set(case["request"]) == REQUEST_KEYS
        assert set(case["candidate_observation"]) == OBSERVATION_KEYS
        assert set(case["expected"]) == EXPECTED_KEYS
        assert isinstance(case["coverage_tags"], list)
        assert all(isinstance(tag, str) for tag in case["coverage_tags"])
        assert isinstance(case["rationale"], str)

        request = case["request"]
        assert isinstance(request["brief"], str)
        assert all(isinstance(item, str) for item in request["hard_constraints"])
        assert all(isinstance(item, str) for item in request["forbidden_elements"])

        observation = case["candidate_observation"]
        assert isinstance(observation["summary"], str)
        assert all(isinstance(item, str) for item in observation["declared_facts"])
        assert all(isinstance(item, str) for item in observation["signals"])

        expected = case["expected"]
        assert expected["outcome"] in OUTCOMES
        assert isinstance(expected["blocking"], bool)
        assert isinstance(expected["repair_allowed"], bool)
        assert isinstance(expected["findings"], list)
        for finding in expected["findings"]:
            assert set(finding) == FINDING_KEYS
            assert isinstance(finding["code"], str)
            assert isinstance(finding["field_path"], str)
            assert isinstance(finding["blocking"], bool)
            assert isinstance(finding["repairable"], bool)


def test_case_ids_are_exactly_nineteen_unique_and_ordered() -> None:
    ids = tuple(case["id"] for case in _cases(_load_fixture()))

    assert ids == EXPECTED_IDS
    assert len(ids) == 19
    assert len(set(ids)) == len(ids)


def test_outcome_invariants_are_frozen() -> None:
    payload = _load_fixture()

    for case in _cases(payload):
        expected = case["expected"]
        outcome = expected["outcome"]
        assert expected["blocking"] is payload["outcomes"][outcome]["blocking"]  # type: ignore[index]
        assert expected["repair_allowed"] is payload["outcomes"][outcome]["repair_allowed"]  # type: ignore[index]

        findings = expected["findings"]
        if outcome == "PASS":
            assert expected["blocking"] is False
            assert expected["repair_allowed"] is False
            assert findings == []
        elif outcome == "REPAIR":
            assert expected["blocking"] is True
            assert expected["repair_allowed"] is True
            assert findings
            assert all(finding["repairable"] for finding in findings)
        else:
            assert outcome == "FAIL"
            assert expected["blocking"] is True
            assert expected["repair_allowed"] is False
            assert findings
            assert any(not finding["repairable"] for finding in findings)


def test_findings_match_case_blocking_and_registry_repairability() -> None:
    payload = _load_fixture()
    registry = payload["finding_codes"]

    used_codes: list[str] = []
    for case in _cases(payload):
        expected = case["expected"]
        for finding in expected["findings"]:
            used_codes.append(finding["code"])
            assert finding["code"] in registry
            assert finding["blocking"] is expected["blocking"]
            assert finding["repairable"] is registry[finding["code"]]["repairable"]

    assert set(used_codes) == EXPECTED_CODES


def test_required_outcomes_categories_tags_and_codes_are_covered() -> None:
    cases = _cases(_load_fixture())

    assert {case["expected"]["outcome"] for case in cases} == set(OUTCOMES)
    assert {case["category"] for case in cases} == REQUIRED_CATEGORIES
    all_tags = {tag for case in cases for tag in case["coverage_tags"]}
    assert REQUIRED_TAGS <= all_tags


def test_combat_role_profiles_are_canonical_and_well_formed() -> None:
    for case in _cases(_load_fixture()):
        profile = case["request"]["combat_role_profile"]
        if profile is None:
            continue
        assert set(profile) == {"primary_role", "secondary_roles"}
        primary = profile["primary_role"]
        secondary = profile["secondary_roles"]
        assert primary is None or primary in ROLE_SET
        assert isinstance(secondary, list)
        assert all(role in ROLE_SET for role in secondary)
        assert len(secondary) == len(set(secondary))
        assert primary not in secondary


def test_six_roles_have_one_fail_mismatch_case_each_and_control_has_pass_neighbor() -> None:
    cases = _cases(_load_fixture())
    mismatches = [
        case
        for case in cases
        if any(finding["code"] == "ROLE_EFFECT_MISMATCH" for finding in case["expected"]["findings"])
    ]

    assert len(mismatches) == 6
    assert {
        case["request"]["combat_role_profile"]["primary_role"] for case in mismatches
    } == ROLE_SET
    assert all(case["expected"]["outcome"] == "FAIL" for case in mismatches)

    near_neighbor = next(
        case for case in cases if case["id"] == "skill_s0_18_control_near_neighbor_pass"
    )
    assert near_neighbor["expected"]["outcome"] == "PASS"
    assert near_neighbor["request"]["combat_role_profile"]["primary_role"] == "control"
    assert "team_interaction" in near_neighbor["coverage_tags"]
    assert "summon_lifecycle" in near_neighbor["coverage_tags"]


def test_case_05_content_and_repair_verdict_are_unchanged_from_v0_1() -> None:
    current = next(
        case
        for case in _cases(_load_fixture())
        if case["id"] == "skill_s0_05_teammate_trigger_ambiguous"
    )
    legacy_payload = json.loads(LEGACY_FIXTURE_PATH.read_text(encoding="utf-8"))
    legacy = next(
        case
        for case in legacy_payload["cases"]
        if case["id"] == "skill_s0_05_teammate_trigger_ambiguous"
    )

    assert current == legacy
    assert current["expected"]["outcome"] == "REPAIR"
    assert current["expected"]["repair_allowed"] is True


def test_case_13_requires_absent_mechanic_skeleton_and_is_not_repairable() -> None:
    case = next(
        case
        for case in _cases(_load_fixture())
        if case["id"] == "skill_s0_13_requested_mechanic_missing"
    )
    expected = case["expected"]
    signals = set(case["candidate_observation"]["signals"])

    assert expected["outcome"] == "FAIL"
    assert expected["blocking"] is True
    assert expected["repair_allowed"] is False
    assert [finding["code"] for finding in expected["findings"]] == [
        "MECHANIC_SKELETON_ABSENT"
    ]
    assert {
        "trigger_subject_missing",
        "effect_subject_missing",
        "feedback_relation_missing",
        "mechanic_skeleton_absent",
    } <= signals
    assert "trigger→effect" in case["candidate_observation"]["summary"]
    assert "因果" in case["candidate_observation"]["summary"]
    assert "机制骨架不存在" in case["rationale"]


def test_case_14_is_canonical_taxonomy_fail_closed_without_profile_normalization() -> None:
    case = next(
        case
        for case in _cases(_load_fixture())
        if case["id"] == "skill_s0_14_cross_taxonomy_role"
    )
    profile = case["request"]["combat_role_profile"]
    signals = set(case["candidate_observation"]["signals"])

    assert case["expected"]["outcome"] == "FAIL"
    assert [finding["code"] for finding in case["expected"]["findings"]] == [
        "CROSS_TAXONOMY_ROLE_LABEL"
    ]
    assert profile == {"primary_role": "support", "secondary_roles": []}
    assert "on_field_dps" not in {
        profile["primary_role"],
        *profile["secondary_roles"],
    }
    assert "crowd_control" not in {
        profile["primary_role"],
        *profile["secondary_roles"],
    }
    assert {
        "canonical_taxonomy_boundary_violation",
        "legacy_flat_alias_seam_not_applicable_to_combat_role_profile",
        "automatic_role_normalization_forbidden",
    } <= signals
    assert "canonical taxonomy boundary" in case["rationale"]
    assert "legacy flat alias seam" in case["rationale"]


def test_case_19_is_a_repairable_near_neighbor_with_present_mechanic_skeleton() -> None:
    case = next(
        case
        for case in _cases(_load_fixture())
        if case["id"] == "skill_s0_19_requested_mechanic_near_neighbor_repair"
    )
    expected = case["expected"]
    signals = set(case["candidate_observation"]["signals"])

    assert expected["outcome"] == "REPAIR"
    assert expected["blocking"] is True
    assert expected["repair_allowed"] is True
    assert [finding["code"] for finding in expected["findings"]] == [
        "REQUESTED_MECHANIC_UNREPRESENTED"
    ]
    assert {
        "trigger_subject_explicit",
        "effect_subject_explicit",
        "mechanic_causal_edge_present",
        "mechanic_skeleton_present",
        "feedback_relation_missing",
    } <= signals
    assert "trigger_subject_missing" not in signals
    assert "effect_subject_missing" not in signals


def test_blind_fixture_is_oracle_free_projection_without_fake_commit() -> None:
    authority = _load_fixture()
    blind = json.loads(BLIND_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert set(blind) == {"schema_version", "cases"}
    assert blind["schema_version"] == BLIND_SCHEMA_VERSION
    assert [case["case_id"] for case in blind["cases"]] == [
        f"case_{index:02d}" for index in range(1, 20)
    ]

    serialized = json.dumps(blind, ensure_ascii=False, sort_keys=True).casefold()
    assert "source_commit" not in serialized
    for leaked_key in ("expected", "finding", "signals", "rationale"):
        assert f'"{leaked_key}"' not in serialized

    for index, (case, authority_case) in enumerate(
        zip(blind["cases"], _cases(authority), strict=True), start=1
    ):
        assert set(case) == {"case_id", "request", "candidate_observation"}
        assert set(case["candidate_observation"]) == {"summary", "declared_facts"}
        assert case == {
            "case_id": f"case_{index:02d}",
            "request": authority_case["request"],
            "candidate_observation": {
                "summary": authority_case["candidate_observation"]["summary"],
                "declared_facts": authority_case["candidate_observation"]["declared_facts"],
            },
        }


def test_fixture_avoids_numeric_balance_contract_and_corpus_identifiers() -> None:
    serialized = json.dumps(_load_fixture(), ensure_ascii=False, sort_keys=True).casefold()
    for term in FORBIDDEN_BALANCE_TERMS:
        assert term.casefold() not in serialized
    for pattern in CORPUS_IDENTIFIER_PATTERNS:
        assert pattern.search(serialized) is None

    copying_case = next(
        case for case in _cases(_load_fixture()) if case["id"] == "skill_s0_15_reference_copying"
    )
    assert any(
        finding["code"] == "REFERENCE_COPYING"
        for finding in copying_case["expected"]["findings"]
    )
    assert "reference_relation_copy_detected" in copying_case["candidate_observation"]["signals"]


def test_fixture_load_and_json_round_trip_are_deterministic() -> None:
    first = _load_fixture()
    second = _load_fixture()
    encoded = json.dumps(first, ensure_ascii=False, sort_keys=True)

    assert first == second
    assert json.loads(encoded) == first
    assert json.dumps(second, ensure_ascii=False, sort_keys=True) == encoded


def test_spec_documents_the_frozen_contract_and_case_matrix() -> None:
    payload = _load_fixture()
    specification = SPEC_PATH.read_text(encoding="utf-8")

    for outcome in OUTCOMES:
        assert f"`{outcome}`" in specification
    for code in EXPECTED_CODES:
        assert f"`{code}`" in specification
    for case in _cases(payload):
        assert f"`{case['id']}`" in specification

    assert "`ability_concept`" in specification
    assert "S0 不把它替换成新的生产字段" in specification
    assert "不新增 production validator" in specification
    assert "不接入 provider" in specification
    assert "Reference Corpus 只能提供抽象先例" in specification
    assert "未来生产 `SkillKit` schema" in specification
    assert "v0.1.1" in specification
    assert "MECHANIC_SKELETON_ABSENT" in specification
    assert "canonical taxonomy boundary" in specification
    assert "legacy flat alias seam" in specification
    assert "`deepseek-v4-flash`" in specification
    assert "MiMo v2.5" in specification
    assert "same non-oracle projection" in specification
    assert "Ox Alpha" not in specification
