export type CharacterRole =
  | "main_dps"
  | "sub_dps"
  | "support"
  | "healer"
  | "control"
  | "defense";

export type SkillFamily = CharacterRole | "basic_passive";
export type SkillMode = "active" | "passive" | "reaction";
export type SkillLanguage = "auto" | "en" | "zh-CN";
export type SkillExecutionMode = "offline" | "live";
export type SkillProviderName = "deepseek" | "opencode_go";
export type SkillSlot = "primary" | "secondary" | "passive" | "utility";
export type ArtifactCompatibility =
  | "CURRENT_COMPATIBLE"
  | "REEVALUATION_RECOMMENDED"
  | "REALIGNMENT_RECOMMENDED"
  | "RECOMPILE_REQUIRED"
  | "UNSUPPORTED_VERSION"
  | "CONTEXT_PROJECTION_DRIFT";

export interface SkillPlaygroundRequest {
  family: SkillFamily;
  mode: SkillMode;
  brief: string;
  constraints: string[];
  language?: SkillLanguage;
  model?: string;
  preset_id?: string | null;
  execution_mode?: SkillExecutionMode;
  provider?: SkillProviderName;
}

export interface SkillFamilyOption {
  id: SkillFamily;
  label: string;
  description: string;
  role: string;
  default_mode: SkillMode;
}

export interface SkillPlaygroundMetaResponse {
  schema_version: "web-skill-playground-meta/0.1";
  families: SkillFamilyOption[];
  modes: SkillMode[];
  examples: string[];
  provider_mode: "offline_fixture" | "injected" | "unavailable";
}

export interface SkillFinding {
  code: string;
  field_path: string;
  blocking: boolean;
  repairable: boolean;
  evidence_refs: string[];
  priority: number;
}

export interface SkillEvaluation {
  outcome: "PASS" | "REPAIR" | "FAIL" | "NOT_RUN";
  blocking: boolean;
  repair_allowed: boolean;
  findings: SkillFinding[];
  candidate_digest: string | null;
  report_digest: string | null;
  diagnostics: Record<string, unknown> | null;
}

export interface SkillProvider {
  mode: "offline_fixture" | "injected" | "live" | "unavailable";
  called: boolean;
  outcome: string;
  transport_attempts: number;
  latency_ms: number | null;
}

export interface SkillArtifactVersions {
  semantic_ir_schema_version: string;
  compiler_version: string;
  canonical_skillkit_schema_version: string;
  skill_evaluator_version: string;
  character_alignment_version: string | null;
  character_context_projection_version: string | null;
}

export interface SkillPlaygroundResponse {
  schema_version: "web-skill-playground/0.1";
  status: "completed" | "failed";
  input: SkillPlaygroundRequest;
  semantic_ir: Record<string, unknown> | null;
  skillkit: Record<string, unknown> | null;
  evaluation: SkillEvaluation;
  pipeline: PipelineStep[];
  provider: SkillProvider;
  evidence: Record<string, unknown>;
  artifact_versions: SkillArtifactVersions | null;
  artifact_compatibility: ArtifactCompatibility | null;
}

export interface CharacterSkillContextRequest {
  request: CharacterGenerationRequest;
  draft: CharacterDraft;
  plan?: CharacterPlan | null;
}

export interface CharacterAffiliationContext {
  faction_id: string;
  name: string;
  faction_type: string;
  summary: string;
  typical_roles: string[];
  semantic_terms: string[];
  division_names: string[];
}

export interface CharacterSkillContextSummary {
  character_name: string;
  combat_role_profile: CombatRoleProfile;
  ability_concept: string;
  design_pitch: string;
  skill_relevant_hard_constraints: string[];
  skill_relevant_forbidden_elements: string[];
  relevant_desired_connections: string[];
  affiliation_context: CharacterAffiliationContext | null;
  projection_version: string;
}

