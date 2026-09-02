import assert from "node:assert/strict";
import test from "node:test";

import {ApiClientError, apiClient} from "../lib/api/client";
import type {CharacterKitRoleCoverageResponse, CharacterSkillContextResponse, CharacterSkillDesignResponse, CharacterValidationRequest, CharacterValidationResponse, SavedCharacter, SavedCharacterListResponse, SavedCharacterSaveResponse, SkillPlaygroundResponse} from "../lib/api/types";

const skillResponse: SkillPlaygroundResponse = {
  schema_version: "web-skill-playground/0.1",
  status: "failed",
  input: {family: "support", mode: "active", brief: "中文辅助技能。", constraints: []},
  semantic_ir: null,
  skillkit: {schema_version: "skill-kit-candidate/0.1.1"},
  evaluation: {outcome: "FAIL", blocking: true, repair_allowed: false, findings: [], candidate_digest: null, report_digest: null, diagnostics: null},
  pipeline: [],
  provider: {mode: "offline_fixture", called: true, outcome: "SUCCESS", transport_attempts: 1, latency_ms: 0},
  evidence: {first_failure_layer: "EVALUATOR"},
  artifact_versions: null,
  artifact_compatibility: null,
};

const validationResponse: CharacterValidationResponse = {
  schema_version: "web-character-validation/0.1",
  status: "failed",
  request_id: "request_001",
  draft_id: "draft_001",
  validators: [{
    name: "canon_checker",
    status: "failed",
    code: "UNSUPPORTED_CANON_CLAIM",
    severity: "error",
    blocking: true,
    field_path: "faction_id",
    message: "The claim is not supported.",
    evidence_ids: [],
  }],
  canon: {
    status: "failed",
    checked_source_ids: [],
    summary: {errors: 1, warnings: 0, infos: 0},
    findings: [],
  },
  combat: {primary_role: "support", secondary_roles: []},
  pipeline: [
    {id: "input", label: "Edited Draft Input", status: "passed", detail: null},
    {id: "evaluation", label: "Evaluation", status: "passed", detail: null},
    {id: "canon", label: "Canon Check", status: "failed", detail: null},
    {id: "final", label: "Validation Result", status: "failed", detail: null},
  ],
  summary: {status: "failed", blocking: true, validator_count: 1, failed_count: 1, warning_count: 0},
};

const characterSkillResponse: CharacterSkillDesignResponse = {
  schema_version: "web-character-skill-design/0.1",
  status: "completed",
  source_context_fingerprint: "a".repeat(64),
  character_context_summary: {
    character_name: "林澈",
    combat_role_profile: {primary_role: "support", secondary_roles: []},
    ability_concept: "稳定有限范围内的物品位置。",
    design_pitch: "以观察帮助同伴。",
    skill_relevant_hard_constraints: [],
    skill_relevant_forbidden_elements: [],
    relevant_desired_connections: [],
    affiliation_context: null,
    projection_version: "character-skill-context/0.2",
  },
  skill_input: {family: "support", mode: "active", brief: "中文辅助技能。", constraints: []},
  semantic_ir: {ability_name: "Support Echo"},
  skillkit: {schema_version: "skill-kit-candidate/0.1.1"},
  evaluation: {outcome: "PASS", blocking: false, repair_allowed: false, findings: [], candidate_digest: "b".repeat(64), report_digest: "c".repeat(64), diagnostics: null},
  alignment: {status: "PASS", coverage: "primary", findings: [], blocking: false, summary: "Skill provides structured support evidence for the Character combat identity.", artifact_digest: "b".repeat(64), source_context_fingerprint: "a".repeat(64), skill_roles: ["support"], evidence: []},
  pipeline: [],
  artifact_digest: "b".repeat(64),
  freshness: "current",
  provider: {mode: "offline_fixture", called: true, outcome: "SUCCESS", transport_attempts: 1, latency_ms: 0},
  evidence: {candidate_digest: "b".repeat(64)},
  artifact_versions: {
    semantic_ir_schema_version: "semantic-skill-plan-ir/0.2.0",
    compiler_version: "skillkit-compiler/0.2.0",
    canonical_skillkit_schema_version: "skill-kit-candidate/0.1.1",
    skill_evaluator_version: "skill-kit-validator/0.1.1",
    character_alignment_version: "character-skill-alignment/0.1.0",
    character_context_projection_version: "character-skill-context/0.2",
  },
  artifact_compatibility: "CURRENT_COMPATIBLE",
};

const requestPayload: CharacterValidationRequest = {
  request: {
    brief: "设计一个辅助角色。",
    hard_constraints: [],
    soft_preferences: [],
    forbidden_elements: [],
    desired_connections: [],
    request_id: "request_001",
  },
  draft: {
    draft_id: "draft_001",
    status: "draft",
    name: "林澈",
    canonical_character_id: null,
    age: null,
    age_range: null,
    gender: null,
    faction_id: null,
    occupation: "研究生助理",
    social_role: "志愿者",
    combat_role_profile: {primary_role: "support", secondary_roles: []},
    design_pitch: "以观察帮助同伴。",
    personality: ["冷静"],
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
  },
};

