import type {CharacterPlannerProjection} from "../../character-planner-view";

function Fact({label, value}: {label: string; value: string}) {
  return <div className="field-card"><p className="field-name">{label}</p><p className={`field-value ${value === "当前结果未提供" ? "muted" : ""}`}>{value}</p></div>;
}

export function CombatView({projection}: {projection: CharacterPlannerProjection}) {
  return (
    <div className="stack" data-testid="character-combat-design">
      <div className="planner-facts">
        <Fact label="战斗定位" value={projection.role} />
        <Fact label="辅助定位" value={projection.secondaryRoles.join("、") || "未指定"} />
        <Fact label="核心玩法" value={projection.combatSummary} />
        <Fact label="主要行为模式" value="当前结果未提供" />
        <Fact label="目标 / 作用对象" value="当前结果未提供" />
        <Fact label="资源机制" value="当前结果未提供" />
        <Fact label="风险 / 节奏" value="当前结果未提供" />
      </div>
      <div className="alignment-summary-grid">
        <section className="alignment-card"><p className="section-label">角色性格</p><div className="tag-row">{projection.personality.map((item) => <span className="tag" key={item}>{item}</span>)}</div><p>仅展示角色与战斗的两个事实，不由前端判断是否一致。</p></section>
        <section className="alignment-card"><p className="section-label">战斗玩法</p><p className="field-value">{projection.combatSummary}</p><p>如需检查一致性，请以服务端设计检查结果为准。</p></section>
      </div>
    </div>
  );
}
