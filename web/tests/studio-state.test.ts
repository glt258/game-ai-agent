import assert from "node:assert/strict";
import test from "node:test";

import {
  applyDraftEdit,
  buildValidationRequest,
  cloneDraft,
  collectValidationTargets,
  invalidateValidationOnEdit,
  isDraftDirty,
  validationStateAfterEdit,
  validationTarget,
} from "../features/character-studio/studio-state";
import type {CharacterDraft, CharacterGenerationRequest, ValidatorResult} from "../lib/api/types";

const request: CharacterGenerationRequest = {
  brief: "设计一个辅助角色。",
  hard_constraints: [],
  soft_preferences: [],
  forbidden_elements: [],
  desired_connections: [],
  request_id: "request_001",
};

const draft: CharacterDraft = {
  draft_id: "draft_001",
  status: "draft",
  name: "林澈",
  canonical_character_id: null,
  age: 23,
  age_range: "20-25",
  gender: "女性",
  faction_id: "faction_002",
  occupation: "研究生助理",
  social_role: "校园公开活动志愿者",
  combat_role_profile: {primary_role: "support", secondary_roles: []},
  design_pitch: "以观察帮助同伴。",
  personality: ["冷静", "谨慎"],
  background: "她在研究中心协助公开活动。",
  story_hook: "她会参与新的校园志愿活动。",
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

test("editing creates an independent dirty draft without mutating the generated draft", () => {
  const generated = cloneDraft(draft);
  const edited = applyDraftEdit(generated, {field: "background", value: "她开始记录每次活动的现场风险。"});

  assert.equal(generated.background, draft.background);
  assert.equal(edited.background, "她开始记录每次活动的现场风险。");
  assert.equal(isDraftDirty(generated, edited), true);
  assert.equal(isDraftDirty(generated, cloneDraft(generated)), false);
});

test("discard can restore a deep clone and editing invalidates prior validation", () => {
  const generated = cloneDraft(draft);
  const edited = applyDraftEdit(generated, {field: "personality", value: "冷静,谨慎,耐心"});
  const discarded = cloneDraft(generated);

  assert.deepEqual(discarded, generated);
  assert.equal(edited.personality.join("/"), "冷静/谨慎/耐心");
  assert.equal(invalidateValidationOnEdit(), "idle");
});

test("validation request contains only the original request context and edited draft", () => {
  const edited = applyDraftEdit(draft, {field: "name", value: "顾澄"});
  const payload = buildValidationRequest(request, edited);

  assert.deepEqual(payload, {request, draft: edited});
  assert.equal("validators" in payload, false);
  assert.equal("raw_data" in payload, false);
  assert.notEqual(payload.draft, edited);
  assert.notEqual(payload.request, request);
});

test("stable field paths and validator identities map findings without parsing human messages", () => {
  assert.deepEqual(validationTarget({name: "canon_checker", code: "UNSUPPORTED_CANON_CLAIM", field_path: "faction_id"}), {
    field: "faction_id",
    section: "identity",
  });
  assert.deepEqual(validationTarget({name: "evaluation_runner", code: null, field_path: null}), {
    field: null,
    section: "evaluation",
  });
  assert.deepEqual(validationTarget({name: "canon_checker", code: null, field_path: null}), {
    field: null,
    section: "canon",
  });
});

test("editing after validation marks the result stale and keeps field routing data-driven", () => {
  assert.equal(validationStateAfterEdit("passed"), "stale");
  assert.equal(validationStateAfterEdit("failed"), "stale");
  assert.equal(validationStateAfterEdit("validating"), "stale");
  assert.equal(validationStateAfterEdit("idle"), "idle");

  const findings: ValidatorResult[] = [
    {
      name: "request_alignment",
      status: "failed",
      code: "AFFILIATION_CONSTRAINT_UNSATISFIED",
      severity: "error",
      blocking: true,
      field_path: "draft.faction_id",
      message: "中文错误消息不参与字段路由。",
      evidence_ids: [],
    },
    {
      name: "identity_coherence",
      status: "failed",
      code: "IDENTITY_AFFILIATION_INCONSISTENT",
      severity: "error",
      blocking: true,
      field_path: "occupation",
      message: "另一个中文错误消息。",
      evidence_ids: [],
    },
    {
      name: "representation_completeness",
      status: "passed",
      code: null,
      severity: null,
      blocking: false,
      field_path: "background",
      message: "通过。",
      evidence_ids: [],
    },
  ];

  const targets = collectValidationTargets(findings);
  assert.equal(targets.fields.get("faction_id")?.[0]?.code, "AFFILIATION_CONSTRAINT_UNSATISFIED");
  assert.equal(targets.fields.get("occupation")?.[0]?.code, "IDENTITY_AFFILIATION_INCONSISTENT");
  assert.equal(targets.fields.has("background"), false);
  assert.equal(targets.sections.has("identity"), true);
});
