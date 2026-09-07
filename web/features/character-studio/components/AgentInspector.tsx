import type {ApiClientError} from "../../../lib/api/client";
import type {CharacterGenerationResponse, CharacterValidationResponse, PipelineStep, SavedCharacterHistorySummary, ValidatorResult} from "../../../lib/api/types";
import {validationTarget} from "../studio-state";
import {plannerStatus, statusLabel} from "../character-planner-view";
import {ErrorNotice} from "./ErrorNotice";

type ValidationState = "idle" | "validating" | "passed" | "failed" | "error" | "stale";

interface AgentInspectorProps {
  result: CharacterGenerationResponse | null;
  requestState: "idle" | "loading" | "success" | "error";
  error: ApiClientError | null;
  validationState: ValidationState;
  validationResult: CharacterValidationResponse | null;
  validationError: ApiClientError | null;
  validationStale: boolean;
  onRetry: () => void;
  onRetryValidation: () => void;
  history: SavedCharacterHistorySummary[];
}

function InspectorSection({title, children}: {title: string; children: React.ReactNode}) {
  return <section className="inspector-section"><div className="inspector-heading"><h2>{title}</h2></div>{children}</section>;
}

function StatusChip({status}: {status: string}) {
  return <span className={`status-chip ${status}`}>{statusLabel(status)}</span>;
}

function PipelineList({pipeline}: {pipeline: PipelineStep[]}) {
  return (
    <div className="pipeline-list">
      {pipeline.map((step) => (
        <div className="pipeline-item" key={step.id}>
          <span className={`pipeline-marker ${step.status}`} aria-hidden="true" />
          <div><strong>{step.label}</strong><p>{step.detail ?? "未提供明细。"}</p></div>
          <StatusChip status={step.status} />
        </div>
      ))}
    </div>
  );
}

function ValidatorList({validators, showTargets = false}: {validators: ValidatorResult[]; showTargets?: boolean}) {
  return (
    <div className="inspector-list">
      {validators.length === 0 && <p className="column-subtitle">未返回检查发现。</p>}
      {validators.map((validator, index) => {
        const target = showTargets ? validationTarget(validator) : null;
        return (
          <div className={`validator-row ${validator.status}`} key={`${validator.name}-${validator.code ?? "summary"}-${index}`}>
            <strong>{validator.name} <StatusChip status={validator.status} /></strong>
            {validator.code && <div className="validator-code">{validator.code}</div>}
            <p>{validator.message}</p>
           {showTargets && target && <div className="validator-target">{target.field ? `字段：${target.field}` : `区域：${target.section}`}</div>}
            {showTargets && validator.field_path && <div className="validator-field-path">field_path: {validator.field_path}</div>}
          </div>
        );
      })}
    </div>
  );
}

function ValidationInspector({state, result, error, stale, onRetry}: {state: ValidationState; result: CharacterValidationResponse | null; error: ApiClientError | null; stale: boolean; onRetry: () => void}) {
  return (
    <InspectorSection title="编辑后检查">
      <div className="validation-summary" aria-live="polite">
        {state === "validating" && <div className="loading"><span className="loading-dot" />正在检查修改…</div>}
        {state === "passed" && <div className="validation-title" role="status"><strong>修改后的方案检查通过</strong><StatusChip status="passed" /></div>}
        {state === "failed" && <div className="validation-title" role="status"><strong>修改后的方案检查未通过</strong><StatusChip status="failed" /></div>}
        {state === "stale" && <div className="stale-notice" role="status">上一次检查结果已过期。</div>}
        {state === "idle" && stale && <div className="stale-notice" role="status">上一次检查结果已过期。</div>}
        {state === "idle" && !stale && <p className="column-subtitle">编辑角色方案后，可以发起一次服务端检查。</p>}
        {state === "error" && <div className="validation-error"><strong>检查失败</strong><ErrorNotice error={error} onRetry={onRetry} actionLabel="重新检查" /></div>}
      </div>
      {result && (
        <>
          <div className="validation-counts">
            <span>结果：{statusLabel(result.summary.status)}</span>
            <span>{result.summary.failed_count} 项未通过</span>
            <span>{result.summary.warning_count} 项需关注</span>
            <span>{result.summary.validator_count} 项检查</span>
          </div>
          <div className="coverage-card">
            <strong>检查范围</strong>
            <span>结构、内容表达、需求匹配与世界观：已提供</span>
            <span>战斗检查：部分提供 · 技能影子检查：未提供</span>
          </div>
          <h3 className="inspector-subheading">检查流程</h3>
          <PipelineList pipeline={result.pipeline} />
          <h3 className="inspector-subheading">检查结果</h3>
          <ValidatorList validators={result.validators} showTargets />
          <h3 className="inspector-subheading">世界观检查结果</h3>
          <div className="canon-summary">
              <div className="audit-row"><span>状态</span><strong><StatusChip status={result.canon.status} /></strong></div>
            <div className="audit-row"><span>错误 / 需关注 / 提示</span><strong>{result.canon.summary.errors} / {result.canon.summary.warnings} / {result.canon.summary.infos}</strong></div>
            <div className="audit-row"><span>已检查来源</span><strong>{result.canon.checked_source_ids.join(", ") || "无"}</strong></div>
          </div>
        </>
      )}
    </InspectorSection>
  );
}

