from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "evals" / "fixtures" / "character_skill_interface_prototype_cases_v0.1.1.json"
MANIFEST_PATH = ROOT / "evals" / "fixtures" / "character_skill_s1_blind_review_input_manifest_v0.1.1.json"
DEEPSEEK_PATH = ROOT / "evals" / "results" / "character_skill_s1_blind_review_deepseek_v0.1.1.json"
MIMO_PATH = ROOT / "evals" / "results" / "character_skill_s1_blind_review_mimo_v0.1.1.json"
REPORT_PATH = ROOT / "evals" / "results" / "character_skill_s1_blind_review_report_v0.1.1.md"
CONTRACT_PATH = ROOT / "docs" / "character_generation" / "character_skill_interface_options_v0.1.1.md"

SOURCE_COMMIT = "c578b091f47dee3a0410fbc4bb5d1176bc2e28d4"
SCHEMA_VERSION = "character-skill-interface-blind-review-output/0.1.1"
CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 20))
REVIEWERS = {
    DEEPSEEK_PATH: "deepseek-v4-flash",
    MIMO_PATH: "mimo-v2.5",
}
STORED_SHA256 = {
    DEEPSEEK_PATH: "682dfdc58a43b0c44fe48cd8976fcf14b60c9378d4f76f3d18f138118152d5ee",
    MIMO_PATH: "d97aebe31c4a8b401864bb184825b82dddb377bec4aa953bd6a60507958cf490",
}
FINDING_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _results_by_case(path: Path) -> dict[str, dict[str, Any]]:
    return {result["case_id"]: result for result in _load(path)["results"]}


def test_reviewer_outputs_bind_exact_commit_inputs_and_provenance() -> None:
    manifest_inputs = _load(MANIFEST_PATH)["input_files"]

    for path, reviewer in REVIEWERS.items():
        payload = _load(path)
        assert set(payload) == {
            "schema_version",
            "source_commit",
            "reviewer",
            "input_files",
            "provenance",
            "results",
        }
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["source_commit"] == SOURCE_COMMIT
        assert payload["reviewer"] == reviewer
        assert payload["input_files"] == manifest_inputs

        provenance = payload["provenance"]
        assert provenance == {
            "provider": "opencode-go",
            "model_requested": reviewer,
            "model_reported": reviewer,
            "generated_at": provenance["generated_at"],
            "request_id": "redacted:manual-hermes-review",
            "normalization": "none",
        }
        assert re.fullmatch(r"2026-08-23T\d{2}:\d{2}:\d{2}Z", provenance["generated_at"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == STORED_SHA256[path]


def test_reviewer_outputs_have_complete_ordered_result_contract() -> None:
    for path in REVIEWERS:
        results = _load(path)["results"]
        assert [result["case_id"] for result in results] == list(CASE_IDS)
        assert len({result["case_id"] for result in results}) == 19

        for result in results:
            assert result["verdict"] in {"PASS", "REPAIR", "FAIL"}
            assert FINDING_PATTERN.fullmatch(result["primary_finding"])
            assert result["reason"].strip()
            if result["verdict"] == "PASS":
                assert result["primary_finding"] == "NONE"
                assert "repair_plan" not in result
            elif result["verdict"] == "REPAIR":
                assert result["primary_finding"] != "NONE"
                assert all(result["repair_plan"][key] for key in ("preserve", "changes"))
            else:
                assert result["primary_finding"] != "NONE"
                assert "repair_plan" not in result


def test_verdict_agreement_counts_and_disagreements_are_frozen() -> None:
    oracle = {
        case_id: case["expected"]
        for case_id, case in zip(CASE_IDS, _load(AUTHORITY_PATH)["cases"])
    }
    deepseek = _results_by_case(DEEPSEEK_PATH)
    mimo = _results_by_case(MIMO_PATH)

    assert sum(deepseek[case_id]["verdict"] == oracle[case_id]["outcome"] for case_id in CASE_IDS) == 18
    assert sum(mimo[case_id]["verdict"] == oracle[case_id]["outcome"] for case_id in CASE_IDS) == 14
    assert sum(deepseek[case_id]["verdict"] == mimo[case_id]["verdict"] for case_id in CASE_IDS) == 15
    assert sum(
        deepseek[case_id]["verdict"] == mimo[case_id]["verdict"] == oracle[case_id]["outcome"]
        for case_id in CASE_IDS
    ) == 14

    assert {
        case_id
        for case_id in CASE_IDS
        if deepseek[case_id]["verdict"] != mimo[case_id]["verdict"]
    } == {"case_02", "case_04", "case_06", "case_17"}

    assert deepseek["case_15"]["verdict"] == mimo["case_15"]["verdict"] == "PASS"
    assert oracle["case_15"] == {"outcome": "FAIL", "primary": "REFERENCE_COPYING"}
    assert deepseek["case_19"]["verdict"] == mimo["case_19"]["verdict"] == "REPAIR"


def test_report_records_sol_adjudication_provenance_limit_and_freeze() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    for token in (
        "Status: **CS-S1 FROZEN**",
        SOURCE_COMMIT,
        "0a8c70040807baff1b665313b90b681a026a163ca79b797862cc1a0979a93169",
        "af2720a6f2fd16728aeffc1058b98b86570f370ff9679ef5e50fdef669c40b91",
        "18/19",
        "14/19",
        "15/19",
        "case_02",
        "case_04",
        "case_06",
        "case_15",
        "case_17",
        "case_19",
        "REFERENCE_COPYING",
        "user-supplied Hermes final-response artifacts",
        "No independent Hermes usage file or public provider request ID was retained",
        "`src/` remains unchanged",
    ):
        assert token in report


def test_interface_contract_now_marks_cs_s1_frozen_without_authorizing_src() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "Status: **CS-S1 FROZEN**" in contract
    assert "does not mark `CS-S1 FROZEN`" not in contract
    assert "does not authorize production integration under `src/`" in " ".join(
        contract.split()
    )
