"""Validate packaged runtime resources through the production loaders."""

from __future__ import annotations

import json
import sys
from importlib.abc import Traversable
from pathlib import Path

EXPECTED_RESOURCE_COUNT = 69
EXPECTED_MANIFEST_BASELINE = "reference-corpus-v0.5"
EXPECTED_MANIFEST_SCHEMA = "character-reference-corpus-manifest/0.2"
EXPECTED_RECORD_COUNT = 16
RESOURCE_SUFFIXES = frozenset({".yaml", ".yml", ".md"})


def _packaged_resource_names(root: Traversable) -> set[str]:
    names: set[str] = set()

    def visit(current: Traversable, prefix: str = "") -> None:
        for child in current.iterdir():
            name = f"{prefix}{child.name}"
            if child.is_dir():
                visit(child, f"{name}/")
            elif child.is_file() and Path(child.name).suffix in RESOURCE_SUFFIXES:
                names.add(name)

    visit(root)
    return names


def _bootstrap_source_import() -> None:
    if __name__ != "__main__":
        return
    source_root = Path(__file__).resolve().parents[2] / "src"
    if source_root.is_dir() and str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))


def validate_runtime() -> dict[str, object]:
    """Run the offline runtime boundary checks and return a JSON-safe summary."""

    from agents.official_character_authoring import load_reference_grounding
    from along_street_resources import data_resource, data_root
    from knowledge.loader import load_canon
    from reference_corpus.loader import load_corpus_manifest
    from story import load_story_repository

    resource_names = _packaged_resource_names(data_root())
    if len(resource_names) != EXPECTED_RESOURCE_COUNT:
        raise RuntimeError(
            f"unexpected packaged runtime resource count: {len(resource_names)}"
        )
    if any("fixture_plan" in name for name in resource_names):
        raise RuntimeError("fixture_plan must remain outside packaged runtime resources")

    manifest = load_corpus_manifest(
        data_resource(
            "reference_corpus",
            "characters",
            "_catalog",
            "corpus_manifest.yaml",
        )
    )
    if manifest.baseline_id != EXPECTED_MANIFEST_BASELINE:
        raise RuntimeError(f"unexpected corpus baseline: {manifest.baseline_id}")
    if (
        manifest.schema_version != EXPECTED_MANIFEST_SCHEMA
        or manifest.record_count != EXPECTED_RECORD_COUNT
        or len(manifest.records) != EXPECTED_RECORD_COUNT
    ):
        raise RuntimeError(
            "unexpected corpus manifest boundary: "
            f"schema={manifest.schema_version!r} records={manifest.record_count}"
        )

    canon = load_canon()
    story = load_story_repository()
    grounding = load_reference_grounding("ordinary urban support character")
    if not canon["characters"]:
        raise RuntimeError("load_canon returned no characters")
    if not story.definitions:
        raise RuntimeError("load_story_repository returned no definitions")
    if (
        grounding.corpus_baseline_id != EXPECTED_MANIFEST_BASELINE
        or grounding.manifest_schema_version != EXPECTED_MANIFEST_SCHEMA
        or grounding.total_records != EXPECTED_RECORD_COUNT
    ):
        raise RuntimeError(
            "unexpected reference grounding boundary: "
            f"baseline={grounding.corpus_baseline_id!r} "
            f"records={grounding.total_records}"
        )

    return {
        "canon_characters": len(canon["characters"]),
        "reference_records": grounding.total_records,
        "resource_count": len(resource_names),
        "story_definitions": len(story.definitions),
    }


def main() -> int:
    _bootstrap_source_import()
    print(json.dumps(validate_runtime(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
