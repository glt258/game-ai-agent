"use client";

import {FormEvent, useCallback, useEffect, useState} from "react";

import {ApiClientError, apiClient} from "../../lib/api/client";
import type {ReferenceCharacterDetailResponse, ReferenceCharacterListResponse} from "../../lib/api/types";

type RequestState = "loading" | "ready" | "error";
type DetailTab = "overview" | "facts" | "abilities" | "combat" | "sources";

const tabs: Array<{id: DetailTab; label: string}> = [
  {id: "overview", label: "Overview"},
  {id: "facts", label: "Facts"},
  {id: "abilities", label: "Abilities"},
  {id: "combat", label: "Combat Analysis"},
  {id: "sources", label: "Sources"},
];

function display(value: string | null | undefined, fallback = "Unavailable") {
  return value?.trim() ? value : fallback;
}

function ErrorPanel({error, onRetry}: {error: ApiClientError; onRetry: () => void}) {
  return (
    <div className="notice" role="alert">
      <strong>Reference corpus unavailable</strong>
      <p>{error.payload.error.message}</p>
      <span className="notice-meta">{error.payload.error.code}</span>
      <div className="reference-actions"><button className="button-secondary" onClick={onRetry}>Retry</button></div>
    </div>
  );
}

function TagList({items, empty = "Unavailable"}: {items: string[]; empty?: string}) {
  return items.length ? <div className="tag-row">{items.map((item) => <span className="tag" key={item}>{item}</span>)}</div> : <span className="field-value muted">{empty}</span>;
}

function Field({name, value}: {name: string; value: string | null | undefined}) {
  return <div className="field-card"><p className="field-name">{name}</p><p className={`field-value ${value ? "" : "muted"}`}>{display(value)}</p></div>;
}

