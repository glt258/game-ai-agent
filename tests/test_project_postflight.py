from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import scripts.project_postflight as postflight_module
from scripts.project_postflight import (
    Change,
    analyze_changes,
    collect_changes,
    dedupe_impacts,
    main,
    material_change,
    parse_name_status_z,
    parse_porcelain_z,
    sync_verdict,
)
from scripts.query_project_graph import load_yaml

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "knowledge" / "project_graph.yaml"


def fixture_graph() -> dict:
    return {
        "schema_version": "engineering-knowledge-graph/0.1",
        "snapshot": {
            "project": "fixture",
            "project_root": "fixture-root",
            "branch": "main",
            "head": "fixture-head",
            "release_tag": None,
            "working_tree": "clean",
            "snapshot_kind": "repository_head",
            "release_equivalent": True,
        },
        "nodes": [
            {
                "id": "component.roles",
                "type": "component",
                "name": "CombatRoleProfile",
                "status": "frozen",
                "responsibility": "Canonical combat role definitions.",
                "path": "src/combat_semantics/roles.py",
                "canonical_source": "src/combat_semantics/roles.py",
                "tests": ["tests/test_roles.py"],
                "evidence": [],
            },
            {
                "id": "component.web",
                "type": "component",
                "name": "Web Adapter",
                "status": "experimental",
                "responsibility": "Experimental Web boundary.",
                "path": "src/web",
                "evidence": [],
            },
            {
                "id": "component.provider",
                "type": "component",
                "name": "ProviderProtocol",
                "status": "stable",
                "responsibility": "Provider abstraction boundary.",
                "path": "src/agents/provider_protocol.py",
                "evidence": [],
            },
        ],
        "edges": [],
        "constraints": [
            {
                "id": "constraint.roles",
                "statement": "Roles have one canonical owner.",
                "severity": "high",
                "scope": ["component.roles"],
                "evidence": [],
            }
        ],
        "known_limitations": [
            {
                "id": "KL-FIXTURE",
                "status": "active",
                "statement": "Fixture limitation.",
                "scope": ["component.roles"],
                "evidence": [{"path": "docs/limitation.md", "locator": "fixture"}],
            }
        ],
        "architecture_decisions": [
            {
                "id": "ADR-FIXTURE",
                "title": "Fixture decision",
                "status": "frozen",
                "decision": "Keep the boundary explicit.",
                "rationale": "Test fixture.",
                "evidence": [{"path": "docs/decision.md", "locator": "fixture"}],
            }
        ],
    }


def fake_runner(old_contents: dict[str, str]):
    def runner(command: list[str], **_: object) -> SimpleNamespace:
        object_path = command[-1]
        path = object_path.split(":", 1)[-1]
        return SimpleNamespace(stdout=old_contents.get(path, "").encode())

    return runner


