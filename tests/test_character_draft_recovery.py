from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    ModelInvocationAudit,
    ModelMalformedResponseError,
    ModelTurn,
    ScriptedAgentModel,
)


FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "canon_checker_good.json"
_RECOVERED_DESIGN_ELEMENTS = [
    "new_design:occupation: 原始草稿中的职业为新设计",
    "new_design:social_role: 原始草稿中的社会角色为新设计",
    "new_design:design_pitch: 原始草稿中的角色概念为新设计",
    "new_design:personality: 原始草稿中的性格为新设计",
    "new_design:background: 原始草稿中的背景为新设计",
    "new_design:story_hook: 原始草稿中的故事钩子为新设计",
    "new_design:ability_concept: 原始草稿中的能力概念为新设计",
    "new_design:knowledge_scope: 原始草稿中的知识范围为新设计",
]


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["draft"]
    # Keep the recovery tests focused on structure rather than Canon
    # grounding; no retrieval turn is part of these fixtures.
    payload["faction_id"] = None
    payload["canon_basis"] = []
    payload["new_design_elements"] = [
        *payload["new_design_elements"],
        "new_design:occupation: 职业为新设计",
        "new_design:social_role: 社会角色为新设计",
    ]
    return payload


def _invocation(turn: int, purpose: str = "generation") -> ModelInvocationAudit:
    return ModelInvocationAudit(
        "recovery-test",
        turn,
        "test-provider",
        "test-model",
        "success",
        1.0,
        0,
        purpose=purpose,
    )


def _run(original: dict, recovery: dict | None = None):
    turns = [
        ModelTurn(text="FINALIZE", invocation=_invocation(1)),
        ModelTurn(
            structured_output=original,
            invocation=_invocation(2),
        ),
    ]
    if recovery is not None:
        turns.append(
            ModelTurn(
                structured_output=recovery,
                invocation=_invocation(3, "character_draft_recovery"),
            )
        )
    return CharacterGenerationAgent(ScriptedAgentModel(turns)).generate(
        CharacterDesignRequest("设计一个完全原创的角色。", request_id="recovery_test")
    )


@pytest.mark.parametrize("missing", ["canon_basis", "new_design_elements"])
def test_missing_one_core_field_uses_one_bounded_recovery_call(missing: str):
    original = _payload()
    original.pop(missing)
    result = _run(
        original,
        {
            missing: []
            if missing == "canon_basis"
            else list(_RECOVERED_DESIGN_ELEMENTS)
        },
    )

    assert result.draft.to_dict()[missing] == (
        [] if missing == "canon_basis" else _RECOVERED_DESIGN_ELEMENTS
    )
    recovery = result.audit.contract_recovery
    assert recovery.status == "applied"
    assert recovery.attempted is True
    assert recovery.recovered_fields == (missing,)
    assert len(result.audit.model_invocations) == 3
    assert result.audit.model_invocations[-1].purpose == "character_draft_recovery"


def test_missing_both_core_fields_are_recovered_in_one_attempt():
    original = _payload()
    original.pop("canon_basis")
    original.pop("new_design_elements")
    result = _run(
        original,
        {
            "canon_basis": [],
            "new_design_elements": list(_RECOVERED_DESIGN_ELEMENTS),
        },
    )

    assert result.audit.contract_recovery.recovered_fields == (
        "canon_basis",
        "new_design_elements",
    )
    assert len(result.audit.model_invocations) == 3


def test_recovery_cannot_overwrite_valid_existing_fields():
    original = _payload()
    original.pop("canon_basis")
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE", invocation=_invocation(1)),
            ModelTurn(structured_output=original, invocation=_invocation(2)),
            ModelTurn(
                structured_output={"canon_basis": [], "name": "改名"},
                invocation=_invocation(3, "character_draft_recovery"),
            ),
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match="overwrite valid field") as captured:
        CharacterGenerationAgent(model).generate("设计一个角色")

    assert captured.value.contract_recovery.status == "failed"
    assert len(model.prompts) == 3  # no fourth recovery attempt


@pytest.mark.parametrize(
    "recovery_turn",
    [
        ModelTurn(structured_output={"canon_basis": []}, invocation=_invocation(3, "character_draft_recovery")),
        ModelTurn(text="{not-json", invocation=_invocation(3, "character_draft_recovery")),
    ],
)
def test_failed_recovery_is_fail_closed_and_never_retried(recovery_turn: ModelTurn):
    original = _payload()
    original.pop("canon_basis")
    original.pop("new_design_elements")
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE", invocation=_invocation(1)),
            ModelTurn(structured_output=original, invocation=_invocation(2)),
            recovery_turn,
        ]
    )

    with pytest.raises(ModelMalformedResponseError):
        CharacterGenerationAgent(model).generate("设计一个角色")

    assert len(model.prompts) == 3
    assert model.prompts[-1].invocation_purpose == "character_draft_recovery"


def test_open_questions_retains_existing_safe_normalization_without_recovery():
    original = _payload()
    original.pop("open_questions")
    result = _run(original)

    assert result.draft.open_questions == ()
    assert result.audit.normalized_fields == ("open_questions",)
    assert result.audit.contract_recovery.status == "not_attempted"
    assert len(result.audit.model_invocations) == 2


@pytest.mark.parametrize("unknown", ["/iframe>{", "generic_unknown_field"])
def test_unknown_fields_are_discarded_only_after_known_draft_is_valid(unknown: str):
    original = _payload()
    original[unknown] = "junk"
    result = _run(original)

    recovery = result.audit.contract_recovery
    assert recovery.status == "applied"
    assert recovery.attempted is False
    assert recovery.discarded_unknown_fields == (unknown,)
    assert unknown not in result.draft.to_dict()
    assert len(result.audit.model_invocations) == 2


def test_unknown_field_with_missing_core_is_not_silently_dropped():
    original = _payload()
    original.pop("canon_basis")
    original["generic_unknown_field"] = "junk"
    model = ScriptedAgentModel(
        [
            ModelTurn(text="FINALIZE", invocation=_invocation(1)),
            ModelTurn(structured_output=original, invocation=_invocation(2)),
        ]
    )

    with pytest.raises(ModelMalformedResponseError, match="unknown fields"):
        CharacterGenerationAgent(model).generate("设计一个角色")

    assert len(model.prompts) == 2