function DetailPanel({detail, onBack}: {detail: ReferenceCharacterDetailResponse; onBack: () => void}) {
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const {identity, facts, abilities, combat_analysis, sources, metadata} = detail;
  const analysis = combat_analysis?.combat;

  return (
    <section className="reference-detail" aria-labelledby="reference-detail-title">
      <button className="button-ghost reference-back" onClick={onBack}>← Back to Characters</button>
      <div className="reference-detail-header">
        <div>
          <p className="workspace-kicker">Reference Corpus Record</p>
          <h1 id="reference-detail-title" className="workspace-title">{identity.canonical_name}</h1>
          <p className="workspace-meta">{identity.game_name} · {detail.reference_id}</p>
        </div>
        <div className="reference-localized" aria-label="Localized names">
          {Object.entries(identity.localized_names).map(([language, name]) => <span className="tag" key={language}>{language}: {name}</span>)}
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="Reference character detail tabs">
        {tabs.map((tab) => <button key={tab.id} className="tab" role="tab" aria-selected={activeTab === tab.id} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
      </div>

      <div className="tab-panel">
        {activeTab === "overview" && <div className="stack">
          <div className="field-grid">
            <Field name="Game / IP" value={identity.game_name} />
            <Field name="Native character ID" value={identity.native_character_id} />
            <Field name="Release version" value={identity.release?.version} />
            <Field name="Release date" value={identity.release?.date} />
            <Field name="Rarity (native)" value={identity.rarity?.native_value === null || identity.rarity?.native_value === undefined ? null : String(identity.rarity.native_value)} />
            <Field name="Verification" value={metadata.verification_status} />
          </div>
          <div className="field-card full"><p className="field-name">Corpus coverage</p><p className="field-value">Facts: available · Abilities: {abilities.length ? "available" : "not provided"} · Analysis: {combat_analysis ? "available" : "not provided"} · Sources: {sources.length ? "available" : "not provided"}</p></div>
          <div className="field-card full"><p className="field-name">Record metadata</p><p className="field-value muted">{metadata.facts_schema_version} · {metadata.analysis_schema_version ?? "No analysis schema"} · {metadata.sources_schema_version}</p></div>
        </div>}

        {activeTab === "facts" && <div className="stack">
          <div className="field-grid">
            <Field name="Faction / affiliation" value={facts.narrative.faction} />
            <Field name="Occupation" value={facts.narrative.occupation} />
            <Field name="Public identity" value={facts.narrative.public_identity} />
            <div className="field-card"><p className="field-name">Affiliations</p><TagList items={facts.narrative.affiliations} /></div>
          </div>
          <div className="field-card"><p className="field-name">Native combat taxonomy</p><div className="stack compact-stack">{Object.entries(facts.combat.native_taxonomy).map(([key, value]) => <div className="audit-row" key={key}><span>{key}</span><strong>{Array.isArray(value) ? value.join(", ") : value}</strong></div>)}{!Object.keys(facts.combat.native_taxonomy).length && <span className="field-value muted">Unavailable</span>}</div></div>
          <div className="field-grid">
            <div className="field-card"><p className="field-name">Official visual tags</p><TagList items={facts.presentation.official_visual_tags} /></div>
            <div className="field-card"><p className="field-name">Character keywords</p><TagList items={facts.presentation.official_character_keywords} /></div>
          </div>
        </div>}

        {activeTab === "abilities" && <div className="stack">
          {abilities.length ? abilities.map((ability) => <article className="field-card" key={ability.ability_id}><div className="audit-row"><span>{ability.native_name ?? ability.ability_id}</span><strong>{ability.native_category}</strong></div><p className="field-value muted">{display(ability.description_summary)}</p>{ability.normalized_category && <span className="tag">{ability.normalized_category}</span>}</article>) : <div className="empty-state compact-empty"><div><strong>No ability facts available for this record.</strong><span>The corpus record is valid but does not provide structured ability entries.</span></div></div>}
        </div>}

        {activeTab === "combat" && <div className="stack">
          {!analysis ? <div className="empty-state compact-empty"><div><strong>Combat analysis unavailable.</strong><span>This record has facts and sources, but no structured analysis projection.</span></div></div> : <>
            <div className="field-grid">
              <div className="field-card"><p className="field-name">Normalized roles</p><TagList items={analysis.normalized_roles} /></div>
              <div className="field-card"><p className="field-name">Combat roles</p><TagList items={analysis.combat_roles} /></div>
              <Field name="Attack range" value={analysis.attack_range} />
              <Field name="Field time" value={analysis.field_time} />
              <Field name="Execution difficulty" value={analysis.execution_difficulty} />
              <Field name="Team dependency" value={analysis.team_dependency} />
            </div>
            <div className="field-grid">
              <div className="field-card"><p className="field-name">Damage patterns</p><TagList items={analysis.damage_patterns} /></div>
              <div className="field-card"><p className="field-name">Core mechanics</p><TagList items={analysis.core_mechanics} /></div>
            </div>
            <div className="field-card full"><p className="field-name">Primary loop</p><p className="field-value">{display(analysis.primary_loop.summary)}</p><ol className="list">{analysis.primary_loop.steps.map((step) => <li key={step}>{step}</li>)}</ol></div>
          </>}
        </div>}

        {activeTab === "sources" && <div className="stack">
          {sources.length ? sources.map((source) => <article className="field-card" key={source.source_id}><div className="audit-row"><span>{source.source_type} · {source.reliability}</span><strong>{source.source_id}</strong></div><h2 className="subheading">{display(source.title, source.publisher ?? "Untitled source")}</h2><div className="audit-row"><span>Language</span><strong>{display(source.language)}</strong></div><div className="audit-row"><span>Version</span><strong>{display(source.version_context)}</strong></div><a className="reference-source-link" href={source.url} target="_blank" rel="noopener noreferrer">Open public source ↗</a></article>) : <div className="empty-state compact-empty"><div><strong>No source records available.</strong><span>This record does not expose a source link.</span></div></div>}
        </div>}
      </div>
      {metadata.warnings.length > 0 && <p className="context-notice" role="note">Corpus notes: {metadata.warnings.join(" · ")}</p>}
    </section>
  );
}

export function ReferenceCharactersBrowser() {
  const [list, setList] = useState<ReferenceCharacterListResponse | null>(null);
  const [listState, setListState] = useState<RequestState>("loading");
  const [listError, setListError] = useState<ApiClientError | null>(null);
  const [query, setQuery] = useState("");
  const [ip, setIp] = useState("");
  const [role, setRole] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReferenceCharacterDetailResponse | null>(null);
  const [detailState, setDetailState] = useState<RequestState>("ready");
  const [detailError, setDetailError] = useState<ApiClientError | null>(null);

  const loadList = useCallback(async (filters: {q?: string; ip?: string; combat_role?: string} = {}) => {
    setListState("loading");
    setListError(null);
    try {
      setList(await apiClient.listReferenceCharacters(filters));
      setListState("ready");
    } catch (caught) {
      const error = caught instanceof ApiClientError ? caught : new ApiClientError({error: {code: "REFERENCE_LIST_ERROR", message: "The reference corpus could not be loaded.", stage: "frontend", retryable: true, details: {}, audit: null}}, 0);
      setListError(error);
      setListState("error");
    }
  }, []);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) void loadList();
    });
    return () => { active = false; };
  }, [loadList]);

  const submitFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSelectedId(null);
    setDetail(null);
    void loadList({q: query.trim() || undefined, ip: ip.trim() || undefined, combat_role: role || undefined});
  };

  const openDetail = async (referenceId: string) => {
    setSelectedId(referenceId);
    setDetail(null);
    setDetailError(null);
    setDetailState("loading");
    try {
      setDetail(await apiClient.getReferenceCharacter(referenceId));
      setDetailState("ready");
    } catch (caught) {
      const error = caught instanceof ApiClientError ? caught : new ApiClientError({error: {code: "REFERENCE_DETAIL_ERROR", message: "The reference record could not be loaded.", stage: "frontend", retryable: true, details: {}, audit: null}}, 0);
      setDetailError(error);
      setDetailState("error");
    }
  };

  const resetFilters = () => {
    setQuery("");
    setIp("");
    setRole("");
    setSelectedId(null);
    setDetail(null);
    void loadList();
  };

  return (
    <main className="reference-shell">
      <header className="reference-header"><div><p className="workspace-kicker">Reference Corpus</p><h1 className="workspace-title">Characters</h1><p className="workspace-meta">Read-only, source-grounded records for comparison and authoring context.</p></div><span className="reference-contract">web-reference-character/0.1</span></header>
      {selectedId && detailState === "ready" && detail ? <DetailPanel detail={detail} onBack={() => { setSelectedId(null); setDetail(null); }} /> : <>
        <form className="reference-filters" onSubmit={submitFilters}>
          <label className="reference-search"><span className="section-label">Search</span><input aria-label="Search characters" className="draft-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, game, affiliation..." /></label>
          <label><span className="section-label">IP / game</span><input aria-label="Filter by IP or game" className="draft-input" value={ip} onChange={(event) => setIp(event.target.value)} placeholder="Zenless Zone Zero" /></label>
          <label><span className="section-label">Combat role</span><select aria-label="Filter by combat role" className="draft-input" value={role} onChange={(event) => setRole(event.target.value)}><option value="">All roles</option><option value="on_field_dps">On-field DPS</option><option value="off_field_dps">Off-field DPS</option><option value="burst_dps">Burst DPS</option><option value="support">Support</option><option value="sustain">Sustain</option><option value="control">Control</option><option value="hybrid">Hybrid</option></select></label>
          <div className="reference-filter-actions"><button className="button-primary" type="submit">Search</button><button className="button-secondary" type="button" onClick={resetFilters}>Clear</button></div>
        </form>
        {listState === "loading" && <div className="reference-loading loading" role="status"><span className="loading-dot" />Loading reference characters...</div>}
        {listState === "error" && listError && <ErrorPanel error={listError} onRetry={() => void loadList({q: query.trim() || undefined, ip: ip.trim() || undefined, combat_role: role || undefined})} />}
        {listState === "ready" && list && <section aria-label="Reference character results"><div className="reference-results-heading"><div><h2 className="subheading">{list.total} records</h2><p className="workspace-meta">Frozen corpus summaries; open a record for facts, analysis and sources.</p></div></div>{list.characters.length ? <div className="reference-grid">{list.characters.map((character) => <button className="reference-card" key={character.reference_id} onClick={() => void openDetail(character.reference_id)}><div className="reference-card-top"><span className="reference-game">{character.game_name}</span><span className="status-chip">{character.verification_status}</span></div><h2>{character.display_name}</h2><p className="reference-id">{character.reference_id}</p><p className="reference-faction">{display(character.faction, "Affiliation not provided")}</p><div className="tag-row"><TagList items={character.combat_roles} empty="Role not classified" /><TagList items={character.ability_categories.slice(0, 3)} empty="No ability facts" /></div></button>)}</div> : <div className="empty-state"><div><strong>No reference characters match these filters.</strong><span>Try a different name, IP, or combat role.</span></div></div>}</section>}
      </>}
      {selectedId && detailState === "loading" && <div className="reference-detail-loading loading" role="status"><span className="loading-dot" />Loading record...</div>}
      {selectedId && detailState === "error" && detailError && <ErrorPanel error={detailError} onRetry={() => void openDetail(selectedId)} />}
    </main>
  );
}
