from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from reference_corpus.repository import CharacterReferenceRepository
from web.app import create_app
from web.services.reference_characters import ReferenceCharacterReadApplication

FIXTURES = Path(__file__).parent / "reference_corpus" / "fixtures" / "valid"


def test_reference_character_list_is_bounded_and_uses_real_production_records() -> None:
    response = TestClient(create_app()).get("/api/reference-characters")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-reference-character-list/0.1"
    assert body["total"] == 16
    jane = next(item for item in body["characters"] if item["reference_id"] == "zenless-zone-zero:jane-doe")
    assert jane["display_name"] == "Jane Doe"
    assert jane["game_name"] == "Zenless Zone Zero"
    assert jane["combat_roles"] == ["on_field_dps"]
    assert "facts" not in jane
    assert "abilities" not in jane


def test_reference_character_list_supports_search_ip_and_role_filters() -> None:
    client = TestClient(create_app())

    search = client.get("/api/reference-characters", params={"q": "Jane Doe"})
    assert [item["reference_id"] for item in search.json()["characters"]] == [
        "zenless-zone-zero:jane-doe"
    ]

    ip = client.get("/api/reference-characters", params={"ip": "Zenless Zone Zero"})
    assert ip.json()["total"] == 5
    assert all(item["game_id"] == "zenless-zone-zero" for item in ip.json()["characters"])

    role = client.get("/api/reference-characters", params={"combat_role": "on_field_dps"})
    assert role.json()["total"] == 4


def test_reference_character_detail_exposes_explicit_facts_analysis_and_sources() -> None:
    response = TestClient(create_app()).get(
        "/api/reference-characters/zenless-zone-zero:jane-doe"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-reference-character/0.1"
    assert body["identity"]["canonical_name"] == "Jane Doe"
    assert body["identity"]["localized_names"]["zh-CN"] == "简·杜"
    assert body["facts"]["narrative"]["faction"] == (
        "Public Security - Criminal Investigation Special Response Team"
    )
    assert body["abilities"]
    assert body["combat_analysis"]["combat"]["normalized_roles"] == ["on_field_dps"]
    assert body["sources"]
    assert body["sources"][0]["url"].startswith("https://")
    assert "D:\\" not in response.text
    assert "Traceback" not in response.text


def test_reference_character_detail_handles_missing_analysis_without_500(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    character_root = root / "characters" / "test-game-alpha"
    shutil.copytree(FIXTURES / "missing_optional_analysis", character_root / "minimal")
    repository = CharacterReferenceRepository(root, manifest_policy="unmanaged")
    service = ReferenceCharacterReadApplication(repository=repository)

    response = TestClient(create_app(reference_service=service)).get(
        "/api/reference-characters/test-game-alpha:test-character-b"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["combat_analysis"] is None
    assert body["metadata"]["analysis_status"] == "missing"
    assert body["abilities"][0]["description_summary"] is None


def test_reference_character_detail_not_found_is_safe_and_stable() -> None:
    response = TestClient(create_app()).get("/api/reference-characters/no-such-record")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REFERENCE_CHARACTER_NOT_FOUND"
    assert "no-such-record" not in response.text
    assert "Traceback" not in response.text


def test_reference_character_api_preserves_unicode_and_does_not_leak_corpus_paths() -> None:
    response = TestClient(create_app()).get(
        "/api/reference-characters/genshin-impact:furina"
    )

    assert response.status_code == 200
    assert "芙宁娜" in response.text
    assert "src/along_street_resources" not in response.text
    assert "reference_corpus" not in response.text