export function AgentInspector({result, requestState, error, validationState, validationResult, validationError, validationStale, onRetry, onRetryValidation, history}: AgentInspectorProps) {
  const invocations = result?.model_invocations ?? [];
  const status = result?.status ?? (requestState === "loading" ? "loading" : requestState === "error" ? "failed" : "idle");
  const evaluationStatus = plannerStatus(result?.pipeline.find((step) => step.id === "evaluation")?.status);
  const canonStatus = plannerStatus(result?.pipeline.find((step) => step.id === "canon")?.status);
  return (
    <aside className="column column-right" aria-label="设计检查">
      <h1 className="column-title">设计检查</h1>
      <p className="column-subtitle">查看角色方案的生成状态、设计检查和世界观检查。</p>

      <InspectorSection title="生成状态">
        {requestState === "loading" ? <div className="loading"><span className="loading-dot" />正在生成角色方案…</div> : <StatusChip status={status} />}
        {requestState === "idle" && <p className="column-subtitle" style={{margin: "10px 0 0"}}>尚未生成方案。</p>}
        {requestState === "error" && <div style={{marginTop: "12px"}}><ErrorNotice error={error} onRetry={onRetry} actionLabel="重新生成" /></div>}
      </InspectorSection>

      {result && (
        <>
          <InspectorSection title="检查结论">
            <div className="planner-check-grid"><div className={`planner-check-card ${evaluationStatus === "通过" ? "passed" : evaluationStatus === "未通过" ? "failed" : "unavailable"}`}><span>设计检查</span><strong>{evaluationStatus}</strong></div><div className={`planner-check-card ${canonStatus === "通过" ? "passed" : canonStatus === "未通过" ? "failed" : "unavailable"}`}><span>世界观检查</span><strong>{canonStatus}</strong></div><div className="planner-check-card"><span>自动修正</span><strong>{statusLabel(result.repair.status)}</strong></div></div>
          </InspectorSection>
          <details className="technical-inspector"><summary>查看生成与检查明细</summary>
            <div className="technical-inspector-body">
              <InspectorSection title="原始生成流程"><PipelineList pipeline={result.pipeline} /></InspectorSection>
              <InspectorSection title="生成检查项"><ValidatorList validators={result.validators} /></InspectorSection>
              <InspectorSection title="自动修正">
                <div className="audit-row"><span>状态</span><strong><StatusChip status={result.repair.status} /></strong></div>
                <div className="audit-row"><span>是否执行</span><strong>{result.repair.repair_performed ? "已执行" : "无需修正"}</strong></div>
                {result.repair.changed_fields.length > 0 && <div className="audit-row"><span>修改字段</span><strong>{result.repair.changed_fields.join(", ")}</strong></div>}
              </InspectorSection>
              <InspectorSection title="模型调用记录">
                {invocations.length === 0 ? <p className="column-subtitle" style={{margin: 0}}>没有可用的调用记录。</p> : invocations.map((invocation, index) => (
                  <div className="stack" key={`${invocation.purpose}-${index}`}>
                    <div className="audit-row"><span>Provider / 模型</span><strong>{invocation.provider} / {invocation.model}</strong></div>
                    <div className="audit-row"><span>用途</span><strong>{invocation.purpose}</strong></div>
                    <div className="audit-row"><span>结果</span><strong>{invocation.outcome}</strong></div>
                    <div className="audit-row"><span>延迟 / 重试</span><strong>{invocation.latency_ms === null ? "未报告" : `${Math.round(invocation.latency_ms)} ms`} / {invocation.retry_count}</strong></div>
                    <div className="audit-row"><span>Token 用量</span><strong>{invocation.usage ? `${invocation.usage.input_tokens ?? "?"} in / ${invocation.usage.output_tokens ?? "?"} out / ${invocation.usage.total_tokens ?? "?"} total` : "未报告"}</strong></div>
                    <div className="audit-row"><span>尝试次数</span><strong>{invocation.attempts.length || (invocation.retry_count + 1)}</strong></div>
                  </div>
                ))}
                {result.usage_summary && <div className="audit-row"><span>用量汇总</span><strong>{result.usage_summary.complete ? "完整" : "部分/未知"} · {result.usage_summary.known_total_tokens ?? "未报告"} total</strong></div>}
              </InspectorSection>
              <ValidationInspector state={validationState} result={validationResult} error={validationError} stale={validationStale} onRetry={onRetryValidation} />
            </div>
          </details>
        </>
      )}
      {history.length > 0 && (
        <InspectorSection title="检查历史">
          <p className="column-subtitle">由明确检查操作记录的只读报告。</p>
          <div className="inspector-list">
            {history.map((item) => <div className="audit-row" key={item.report_id}><span>{item.report_family} · {item.status}</span><strong>{new Date(item.created_at).toLocaleString()}</strong></div>)}
          </div>
        </InspectorSection>
      )}
    </aside>
  );
}
