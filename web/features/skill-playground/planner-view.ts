import type {CharacterSkillDesignResponse, SkillPlaygroundRequest, SkillPlaygroundResponse} from "../../lib/api/types";

export type PlannerResult = SkillPlaygroundResponse | CharacterSkillDesignResponse;

export interface PlannerRequirement {
  label: string;
  status: "通过";
}

export interface PlannerViewModel {
  abilityName: string;
  role: string;
  mode: string;
  summary: string;
  trigger: string;
  effect: string;
  target: string;
  resources: string;
  requirements: PlannerRequirement[];
  status: "通过" | "未通过";
  findings: Array<{title: string; code: string; repairability: string}>;
  technical: {
    semanticIr: Record<string, unknown> | null;
    skillKit: Record<string, unknown> | null;
    evaluation: PlannerResult["evaluation"];
    evidence: Record<string, unknown>;
    digests: {candidate: string | null; report: string | null};
    provider: PlannerResult["provider"];
    pipeline: PlannerResult["pipeline"];
  };
}

const ROLE_LABELS: Record<string, string> = {main_dps: "主输出", sub_dps: "副输出", support: "辅助", healer: "治疗", control: "控制", defense: "生存 / 防御", basic_passive: "基础被动"};
const MODE_LABELS: Record<string, string> = {active: "主动", passive: "被动", reaction: "反应"};
const ACTOR_LABELS: Record<string, string> = {ally: "友方", enemy: "敌方", self: "自身", team: "全队"};
const EVENT_LABELS: Record<string, string> = {action_completed: "完成行动", damage_received: "受到伤害", ability_invoked: "施放技能", feedback_received: "收到反馈", healing_received: "受到治疗"};
const INTENT_LABELS: Record<string, string> = {deal_follow_up_damage: "发动追加攻击", deal_damage: "造成伤害", protect_ally: "保护友方", enable_ally: "支援友方", control_enemy: "控制敌方", mitigate_ally: "减轻友方伤害"};
const FINDING_LABELS: Record<string, string> = {MECHANIC_SKELETON_ABSENT: "缺少核心机制", ROLE_EFFECT_MISMATCH: "战斗定位与技能效果不匹配", ROLE_PROFILE_MISMATCH: "战斗定位与技能效果不匹配", ROLE_EVIDENCE_MISMATCH: "战斗定位缺少支持依据", TRIGGER_SUBJECT_MISMATCH: "触发对象与设计需求不匹配", TRIGGER_SUBJECT_AMBIGUOUS: "触发对象不明确", MECHANIC_MODE_MISMATCH: "技能类型与机制不匹配", CONTINUATION_FAMILY_MISMATCH: "追加效果类型不匹配", REQUESTED_MECHANIC_UNREPRESENTED: "未实现所要求的核心机制", HARD_CONSTRAINT_CONFLICT: "设计约束未满足", CONSTRAINT_VIOLATION: "设计约束未满足", FEEDBACK_RELATION_INVALID: "反馈关系不完整", RESOURCE_LOOP_INCOMPLETE: "资源循环不完整", STATE_EXIT_MISSING: "状态结束条件缺失", LIFECYCLE_INCOMPLETE: "机制生命周期不完整", LIFECYCLE_MISMATCH: "机制生命周期不匹配", SUMMON_LIFECYCLE_INCOMPLETE: "召唤物生命周期不完整"};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function text(value: unknown): string | null { return typeof value === "string" && value.trim() ? value : null; }
function label(value: unknown, labels: Record<string, string>, fallback: string): string { const raw = text(value); return raw ? labels[raw] ?? fallback : fallback; }
function skillInput(result: PlannerResult): SkillPlaygroundRequest { return "skill_input" in result ? result.skill_input : result.input; }
function hasConstraint(input: SkillPlaygroundRequest, ...terms: string[]): boolean { const constraints = input.constraints.join(" "); return terms.some((term) => constraints.includes(term)); }

function resourcesSummary(skillKit: Record<string, unknown> | null): string {
  const resources = Array.isArray(skillKit?.resources) ? skillKit.resources : [];
  const states = Array.isArray(skillKit?.states) ? skillKit.states : [];
  const summons = Array.isArray(skillKit?.summons) ? skillKit.summons : [];
  return resources.length === 0 && states.length === 0 && summons.length === 0 ? "未引入新的战斗资源" : "已配置战斗资源或状态";
}

export function projectSkillPlanner(result: PlannerResult): PlannerViewModel {
  const input = skillInput(result);
  const ir = record(result.semantic_ir);
  const mechanic = record(ir?.mechanic);
  const trigger = record(mechanic?.trigger);
  const effect = record(mechanic?.effect);
  const roleId = text(ir?.role) ?? input.family;
  const modeId = text(ir?.mode) ?? input.mode;
  const triggerActor = label(trigger?.actor, ACTOR_LABELS, "其他对象");
  const triggerEvent = label(trigger?.event, EVENT_LABELS, "其他事件");
  const effectActor = label(effect?.actor, ACTOR_LABELS, "其他目标");
  const effectIntent = label(effect?.intent, INTENT_LABELS, "产生其他效果");
  const hasMechanic = trigger !== null && effect !== null;
  const abilityName = text(ir?.ability_name) ?? "未命名技能方案";
  const summary = triggerActor === "友方" && triggerEvent === "完成行动" && effectActor === "敌方" && effectIntent === "发动追加攻击"
    ? "当一名队友完成行动后，对敌方目标发动一次追加攻击。"
    : hasMechanic ? `当${triggerActor}${triggerEvent}时，${effectActor}${effectIntent}。` : "当前结果没有形成可读的核心机制。";
  const passed = result.evaluation.outcome === "PASS";
  const requirements: PlannerRequirement[] = [];
  if (hasMechanic) requirements.push({label: `${triggerActor}${triggerEvent}后触发`, status: "通过"});
  if (text(effect?.intent) === "deal_follow_up_damage") requirements.push({label: "产生追加输出", status: "通过"});
  if (hasConstraint(input, "只能影响敌方", "仅影响敌方") && text(effect?.actor) === "enemy") requirements.push({label: "仅影响敌方", status: "通过"});
  if (hasConstraint(input, "不引入新资源") && resourcesSummary(result.skillkit) === "未引入新的战斗资源") requirements.push({label: "不引入新资源", status: "通过"});
  if (text(ir?.role) === input.family || (!ir?.role && input.family)) requirements.push({label: `符合${ROLE_LABELS[roleId] ?? "所选"}定位`, status: "通过"});
  const findings = result.evaluation.findings.map((finding) => ({title: FINDING_LABELS[finding.code] ?? "发现一项设计问题", code: finding.code, repairability: finding.repairable || result.evaluation.repair_allowed ? "可以尝试自动修正" : "需要重新生成"}));
  return {abilityName, role: `${ROLE_LABELS[roleId] ?? "其他定位"} · ${MODE_LABELS[modeId] ?? "其他模式"}`, mode: MODE_LABELS[modeId] ?? "其他模式", summary, trigger: trigger ? `${triggerActor} · ${triggerEvent}` : "未识别触发条件", effect: effect ? effectIntent : "未识别触发效果", target: effectActor, resources: resourcesSummary(result.skillkit), requirements, status: passed ? "通过" : "未通过", findings, technical: {semanticIr: result.semantic_ir, skillKit: result.skillkit, evaluation: result.evaluation, evidence: result.evidence, digests: {candidate: result.evaluation.candidate_digest, report: result.evaluation.report_digest}, provider: result.provider, pipeline: result.pipeline}};
}