export interface CharacterSkillContextResponse {
  schema_version: "web-character-skill-context/0.1";
  source_context_fingerprint: string;
  character_context_summary: CharacterSkillContextSummary;
}

export interface CharacterSkillDesignRequest {
  character: CharacterSkillContextRequest;
  skill: SkillPlaygroundRequest;
}

export interface CharacterSkillDesignResponse {
  schema_version: "web-character-skill-design/0.1";
  status: "completed" | "failed";
  source_context_fingerprint: string;
  character_context_summary: CharacterSkillContextSummary;
  skill_input: SkillPlaygroundRequest;
  semantic_ir: Record<string, unknown> | null;
  skillkit: Record<string, unknown> | null;
  evaluation: SkillEvaluation;
  alignment: CharacterSkillAlignmentResult;
  pipeline: PipelineStep[];
  artifact_digest: string | null;
  freshness: "current" | "stale";
  provider: SkillProvider;
  evidence: Record<string, unknown>;
  artifact_versions: SkillArtifactVersions | null;
  artifact_compatibility: ArtifactCompatibility | null;
  artifact?: SkillDesignArtifactTransport | null;
  binding?: CharacterSkillArtifactBinding | null;
}

export type LiveJobStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type LiveJobKind = "skill_playground" | "character_skill_design";

export interface LiveJobAccepted {
  schema_version: "web-live-skill-job/0.1";
  job_id: string;
  kind: LiveJobKind;
  status: LiveJobStatus;
  provider: string;
  model: string;
  poll_after_ms: number;
}

export interface LiveJobStatusResponse {
  schema_version: "web-live-skill-job/0.1";
  job_id: string;
  kind: LiveJobKind;
  status: LiveJobStatus;
  provider: string;
  model: string;
  elapsed_ms: number;
  result: SkillPlaygroundResponse | CharacterSkillDesignResponse | null;
  error: ApiErrorBody | null;
}

export interface CharacterSkillSlot {
  id: SkillSlot;
  order: number;
  label: string;
  description: string;
  max_items: number | null;
}

export interface CharacterSkillMetaResponse {
  schema_version: "web-character-skill-meta/0.1";
  slots: CharacterSkillSlot[];
}

export interface CharacterKitStructuralFinding {
  code: string;
  field_path: string;
  message: string;
  blocking: boolean;
}

export interface CharacterKitStructuralValidation {
  status: "PASS" | "FAIL";
  blocking: boolean;
  findings: CharacterKitStructuralFinding[];
}

export interface CharacterKitValidationRequest {
  schema_version: "web-character-kit-validation/0.1";
  kit: Record<string, unknown>;
}

export interface CharacterKitValidationResponse {
  schema_version: "web-character-kit-validation/0.1";
  contract_version: string;
  associations: Record<string, unknown>[];
  structural_validation: CharacterKitStructuralValidation;
  kit_digest: string;
}

export interface CharacterKitRoleCoverageRequest {
  schema_version: "web-character-kit-role-coverage/0.1";
  kit: CharacterKitEvaluationKit;
  combat_role_profile: CombatRoleProfile;
  current_skill_context_fingerprint?: string | null;
}

export interface CharacterKitEvaluationKit {
  contract_version: "character-kit/0.1.0";
  placement_schema_version: "character-kit-placement/0.1.0";
  associations: CharacterKitEvaluationAssociation[];
  kit_digest?: string | null;
}

export interface CharacterKitRoleCoverageEvidence {
  role: string;
  association_id: string;
  artifact_digest: string;
  operation: string;
  artifact_paths: string[];
  centrality: string | null;
  family: string;
  mode: string;
}

export interface CharacterKitRoleCoverageItem {
  role: string;
  supported: boolean;
  evidence: CharacterKitRoleCoverageEvidence[];
}

export interface CharacterKitCoverage {
  primary: CharacterKitRoleCoverageItem;
  secondary: CharacterKitRoleCoverageItem[];
  observed_roles: string[];
}

