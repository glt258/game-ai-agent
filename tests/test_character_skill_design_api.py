from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from agents.character_generation import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
)
from character_intelligence.character_kit import (
    CHARACTER_KIT_CONTRACT_VERSION,
    KIT_PLACEMENT_SCHEMA_VERSION,
    compute_character_kit_digest,
)
from character_intelligence.character_skill_projection import build_character_skill_design_context
from character_intelligence.hybrid_ir.runner import FakeProvider
from combat_semantics import CombatRoleProfile
from web.app import create_app
from web.services.skill_playground import SkillPlaygroundApplication

ROOT = Path(__file__).resolve().parents[1]


def _fixture(case_id: str) -> dict[str, object]:
    filename = (
        "hybrid_final_coverage_v2_goldens.json"
        if case_id in {
            "generalization_sub_dps_v1",
            "generalization_defense_v1",
            "generalization_basic_passive_v1",
            "character_alignment_support_v1",
            "character_alignment_main_dps_v1",
            "character_alignment_control_v1",
        }
        else "hybrid_multi_case_generalization_goldens.json"
    )
    values = json.loads((ROOT / "tests" / "fixtures" / filename).read_text(encoding="utf-8"))
    return values[case_id]


def _character_payload(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/characters/generate",
        json={
            "brief": "设计一个中文辅助角色，保留公开世界观约束。",
            "request_id": "character_skill_design_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    return {"request": body["request"], "draft": body["draft"], "plan": body["plan"]}


def test_projection_fingerprint_uses_only_relevant_character_fields():
    request = CharacterDesignRequest(
        "设计一个辅助角色。",
        hard_constraints=("不新增组织",),
        forbidden_elements=("数值膨胀",),
        desired_connections=("保护队友",),
    )
    result = CharacterGenerationAgent(DeterministicCharacterGenerationModel()).generate(request)
    context = build_character_skill_design_context(request, result.draft, result.design_plan)

    assert context.ability_concept == result.draft.ability_concept
    assert context.combat_role_profile == result.draft.combat_role_profile
    assert context.skill_relevant_hard_constraints == ("不新增组织",)
    assert "background" not in context.to_projection_mapping()
    assert context.to_projection_mapping()["character_name"] == result.draft.name

    assert build_character_skill_design_context(
        request,
        replace(result.draft, age=(result.draft.age or 0) + 1, name=result.draft.name + "x"),
        result.design_plan,
    ).source_context_fingerprint != context.source_context_fingerprint
    assert build_character_skill_design_context(
        request,
        replace(result.draft, ability_concept=result.draft.ability_concept + "，改为控制。"),
        result.design_plan,
    ).source_context_fingerprint != context.source_context_fingerprint
    assert build_character_skill_design_context(
        request,
        replace(result.draft, combat_role_profile=CombatRoleProfile(primary_role="control")),
        result.design_plan,
    ).source_context_fingerprint != context.source_context_fingerprint


def test_explicit_combat_role_profile_survives_intent_layer_generation():
    client = TestClient(create_app())

    response = client.post(
        "/api/characters/generate",
        json={
            "brief": "设计一名辅助控制角色。",
            "request_id": "explicit_role_profile_test",
            "combat_role_profile": {
                "primary_role": "support",
                "secondary_roles": ["control"],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["draft"]["combat_role_profile"] == {
        "primary_role": "support",
        "secondary_roles": ["control"],
    }


def test_character_skill_context_is_backend_owned_and_provider_free():
    calls: list[str] = []

    def provider_factory(model: str):
        calls.append(model)
        return FakeProvider(_fixture("generalization_sub_dps_v1"))

    service = SkillPlaygroundApplication(provider_factory=provider_factory)
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)

    response = client.post("/api/characters/skill-context", json=character)

    assert response.status_code == 200
    body = response.json()
    assert len(body["source_context_fingerprint"]) == 64
    assert body["character_context_summary"]["ability_concept"] == character["draft"]["ability_concept"]
    assert calls == []

    irrelevant = copy.deepcopy(character)
    irrelevant["draft"]["age"] = 99
    irrelevant["draft"]["name"] = "名字改动"
    assert client.post("/api/characters/skill-context", json=irrelevant).json()["source_context_fingerprint"] != body["source_context_fingerprint"]

    relevant = copy.deepcopy(character)
    relevant["draft"]["ability_concept"] += "，增加一个明确的控制效果。"
    assert client.post("/api/characters/skill-context", json=relevant).json()["source_context_fingerprint"] != body["source_context_fingerprint"]


def test_character_skill_meta_exposes_ordered_backend_slot_contract():
    client = TestClient(create_app())

    response = client.get("/api/characters/skill-meta")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "web-character-skill-meta/0.1",
        "slots": [
            {
                "id": "primary",
                "order": 0,
                "label": "Primary",
                "description": "Primary Character Skill association.",
                "max_items": 1,
            },
            {
                "id": "secondary",
                "order": 1,
                "label": "Secondary",
                "description": "Secondary Character Skill association.",
                "max_items": 1,
            },
            {
                "id": "passive",
                "order": 2,
                "label": "Passive",
                "description": "Passive Character Skill association.",
                "max_items": None,
            },
            {
                "id": "utility",
                "order": 3,
                "label": "Utility",
                "description": "Utility Character Skill association.",
                "max_items": None,
            },
        ],
    }


def test_character_skill_design_reuses_skill_pipeline_and_preserves_utf8():
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_support_v1")),
    )
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)
    payload = {
        "character": character,
        "skill": {
            "family": "support",
            "mode": "active",
            "brief": "为顾澄设计一个中文控制技能，保留辅助定位。",
            "constraints": ["不新增资源"],
            "language": "zh-CN",
            "preset_id": "character_alignment_support_v1",
        },
    }

    response = client.post("/api/characters/skill-design", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-character-skill-design/0.1"
    assert body["status"] == "completed"
    assert body["evaluation"]["outcome"] == "PASS"
    assert body["alignment"]["status"] == "PASS"
    assert body["alignment"]["coverage"] in {"primary", "secondary"}
    assert body["alignment"]["artifact_digest"] == body["artifact_digest"]
    assert body["skill_input"]["brief"] == payload["skill"]["brief"]
    assert body["freshness"] == "current"
    assert body["artifact_digest"]
    assert body["semantic_ir"] is not None
    assert body["skillkit"] is not None
    assert "raw_response" not in body


def test_character_skill_design_transports_canonical_artifact_and_binding_to_kit_evaluation():
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_support_v1")),
    )
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)
    design = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "support",
                "mode": "active",
                "brief": "为顾澄设计一个可追溯的辅助技能。",
                "constraints": [],
                "language": "zh-CN",
                "preset_id": "character_alignment_support_v1",
            },
        },
    )

    assert design.status_code == 200
    designed = design.json()
    assert designed["artifact"]["identity"]["artifact_digest"] == designed["artifact_digest"]
    assert designed["binding"]["artifact_digest"] == designed["artifact_digest"]
    assert designed["binding"]["alignment"]["artifact_digest"] == designed["artifact_digest"]

    role_evaluation = client.post(
        "/api/characters/character-kit/evaluate",
        json={
            "schema_version": "web-character-kit-role-coverage/0.1",
            "kit": {
                "contract_version": "character-kit/0.1.0",
                "placement_schema_version": "character-kit-placement/0.1.0",
                "associations": [
                    {
                        "association_id": f"session-skill:primary:{designed['artifact_digest']}",
                        "artifact": designed["artifact"],
                        "binding": designed["binding"],
                        "slot": "primary",
                        "order": 0,
                        "family": designed["skill_input"]["family"],
                        "mode": designed["skill_input"]["mode"],
                        "display_summary": "canonical transport",
                    }
                ],
            },
            "combat_role_profile": designed["character_context_summary"]["combat_role_profile"],
        },
    )

    assert role_evaluation.status_code == 200
    assert role_evaluation.json()["structural_validation"]["status"] == "PASS"