test("validateCharacter returns a failed business result from HTTP 200", async () => {
  const originalFetch = globalThis.fetch;
  let capturedBody = "";
  globalThis.fetch = async (input, init) => {
    assert.equal(input, "/api/characters/validate");
    capturedBody = String(init?.body);
    return new Response(JSON.stringify(validationResponse), {status: 200, headers: {"Content-Type": "application/json"}});
  };

  try {
    const response = await apiClient.validateCharacter(requestPayload);
    assert.equal(response.status, "failed");
    assert.deepEqual(JSON.parse(capturedBody), requestPayload);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("validateCharacter parses a safe 422 error envelope", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    error: {
      code: "DRAFT_CONTRACT_INVALID",
      message: "Draft structure is invalid.",
      stage: "validation",
      retryable: false,
      details: {field: "age"},
      audit: null,
    },
  }), {status: 422, headers: {"Content-Type": "application/json"}});

  try {
    await assert.rejects(
      () => apiClient.validateCharacter(requestPayload),
      (error: unknown) => error instanceof ApiClientError
        && error.statusCode === 422
        && error.payload.error.code === "DRAFT_CONTRACT_INVALID"
        && error.payload.error.message === "Draft structure is invalid.",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("validateCharacter separates a network failure from a business validation failure", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("connection refused");
  };

  try {
    await assert.rejects(
      () => apiClient.validateCharacter(requestPayload),
      (error: unknown) => error instanceof ApiClientError
        && error.statusCode === 0
        && error.payload.error.code === "NETWORK_ERROR",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("validateCharacter rejects an invalid successful response as a contract error", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    schema_version: "web-character-validation/0.1",
    status: "passed",
  }), {status: 200, headers: {"Content-Type": "application/json"}});

  try {
    await assert.rejects(
      () => apiClient.validateCharacter(requestPayload),
      (error: unknown) => error instanceof ApiClientError
        && error.statusCode === 200
        && error.payload.error.code === "VALIDATION_RESPONSE_INVALID",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("runSkillPlayground preserves typed business failure responses", async () => {
  const originalFetch = globalThis.fetch;
  let capturedBody = "";
  globalThis.fetch = async (input, init) => {
    assert.equal(input, "/api/skills/playground/run");
    capturedBody = String(init?.body);
    return new Response(JSON.stringify(skillResponse), {status: 200, headers: {"Content-Type": "application/json"}});
  };
  const payload = {family: "support" as const, mode: "active" as const, brief: "中文辅助技能。", constraints: []};
  try {
    const response = await apiClient.runSkillPlayground(payload);
    assert.equal(response.status, "failed");
    assert.equal(response.evaluation.outcome, "FAIL");
    assert.deepEqual(JSON.parse(capturedBody), payload);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Character Skill context and design use dedicated typed endpoints", async () => {
  const originalFetch = globalThis.fetch;
  const contextResponse: CharacterSkillContextResponse = {
    schema_version: "web-character-skill-context/0.1",
    source_context_fingerprint: "a".repeat(64),
    character_context_summary: characterSkillResponse.character_context_summary,
  };
  const character = {request: requestPayload.request, draft: requestPayload.draft};
  const designPayload = {
    character,
    skill: characterSkillResponse.skill_input,
  };
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(String(input));
    if (input === "/api/characters/skill-context") {
      assert.deepEqual(JSON.parse(String(init?.body)), character);
      return new Response(JSON.stringify(contextResponse), {status: 200, headers: {"Content-Type": "application/json"}});
    }
    assert.equal(input, "/api/characters/skill-design");
    assert.deepEqual(JSON.parse(String(init?.body)), designPayload);
    return new Response(JSON.stringify(characterSkillResponse), {status: 200, headers: {"Content-Type": "application/json"}});
  };

  try {
    const context = await apiClient.getCharacterSkillContext(character);
    const result = await apiClient.runCharacterSkillDesign(designPayload);
    assert.equal(context.source_context_fingerprint, "a".repeat(64));
    assert.equal(result.artifact_digest, "b".repeat(64));
    assert.deepEqual(calls, ["/api/characters/skill-context", "/api/characters/skill-design"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("live job endpoints accept quickly and preserve the normal result contract", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(String(input));
    if (String(input) === "/api/skills/playground/jobs") {
      assert.equal(init?.method, "POST");
      return new Response(JSON.stringify({
        schema_version: "web-live-skill-job/0.1",
        job_id: "job_123",
        kind: "skill_playground",
        status: "PENDING",
        provider: "opencode_go",
        model: "deepseek-v4-pro",
        poll_after_ms: 1500,
      }), {status: 202, headers: {"Content-Type": "application/json"}});
    }
    return new Response(JSON.stringify({
      schema_version: "web-live-skill-job/0.1",
      job_id: "job_123",
      kind: "skill_playground",
      status: "SUCCEEDED",
      provider: "opencode_go",
      model: "deepseek-v4-pro",
      elapsed_ms: 1234,
      result: skillResponse,
      error: null,
    }), {status: 200, headers: {"Content-Type": "application/json"}});
  };

  try {
    const accepted = await apiClient.createSkillPlaygroundLiveJob({
      family: "support",
      mode: "active",
      brief: "中文实时辅助技能。",
      constraints: [],
      execution_mode: "live",
      provider: "opencode_go",
      model: "deepseek-v4-pro",
    });
    const result = await apiClient.getSkillPlaygroundLiveJob(accepted.job_id);
    assert.equal(accepted.status, "PENDING");
    assert.equal(result.status, "SUCCEEDED");
    assert.equal(result.result?.schema_version, "web-skill-playground/0.1");
    assert.deepEqual(calls, ["/api/skills/playground/jobs", "/api/skills/playground/jobs/job_123"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Character Kit role coverage client preserves typed semantic status and evidence", async () => {
  const originalFetch = globalThis.fetch;
  const response: CharacterKitRoleCoverageResponse = {
    schema_version: "web-character-kit-role-coverage/0.1",
    contract_version: "character-kit/0.1.0",
    kit_digest: "a".repeat(64),
    structural_validation: {status: "PASS", blocking: false, findings: []},
    role_coverage: {
      status: "PARTIAL",
      kit_digest: "a".repeat(64),
      evaluation_context_fingerprint: "b".repeat(64),
      evaluator_version: "character-kit-role-coverage-evaluator/0.1.0",
      coverage: {
        primary: {
          role: "support",
          supported: true,
          evidence: [{
            role: "support",
            association_id: "session-skill:primary:a",
            artifact_digest: "a".repeat(64),
            operation: "ally_enablement",
            artifact_paths: ["/entries/skill_01/effects/enable"],
            centrality: "core",
            family: "support",
            mode: "active",
          }],
        },
        secondary: [{role: "control", supported: false, evidence: []}],
        observed_roles: ["support"],
      },
      findings: [],
      report_digest: "c".repeat(64),
      blocking: false,
      summary: "Primary role covered.",
    },
  };
  const request = {
    schema_version: "web-character-kit-role-coverage/0.1" as const,
    kit: {
      contract_version: "character-kit/0.1.0" as const,
      placement_schema_version: "character-kit-placement/0.1.0" as const,
      associations: [],
    },
    combat_role_profile: {primary_role: "support" as const, secondary_roles: ["control" as const]},
  };
  globalThis.fetch = async (input, init) => {
    assert.equal(input, "/api/characters/character-kit/evaluate");
    assert.deepEqual(JSON.parse(String(init?.body)), request);
    return new Response(JSON.stringify(response), {status: 200, headers: {"Content-Type": "application/json"}});
  };

  try {
    const result = await apiClient.evaluateCharacterKitRoleCoverage(request);
    assert.equal(result.role_coverage.status, "PARTIAL");
    assert.equal(result.role_coverage.coverage.primary.evidence[0].operation, "ally_enablement");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

const savedCharacter: SavedCharacter = {
  character_id: "character_001",
  current_revision_id: "revision_001",
  current_kit_assignment_id: null,
  created_at: "2026-09-02T00:00:00Z",
  updated_at: "2026-09-02T00:00:00Z",
  revision: {revision_id: "revision_001", kind: "GENERATED", parent_revision_id: null, created_at: "2026-09-02T00:00:00Z", is_current: true},
  draft: requestPayload.draft,
  request: requestPayload.request,
  plan: null,
  associations: [],
  kit: null,
  derived: {freshness_by_association_id: {}, compatibility_by_association_id: {}, structural_validation: null},
  history: [],
};

test("Saved Character client keeps list/open/save endpoints typed", async () => {
  const originalFetch = globalThis.fetch;
  const payload = {
    schema_version: "web-saved-character-save/0.1" as const,
    request: savedCharacter.request,
    draft: savedCharacter.draft,
    plan: null,
    associations: [],
  };
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(`${init?.method}:${String(input)}`);
    if (String(input) === "/api/saved-characters" && init?.method === "GET") {
      const list: SavedCharacterListResponse = {schema_version: "web-saved-character-list/0.1", characters: [], total: 0};
      return new Response(JSON.stringify(list), {status: 200});
    }
    if (String(input) === "/api/saved-characters/character_001" && init?.method === "GET") {
      return new Response(JSON.stringify(savedCharacter), {status: 200});
    }
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), payload);
    const response: SavedCharacterSaveResponse = {schema_version: "web-saved-character-save/0.1", saved: savedCharacter};
    return new Response(JSON.stringify(response), {status: 201});
  };
  try {
    assert.equal((await apiClient.listSavedCharacters()).total, 0);
    assert.equal((await apiClient.openSavedCharacter("character_001")).character_id, "character_001");
    assert.equal((await apiClient.createSavedCharacter(payload)).saved.current_revision_id, "revision_001");
    assert.deepEqual(calls, [
      "GET:/api/saved-characters",
      "GET:/api/saved-characters/character_001",
      "POST:/api/saved-characters",
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
