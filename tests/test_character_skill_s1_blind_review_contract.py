from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE_PATH = ROOT / "evals" / "fixtures" / "character_skill_interface_prototype_cases_v0.1.1.public.json"
PROMPT_PATH = ROOT / "evals" / "fixtures" / "character_skill_s1_blind_review_prompt_v0.1.1.md"
SCHEMA_PATH = ROOT / "evals" / "fixtures" / "character_skill_s1_blind_review_output_schema_v0.1.1.json"
MANIFEST_PATH = ROOT / "evals" / "fixtures" / "character_skill_s1_blind_review_input_manifest_v0.1.1.json"
RESULTS_DIR = ROOT / "evals" / "results"

CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 20))
INPUT_PATHS = (
    "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json",
    "evals/fixtures/character_skill_s1_blind_review_prompt_v0.1.1.md",
    "evals/fixtures/character_skill_s1_blind_review_output_schema_v0.1.1.json",
)
RESULT_PATHS = (
    RESULTS_DIR / "character_skill_s1_blind_review_deepseek_v0.1.1.json",
    RESULTS_DIR / "character_skill_s1_blind_review_mimo_v0.1.1.json",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for key, child in value.items():
            values.extend(_walk(key))
            values.extend(_walk(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk(child))
    return values


def test_input_manifest_has_raw_byte_digests_for_exact_three_inputs() -> None:
    manifest = _load(MANIFEST_PATH)

    assert set(manifest) == {"schema_version", "input_files"}
    assert manifest["schema_version"] == (
        "character-skill-interface-blind-review-input-manifest/0.1.1"
    )
    assert "source_commit" not in manifest

    entries = manifest["input_files"]
    assert [entry["path"] for entry in entries] == list(INPUT_PATHS)
    assert len(entries) == len(INPUT_PATHS)

    for entry, relative_path in zip(entries, INPUT_PATHS):
        assert set(entry) == {"path", "sha256"}
        digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert entry["sha256"] == digest
        assert SHA256_PATTERN.fullmatch(entry["sha256"])


def test_public_fixture_has_nineteen_ordered_unique_cases_without_oracle_fields() -> None:
    fixture = _load(PUBLIC_FIXTURE_PATH)

    assert set(fixture) == {"schema_version", "cases"}
    assert fixture["schema_version"] == "character-skill-interface-blind-review-input/0.1.1"
    cases = fixture["cases"]
    assert [case["case_id"] for case in cases] == list(CASE_IDS)
    assert len({case["case_id"] for case in cases}) == 19

    serialized = json.dumps(fixture, ensure_ascii=False).lower()
    for forbidden_token in (
        "\"expected\"",
        "\"outcome\"",
        "\"finding\"",
        "\"findings\"",
        "\"oracle\"",
        "\"repairable\"",
        "\"authorized_paths\"",
        "acceptance mapping",
    ):
        assert forbidden_token not in serialized

    keys_and_values = _walk(fixture)
    assert "character_skill_interface_prototype_cases_v0.1.1.json" not in keys_and_values


def test_prompt_is_standalone_and_does_not_name_hidden_review_material() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json" in prompt
    assert "evals/fixtures/character_skill_s1_blind_review_output_schema_v0.1.1.json" in prompt
    assert "review package contains this prompt plus two semantic inputs" in prompt
    assert "The semantic inputs are only the public case fixture and the output schema" in prompt
    assert "PASS" in prompt
    assert "`NONE`" in prompt
    assert "non-`NONE`" in prompt
    assert "character_skill_interface_prototype_cases_v0.1.1.json" not in prompt
    assert "character_skill_interface_options_v0.1.1.md" not in prompt
    assert "tests/" not in prompt
    assert "acceptance mapping" not in prompt.lower()
    assert "expected mapping" not in prompt.lower()
    assert "expected verdict" not in prompt.lower()
    assert "section 13" not in prompt.lower()

    # No case-specific code or verdict mapping may be encoded in the prompt.
    assert not re.search(r"case_\d{2}\s*(?:[:=]|->)\s*[A-Z][A-Z0-9_]+", prompt)


def test_output_schema_has_fixed_top_level_and_provenance_contract() -> None:
    schema = _load(SCHEMA_PATH)

    assert schema["$id"] == "character-skill-interface-blind-review-output/0.1.1"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "schema_version",
        "source_commit",
        "reviewer",
        "input_files",
        "provenance",
        "results",
    ]
    assert set(schema["properties"]) == set(schema["required"])
    assert schema["properties"]["schema_version"]["const"] == schema["$id"]
    assert schema["properties"]["source_commit"]["pattern"] == r"^[0-9a-f]{40}$"
    assert schema["properties"]["reviewer"]["enum"] == [
        "deepseek-v4-flash",
        "mimo-v2.5",
    ]

    input_files = schema["properties"]["input_files"]
    assert input_files["minItems"] == input_files["maxItems"] == 3
    assert input_files["items"]["$ref"] == "#/$defs/input_file"
    input_file = schema["$defs"]["input_file"]
    assert input_file["required"] == ["path", "sha256"]
    assert input_file["properties"]["path"]["enum"] == list(INPUT_PATHS)
    assert input_file["properties"]["sha256"]["pattern"] == r"^[0-9a-f]{64}$"

    provenance = schema["properties"]["provenance"]
    assert provenance["required"] == [
        "provider",
        "model_requested",
        "model_reported",
        "generated_at",
        "request_id",
        "normalization",
    ]
    assert provenance["additionalProperties"] is False
    assert provenance["properties"]["generated_at"]["format"] == "date-time"


def test_output_schema_has_nineteen_results_and_repair_only_condition() -> None:
    schema = _load(SCHEMA_PATH)
    results = schema["properties"]["results"]
    assert results["minItems"] == results["maxItems"] == 19
    assert results["items"]["$ref"] == "#/$defs/result"

    result = schema["$defs"]["result"]
    assert result["required"] == ["case_id", "verdict", "primary_finding", "reason"]
    assert result["properties"]["case_id"]["pattern"] == r"^case_(0[1-9]|1[0-9])$"
    assert result["properties"]["verdict"]["enum"] == ["PASS", "REPAIR", "FAIL"]
    assert result["properties"]["primary_finding"]["pattern"] == (
        r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$"
    )
    assert "interface_risks" in result["properties"]
    assert "provider_difficulty" in result["properties"]

    repair_plan = result["properties"]["repair_plan"]
    assert repair_plan["required"] == ["preserve", "changes"]
    assert repair_plan["properties"]["preserve"]["$ref"] == "#/$defs/non_empty_string_array"
    assert repair_plan["properties"]["changes"]["$ref"] == "#/$defs/non_empty_string_array"

    conditions = result["allOf"]
    repair_condition = next(
        condition
        for condition in conditions
        if condition["if"]["properties"]["verdict"].get("const") == "REPAIR"
    )
    assert repair_condition["then"]["required"] == ["repair_plan"]
    assert repair_condition["else"]["not"]["required"] == ["repair_plan"]

    pass_condition = next(
        condition
        for condition in conditions
        if condition["if"]["properties"]["verdict"].get("const") == "PASS"
    )
    assert pass_condition["then"]["properties"]["primary_finding"] == {"const": "NONE"}

    non_pass_condition = next(
        condition
        for condition in conditions
        if condition["if"]["properties"]["verdict"].get("enum") == ["REPAIR", "FAIL"]
    )
    assert non_pass_condition["then"]["properties"]["primary_finding"] == {
        "not": {"const": "NONE"}
    }


def test_reviewer_result_paths_are_reserved_without_fabricating_outputs() -> None:
    assert [path.name for path in RESULT_PATHS] == [
        "character_skill_s1_blind_review_deepseek_v0.1.1.json",
        "character_skill_s1_blind_review_mimo_v0.1.1.json",
    ]
    assert all(path.parent == RESULTS_DIR for path in RESULT_PATHS)


def test_contract_worktree_diff_contains_no_src_changes() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", "src"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    allowed_diagnostics = {
        "src/agents/character_generation.py",
        "src/agents/models.py",
        "src/character_skill/__init__.py",
        "src/character_skill/contract.py",
        "src/character_skill/errors.py",
    }
    changed = {
        line[3:].replace("\\", "/")
        for line in result.stdout.splitlines()
        if len(line) >= 4
    }
    assert changed <= allowed_diagnostics
