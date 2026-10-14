from __future__ import annotations

import json

import agents.character_generation_cli as production_cli
import agents.official_character_authoring as historical_cli


def test_v2_cli_generates_offline_draft_and_preserves_explicit_name(capsys) -> None:
    exit_code = production_cli.main(
        ["--brief", "请设计一名女性角色，定位辅助，姓名为Alice，角色年龄是25岁。", "--json"]
    )

    captured = capsys.readouterr()
    response = json.loads(captured.out)

    assert exit_code == 0
    assert response["draft"]["name"] == "Alice"
    assert response["draft"]["gender"] == "女性"
    assert response["draft"]["age"] == 25
    assert response["cli"]["route"] == "CHARACTER_GENERATION_V2"
    assert [item["id"] for item in response["pipeline"]] == [
        "concept_search",
        "concept_selector",
        "planner",
        "naming",
        "spec_freeze",
        "generation",
        "evaluation",
        "canon",
        "repair",
        "final",
    ]


def test_v2_cli_valid_scenario_preserves_canon_affiliation(capsys) -> None:
    exit_code = production_cli.main(["--scenario", "valid", "--model", "offline", "--json"])

    captured = capsys.readouterr()
    response = json.loads(captured.out)

    assert exit_code == 0
    assert response["cli"]["route"] == "CHARACTER_GENERATION_V2"
    assert response["draft"]["faction_id"] == "faction_002"
    assert [item["id"] for item in response["pipeline"]][-1] == "final"


def test_historical_module_command_forwards_to_the_v2_cli(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_main(argv):
        captured["argv"] = argv
        return 7

    monkeypatch.setattr(production_cli, "main", fake_main)

    result = historical_cli.main(["--brief", "a character brief"])

    assert result == 7
    assert captured["argv"] == ["--brief", "a character brief"]
