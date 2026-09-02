import type {
  ApiError,
  CharacterSkillContextRequest,
  CharacterSkillContextResponse,
  CharacterSkillDesignRequest,
  CharacterSkillDesignResponse,
  CharacterSkillMetaResponse,
  CharacterKitValidationRequest,
  CharacterKitValidationResponse,
  CharacterKitRoleCoverageRequest,
  CharacterKitRoleCoverageResponse,
  CharacterGenerationRequest,
  CharacterGenerationResponse,
  CharacterValidationRequest,
  CharacterValidationResponse,
  CanonEntityDetailResponse,
  CanonEntityListResponse,
  CanonEntityType,
  HealthResponse,
  ReferenceCharacterDetailResponse,
  ReferenceCharacterListResponse,
  SkillFamily,
  SkillPlaygroundMetaResponse,
  SkillPlaygroundRequest,
  SkillPlaygroundResponse,
  LiveJobAccepted,
  LiveJobStatusResponse,
  SavedCharacter,
  SavedCharacterListResponse,
  SavedCharacterSaveRequest,
  SavedCharacterSaveResponse,
} from "./types";

const API_PREFIX = "/api";

export class ApiClientError extends Error {
  readonly payload: ApiError;
  readonly statusCode: number;

  constructor(payload: ApiError, statusCode: number) {
    super(payload.error.message);
    this.name = "ApiClientError";
    this.payload = payload;
    this.statusCode = statusCode;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isApiError(value: unknown): value is ApiError {
  if (!isRecord(value) || !isRecord(value.error)) {
    return false;
  }
  return typeof value.error.code === "string" && typeof value.error.message === "string";
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    value.status === "ok" &&
    typeof value.service === "string" &&
    typeof value.api_version === "string" &&
    typeof value.character_generation_available === "boolean"
  );
}

function isGenerationResponse(value: unknown): value is CharacterGenerationResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    value.schema_version === "web-character-generation/0.1" &&
    value.status === "completed" &&
    isRecord(value.draft) &&
    typeof value.draft.draft_id === "string" &&
    isRecord(value.combat) &&
    Array.isArray(value.validators) &&
    Array.isArray(value.pipeline) &&
    isRecord(value.repair) &&
    isRecord(value.audit)
  );
}

function isValidationResponse(value: unknown): value is CharacterValidationResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    value.schema_version === "web-character-validation/0.1" &&
    (value.status === "passed" || value.status === "failed") &&
    typeof value.request_id === "string" &&
    typeof value.draft_id === "string" &&
    Array.isArray(value.validators) &&
    isRecord(value.canon) &&
    Array.isArray(value.pipeline) &&
    isRecord(value.summary)
  );
}

function isCharacterSkillContextResponse(value: unknown): value is CharacterSkillContextResponse {
  if (!isRecord(value) || value.schema_version !== "web-character-skill-context/0.1" || typeof value.source_context_fingerprint !== "string" || !isRecord(value.character_context_summary)) {
    return false;
  }
  const summary = value.character_context_summary;
  return typeof summary.character_name === "string"
    && isRecord(summary.combat_role_profile)
    && typeof summary.ability_concept === "string"
    && typeof summary.design_pitch === "string"
    && Array.isArray(summary.skill_relevant_hard_constraints)
    && Array.isArray(summary.skill_relevant_forbidden_elements)
    && Array.isArray(summary.relevant_desired_connections)
    && (summary.affiliation_context === null || isRecord(summary.affiliation_context))
    && typeof summary.projection_version === "string";
}

function isArtifactCompatibility(value: unknown): boolean {
  return value === "CURRENT_COMPATIBLE"
    || value === "REEVALUATION_RECOMMENDED"
    || value === "REALIGNMENT_RECOMMENDED"
    || value === "RECOMPILE_REQUIRED"
    || value === "UNSUPPORTED_VERSION"
    || value === "CONTEXT_PROJECTION_DRIFT";
}

function isArtifactVersions(value: unknown): boolean {
  return isRecord(value)
    && typeof value.semantic_ir_schema_version === "string"
    && typeof value.compiler_version === "string"
    && typeof value.canonical_skillkit_schema_version === "string"
    && typeof value.skill_evaluator_version === "string"
    && (value.character_alignment_version === null || typeof value.character_alignment_version === "string")
    && (value.character_context_projection_version === null || typeof value.character_context_projection_version === "string");
}

