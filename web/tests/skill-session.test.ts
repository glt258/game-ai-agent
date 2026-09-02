import assert from "node:assert/strict";
import test from "node:test";

import {buildCharacterKitEvaluationRequest, buildCharacterSkillAssociation, canAttachSkill, createRoleCoverageEvaluationCoordinator, orderedAssociations, skillFreshness} from "../features/character-studio/skill-session";
import type {CharacterSkillDesignResponse, CharacterSkillSlot, SkillArtifactEvaluation, SkillArtifactVersions} from "../lib/api/types";

const artifactVersions: SkillArtifactVersions = {
  semantic_ir_schema_version: "semantic-skill-plan-ir/0.2.0",
  compiler_version: "skillkit-compiler/0.2.0",
  canonical_skillkit_schema_version: "skill-kit-candidate/0.1.1",
  skill_evaluator_version: "skill-kit-validator/0.1.1",
  character_alignment_version: "character-skill-alignment/0.1.0",
  character_context_projection_version: "character-skill-context/0.2",
};

const evaluation: SkillArtifactEvaluation = {
  outcome: "PASS",
  blocking: false,
  repair_allowed: false,
  findings: [],
  candidate_digest: "b".repeat(64),
  context_digest: "d".repeat(64),
  report_digest: "c".repeat(64),
  base_digest: "b".repeat(64),
  finding_codes: [],
};

const alignment = {
  status: "PASS" as const,
  coverage: "primary" as const,
  findings: [],
  blocking: false,
  summary: "aligned",
  artifact_digest: "b".repeat(64),
  source_context_fingerprint: "a".repeat(64),
  skill_roles: ["support"],
  evidence: [],
};

const result: CharacterSkillDesignResponse = {
  schema_version: "web-character-skill-design/0.1",
  status: "completed",
  source_context_fingerprint: "a".repeat(64),
  character_context_summary: {
    character_name: "顾澄",
    combat_role_profile: {primary_role: "support", secondary_roles: []},
    ability_concept: "稳定现场。",
    design_pitch: "辅助控制。",
    skill_relevant_hard_constraints: [],
    skill_relevant_forbidden_elements: [],
    relevant_desired_connections: [],
    affiliation_context: null,
    projection_version: "character-skill-context/0.2",
  },
  skill_input: {family: "sub_dps", mode: "active", brief: "中文技能。", constraints: []},
  semantic_ir: {ability_name: "Support Echo"},
  skillkit: {schema_version: "skill-kit-candidate/0.1.1"},
  evaluation: {...evaluation, report_digest: evaluation.report_digest, diagnostics: null} as CharacterSkillDesignResponse["evaluation"],
  alignment,
  pipeline: [],
  artifact_digest: "b".repeat(64),
  freshness: "current",
  provider: {mode: "offline_fixture", called: true, outcome: "SUCCESS", transport_attempts: 1, latency_ms: 0},
  evidence: {},
  artifact_versions: artifactVersions,
  artifact_compatibility: "CURRENT_COMPATIBLE",
  artifact: {
    artifact_contract_version: "skill-design-artifact/0.1.0",
    identity: {artifact_digest: "b".repeat(64), canonical_schema_version: "skill-kit-candidate/0.1.1", artifact_kind: "skill_design"},
    versions: artifactVersions,
    semantic_source: {ir_version: "semantic-skill-plan-ir/0.2.0"},
    semantic_source_digest: "e".repeat(64),
    canonical_artifact: {schema_version: "skill-kit-candidate/0.1.1"},
    original_evaluation: evaluation,
    provenance: {compiler_provenance: {compiler_version: "skillkit-compiler/0.2.0", entries: []}, run_id: null, provider: "fixture", model: null},
  },
  binding: {
    binding_contract_version: "character-skill-artifact-binding/0.1.0",
    artifact_digest: "b".repeat(64),
    source_context_fingerprint: "a".repeat(64),
    alignment,
    alignment_version: "character-skill-alignment/0.1.0",
    character_context_projection_version: "character-skill-context/0.2",
  },
};

test("freshness compares backend fingerprints and keeps irrelevant edits current", () => {
  assert.equal(skillFreshness(result.source_context_fingerprint, result.source_context_fingerprint), "current");
  assert.equal(skillFreshness(result.source_context_fingerprint, "c".repeat(64)), "stale");
  assert.equal(skillFreshness(result.source_context_fingerprint, null), "current");
});

test("only a passing result with an artifact can be attached", () => {
  assert.equal(canAttachSkill(result), true);
  assert.equal(canAttachSkill({...result, alignment: {...result.alignment, status: "FAIL", blocking: true}}), false);
  assert.equal(canAttachSkill({...result, status: "failed"}), false);
  assert.equal(canAttachSkill({...result, evaluation: {...result.evaluation, outcome: "FAIL"}}), false);
  assert.equal(canAttachSkill({...result, freshness: "stale"}), false);
  assert.equal(canAttachSkill({...result, artifact_digest: null}), false);
});

