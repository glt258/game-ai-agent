"""Offline H1 pilot tests for the semantic-to-canonical SkillKit compiler."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from character_intelligence.compiler import (
    CompilerProvenanceResult,
    SemanticMappingRegistry,
    SkillKitCompilerError,
    compile_skill_semantic_ir,
    validate_reference_integrity,
)
from character_intelligence.semantic_ir import (
    SEMANTIC_IR_VERSION,
    SemanticEffect,
    SemanticFeedback,
    SemanticIRShapeError,
    SemanticIRValidationError,
    SemanticIRValidator,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SkillSemanticIR,
    parse_semantic_ir,
)
from character_skill.contract import parse_candidate
from character_skill.evaluation import evaluate
from character_skill.models import ProtocolSkillKitCandidate

FIXTURE = Path("evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json")


def _case_13_context() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return next(item["context"] for item in payload["cases"] if item["case_id"] == "case_13")


def _case_13_ir() -> SkillSemanticIR:
    return SkillSemanticIR(
        SEMANTIC_IR_VERSION,
        "Echo",
        "Echo resonance support",
        "active",
        "support",
        "core",
        SemanticMechanic(
            SemanticTrigger("ally", "action_completed"),
            SemanticEffect("self", "enable_ally", "Enable the ally after completion."),
            SemanticFeedback(
                "effect_resolved",
                "enables",
                SemanticTrigger("self", "feedback_received"),
                SemanticEffect("self", "enable_ally", "Continue the resonance."),
            ),
        ),
        SemanticRolePath(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("ally", "enable_ally", "Support an ally."),
        ),
    )


def _walk(value: object):
    yield value
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _shape_metrics(value: object) -> tuple[int, int, int]:
    objects = fields = max_depth = 0

    def visit(node: object, depth: int) -> None:
        nonlocal objects, fields, max_depth
        max_depth = max(max_depth, depth)
        if isinstance(node, dict):
            objects += 1
            fields += len(node)
            for child in node.values():
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)

    visit(value, 1)
    return objects, fields, max_depth


def test_h1_pipeline_is_legal_and_evaluator_passes() -> None:
    source = _case_13_ir()
    validated = SemanticIRValidator.validate(parse_semantic_ir(source.to_mapping()))
    result = compile_skill_semantic_ir(validated)

    assert isinstance(result, CompilerProvenanceResult)
    validate_reference_integrity(result.candidate)
    parsed = parse_candidate(result.candidate.to_mapping())
    assert isinstance(parsed, ProtocolSkillKitCandidate)
    report = evaluate(parsed, _case_13_context())
    assert report.outcome == "PASS"
    assert report.findings == ()
    assert report.repair_allowed is False
    assert result.provenance.entries
    assert result.provenance.digest


def test_ir_stays_mechanically_light_and_provenance_is_safe() -> None:
    mapping = _case_13_ir().to_mapping()
    objects, fields, depth = _shape_metrics(mapping)
    assert objects <= 15
    assert fields <= 35
    assert depth <= 7
    forbidden_keys = {"schema_version", "ability_id", "protocol_id", "effect_id"}
    assert not any(isinstance(key, str) and key in forbidden_keys for key in _walk(mapping))
    assert not any(isinstance(value, dict) and set(value) == {"kind", "id"} for value in _walk(mapping))

    result = compile_skill_semantic_ir(SemanticIRValidator.validate(_case_13_ir()))
    provenance = result.provenance.to_mapping()
    serialized = json.dumps(provenance, sort_keys=True)
    assert "provider" not in serialized
    assert "prompt" not in serialized
    assert '"description"' not in serialized


def test_compilation_is_deterministic_and_does_not_mutate_input() -> None:
    source = _case_13_ir()
    before = copy.deepcopy(source.to_mapping())
    validated = SemanticIRValidator.validate(source)
    first = compile_skill_semantic_ir(validated)
    second = compile_skill_semantic_ir(validated)
    assert first.candidate.canonical_json() == second.candidate.canonical_json()
    assert first.candidate_digest == second.candidate_digest
    assert first.provenance.to_mapping() == second.provenance.to_mapping()
    assert first.provenance.digest == second.provenance.digest
    assert first.semantic_ir_digest == source.digest
    assert source.to_mapping() == before


@pytest.mark.parametrize(
    ("field", "value"),
    [("mode", "unsupported"), ("role", "unsupported"), ("centrality", "unsupported")],
)
def test_validator_rejects_invalid_semantic_choices(field: str, value: str) -> None:
    payload = _case_13_ir().to_mapping()
    payload[field] = value
    ir = parse_semantic_ir(payload)
    with pytest.raises(SemanticIRValidationError) as error:
        SemanticIRValidator.validate(ir)
    assert error.value.code == "IR_INVALID"


def test_parser_rejects_missing_and_unknown_fields() -> None:
    payload = _case_13_ir().to_mapping()
    payload["mechanic"] = dict(payload["mechanic"])
    del payload["mechanic"]["trigger"]
    with pytest.raises(SemanticIRShapeError) as missing:
        parse_semantic_ir(payload)
    assert missing.value.code == "MISSING_FIELD"

    payload = _case_13_ir().to_mapping()
    payload["unexpected"] = True
    with pytest.raises(SemanticIRShapeError) as unknown:
        parse_semantic_ir(payload)
    assert unknown.value.code == "UNKNOWN_FIELD"


def test_validator_rejects_bad_feedback_wiring_and_unsupported_mapping() -> None:
    source = _case_13_ir()
    bad_feedback = replace(
        source.mechanic.feedback,
        response_trigger=SemanticTrigger("ally", "feedback_received"),
    )
    bad_source = replace(source, mechanic=replace(source.mechanic, feedback=bad_feedback))
    with pytest.raises(SemanticIRValidationError) as wiring:
        SemanticIRValidator.validate(bad_source)
    assert wiring.value.code == "IR_INVALID"

    unsupported = replace(source.mechanic.effect, intent="unknown_intent")
    unsupported_source = replace(source, mechanic=replace(source.mechanic, effect=unsupported))
    with pytest.raises(SemanticIRValidationError) as mapping:
        SemanticIRValidator.validate(unsupported_source)
    assert mapping.value.code == "UNSUPPORTED_SEMANTIC_MAPPING"


def test_compiler_fails_closed_for_missing_mapping_and_reference() -> None:
    validated = SemanticIRValidator.validate(_case_13_ir())
    empty_registry = SemanticMappingRegistry(effect_operations={})
    with pytest.raises(SkillKitCompilerError) as mapping:
        compile_skill_semantic_ir(validated, registry=empty_registry)
    assert mapping.value.code == "UNSUPPORTED_SEMANTIC_MAPPING"

    compiled = compile_skill_semantic_ir(validated).candidate
    broken_relation = replace(
        compiled.feedback_relations[0],
        target_protocol=replace(compiled.feedback_relations[0].target_protocol, id="missing/protocol"),
    )
    broken = replace(compiled, feedback_relations=(broken_relation,))
    with pytest.raises(SkillKitCompilerError) as reference:
        validate_reference_integrity(broken)
    assert reference.value.code == "REFERENCE_WIRING_FAILURE"