function isArtifactMetadata(value: Record<string, unknown>): boolean {
  return (value.artifact_versions === null && value.artifact_compatibility === null)
    || (isArtifactVersions(value.artifact_versions) && isArtifactCompatibility(value.artifact_compatibility));
}

function isSkillDesignArtifactTransport(value: unknown): boolean {
  if (!isRecord(value) || typeof value.artifact_contract_version !== "string" || !isRecord(value.identity) || !isArtifactVersions(value.versions) || !isRecord(value.semantic_source) || typeof value.semantic_source_digest !== "string" || !isRecord(value.canonical_artifact) || !isRecord(value.original_evaluation) || !isRecord(value.provenance)) {
    return false;
  }
  return typeof value.identity.artifact_digest === "string"
    && typeof value.identity.canonical_schema_version === "string"
    && value.identity.artifact_kind === "skill_design"
    && (value.original_evaluation.outcome === "PASS" || value.original_evaluation.outcome === "REPAIR" || value.original_evaluation.outcome === "FAIL")
    && Array.isArray(value.original_evaluation.findings)
    && typeof value.provenance.compiler_provenance === "object";
}

function isCharacterSkillArtifactBinding(value: unknown): boolean {
  return isRecord(value)
    && typeof value.binding_contract_version === "string"
    && typeof value.artifact_digest === "string"
    && typeof value.source_context_fingerprint === "string"
    && isRecord(value.alignment)
    && typeof value.alignment.status === "string"
    && typeof value.alignment_version === "string"
    && typeof value.character_context_projection_version === "string";
}

function isCharacterSkillDesignResponse(value: unknown): value is CharacterSkillDesignResponse {
  return isRecord(value)
    && value.schema_version === "web-character-skill-design/0.1"
    && (value.status === "completed" || value.status === "failed")
    && typeof value.source_context_fingerprint === "string"
    && isRecord(value.character_context_summary)
    && isRecord(value.skill_input)
    && isRecord(value.evaluation)
    && isRecord(value.alignment)
    && (value.alignment.status === "PASS" || value.alignment.status === "FAIL" || value.alignment.status === "PARTIAL" || value.alignment.status === "NOT_EVALUATED")
    && Array.isArray(value.alignment.findings)
    && typeof value.alignment.summary === "string"
    && Array.isArray(value.pipeline)
    && isRecord(value.provider)
    && isRecord(value.evidence)
    && (value.freshness === "current" || value.freshness === "stale")
    && (value.artifact_digest === null || typeof value.artifact_digest === "string")
    && (value.artifact === undefined || value.artifact === null || isSkillDesignArtifactTransport(value.artifact))
    && (value.binding === undefined || value.binding === null || isCharacterSkillArtifactBinding(value.binding))
    && isArtifactMetadata(value);
}

function isSkillSlot(value: unknown): value is CharacterSkillMetaResponse["slots"][number]["id"] {
  return value === "primary" || value === "secondary" || value === "passive" || value === "utility";
}

function isCharacterSkillMetaResponse(value: unknown): value is CharacterSkillMetaResponse {
  return isRecord(value)
    && value.schema_version === "web-character-skill-meta/0.1"
    && Array.isArray(value.slots)
    && value.slots.every((item) => isRecord(item)
      && isSkillSlot(item.id)
      && typeof item.order === "number"
      && typeof item.label === "string"
      && typeof item.description === "string"
      && (typeof item.max_items === "number" || item.max_items === null));
}

function isCharacterKitValidationResponse(value: unknown): value is CharacterKitValidationResponse {
  return isRecord(value)
    && value.schema_version === "web-character-kit-validation/0.1"
    && typeof value.contract_version === "string"
    && Array.isArray(value.associations)
    && typeof value.kit_digest === "string"
    && isRecord(value.structural_validation)
    && (value.structural_validation.status === "PASS" || value.structural_validation.status === "FAIL")
    && typeof value.structural_validation.blocking === "boolean"
    && Array.isArray(value.structural_validation.findings)
    && value.structural_validation.findings.every((item) => isRecord(item)
      && typeof item.code === "string"
      && typeof item.field_path === "string"
      && typeof item.message === "string"
      && typeof item.blocking === "boolean");
}

function isCharacterKitRoleCoverageEvidence(value: unknown): boolean {
  return isRecord(value)
    && typeof value.role === "string"
    && typeof value.association_id === "string"
    && typeof value.artifact_digest === "string"
    && typeof value.operation === "string"
    && Array.isArray(value.artifact_paths)
    && value.artifact_paths.every((item) => typeof item === "string")
    && (value.centrality === null || typeof value.centrality === "string")
    && typeof value.family === "string"
    && typeof value.mode === "string";
}

