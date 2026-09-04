from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

import web.services.skill_playground as skill_playground_module
from character_intelligence.hybrid_ir.runner import FakeProvider
from web.app import create_app
from web.services.skill_playground import SkillPlaygroundApplication

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _fixture(case_id: str) -> dict:
    filename = (
        "hybrid_final_coverage_v2_goldens.json"
        if case_id.startswith("generalization_") and case_id in {
            "generalization_sub_dps_v1",
            "generalization_defense_v1",
            "generalization_basic_passive_v1",
        }
        else "hybrid_multi_case_generalization_goldens.json"
    )
    values = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return values[case_id]


def _client(response: object) -> TestClient:
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(response),
    )
    return TestClient(create_app(skill_playground_service=service))


def test_meta_exposes_authoritative_seven_families_and_modes():
    response = TestClient(create_app()).get("/api/skills/playground/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-skill-playground-meta/0.1"
    assert {item["id"] for item in body["families"]} == {
        "main_dps",
        "sub_dps",
        "support",
        "healer",
        "control",
        "defense",
        "basic_passive",
    }
    assert set(body["modes"]) == {"active", "passive", "reaction"}


def test_offline_presets_cover_the_three_v2_families_with_full_pipeline_passes():
    client = TestClient(create_app())
    cases = (
        ("sub_dps", "active", "generalization_sub_dps_v1"),
        ("defense", "reaction", "generalization_defense_v1"),
        ("basic_passive", "passive", "generalization_basic_passive_v1"),
    )

    for family, mode, preset_id in cases:
        response = client.post(
            "/api/skills/playground/run",
            json={
                "family": family,
                "mode": mode,
                "brief": "中文离线技能验收。",
                "constraints": [],
                "preset_id": preset_id,
                "language": "zh-CN",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["evaluation"]["outcome"] == "PASS"
        assert all(step["status"] == "passed" for step in body["pipeline"])


def test_default_repo_root_resolves_from_web_working_directory(monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT / "web")

    service = SkillPlaygroundApplication()

    assert service.repo_root == PROJECT_ROOT


def test_offline_fixture_provider_uses_application_repo_root(tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    shutil.copy2(FIXTURES / "hybrid_final_coverage_v2_goldens.json", fixture_dir)

    request = skill_playground_module.SkillPlaygroundRequestDTO(
        family="support",
        mode="active",
        brief="保护队友。",
        preset_id="character_support_skill_v1",
    )
    provider = SkillPlaygroundApplication(repo_root=tmp_path).provider_for(request)

    assert isinstance(provider, FakeProvider)


def test_run_returns_real_pipeline_views_and_canonical_skillkit():
    client = _client(_fixture("generalization_sub_dps_v1"))

    response = client.post(
        "/api/skills/playground/run",
        json={
            "family": "sub_dps",
            "mode": "active",
            "brief": "设计一名主输出技能。",
            "constraints": ["只能攻击敌方"],
            "language": "zh-CN",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-skill-playground/0.1"
    assert body["status"] == "completed"
    assert body["evaluation"]["outcome"] == "PASS"
    assert body["semantic_ir"]["ability_name"] == "Echo Volley"
    assert body["skillkit"]["schema_version"] == "skill-kit-candidate/0.1.1"
    assert [item["id"] for item in body["pipeline"]] == [
        "provider",
        "json",
        "ir_parse",
        "ir_validation",
        "compiler",
        "canonical_parser",
        "reference_integrity",
        "evaluator",
    ]
    assert all(item["status"] == "passed" for item in body["pipeline"])
    assert body["input"]["brief"] == "设计一名主输出技能。"
    assert "raw_response" not in body


def test_evaluator_failure_is_business_result_and_retains_skillkit():
    payload = _fixture("generalization_sub_dps_v1")
    payload["role_path"]["effect"]["actor"] = "ally"
    client = _client(payload)

    response = client.post(
        "/api/skills/playground/run",
        json={
            "family": "sub_dps",
            "mode": "active",
            "brief": "主输出技能，但故意制造评估失败。",
            "constraints": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["evaluation"]["outcome"] == "FAIL"
    assert body["skillkit"] is not None
    assert body["pipeline"][-1]["status"] == "failed"
    assert body["evaluation"]["findings"]


def test_unsupported_family_is_safe_request_error():
    response = TestClient(create_app()).post(
        "/api/skills/playground/run",
        json={"family": "unknown", "mode": "active", "brief": "x", "constraints": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert "Traceback" not in response.text


def test_provider_unavailable_is_runtime_error_not_business_failure():
    def unavailable(_model: str):
        raise RuntimeError("secret provider token D:/private/key")

    service = SkillPlaygroundApplication(provider_factory=unavailable)
    response = TestClient(create_app(skill_playground_service=service)).post(
        "/api/skills/playground/run",
        json={
            "family": "support",
            "mode": "active",
            "brief": "中文辅助技能：保护队友。",
            "constraints": [],
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SKILL_PLAYGROUND_UNAVAILABLE"
    assert "secret provider" not in response.text
    assert "private" not in response.text


def test_live_mode_is_explicit_and_backend_owned_when_credentials_are_missing(monkeypatch):
    monkeypatch.delenv("NPC_LLM_API_KEY", raising=False)
    response = TestClient(create_app()).post(
        "/api/skills/playground/run",
        json={
            "family": "support",
            "mode": "active",
            "brief": "设计一个实时辅助技能。",
            "constraints": [],
            "execution_mode": "live",
            "provider": "deepseek",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SKILL_PLAYGROUND_LIVE_CONFIGURATION_INVALID"
    assert "NPC_LLM_API_KEY" not in response.text


def test_injected_live_mode_keeps_provider_call_inside_backend_service():
    client = _client(_fixture("generalization_support_alternate_v1"))
    response = client.post(
        "/api/skills/playground/run",
        json={
            "family": "support",
            "mode": "active",
            "brief": "设计一个实时辅助技能。",
            "constraints": [],
            "execution_mode": "live",
            "provider": "deepseek",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 200
    assert response.json()["provider"]["mode"] == "live"


def test_chinese_input_is_preserved_in_web_dto():
    client = _client(_fixture("generalization_support_alternate_v1"))
    brief = "设计一个‘临洲’辅助技能，保护队友并保留中文标点。"

    response = client.post(
        "/api/skills/playground/run",
        json={
            "family": "support",
            "mode": "active",
            "brief": brief,
            "constraints": ["不新增组织"],
            "language": "zh-CN",
        },
    )

    assert response.status_code == 200
    assert response.json()["input"]["brief"] == brief
