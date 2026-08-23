"""Verify that an installed wheel can load all packaged runtime resources.

Usage:
    python scripts/verify_wheel_runtime_resources.py --wheel dist/project.whl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


RESOURCE_SUFFIXES = {".yaml", ".yml", ".md"}
PACKAGE_DATA_PREFIX = "along_street_resources/data/"


def _source_resource_names(source_root: Path) -> set[str]:
    data_root = source_root / "src" / "along_street_resources" / "data"
    return {
        path.relative_to(data_root).as_posix()
        for path in data_root.rglob("*")
        if path.is_file() and path.suffix in RESOURCE_SUFFIXES
    }


def _wheel_resource_names(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as archive:
        return {
            str(PurePosixPath(name).relative_to(PACKAGE_DATA_PREFIX.rstrip("/")))
            for name in archive.namelist()
            if name.startswith(PACKAGE_DATA_PREFIX)
            and not name.endswith("/")
            and PurePosixPath(name).suffix in RESOURCE_SUFFIXES
        }


def _run_installed_smoke(
    *, wheel: Path, expected_names: set[str], python: str
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="along-street-wheel-target-") as target_name:
        target = Path(target_name)
        install = subprocess.run(
            [python, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)],
            capture_output=True,
            text=True,
            check=False,
        )
        if install.returncode:
            raise RuntimeError(
                "wheel installation failed:\n"
                f"stdout={install.stdout}\nstderr={install.stderr}"
            )

        smoke_cwd = target / "outside-repository-cwd"
        smoke_cwd.mkdir()
        target_literal = json.dumps(str(target))
        expected_literal = json.dumps(sorted(expected_names))
        script = f"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, {target_literal})

from agents.official_character_authoring import load_reference_grounding
from along_street_resources import data_root
from character_intelligence.intent.parser import DeterministicCharacterDesignIntentParser
from knowledge import KnowledgeResolver
from knowledge.loader import load_canon
from story import load_story_repository

EXPECTED = set({expected_literal})

def resource_names(root):
    names = set()
    def visit(current, prefix=""):
        for child in current.iterdir():
            name = f"{{prefix}}{{child.name}}"
            if child.is_dir():
                visit(child, name + "/")
            elif child.is_file() and Path(child.name).suffix in {{".yaml", ".yml", ".md"}}:
                names.add(name)
    visit(root)
    return names

def copy_resources(source, target):
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            destination.mkdir()
            copy_resources(child, destination)
        elif child.is_file():
            with child.open("rb") as source_stream, destination.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)

packaged = resource_names(data_root())
assert packaged == EXPECTED, (len(packaged), len(EXPECTED), sorted(packaged ^ EXPECTED))
canon = load_canon()
story = load_story_repository()
grounding = load_reference_grounding("ordinary urban support character")
parser = DeterministicCharacterDesignIntentParser()
parsed = parser.parse("a support character")
assert canon["characters"]
assert story.definitions
assert grounding.total_records > 0
assert parsed.combat_role_profile is not None

with tempfile.TemporaryDirectory(prefix="along-street-explicit-data-") as override_name:
    override = Path(override_name)
    copy_resources(data_root(), override)
    assert load_canon(override)["characters"]
    assert load_story_repository(override).definitions
    assert load_reference_grounding(
        "ordinary urban support character",
        corpus_root=override / "reference_corpus" / "characters",
    ).total_records == grounding.total_records
    assert KnowledgeResolver(data_dir=override).characters

print(json.dumps({{
    "resource_count": len(packaged),
    "canon_characters": len(canon["characters"]),
    "story_definitions": len(story.definitions),
    "reference_records": grounding.total_records,
    "parser": type(parser).__name__,
    "explicit_overrides": True,
}}, ensure_ascii=False, sort_keys=True))
"""
        smoke = subprocess.run(
            [python, "-I", "-c", script],
            cwd=smoke_cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if smoke.returncode:
            raise RuntimeError(
                "installed wheel smoke failed:\n"
                f"stdout={smoke.stdout}\nstderr={smoke.stderr}"
            )
        return json.loads(smoke.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    source_names = _source_resource_names(args.source_root.resolve())
    wheel_names = _wheel_resource_names(args.wheel.resolve())
    if source_names != wheel_names:
        missing = sorted(source_names - wheel_names)
        unexpected = sorted(wheel_names - source_names)
        raise SystemExit(
            "wheel resource set mismatch: "
            f"source={len(source_names)} wheel={len(wheel_names)} "
            f"missing={missing} unexpected={unexpected}"
        )
    smoke = _run_installed_smoke(
        wheel=args.wheel.resolve(),
        expected_names=source_names,
        python=args.python,
    )
    print(
        json.dumps(
            {
                "source_resource_count": len(source_names),
                "wheel_resource_count": len(wheel_names),
                "resource_sets_match": True,
                "installed_smoke": smoke,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