function isCharacterKitRoleCoverageItem(value: unknown): boolean {
  return isRecord(value)
    && typeof value.role === "string"
    && typeof value.supported === "boolean"
    && Array.isArray(value.evidence)
    && value.evidence.every(isCharacterKitRoleCoverageEvidence);
}

function isCharacterKitRoleCoverageResponse(value: unknown): value is CharacterKitRoleCoverageResponse {
  if (!isRecord(value)
    || value.schema_version !== "web-character-kit-role-coverage/0.1"
    || typeof value.contract_version !== "string"
    || typeof value.kit_digest !== "string"
    || !isRecord(value.structural_validation)
    || (value.structural_validation.status !== "PASS" && value.structural_validation.status !== "FAIL")
    || typeof value.structural_validation.blocking !== "boolean"
    || !Array.isArray(value.structural_validation.findings)
    || !isRecord(value.role_coverage)) {
    return false;
  }
  const coverage = value.role_coverage.coverage;
  return (value.role_coverage.status === "PASS"
      || value.role_coverage.status === "PARTIAL"
      || value.role_coverage.status === "FAIL"
      || value.role_coverage.status === "NOT_EVALUATED")
    && typeof value.role_coverage.kit_digest === "string"
    && typeof value.role_coverage.evaluation_context_fingerprint === "string"
    && typeof value.role_coverage.evaluator_version === "string"
    && typeof value.role_coverage.report_digest === "string"
    && typeof value.role_coverage.blocking === "boolean"
    && typeof value.role_coverage.summary === "string"
    && isRecord(coverage)
    && isCharacterKitRoleCoverageItem(coverage.primary)
    && Array.isArray(coverage.secondary)
    && coverage.secondary.every(isCharacterKitRoleCoverageItem)
    && Array.isArray(coverage.observed_roles)
    && coverage.observed_roles.every((item) => typeof item === "string")
    && Array.isArray(value.role_coverage.findings)
    && value.role_coverage.findings.every((item) => isRecord(item)
      && typeof item.code === "string"
      && (item.kind === "supporting_evidence" || item.kind === "missing_evidence" || item.kind === "direct_contradiction" || item.kind === "not_evaluated")
      && typeof item.blocking === "boolean"
      && (item.character_role === null || typeof item.character_role === "string")
      && Array.isArray(item.artifact_evidence)
      && item.artifact_evidence.every(isCharacterKitRoleCoverageEvidence)
      && Array.isArray(item.artifact_digests)
      && item.artifact_digests.every((digest) => typeof digest === "string")
      && typeof item.field_path === "string"
      && typeof item.message === "string");
}

function isReferenceListResponse(value: unknown): value is ReferenceCharacterListResponse {
  if (!isRecord(value) || value.schema_version !== "web-reference-character-list/0.1" || !Array.isArray(value.characters) || typeof value.total !== "number") {
    return false;
  }
  return value.characters.every((item) => isRecord(item)
    && item.schema_version === "web-reference-character-summary/0.1"
    && typeof item.reference_id === "string"
    && typeof item.display_name === "string"
    && typeof item.game_name === "string"
    && Array.isArray(item.combat_roles)
    && isRecord(item.availability));
}

function isReferenceDetailResponse(value: unknown): value is ReferenceCharacterDetailResponse {
  return isRecord(value)
    && value.schema_version === "web-reference-character/0.1"
    && typeof value.reference_id === "string"
    && isRecord(value.identity)
    && typeof value.identity.canonical_name === "string"
    && isRecord(value.facts)
    && isRecord(value.facts.narrative)
    && Array.isArray(value.abilities)
    && (value.combat_analysis === null || isRecord(value.combat_analysis))
    && Array.isArray(value.sources)
    && isRecord(value.metadata);
}

function isCanonEntityType(value: unknown): value is CanonEntityType {
  return value === "faction" || value === "lore" || value === "character" || value === "project" || value === "case" || value === "incident" || value === "story";
}

function isCanonListResponse(value: unknown): value is CanonEntityListResponse {
  if (!isRecord(value) || value.schema_version !== "web-canon-entity-list/0.1" || !Array.isArray(value.entities) || !Array.isArray(value.entity_types) || typeof value.total !== "number") {
    return false;
  }
  return value.entity_types.every(isCanonEntityType) && value.entities.every((item) => isRecord(item)
    && typeof item.entity_id === "string"
    && isCanonEntityType(item.entity_type)
    && typeof item.name === "string"
    && Array.isArray(item.aliases)
    && Array.isArray(item.tags)
    && typeof item.summary === "string"
    && typeof item.relation_count === "number"
    && item.visibility === "public");
}

