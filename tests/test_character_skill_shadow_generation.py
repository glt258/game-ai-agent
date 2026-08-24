from __future__ import annotations

import copy
import json
from pathlib import Path

from agents.character_generation import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
)
from agents.models import ModelInvocationAudit, ModelTurn, SkillShadowConfig


def _candidate_payload() -> dict[str, object]:
    return {
        "schema_version": "skill-kit-candidate/0.1.1",
        "entries": [
            {
                "ability_id": "signal",
                "name": "Signal",
                "mode": "active",
                "protocols": [],
                "display_text": "A structured signal.",
            }
        ],
        "feedback_relations": [],
        "resources": [],
        "states": [],
        "summons": [],
        "role_evidence": [],
        "display_summary": "A concise structured summary.",
    }


def _repair_candidate_payload() -> dict[str, object]:
    fixture = json.loads(
        Path(
            "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json"
        ).read_text(encoding="utf-8")
    )
    return copy.deepcopy(next(item["candidate"] for item in fixture["cases"] if item["case_id"] == "case_02"))


class _ShadowModel:
    """A provider-neutral model double used only through CharacterGenerationAgent."""

    def __init__(self, shadow_turn: ModelTurn | None = None, shadow_error: Exception | None = None):
        self.legacy = DeterministicCharacterGenerationModel()
        self.prompts = []
        self.shadow_turn = shadow_turn
        self.shadow_error = shadow_error

    def generate(self, prompt):
        self.prompts.append(prompt)
        if prompt.response_format == "character_skill_kit":
            if self.shadow_error is not None:
                raise self.shadow_error
            assert self.shadow_turn is not None
            return self.shadow_turn
        return self.legacy.generate(prompt)


def _request() -> CharacterDesignRequest:
    return CharacterDesignRequest(
        "设计一个角色",
        request_id="shadow_request",
    )


def _enabled_model(**kwargs) -> _ShadowModel:
    return _ShadowModel(
        shadow_turn=ModelTurn(structured_output=kwargs.get("payload")),
        shadow_error=kwargs.get("error"),
    )


def test_skill_shadow_config_is_disabled_by_default():
    config = SkillShadowConfig()

    assert config.enabled is False


def test_disabled_shadow_has_exact_legacy_output_audit_and_call_parity():
    request = _request()
    first_model = _ShadowModel()
    second_model = _ShadowModel()

    first = CharacterGenerationAgent(first_model).generate(request)
    second = CharacterGenerationAgent(
        second_model,
        shadow_config=SkillShadowConfig(enabled=False),
    ).generate(request)

    assert first.skill_shadow is None
    assert second.skill_shadow is None
    assert first.draft == second.draft
    assert first.sources == second.sources
    assert first.audit == second.audit
    assert first.design_plan == second.design_plan
    assert len(first_model.prompts) == len(second_model.prompts)
    assert [prompt.response_format for prompt in first_model.prompts] == [
        prompt.response_format for prompt in second_model.prompts
    ]
    assert all(prompt.response_format != "character_skill_kit" for prompt in first_model.prompts)


def test_enabled_shadow_parses_and_structurally_validates_without_changing_draft():
    model = _enabled_model(payload=_candidate_payload())
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.draft_id == result.draft.draft_id
    assert shadow.response_compliant is True
    assert shadow.candidate is not None
    assert shadow.validation_report is not None
    assert shadow.validation_report.outcome == "PASS"
    assert shadow.failure_stage is None
    assert shadow.rendered_ability_concept == (
        "A concise structured summary. Signal: no protocols"
    )
    assert shadow.legacy_ability_concept == result.draft.ability_concept
    assert shadow.ability_concept_diff["matches"] is False
    assert len([prompt for prompt in model.prompts if prompt.response_format == "character_skill_kit"]) == 1
    assert all(prompt.available_tools == () for prompt in model.prompts if prompt.response_format == "character_skill_kit")


def test_shadow_provider_failure_is_contained_and_not_added_to_legacy_audit():
    model = _ShadowModel(shadow_error=RuntimeError("secret provider payload"))
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.failure_stage == "provider"
    assert shadow.error_message == "SkillKit shadow provider invocation failed"
    assert "secret provider payload" not in (shadow.error_message or "")
    assert shadow.candidate is None
    assert result.draft.status == "draft"
    assert all(inv.response_contract != "character_skill_kit" for inv in result.audit.model_invocations)


def test_shadow_malformed_json_is_contained():
    model = _ShadowModel(shadow_turn=ModelTurn(text="{not-json"))
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.failure_stage == "json"
    assert shadow.response_compliant is False
    assert shadow.candidate is None
    assert result.draft.status == "draft"


def test_shadow_legacy_or_enveloped_shape_is_rejected():
    model = _ShadowModel(
        shadow_turn=ModelTurn(
            structured_output={"ability_concept": "legacy text"}
        )
    )
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.failure_stage == "shape"
    assert shadow.response_compliant is False
    assert shadow.candidate is None
    assert result.draft.status == "draft"


def test_shadow_repair_report_does_not_change_legacy_draft_or_verdict():
    model = _enabled_model(payload=_repair_candidate_payload())
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.response_compliant is True
    assert shadow.validation_report is not None
    assert shadow.validation_report.outcome == "REPAIR"
    assert result.draft.status == "draft"
    assert result.draft.ability_concept == shadow.legacy_ability_concept


def test_shadow_prompt_does_not_contain_legacy_ability_concept():
    model = _enabled_model(payload=_candidate_payload())
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    shadow_prompt = next(
        prompt for prompt in model.prompts if prompt.response_format == "character_skill_kit"
    )
    serialized_prompt = json.dumps(
        {
            "system": shadow_prompt.system_contract,
            "messages": [message.content for message in shadow_prompt.messages],
            "payload": shadow_prompt.authoring_payload,
            "runtime": shadow_prompt.runtime.brief,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert result.draft.ability_concept not in serialized_prompt


def test_shadow_audit_is_separate_and_result_is_deterministic():
    invocation = ModelInvocationAudit(
        session_id="shadow_session",
        turn_number=1,
        provider="fake-provider",
        model="fake-model",
        outcome="success",
        latency_ms=0.0,
        retry_count=0,
        provider_request_id="provider-request-1",
        response_contract="character_skill_kit",
    )
    first_model = _ShadowModel(
        shadow_turn=ModelTurn(
            structured_output=_candidate_payload(),
            invocation=invocation,
        )
    )
    second_model = _ShadowModel(
        shadow_turn=ModelTurn(
            structured_output=_candidate_payload(),
            invocation=invocation,
        )
    )
    first = CharacterGenerationAgent(
        first_model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())
    second = CharacterGenerationAgent(
        second_model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request())

    assert first.skill_shadow == second.skill_shadow
    assert first.skill_shadow is not None
    assert first.skill_shadow.audit.request_id == "shadow_request"
    assert first.skill_shadow.audit.provider == "fake-provider"
    assert first.skill_shadow.audit.model == "fake-model"
    assert first.skill_shadow.audit.provider_request_id == "provider-request-1"
    assert first.skill_shadow.audit.response_contract == "character_skill_kit"
    assert first.skill_shadow.audit.invocation_purpose == "character_skill_shadow"
    assert all(
        invocation.response_contract != "character_skill_kit"
        for invocation in first.audit.model_invocations
    )
