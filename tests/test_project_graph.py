from __future__ import annotations

from pathlib import Path

import pytest

from scripts.query_project_graph import (
    GraphValidationError,
    build_query_result,
    git_state,
    render_markdown,
    repository_root_from_graph_path,
    snapshot_warnings,
    validate_graph,
)

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "knowledge" / "project_graph.yaml"


def load_graph() -> dict:
    import yaml

    with GRAPH_PATH.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_project_graph_schema_and_repository_paths_are_valid() -> None:
    validate_graph(load_graph(), GRAPH_PATH)


def test_repository_root_is_derived_from_graph_checkout_not_metadata(tmp_path: Path) -> None:
    graph_path = tmp_path / "knowledge" / "project_graph.yaml"
    graph_path.parent.mkdir()
    (tmp_path / ".git").mkdir()
    graph_path.write_text("{}", encoding="utf-8")

    assert repository_root_from_graph_path(graph_path) == tmp_path.resolve()


def test_windows_style_project_root_is_rejected_as_nonportable() -> None:
    graph = load_graph()
    graph["snapshot"]["project_root"] = "D:/game-ai-agent"
    with pytest.raises(GraphValidationError, match="repository-relative"):
        validate_graph(graph, GRAPH_PATH, check_paths=False)


def test_relative_evidence_resolves_under_actual_temporary_repository_root(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "knowledge" / "project_graph.yaml"
    graph_path.parent.mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "foo.md").write_text("evidence\n", encoding="utf-8")
    graph = {
        "schema_version": "engineering-knowledge-graph/0.1",
        "snapshot": {
            "project": "fixture",
            "project_root": ".",
            "branch": "main",
            "base_head": "fixture-head",
            "working_tree": "clean",
            "snapshot_kind": "clean_head",
            "release_equivalent": True,
        },
        "nodes": [
            {
                "id": "component.fixture",
                "type": "component",
                "name": "Fixture",
                "status": "stable",
                "responsibility": "Fixture evidence.",
                "evidence": [{"path": "docs/foo.md", "locator": "evidence"}],
            }
        ],
        "edges": [],
        "constraints": [],
        "known_limitations": [],
        "architecture_decisions": [],
    }

    validate_graph(graph, graph_path)


def test_node_ids_are_unique() -> None:
    graph = load_graph()
    graph["nodes"].append(dict(graph["nodes"][0]))
    with pytest.raises(GraphValidationError, match="Duplicate node ID"):
        validate_graph(graph, GRAPH_PATH, check_paths=False)


def test_edges_have_valid_endpoints_and_relations() -> None:
    graph = load_graph()
    graph["edges"] = [{"from": "missing", "relation": "depends_on", "to": graph["nodes"][0]["id"]}]
    with pytest.raises(GraphValidationError, match="Dangling edge"):
        validate_graph(graph, GRAPH_PATH, check_paths=False)


def test_invalid_relation_is_rejected() -> None:
    graph = load_graph()
    graph["edges"] = [
        {
            "from": graph["nodes"][0]["id"],
            "relation": "relates_to",
            "to": graph["nodes"][1]["id"],
            "evidence": [],
        }
    ]
    with pytest.raises(GraphValidationError, match="Invalid relation"):
        validate_graph(graph, GRAPH_PATH, check_paths=False)


def test_missing_path_is_rejected() -> None:
    graph = load_graph()
    graph["nodes"][0]["path"] = "does/not/exist.py"
    with pytest.raises(GraphValidationError, match="path does not exist"):
        validate_graph(graph, GRAPH_PATH)


def test_canonical_ownership_conflict_is_rejected() -> None:
    graph = load_graph()
    graph["nodes"].append(
        {
            "id": "component.conflicting_owner",
            "type": "component",
            "name": "Conflicting owner",
            "status": "stable",
            "responsibility": "Test conflict",
            "evidence": [],
        }
    )
    graph["edges"].append(
        {
            "from": "component.conflicting_owner",
            "relation": "canonical_for",
            "to": "concept.canonical_combat_roles",
            "evidence": [],
        }
    )
    with pytest.raises(GraphValidationError, match="Canonical ownership conflict"):
        validate_graph(graph, GRAPH_PATH, check_paths=False)


def test_combat_role_query_is_deterministic_and_returns_canonical_source() -> None:
    result = build_query_result(load_graph(), ["combat_role"])
    assert "src/combat_semantics/roles.py" in result["canonical_sources"]
    assert "tests/test_combat_role_compatibility_freeze_b15.py" in result["tests"]


def test_character_generation_query_returns_related_context() -> None:
    result = build_query_result(load_graph(), ["character_generation", "canon_checker"])
    names = {node["name"] for node in result["matches"]}
    assert {"CharacterGenerationAgent", "CanonChecker"}.issubset(names)
    assert "src/agents/character_generation.py" in result["paths"]


def test_dirty_snapshot_warning_uses_mocked_git_state() -> None:
    graph = load_graph()
    result = build_query_result(graph, ["combat_role"])
    output = render_markdown(
        result,
        {
            "branch": "main",
            "head": "different-head",
            "working_tree": "dirty",
        },
    )
    assert "WORKING TREE WARNING" in output
    assert "GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE" in output


def test_reviewed_snapshot_tooling_only_advance_is_not_architecture_mismatch() -> None:
    graph = load_graph()
    warnings = snapshot_warnings(
        graph["snapshot"],
        {"branch": "main", "head": "tooling-head", "working_tree": "clean"},
        history_paths=["knowledge/project_graph.yaml", "scripts/project_postflight.py"],
    )
    assert "ENGINEERING KNOWLEDGE TOOLING ADVANCED SINCE BASE" in warnings
    assert "GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE" not in warnings


def test_reviewed_snapshot_architecture_advance_gets_review_base_warning() -> None:
    graph = load_graph()
    warnings = snapshot_warnings(
        graph["snapshot"],
        {"branch": "main", "head": "architecture-head", "working_tree": "clean"},
        history_paths=["src/combat_semantics/roles.py"],
    )
    assert "GRAPH REVIEW BASE IS OLDER THAN ARCHITECTURE" in warnings


def test_git_state_isolated_from_dirty_fixture(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(
        command: list[str], *, text: bool, encoding: str, errors: str, stderr: object
    ) -> str:
        assert text is True
        assert encoding == "utf-8"
        assert errors == "strict"
        calls.append(command)
        if command[-2:] == ["branch", "--show-current"]:
            return "fixture-branch\n"
        if command[-2:] == ["rev-parse", "HEAD"]:
            return "fixture-head\n"
        return " M fixture.txt\n"

    state = git_state(tmp_path, fake_runner)
    assert state == {"branch": "fixture-branch", "head": "fixture-head", "working_tree": "dirty"}
    assert len(calls) == 3