function isCanonDetailResponse(value: unknown): value is CanonEntityDetailResponse {
  return isRecord(value)
    && value.schema_version === "web-canon-entity/0.1"
    && typeof value.entity_id === "string"
    && isCanonEntityType(value.entity_type)
    && typeof value.name === "string"
    && isRecord(value.sections)
    && Array.isArray(value.relationships)
    && Array.isArray(value.provenance);
}

function isSkillFamily(value: unknown): value is SkillFamily {
  return value === "main_dps" || value === "sub_dps" || value === "support" || value === "healer"
    || value === "control" || value === "defense" || value === "basic_passive";
}

function isSkillMetaResponse(value: unknown): value is SkillPlaygroundMetaResponse {
  return isRecord(value)
    && value.schema_version === "web-skill-playground-meta/0.1"
    && Array.isArray(value.families)
    && value.families.every((item) => isRecord(item) && isSkillFamily(item.id) && typeof item.label === "string")
    && Array.isArray(value.modes)
    && value.modes.every((item) => item === "active" || item === "passive" || item === "reaction")
    && Array.isArray(value.examples)
    && value.examples.every((item) => typeof item === "string");
}

function isSkillPlaygroundResponse(value: unknown): value is SkillPlaygroundResponse {
  return isRecord(value)
    && value.schema_version === "web-skill-playground/0.1"
    && (value.status === "completed" || value.status === "failed")
    && isRecord(value.input)
    && isSkillFamily(value.input.family)
    && typeof value.input.mode === "string"
    && typeof value.input.brief === "string"
    && Array.isArray(value.pipeline)
    && isRecord(value.evaluation)
    && typeof value.evaluation.outcome === "string"
    && isRecord(value.provider)
    && isRecord(value.evidence)
    && isArtifactMetadata(value);
}

function isLiveJobAccepted(value: unknown): value is LiveJobAccepted {
  return isRecord(value)
    && value.schema_version === "web-live-skill-job/0.1"
    && typeof value.job_id === "string"
    && (value.kind === "skill_playground" || value.kind === "character_skill_design")
    && (value.status === "PENDING" || value.status === "RUNNING" || value.status === "SUCCEEDED" || value.status === "FAILED")
    && typeof value.provider === "string"
    && typeof value.model === "string"
    && typeof value.poll_after_ms === "number";
}

function isApiErrorBody(value: unknown): value is ApiError["error"] {
  return isRecord(value)
    && typeof value.code === "string"
    && typeof value.message === "string"
    && typeof value.retryable === "boolean"
    && isRecord(value.details);
}

function isLiveJobStatusResponse(value: unknown): value is LiveJobStatusResponse {
  if (!isRecord(value)
    || value.schema_version !== "web-live-skill-job/0.1"
    || typeof value.job_id !== "string"
    || (value.kind !== "skill_playground" && value.kind !== "character_skill_design")
    || (value.status !== "PENDING" && value.status !== "RUNNING" && value.status !== "SUCCEEDED" && value.status !== "FAILED")
    || typeof value.provider !== "string"
    || typeof value.model !== "string"
    || typeof value.elapsed_ms !== "number"
    || (value.error !== null && !isApiErrorBody(value.error))) {
    return false;
  }
  if (value.result === null) {
    return value.status !== "SUCCEEDED";
  }
  return value.kind === "skill_playground"
    ? isSkillPlaygroundResponse(value.result)
    : isCharacterSkillDesignResponse(value.result);
}

function isSavedCharacterSummary(value: unknown): boolean {
  return isRecord(value)
    && typeof value.character_id === "string"
    && typeof value.display_name === "string"
    && typeof value.current_revision_id === "string"
    && (value.revision_kind === "GENERATED" || value.revision_kind === "EDITED")
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string"
    && typeof value.has_kit === "boolean"
    && typeof value.skill_count === "number";
}

function isSavedCharacter(value: unknown): value is SavedCharacter {
  return isRecord(value)
    && typeof value.character_id === "string"
    && typeof value.current_revision_id === "string"
    && (typeof value.current_kit_assignment_id === "string" || value.current_kit_assignment_id === null)
    && isRecord(value.draft)
    && isRecord(value.request)
    && Array.isArray(value.associations)
    && isRecord(value.derived)
    && Array.isArray(value.history);
}

