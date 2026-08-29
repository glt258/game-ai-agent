from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from agents.character_generation import (
    CharacterAuthoringView,
    CharacterGenerationRuntimeView,
)
from agents.errors import ModelProviderError
from agents.live_llm import LiveLLMAdapter
from agents.models import (
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    ModelUsage,
)
from agents.provider_profiles import resolve_provider_profile
from agents.provider_protocol import ProviderCompletion
from evals import character_skill_s2_shadow_evidence as evidence
from tests.historical_fixtures import FIXTURE_ROOT, historical_fixture_path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CASES = json.loads(
    (ROOT / "evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json").read_text(
        encoding="utf-8"
    )
)["cases"]
PUBLIC_BY_ID = {item["case_id"]: item for item in PUBLIC_CASES}


def _invocation(model: str = "deepseek-v4-flash") -> ModelInvocationAudit:
    return ModelInvocationAudit(
        session_id="provider-session",
        turn_number=1,
        provider="opencode_go",
        model=model,
        outcome="success",
        latency_ms=12.5,
        retry_count=0,
        usage=ModelUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        transport="openai_chat_completions",
        response_contract="character_skill_kit",
    )


class _CandidateModel:
    def __init__(self, payload: object = None, *, error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.prompts: list[AgentPrompt] = []
        self.calls = 0

    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        self.calls += 1
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return ModelTurn(structured_output=self.payload, invocation=_invocation())


class _MalformedModel(_CandidateModel):
    def generate(self, prompt: AgentPrompt) -> ModelTurn:
        self.calls += 1
        self.prompts.append(prompt)
        return ModelTurn(text="{not-json", invocation=_invocation())


class _WireClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.messages: list[dict[str, object]] = []

    def complete(self, *, model, messages, tools, timeout_seconds, response_contract):
        del model, tools, timeout_seconds, response_contract
        self.messages = [dict(item) for item in messages]
        return ProviderCompletion(
            text=json.dumps(self.payload, ensure_ascii=False),
            request_id="provider-request-id",
            usage=ModelUsage(input_tokens=5, output_tokens=7, total_tokens=12),
        )


def _run_case(tmp_path: Path, case_id: str, model: object) -> dict[str, object]:
    output = tmp_path / f"{case_id}.json"
    return evidence.ShadowEvidenceRunner(ROOT).run(
        live=True,
        case_id=case_id,
        output_path=output,
        shadow_model=model,
        enforce_clean_tree=False,
    )


def test_manifest_and_default_dry_run_are_reproducible_without_factory_or_result() -> None:
    runner = evidence.ShadowEvidenceRunner(ROOT)
    before = {
        path.name
        for path in FIXTURE_ROOT.glob("character_skill_s2_shadow_deepseek_run_*.json")
    }
    result = runner.run(live=False, case_id="case_13")

    assert result["status"] == "dry_run"
    assert result["case_ids"] == ["case_13"]
    assert result["provider_factory_constructed"] is False
    assert result["provider_called"] is False
    assert result["result_count"] == 0
    assert result["result_path"] is None
    after = {
        path.name
        for path in FIXTURE_ROOT.glob("character_skill_s2_shadow_deepseek_run_*.json")
    }
    assert after == before


def test_router_rebuilds_remote_prompt_from_only_four_frozen_projection_fields() -> None:
    shadow = _CandidateModel({})
    router = evidence.ShadowEvidenceModelRouter(shadow)
    runtime = CharacterGenerationRuntimeView(
        request_id="request_secret",
        brief="public brief",
        hard_constraints=("hard constraint",),
        soft_preferences=("soft_preferences SECRET",),
        forbidden_elements=("forbidden element",),
        desired_connections=("desired_connections SECRET",),
        reference_context=(
            {"reference context": "private oracle", "fingerprint": "PRIVATE_FINGERPRINT"},
        ),
    )
    prompt = AgentPrompt(
        "system",
        CharacterAuthoringView("authoring", "purpose", ()),
        runtime,
        (ConversationMessage("user", "candidate_observation public candidate private oracle"),),
        (),
        "request_secret",
        1,
        response_format="character_skill_kit",
        authoring_payload={"private": "should not survive"},
        invocation_purpose="character_skill_shadow",
    )

    router.generate(prompt)

    remote = shadow.prompts[0]
    assert set(remote.authoring_payload or {}) == {
        "brief",
        "hard_constraints",
        "forbidden_elements",
        "combat_role_profile",
    }
    serialized = json.dumps(
        {
            "character": asdict(remote.character),
            "runtime": asdict(remote.runtime),
            "messages": [message.content for message in remote.messages],
            "payload": remote.authoring_payload,
            "session_id": remote.session_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for secret in (
        "candidate_observation",
        "public candidate",
        "private oracle",
        "request_secret",
        "soft_preferences SECRET",
        "desired_connections SECRET",
        "PRIVATE_FINGERPRINT",
        "reference context",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    ("case_id", "outcome", "code", "path"),
    [
        ("case_13", "FAIL", "MECHANIC_SKELETON_ABSENT", "/entries"),
        ("case_19", "REPAIR", "REQUESTED_MECHANIC_UNREPRESENTED", "/feedback_relations/-"),
    ],
)
def test_runner_evaluates_case_13_case_19_boundary_without_provider_payload_leak(
    tmp_path: Path, case_id: str, outcome: str, code: str, path: str
) -> None:
    model = _CandidateModel(PUBLIC_BY_ID[case_id]["candidate"])
    bundle = _run_case(tmp_path, case_id, model)
    record = bundle["observations"][0]

    assert record["observation"]["outcome"] == outcome
    assert record["observation"]["finding_codes"] == [{"code": code, "path": path}]
    assert record["observation"]["legacy_impact"] is False
    assert record["sanitization"] == {
        "raw_prompt_stored": False,
        "raw_response_stored": False,
        "secrets_detected": False,
    }
    assert model.calls == 1
    candidate_text = json.dumps(PUBLIC_BY_ID[case_id]["candidate"], ensure_ascii=False, sort_keys=True)
    assert candidate_text not in json.dumps(record, ensure_ascii=False, sort_keys=True)
    evidence.validate_evidence_bundle(bundle)


def test_case_14_context_path_is_normalized_to_json_pointer(tmp_path: Path) -> None:
    model = _CandidateModel(PUBLIC_BY_ID["case_14"]["candidate"])
    bundle = _run_case(tmp_path, "case_14", model)
    findings = bundle["observations"][0]["observation"]["finding_codes"]

    assert findings == [{"code": "CROSS_TAXONOMY_ROLE_LABEL", "path": "/context/combat_role_profile"}]


def test_case_15_reference_fingerprint_is_evaluator_only(tmp_path: Path) -> None:
    model = _CandidateModel(PUBLIC_BY_ID["case_15"]["candidate"])
    bundle = _run_case(tmp_path, "case_15", model)

    record = bundle["observations"][0]
    assert record["observation"]["outcome"] == "FAIL"
    assert record["observation"]["finding_codes"] == [
        {"code": "REFERENCE_COPYING", "path": "/context/reference_review_context"}
    ]
    assert model.prompts
    provider_prompt = json.dumps(
        {
            "messages": [message.content for message in model.prompts[0].messages],
            "payload": model.prompts[0].authoring_payload,
        },
        ensure_ascii=False,
    )
    assert "external/control" not in provider_prompt
    assert "4fcd9f45d9231869bd6097bc2db50cd974db12fe5001a5c47d43e0198b61b974" not in provider_prompt


def test_live_llm_adapter_receives_only_sanitized_wire_projection(tmp_path: Path) -> None:
    client = _WireClient(PUBLIC_BY_ID["case_15"]["candidate"])
    profile = resolve_provider_profile("opencode_go", "deepseek-v4-flash")
    adapter = LiveLLMAdapter(
        client,
        provider="opencode_go",
        model="deepseek-v4-flash",
        profile=profile,
        sleep=lambda _: None,
    )

    _run_case(tmp_path, "case_15", adapter)

    wire = json.dumps(client.messages, ensure_ascii=False, sort_keys=True)
    for secret in (
        "candidate_observation",
        "external/control",
        "4fcd9f45d9231869bd6097bc2db50cd974db12fe5001a5c47d43e0198b61b974",
        "draft_s2_case_15",
        "request_id",
        "reference_review_context",
    ):
        assert secret not in wire
    assert "brief" in wire and "hard_constraints" in wire and "forbidden_elements" in wire


def test_malformed_and_provider_failure_are_stable_and_non_leaking(tmp_path: Path) -> None:
    malformed = _run_case(tmp_path, "case_13", _MalformedModel())
    failed = _run_case(
        tmp_path,
        "case_19",
        _CandidateModel(error=ModelProviderError("provider secret raw response")),
    )

    malformed_observation = malformed["observations"][0]["observation"]
    failed_observation = failed["observations"][0]["observation"]
    assert (malformed_observation["failure_stage"], malformed_observation["failure_code"]) == (
        "json",
        "RESPONSE_JSON_INVALID",
    )
    assert (failed_observation["failure_stage"], failed_observation["failure_code"]) == (
        "provider",
        "PROVIDER_INVOCATION_FAILED",
    )
    serialized = json.dumps([malformed, failed], ensure_ascii=False)
    assert "provider secret raw response" not in serialized


def test_resume_skips_valid_observation_and_does_not_overwrite_without_resume(tmp_path: Path) -> None:
    output = tmp_path / "resume.json"
    first_model = _CandidateModel(PUBLIC_BY_ID["case_13"]["candidate"])
    first = evidence.ShadowEvidenceRunner(ROOT).run(
        live=True,
        case_id="case_13",
        output_path=output,
        shadow_model=first_model,
        enforce_clean_tree=False,
    )
    original_bytes = output.read_bytes()
    second_model = _CandidateModel(error=AssertionError("must not call provider on resume"))
    resumed = evidence.ShadowEvidenceRunner(ROOT).run(
        live=True,
        case_id="case_13",
        resume=True,
        output_path=output,
        shadow_model=second_model,
        enforce_clean_tree=False,
    )

    assert first["observations"] == resumed["observations"]
    assert second_model.calls == 0
    assert output.read_bytes() == original_bytes
    assert not output.with_name("." + output.name + ".tmp").exists()
    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        evidence.ShadowEvidenceRunner(ROOT).run(
            live=True,
            case_id="case_13",
            output_path=output,
            shadow_model=_CandidateModel(PUBLIC_BY_ID["case_13"]["candidate"]),
            enforce_clean_tree=False,
        )
    assert captured.value.code == "RESULT_EXISTS_WITHOUT_RESUME"


def _copy_run_01(tmp_path: Path) -> Path:
    source = tmp_path / "source-run-01.json"
    source.write_bytes(
        historical_fixture_path(evidence.RESULT_RELATIVE_TEMPLATE.format(repeat=1)).read_bytes()
    )
    return source


def test_retry_unavailable_dry_run_is_provider_free_and_preserves_source(tmp_path: Path) -> None:
    source = _copy_run_01(tmp_path)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    runner = evidence.RetryUnavailableCohortRunner(ROOT)
    result = runner.run(source_path=source, live=False)

    assert result["status"] == "dry_run_retry_unavailable"
    assert result["eligible_count"] == 3
    assert result["retry_target_count"] == 3
    assert result["provider_called"] is False
    assert result["provider_factory_constructed"] is False
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_retry_unavailable_creates_lineage_and_resumes_without_duplicate_provider_call(tmp_path: Path) -> None:
    source = _copy_run_01(tmp_path)
    output = tmp_path / "retry.json"
    first_model = _CandidateModel(PUBLIC_BY_ID["case_13"]["candidate"])
    first = evidence.RetryUnavailableCohortRunner(ROOT).run(
        source_path=source,
        live=True,
        case_id="case_13",
        output_path=output,
        shadow_model=first_model,
        enforce_clean_tree=False,
    )

    record = first["observations"][0]
    source_record = json.loads(source.read_text(encoding="utf-8"))["observations"]
    original_id = next(item["observation"]["observation_id"] for item in source_record if item["observation"]["case_id"] == "case_13")
    assert record["observation"]["observation_id"] != original_id
    assert record["observation"]["supersedes"] == original_id
    evidence.validate_retry_evidence_bundle(first)
    digest_before = hashlib.sha256(source.read_bytes()).hexdigest()

    second_model = _CandidateModel(error=AssertionError("provider must not be called on retry resume"))
    resumed = evidence.RetryUnavailableCohortRunner(ROOT).run(
        source_path=source,
        live=True,
        case_id="case_13",
        resume=True,
        output_path=output,
        shadow_model=second_model,
        enforce_clean_tree=False,
    )
    assert second_model.calls == 0
    assert resumed["observations"] == first["observations"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest_before


def test_retry_validator_rejects_duplicate_supersede_and_non_unavailable_targets(tmp_path: Path) -> None:
    source = _copy_run_01(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["observations"][0]["observation"]["outcome"] = "PASS"
    record = payload["observations"][0]
    body = {
        "observation": record["observation"],
        "audit": record["audit"],
        "sanitization": record["sanitization"],
    }
    record["record_digest"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    source.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        evidence.RetryUnavailableCohortRunner(ROOT).run(
            source_path=source, live=False, case_id="case_01"
        )
    assert captured.value.code == "RETRY_TARGET_INELIGIBLE"


def test_live_mode_rejects_dirty_source_before_factory_or_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(evidence, "_dirty_paths", lambda _root: ("src/unauthorized.py",))
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return _CandidateModel(PUBLIC_BY_ID["case_13"]["candidate"])

    with pytest.raises(evidence.EvidenceRunnerError) as captured:
        evidence.ShadowEvidenceRunner(ROOT).run(
            live=True,
            case_id="case_13",
            output_path=tmp_path / "blocked.json",
            model_factory=factory,
        )
    assert captured.value.code == "LIVE_DIRTY_TREE"
    assert called is False