def analyze_fixture(
    tmp_path: Path,
    change: Change,
    old_contents: dict[str, str] | None = None,
    new_content: str = "class Current:\n    VALUE = 2\n",
) -> list[dict]:
    graph = fixture_graph()
    for directory in ("src/combat_semantics", "src/web", "src/agents", "tests", "docs"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    if not change.is_deleted:
        target = tmp_path / change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
    return analyze_changes(
        graph,
        [change],
        root=tmp_path,
        runner=fake_runner(old_contents or {}),
    )


def categories(impacts: list[dict]) -> set[str]:
    return {impact["category"] for impact in impacts}


def test_git_name_status_parsers_support_modified_added_deleted_and_renamed() -> None:
    assert parse_name_status_z("M\0src/a.py\0R100\0src/old.py\0src/new.py\0") == [
        Change("M", "src/a.py"),
        Change("R", "src/new.py", old_path="src/old.py"),
    ]
    assert parse_porcelain_z(" M src/a.py\0?? src/new.py\0R  src/old.py\0src/new.py\0") == [
        Change("M", "src/a.py"),
        Change("??", "src/new.py"),
        Change("R", "src/new.py", old_path="src/old.py"),
    ]


def test_unrelated_readme_change_is_in_sync(tmp_path: Path) -> None:
    impacts = analyze_fixture(
        tmp_path,
        Change("M", "README.md"),
        {"README.md": "old text\n"},
    )
    assert sync_verdict(True, impacts) == "IN_SYNC"


def test_formatting_only_canonical_python_change_is_not_update_required(tmp_path: Path) -> None:
    old = 'class Roles:\n    """old docs"""\n    VALUE = 1\n'
    new = 'class Roles:\n        """new docs"""\n        VALUE=1\n'
    assert material_change("roles.py", old, new) is False
    impacts = analyze_fixture(
        tmp_path,
        Change("M", "src/combat_semantics/roles.py"),
        {"src/combat_semantics/roles.py": old},
        new_content=new,
    )
    assert "K1" in categories(impacts)
    assert sync_verdict(True, impacts) != "KNOWLEDGE_UPDATE_REQUIRED"


def test_material_canonical_change_requires_knowledge_update(tmp_path: Path) -> None:
    old = "CANONICAL_ROLES = ('main_dps',)\n"
    impacts = analyze_fixture(
        tmp_path,
        Change("M", "src/combat_semantics/roles.py"),
        {"src/combat_semantics/roles.py": old},
    )
    assert "K1" in categories(impacts)
    assert sync_verdict(True, impacts) == "KNOWLEDGE_UPDATE_REQUIRED"


def test_frozen_contract_change_is_reported(tmp_path: Path) -> None:
    impacts = analyze_fixture(
        tmp_path,
        Change("M", "src/combat_semantics/roles.py"),
        {"src/combat_semantics/roles.py": "class Old:\n    VALUE = 1\n"},
    )
    assert "K2" in categories(impacts)
    assert sync_verdict(True, impacts) == "KNOWLEDGE_UPDATE_REQUIRED"


def test_deleted_and_renamed_graph_paths_are_stale(tmp_path: Path) -> None:
    deleted = analyze_fixture(
        tmp_path,
        Change("D", "src/combat_semantics/roles.py"),
        {"src/combat_semantics/roles.py": "class Old:\n    VALUE = 1\n"},
    )
    renamed = analyze_fixture(
        tmp_path,
        Change("R", "src/new_roles.py", old_path="src/combat_semantics/roles.py"),
        {"src/combat_semantics/roles.py": "class Old:\n    VALUE = 1\n"},
    )
    assert "K4" in categories(deleted)
    assert "K4" in categories(renamed)
    assert sync_verdict(True, renamed) == "KNOWLEDGE_UPDATE_REQUIRED"


def test_new_architecture_file_is_reviewed_without_auto_node_creation(tmp_path: Path) -> None:
    impacts = analyze_fixture(tmp_path, Change("??", "src/combat_semantics/new_roles.py"))
    assert "K5" in categories(impacts)
    assert sync_verdict(True, impacts) == "REVIEW_RECOMMENDED"


def test_experimental_provider_limitation_and_adr_impacts_are_detected(tmp_path: Path) -> None:
    experimental = analyze_fixture(tmp_path, Change("M", "src/web/app.py"))
    provider = analyze_fixture(tmp_path, Change("M", "src/agents/provider_protocol.py"))
    limitation = analyze_fixture(tmp_path, Change("M", "docs/limitation.md"))
    adr = analyze_fixture(tmp_path, Change("M", "docs/decision.md"))
    assert "K6" in categories(experimental)
    assert "K7" in categories(provider)
    assert "K8" in categories(limitation)
    assert "K9" in categories(adr)


def test_protected_test_change_is_reported_and_can_escalate(tmp_path: Path) -> None:
    graph = fixture_graph()
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/combat_semantics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests/test_roles.py").write_text("assert True\n", encoding="utf-8")
    (tmp_path / "src/combat_semantics/roles.py").write_text(
        "class Current:\n    VALUE = 2\n", encoding="utf-8"
    )
    impacts = analyze_changes(
        graph,
        [
            Change("M", "tests/test_roles.py"),
            Change("M", "src/combat_semantics/roles.py"),
        ],
        root=tmp_path,
        runner=fake_runner({"src/combat_semantics/roles.py": "class Old:\n    VALUE = 1\n"}),
    )
    assert "K3" in categories(impacts)
    assert "K3_ESCALATION" in categories(impacts)


def test_knowledge_layer_change_is_reported_without_recursive_update(tmp_path: Path) -> None:
    impacts = analyze_fixture(tmp_path, Change("??", "knowledge/project_graph.yaml"))
    assert "KNOWLEDGE_LAYER" in categories(impacts)


def test_postflight_output_is_deterministic_and_does_not_mutate_graph(tmp_path: Path) -> None:
    graph = load_yaml(GRAPH_PATH)
    before = copy.deepcopy(graph)
    graph_bytes_before = GRAPH_PATH.read_bytes()
    first = analyze_fixture(tmp_path, Change("??", "src/combat_semantics/new_roles.py"))
    second = analyze_fixture(tmp_path, Change("??", "src/combat_semantics/new_roles.py"))
    assert dedupe_impacts(first) == dedupe_impacts(second)
    assert graph == before
    assert GRAPH_PATH.read_bytes() == graph_bytes_before


def test_invalid_graph_cli_returns_graph_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid_graph = load_yaml(GRAPH_PATH)
    invalid_graph["edges"][0]["to"] = "missing.node"
    graph_file = tmp_path / "project_graph.yaml"
    graph_file.write_text(
        yaml.safe_dump(invalid_graph, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["project_postflight.py", "--graph", str(graph_file)])
    assert main() == 2
    assert "GRAPH_INVALID" in capsys.readouterr().err


def test_staged_collection_uses_cached_diff_without_real_git_state(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(stdout=b"M\0src/staged.py\0")

    changes = collect_changes(tmp_path, staged=True, runner=runner)
    assert changes == [Change("M", "src/staged.py")]
    assert "--cached" in calls[0]


def test_from_baseline_missing_is_explicit_cli_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(_: Path) -> tuple[Path, dict]:
        raise postflight_module.BaselineError("TASK_BASELINE_NOT_FOUND: fixture")

    monkeypatch.setattr(postflight_module, "load_baseline", missing)
    monkeypatch.setattr(sys, "argv", ["project_postflight.py", "--from-baseline"])
    assert postflight_module.main() == 2
    assert "TASK_BASELINE_NOT_FOUND" in capsys.readouterr().out


def test_from_baseline_branch_mismatch_is_explicit_cli_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = {"branch": "other-branch", "head": "old-head", "working_tree_files": []}
    monkeypatch.setattr(
        postflight_module,
        "load_baseline",
        lambda root: (root / "baseline.json", baseline),
    )
    monkeypatch.setattr(sys, "argv", ["project_postflight.py", "--from-baseline"])
    assert postflight_module.main() == 2
    assert "TASK_BASELINE_BRANCH_MISMATCH" in capsys.readouterr().out
