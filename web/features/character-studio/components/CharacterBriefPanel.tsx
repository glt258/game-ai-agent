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
      <h1 id="brief-title" className="column-title">Character Brief</h1>
      <p className="column-subtitle">A focused brief becomes a reviewable character candidate through the existing runtime.</p>
      <label className="section-label" htmlFor="character-brief">Design brief</label>
      <textarea
        id="character-brief"
        className="brief-input"
        value={brief}
        maxLength={12000}
        onChange={(event) => onBriefChange(event.target.value)}
        placeholder="Describe the character you want to explore..."
      />
      <div className="brief-footer">
        <span className="char-count">{brief.length.toLocaleString()} / 12,000</span>
        <button className="button-primary" disabled={loading || !brief.trim()} onClick={onGenerate}>
          {loading ? "Generating..." : "Generate"}
        </button>
      </div>
      <button className="button-ghost" onClick={() => onBriefChange(exampleBrief)}>Load example brief</button>
      <div className="deferred-card">
        <p className="section-label">Advanced Mode</p>
        <p>Reserved for the next slice. This shell sends only fields from the frozen request contract.</p>
      </div>
    </section>
  );
}
