import assert from "node:assert/strict";
import test from "node:test";

import type {SkillPlaygroundResponse} from "../lib/api/types";
import {projectSkillPlanner} from "../features/skill-playground/planner-view";
import {PRIMARY_NAVIGATION} from "../lib/ui-labels";

function result(overrides: Partial<SkillPlaygroundResponse> = {}): SkillPlaygroundResponse {
  return {schema_version: "web-skill-playground/0.1", status: "completed", input: {family: "sub_dps", mode: "active", brief: "设计一个在队友行动后追加输出的技能。", constraints: ["只能影响敌方", "不引入新资源"]}, semantic_ir: {ability_name: "Echo Volley", mode: "active", role: "sub_dps", mechanic: {kind: "triggered", trigger: {actor: "ally", event: "action_completed", qualifier: null}, effect: {actor: "enemy", intent: "deal_follow_up_damage", description: "Deal follow-up damage."}}}, skillkit: {resources: [], states: [], summons: []}, evaluation: {outcome: "PASS", blocking: false, repair_allowed: false, findings: [], candidate_digest: "candidate", report_digest: "report", diagnostics: null}, pipeline: [], provider: {mode: "offline_fixture", called: true, outcome: "SUCCESS", transport_attempts: 1, latency_ms: 0}, evidence: {candidate_digest: "candidate"}, artifact_versions: null, artifact_compatibility: null, ...overrides};
}

test("PASS fixture projects a planner-readable Chinese summary and preserves technical data", () => {
  const view = projectSkillPlanner(result());
  assert.equal(view.abilityName, "Echo Volley"); assert.equal(view.role, "副输出 · 主动"); assert.equal(view.trigger, "友方 · 完成行动"); assert.equal(view.effect, "发动追加攻击"); assert.equal(view.target, "敌方"); assert.equal(view.resources, "未引入新的战斗资源"); assert.equal(view.status, "通过");
  assert.ok(view.requirements.some((item) => item.label === "不引入新资源")); assert.equal(view.technical.semanticIr?.ability_name, "Echo Volley"); assert.equal(view.technical.skillKit?.resources instanceof Array, true);
});

test("FAIL findings become safe planner explanations without losing technical codes", () => {
  const view = projectSkillPlanner(result({status: "failed", semantic_ir: {ability_name: "Broken Skill", role: "sub_dps", mode: "active"}, evaluation: {outcome: "FAIL", blocking: true, repair_allowed: false, findings: [{code: "MECHANIC_SKELETON_ABSENT", field_path: "/entries", blocking: true, repairable: false, evidence_refs: [], priority: 1}, {code: "ROLE_EFFECT_MISMATCH", field_path: "/role_evidence", blocking: false, repairable: false, evidence_refs: [], priority: 2}, {code: "SOME_FUTURE_FINDING", field_path: "/future", blocking: false, repairable: false, evidence_refs: [], priority: 3}], candidate_digest: "candidate", report_digest: "report", diagnostics: null}}));
  assert.equal(view.status, "未通过"); assert.deepEqual(view.findings.map((finding) => finding.title), ["缺少核心机制", "战斗定位与技能效果不匹配", "发现一项设计问题"]); assert.equal(view.findings[2]?.code, "SOME_FUTURE_FINDING"); assert.equal(view.findings[0]?.repairability, "需要重新生成");
});

test("unknown mechanic vocabulary falls back without throwing", () => {
  const view = projectSkillPlanner(result({semantic_ir: {ability_name: "Unknown", role: "future_role", mode: "future_mode", mechanic: {trigger: {actor: "future_actor", event: "future_event"}, effect: {actor: "future_target", intent: "future_intent"}}}}));
  assert.equal(view.role, "其他定位 · 其他模式"); assert.equal(view.trigger, "其他对象 · 其他事件"); assert.equal(view.effect, "产生其他效果"); assert.equal(view.target, "其他目标");
});

test("primary navigation uses the Chinese planner-facing labels", () => {
  assert.deepEqual(PRIMARY_NAVIGATION.map((item) => item.label), ["角色设计台", "已保存角色", "世界观资料", "角色资料库", "技能设计台"]);
});