export interface CharacterKitEvaluationFinding {
  code: string;
  kind: "supporting_evidence" | "missing_evidence" | "direct_contradiction" | "not_evaluated";
  blocking: boolean;
  character_role: string | null;
  artifact_evidence: CharacterKitRoleCoverageEvidence[];
  artifact_digests: string[];
  field_path: string;
  message: string;
}

export interface CharacterKitRoleCoverage {
  status: "PASS" | "PARTIAL" | "FAIL" | "NOT_EVALUATED";
  kit_digest: string;
  evaluation_context_fingerprint: string;
  evaluator_version: string;
  coverage: CharacterKitCoverage;
  findings: CharacterKitEvaluationFinding[];
  report_digest: string;
  blocking: boolean;
  summary: string;
}

export interface CharacterKitRoleCoverageResponse {
  schema_version: "web-character-kit-role-coverage/0.1";
  contract_version: string;
  kit_digest: string;
  structural_validation: CharacterKitStructuralValidation;
  role_coverage: CharacterKitRoleCoverage;
}

export interface SkillArtifactIdentity {
  artifact_digest: string;
  canonical_schema_version: string;
  artifact_kind: "skill_design";
}

export interface CompilerProvenanceEntry {
  canonical_path: string;
  source_kind: string;
  source_path?: string;
  rule_id?: string;
}

export interface SkillArtifactProvenance {
  compiler_provenance: {
    compiler_version: string;
    entries: CompilerProvenanceEntry[];
  };
  run_id: string | null;
  provider: string | null;
  model: string | null;
}

export interface SkillArtifactFinding {
  code: string;
  field_path: string;
  blocking: boolean;
  repairable: boolean;
  evidence_refs: string[];
  authorized_paths: string[];
  priority: number;
}

export interface SkillArtifactEvaluation {
  outcome: "PASS" | "REPAIR" | "FAIL";
  blocking: boolean;
  repair_allowed: boolean;
  findings: SkillArtifactFinding[];
  candidate_digest: string;
  context_digest: string;
  report_digest: string;
  base_digest: string;
  finding_codes: string[];
}

export interface SkillDesignArtifactTransport {
  artifact_contract_version: string;
  identity: SkillArtifactIdentity;
  versions: SkillArtifactVersions;
  semantic_source: Record<string, unknown>;
  semantic_source_digest: string;
  canonical_artifact: Record<string, unknown>;
  original_evaluation: SkillArtifactEvaluation;
  provenance: SkillArtifactProvenance;
}

export interface CharacterSkillArtifactBinding {
  binding_contract_version: string;
  artifact_digest: string;
  source_context_fingerprint: string;
  alignment: CharacterSkillAlignmentResult;
  alignment_version: string;
  character_context_projection_version: string;
}

export interface CharacterSkillAssociation {
  association_id: string;
  artifact: SkillDesignArtifactTransport;
  binding: CharacterSkillArtifactBinding;
  artifact_compatibility: ArtifactCompatibility;
  slot: SkillSlot;
  order: number;
  family: SkillFamily;
  mode: SkillMode;
  display_summary: string;
}

export type CharacterKitEvaluationAssociation = Omit<CharacterSkillAssociation, "artifact_compatibility">;

export interface CharacterSkillEvidence {
  role: string;
  operation: string;
  family: string;
  mode: string;
  artifact_paths: string[];
  centrality: string | null;
}

export interface CharacterSkillAlignmentFinding {
  code: string;
  kind: "supporting_evidence" | "missing_evidence" | "direct_contradiction" | "not_evaluated";
  blocking: boolean;
  character_role: string | null;
  skill_evidence: CharacterSkillEvidence[];
  field_path: string;
  artifact_path: string | null;
  message: string;
}