test("association state stores the formal artifact/binding tuple and follows backend slot order", () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  const secondary: CharacterSkillSlot = {id: "secondary", order: 1, label: "Secondary", description: "Secondary", max_items: 1};
  const first = buildCharacterSkillAssociation(result, secondary);
  const second = buildCharacterSkillAssociation({...result, artifact_digest: "c".repeat(64)}, primary);

  assert.ok(first);
  assert.ok(second);
  assert.equal(first?.association_id, `session-skill:secondary:${"b".repeat(64)}`);
  assert.equal(first?.artifact.original_evaluation, result.artifact?.original_evaluation);
  assert.equal(first?.binding.alignment, result.binding?.alignment);
  assert.equal(first?.artifact_compatibility, result.artifact_compatibility);
  assert.equal("result" in (first ?? {}), false);
  assert.deepEqual(orderedAssociations([first!, second!]).map((item) => item.slot), ["primary", "secondary"]);
});

test("association construction stays blocked for stale or incompatible artifacts", () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  assert.equal(buildCharacterSkillAssociation({...result, freshness: "stale"}, primary), null);
  assert.equal(buildCharacterSkillAssociation({...result, artifact_compatibility: "REEVALUATION_RECOMMENDED"}, primary), null);
});

test("request builder transports formal associations without generating a Kit digest", () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  const secondary: CharacterSkillSlot = {id: "secondary", order: 1, label: "Secondary", description: "Secondary", max_items: 1};
  const first = buildCharacterSkillAssociation(result, secondary);
  const second = buildCharacterSkillAssociation({...result, artifact_digest: "c".repeat(64), artifact: {...result.artifact!, identity: {...result.artifact!.identity, artifact_digest: "c".repeat(64)}, original_evaluation: {...result.artifact!.original_evaluation, candidate_digest: "c".repeat(64), base_digest: "c".repeat(64)},}, binding: {...result.binding!, artifact_digest: "c".repeat(64), alignment: {...result.binding!.alignment, artifact_digest: "c".repeat(64)}},}, primary);
  assert.ok(first);
  assert.ok(second);
  const built = buildCharacterKitEvaluationRequest({primary_role: "support", secondary_roles: ["control"]}, [first!, second!]);
  assert.equal(built.ok, true);
  if (built.ok) {
    assert.equal(built.request.kit.kit_digest, undefined);
    assert.deepEqual(built.request.kit.associations.map((item) => item.slot), ["primary", "secondary"]);
  }
});

test("request builder fails closed when artifact or binding transport is missing", () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  const association = buildCharacterSkillAssociation(result, primary)!;
  assert.equal(buildCharacterKitEvaluationRequest({primary_role: "support", secondary_roles: []}, [{...association, artifact: undefined} as never]).ok, false);
  assert.equal(buildCharacterKitEvaluationRequest({primary_role: "support", secondary_roles: []}, [{...association, binding: undefined} as never]).ok, false);
});

test("role coverage coordinator ignores a late response from an older Kit revision", async () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  const association = buildCharacterSkillAssociation(result, primary)!;
  const responses: Array<(value: never) => void> = [];
  const states: string[] = [];
  const coordinator = createRoleCoverageEvaluationCoordinator(
    () => new Promise((resolve) => responses.push(resolve as (value: never) => void)),
    (state) => states.push(state.phase),
  );
  coordinator.evaluate({primary_role: "support", secondary_roles: []}, [association]);
  coordinator.evaluate({primary_role: "support", secondary_roles: ["control"]}, [association]);
  const newer = {
    kit_digest: "new",
    role_coverage: {kit_digest: "new", evaluation_context_fingerprint: "context"},
  } as never;
  responses[1](newer);
  responses[0]({kit_digest: "old"} as never);
  await Promise.resolve();
  assert.deepEqual(states, ["loading", "loading", "ready"]);
});

test("role coverage coordinator rejects a response whose Kit identity is inconsistent", async () => {
  const primary: CharacterSkillSlot = {id: "primary", order: 0, label: "Primary", description: "Primary", max_items: 1};
  const association = buildCharacterSkillAssociation(result, primary)!;
  const states: string[] = [];
  const coordinator = createRoleCoverageEvaluationCoordinator(
    async () => ({
      kit_digest: "top-level-kit",
      structural_validation: {status: "PASS", blocking: false, findings: []},
      role_coverage: {kit_digest: "nested-kit", evaluation_context_fingerprint: "context", status: "PASS"},
    } as never),
    (state) => states.push(state.phase),
  );

  coordinator.evaluate({primary_role: "support", secondary_roles: []}, [association]);
  await Promise.resolve();
  assert.deepEqual(states, ["loading", "error"]);
});
