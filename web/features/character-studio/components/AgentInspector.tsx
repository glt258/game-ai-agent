import type {ApiClientError} from "../../../lib/api/client";
import type {CharacterGenerationResponse, CharacterValidationResponse, PipelineStep, SavedCharacterHistorySummary, ValidatorResult} from "../../../lib/api/types";
import {validationTarget} from "../studio-state";
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
  return <span className={`status-chip ${status}`}>{status.replaceAll("_", " ")}</span>;
}

function PipelineList({pipeline}: {pipeline: PipelineStep[]}) {
  return (
    <div className="pipeline-list">
      {pipeline.map((step) => (
        <div className="pipeline-item" key={step.id}>
          <span className={`pipeline-marker ${step.status}`} aria-hidden="true" />
          <div><strong>{step.label}</strong><p>{step.detail ?? "No detail provided."}</p></div>
          <StatusChip status={step.status} />
        </div>
      ))}
    </div>
  );
}

function ValidatorList({validators, showTargets = false}: {validators: ValidatorResult[]; showTargets?: boolean}) {
  return (
    <div className="inspector-list">
      {validators.length === 0 && <p className="column-subtitle">No validator findings returned.</p>}
      {validators.map((validator, index) => {
        const target = showTargets ? validationTarget(validator) : null;
        return (
          <div className={`validator-row ${validator.status}`} key={`${validator.name}-${validator.code ?? "summary"}-${index}`}>
            <strong>{validator.name} <StatusChip status={validator.status} /></strong>
            {validator.code && <div className="validator-code">{validator.code}</div>}
            <p>{validator.message}</p>
           {showTargets && target && <div className="validator-target">{target.field ? `Field: ${target.field}` : `Section: ${target.section}`}</div>}
            {showTargets && validator.field_path && <div className="validator-field-path">field_path: {validator.field_path}</div>}
          </div>
        );
      })}
    </div>
  );
}

function ValidationInspector({state, result, error, stale, onRetry}: {state: ValidationState; result: CharacterValidationResponse | null; error: ApiClientError | null; stale: boolean; onRetry: () => void}) {
  return (
    <InspectorSection title="Edited draft validation">
      <div className="validation-summary" aria-live="polite">
        {state === "validating" && <div className="loading"><span className="loading-dot" />Validating edited draft...</div>}
        {state === "passed" && <div className="validation-title" role="status"><strong>EDITED DRAFT VALIDATION PASSED</strong><StatusChip status="passed" /></div>}
        {state === "failed" && <div className="validation-title" role="status"><strong>EDITED DRAFT VALIDATION FAILED</strong><StatusChip status="failed" /></div>}
        {state === "stale" && <div className="stale-notice" role="status">STALE · The last validation result is outdated.</div>}
        {state === "idle" && stale && <div className="stale-notice" role="status">STALE · The last validation result is outdated.</div>}
        {state === "idle" && !stale && <p className="column-subtitle">Edit the draft to enable deterministic validation.</p>}
        {state === "error" && <div className="validation-error"><strong>VALIDATION ERROR</strong><ErrorNotice error={error} onRetry={onRetry} actionLabel="Retry validation" /></div>}
      </div>
      {result && (
        <>
          <div className="validation-counts">
            <span>summary: {result.summary.status}</span>
            <span>{result.summary.failed_count} failed</span>
            <span>{result.summary.warning_count} warnings</span>
            <span>{result.summary.validator_count} validators</span>
          </div>
          <div className="coverage-card">
            <strong>Coverage</strong>
            <span>Schema / representation / request alignment / Canon: available</span>
            <span>Combat validation: partial · Skill shadow: not available</span>
          </div>
          <h3 className="inspector-subheading">Validation pipeline</h3>
          <PipelineList pipeline={result.pipeline} />
          <h3 className="inspector-subheading">Validator results</h3>
          <ValidatorList validators={result.validators} showTargets />
          <h3 className="inspector-subheading">Canon result</h3>
          <div className="canon-summary">
            <div className="audit-row"><span>Status</span><strong><StatusChip status={result.canon.status} /></strong></div>
            <div className="audit-row"><span>Errors / warnings / info</span><strong>{result.canon.summary.errors} / {result.canon.summary.warnings} / {result.canon.summary.infos}</strong></div>
            <div className="audit-row"><span>Checked sources</span><strong>{result.canon.checked_source_ids.join(", ") || "None"}</strong></div>
          </div>
        </>
      )}
    </InspectorSection>
  );
}

export function AgentInspector({result, requestState, error, validationState, validationResult, validationError, validationStale, onRetry, onRetryValidation, history}: AgentInspectorProps) {
  const status = result?.status ?? (requestState === "loading" ? "loading" : requestState === "error" ? "failed" : "idle");
  return (
    <aside className="column column-right" aria-label="Agent inspector">
      <h1 className="column-title">Agent Inspector</h1>
      <p className="column-subtitle">Generation metadata and edited-draft validation from the frozen public contract.</p>

      <InspectorSection title="Generation status">
        {requestState === "loading" ? <div className="loading"><span className="loading-dot" />Generating character...</div> : <StatusChip status={status} />}
        {requestState === "idle" && <p className="column-subtitle" style={{margin: "10px 0 0"}}>No run yet.</p>}
        {requestState === "error" && <div style={{marginTop: "12px"}}><ErrorNotice error={error} onRetry={onRetry} /></div>}
      </InspectorSection>

      {result && (
        <>
          <InspectorSection title="Original generation pipeline"><PipelineList pipeline={result.pipeline} /></InspectorSection>
          <InspectorSection title="Generation validators"><ValidatorList validators={result.validators} /></InspectorSection>
          <InspectorSection title="Repair">
            <div className="audit-row"><span>Status</span><strong><StatusChip status={result.repair.status} /></strong></div>
            <div className="audit-row"><span>Performed</span><strong>{result.repair.repair_performed ? "Yes" : "No repair required"}</strong></div>
            {result.repair.changed_fields.length > 0 && <div className="audit-row"><span>Changed fields</span><strong>{result.repair.changed_fields.join(", ")}</strong></div>}
          </InspectorSection>
          <InspectorSection title="Original model invocation">
            {result.model_invocations.length === 0 ? <p className="column-subtitle" style={{margin: 0}}>No invocation metadata available.</p> : result.model_invocations.map((invocation, index) => (
              <div className="stack" key={`${invocation.purpose}-${index}`}>
                <div className="audit-row"><span>Provider / model</span><strong>{invocation.provider} / {invocation.model}</strong></div>
                <div className="audit-row"><span>Purpose</span><strong>{invocation.purpose}</strong></div>
                <div className="audit-row"><span>Outcome</span><strong>{invocation.outcome}</strong></div>
              </div>
            ))}
          </InspectorSection>
          <ValidationInspector state={validationState} result={validationResult} error={validationError} stale={validationStale} onRetry={onRetryValidation} />
        </>
      )}
      {history.length > 0 && (
        <InspectorSection title="Recorded evaluation history">
          <p className="column-subtitle">Read-only reports recorded by explicit evaluation events.</p>
          <div className="inspector-list">
            {history.map((item) => <div className="audit-row" key={item.report_id}><span>{item.report_family} · {item.status}</span><strong>{new Date(item.created_at).toLocaleString()}</strong></div>)}
          </div>
        </InspectorSection>
      )}
    </aside>
  );
}
