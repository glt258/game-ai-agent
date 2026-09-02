from __future__ import annotations

import json
from pathlib import Path

from character_intelligence.character_skill_projection import CharacterSkillDesignContext
from character_intelligence.hybrid_ir.playground import (
    build_playground_context,
    build_playground_evaluation_context,
    run_playground_context_pipeline,
)
from character_intelligence.hybrid_ir.runner import FakeProvider
from character_intelligence.skill_artifact import build_skill_design_artifact_from_pipeline_result
from combat_semantics import CombatRoleProfile

ROOT = Path(__file__).resolve().parents[1]


def _controlled_artifact(case_id: str, family: str, mode: str):
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "hybrid_final_coverage_v2_goldens.json").read_text(
            encoding="utf-8"
        )
    )[case_id]
    context = build_playground_context(family, mode, f"Controlled fixture: {case_id}")
    result = run_playground_context_pipeline(
        FakeProvider(fixture),
        context,
        build_playground_evaluation_context(family, mode),
        model="web-offline-fixture",
        language="zh-CN",
        repo_root=ROOT,
        invocation_id=f"controlled-{case_id}",
    )
    assert result.candidate and result.report and result.validated_ir and result.compiler_provenance
    return build_skill_design_artifact_from_pipeline_result(result)


def _context(name: str) -> CharacterSkillDesignContext:
    return CharacterSkillDesignContext(
        character_name=name,
        combat_role_profile=CombatRoleProfile(primary_role="support"),
        ability_concept="帮助队友完成现场处置。",
        design_pitch="将观察与协作转化为战斗作用。",
    )
