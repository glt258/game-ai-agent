from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.canon_checker import CanonChecker
from agents.character_generation import (
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
)
from agents.character_repair import CharacterRepairAgent, DeterministicCharacterRepairModel
from agents.errors import AgentExecutionError
from web.app import create_app
from web.schemas.validation import CharacterValidationRequestDTO
from web.services.character_generation import CharacterGenerationApplication
from web.services.character_validation import CharacterValidationApplication

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "web"
CANON_FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _contract() -> dict:
    return json.loads((FIXTURES / "character_contract_v0_1.json").read_text(encoding="utf-8"))


def _canon_case(name: str) -> dict:
    return json.loads((CANON_FIXTURES / f"canon_checker_{name}.json").read_text(encoding="utf-8"))


def test_health_returns_stable_readiness_shape():
    client = TestClient(create_app())

    response = client.get("/api/system/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "game-ai-agent-web",
        "api_version": "v0.1",
        "character_generation_available": True,
    }


def test_generation_uses_real_offline_character_runtime_and_maps_studio_data():
    client = TestClient(create_app())

    response = client.post(
        "/api/characters/generate",
        json={
            "brief": "设计一个新的都市辅助角色。",
            "request_id": "web_test_001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    contract = _contract()["generate_success"]
    assert body["schema_version"] == contract["schema_version"]
    assert body["status"] == contract["status"]
    assert set(contract["required_top_level_fields"]) <= body.keys()
    assert body["draft"]["draft_id"] == "draft_web_test_001"
    assert body["draft"]["status"] == "draft"
    assert body["plan"] is not None
    assert body["combat"]["combat_role_profile"]["primary_role"] == "support"
    assert body["canon_basis"]
    assert set(contract["validator_ids"]) <= {item["name"] for item in body["validators"]}
    assert [step["id"] for step in body["pipeline"]] == contract["pipeline_ids"]
    assert all(step["status"] not in {"pending", "running"} for step in body["pipeline"])
    assert body["raw_data"]["draft"]["draft_id"] == body["draft"]["draft_id"]


def test_utf8_simplified_chinese_browser_payload_completes_generation():
    brief = (
        "设计一名临洲市公共安全联席体系所属的新角色。\n\n"
        "要求：\n"
        "- 女性\n"
        "- 25 岁左右\n"
        "- 性格冷静但并不冷漠\n"
        "- 战斗偏向辅助控制\n"
        "- 不允许新增组织\n"
        "- 与现有世界观保持一致"
    )
    client = TestClient(create_app())

    response = client.post(
        "/api/characters/generate",
        json={
            "brief": brief,
            "hard_constraints": [],
            "soft_preferences": [],
            "forbidden_elements": [],
            "desired_connections": [],
            "request_id": None,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["request"]["brief"] == brief
    assert body["draft"]["age"] == 25
    assert body["draft"]["age_range"] == "23-27"
    assert body["draft"]["gender"] == "女性"
    assert body["draft"]["faction_id"] == "faction_005"
    assert body["draft"]["combat_role_profile"]["primary_role"] == "support"


def test_utf8_chinese_punctuation_and_mixed_ascii_are_preserved_end_to_end():
    briefs = (
        "请设计一名负责‘现场协同’的辅助角色，代号 Alpha-7。",
        "设计一个新的都市辅助角色。English/ASCII mixed，保留括号（A-1）与破折号——。",
    )
    client = TestClient(create_app())

    for brief in briefs:
        response = client.post(
            "/api/characters/generate",
            json={
                "brief": brief,
                "hard_constraints": [],
                "soft_preferences": [],
                "forbidden_elements": [],
                "desired_connections": [],
                "request_id": None,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["request"]["brief"] == brief
        assert body["plan"]["parsed_intent"]["raw_request"] == brief
        assert body["draft"]["draft_id"].startswith("draft_web_request_")


def test_invalid_request_uses_safe_error_envelope():
    client = TestClient(create_app())

    response = client.post("/api/characters/generate", json={"brief": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert "brief" in response.text
    assert "Traceback" not in response.text


class _ExplodingModel:
    def generate(self, _prompt):
        raise AgentExecutionError(
            "secret-value D:\\game-ai-agent\\private.env Authorization: Bearer token"
        )


def test_runtime_failure_is_sanitized_without_raw_exception_text():
    service = CharacterGenerationApplication(
        generation_agent=CharacterGenerationAgent(_ExplodingModel()),
    )
    client = TestClient(create_app(service))

    response = client.post("/api/characters/generate", json={"brief": "任意角色"})

    assert response.status_code == 502
    text = response.text
    assert response.json()["error"]["code"] == "GENERATION_NOT_COMPLETED"
    assert response.json()["error"]["details"] == {
        "reason_code": "generation_execution_failed",
        "model_invocation_count": 0,
        "contract_recovery_status": "not_attempted",
    }
    assert "secret-value" not in text
    assert "D:\\game-ai-agent" not in text
    assert "Authorization" not in text
    assert "Traceback" not in text


def test_generation_failure_contract_fixture_is_stable():
    contract = _contract()["generate_failure"]
    service = CharacterGenerationApplication(
        generation_agent=CharacterGenerationAgent(_ExplodingModel()),
    )
    response = TestClient(create_app(service)).post(
        "/api/characters/generate",
        json={"brief": "任意角色"},
    )

    assert response.status_code == contract["http_status"]
    assert set(contract["error_fields"]) <= response.json()["error"].keys()


def test_generation_repair_success_contract_fixture_is_stable():
    generation_agent = CharacterGenerationAgent(
        DeterministicCharacterGenerationModel(scenario="canon_conflict")
    )
    checker = CanonChecker()
    service = CharacterGenerationApplication(
        generation_agent=generation_agent,
        repair_agent=CharacterRepairAgent(
            DeterministicCharacterRepairModel(),
            checker=checker,
        ),
        checker=checker,
    )
    response = TestClient(create_app(service)).post(
        "/api/characters/generate",
        json={"brief": "设计一个公共安全辅助角色。", "request_id": "web_repair_001"},
    )

    assert response.status_code == 200
    body = response.json()
    expected = _contract()["repair_success"]
    assert body["repair"]["repair_performed"] is expected["repair_performed"]
    assert body["repair"]["repair_succeeded"] is expected["repair_succeeded"]
    assert body["repair"]["status"] == expected["status"]


def test_validate_pass_contract_fixture_reuses_deterministic_checker_and_evaluator():
    case = _canon_case("good")
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={"request": case["request"], "draft": case["draft"]},
    )

    contract = _contract()["validate"]
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == contract["schema_version"]
    assert body["status"] in contract["status_values"]
    assert set(contract["required_top_level_fields"]) <= body.keys()
    assert [step["id"] for step in body["pipeline"]] == contract["pipeline_ids"]
    assert body["status"] == "passed"
    assert {item["name"] for item in body["validators"]} >= {
        "evaluation_runner",
        "canon_checker",
    }
    assert not any(field in body for field in contract["generation_only_fields"])


def _affiliation_validation_payload(
    *, draft_faction_id: str | None, correct_basis: bool = False
) -> dict:
    case = _canon_case("good")
    case["request"] = {
        "brief": "设计一个必须属于临洲市公共安全联席体系的女性辅助角色。",
        "hard_constraints": [],
        "soft_preferences": [],
        "forbidden_elements": [],
        "desired_connections": [],
        "request_id": "affiliation_web_test",
    }
    case["draft"]["faction_id"] = draft_faction_id
    if correct_basis:
        for entry in case["draft"]["canon_basis"]:
            if entry["source_id"] == "faction_002":
                entry["source_id"] = "faction_005"
        case["draft"]["occupation"] = "公共安全协作员"
        case["draft"]["social_role"] = "参与公共安全联席事项的现场协作员"
    return {"request": case["request"], "draft": case["draft"]}


@pytest.mark.parametrize(
    ("draft_faction_id", "correct_basis", "expected_canon_status"),
    [(None, False, "passed"), ("faction_002", False, "passed"), ("faction_005", True, "passed")],
)
def test_validate_explicit_affiliation_is_checked_separately_from_canon(
    draft_faction_id, correct_basis, expected_canon_status
):
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json=_affiliation_validation_payload(
            draft_faction_id=draft_faction_id,
            correct_basis=correct_basis,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    alignment = [item for item in body["validators"] if item["name"] == "request_alignment"]
    assert body["canon"]["status"] == expected_canon_status
    if draft_faction_id == "faction_005":
        assert body["status"] == "passed"
        assert alignment == []
    else:
        assert body["status"] == "failed"
        assert alignment == [
            {
                "name": "request_alignment",
                "status": "failed",
                "code": "AFFILIATION_CONSTRAINT_UNSATISFIED",
                "severity": "ERROR",
                "blocking": True,
                "field_path": "faction_id",
                "message": "Generated draft does not satisfy the requested affiliation.",
                "evidence_ids": [],
            }
        ]


def test_validate_rejects_campus_identity_even_when_affiliation_id_matches():
    payload = _affiliation_validation_payload(
        draft_faction_id="faction_005",
        correct_basis=True,
    )
    payload["draft"].update(
        {
            "occupation": "临洲大学学生助理",
            "social_role": "校园活动与社区安全志愿协调者",
            "background": "她在校园与社区活动中逐渐形成了谨慎处理复杂关系的习惯。",
        }
    )

    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["canon"]["status"] == "passed"
    assert body["status"] == "failed"
    assert any(
        item["name"] == "identity_coherence"
        and item["code"] == "IDENTITY_AFFILIATION_INCONSISTENT"
        and item["field_path"] == "occupation"
        and item["blocking"] is True
        for item in body["validators"]
    )


def test_validate_fail_contract_returns_validation_status_not_http_500():
    case = _canon_case("bad")
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={"request": case["request"], "draft": case["draft"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["canon"]["status"] == "failed"
    assert any(
        item["name"] == "canon_checker" and item["status"] == "failed"
        for item in body["validators"]
    )


def test_validate_does_not_call_generation_provider_or_repair():
    service = CharacterGenerationApplication(
        generation_agent=CharacterGenerationAgent(_ExplodingModel()),
    )
    case = _canon_case("good")

    response = TestClient(create_app(service)).post(
        "/api/characters/validate",
        json={"request": case["request"], "draft": case["draft"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "passed"


def test_validate_malformed_request_uses_safe_error_envelope():
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={"request": {"brief": "编辑角色"}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert "Traceback" not in response.text


def test_validate_domain_contract_failure_is_not_a_runtime_error():
    case = _canon_case("good")
    case["draft"]["status"] = "published"
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={"request": case["request"], "draft": case["draft"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DRAFT_CONTRACT_INVALID"
    assert "published" not in response.text


class _ExplodingChecker:
    def check(self, *_args, **_kwargs):
        raise RuntimeError("secret D:\\private Authorization: Bearer token")


def test_validate_runtime_failure_is_sanitized():
    case = _canon_case("good")
    service = CharacterValidationApplication(checker=_ExplodingChecker())
    payload = CharacterValidationRequestDTO(request=case["request"], draft=case["draft"])

    response = TestClient(create_app(validation_service=service)).post(
        "/api/characters/validate",
        json=payload.model_dump(mode="json"),
    )

    assert response.status_code == 500
    text = response.text
    assert response.json()["error"]["code"] == "VALIDATION_RUNTIME_ERROR"
    assert "secret" not in text
    assert "D:\\private" not in text
    assert "Authorization" not in text
    assert "Traceback" not in text


def test_validate_preserves_user_text_but_does_not_expose_server_diagnostics():
    case = _canon_case("good")
    case["draft"]["background"] = "用户创作文本 D:\\fake Authorization: abc"
    response = TestClient(create_app()).post(
        "/api/characters/validate",
        json={"request": case["request"], "draft": case["draft"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"passed", "failed"}
    assert "Traceback" not in response.text


def test_openapi_freezes_web_routes_and_public_error_models():
    schema = create_app().openapi()

    assert sorted(schema["paths"]) == [
        "/api/canon/entities",
        "/api/canon/entities/{entity_id}",
        "/api/characters/character-kit/evaluate",
        "/api/characters/generate",
        "/api/characters/skill-context",
        "/api/characters/skill-design",
        "/api/characters/skill-design/jobs",
        "/api/characters/skill-design/jobs/{job_id}",
        "/api/characters/skill-kit/validate",
        "/api/characters/skill-meta",
        "/api/characters/validate",
        "/api/reference-characters",
        "/api/reference-characters/{reference_id}",
        "/api/saved-characters",
        "/api/saved-characters/{character_id}",
        "/api/skills/playground/jobs",
        "/api/skills/playground/jobs/{job_id}",
        "/api/skills/playground/meta",
        "/api/skills/playground/run",
        "/api/system/health",
    ]
    models = schema["components"]["schemas"]
    assert {
        "CharacterValidationRequestDTO",
        "CharacterValidationResponseDTO",
        "CharacterSkillContextRequestDTO",
        "CharacterSkillContextResponseDTO",
        "CharacterSkillAlignmentFindingDTO",
        "CharacterSkillAlignmentResultDTO",
        "CharacterSkillEvidenceDTO",
        "CharacterSkillDesignRequestDTO",
        "CharacterSkillDesignResponseDTO",
        "LiveJobAcceptedDTO",
        "LiveJobStatusDTO",
        "CharacterKitRoleCoverageRequestDTO",
        "CharacterKitRoleCoverageResponseDTO",
        "CanonEntityDetailDTO",
        "CanonEntityListDTO",
        "ErrorResponseDTO",
        "ReferenceCharacterDetailDTO",
        "ReferenceCharacterListDTO",
        "SkillPlaygroundMetaDTO",
        "SkillPlaygroundRequestDTO",
        "SkillPlaygroundResponseDTO",
    } <= models.keys()
