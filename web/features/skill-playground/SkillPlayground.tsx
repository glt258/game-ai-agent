"use client";

import {useEffect, useMemo, useRef, useState} from "react";

import {apiClient, ApiClientError} from "../../lib/api/client";
import type {
  CharacterSkillContextRequest,
  CharacterSkillContextResponse,
  CharacterSkillDesignResponse,
  CharacterSkillSlot,
  LiveJobStatusResponse,
  SkillExecutionMode,
  SkillFamily,
  SkillMode,
  SkillPlaygroundMetaResponse,
  SkillPlaygroundRequest,
  SkillProviderName,
  SkillSlot,
} from "../../lib/api/types";
import {canAttachSkill} from "../character-studio/skill-session";
import {projectSkillPlanner, type PlannerResult, type PlannerViewModel} from "./planner-view";

const DEFAULT_PRESET = "generalization_sub_dps_v1";
const MAX_LIVE_WAIT_MS = 120_000;
type Tab = "planner" | "checks" | "technical";

export interface SkillPlaygroundProps {
  embedded?: boolean;
  characterInput?: CharacterSkillContextRequest | null;
  characterContext?: CharacterSkillContextResponse | null;
  slotOptions?: CharacterSkillSlot[];
  onAttach?: (result: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => void;
}

function pretty(value: unknown): string { return JSON.stringify(value, null, 2); }
function skillInput(result: PlannerResult): SkillPlaygroundRequest { return "skill_input" in result ? result.skill_input : result.input; }
function sourceFingerprint(result: PlannerResult): string | null { return "source_context_fingerprint" in result ? result.source_context_fingerprint : null; }

function liveJobError(status: LiveJobStatusResponse): ApiClientError {
  return new ApiClientError(
    {error: status.error ?? {code: "LIVE_EXECUTION_FAILED", message: "技能生成没有返回可用结果。", stage: "live_execution", retryable: true, details: {}, audit: null}},
    status.error?.code === "PROVIDER_TIMEOUT" || status.error?.code === "BACKEND_REQUEST_TIMEOUT" ? 504 : 503,
  );
}

function PlannerSummary({view}: {view: PlannerViewModel}) {
  return <div className="planner-summary" data-testid="planner-summary">
    <div className="planner-status-row"><span className={`status-chip ${view.status === "通过" ? "passed" : "failed"}`}>{view.status === "通过" ? "设计检查通过" : "设计检查未通过"}</span></div>
    <p className="section-label">技能摘要</p>
    <p className="planner-summary-text">{view.summary}</p>
    <div className="planner-facts">
      <div className="field-card"><p className="field-name">定位</p><p className="field-value">{view.role}</p></div>
      <div className="field-card"><p className="field-name">资源与状态</p><p className="field-value">{view.resources}</p></div>
      <div className="field-card full"><p className="field-name">核心机制</p><div className="mechanic-flow"><div><span>触发条件</span><strong>{view.trigger}</strong></div><b aria-hidden="true">↓</b><div><span>触发效果</span><strong>{view.effect}</strong></div><b aria-hidden="true">↓</b><div><span>作用目标</span><strong>{view.target}</strong></div></div></div>
      <div className="field-card full"><p className="field-name">需求匹配</p>{view.requirements.length > 0 ? <div className="requirement-list">{view.requirements.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.status}</strong></div>)}</div> : <p className="field-value muted">机制检查通过，未生成可逐条确认的需求项。</p>}</div>
    </div>
  </div>;
}

function ChecksView({view}: {view: PlannerViewModel}) {
  return <div className="stack" data-testid="planner-checks">
    <div className={`planner-check-banner ${view.status === "通过" ? "passed" : "failed"}`}><strong>{view.status === "通过" ? "设计检查通过" : "设计检查未通过"}</strong><span>{view.status === "通过" ? "技能机制、定位与现有约束检查通过。" : "当前技能方案没有满足全部设计要求。"}</span></div>
    {view.findings.length > 0 ? <div className="stack">{view.findings.map((finding) => <div className="finding-card" key={`${finding.code}-${finding.title}`}><strong>{finding.title}</strong><span>{finding.repairability}</span><small>技术代码：{finding.code}</small></div>)}</div> : <div className="field-card"><p className="field-value">没有发现需要处理的设计问题。</p></div>}
    {view.status === "未通过" && <div className="planner-repair-note"><strong>处理建议</strong><span>{view.findings.some((finding) => finding.repairability === "可以尝试自动修正") ? "可以尝试自动修正。" : "该结果需要重新生成，而不是局部修复。"}</span></div>}
  </div>;
}