function isSavedCharacterListResponse(value: unknown): value is SavedCharacterListResponse {
  return isRecord(value)
    && value.schema_version === "web-saved-character-list/0.1"
    && typeof value.total === "number"
    && Array.isArray(value.characters)
    && value.characters.every(isSavedCharacterSummary);
}

function isSavedCharacterSaveResponse(value: unknown): value is SavedCharacterSaveResponse {
  return isRecord(value)
    && value.schema_version === "web-saved-character-save/0.1"
    && isSavedCharacter(value.saved);
}

async function request<T>(
  path: string,
  init: RequestInit,
  guard: (value: unknown) => value is T,
  invalidResponseCode: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
  } catch {
    if (init.signal?.aborted) {
      throw new ApiClientError(
        {
          error: {
            code: "CLIENT_ABORTED",
            message: "The live request was cancelled.",
            stage: "client",
            retryable: false,
            details: {},
            audit: null,
          },
        },
        0,
      );
    }
    throw new ApiClientError(
      {
        error: {
          code: "NETWORK_ERROR",
          message: "The backend could not be reached.",
          stage: "network",
          retryable: true,
          details: {},
          audit: null,
        },
      },
      0,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const payload: ApiError = isApiError(body)
      ? body
      : {
          error: {
            code: "HTTP_ERROR",
            message: "The backend returned an unexpected error.",
            stage: "http",
            retryable: response.status >= 500,
            details: {},
            audit: null,
          },
        };
    throw new ApiClientError(payload, response.status);
  }

  if (!guard(body)) {
    throw new ApiClientError(
      {
        error: {
          code: invalidResponseCode,
          message: "The backend response did not match the frozen Web contract.",
          stage: "contract",
          retryable: false,
          details: {},
          audit: null,
        },
      },
      response.status,
    );
  }
  return body;
}

