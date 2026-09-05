import type {CanonBasis} from "../../../../lib/api/types";

const SOURCE_LABELS: Record<string, string> = {faction: "组织设定", character: "角色设定", lore: "世界观设定", story: "剧情设定", project: "项目设定", case: "事件设定", incident: "事件记录"};

export function CanonBasisView({basis, affiliationId, affiliationName}: {basis: CanonBasis[]; affiliationId: string | null; affiliationName: string | null}) {
  return (
    <div className="stack" data-testid="character-canon-basis">
      <p className="column-subtitle">这里展示本角色使用的世界观依据；内部引用编号收在技术详情中。</p>
      {basis.length === 0 ? <div className="empty-state"><div><strong>暂未返回世界观依据</strong><span>本次结果没有可展示的来源投影。</span></div></div> : basis.map((item) => {
        const isAffiliation = item.source_id === affiliationId && affiliationName;
        return <article className="field-card" key={`${item.source_type ?? "source"}-${item.source_id}`}>
          <p className="field-name">{SOURCE_LABELS[item.source_type ?? ""] ?? "相关世界观资料"}</p>
          <p className="field-value">{isAffiliation ? affiliationName : "与本角色相关的世界观依据"}</p>
          <p className="field-value muted">支持：{item.supports.join("、") || "未提供"}</p>
          <details className="technical-inline"><summary>查看技术引用</summary><div className="technical-id-list"><span>source_id：{item.source_id}</span><span>source_type：{item.source_type ?? "null"}</span></div></details>
        </article>;
      })}
    </div>
  );
}