def test_valid_main_dps_artifact_reaches_role_coverage_fail_without_attach_guard_bypass():
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_main_dps_v1")),
    )
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)
    design = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "main_dps",
                "mode": "active",
                "brief": "为顾澄设计一个有效但不匹配辅助身份的输出技能。",
                "constraints": [],
                "language": "zh-CN",
                "preset_id": "character_alignment_main_dps_v1",
            },
        },
    )

    assert design.status_code == 200
    designed = design.json()
    assert designed["evaluation"]["outcome"] == "PASS"
    assert designed["alignment"]["status"] == "FAIL"
    role_evaluation = client.post(
        "/api/characters/character-kit/evaluate",
        json={
            "schema_version": "web-character-kit-role-coverage/0.1",
            "kit": {
                "contract_version": "character-kit/0.1.0",
                "placement_schema_version": "character-kit-placement/0.1.0",
                "associations": [{
                    "association_id": f"session-skill:primary:{designed['artifact_digest']}",
                    "artifact": designed["artifact"],
                    "binding": designed["binding"],
                    "slot": "primary",
                    "order": 0,
                    "family": "main_dps",
                    "mode": "active",
                    "display_summary": "valid wrong-role artifact",
                }],
            },
            "combat_role_profile": {
                "primary_role": "support",
                "secondary_roles": ["control"],
            },
        },
    )

    assert role_evaluation.status_code == 200
    assert role_evaluation.json()["structural_validation"]["status"] == "PASS"
    assert role_evaluation.json()["role_coverage"]["status"] == "FAIL"


