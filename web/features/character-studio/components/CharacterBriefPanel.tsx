interface CharacterBriefPanelProps {
  brief: string;
  loading: boolean;
  exampleBrief: string;
  onBriefChange: (value: string) => void;
  onGenerate: () => void;
}

export function CharacterBriefPanel({brief, loading, exampleBrief, onBriefChange, onGenerate}: CharacterBriefPanelProps) {
  return (
    <section className="column column-left" aria-labelledby="brief-title">
      <h1 id="brief-title" className="column-title">角色设计需求</h1>
      <p className="column-subtitle">填写角色需求，生成可直接评审的角色方案。</p>
      <label className="section-label" htmlFor="character-brief">设计需求</label>
      <textarea
        id="character-brief"
        className="brief-input"
        value={brief}
        maxLength={12000}
        onChange={(event) => onBriefChange(event.target.value)}
        placeholder="描述你想设计的角色……"
      />
      <div className="brief-footer">
        <span className="char-count">{brief.length.toLocaleString()} / 12,000</span>
        <button className="button-primary" disabled={loading || !brief.trim()} onClick={onGenerate}>
          {loading ? "正在生成…" : "生成角色"}
        </button>
      </div>
      <button className="button-ghost" onClick={() => onBriefChange(exampleBrief)}>加载示例需求</button>
      <div className="deferred-card">
        <p className="section-label">高级设置</p>
        <p>高级设置暂未开放。当前页面只提交既定的角色设计需求字段。</p>
      </div>
    </section>
  );
}