export const apiClient = {
  getHealth(): Promise<HealthResponse> {
    return request("/system/health", {method: "GET"}, isHealthResponse, "HEALTH_RESPONSE_INVALID");
  },

  generateCharacter(payload: CharacterGenerationRequest): Promise<CharacterGenerationResponse> {
    return request(
      "/characters/generate",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      isGenerationResponse,
      "GENERATION_RESPONSE_INVALID",
    );
  },

  validateCharacter(payload: CharacterValidationRequest): Promise<CharacterValidationResponse> {
    return request(
      "/characters/validate",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      isValidationResponse,
      "VALIDATION_RESPONSE_INVALID",
    );
  },

  getCharacterSkillContext(payload: CharacterSkillContextRequest): Promise<CharacterSkillContextResponse> {
    return request(
      "/characters/skill-context",
      {method: "POST", body: JSON.stringify(payload)},
      isCharacterSkillContextResponse,
      "CHARACTER_SKILL_CONTEXT_RESPONSE_INVALID",
    );
  },

  runCharacterSkillDesign(payload: CharacterSkillDesignRequest): Promise<CharacterSkillDesignResponse> {
    return request(
      "/characters/skill-design",
      {method: "POST", body: JSON.stringify(payload)},
      isCharacterSkillDesignResponse,
      "CHARACTER_SKILL_DESIGN_RESPONSE_INVALID",
    );
  },

  createSkillPlaygroundLiveJob(payload: SkillPlaygroundRequest, signal?: AbortSignal): Promise<LiveJobAccepted> {
    return request(
      "/skills/playground/jobs",
      {method: "POST", body: JSON.stringify(payload), signal},
      isLiveJobAccepted,
      "LIVE_JOB_ACCEPTANCE_INVALID",
    );
  },

  getSkillPlaygroundLiveJob(jobId: string, signal?: AbortSignal): Promise<LiveJobStatusResponse> {
    return request(
      `/skills/playground/jobs/${encodeURIComponent(jobId)}`,
      {method: "GET", signal},
      isLiveJobStatusResponse,
      "LIVE_JOB_STATUS_INVALID",
    );
  },

  createCharacterSkillDesignLiveJob(payload: CharacterSkillDesignRequest, signal?: AbortSignal): Promise<LiveJobAccepted> {
    return request(
      "/characters/skill-design/jobs",
      {method: "POST", body: JSON.stringify(payload), signal},
      isLiveJobAccepted,
      "LIVE_JOB_ACCEPTANCE_INVALID",
    );
  },

  getCharacterSkillDesignLiveJob(jobId: string, signal?: AbortSignal): Promise<LiveJobStatusResponse> {
    return request(
      `/characters/skill-design/jobs/${encodeURIComponent(jobId)}`,
      {method: "GET", signal},
      isLiveJobStatusResponse,
      "LIVE_JOB_STATUS_INVALID",
    );
  },

  getCharacterSkillMeta(): Promise<CharacterSkillMetaResponse> {
    return request("/characters/skill-meta", {method: "GET"}, isCharacterSkillMetaResponse, "CHARACTER_SKILL_META_RESPONSE_INVALID");
  },

  validateCharacterKit(payload: CharacterKitValidationRequest): Promise<CharacterKitValidationResponse> {
    return request(
      "/characters/skill-kit/validate",
      {method: "POST", body: JSON.stringify(payload)},
      isCharacterKitValidationResponse,
      "CHARACTER_KIT_VALIDATION_RESPONSE_INVALID",
    );
  },

  evaluateCharacterKitRoleCoverage(payload: CharacterKitRoleCoverageRequest): Promise<CharacterKitRoleCoverageResponse> {
    return request(
      "/characters/character-kit/evaluate",
      {method: "POST", body: JSON.stringify(payload)},
      isCharacterKitRoleCoverageResponse,
      "CHARACTER_KIT_ROLE_COVERAGE_RESPONSE_INVALID",
    );
  },

  listReferenceCharacters(filters: {q?: string; ip?: string; combat_role?: string} = {}): Promise<ReferenceCharacterListResponse> {
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.ip) params.set("ip", filters.ip);
    if (filters.combat_role) params.set("combat_role", filters.combat_role);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/reference-characters${suffix}`, {method: "GET"}, isReferenceListResponse, "REFERENCE_CHARACTER_LIST_INVALID");
  },

  getReferenceCharacter(referenceId: string): Promise<ReferenceCharacterDetailResponse> {
    return request(`/reference-characters/${encodeURIComponent(referenceId)}`, {method: "GET"}, isReferenceDetailResponse, "REFERENCE_CHARACTER_DETAIL_INVALID");
  },

  listCanonEntities(filters: {q?: string; type?: CanonEntityType} = {}): Promise<CanonEntityListResponse> {
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.type) params.set("type", filters.type);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request(`/canon/entities${suffix}`, {method: "GET"}, isCanonListResponse, "CANON_ENTITY_LIST_INVALID");
  },

  getCanonEntity(entityId: string): Promise<CanonEntityDetailResponse> {
    return request(`/canon/entities/${encodeURIComponent(entityId)}`, {method: "GET"}, isCanonDetailResponse, "CANON_ENTITY_DETAIL_INVALID");
  },

  getSkillPlaygroundMeta(): Promise<SkillPlaygroundMetaResponse> {
    return request("/skills/playground/meta", {method: "GET"}, isSkillMetaResponse, "SKILL_META_RESPONSE_INVALID");
  },

  runSkillPlayground(payload: SkillPlaygroundRequest): Promise<SkillPlaygroundResponse> {
    return request(
      "/skills/playground/run",
      {method: "POST", body: JSON.stringify(payload)},
      isSkillPlaygroundResponse,
      "SKILL_PLAYGROUND_RESPONSE_INVALID",
    );
  },

  listSavedCharacters(): Promise<SavedCharacterListResponse> {
    return request("/saved-characters", {method: "GET"}, isSavedCharacterListResponse, "SAVED_CHARACTER_LIST_INVALID");
  },

  openSavedCharacter(characterId: string): Promise<SavedCharacter> {
    return request(`/saved-characters/${encodeURIComponent(characterId)}`, {method: "GET"}, isSavedCharacter, "SAVED_CHARACTER_RESPONSE_INVALID");
  },

  createSavedCharacter(payload: SavedCharacterSaveRequest): Promise<SavedCharacterSaveResponse> {
    return request("/saved-characters", {method: "POST", body: JSON.stringify(payload)}, isSavedCharacterSaveResponse, "SAVED_CHARACTER_SAVE_RESPONSE_INVALID");
  },

  updateSavedCharacter(characterId: string, payload: SavedCharacterSaveRequest): Promise<SavedCharacterSaveResponse> {
    return request(`/saved-characters/${encodeURIComponent(characterId)}`, {method: "PUT", body: JSON.stringify(payload)}, isSavedCharacterSaveResponse, "SAVED_CHARACTER_SAVE_RESPONSE_INVALID");
  },
};
