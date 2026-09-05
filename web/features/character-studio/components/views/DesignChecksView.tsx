import type {CharacterGenerationResponse} from "../../../../lib/api/types";
import {projectCharacterPlanner, type CharacterPlannerProjection} from "../../character-planner-view";

function CheckCard({title, status}: {title: string; status: string}) {
  const passed = status === "通过";
  return <div className={`planner-check-card ${passed ? "passed" : status === "未通过" ? "failed" : "unavailable"}`}><span>{title}</span><strong>{status}</strong></div>;
}

export function DesignChecksView({result, affiliationName}: {result: CharacterGenerationResponse; affiliationName: string | null}) {
  const view: CharacterPlannerProjection = projectCharacterPlanner(result, affiliationName);
  return (
    <div className="stack" data-testid="character-design-checks">
      <div className={`planner-check-banner ${view.evaluationStatus === "通过" ? "passed" : view.evaluationStatus === "未通过" ? "failed" : "unavailable"}`}>
        <strong>{view.evaluationStatus === "通过" ? "设计检查通过" : view.evaluationStatus === "未通过" ? "设计检查未通过" : "设计检查未提供"}</strong>
        <span>此处忠实展示角色评估器返回的结果，不在前端新增判断。</span>
      </div>
      <div className="planner-check-grid">
        <CheckCard title="设计检查" status={view.evaluationStatus} />
        <CheckCard title="世界观检查" status={view.canonStatus} />
        <CheckCard title="自动修正" status={view.repairStatus} />
      </div>
      {view.findings.length > 0 ? <div className="stack">{view.findings.map((finding) => <div className="finding-card" key={`${finding.code}-${finding.title}`}><strong>{finding.title}</strong><span>{finding.detail}</span><small>技术代码：{finding.code}</small></div>)}</div> : <div className="field-card"><p className="field-value">没有返回需要处理的设计问题。</p></div>}
    </div>
  );
}
