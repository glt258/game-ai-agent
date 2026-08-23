from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agents.official_character_authoring import load_reference_grounding
from along_street_resources import data_resource, data_root
from character_intelligence.intent.parser import DeterministicCharacterDesignIntentParser
from knowledge.loader import load_canon
from story import load_story_repository


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA_ROOT = REPOSITORY_ROOT / "src" / "along_street_resources" / "data"


def _source_resource_names() -> set[str]:
    return {
        path.relative_to(SOURCE_DATA_ROOT).as_posix()
        for path in SOURCE_DATA_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".yml", ".md"}
    }


def _traversable_resource_names(root) -> set[str]:
    names: set[str] = set()

    def visit(current, prefix: str = "") -> None:
        for child in current.iterdir():
            child_name = f"{prefix}{child.name}"
            if child.is_dir():
                visit(child, f"{child_name}/")
            elif child.is_file() and Path(child.name).suffix in {".yaml", ".yml", ".md"}:
                names.add(child_name)

    visit(root)
    return names


def test_packaged_resources_match_the_source_checkout() -> None:
    expected = _source_resource_names()
    actual = _traversable_resource_names(data_root())

    assert len(expected) == 70
    assert actual == expected
    assert data_resource("characters", "characters.yaml").is_file()


def test_default_runtime_entries_work_without_repository_cwd() -> None:
    source_path = repr(str(REPOSITORY_ROOT / "src"))
    script = f"""
import sys
sys.path.insert(0, {source_path})

from agents.official_character_authoring import load_reference_grounding
from character_intelligence.intent.parser import DeterministicCharacterDesignIntentParser
from knowledge.loader import load_canon
from story import load_story_repository

canon = load_canon()
story = load_story_repository()
grounding = load_reference_grounding("ordinary urban support character")
parser = DeterministicCharacterDesignIntentParser()
parsed = parser.parse("a support character")
assert canon["characters"]
assert story.definitions
assert grounding.total_records > 0
assert parsed.combat_role_profile is not None
print("runtime defaults ok")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=REPOSITORY_ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode:
        pytest.fail(
            "default runtime entry points failed outside the repository CWD:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def test_explicit_filesystem_overrides_remain_supported(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    for relative in (
        "characters/characters.yaml",
        "lore/lore.yaml",
        "knowledge/knowledge_rules.yaml",
        "knowledge/condition_scopes.yaml",
        "projects/projects.yaml",
        "cases/cases.yaml",
        "incidents/incidents.yaml",
        "knowledge/authorizations.yaml",
        "stories/story_canon.yaml",
        "stories/story_definitions.yaml",
        "factions/factions.yaml",
        "locations/cities.yaml",
    ):
        target = data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data_resource(*relative.split("/")).read_text(encoding="utf-8"), encoding="utf-8")

    assert load_canon(data_dir)["characters"]
    assert load_story_repository(data_dir).definitions


def test_runtime_resource_smoke_output_is_json_serializable() -> None:
    result = {
        "resource_count": len(_traversable_resource_names(data_root())),
        "canon_characters": len(load_canon()["characters"]),
        "story_definitions": len(load_story_repository().definitions),
        "reference_records": load_reference_grounding("ordinary urban support character").total_records,
        "parser_type": type(DeterministicCharacterDesignIntentParser()).__name__,
    }
    assert json.loads(json.dumps(result)) == result
