"""Offline proof that projected semantic domains match validator/compiler domains."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from character_intelligence.compiler import compile_skill_semantic_ir, validate_reference_integrity
from character_intelligence.hybrid_ir import (
    FakeProvider,
    HybridGenerationContext,
    project_semantic_enums,
    run_fake_pipeline,
)
from character_intelligence.semantic_ir import (
    SEMANTIC_IR_VERSION,
    SUPPORTED_SEMANTIC_ACTORS,
    SemanticEffect,
    SemanticFeedback,
    SemanticMechanic,
    SemanticRolePath,
    SemanticTrigger,
    SemanticIRValidator,
    SkillSemanticIR,
)
from character_skill.contract import (
    ABILITY_MODES,
    CENTRALITIES,
    FEEDBACK_EVENTS,
    FEEDBACK_OPERATIONS,
    SUBJECT_KINDS,
    TRIGGER_EVENTS,
    parse_candidate,
)
from combat_semantics import CANONICAL_COMBAT_ROLES

ROOT = Path(__file__).resolve().parents[1]


def _base_ir() -> SkillSemanticIR:
    return SkillSemanticIR(
        SEMANTIC_IR_VERSION,
        "Support",
        "Support action",
        "active",
        "support",
        "core",
        SemanticMechanic(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("ally", "enable_ally", "Enable an ally."),
            SemanticFeedback(
                "effect_resolved",
                "enables",
                SemanticTrigger("ally", "feedback_received"),
                SemanticEffect("ally", "enable_ally", "Continue enabling the ally."),
            ),
        ),
        SemanticRolePath(
            SemanticTrigger("self", "ability_invoked"),
            SemanticEffect("ally", "enable_ally", "Support an ally."),
        ),
    )


def _compile_and_parse(ir: SkillSemanticIR) -> None:
    compiled = compile_skill_semantic_ir(SemanticIRValidator.validate(ir))
    validate_reference_integrity(compiled.candidate)
    assert parse_candidate(compiled.candidate.to_mapping()) == compiled.candidate


@pytest.mark.parametrize("actor", sorted(SUPPORTED_SEMANTIC_ACTORS))
def test_every_supported_actor_validates_and_compiles(actor: str) -> None:
    source = _base_ir()
    mechanic = replace(
        source.mechanic,
        trigger=replace(source.mechanic.trigger, actor=actor),
        effect=replace(source.mechanic.effect, actor=actor),
        feedback=replace(
            source.mechanic.feedback,
            response_trigger=replace(source.mechanic.feedback.response_trigger, actor=actor),
            response_effect=replace(source.mechanic.feedback.response_effect, actor=actor),
        ),
    )
    role_path = replace(
        source.role_path,
        trigger=replace(source.role_path.trigger, actor=actor),
        effect=replace(source.role_path.effect, actor=actor),
    )
    _compile_and_parse(replace(source, mechanic=mechanic, role_path=role_path))


@pytest.mark.parametrize("event", sorted(TRIGGER_EVENTS))
def test_every_canonical_trigger_event_validates_and_compiles(event: str) -> None:
    source = _base_ir()
    mechanic = replace(
        source.mechanic,
        trigger=replace(source.mechanic.trigger, event=event),
        feedback=replace(
            source.mechanic.feedback,
            response_trigger=replace(source.mechanic.feedback.response_trigger, event=event),
        ),
    )
    role_path = replace(source.role_path, trigger=replace(source.role_path.trigger, event=event))
    _compile_and_parse(replace(source, mechanic=mechanic, role_path=role_path))


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("feedback_event", sorted(FEEDBACK_EVENTS)),
        ("feedback_relation", sorted(FEEDBACK_OPERATIONS)),
        ("mode", sorted(ABILITY_MODES)),
        ("role", list(CANONICAL_COMBAT_ROLES)),
        ("centrality", sorted(CENTRALITIES)),
    ],
)
def test_every_canonical_scalar_domain_validates_and_compiles(field: str, values: list[str]) -> None:
    for value in values:
        source = _base_ir()
        if field == "feedback_event":
            source = replace(
                source,
                mechanic=replace(source.mechanic, feedback=replace(source.mechanic.feedback, event=value)),
            )
        elif field == "feedback_relation":
            source = replace(
                source,
                mechanic=replace(source.mechanic, feedback=replace(source.mechanic.feedback, relation=value)),
            )
        else:
            source = replace(source, **{field: value})
        _compile_and_parse(source)


def test_authoritative_projection_preserves_structural_feedback_trigger() -> None:
    context = HybridGenerationContext(
        "Design a support ability.",
        contract_profile="aligned_v1",
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked",),
        allowed_feedback_events=("effect_resolved",),
        allowed_feedback_relations=("enables",),
        allowed_modes=("active",),
        allowed_roles=("support",),
        allowed_centralities=("core",),
    )
    assert project_semantic_enums(context).domain("trigger_event").values == (
        "ability_invoked",
        "feedback_received",
    )


def test_projected_domains_are_validator_domains_or_safe_subsets() -> None:
    projection = project_semantic_enums(HybridGenerationContext("generic skill"))
    assert set(projection.domain("actor").values) <= set(SUBJECT_KINDS - {"summon"})
    assert set(projection.domain("trigger_event").values) <= set(TRIGGER_EVENTS)
    assert set(projection.domain("feedback_event").values) <= set(FEEDBACK_EVENTS)
    assert set(projection.domain("feedback_relation").values) <= set(FEEDBACK_OPERATIONS)
    assert set(projection.domain("mode").values) <= set(ABILITY_MODES)
    assert set(projection.domain("role").values) <= set(CANONICAL_COMBAT_ROLES)
    assert set(projection.domain("centrality").values) <= set(CENTRALITIES)
    assert set(projection.domain("intent").values) == {"enable_ally"}


def test_invalid_semantic_value_is_safe_in_fake_pipeline() -> None:
    payload = _base_ir().to_mapping()
    payload["mechanic"]["feedback"]["event"] = "not_a_feedback_event"
    result = run_fake_pipeline(
        FakeProvider(payload),
        HybridGenerationContext("generic skill"),
        {"intent": {}, "combat_role_profile": {}, "reference_review_context": None},
        repo_root=ROOT,
    )
    assert result.evidence.first_failure_layer == "IR_VALIDATION"
    assert result.evidence.failure_code == "IR_INVALID_SEMANTIC_VALUE"
    assert "not_a_feedback_event" not in str(result.evidence.to_mapping())
