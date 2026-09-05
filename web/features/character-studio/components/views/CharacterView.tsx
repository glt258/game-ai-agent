import type {CharacterPlannerProjection} from "../../character-planner-view";

function Field({name, value, full = false}: {name: string; value: string; full?: boolean}) {
  return <div className={`field-card ${full ? "full" : ""}`}><p className="field-name">{name}</p><p className={`field-value ${value === "未提供" ? "muted" : ""}`}>{value}</p></div>;
}

export function CharacterView({projection}: {projection: CharacterPlannerProjection}) {
  return (
    <div className="character-planner-view" data-testid="character-planner-view">
      <div className="planner-lead">
        <div><p className="field-name">一句话定位</p><p className="planner-summary-text">{projection.designPitch}</p></div>
        <div className="planner-check-grid">
          <div className="planner-check-card passed"><span>战斗定位</span><strong>{projection.role}</strong></div>
          <div className={`planner-check-card ${projection.evaluationStatus === "通过" ? "passed" : "unavailable"}`}><span>设计检查</span><strong>{projection.evaluationStatus}</strong></div>
          <div className={`planner-check-card ${projection.canonStatus === "通过" ? "passed" : "unavailable"}`}><span>世界观检查</span><strong>{projection.canonStatus}</strong></div>
        </div>
      </div>
      <div className="field-grid">
        <Field name="职业" value={projection.identity.occupation} />
        <Field name="社会身份" value={projection.identity.socialRole} />
        <Field name="所属组织" value={projection.identity.affiliation} />
        <Field name="性别" value={projection.identity.gender} />
        <Field name="年龄" value={projection.identity.age} />
        <Field name="年龄范围" value={projection.identity.ageRange} />
        <div className="field-card full"><p className="field-name">性格</p><div className="tag-row">{projection.personality.map((item) => <span className="tag" key={item}>{item}</span>)}</div></div>
        <Field name="背景经历" value={projection.background} full />
        <Field name="剧情钩子" value={projection.storyHook} full />
        <Field name="能力构想" value={projection.abilityConcept} full />
        <Field name="核心玩法" value={projection.combatSummary} full />
      </div>
    </div>
  );
}
