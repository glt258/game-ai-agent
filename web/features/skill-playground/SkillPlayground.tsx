"use client";

import {useEffect, useMemo, useRef, useState} from "react";

import {apiClient, ApiClientError} from "../../lib/api/client";
import type {
  CharacterSkillContextRequest,
  CharacterSkillContextResponse,
  CharacterSkillDesignResponse,
  CharacterSkillSlot,
  SkillFamily,
  SkillExecutionMode,
  SkillMode,
  SkillProviderName,
  SkillSlot,
  SkillPlaygroundMetaResponse,
  SkillPlaygroundRequest,
  SkillPlaygroundResponse,
  LiveJobStatusResponse,
} from "../../lib/api/types";
import {canAttachSkill} from "../character-studio/skill-session";

const DEFAULT_PRESET = "generalization_sub_dps_v1";
const MAX_LIVE_WAIT_MS = 120_000;
type Tab = "overview" | "ir" | "skillkit" | "evaluation" | "evidence";
type SkillResult = SkillPlaygroundResponse | CharacterSkillDesignResponse;

export interface SkillPlaygroundProps {
  embedded?: boolean;
  characterInput?: CharacterSkillContextRequest | null;
  characterContext?: CharacterSkillContextResponse | null;
  slotOptions?: CharacterSkillSlot[];
  onAttach?: (result: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => void;
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function skillInput(result: SkillResult): SkillPlaygroundRequest {
  return "skill_input" in result ? result.skill_input : result.input;
}

function sourceFingerprint(result: SkillResult): string | null {
  return "source_context_fingerprint" in result ? result.source_context_fingerprint : null;
}

function liveJobError(status: LiveJobStatusResponse): ApiClientError {
  return new ApiClientError(
    {
      error: status.error ?? {
        code: "LIVE_EXECUTION_FAILED",
        message: "The live execution did not return a safe result.",
        stage: "live_execution",
        retryable: true,
        details: {},
        audit: null,
      },
    },
    status.error?.code === "PROVIDER_TIMEOUT" || status.error?.code === "BACKEND_REQUEST_TIMEOUT" ? 504 : 503,
  );
}

export function SkillPlayground({
  embedded = false,
  characterInput = null,
  characterContext = null,
  slotOptions = [],
  onAttach,
}: SkillPlaygroundProps) {
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
  const [result, setResult] = useState<SkillResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [stale, setStale] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [selectedSlot, setSelectedSlot] = useState<SkillSlot | "">(slotOptions[0]?.id ?? "");
  const [liveJobStatus, setLiveJobStatus] = useState<"PENDING" | "RUNNING" | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const runGeneration = useRef(0);
  const activeController = useRef<AbortController | null>(null);

  const inCharacterMode = Boolean(characterInput && characterContext);

  useEffect(() => {
    apiClient.getSkillPlaygroundMeta().then(setMeta).catch((reason: unknown) => {
      setError(reason instanceof ApiClientError ? reason : new ApiClientError({error: {code: "META_LOAD_FAILED", message: "技能元数据无法加载。", stage: "meta", retryable: true, details: {}, audit: null}}, 0));
    });
  }, []);

  useEffect(() => () => {
    runGeneration.current += 1;
    activeController.current?.abort();
  }, []);

  const selectedFamily = useMemo(() => meta?.families.find((item) => item.id === family), [meta, family]);
  const markEdited = (setter: (value: string) => void, value: string) => {
    setter(value);
    setStale(result !== null);
  };

  const run = async () => {
    if (!brief.trim()) {
      return;
    }
    activeController.current?.abort();
    const generation = runGeneration.current + 1;
    runGeneration.current = generation;
    const controller = new AbortController();
    activeController.current = controller;
    setLoading(true); setError(null); setStale(result !== null); setLiveJobStatus(null); setLiveElapsedMs(0);
    const skillPayload: SkillPlaygroundRequest = {
      family, mode, brief: brief.trim(),
      constraints: constraints.split("\n").map((item) => item.trim()).filter(Boolean),
      language,
      model: executionMode === "live" ? model : "web-offline-fixture",
      provider,
      execution_mode: executionMode,
      preset_id: executionMode === "offline" ? (preset || null) : null,
    };
    try {
      let response: SkillResult;
      if (executionMode === "live") {
        const accepted = inCharacterMode && characterInput
          ? await apiClient.createCharacterSkillDesignLiveJob({character: characterInput, skill: skillPayload}, controller.signal)
          : await apiClient.createSkillPlaygroundLiveJob(skillPayload, controller.signal);
        setLiveJobStatus(accepted.status === "PENDING" ? "PENDING" : "RUNNING");
        const deadline = Date.now() + MAX_LIVE_WAIT_MS;
        while (true) {
          const status = inCharacterMode && characterInput
            ? await apiClient.getCharacterSkillDesignLiveJob(accepted.job_id, controller.signal)
            : await apiClient.getSkillPlaygroundLiveJob(accepted.job_id, controller.signal);
          if (generation !== runGeneration.current || controller.signal.aborted) return;
          setLiveJobStatus(status.status === "PENDING" ? "PENDING" : status.status === "RUNNING" ? "RUNNING" : null);
          setLiveElapsedMs(status.elapsed_ms);
          if (status.status === "SUCCEEDED") {
            if (!status.result) throw liveJobError(status);
            response = status.result as SkillResult;
            break;
          }
          if (status.status === "FAILED") throw liveJobError(status);
          if (Date.now() >= deadline) {
            throw new ApiClientError({error: {code: "CLIENT_TIMEOUT", message: "The live request exceeded the browser wait budget.", stage: "client", retryable: true, details: {}, audit: null}}, 504);
          }
          await new Promise((resolve) => setTimeout(resolve, Math.max(accepted.poll_after_ms, 1000)));
        }
      } else {
        response = inCharacterMode && characterInput
          ? await apiClient.runCharacterSkillDesign({character: characterInput, skill: skillPayload})
          : await apiClient.runSkillPlayground(skillPayload);
      }
      if (generation !== runGeneration.current || controller.signal.aborted) return;
      setResult(response); setStale(false); setTab("overview");
    } catch (reason: unknown) {
      if (generation === runGeneration.current && !controller.signal.aborted) {
        setError(reason instanceof ApiClientError ? reason : null);
      }
    } finally {
      if (generation === runGeneration.current) {
        setLoading(false); setLiveJobStatus(null);
      }
    }
  };

  const chooseFamily = (value: SkillFamily) => {
    setFamily(value);
    if (value === "basic_passive") setMode("passive");
    setStale(result !== null);
  };

  const Root = embedded ? "section" : "main";
  const currentInput = result ? skillInput(result) : null;
  const currentFingerprint = characterContext?.source_context_fingerprint ?? null;
  const resultFingerprint = result ? sourceFingerprint(result) : null;
  const contextStale = resultFingerprint !== null && currentFingerprint !== null && resultFingerprint !== currentFingerprint;
  const resultIsStale = stale || contextStale;
  const alignment = result && "alignment" in result ? result.alignment : null;
  const alignmentDisplayStatus = alignment && resultIsStale ? "STALE" : alignment?.status ?? "NOT_APPLICABLE";
  const effectiveSlot = slotOptions.some((item) => item.id === selectedSlot) ? selectedSlot : slotOptions[0]?.id ?? "";

  return (
    <Root className="reference-shell skill-shell">
      <header className="reference-header"><div><p className="workspace-kicker">Skill Design v1 / {inCharacterMode ? "Character context" : "W4-S1"}</p><h1 className="workspace-title">Skill Playground</h1><p className="column-subtitle">从结构化输入运行一次真实的 Semantic IR → SkillKit → Evaluation 流水线。</p></div><span className="reference-contract">{inCharacterMode ? "web-character-skill-design/0.1" : "web-skill-playground/0.1"}</span></header>
      {inCharacterMode && characterContext && <div className="character-skill-context" aria-label="Character context"><div><p className="section-label">Designing for Character</p><strong>{characterContext.character_context_summary.character_name}</strong><p className="field-value">Combat role: {characterContext.character_context_summary.combat_role_profile.primary_role ?? "Not specified"}</p></div><div><p className="field-name">Ability concept seed</p><p className="field-value">{characterContext.character_context_summary.ability_concept}</p>{characterContext.character_context_summary.skill_relevant_hard_constraints.length > 0 && <p className="context-derived">Character constraints: {characterContext.character_context_summary.skill_relevant_hard_constraints.join("; ")}</p>}{characterContext.character_context_summary.skill_relevant_forbidden_elements.length > 0 && <p className="context-derived">Forbidden elements: {characterContext.character_context_summary.skill_relevant_forbidden_elements.join("; ")}</p>}</div><span className="context-fingerprint">Context: {characterContext.source_context_fingerprint.slice(0, 12)}…</span></div>}
      <div className="skill-layout">
        <section className="skill-form-panel" aria-label="Skill Playground input">
          <p className="section-label">Design input</p>
          <label className="skill-field"><span className="section-label">Family</span><select value={family} onChange={(event) => chooseFamily(event.target.value as SkillFamily)}>{(meta?.families ?? []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>{selectedFamily?.description ?? "Loading authoritative families…"}</small></label>
          <label className="skill-field"><span className="section-label">Mode</span><select value={mode} disabled={family === "basic_passive"} onChange={(event) => { setMode(event.target.value as SkillMode); setStale(result !== null); }}>{(meta?.modes ?? ["active", "passive", "reaction"]).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label className="skill-field"><span className="section-label">Brief / intent</span><textarea value={brief} onChange={(event) => markEdited(setBrief, event.target.value)} rows={7} /></label>
          <label className="skill-field"><span className="section-label">Skill constraints</span><textarea value={constraints} onChange={(event) => markEdited(setConstraints, event.target.value)} rows={4} placeholder="One constraint per line" /></label>
          <label className="skill-field"><span className="section-label">Offline example</span><select value={preset} onChange={(event) => markEdited(setPreset, event.target.value)}><option value="">No preset (requires injected provider)</option>{(meta?.examples ?? []).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label className="skill-field"><span className="section-label">Execution mode</span><select value={executionMode} onChange={(event) => { setExecutionMode(event.target.value as SkillExecutionMode); setStale(result !== null); }}><option value="offline">Offline fixture</option><option value="live">Live provider (backend)</option></select></label>
          {executionMode === "live" && <><label className="skill-field"><span className="section-label">Provider</span><select value={provider} onChange={(event) => { setProvider(event.target.value as SkillProviderName); setStale(result !== null); }}><option value="opencode_go">OpenCode Go</option><option value="deepseek">DeepSeek</option></select><small>Credentials stay in the FastAPI environment.</small></label><label className="skill-field"><span className="section-label">Model</span><select value={model} onChange={(event) => { setModel(event.target.value); setStale(result !== null); }}><option value="deepseek-v4-pro">deepseek-v4-pro</option><option value="deepseek-chat">deepseek-chat</option><option value="mimo-v2.5">mimo-v2.5</option><option value="mimo-v2.5-pro">mimo-v2.5-pro</option></select></label></>}
          <label className="skill-field"><span className="section-label">Output language</span><select value={language} onChange={(event) => setLanguage(event.target.value as typeof language)}><option value="zh-CN">简体中文</option><option value="en">English</option><option value="auto">Auto</option></select></label>
          <button className="button-primary skill-run" disabled={loading || !brief.trim() || (!inCharacterMode && Boolean(characterInput))} onClick={run}>{loading ? (executionMode === "live" ? "Live model running…" : "Running…") : "Run pipeline"}</button>
          {meta && <p className="skill-note">Provider: {executionMode === "live" ? "live (backend)" : meta.provider_mode}. {executionMode === "live" ? "Credentials stay in the FastAPI environment." : "不会默认调用 live model。"}</p>}
        </section>
        <section className="skill-result-panel" aria-live="polite">
          {loading && executionMode === "live" && <div className="notice" role="status"><strong>Live model running</strong><p>Provider: {provider} · Model: {model}</p><span className="notice-meta">{liveJobStatus === "PENDING" ? "Queued" : "Waiting for provider"} · elapsed {Math.round(liveElapsedMs)} ms</span></div>}
          {error && <div className="notice"><strong>{error.payload.error.code}</strong><p>{error.payload.error.message}</p><span className="notice-meta">stage: {error.payload.error.stage ?? "unknown"}</span></div>}
          {resultIsStale && result && <p className="stale-notice">输入或 Character context 已修改；当前结果是上一次运行的快照。重新 Run 以更新。</p>}
          {!result && !error && <div className="empty-state"><div><strong>Ready to run</strong><span>{inCharacterMode ? "Review the Character context, then run an explicit Skill design." : "Choose a family, describe the intent, then inspect each real pipeline stage."}</span></div></div>}
          {result && <><div className="workspace-header"><div><p className="workspace-kicker">{result.status === "completed" ? "PASS" : "BUSINESS FAILURE"}</p><h2 className="workspace-title">{String(result.semantic_ir?.ability_name ?? "Pipeline result")}</h2><span className="workspace-meta">{result.evaluation.outcome} · {result.provider.outcome}{result.provider.latency_ms !== null ? ` · provider ${Math.round(result.provider.latency_ms)} ms` : ""}{executionMode === "live" && liveElapsedMs > 0 ? ` · total ${Math.round(liveElapsedMs)} ms` : ""}</span></div><div className="workspace-actions"><span className={`status-chip ${result.status}`}>{result.status}</span>{inCharacterMode && "source_context_fingerprint" in result && <><label className="slot-select"><span className="sr-only">Attach Skill slot</span><select aria-label="Attach Skill slot" value={effectiveSlot} onChange={(event) => setSelectedSlot(event.target.value as SkillSlot)} disabled={slotOptions.length === 0}><option value="">Choose slot</option>{slotOptions.map((slot) => <option key={slot.id} value={slot.id}>{slot.label}</option>)}</select></label><button className="button-primary" disabled={!canAttachSkill(result) || resultIsStale || !effectiveSlot} onClick={() => { const slot = slotOptions.find((item) => item.id === effectiveSlot); if (slot) onAttach?.(result, slot); }}>{canAttachSkill(result) ? "Attach to Character" : resultIsStale ? "Attach requires fresh run" : result.evaluation.outcome === "PASS" && alignment?.status === "FAIL" ? "Attach blocked by Character fit" : result.artifact_compatibility && result.artifact_compatibility !== "CURRENT_COMPATIBLE" ? "Attach requires compatible artifact" : "Attach requires PASS"}</button></>}</div></div>{inCharacterMode && alignment && <div className="alignment-summary-grid"><section className="alignment-card"><p className="section-label">Skill Validation</p><div className={`alignment-status ${result.evaluation.outcome === "PASS" ? "passed" : "failed"}`}>{result.evaluation.outcome}</div><p>Internal Skill validity is evaluated independently.</p></section><section className="alignment-card"><p className="section-label">Character Alignment</p><div className={`alignment-status ${alignmentDisplayStatus === "PASS" ? "passed" : alignmentDisplayStatus === "STALE" ? "stale" : "failed"}`}>{alignmentDisplayStatus}</div><p>{resultIsStale ? "Alignment is stale because the Skill or Character context changed; run again." : alignment.summary}</p>{!resultIsStale && alignment.findings.map((finding) => <div className="alignment-finding" key={`${finding.code}-${finding.field_path}`}><strong>{finding.code}</strong><span>{finding.message}</span>{finding.skill_evidence.length > 0 && <small>Evidence: {finding.skill_evidence.map((item) => `${item.role} / ${item.operation}`).join(", ")}</small>}</div>)}</section></div>}<div className="pipeline-list skill-pipeline">{result.pipeline.map((step) => <div className="pipeline-item" key={step.id}><span className={`pipeline-marker ${step.status}`} /><div><strong>{step.label}</strong><p>{step.status}</p></div></div>)}</div><div className="tabs skill-tabs" role="tablist">{(["overview", "ir", "skillkit", "evaluation", "evidence"] as Tab[]).map((item) => <button className="tab" key={item} role="tab" aria-selected={tab === item} onClick={() => setTab(item)}>{item === "ir" ? "Semantic IR" : item === "skillkit" ? "SkillKit" : item[0].toUpperCase() + item.slice(1)}</button>)}</div><div className="tab-panel">{tab === "overview" && <div className="stack"><div className="field-card"><p className="field-name">Input brief</p><p className="field-value">{currentInput?.brief}</p></div><div className="field-card"><p className="field-name">Digest</p><p className="field-value">{String("artifact_digest" in result ? result.artifact_digest : result.evidence.candidate_digest ?? "not generated")}</p></div>{inCharacterMode && <div className="field-card"><p className="field-name">Source context</p><p className="field-value">{resultFingerprint === currentFingerprint ? "CURRENT" : "STALE"}</p></div>}</div>}{tab === "ir" && <pre className="json-view">{pretty(result.semantic_ir)}</pre>}{tab === "skillkit" && <pre className="json-view">{pretty(result.skillkit)}</pre>}{tab === "evaluation" && <div className="stack"><div className={`status-chip ${result.evaluation.outcome === "PASS" ? "passed" : "failed"}`}>{result.evaluation.outcome}</div><pre className="json-view">{pretty(result.evaluation)}</pre></div>}{tab === "evidence" && <><p className="debug-label">Safe evidence only</p><pre className="json-view">{pretty(result.evidence)}</pre></>}</div></>}
        </section>
      </div>
    </Root>
  );
}
