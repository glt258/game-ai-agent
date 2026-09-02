"use client";

import {FormEvent, useCallback, useEffect, useState} from "react";
import {useRouter} from "next/navigation";

import {ApiClientError, apiClient} from "../../lib/api/client";
import type {CanonEntityListResponse, CanonEntityType} from "../../lib/api/types";
import {CanonicalEntityLink} from "./CanonicalEntityLink";

type RequestState = "loading" | "ready" | "error";

function errorFor(caught: unknown, fallback: string): ApiClientError {
  return caught instanceof ApiClientError
    ? caught
    : new ApiClientError({error: {code: "CANON_LIST_ERROR", message: fallback, stage: "frontend", retryable: true, details: {}, audit: null}}, 0);
}

function labelFor(type: CanonEntityType): string {
  return type.replaceAll("_", " ");
}

export function CanonExplorer() {
  const router = useRouter();
  const [list, setList] = useState<CanonEntityListResponse | null>(null);
  const [state, setState] = useState<RequestState>("loading");
  const [error, setError] = useState<ApiClientError | null>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<CanonEntityType | "">("");

  const load = useCallback(async (filters: {q?: string; type?: CanonEntityType} = {}) => {
    setState("loading");
    setError(null);
    try {
      setList(await apiClient.listCanonEntities(filters));
      setState("ready");
    } catch (caught) {
      setError(errorFor(caught, "The Canon index could not be loaded."));
      setState("error");
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(() => load()); }, [load]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void load({q: query.trim() || undefined, type: type || undefined});
  };

  const clear = () => {
    setQuery("");
    setType("");
    void load();
  };

  return (
    <main className="canon-shell">
      <header className="canon-header">
        <div>
          <p className="workspace-kicker">Canonical Knowledge</p>
          <h1 className="workspace-title">Canon Explorer</h1>
          <p className="workspace-meta">Public-safe entities, relationships, and provenance from the project Canon.</p>
        </div>
        <span className="reference-contract">web-canon-entity/0.1</span>
      </header>
      <form className="canon-filters" onSubmit={submit}>
        <label className="canon-search"><span className="section-label">Search Canon</span><input aria-label="Search Canon" className="draft-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, ID, alias, tag..." /></label>
        <label><span className="section-label">Entity type</span><select aria-label="Filter Canon by entity type" className="draft-input" value={type} onChange={(event) => setType(event.target.value as CanonEntityType | "")}><option value="">All types</option>{list?.entity_types.map((item) => <option value={item} key={item}>{labelFor(item)}</option>)}</select></label>
        <div className="reference-filter-actions"><button className="button-primary" type="submit">Search</button><button className="button-secondary" type="button" onClick={clear}>Clear</button></div>
      </form>
      {state === "loading" && <div className="reference-loading loading" role="status"><span className="loading-dot" />Loading Canon entities...</div>}
      {state === "error" && error && <div className="notice" role="alert"><strong>Canon unavailable</strong><p>{error.payload.error.message}</p><span className="notice-meta">{error.payload.error.code}</span><div className="reference-actions"><button className="button-secondary" onClick={() => void load({q: query.trim() || undefined, type: type || undefined})}>Retry</button></div></div>}
      {state === "ready" && list && <section aria-label="Canon entity results"><div className="reference-results-heading"><div><h2 className="subheading">{list.total} entities</h2><p className="workspace-meta">Only public-safe projections are available in this read-only explorer.</p></div></div>{list.entities.length ? <div className="canon-grid">{list.entities.map((entity) => <article className="canon-card" key={`${entity.entity_type}:${entity.entity_id}`}><div className="reference-card-top"><span className="reference-game">{labelFor(entity.entity_type)}</span><span className="status-chip">{entity.relation_count} relations</span></div><h2><CanonicalEntityLink entity_id={entity.entity_id} entity_type={entity.entity_type} display_name={entity.name} /></h2><p className="reference-id">{entity.entity_id}</p><p className="canon-card-summary">{entity.summary}</p>{entity.tags.length > 0 && <div className="tag-row">{entity.tags.slice(0, 5).map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>}</article>)}</div> : <div className="empty-state"><div><strong>No Canon entities match these filters.</strong><span>Try a different name, ID, or entity type.</span></div></div>}</section>}
      <button className="button-ghost canon-studio-link" onClick={() => router.push("/studio")}>← Return to Character Studio</button>
    </main>
  );
}