function TechnicalView({view}: {view: PlannerViewModel}) {
  const {technical} = view;
  return <div className="stack technical-view" data-testid="planner-technical-details">
    <div className="technical-overview"><span>技术详情</span><small>{technical.provider.mode} · {technical.provider.outcome}</small></div>
    <details open><summary>Semantic IR</summary><pre className="json-view">{pretty(technical.semanticIr)}</pre></details>
    <details><summary>SkillKit</summary><pre className="json-view">{pretty(technical.skillKit)}</pre></details>
    <details><summary>Evaluation</summary><pre className="json-view">{pretty(technical.evaluation)}</pre></details>
    <details><summary>检查依据</summary><pre className="json-view">{pretty(technical.evidence)}</pre></details>
    <details><summary>原始生成阶段</summary><div className="pipeline-list skill-pipeline">{technical.pipeline.map((step) => <div className="pipeline-item" key={step.id}><span className={`pipeline-marker ${step.status}`} /><div><strong>{step.label}</strong><p>{step.status}</p></div></div>)}</div></details>
    <div className="field-grid"><div className="field-card"><p className="field-name">candidate_digest</p><p className="field-value">{technical.digests.candidate ?? "未生成"}</p></div><div className="field-card"><p className="field-name">report_digest</p><p className="field-value">{technical.digests.report ?? "未生成"}</p></div><div className="field-card"><p className="field-name">provider diagnostics</p><p className="field-value">{technical.provider.latency_ms === null ? "无延迟数据" : `${Math.round(technical.provider.latency_ms)} ms`}</p></div></div>
  </div>;
}

