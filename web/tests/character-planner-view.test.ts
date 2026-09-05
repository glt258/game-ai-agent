import assert from "node:assert/strict";
import test from "node:test";

import {characterGenderLabel, characterRoleLabel, projectCharacterPlanner, projectSavedCharacterDraft} from "../features/character-studio/character-planner-view";
import type {CharacterDraft, CharacterGenerationResponse} from "../lib/api/types";

const draft: CharacterDraft = {
  draft_id: "draft_001",
  status: "draft",
  name: "林澈",
  canonical_character_id: "canon_001",
  age: 23,
  age_range: "20-25岁",
  gender: "female",
  faction_id: "faction_002",
  occupation: "研究生助理",
  social_role: "校园志愿者",
  combat_role_profile: {primary_role: "support", secondary_roles: ["control"]},
  design_pitch: "以观察帮助同伴。",
  personality: ["冷静", "谨慎"],
  background: "她在研究中心协助公开活动。",
  story_hook: "她发现活动记录中有一段缺失。",
  relationships: [],
  ability_concept: "稳定有限范围内的物品位置。",
  knowledge_scope: "仅接触公开信息。",
  canon_basis: [],
  new_design_elements: [],
  open_questions: [],
  constraint_notes: [],
  story_link: null,
  proposed_new_content: [],
};

const response: CharacterGenerationResponse = {
  schema_version: "web-character-generation/0.1",
  status: "completed",
  request: {brief: "设计一个辅助角色。", hard_constraints: [], soft_preferences: [], forbidden_elements: [], desired_connections: [], request_id: "request_001"},
  draft,
  plan: null,
  combat: {combat_role_profile: draft.combat_role_profile, skill_shadow_available: false, skill_shadow_status: "not_available", skill_summary: "通过位置控制保护队友。", skill_evaluation: null},
  canon_basis: [{source_id: "world_001", supports: ["研究中心"], source_type: "world"}],
  validators: [
    {name: "evaluation_runner", status: "passed", code: null, severity: null, blocking: false, field_path: null, message: "PASS", evidence_ids: []},
    {name: "canon_checker", status: "failed", code: "UNSUPPORTED_CANON_CLAIM", severity: "error", blocking: true, field_path: "faction_id", message: "raw technical message", evidence_ids: ["world_001"]},
  ],
  repair: {repair_performed: false, repair_attempts: 0, status: "NO_REPAIR_NEEDED", repair_succeeded: true, changed_fields: [], initial_status: "passed", final_status: "passed", failure_code: null},
  model_invocations: [],
  pipeline: [
    {id: "evaluation", label: "Evaluation", status: "passed", detail: null},
    {id: "canon", label: "Canon", status: "failed", detail: null},
  ],
  audit: {request_id: "request_001", tool_rounds: 0, tool_calls: [], source_ids: [], reference_ids: [], normalized_fields: [], contract_recovery: {status: "ok", attempted: false, missing_required: [], unknown_fields: [], invalid_fields: [], recovered_fields: [], discarded_unknown_fields: []}},
  raw_data: {draft: {}, plan: null, generation_audit: {}, authoring_audit: {}},
};

test("planner projection keeps user-facing fields and demotes technical identity", () => {
  const projected = projectCharacterPlanner(response, "研究中心");

  assert.equal(projected.name, "林澈");
  assert.deepEqual(projected.identity, {gender: "女性", age: "23 岁", ageRange: "20-25岁", occupation: "研究生助理", socialRole: "校园志愿者", affiliation: "研究中心"});
  assert.equal(projected.role, "辅助");
  assert.deepEqual(projected.secondaryRoles, ["控制"]);
  assert.equal(projected.evaluationStatus, "通过");
  assert.equal(projected.canonStatus, "未通过");
  assert.equal(projected.repairStatus, "无需修正");
  assert.deepEqual(projected.findings[0], {title: "世界观依据不足", detail: "请在技术详情中查看原始检查说明。", code: "UNSUPPORTED_CANON_CLAIM"});
  assert.equal("draft_id" in projected, false);
  assert.equal("raw_data" in projected, false);
});

test("planner labels unknown enums and saved drafts with honest fallbacks", () => {
  assert.equal(characterRoleLabel("future_role"), "其他定位");
  assert.equal(characterGenderLabel("future_gender"), "未说明");

  const projected = projectSavedCharacterDraft({...draft, age: null, gender: null}, null);
  assert.equal(projected.identity.age, "未说明");
  assert.equal(projected.identity.gender, "未说明");
  assert.equal(projected.identity.affiliation, "所属组织信息见世界观依据");
  assert.equal(projected.combatSummary, "当前结果未提供");
  assert.equal(projected.evaluationStatus, "未提供");
});