export interface CharacterSkillAlignmentResult {
  status: "PASS" | "FAIL" | "PARTIAL" | "NOT_EVALUATED";
  coverage: "primary" | "secondary" | "none" | "not_evaluated";
  findings: CharacterSkillAlignmentFinding[];
  blocking: boolean;
  summary: string;
  artifact_digest: string | null;
  source_context_fingerprint: string;
  skill_roles: string[];
  evidence: CharacterSkillEvidence[];
}

export interface CombatRoleProfile {
  primary_role: CharacterRole | null;
  secondary_roles: CharacterRole[];
}

export interface CharacterGenerationRequest {
  brief: string;
  hard_constraints: string[];
  soft_preferences: string[];
  forbidden_elements: string[];
  desired_connections: string[];
  request_id?: string | null;
  combat_role_profile?: CombatRoleProfile | null;
}

export interface CanonBasis {
  source_id: string;
  supports: string[];
  source_type: string | null;
}

export interface Relationship {
  target_id: string | null;
  description: string | null;
  status: string | null;
  type: string | null;
}

export interface StoryLink {
  target_id: string;
  relation: string;
  status: string;
}

export interface CharacterDraft {
  draft_id: string;
  status: string;
  name: string;
  canonical_character_id: string | null;
  age: number | null;
  age_range: string | null;
  gender: string | null;
  faction_id: string | null;
  occupation: string;
  social_role: string;
  combat_role_profile: CombatRoleProfile;
  design_pitch: string;
  personality: string[];
  background: string;
  story_hook: string;
  relationships: Relationship[];
  ability_concept: string;
  knowledge_scope: string;
  canon_basis: CanonBasis[];
  new_design_elements: string[];
  open_questions: string[];
  constraint_notes: string[];
  story_link: StoryLink | null;
  proposed_new_content: string[];
}

export interface CharacterIntent {
  role_type: string;
  rarity: number | null;
  target_audience: string;
  personality_keywords: string[];
  design_goals: string[];
  forbidden_patterns: string[];
  element: string | null;
  raw_request: string;
  combat_role_profile: CombatRoleProfile;
}

export interface CharacterPlan {
  parsed_intent: CharacterIntent;
  combat_role_profile: CombatRoleProfile;
  generation_constraints: string[];
  recommended_traits: string[];
  expected_affiliation_id?: string | null;
  affiliation_context?: CharacterAffiliationContext | null;
}

export type ValidatorStatus = "passed" | "warning" | "failed" | "not_available";

export interface ValidatorResult {
  name: string;
  status: ValidatorStatus;
  code: string | null;
  severity: string | null;
  blocking: boolean | null;
  field_path: string | null;
  message: string;
  evidence_ids: string[];
}

export interface RepairSummary {
  repair_performed: boolean;
  repair_attempts: number;
  status: string;
  repair_succeeded: boolean;
  changed_fields: string[];
  initial_status: string;
  final_status: string;
  failure_code: string | null;
}

export interface PipelineStep {
  id: string;
  label: string;
  status: "passed" | "failed" | "repaired" | "skipped";
  detail: string | null;
}

