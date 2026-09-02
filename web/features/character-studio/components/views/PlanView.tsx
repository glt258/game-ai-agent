import type {CharacterPlan} from "../../../../lib/api/types";

export function PlanView({plan}: {plan: CharacterPlan | null}) {
  if (!plan) {
    return <div className="empty-state"><div><strong>Plan unavailable for this result.</strong><span>The backend did not return a plan in this response.</span></div></div>;
  }
  const intent = plan.parsed_intent;
  return (
    <div className="stack">
      <div className="field-grid">
        <div className="field-card"><p className="field-name">Role type</p><p className="field-value">{intent.role_type}</p></div>
        <div className="field-card"><p className="field-name">Target audience</p><p className="field-value">{intent.target_audience}</p></div>
        <div className="field-card full"><p className="field-name">Design goals</p><div className="tag-row">{intent.design_goals.map((item) => <span className="tag" key={item}>{item}</span>)}</div></div>
      </div>
      <div><h3 className="subheading">Generation constraints</h3><ul className="list">{plan.generation_constraints.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <div><h3 className="subheading">Recommended traits</h3><div className="tag-row">{plan.recommended_traits.map((item) => <span className="tag" key={item}>{item}</span>)}</div></div>
    </div>
  );
}