def test_character_kit_evaluation_rejects_incomplete_or_tampered_artifact_transport():
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_support_v1")),
    )
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)
    designed = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "support",
                "mode": "active",
                "brief": "为顾澄设计一个可追溯的辅助技能。",
                "constraints": [],
                "language": "zh-CN",
                "preset_id": "character_alignment_support_v1",
            },
        },
    ).json()

    def request_for(association: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "web-character-kit-role-coverage/0.1",
            "kit": {
                "contract_version": "character-kit/0.1.0",
                "placement_schema_version": "character-kit-placement/0.1.0",
                "associations": [association],
            },
            "combat_role_profile": designed["character_context_summary"]["combat_role_profile"],
        }

    association = {
        "association_id": f"session-skill:primary:{designed['artifact_digest']}",
        "artifact": designed["artifact"],
        "binding": designed["binding"],
        "slot": "primary",
        "order": 0,
        "family": designed["skill_input"]["family"],
        "mode": designed["skill_input"]["mode"],
        "display_summary": "canonical transport",
    }
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(association)).status_code == 200

    missing_artifact = copy.deepcopy(association)
    missing_artifact.pop("artifact")
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(missing_artifact)).status_code == 422

    missing_binding = copy.deepcopy(association)
    missing_binding.pop("binding")
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(missing_binding)).status_code == 422

    artifact_digest_mismatch = copy.deepcopy(association)
    artifact_digest_mismatch["artifact"]["identity"]["artifact_digest"] = "f" * 64
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(artifact_digest_mismatch)).status_code == 422

    binding_digest_mismatch = copy.deepcopy(association)
    binding_digest_mismatch["binding"]["artifact_digest"] = "e" * 64
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(binding_digest_mismatch)).status_code == 422

    unsupported_contract = copy.deepcopy(association)
    unsupported_contract["artifact"]["artifact_contract_version"] = "skill-design-artifact/9.9.9"
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(unsupported_contract)).status_code == 422

    tampered_candidate = copy.deepcopy(association)
    tampered_candidate["artifact"]["canonical_artifact"]["entries"][0]["operation"] = "tampered"
    assert client.post("/api/characters/character-kit/evaluate", json=request_for(tampered_candidate)).status_code == 422


def test_character_kit_validation_endpoint_returns_stable_empty_pass():
    client = TestClient(create_app())
    response = client.post(
        "/api/characters/skill-kit/validate",
        json={
            "schema_version": "web-character-kit-validation/0.1",
            "kit": {
                "contract_version": CHARACTER_KIT_CONTRACT_VERSION,
                "placement_schema_version": KIT_PLACEMENT_SCHEMA_VERSION,
                "associations": [],
                "kit_digest": compute_character_kit_digest(()),
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == CHARACTER_KIT_CONTRACT_VERSION
    assert body["associations"] == []
    assert body["structural_validation"] == {"status": "PASS", "blocking": False, "findings": []}


def test_character_skill_design_business_failure_is_http_200_and_keeps_artifact():
    invalid = _fixture("character_alignment_support_v1")
    invalid["role_path"]["effect"]["actor"] = "ally"
    service = SkillPlaygroundApplication(provider_factory=lambda _model: FakeProvider(invalid))
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)

    response = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "sub_dps",
                "mode": "active",
                "brief": "中文失败技能。",
                "constraints": [],
                "language": "zh-CN",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["evaluation"]["outcome"] == "FAIL"
    assert body["alignment"]["status"] == "NOT_EVALUATED"
    assert body["skillkit"] is not None
    assert body["artifact_digest"]


def test_valid_but_mismatched_skill_is_alignment_failure_and_not_attachable():
    service = SkillPlaygroundApplication(
        provider_factory=lambda _model: FakeProvider(_fixture("character_alignment_main_dps_v1")),
    )
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)
    character["draft"]["combat_role_profile"] = {
        "primary_role": "support",
        "secondary_roles": ["control"],
    }

    response = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "main_dps",
                "mode": "active",
                "brief": "中文纯输出技能。",
                "constraints": [],
                "language": "zh-CN",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["outcome"] == "PASS"
    assert body["alignment"]["status"] == "FAIL"
    assert body["alignment"]["blocking"] is True
    assert body["alignment"]["findings"][0]["code"] == "SKILL_ROLE_CONTRADICTS_CHARACTER_IDENTITY"


def test_character_skill_design_runtime_failure_is_safe_error():
    service = SkillPlaygroundApplication(provider_factory=lambda _model: (_ for _ in ()).throw(RuntimeError("secret token")))
    client = TestClient(create_app(skill_playground_service=service))
    character = _character_payload(client)

    response = client.post(
        "/api/characters/skill-design",
        json={
            "character": character,
            "skill": {
                "family": "support",
                "mode": "active",
                "brief": "运行时错误测试。",
                "constraints": [],
                "language": "zh-CN",
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHARACTER_SKILL_DESIGN_UNAVAILABLE"
    assert "secret token" not in response.text
