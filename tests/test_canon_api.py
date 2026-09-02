from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import create_app


def test_canon_entity_list_exposes_real_public_inventory_and_dynamic_types() -> None:
    response = TestClient(create_app()).get("/api/canon/entities")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-canon-entity-list/0.1"
    assert body["total"] == 30
    assert body["entity_types"] == [
        "faction",
        "lore",
        "character",
        "project",
        "case",
        "incident",
        "story",
    ]
    assert {item["entity_type"] for item in body["entities"]} == set(body["entity_types"])
    faction = next(item for item in body["entities"] if item["entity_id"] == "faction_005")
    assert faction["name"] == "临洲市公共安全联席体系"
    assert faction["relation_count"] == 5
    assert "knowledge_boundary" not in faction


def test_canon_search_and_type_filter_use_backend_entity_type_metadata() -> None:
    client = TestClient(create_app())

    search = client.get("/api/canon/entities", params={"q": "临洲市公共安全联席体系"})
    assert [item["entity_id"] for item in search.json()["entities"]] == ["faction_005"]

    by_id = client.get("/api/canon/entities", params={"q": "faction_005"})
    assert [item["entity_id"] for item in by_id.json()["entities"]] == ["faction_005"]

    lore = client.get("/api/canon/entities", params={"type": "lore"})
    assert lore.json()["total"] == 13
    assert all(item["entity_type"] == "lore" for item in lore.json()["entities"])


def test_faction_detail_is_typed_public_projection_with_directional_relationships() -> None:
    response = TestClient(create_app()).get("/api/canon/entities/faction_005")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "faction"
    assert body["name"] == "临洲市公共安全联席体系"
    assert body["sections"]["faction"]["core_function"]["description"]
    assert body["sections"]["faction"]["member_profile"]["typical_roles"]
    assert "internal_structure" not in body["sections"]["faction"]
    relationship = next(
        item for item in body["relationships"] if item["target_entity_id"] == "faction_001"
    )
    assert relationship["direction"] == "outgoing"
    assert relationship["target_entity_type"] == "faction"
    assert relationship["target_name"] == "临洲市协理人联合会"
    assert relationship["available"] is True
    assert "knowledge_boundary" not in response.text
    assert "secret_information" not in response.text
    assert "D:\\game-ai-agent" not in response.text


def test_public_lore_detail_is_available_but_restricted_lore_is_not_disclosed() -> None:
    client = TestClient(create_app())

    public = client.get("/api/canon/entities/lore_023")
    assert public.status_code == 200
    assert public.json()["sections"]["lore"]["title"] == "临洲公共安全联席体系的协作范围"
    assert public.json()["sections"]["lore"]["statement"]

    restricted = client.get("/api/canon/entities/lore_011")
    assert restricted.status_code == 404
    assert restricted.json()["error"]["code"] == "CANON_ENTITY_NOT_FOUND"
    assert "商业能力模型历史数据的复核" not in restricted.text
    assert "restricted" not in restricted.text


def test_canon_detail_relationship_target_can_be_navigated_by_stable_id() -> None:
    client = TestClient(create_app())
    detail = client.get("/api/canon/entities/incident_nanzhan_postshow_route_conflict_001")

    assert detail.status_code == 200
    target = next(
        item for item in detail.json()["relationships"]
        if item["target_entity_id"] == "case_nanzhan_postshow_coordination_001"
    )
    assert target["target_entity_type"] == "case"
    assert target["available"] is True
    assert client.get(f"/api/canon/entities/{target['target_entity_id']}").status_code == 200


def test_canon_character_and_story_details_keep_families_distinct() -> None:
    client = TestClient(create_app())

    character = client.get("/api/canon/entities/char_launch_007")
    assert character.status_code == 200
    assert character.json()["entity_type"] == "character"
    assert character.json()["sections"]["character"]["display_name"] == "纪衡"

    story = client.get("/api/canon/entities/story_after_the_show_001")
    assert story.status_code == 200
    assert story.json()["entity_type"] == "story"
    assert story.json()["sections"]["story"]["title"] == "散场之后"


def test_unknown_canon_entity_returns_safe_404_without_internal_details() -> None:
    response = TestClient(create_app()).get("/api/canon/entities/not_real")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CANON_ENTITY_NOT_FOUND"
    assert "not_real" not in response.text
    assert "Traceback" not in response.text
