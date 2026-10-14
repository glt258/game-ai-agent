from __future__ import annotations

from collections.abc import Mapping

import pytest

from agents.evaluation.models import EvaluationOutcome
from web.errors import WebApplicationError
from web.schemas.characters import CharacterGenerationRequestDTO
from web.services.character_generation_v2_production import (
    CharacterGenerationRoute,
    OfflineCharacterGenerationV2Model,
    build_character_generation_v2_application,
)


class _InvalidConstraintOutputModel(OfflineCharacterGenerationV2Model):
    def __init__(self, field_name: str, value: object) -> None:
        self.field_name = field_name
        self.value = value

    def _draft_output(self, prompt) -> Mapping[str, object]:
        output = dict(super()._draft_output(prompt))
        if prompt.response_format == "character_draft":
            output[self.field_name] = self.value
        return output


class _ForbiddenPatternOutputModel(OfflineCharacterGenerationV2Model):
    def _draft_output(self, prompt) -> Mapping[str, object]:
        output = dict(super()._draft_output(prompt))
        if prompt.response_format == "character_draft":
            output["background"] = "她是秘密政府机构的特工。"
        return output


def test_offline_application_runs_one_complete_v2_production_workflow() -> None:
    application = build_character_generation_v2_application(generation_mode="offline")
    request = CharacterGenerationRequestDTO(
        brief="Create a female support character named Alice.",
        request_id="production_v2_test_001",
    )

    result = application.generate(request)

    assert result.route is CharacterGenerationRoute.CHARACTER_GENERATION_V2
    assert result.generator_result.status.value == "COMPLETED"
    assert result.authoring.final_draft.name == "Alice"
    assert result.authoring.final_draft.gender == "女性"
    assert result.naming_design is not None
    assert result.naming_design.owner.value == "USER_SPECIFIED"
    assert result.authoring.final_check.status.value == "pass"
    assert result.evaluation.outcome is EvaluationOutcome.PASS
    assert result.workflow_audit is not None
    assert result.workflow_audit.spec_id
    assert result.call_accounting is not None
    assert result.call_accounting.concept_search == 1
    assert result.call_accounting.selector == 1
    assert result.call_accounting.planner == 1
    assert result.call_accounting.generation == 1
    assert result.call_accounting.structural_recovery == 0
    assert result.call_accounting.canon_checks == 1
    assert result.call_accounting.repair == 0
    assert result.call_accounting.evaluation == 1


def test_v2_offline_workflow_repairs_forbidden_output_before_evaluation() -> None:
    model = _ForbiddenPatternOutputModel()
    application = build_character_generation_v2_application(
        model_factory=lambda **_kwargs: model,
        generation_mode="offline",
    )
    request = CharacterGenerationRequestDTO(
        brief="Create a female support character named Alice.",
        forbidden_elements=["秘密政府机构"],
        request_id="production_v2_repair_test_001",
    )

    result = application.generate(request)

    assert result.route is CharacterGenerationRoute.CHARACTER_GENERATION_V2
    assert result.generator_result.status.value == "COMPLETED"
    assert result.authoring.repair_result.repair_attempted is True
    assert result.authoring.repair_result.repair_succeeded is True
    assert result.authoring.final_status.value == "pass"
    assert result.authoring.final_check.status.value == "pass"
    assert result.authoring.final_draft.name == "Alice"
    assert result.authoring.final_draft.gender == "女性"
    assert "秘密政府机构" not in result.authoring.final_draft.background
    assert result.evaluation.outcome is EvaluationOutcome.PASS
    assert result.call_accounting.repair == 1
    assert result.call_accounting.evaluation == 1


def test_v2_web_live_job_routes_preserve_the_existing_async_contract() -> None:
    from fastapi.testclient import TestClient

    from web.app import create_app

    application = build_character_generation_v2_application(
        environment={},
        generation_mode="offline",
    )
    client = TestClient(create_app(generation_service=application))

    submission = client.post(
        "/api/characters/generate/jobs",
        json={"brief": "Create a character."},
    )
    status = client.get("/api/characters/generate/jobs/not-created")

    assert submission.status_code == 503
    assert submission.json()["error"]["code"] == "CHARACTER_LIVE_CONFIGURATION_INVALID"
    assert status.status_code == 404
    assert status.json()["error"]["code"] == "LIVE_JOB_NOT_FOUND"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (("age", 30), ("faction_id", "faction_003")),
)
def test_generator_fails_closed_when_output_breaks_frozen_user_constraints(
    field_name: str,
    invalid_value: object,
) -> None:
    model = _InvalidConstraintOutputModel(field_name, invalid_value)
    application = build_character_generation_v2_application(
        model_factory=lambda **_kwargs: model,
        generation_mode="offline",
    )
    request = CharacterGenerationRequestDTO(
        brief=(
            "设计一名25岁左右的女性辅助角色，所属临洲市公共安全联席体系。"
        ),
        request_id=f"constraint_{field_name}_001",
    )

    with pytest.raises(WebApplicationError) as captured:
        application.generate(request)

    assert captured.value.code == "CHARACTER_GENERATION_V2_FAILED"
    assert captured.value.details["reason_code"] == "HARD_REQUIREMENT_VIOLATION"
