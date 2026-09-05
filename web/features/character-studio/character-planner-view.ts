import type {CharacterDraft, CharacterGenerationResponse, PipelineStep, ValidatorResult} from "../../lib/api/types";

const ROLE_LABELS: Record<string, string> = {
  main_dps: "主输出",
  sub_dps: "副输出",
  support: "辅助",
  healer: "治疗",
  control: "控制",
  defense: "生存 / 防御",
};

const GENDER_LABELS: Record<string, string> = {female: "女性", male: "男性", non_binary: "非二元", unknown: "未说明"};
const STATUS_LABELS: Record<string, string> = {
  idle: "尚未生成",
  loading: "生成中",
  completed: "已完成",
  success: "已完成",
  passed: "通过",
  failed: "未通过",
  warning: "需关注",
  not_available: "未提供",
  skipped: "未执行",
  repaired: "已自动修正",
  NO_REPAIR_NEEDED: "无需修正",
  REPAIRED_PASS: "已自动修正",
  REPAIRED_WARN: "已修正，仍需关注",
  IMPROVED_BUT_FAILED: "已尝试修正但未通过",
  NO_IMPROVEMENT: "未发现有效修正",
  REGRESSION: "修正后出现回退",
  REPAIR_MODEL_FAILED: "自动修正失败",
  REPAIR_SCOPE_VIOLATION: "自动修正超出范围",
  REPAIR_HARD_CONSTRAINT_VIOLATION: "自动修正违反硬约束",
};

const FINDING_LABELS: Record<string, string> = {
  MISSING_CHARACTER_DESCRIPTION: "缺少角色描述",
  MISSING_COMBAT_ROLE: "缺少战斗定位",
  REQUEST_PRIMARY_ROLE_MISMATCH: "与需求中的主定位不匹配",
  REQUEST_SECONDARY_ROLE_MISSING: "缺少需求中的辅助定位",
  UNSUPPORTED_CANON_CLAIM: "世界观依据不足",
  INVALID_CANON_REFERENCE: "世界观引用无效",
  CANON_PRESENTED_AS_PROPOSAL: "世界观设定与新增提案边界不清",
  PROPOSAL_PRESENTED_AS_CANON: "新增提案被当作既有设定",
  HARD_CONSTRAINT_VIOLATION: "设计约束未满足",
  KNOWLEDGE_SCOPE_OVERREACH: "知识范围超出设定依据",
  INVALID_FACTION_ROLE: "所属组织与角色身份不匹配",
};

export type PlannerStatus = "通过" | "未通过" | "未提供";

export interface CharacterPlannerProjection {
  name: string;
  identity: {
    gender: string;
    age: string;
    ageRange: string;
    occupation: string;
    socialRole: string;
    affiliation: string;
  };
  role: string;
  secondaryRoles: string[];
  designPitch: string;
  personality: string[];
  background: string;
  storyHook: string;
  abilityConcept: string;
  knowledgeScope: string;
  combatSummary: string;
  evaluationStatus: PlannerStatus;
  canonStatus: PlannerStatus;
  repairStatus: string;
  findings: Array<{title: string; detail: string; code: string}>;
}

function value(value: string | null | undefined, fallback = "未提供"): string {
  return value?.trim() || fallback;
}

export function characterRoleLabel(role: string | null | undefined): string {
  return role ? ROLE_LABELS[role] ?? "其他定位" : "未指定";
}

export function characterGenderLabel(gender: string | null | undefined): string {
  return gender ? GENDER_LABELS[gender] ?? "未说明" : "未说明";
}

export function plannerStatus(status: string | null | undefined): PlannerStatus {
  if (status === "passed") return "通过";
  if (status === "failed") return "未通过";
  return "未提供";
}

export function statusLabel(status: string | null | undefined): string {
  return status ? STATUS_LABELS[status] ?? "未提供" : "未提供";
}

function pipelineStatus(pipeline: PipelineStep[], id: string): PlannerStatus {
  return plannerStatus(pipeline.find((step) => step.id === id)?.status);
}

function findingTitle(finding: ValidatorResult): string {
  return finding.code ? FINDING_LABELS[finding.code] ?? "发现一项需要检查的问题" : "发现一项需要检查的问题";
}

export function projectCharacterPlanner(
  response: CharacterGenerationResponse,
  affiliationName: string | null,
): CharacterPlannerProjection {
  const {draft, combat, pipeline, repair} = response;
  const secondaryRoles = draft.combat_role_profile.secondary_roles.map(characterRoleLabel);
  return {
    name: value(draft.name, "未命名角色"),
    identity: {
      gender: characterGenderLabel(draft.gender),
      age: draft.age === null ? "未说明" : `${draft.age} 岁`,
      ageRange: value(draft.age_range),
      occupation: value(draft.occupation),
      socialRole: value(draft.social_role),
      affiliation: affiliationName ? value(affiliationName) : "所属组织信息见世界观依据",
    },
    role: characterRoleLabel(draft.combat_role_profile.primary_role),
    secondaryRoles,
    designPitch: value(draft.design_pitch),
    personality: draft.personality.length > 0 ? draft.personality : ["未提供"],
    background: value(draft.background),
    storyHook: value(draft.story_hook),
    abilityConcept: value(draft.ability_concept),
    knowledgeScope: value(draft.knowledge_scope),
    combatSummary: value(combat.skill_summary),
    evaluationStatus: pipelineStatus(pipeline, "evaluation"),
    canonStatus: pipelineStatus(pipeline, "canon"),
    repairStatus: statusLabel(repair.status),
    findings: response.validators
      .filter((finding) => finding.status === "failed" || finding.status === "warning")
      .map((finding) => ({title: findingTitle(finding), detail: "请在技术详情中查看原始检查说明。", code: value(finding.code, finding.name)})),
  };
}

export function projectSavedCharacterDraft(draft: CharacterDraft, affiliationName: string | null): CharacterPlannerProjection {
  return {
    name: value(draft.name, "未命名角色"),
    identity: {
      gender: characterGenderLabel(draft.gender),
      age: draft.age === null ? "未说明" : `${draft.age} 岁`,
      ageRange: value(draft.age_range),
      occupation: value(draft.occupation),
      socialRole: value(draft.social_role),
      affiliation: affiliationName ? value(affiliationName) : "所属组织信息见世界观依据",
    },
    role: characterRoleLabel(draft.combat_role_profile.primary_role),
    secondaryRoles: draft.combat_role_profile.secondary_roles.map(characterRoleLabel),
    designPitch: value(draft.design_pitch),
    personality: draft.personality.length > 0 ? draft.personality : ["未提供"],
    background: value(draft.background),
    storyHook: value(draft.story_hook),
    abilityConcept: value(draft.ability_concept),
    knowledgeScope: value(draft.knowledge_scope),
    combatSummary: "当前结果未提供",
    evaluationStatus: "未提供",
    canonStatus: "未提供",
    repairStatus: "未提供",
    findings: [],
  };
}
