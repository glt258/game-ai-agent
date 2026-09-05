import type {CharacterPlan} from "../../../../lib/api/types";

export function PlanView({plan}: {plan: CharacterPlan | null}) {
  if (!plan) {
    return <div className="empty-state"><div><strong>暂未提供设计规划</strong><span>本次结果没有返回可展示的设计规划。</span></div></div>;
  }
  const intent = plan.parsed_intent;
  return (
    <div className="stack" data-testid="character-design-plan">
      <div className="field-grid">
        <div className="field-card"><p className="field-name">设计类型</p><p className="field-value">{intent.role_type || "未提供"}</p></div>
        <div className="field-card"><p className="field-name">目标受众</p><p className="field-value">{intent.target_audience || "未提供"}</p></div>
        <div className="field-card full"><p className="field-name">设计目标</p><div className="tag-row">{intent.design_goals.length ? intent.design_goals.map((item) => <span className="tag" key={item}>{item}</span>) : <span className="field-value muted">未提供</span>}</div></div>
      </div>
      <div><h3 className="subheading">生成约束</h3><ul className="list">{plan.generation_constraints.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <div><h3 className="subheading">建议特征</h3><div className="tag-row">{plan.recommended_traits.length ? plan.recommended_traits.map((item) => <span className="tag" key={item}>{item}</span>) : <span className="field-value muted">未提供</span>}</div></div>
    </div>
  );
}