export function SkillPlayground({embedded = false, characterInput = null, characterContext = null, slotOptions = [], onAttach}: SkillPlaygroundProps) {
  const [meta, setMeta] = useState<SkillPlaygroundMetaResponse | null>(null);
  const [family, setFamily] = useState<SkillFamily>("sub_dps");
  const [mode, setMode] = useState<SkillMode>("active");
  const [brief, setBrief] = useState(characterContext?.character_context_summary.ability_concept ?? "设计一个在队友行动后追加输出的技能。");
  const [constraints, setConstraints] = useState("只能影响敌方；不引入新资源。");
  const [preset, setPreset] = useState(DEFAULT_PRESET);
  const [language, setLanguage] = useState<"auto" | "en" | "zh-CN">("zh-CN");
  const [executionMode, setExecutionMode] = useState<SkillExecutionMode>("offline");
  const [provider, setProvider] = useState<SkillProviderName>("opencode_go");
  const [model, setModel] = useState("deepseek-v4-pro");
  const [result, setResult] = useState<PlannerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [stale, setStale] = useState(false);
  const [tab, setTab] = useState<Tab>("planner");
  const [selectedSlot, setSelectedSlot] = useState<SkillSlot | "">(slotOptions[0]?.id ?? "");
  const [liveJobStatus, setLiveJobStatus] = useState<"PENDING" | "RUNNING" | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const runGeneration = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const inCharacterMode = Boolean(characterInput && characterContext);

  useEffect(() => {
    apiClient.getSkillPlaygroundMeta().then(setMeta).catch((reason: unknown) => setError(reason instanceof ApiClientError ? reason : new ApiClientError({error: {code: "META_LOAD_FAILED", message: "技能元数据无法加载。", stage: "meta", retryable: true, details: {}, audit: null}}, 0)));
  }, []);
  useEffect(() => () => { runGeneration.current += 1; activeController.current?.abort(); }, []);
  const selectedFamily = useMemo(() => meta?.families.find((item) => item.id === family), [meta, family]);
  const markEdited = (setter: (value: string) => void, value: string) => { setter(value); setStale(result !== null); };

  const run = async () => {
    if (!brief.trim()) return;
    activeController.current?.abort();
    const generation = runGeneration.current + 1;
    runGeneration.current = generation;
    const controller = new AbortController();
    activeController.current = controller;
    setLoading(true); setError(null); setStale(result !== null); setLiveJobStatus(null); setLiveElapsedMs(0);
    const skillPayload: SkillPlaygroundRequest = {family, mode, brief: brief.trim(), constraints: constraints.split("\n").map((item) => item.trim()).filter(Boolean), language, model: executionMode === "live" ? model : "web-offline-fixture", provider, execution_mode: executionMode, preset_id: executionMode === "offline" ? (preset || null) : null};
    try {
      let response: PlannerResult;
      if (executionMode === "live") {
        const accepted = inCharacterMode && characterInput ? await apiClient.createCharacterSkillDesignLiveJob({character: characterInput, skill: skillPayload}, controller.signal) : await apiClient.createSkillPlaygroundLiveJob(skillPayload, controller.signal);
        setLiveJobStatus(accepted.status === "PENDING" ? "PENDING" : "RUNNING");
        const deadline = Date.now() + MAX_LIVE_WAIT_MS;
        while (true) {
          const status = inCharacterMode && characterInput ? await apiClient.getCharacterSkillDesignLiveJob(accepted.job_id, controller.signal) : await apiClient.getSkillPlaygroundLiveJob(accepted.job_id, controller.signal);
          if (generation !== runGeneration.current || controller.signal.aborted) return;
          setLiveJobStatus(status.status === "PENDING" ? "PENDING" : status.status === "RUNNING" ? "RUNNING" : null); setLiveElapsedMs(status.elapsed_ms);
          if (status.status === "SUCCEEDED") { if (!status.result) throw liveJobError(status); response = status.result as PlannerResult; break; }
          if (status.status === "FAILED") throw liveJobError(status);
          if (Date.now() >= deadline) throw new ApiClientError({error: {code: "CLIENT_TIMEOUT", message: "生成请求超出浏览器等待时间。", stage: "client", retryable: true, details: {}, audit: null}}, 504);
          await new Promise((resolve) => setTimeout(resolve, Math.max(accepted.poll_after_ms, 1000)));
        }
      } else {
        response = inCharacterMode && characterInput ? await apiClient.runCharacterSkillDesign({character: characterInput, skill: skillPayload}) : await apiClient.runSkillPlayground(skillPayload);
      }
      if (generation !== runGeneration.current || controller.signal.aborted) return;
      setResult(response); setStale(false); setTab("planner");
    } catch (reason: unknown) {
      if (generation === runGeneration.current && !controller.signal.aborted) setError(reason instanceof ApiClientError ? reason : null);
    } finally {
      if (generation === runGeneration.current) { setLoading(false); setLiveJobStatus(null); }
    }
  };

  const chooseFamily = (value: SkillFamily) => { setFamily(value); if (value === "basic_passive") setMode("passive"); setStale(result !== null); };
  const Root = embedded ? "section" : "main";
  const currentInput = result ? skillInput(result) : null;
  const currentFingerprint = characterContext?.source_context_fingerprint ?? null;
  const resultFingerprint = result ? sourceFingerprint(result) : null;
  const contextStale = resultFingerprint !== null && currentFingerprint !== null && resultFingerprint !== currentFingerprint;
  const resultIsStale = stale || contextStale;
  const planner = result ? projectSkillPlanner(result) : null;
  const currentResult = result;
  const currentPlanner = planner;
  const alignment = currentResult && "alignment" in currentResult ? currentResult.alignment : null;
  const alignmentDisplayStatus = alignment && resultIsStale ? "STALE" : alignment?.status ?? "NOT_APPLICABLE";
  const effectiveSlot = slotOptions.some((item) => item.id === selectedSlot) ? selectedSlot : slotOptions[0]?.id ?? "";

  return <Root className="reference-shell skill-shell">
    <header className="reference-header"><div><p className="workspace-kicker">技能设计 / {inCharacterMode ? "角色上下文" : "离线示例"}</p><h1 className="workspace-title">技能设计台</h1><p className="column-subtitle">输入技能设计需求，生成技能方案并检查机制、定位与约束是否匹配。</p></div><span className="reference-contract">{inCharacterMode ? "web-character-skill-design/0.1" : "web-skill-playground/0.1"}</span></header>
    {inCharacterMode && characterContext && <div className="character-skill-context" aria-label="角色上下文"><div><p className="section-label">当前角色</p><strong>{characterContext.character_context_summary.character_name}</strong><p className="field-value">战斗定位：{characterContext.character_context_summary.combat_role_profile.primary_role ?? "未指定"}</p></div><div><p className="field-name">技能概念</p><p className="field-value">{characterContext.character_context_summary.ability_concept}</p>{characterContext.character_context_summary.skill_relevant_hard_constraints.length > 0 && <p className="context-derived">角色约束：{characterContext.character_context_summary.skill_relevant_hard_constraints.join("；")}</p>}{characterContext.character_context_summary.skill_relevant_forbidden_elements.length > 0 && <p className="context-derived">禁止元素：{characterContext.character_context_summary.skill_relevant_forbidden_elements.join("；")}</p>}</div><span className="context-fingerprint">上下文：{characterContext.source_context_fingerprint.slice(0, 12)}…</span></div>}
    <div className="skill-layout">
      <section className="skill-form-panel" aria-label="技能设计需求">
        <p className="section-label skill-panel-title">技能设计需求</p>
        <label className="skill-field"><span className="section-label">技能定位</span><select aria-label="技能定位" value={family} onChange={(event) => chooseFamily(event.target.value as SkillFamily)}>{(meta?.families ?? []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>{selectedFamily?.description ?? "正在加载技能定位…"}</small></label>
        <label className="skill-field"><span className="section-label">技能类型 / 模式</span><select aria-label="技能类型 / 模式" value={mode} disabled={family === "basic_passive"} onChange={(event) => { setMode(event.target.value as SkillMode); setStale(result !== null); }}>{(meta?.modes ?? ["active", "passive", "reaction"]).map((item) => <option key={item} value={item}>{({active: "主动", passive: "被动", reaction: "反应"} as Record<string, string>)[item] ?? "其他模式"}</option>)}</select></label>
        <label className="skill-field"><span className="section-label">设计需求</span><textarea aria-label="设计需求" value={brief} onChange={(event) => markEdited(setBrief, event.target.value)} rows={7} /></label>
        <label className="skill-field"><span className="section-label">设计约束</span><textarea aria-label="设计约束" value={constraints} onChange={(event) => markEdited(setConstraints, event.target.value)} rows={4} placeholder="每行填写一条约束" /></label>
        <details className="advanced-settings"><summary>高级设置</summary><div className="advanced-settings-body"><label className="skill-field"><span className="section-label">离线示例</span><select aria-label="离线示例" value={preset} onChange={(event) => markEdited(setPreset, event.target.value)}><option value="">不使用预设（需要已配置的 AI Provider）</option>{(meta?.examples ?? []).map((item) => <option key={item} value={item}>{item === "generalization_sub_dps_v1" ? "副输出追击示例" : item === "generalization_defense_v1" ? "防御反应示例" : item === "character_defense_skill_v1" ? "角色防御技能示例" : item === "character_support_skill_v1" ? "角色辅助技能示例" : item === "generalization_basic_passive_v1" ? "角色基础被动示例" : item}</option>)}</select><small>技术 ID 仅用于选择真实 fixture，不改变内部值。</small></label><label className="skill-field"><span className="section-label">生成方式</span><select aria-label="生成方式" value={executionMode} onChange={(event) => { setExecutionMode(event.target.value as SkillExecutionMode); setStale(result !== null); }}><option value="offline">离线示例</option><option value="live">AI 生成</option></select></label>{executionMode === "live" && <><label className="skill-field"><span className="section-label">Provider</span><select aria-label="Provider" value={provider} onChange={(event) => { setProvider(event.target.value as SkillProviderName); setStale(result !== null); }}><option value="opencode_go">OpenCode Go</option><option value="deepseek">DeepSeek</option></select><small>凭据保留在 FastAPI 环境中。</small></label><label className="skill-field"><span className="section-label">模型</span><select aria-label="模型" value={model} onChange={(event) => { setModel(event.target.value); setStale(result !== null); }}><option value="deepseek-v4-pro">deepseek-v4-pro</option><option value="deepseek-chat">deepseek-chat</option><option value="mimo-v2.5">mimo-v2.5</option><option value="mimo-v2.5-pro">mimo-v2.5-pro</option></select></label></>}</div></details>
        <label className="skill-field"><span className="section-label">输出语言</span><select aria-label="输出语言" value={language} onChange={(event) => setLanguage(event.target.value as typeof language)}><option value="zh-CN">简体中文</option><option value="en">English</option><option value="auto">自动</option></select></label>
        <button className="button-primary skill-run" disabled={loading || !brief.trim() || (!inCharacterMode && Boolean(characterInput))} onClick={run}>{loading ? "正在生成技能方案…" : "生成技能"}</button>
        {meta && <p className="skill-note">{executionMode === "live" ? "AI 生成会使用后端 Provider。" : "当前使用离线示例，不会调用 live model。"}</p>}
      </section>
      <section className="skill-result-panel" aria-live="polite">
        {loading && executionMode === "live" && <div className="notice loading-notice" role="status"><strong>正在生成技能方案…</strong><p>生成方式：AI 生成</p><span className="notice-meta">{liveJobStatus === "PENDING" ? "正在排队" : "等待生成结果"} · 已用时 {Math.round(liveElapsedMs)} ms</span></div>}
        {error && <div className="notice" role="alert"><strong>生成失败</strong><p>{error.payload.error.message}</p><span className="notice-meta">技术阶段：{error.payload.error.stage ?? "未知"} · {error.payload.error.code}</span></div>}
        {resultIsStale && result && <p className="stale-notice">输入或角色上下文已修改；当前结果是上一次运行的快照。重新生成以更新。</p>}
        {!result && !error && <div className="empty-state"><div><strong>尚未生成技能方案</strong><span>填写左侧设计需求后，点击“生成技能”查看技能方案与设计检查结果。</span></div></div>}
        {currentResult && currentPlanner && <><div className="workspace-header"><div><p className="workspace-kicker">技能方案</p><h2 className="workspace-title">{currentPlanner.abilityName}</h2><span className="workspace-meta">{currentPlanner.role}</span></div><div className="workspace-actions">{inCharacterMode && "source_context_fingerprint" in currentResult && <><label className="slot-select"><span className="sr-only">绑定技能槽位</span><select aria-label="绑定技能槽位" value={effectiveSlot} onChange={(event) => setSelectedSlot(event.target.value as SkillSlot)} disabled={slotOptions.length === 0}><option value="">选择槽位</option>{slotOptions.map((slot) => <option key={slot.id} value={slot.id}>{slot.label}</option>)}</select></label><button className="button-primary" disabled={!canAttachSkill(currentResult) || resultIsStale || !effectiveSlot} onClick={() => { const slot = slotOptions.find((item) => item.id === effectiveSlot); if (slot) onAttach?.(currentResult, slot); }}>{canAttachSkill(currentResult) ? "绑定到角色" : resultIsStale ? "绑定前需要重新生成" : currentResult.evaluation.outcome === "PASS" && alignment?.status === "FAIL" ? "角色适配未通过" : currentResult.artifact_compatibility && currentResult.artifact_compatibility !== "CURRENT_COMPATIBLE" ? "需要兼容的技能方案" : "仅可绑定通过的方案"}</button></>}</div></div></>}
        {inCharacterMode && alignment && currentResult && <div className="alignment-summary-grid"><section className="alignment-card"><p className="section-label">技能检查</p><div className={`alignment-status ${currentResult.evaluation.outcome === "PASS" ? "passed" : "failed"}`}>{currentResult.evaluation.outcome === "PASS" ? "通过" : "未通过"}</div><p>技能有效性独立于角色适配检查。</p></section><section className="alignment-card"><p className="section-label">角色适配</p><div className={`alignment-status ${alignmentDisplayStatus === "PASS" ? "passed" : alignmentDisplayStatus === "STALE" ? "stale" : "failed"}`}>{alignmentDisplayStatus === "PASS" ? "通过" : alignmentDisplayStatus === "STALE" ? "已过期" : "未通过"}</div><p>{resultIsStale ? "技能或角色上下文已变化，请重新生成。" : alignment.summary}</p></section></div>}
        {currentPlanner && <><div className="tabs skill-tabs" role="tablist">{([{id: "planner", label: "设计结果"}, {id: "checks", label: "设计检查"}, {id: "technical", label: "技术详情"}] as const).map((item) => <button className="tab" key={item.id} role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</button>)}</div>
        <div className="tab-panel">{tab === "planner" && <PlannerSummary view={currentPlanner} />}{tab === "checks" && <ChecksView view={currentPlanner} />}{tab === "technical" && <TechnicalView view={currentPlanner} />}</div>
        <details className="planner-input-details"><summary>本次设计需求</summary><div className="field-card"><p className="field-value">{currentInput?.brief}</p>{currentInput?.constraints.length ? <p className="field-value muted">约束：{currentInput.constraints.join("；")}</p> : null}</div></details></>}
      </section>
    </div>
  </Root>;
}
