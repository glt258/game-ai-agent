"""Character-context orchestration over the existing Skill application seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .character_skill_projection import CharacterSkillDesignContext
from .hybrid_ir.playground import (
    build_playground_context,
    build_playground_evaluation_context,
    resolve_family,
    run_playground_context_pipeline,
)
from .hybrid_ir.runner import FakePipelineResult, HybridProvider


@dataclass(frozen=True)
class CharacterSkillDesignInput:
    """Explicit user-owned Skill input kept separate from Character context."""

    family: str
    mode: str
    brief: str
    constraints: tuple[str, ...] = ()
    language: str = "auto"
    model: str = "web-offline-fixture"
    preset_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.brief, str) or not self.brief.strip():
            raise ValueError("brief must be non-empty")
        object.__setattr__(self, "brief", self.brief.strip())
        object.__setattr__(
            self,
            "constraints",
            tuple(item.strip() for item in self.constraints if item.strip()),
        )


@dataclass(frozen=True)
class CharacterSkillDesignExecution:
    context: CharacterSkillDesignContext
    skill_input: CharacterSkillDesignInput
    pipeline_result: FakePipelineResult


def _context_requirement(
    context: CharacterSkillDesignContext,
    skill_input: CharacterSkillDesignInput,
) -> str:
    profile = context.combat_role_profile.to_dict()
    lines = [
        "Character design context (authoritative seed, not a SkillKit):",
        f"Character name: {context.character_name}",
        f"Combat role profile: {profile}",
        f"Ability concept: {context.ability_concept}",
        f"Design pitch: {context.design_pitch}",
    ]
    if context.skill_relevant_hard_constraints:
        lines.append(
            "Character-derived hard constraints: "
            + "; ".join(context.skill_relevant_hard_constraints)
        )
    if context.skill_relevant_forbidden_elements:
        lines.append(
            "Character-derived forbidden elements: "
            + "; ".join(context.skill_relevant_forbidden_elements)
        )
    if context.relevant_desired_connections:
        lines.append(
            "Character-derived desired connections: "
            + "; ".join(context.relevant_desired_connections)
        )
    if context.affiliation_context is not None:
        affiliation = context.affiliation_context
        lines.append(
            f"Relevant affiliation context: {affiliation.name} ({affiliation.faction_id}) — "
            f"{affiliation.summary}"
        )
    lines.extend(["", "User Skill design intent:", skill_input.brief])
    if skill_input.constraints:
        lines.append("User Skill constraints: " + "; ".join(skill_input.constraints))
    return "\n".join(lines)


def run_character_skill_design(
    provider: HybridProvider,
    context: CharacterSkillDesignContext,
    skill_input: CharacterSkillDesignInput,
    *,
    repo_root: Path | str,
    invocation_id: str | None = None,
) -> CharacterSkillDesignExecution:
    """Run one explicit Character-context Skill design through the shared seam."""

    role, mode = resolve_family(skill_input.family, skill_input.mode)
    requirement = _context_requirement(context, skill_input)
    hybrid_context = build_playground_context(role, mode, requirement)
    evaluation_context = build_playground_evaluation_context(role, mode)
    result = run_playground_context_pipeline(
        provider,
        hybrid_context,
        evaluation_context,
        model=skill_input.model,
        language=skill_input.language,
        repo_root=repo_root,
        invocation_id=invocation_id,
    )
    return CharacterSkillDesignExecution(context, skill_input, result)


__all__ = [
    "CharacterSkillDesignExecution",
    "CharacterSkillDesignInput",
    "run_character_skill_design",
]
