from __future__ import annotations

from fastapi.testclient import TestClient
from test_character_skill_association import _association

from character_intelligence.character_kit import build_character_kit
from character_intelligence.character_kit_evaluation import (
    CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION,
    CharacterKitEvaluationContext,
)
from character_intelligence.character_skill_association import SkillSlot
from combat_semantics import CombatRoleProfile
from web.app import create_app


def test_role_coverage_endpoint_returns_separate_structure_and_semantic_status() -> None:
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    profile = CombatRoleProfile(primary_role="support")
    context = CharacterKitEvaluationContext(combat_role_profile=profile)
    client = TestClient(create_app())

    response = client.post(
        "/api/characters/character-kit/evaluate",
        json={
            "schema_version": "web-character-kit-role-coverage/0.1",
            "kit": kit.to_mapping(),
            "combat_role_profile": profile.to_dict(),
            "current_skill_context_fingerprint": kit.associations[0].source_context_fingerprint,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "web-character-kit-role-coverage/0.1"
    assert body["structural_validation"]["status"] == "PASS"
    assert body["role_coverage"]["status"] == "PASS"
    assert body["role_coverage"]["evaluator_version"] == CHARACTER_KIT_ROLE_COVERAGE_EVALUATOR_VERSION
    assert body["role_coverage"]["evaluation_context_fingerprint"] == context.context_fingerprint
    assert body["role_coverage"]["coverage"]["primary"]["supported"] is True
    assert body["role_coverage"]["coverage"]["primary"]["evidence"]
    assert body["role_coverage"]["report_digest"]


def test_role_coverage_endpoint_keeps_structural_failure_separate_from_not_evaluated() -> None:
    kit = build_character_kit((_association(SkillSlot.PRIMARY),))
    invalid = kit.to_mapping()
    invalid["kit_digest"] = "0" * 64
    client = TestClient(create_app())

    response = client.post(
        "/api/characters/character-kit/evaluate",
        json={
            "schema_version": "web-character-kit-role-coverage/0.1",
            "kit": invalid,
            "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["structural_validation"]["status"] == "FAIL"
    assert body["role_coverage"]["status"] == "NOT_EVALUATED"
