from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from scripts.project_preflight import (
    build_preflight,
    load_aliases,
    main,
    resolve_topics,
)
from scripts.query_project_graph import load_yaml

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "knowledge" / "project_graph.yaml"
ALIASES_PATH = ROOT / "knowledge" / "topic_aliases.yaml"


def graph() -> dict:
    return load_yaml(GRAPH_PATH)


def aliases() -> dict[str, list[str]]:
    return load_aliases(ALIASES_PATH)


def clean_git() -> dict[str, str]:
    return {
        "branch": "main",
        "head": "d1e511ebe82684867c3beff9ccc6bd1c36bbbbf6",
        "working_tree": "clean",
    }


def test_explicit_combat_topic_is_ready_with_snapshot_warning() -> None:
    verdict, output = build_preflight(
        graph(),
        graph_path=GRAPH_PATH,
        aliases=aliases(),
        explicit_topics=["combat_role"],
        current_git={**clean_git(), "working_tree": "dirty"},
    )
    assert verdict == "READY_WITH_WARNINGS"
    assert "src/combat_semantics/roles.py" in output


def test_task_mode_maps_combat_role_alias() -> None:
    resolved, matched, _ = resolve_topics(
        graph=graph(), aliases=aliases(), task="Modify character combat role handling"
    )
    assert "combat_role" in resolved
    assert "component.combat_role_profile" in matched["combat_role"]


def test_task_mode_maps_character_draft_and_canon_checker() -> None:
    resolved, _, _ = resolve_topics(
        graph=graph(),
        aliases=aliases(),
        task="Change how generated CharacterDraft is validated by CanonChecker",
    )
    assert {"character_generation", "canon_checker"}.issubset(resolved)


def test_legacy_and_frozen_markers_are_rendered() -> None:
    _, output = build_preflight(
        graph(),
        graph_path=GRAPH_PATH,
        aliases=aliases(),
        explicit_topics=["combat_role"],
        current_git={**clean_git(), "working_tree": "dirty"},
    )
    assert "CANONICAL SOURCE" in output
    assert "DO NOT TREAT AS CANONICAL" in output
    assert "FROZEN CONTRACT" in output


def test_head_mismatch_is_reported_without_blocking() -> None:
    verdict, output = build_preflight(
        graph(),
        graph_path=GRAPH_PATH,
        aliases=aliases(),
        explicit_topics=["combat_role"],
        current_git={"branch": "main", "head": "different-head", "working_tree": "clean"},
    )
    assert verdict == "READY_WITH_WARNINGS"
    assert "GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE" in output


def test_vague_task_returns_insufficient_context() -> None:
    verdict, output = build_preflight(
        graph(),
        graph_path=GRAPH_PATH,
        aliases=aliases(),
        task="fix weird thing",
        current_git=clean_git(),
    )
    assert verdict == "INSUFFICIENT_CONTEXT"
    assert "NO_RELIABLE_TOPIC_MATCH" in output
    assert "Available graph candidates" in output


def test_invalid_graph_returns_graph_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid_graph = graph()
    invalid_graph["edges"][0]["to"] = "missing.node"
    graph_file = tmp_path / "project_graph.yaml"
    aliases_file = tmp_path / "topic_aliases.yaml"
    graph_file.write_text(
        yaml.safe_dump(invalid_graph, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    aliases_file.write_text(ALIASES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "project_preflight.py",
            "--graph",
            str(graph_file),
            "--aliases",
            str(aliases_file),
            "--topic",
            "combat_role",
        ],
    )
    assert main() == 2
    assert "GRAPH_INVALID" in capsys.readouterr().err


def test_query_output_is_deterministic() -> None:
    arguments = {
        "graph_path": GRAPH_PATH,
        "aliases": aliases(),
        "task": "Modify character combat role handling",
        "current_git": {**clean_git(), "working_tree": "dirty"},
    }
    first = build_preflight(graph(), **arguments)
    second = build_preflight(graph(), **arguments)
    assert first == second