export interface ModelUsage {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface ModelInvocation {
  provider: string;
  model: string;
  turn_number: number;
  outcome: string;
  latency_ms: number | null;
  retry_count: number;
  finish_reason: string | null;
  tool_call_count: number;
  usage: ModelUsage | null;
  purpose: string;
  provider_status_code: number | null;
  provider_retryable: boolean | null;
}

export interface ContractRecovery {
  status: string;
  attempted: boolean;
  missing_required: string[];
  unknown_fields: string[];
  invalid_fields: string[];
  recovered_fields: string[];
  discarded_unknown_fields: string[];
}

export interface ToolAudit {
  round: number;
  tool_name: string;
  result_status: string;
  source_ids: string[];
  denied_requested_ids: string[];
  resolver_reason_code: string | null;
}

export interface GenerationAudit {
  request_id: string;
  tool_rounds: number;
  tool_calls: ToolAudit[];
  source_ids: string[];
  reference_ids: string[];
  normalized_fields: string[];
  contract_recovery: ContractRecovery;
}

export interface Combat {
  combat_role_profile: CombatRoleProfile;
  skill_shadow_available: boolean;
  skill_shadow_status: string;
  skill_summary: string | null;
  skill_evaluation: Record<string, unknown> | null;
}

export interface RawCharacterResult {
  draft: Record<string, unknown>;
  plan: Record<string, unknown> | null;
  generation_audit: Record<string, unknown>;
  authoring_audit: Record<string, unknown>;
}

export interface CharacterGenerationResponse {
  schema_version: "web-character-generation/0.1";
  status: "completed";
  request: CharacterGenerationRequest;
  draft: CharacterDraft;
  plan: CharacterPlan | null;
  combat: Combat;
  canon_basis: CanonBasis[];
  validators: ValidatorResult[];
  repair: RepairSummary;
  model_invocations: ModelInvocation[];
  pipeline: PipelineStep[];
  audit: GenerationAudit;
  raw_data: RawCharacterResult;
}

export interface CharacterValidationRequest {
  request: CharacterGenerationRequest;
  draft: CharacterDraft;
}

export type ValidationStatus = "passed" | "failed";

export interface CanonValidationSummary {
  errors: number;
  warnings: number;
  infos: number;
}

export interface CanonValidation {
  status: "passed" | "warning" | "failed";
  checked_source_ids: string[];
  summary: CanonValidationSummary;
  findings: ValidatorResult[];
}

export interface ValidationSummary {
  status: ValidationStatus;
  blocking: boolean;
  validator_count: number;
  failed_count: number;
  warning_count: number;
}

export interface CharacterValidationResponse {
  schema_version: "web-character-validation/0.1";
  status: ValidationStatus;
  request_id: string;
  draft_id: string;
  validators: ValidatorResult[];
  canon: CanonValidation;
  combat: CombatRoleProfile;
  pipeline: PipelineStep[];
  summary: ValidationSummary;
}

export interface SavedCharacterRevision {
  revision_id: string;
  kind: "GENERATED" | "EDITED";
  parent_revision_id: string | null;
  created_at: string;
  is_current: boolean;
}

export interface SavedCharacterSummary {
  character_id: string;
  display_name: string;
  current_revision_id: string;
  revision_kind: "GENERATED" | "EDITED";
  created_at: string;
  updated_at: string;
  has_kit: boolean;
  skill_count: number;
}

export interface SavedCharacterHistorySummary {
  report_family: "skill_evaluation" | "alignment" | "role_coverage";
  report_id: string;
  created_at: string;
  target: string;
  version: string;
  status: string;
}

export interface SavedCharacterDerivedState {
  freshness_by_association_id: Record<string, "current" | "stale">;
  compatibility_by_association_id: Record<string, string>;
  structural_validation: CharacterKitStructuralValidation | null;
}

export interface SavedCharacter {
  character_id: string;
  current_revision_id: string;
  current_kit_assignment_id: string | null;
  created_at: string;
  updated_at: string;
  revision: SavedCharacterRevision;
  draft: CharacterDraft;
  request: CharacterGenerationRequest;
  plan: CharacterPlan | null;
  associations: CharacterSkillAssociation[];
  kit: Record<string, unknown> | null;
  derived: SavedCharacterDerivedState;
  history: SavedCharacterHistorySummary[];
}

export interface SavedCharacterListResponse {
  schema_version: "web-saved-character-list/0.1";
  characters: SavedCharacterSummary[];
  total: number;
}

export interface SavedCharacterSaveRequest {
  schema_version: "web-saved-character-save/0.1";
  request: CharacterGenerationRequest;
  draft: CharacterDraft;
  plan: CharacterPlan | null;
  associations: CharacterSkillAssociation[];
  expected_current_revision_id?: string | null;
  expected_current_kit_assignment_id?: string | null;
}

export interface SavedCharacterSaveResponse {
  schema_version: "web-saved-character-save/0.1";
  saved: SavedCharacter;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  api_version: string;
  character_generation_available: boolean;
}

export interface ApiAudit {
  stage: string | null;
  model_invocations: ModelInvocation[];
}

export interface ApiErrorBody {
  code: string;
  message: string;
  stage: string | null;
  retryable: boolean;
  details: Record<string, unknown>;
  audit: ApiAudit | null;
}

export interface ApiError {
  error: ApiErrorBody;
}

export interface ReferenceCoverage {
  identity: number;
  combat: number;
  narrative: number;
  presentation: number;
  analysis: number;
}

export interface ReferenceAvailability {
  facts: boolean;
  abilities: boolean;
  analysis: boolean;
  sources: boolean;
}

export interface ReferenceCharacterSummary {
  schema_version: "web-reference-character-summary/0.1";
  reference_id: string;
  display_name: string;
  localized_names: Record<string, string>;
  game_id: string;
  game_name: string;
  native_character_id: string | null;
  faction: string | null;
  occupation: string | null;
  combat_roles: string[];
  ability_categories: string[];
  verification_status: string;
  analysis_status: string;
  availability: ReferenceAvailability;
  completeness: ReferenceCoverage;
}

export interface ReferenceCharacterListResponse {
  schema_version: "web-reference-character-list/0.1";
  characters: ReferenceCharacterSummary[];
  total: number;
}

export interface ReferenceIdentity {
  game_id: string;
  game_name: string;
  native_character_id: string | null;
  canonical_name: string;
  localized_names: Record<string, string>;
  release: {version: string | null; date: string | null} | null;
  rarity: {native_value: string | number | null; normalized_tier: string | null} | null;
}

export interface ReferenceAbility {
  ability_id: string;
  native_name: string | null;
  native_category: string;
  normalized_category: string | null;
  description_summary: string | null;
}

export interface ReferenceFacts {
  narrative: {
    faction: string | null;
    occupation: string | null;
    affiliations: string[];
    public_identity: string | null;
  };
  presentation: {official_visual_tags: string[]; official_character_keywords: string[]};
  combat: {
    native_taxonomy: Record<string, string | string[]>;
    mechanics: {
      resources: Array<{resource_id: string; native_name: string | null; description_summary: string | null; cap: number | null}>;
      states: Array<{state_id: string; native_name: string | null; subject_scope: string; description_summary: string | null}>;
      transformations: string[];
      summons: string[];
      mobility_mechanics: string[];
      targeting_mechanics: string[];
    };
    team_mechanics: {
      buffs: string[];
      debuffs: string[];
      healing: string[];
      shielding: string[];
      grouping: string[];
      off_field_effects: string[];
      interactions: Array<{interaction_id: string; native_name: string | null; description_summary: string}>;
    };
    relations: Array<{relation_id: string; source: {kind: string; id: string}; relation_type: string; target: {kind: string; id: string}; description_summary: string | null}>;
  };
}

export interface ReferenceCombatAnalysis {
  normalized_roles: string[];
  combat_roles: string[];
  damage_patterns: string[];
  mechanics: string[];
  team_position: string[];
  attack_range: string;
  field_time: string;
  mechanical_complexity: string;
  execution_difficulty: string;
  mobility: string;
  survivability: string;
  team_dependency: string;
  primary_loop: {summary: string | null; steps: string[]};
  resource_loop: string | null;
  burst_pattern: string | null;
  archetypes: string[];
  core_mechanics: string[];
  role_rationale: Record<string, string>;
  evidence: Array<{dimension: string; token: string | null; ability_ids: string[]; mechanic_refs: Array<{kind: string; id: string}>; note: string}>;
}

export interface ReferenceCharacterAnalysis {
  metadata: {analyzer: string; prompt_version: string | null; analyzed_at: string | null};
  combat: ReferenceCombatAnalysis;
  character_fantasy: string | null;
  personality_archetypes: string[];
  identity_hooks: string[];
  narrative_hooks: string[];
  visual_motifs: string[];
  primary_selling_points: string[];
  gameplay_hooks: string[];
  visual_hooks: string[];
  narrative_design_hooks: string[];
  novelty_dimensions: string[];
  strongest_differentiators: string[];
  common_patterns: string[];
  unusual_patterns: string[];
  extracted_patterns: string[];
  combat_signature: string[];
  narrative_signature: string[];
  presentation_signature: string[];
}

export interface ReferenceSource {
  source_id: string;
  source_type: string;
  publisher: string | null;
  title: string | null;
  url: string;
  language: string | null;
  published_at: string | null;
  version_context: string | null;
  reliability: string;
}

export interface ReferenceCharacterDetailResponse {
  schema_version: "web-reference-character/0.1";
  reference_id: string;
  identity: ReferenceIdentity;
  facts: ReferenceFacts;
  abilities: ReferenceAbility[];
  combat_analysis: ReferenceCharacterAnalysis | null;
  sources: ReferenceSource[];
  metadata: {
    baseline_id: string | null;
    facts_schema_version: string;
    analysis_schema_version: string | null;
    sources_schema_version: string;
    verification_status: string;
    analysis_status: string;
    completeness: ReferenceCoverage;
    warnings: string[];
  };
}

export type CanonEntityType = "faction" | "lore" | "character" | "project" | "case" | "incident" | "story";

export interface CanonEntitySummary {
  entity_id: string;
  entity_type: CanonEntityType;
  name: string;
  aliases: string[];
  summary: string;
  tags: string[];
  relation_count: number;
  visibility: "public";
}

export interface CanonEntityListResponse {
  schema_version: "web-canon-entity-list/0.1";
  entities: CanonEntitySummary[];
  entity_types: CanonEntityType[];
  total: number;
}

export interface CanonText {
  description: string | null;
}

export interface CanonFactionSection {
  display_name: string;
  aliases: string[];
  faction_type: string | null;
  status: string | null;
  core_function: CanonText;
  public_identity: CanonText;
  public_reputation: CanonText;
  member_profile: {
    typical_roles: string[];
    recruitment_description: string | null;
    culture: string | null;
  };
  tags: string[];
}

export interface CanonLoreSection {
  title: string;
  statement: string;
  category: string | null;
  truth_status: boolean | null;
  sensitivity: "public";
  canon_level: string | null;
  temporal: {status: string | null; since: string | null; until: string | null};
  tags: string[];
}

export interface CanonCharacterSection {
  display_name: string;
  aliases: string[];
  occupation: string | null;
  faction_id: string | null;
  first_impression: string | null;
  combat_role: string | null;
  public_reputation: string | null;
  tags: string[];
}

export interface CanonRegistrySection {
  name: string;
  description: string | null;
  status: string | null;
}

export interface CanonStorySection {
  title: string;
  canon_status: string | null;
  premise: string;
  city_id: string | null;
  district_name: string | null;
  objective_facts: string[];
}

export interface CanonRelationship {
  source_entity_id: string;
  target_entity_id: string;
  target_entity_type: string;
  target_name: string;
  relation_type: string;
  direction: "outgoing";
  status: string | null;
  description: string | null;
  available: boolean;
}

export interface CanonEntityDetailResponse extends CanonEntitySummary {
  schema_version: "web-canon-entity/0.1";
  sections: {
    faction: CanonFactionSection | null;
    lore: CanonLoreSection | null;
    character: CanonCharacterSection | null;
    project: CanonRegistrySection | null;
    case: CanonRegistrySection | null;
    incident: CanonRegistrySection | null;
    story: CanonStorySection | null;
  };
  relationships: CanonRelationship[];
  provenance: Array<{source_type: string; references: string[]}>;
}
