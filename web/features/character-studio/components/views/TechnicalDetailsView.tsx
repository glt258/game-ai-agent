import type {CharacterGenerationResponse, CharacterValidationResponse} from "../../../../lib/api/types";

function pretty(value: unknown): string { return JSON.stringify(value, null, 2); }

export function TechnicalDetailsView({result, validation}: {result: CharacterGenerationResponse; validation: CharacterValidationResponse | null}) {
  return (
    <div className="stack technical-view" data-testid="character-technical-details">
      <p className="debug-label">技术详情 · 原始协议与调试数据</p>
      <details open><summary>CharacterDraft 原始数据</summary><pre className="json-view">{pretty(result.raw_data.draft)}</pre></details>
      <details><summary>Plan 原始数据</summary><pre className="json-view">{pretty(result.raw_data.plan)}</pre></details>
      <details><summary>Combat 原始数据</summary><pre className="json-view">{pretty(result.combat)}</pre></details>
      <details><summary>Canon Basis 原始数据</summary><pre className="json-view">{pretty(result.canon_basis)}</pre></details>
      <details><summary>Evaluation 与 Validators · 评估检查器</summary><pre className="json-view">{pretty(result.validators)}</pre></details>
      <details><summary>Repair · 自动修正原始数据</summary><pre className="json-view">{pretty(result.repair)}</pre></details>
      <details><summary>ModelInvocationAudit · 模型调用审计</summary><pre className="json-view">{pretty(result.model_invocations)}</pre></details>
      <details><summary>Pipeline · 生成流程</summary><pre className="json-view">{pretty(result.pipeline)}</pre></details>
      <details><summary>Generation Audit · 生成审计</summary><pre className="json-view">{pretty(result.audit)}</pre></details>
      {validation && <details><summary>Edited draft validation · 编辑后检查</summary><pre className="json-view">{pretty(validation)}</pre></details>}
      <div className="field-card">
        <p className="field-name">内部标识</p>
        <div className="technical-id-list"><span>draft_id：{result.draft.draft_id}</span><span>canonical_character_id：{result.draft.canonical_character_id ?? "null"}</span><span>faction_id：{result.draft.faction_id ?? "null"}</span></div>
      </div>
    </div>
  );
}
