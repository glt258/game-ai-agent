interface CharacterBriefPanelProps {
  brief: string;
  loading: boolean;
  executionMode: "offline" | "live";
  exampleBrief: string;
  onBriefChange: (value: string) => void;
  onExecutionModeChange: (value: "offline" | "live") => void;
  onGenerate: () => void;
}

export function CharacterBriefPanel({brief, loading, executionMode, exampleBrief, onBriefChange, onExecutionModeChange, onGenerate}: CharacterBriefPanelProps) {
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
        <label className="skill-field"><span className="section-label">生成方式</span><select aria-label="生成方式" value={executionMode} onChange={(event) => onExecutionModeChange(event.target.value as "offline" | "live")}><option value="offline">离线示例</option><option value="live">AI 生成</option></select></label>
        <p>{executionMode === "live" ? "AI 生成通过后台任务执行，凭据保留在 FastAPI 环境中。" : "当前使用离线示例，不会调用 live model。"}</p>
      </div>
    </section>
  );
}
