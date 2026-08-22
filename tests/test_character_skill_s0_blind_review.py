from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "evals" / "fixtures" / "character_skill_failure_cases_v0.1.1.json"
SPEC_PATH = ROOT / "docs" / "character_generation" / "character_skill_failure_cases_v0.1.1.md"
BLIND_INPUT_PATH = ROOT / "evals" / "fixtures" / "hermes_character_skill_s0_blind_cases_v0.1.1.json"
DEEPSEEK_PATH = ROOT / "evals" / "results" / "character_skill_s0_blind_review_deepseek_v0.1.1.json"
MIMO_PATH = ROOT / "evals" / "results" / "character_skill_s0_blind_review_mimo_v0.1.1.json"
REPORT_PATH = ROOT / "docs" / "character_generation" / "character_skill_s0_blind_review_v0.1.1.md"

COMMIT_A = "f96b45023e844e501a07b4426ef7fa963285a054"
SCHEMA_VERSION = "character-skill-blind-review-output/0.1.1"
REVIEWER_IDS = {
    "deepseek": "deepseek-v4-flash",
    "mimo": "mimo-v2.5",
}
CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 20))
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_show(commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _git_commit_exists(commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def _results_by_case(path: Path) -> dict[str, dict[str, Any]]:
    return {item["case_id"]: item for item in _load(path)["results"]}


@pytest.fixture(scope="module")
def authority() -> dict[str, Any]:
    return _load(AUTHORITY_PATH)


def test_reviewer_outputs_have_frozen_top_level_contract_and_commit_a() -> None:
    for path, reviewer_id in (
        (DEEPSEEK_PATH, REVIEWER_IDS["deepseek"]),
        (MIMO_PATH, REVIEWER_IDS["mimo"]),
    ):
        payload = _load(path)

        assert set(payload) == {"schema_version", "source_commit", "reviewer", "results"}
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["source_commit"] == COMMIT_A
        assert SHA_PATTERN.fullmatch(payload["source_commit"])
        assert _git_commit_exists(payload["source_commit"])
        assert payload["reviewer"] == reviewer_id


def test_reviewer_cases_are_ordered_unique_and_have_valid_reason_and_repair_shapes() -> None:
    for path in (DEEPSEEK_PATH, MIMO_PATH):
        results = _load(path)["results"]

        assert [item["case_id"] for item in results] == list(CASE_IDS)
        assert len({item["case_id"] for item in results}) == 19

        for item in results:
            assert item["verdict"] in {"PASS", "REPAIR", "FAIL"}
            assert isinstance(item["reason"], str)
            assert item["reason"].strip()
            if item["verdict"] == "REPAIR":
                assert set(item) == {"case_id", "verdict", "reason", "repair_plan"}
                repair_plan = item["repair_plan"]
                assert set(repair_plan) == {"preserve", "changes"}
                assert isinstance(repair_plan["preserve"], list)
                assert isinstance(repair_plan["changes"], list)
                assert repair_plan["preserve"]
                assert repair_plan["changes"]
                assert all(
                    isinstance(entry, str) and entry.strip()
                    for entry in repair_plan["preserve"] + repair_plan["changes"]
                )
            else:
                assert set(item) == {"case_id", "verdict", "reason"}


def test_agreement_counts_and_case_05_oracle_adjudication_are_frozen(
    authority: dict[str, Any],
) -> None:
    deepseek = _results_by_case(DEEPSEEK_PATH)
    mimo = _results_by_case(MIMO_PATH)
    oracle_by_case = {
        f"case_{index:02d}": case["expected"]
        for index, case in enumerate(authority["cases"], start=1)
    }

    deepseek_matches = [
        case_id
        for case_id in CASE_IDS
        if deepseek[case_id]["verdict"] == oracle_by_case[case_id]["outcome"]
    ]
    mimo_matches = [
        case_id
        for case_id in CASE_IDS
        if mimo[case_id]["verdict"] == oracle_by_case[case_id]["outcome"]
    ]
    reviewer_disagreements = [
        case_id
        for case_id in CASE_IDS
        if deepseek[case_id]["verdict"] != mimo[case_id]["verdict"]
    ]

    assert len(deepseek_matches) == 19
    assert len(mimo_matches) == 18
    assert reviewer_disagreements == ["case_05"]

    case_05 = oracle_by_case["case_05"]
    assert case_05["outcome"] == "REPAIR"
    assert [finding["code"] for finding in case_05["findings"]] == [
        "TRIGGER_SUBJECT_AMBIGUOUS"
    ]
    assert deepseek["case_05"]["verdict"] == "REPAIR"
    assert mimo["case_05"]["verdict"] == "FAIL"


def test_blind_review_report_is_english_and_records_freeze_evidence() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")

    assert not re.search(r"[\u3400-\u9fff]", report)
    assert "Ox Alpha" not in report
    for required in (
        COMMIT_A,
        "evals/fixtures/character_skill_failure_cases_v0.1.1.json",
        "evals/fixtures/hermes_character_skill_s0_blind_cases_v0.1.1.json",
        "docs/character_generation/character_skill_failure_cases_v0.1.1.md",
        "deepseek-v4-flash",
        "mimo-v2.5",
        "MiMo v2.5",
        "19/19",
        "18/19",
        "case_05",
        "REPAIR / TRIGGER_SUBJECT_AMBIGUOUS",
        "syntax-only normalization",
        "raw transport artifact",
        "not included in the repository",
    ):
        assert required in report


def test_commit_a_source_assets_are_unchanged_after_freeze() -> None:
    source_assets = (
        "evals/fixtures/character_skill_failure_cases_v0.1.1.json",
        "docs/character_generation/character_skill_failure_cases_v0.1.1.md",
        "evals/fixtures/hermes_character_skill_s0_blind_cases_v0.1.1.json",
    )

    for relative_path in source_assets:
        assert (ROOT / relative_path).read_bytes() == _git_show(COMMIT_A, relative_path)
