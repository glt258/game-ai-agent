"""CS-S2 integration gate through the reviewed public seams."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import character_skill
from agents.character_generation import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    DeterministicCharacterGenerationModel,
)
from agents.models import ModelTurn, SkillShadowConfig
from agents.response_contracts import CHARACTER_DRAFT_RESPONSE_CONTRACT, response_contract_for
from character_skill import (
    ProtocolSkillKitCandidate,
    SkillKitPatchError,
    SkillKitShapeError,
    evaluate,
    parse_candidate,
    render_ability_concept,
    repair_once,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE = (
    ROOT
    / "evals"
    / "fixtures"
    / "character_skill_interface_prototype_cases_v0.1.1.public.json"
)


def _public_cases() -> tuple[dict[str, object], ...]:
    return tuple(json.loads(PUBLIC_FIXTURE.read_text(encoding="utf-8"))["cases"])


def _case(case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    row = next(item for item in _public_cases() if item["case_id"] == case_id)
    return copy.deepcopy(row["candidate"]), copy.deepcopy(row["context"])


_EXPECTED_SEMANTICS = {
    "case_01": ("PASS", (), "5090c635d1d94df2a82384d5a79432317807f0b6a751c19f450a9a6c0886a09a", "484cf36660bea0ecc2c1436475c5cc6df16cb111beff1ad9915b5927997a0e30", "7b47fc43823ceb0a9be016cd724ae9e7c9ba5b9b0641d5ad299aea83b7898a6b"),
    "case_02": ("REPAIR", ("RESOURCE_LOOP_INCOMPLETE",), "3e17a8d922374373b04f4fee3e22e60d14e33a23979c42a6ffc238e42bada8b4", "484cf36660bea0ecc2c1436475c5cc6df16cb111beff1ad9915b5927997a0e30", "b95f47d27ca9bd65f41e159b0c0ddafd427e7e1b626748e7b65ff2eccdbf0fdb"),
    "case_03": ("FAIL", ("FORBIDDEN_RESOURCE_INTRODUCED",), "5090c635d1d94df2a82384d5a79432317807f0b6a751c19f450a9a6c0886a09a", "27b650ae05bc8f306967ffb125b4a7e5f47ae9bbed5439be7b3444c142af94d3", "aa18b2dbf32ff683f2d8d1a8cc8389b772e3b8eaa9043555d8818f5304e0a480"),
    "case_04": ("REPAIR", ("STATE_EXIT_MISSING",), "010a17662b9cf42203d7d210c81f1ff44589b827f11e82734948a65b0673a356", "484cf36660bea0ecc2c1436475c5cc6df16cb111beff1ad9915b5927997a0e30", "b0c20e826e7c3c1ec074322d9165090cd8ab013a8b5f7465bccb7dda64f5b403"),
    "case_05": ("REPAIR", ("TRIGGER_SUBJECT_AMBIGUOUS",), "c5bf6a870bd8920488606b0ecc483006ab0e28804bdcc563cca86c81029402d6", "fbdcb6778fe07f5003de0f5223292351437a2de226b7e7ac47ef50d9c6c29d34", "b835daa3a8d4d1dfd0d9322d1ab25246c45535766b7e02375ccd8985b074dc53"),
    "case_06": ("REPAIR", ("SUMMON_LIFECYCLE_INCOMPLETE",), "bd9fa59c991356375a67c0d0fb53bc8352cc2bb73ed97d0c5976a63f116feaaa", "c4585e040beba281be102c8a2e9c342ab4c312aef2990758e10ec8fe7fe21018", "3edc9043592f9c44e5f86d3ab1c46e60d144ddca6a6b561efe4bdcfa45f92782"),
    "case_07": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "dc3602490dd5b2e72accdb04dad185cd07357633e8540c733893facb02b4f095", "1692f8786abd346f55f41702510834611dbebce52f472b10e8e656ee86eb6ec0", "85a7fc59e83fb137330376722f76d5399a22e7cc66c0a30a3ff6e76905187a40"),
    "case_08": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "dc3602490dd5b2e72accdb04dad185cd07357633e8540c733893facb02b4f095", "9a645de37fe6e7a8fd5cedeb244070f789897de033cfc7fa658eca05fc421457", "c7e13583f3975e755ef28dd539869b80d6191188939553a367945e5fb42e2b6c"),
    "case_09": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "3f307fa0c88a0142b788efdd126757d49ecb641e4e30878d69587f9de677d942", "fbdcb6778fe07f5003de0f5223292351437a2de226b7e7ac47ef50d9c6c29d34", "72803db3d53350ef96830b73ae80f947ef54eb6a09fe01c1d5088f937cd9f145"),
    "case_10": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "3f307fa0c88a0142b788efdd126757d49ecb641e4e30878d69587f9de677d942", "ed9231e8aa76d76c90188999f9657ec832f15627a44c757ff3ac220417202bc8", "ec72cb671a5273d89184276c6e4db45085c7a7d110ae04fddcdd41cc681583eb"),
    "case_11": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "3f307fa0c88a0142b788efdd126757d49ecb641e4e30878d69587f9de677d942", "c4585e040beba281be102c8a2e9c342ab4c312aef2990758e10ec8fe7fe21018", "6c73d94940ffa764fdcb7a2f9774d2dae4e18c22ef1aed2b4a15fdd6b891207d"),
    "case_12": ("FAIL", ("ROLE_EFFECT_MISMATCH",), "3f307fa0c88a0142b788efdd126757d49ecb641e4e30878d69587f9de677d942", "b16b53d7426aaa7d2a57da8608da19ff0f6c51aee7db162b5d2ca3b3ae930483", "90a7fbff03f3dc77a8a4d1653875fa9fa54ae520284c22bc575119a82d4e87ee"),
    "case_13": ("FAIL", ("MECHANIC_SKELETON_ABSENT",), "1d43623401c96ce5c586f2192f7cc5e015c44ddd00d64cb63b28c50dac769ea1", "9824ca7fc2165bac545ea5ab427217eac476f2aa771ffa20bccd81478f16686f", "ad0b3c23bd96f9d7e6b389b5d9e5707a82770d176ecd215a365145f4950a1faa"),
    "case_14": ("FAIL", ("CROSS_TAXONOMY_ROLE_LABEL",), "541afbbf09eb26136c9cf30bdc619213b51f27e46782f8506344dc4e2eb1c934", "f99cfc1e13f74032b459a494208bf126e4295b5d964f496b2fa795bb7a63c4f5", "8d6407885217b94751109a432fd1654f71b0b3f6904dc066f582dc641cb67087"),
    "case_15": ("FAIL", ("REFERENCE_COPYING",), "16b96809c0c8a5ccd40a1b0054b561680c634840e37dc1266559bb350cebf6e0", "7f3c031aa5f5aa6b03abbd19dd2314b88b77eadfb5a8c97a10c5ab98d59ecf2d", "a3a59a61a91d2de06052efb2772bf18ab21176e368bfb46ea28636edd5a802d8"),
    "case_16": ("FAIL", ("HARD_CONSTRAINT_CONFLICT",), "16b96809c0c8a5ccd40a1b0054b561680c634840e37dc1266559bb350cebf6e0", "02fb476ca50e47b6b9622f07419780ff23c38a4c1e7b89d267dc54b4e07b227c", "ceb0677e1e93e4a1863bf8dab6f7b22976e4547e2ef4683fc200f87ecea4baa0"),
    "case_17": ("REPAIR", ("MULTI_SKILL_LOOP_INCOHERENT",), "d71295a0c1e2e99d1ad061ac30b89276bf965a54eeabe289df43693173966d3b", "c2b9a446f28f1d50f1e48beab461f771a4b9102777757040b5fddaceeeeea14e", "0b4aa0613746d68bcc4d940a2010bb90094ff5f97c6a395740f43dbf3801697a"),
    "case_18": ("PASS", (), "16b96809c0c8a5ccd40a1b0054b561680c634840e37dc1266559bb350cebf6e0", "c4585e040beba281be102c8a2e9c342ab4c312aef2990758e10ec8fe7fe21018", "6c004130c0760c8467dea5ab30708ff3d9aef30a744ae33f794c7cb952cbdbda"),
    "case_19": ("REPAIR", ("REQUESTED_MECHANIC_UNREPRESENTED",), "e5f520a491ef649bfa623e666f69f72518bcf6ad565c8edc09b6b19cc1612013", "9824ca7fc2165bac545ea5ab427217eac476f2aa771ffa20bccd81478f16686f", "e009696659b5d612bdf9bf3a52a8becb8de5ffd985957005413b7e9807594ccc"),
}

_EXPECTED_RENDERINGS = {
    "case_01": "Resource: scene/scene scene_exited -> resource_clear; self/owner ability_invoked -> resource_gain; self/owner ability_invoked -> resource_use",
    "case_02": "Resource: self/owner ability_invoked -> resource_use",
    "case_03": "Resource: scene/scene scene_exited -> resource_clear; self/owner ability_invoked -> resource_gain; self/owner ability_invoked -> resource_use",
    "case_04": "Focus: self/owner ability_invoked -> state_apply; self/owner ability_invoked -> state_enter",
    "case_05": "Ambiguous: self/owner ability_invoked -> ally_enablement; ally event -> ally_enablement",
    "case_06": "Control: self/owner ability_invoked -> enemy_action_control; summon/field summon_acted -> summon_act; self/owner ability_invoked -> summon_spawn",
    "case_07": "Support: self/owner ability_invoked -> ally_enablement",
    "case_08": "Support: self/owner ability_invoked -> ally_enablement",
    "case_09": "Direct: self/owner ability_invoked -> direct_output",
    "case_10": "Direct: self/owner ability_invoked -> direct_output",
    "case_11": "Direct: self/owner ability_invoked -> direct_output",
    "case_12": "Direct: self/owner ability_invoked -> direct_output",
    "case_13": "echo echo resonance Base: self/owner ability_invoked -> ally_enablement",
    "case_14": "SkillKit concept: no ability entries declared.",
    "case_15": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_16": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_17": "First: ally/ally action_completed -> follow_up_output; self/owner ability_invoked -> ally_enablement Second: self/owner ability_invoked -> resource_use",
    "case_18": "Control: ally/ally action_completed -> enemy_action_control; summon/field summon_acted -> summon_act; scene/scene scene_exited -> summon_replace; self/owner ability_invoked -> summon_spawn",
    "case_19": "Echo: self/owner feedback_received -> ally_enablement; self/owner ability_invoked -> ally_enablement; ally/ally action_completed -> ally_enablement",
}

_EXPECTED_FINDING_PATHS = {
    "case_01": (),
    "case_02": (("RESOURCE_LOOP_INCOMPLETE", "/resources/0"),),
    "case_03": (("FORBIDDEN_RESOURCE_INTRODUCED", "/resources"),),
    "case_04": (("STATE_EXIT_MISSING", "/states/0/ended_or_replaced_by"),),
    "case_05": (("TRIGGER_SUBJECT_AMBIGUOUS", "/entries/0/protocols/0/when"),),
    "case_06": (("SUMMON_LIFECYCLE_INCOMPLETE", "/summons/0"),),
    "case_07": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_08": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_09": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_10": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_11": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_12": (("ROLE_EFFECT_MISMATCH", "/role_evidence"),),
    "case_13": (("MECHANIC_SKELETON_ABSENT", "/entries"),),
    "case_14": (("CROSS_TAXONOMY_ROLE_LABEL", "context.combat_role_profile"),),
    "case_15": (("REFERENCE_COPYING", "/context/reference_review_context"),),
    "case_16": (("HARD_CONSTRAINT_CONFLICT", "/context/intent/hard_constraint_conflicts"),),
    "case_17": (("MULTI_SKILL_LOOP_INCOHERENT", "/resources/0"),),
    "case_18": (),
    "case_19": (("REQUESTED_MECHANIC_UNREPRESENTED", "/feedback_relations/-"),),
}


def test_s2_gate_closes_19_case_parse_evaluate_and_renderer_goldens() -> None:
    assert {item["case_id"] for item in _public_cases()} == set(_EXPECTED_SEMANTICS)
    assert set(_EXPECTED_RENDERINGS) == set(_EXPECTED_SEMANTICS)
    for row in _public_cases():
        case_id = row["case_id"]
        candidate = parse_candidate(row["candidate"])
        report = evaluate(candidate, row["context"])
        outcome, codes, candidate_digest, context_digest, report_digest = _EXPECTED_SEMANTICS[case_id]
        assert isinstance(candidate, ProtocolSkillKitCandidate)
        assert report.outcome == outcome
        assert report.finding_codes == codes
        assert tuple((item.code, item.field_path) for item in report.findings) == _EXPECTED_FINDING_PATHS[case_id]
        assert report.candidate_digest == candidate_digest
        assert report.context_digest == context_digest
        assert report.report_digest == report_digest
        assert render_ability_concept(candidate) == _EXPECTED_RENDERINGS[case_id]


def test_s2_gate_serialization_digest_and_findings_are_deterministic() -> None:
    for row in _public_cases():
        candidate = parse_candidate(row["candidate"])
        first = evaluate(candidate, row["context"])
        second = evaluate(parse_candidate(candidate.to_mapping()), row["context"])
        assert candidate.canonical_json() == parse_candidate(candidate.to_mapping()).canonical_json()
        assert candidate.digest == parse_candidate(candidate.to_mapping()).digest
        assert first.to_mapping() == second.to_mapping()
        assert render_ability_concept(candidate) == render_ability_concept(parse_candidate(candidate.to_mapping()))


def test_s2_gate_provider_contract_is_direct_strict_and_does_not_change_legacy_routing() -> None:
    contract = response_contract_for("character_skill_kit")
    assert contract.strict is True
    assert contract.json_schema is not None
    assert contract.json_schema["additionalProperties"] is False
    assert set(contract.json_schema["required"]) == {
        "schema_version", "entries", "feedback_relations", "resources", "states",
        "summons", "role_evidence", "display_summary",
    }
    assert contract is not CHARACTER_DRAFT_RESPONSE_CONTRACT
    assert response_contract_for("character_draft") is CHARACTER_DRAFT_RESPONSE_CONTRACT
    assert response_contract_for("unknown-format").name == "text"
    candidate_payload, _ = _case("case_01")
    for payload in (
        {"skill_kit": candidate_payload},
        {"ability_concept": "legacy"},
        {**candidate_payload, "unexpected": True},
    ):
        assert set(payload) != set(contract.json_schema["required"])
    with pytest.raises(SkillKitShapeError):
        parse_candidate({**candidate_payload, "unexpected": True})
    for row in _public_cases():
        assert isinstance(parse_candidate(row["candidate"]), ProtocolSkillKitCandidate)
    assert {"parse_candidate", "evaluate", "render_ability_concept", "repair_once"} <= set(
        character_skill.__all__
    )


class _GateShadowModel:
    def __init__(self, *, shadow: ModelTurn | None = None, failure: Exception | None = None) -> None:
        self.legacy = DeterministicCharacterGenerationModel()
        self.prompts: list[object] = []
        self.shadow = shadow
        self.failure = failure

    def generate(self, prompt: object) -> ModelTurn:
        self.prompts.append(prompt)
        if prompt.response_format == "character_skill_kit":
            if self.failure is not None:
                raise self.failure
            assert self.shadow is not None
            return self.shadow
        return self.legacy.generate(prompt)


def _request(request_id: str = "s2_gate_request") -> CharacterDesignRequest:
    return CharacterDesignRequest("设计一个角色", request_id=request_id)


def test_s2_gate_flag_off_preserves_legacy_result_and_call_contract() -> None:
    first_model = _GateShadowModel()
    second_model = _GateShadowModel()
    first = CharacterGenerationAgent(first_model).generate(_request())
    second = CharacterGenerationAgent(
        second_model,
        shadow_config=SkillShadowConfig(enabled=False),
    ).generate(_request())

    assert first.skill_shadow is None and second.skill_shadow is None
    assert first.draft == second.draft
    assert first.sources == second.sources
    assert first.audit == second.audit
    assert first.design_plan == second.design_plan
    assert [prompt.response_format for prompt in first_model.prompts] == [
        prompt.response_format for prompt in second_model.prompts
    ]
    assert all(prompt.response_format != "character_skill_kit" for prompt in first_model.prompts)


def test_s2_gate_shadow_is_sidecar_and_sanitizes_provider_secrets() -> None:
    secret = "S2_UNIQUE_PROVIDER_SECRET_4f90"
    model = _GateShadowModel(failure=RuntimeError(secret))
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request("s2_secret_request"))
    shadow = result.skill_shadow
    assert shadow is not None
    assert shadow.failure_stage == "provider"
    assert shadow.error_message == "SkillKit shadow provider invocation failed"
    serialized = " ".join((repr(result), repr(shadow), repr(shadow.audit), shadow.error_message or ""))
    assert secret not in serialized
    assert all(inv.response_contract != "character_skill_kit" for inv in result.audit.model_invocations)

    malformed = _GateShadowModel(shadow=ModelTurn(text=f'{{"secret":"{secret}"}}'))
    malformed_result = CharacterGenerationAgent(
        malformed,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request("s2_malformed_request"))
    malformed_shadow = malformed_result.skill_shadow
    assert malformed_shadow is not None
    assert malformed_shadow.error_message == "SkillKit shadow candidate failed the strict shape contract"
    assert secret not in repr(malformed_result)


def _valid_feedback_relation() -> dict[str, object]:
    return {
        "feedback_id": "echo_feedback",
        "source_effect": {"kind": "effect", "id": "echo/trigger/apply"},
        "target_protocol": {"kind": "protocol", "id": "echo/feedback"},
        "event": "effect_resolved",
        "operation": "enables",
    }


def test_s2_gate_repair_once_is_bound_and_case19_passes() -> None:
    candidate_payload, context = _case("case_19")
    candidate = parse_candidate(candidate_payload)
    report = evaluate(candidate, context)
    original_digest = candidate.digest
    calls: list[object] = []

    def provider(request: object) -> object:
        calls.append(request)
        return {
            "base_digest": request.base_digest,
            "report_digest": request.report_digest,
            "operations": [{"op": "add", "path": "/feedback_relations/-", "value": _valid_feedback_relation()}],
        }

    result = repair_once(candidate, report, context, provider)
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.report.outcome == "PASS"
    assert candidate.digest == original_digest

    with pytest.raises(SkillKitPatchError):
        repair_once(
            candidate,
            report,
            context,
            lambda request: {
                "base_digest": "0" * 64,
                "report_digest": request.report_digest,
                "operations": [],
            },
        )

    with pytest.raises(SkillKitPatchError):
        repair_once(
            candidate,
            report,
            context,
            lambda request: {
                "base_digest": request.base_digest,
                "report_digest": request.report_digest,
                "operations": [{"op": "add", "path": "/canon_basis/-", "value": {}}],
            },
        )


@pytest.mark.parametrize("case_id", ["case_13", "case_14", "case_15"])
def test_s2_gate_nonrepairable_findings_never_call_provider(case_id: str) -> None:
    candidate_payload, context = _case(case_id)
    candidate = parse_candidate(candidate_payload)
    report = evaluate(candidate, context)
    calls: list[object] = []
    with pytest.raises(SkillKitPatchError):
        repair_once(candidate, report, context, lambda request: calls.append(request))
    assert calls == []


def test_s2_gate_shadow_findings_do_not_mutate_legacy_draft() -> None:
    candidate_payload, _ = _case("case_02")
    model = _GateShadowModel(shadow=ModelTurn(structured_output=candidate_payload))
    result = CharacterGenerationAgent(
        model,
        shadow_config=SkillShadowConfig(enabled=True),
    ).generate(_request("s2_repair_shadow"))
    assert result.skill_shadow is not None
    assert result.skill_shadow.validation_report.outcome == "REPAIR"
    assert result.draft.status == "draft"
    assert result.draft.ability_concept == result.skill_shadow.legacy_ability_concept
