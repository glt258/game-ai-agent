from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from character_intelligence.hybrid_ir.runner import FakeProvider
from web.app import create_app
from web.services.skill_playground import SkillPlaygroundApplication


def _client(tmp_path):
    return TestClient(create_app(database_path=tmp_path / "studio.db"))


def _generated(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/generate",
        json={
            "brief": "Design a support character.",
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
            "request_id": "saved_character_test",
        },
    )
    assert response.status_code == 200
    return response.json()


def _save_payload(generated: dict[str, object], *, associations=None) -> dict[str, object]:
    return {
        "schema_version": "web-saved-character-save/0.1",
        "request": generated["request"],
        "draft": generated["draft"],
        "plan": generated["plan"],
        "associations": associations or [],
    }


def test_saved_character_list_is_empty_then_create_open_and_history_is_read_only(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/saved-characters").json()["characters"] == []

    generated = _generated(client)
    saved_response = client.post("/api/saved-characters", json=_save_payload(generated))
    assert saved_response.status_code == 201
    saved = saved_response.json()["saved"]
    assert saved["revision"]["kind"] == "GENERATED"
    assert saved["current_kit_assignment_id"] is None
    assert saved["history"] == []

    character_id = saved["character_id"]
    opened = client.get(f"/api/saved-characters/{character_id}")
    assert opened.status_code == 200
    assert opened.json()["current_revision_id"] == saved["current_revision_id"]
    assert opened.json()["derived"]["structural_validation"] is None
    assert client.get("/api/saved-characters").json()["total"] == 1


def test_saved_character_edit_duplicate_and_revision_conflict(tmp_path):
    client = _client(tmp_path)
    generated = _generated(client)
    saved = client.post("/api/saved-characters", json=_save_payload(generated)).json()["saved"]
    payload = _save_payload(generated)
    payload["expected_current_revision_id"] = saved["current_revision_id"]
    payload["draft"] = {**payload["draft"], "name": "Edited support character"}

    edited = client.put(f"/api/saved-characters/{saved['character_id']}", json=payload)
    assert edited.status_code == 200
    edited_saved = edited.json()["saved"]
    assert edited_saved["character_id"] == saved["character_id"]
    assert edited_saved["revision"]["kind"] == "EDITED"
    assert edited_saved["revision"]["parent_revision_id"] == saved["current_revision_id"]

    duplicate_payload = {
        **payload,
        "expected_current_revision_id": edited_saved["current_revision_id"],
    }
    duplicate = client.put(f"/api/saved-characters/{saved['character_id']}", json=duplicate_payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["saved"]["current_revision_id"] == edited_saved["current_revision_id"]

    conflict_payload = {**duplicate_payload, "expected_current_revision_id": "stale-revision"}
    conflict = client.put(f"/api/saved-characters/{saved['character_id']}", json=conflict_payload)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SAVED_CHARACTER_CONFLICT"


def test_missing_and_corrupt_saved_character_fail_closed(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/saved-characters/not-found").status_code == 404
    generated = _generated(client)
    saved = client.post("/api/saved-characters", json=_save_payload(generated)).json()["saved"]
    with sqlite3.connect(tmp_path / "studio.db") as connection:
        connection.execute(
            "UPDATE character_revisions SET character_payload_json = ? WHERE revision_id = ?",
            ('{"name":"corrupt"}', saved["current_revision_id"]),
        )
    response = client.get(f"/api/saved-characters/{saved['character_id']}")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PERSISTED_CHARACTER_INTEGRITY_ERROR"


def test_saved_character_round_trip_preserves_skill_identity_and_kit(tmp_path):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "hybrid_final_coverage_v2_goldens.json").read_text(
            encoding="utf-8"
        )
    )["character_alignment_support_v1"]
    skills = SkillPlaygroundApplication(provider_factory=lambda _model: FakeProvider(fixture))
    client = TestClient(
        create_app(skill_playground_service=skills, database_path=tmp_path / "studio.db")
    )
    generated = _generated(client)
    skill = client.post(
        "/api/characters/skill-design",
        json={
            "character": {
                "request": generated["request"],
                "draft": generated["draft"],
                "plan": generated["plan"],
            },
            "skill": {
                "family": "support",
                "mode": "active",
                "brief": "Protect allies",
                "constraints": [],
            },
        },
    ).json()
    association = {
        "association_id": f"session-skill:primary:{skill['artifact_digest']}",
        "artifact": skill["artifact"],
        "binding": skill["binding"],
        "artifact_compatibility": skill["artifact_compatibility"],
        "slot": "primary",
        "order": 0,
        "family": "support",
        "mode": "active",
        "display_summary": "Protect allies",
    }
    saved = client.post(
        "/api/saved-characters",
        json=_save_payload(generated, associations=[association]),
    ).json()["saved"]
    opened = client.get(f"/api/saved-characters/{saved['character_id']}").json()
    assert opened["associations"][0]["association_id"] == saved["associations"][0]["association_id"]
    assert opened["associations"][0]["artifact"] == association["artifact"]
    assert opened["kit"]["kit_digest"] == saved["kit"]["kit_digest"]
    assert opened["derived"]["freshness_by_association_id"] == {
        saved["associations"][0]["association_id"]: "current"
    }
    update_payload = _save_payload(generated, associations=[association])
    update_payload["expected_current_revision_id"] = saved["current_revision_id"]
    update_payload["expected_current_kit_assignment_id"] = "stale-kit-assignment"
    conflict = client.put(f"/api/saved-characters/{saved['character_id']}", json=update_payload)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["resource"] == "Kit assignment"

    stale_payload = _save_payload(generated, associations=[association])
    stale_payload["expected_current_revision_id"] = saved["current_revision_id"]
    stale_payload["expected_current_kit_assignment_id"] = saved["current_kit_assignment_id"]
    stale_payload["draft"] = {
        **stale_payload["draft"],
        "ability_concept": f"{stale_payload['draft']['ability_concept']} changed",
    }
    stale = client.put(f"/api/saved-characters/{saved['character_id']}", json=stale_payload)
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["resource"] == "binding freshness"
    assert (
        client.get(f"/api/saved-characters/{saved['character_id']}").json()["current_revision_id"]
        == saved["current_revision_id"]
    )
