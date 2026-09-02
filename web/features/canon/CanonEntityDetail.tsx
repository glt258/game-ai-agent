"use client";

import {useCallback, useEffect, useState} from "react";
import Link from "next/link";

import {ApiClientError, apiClient} from "../../lib/api/client";
import type {CanonEntityDetailResponse} from "../../lib/api/types";
import {CanonicalEntityLink, isCanonEntityType} from "./CanonicalEntityLink";

function display(value: string | null | undefined, fallback = "Not provided") {
  return value?.trim() ? value : fallback;
}

function TagList({items}: {items: string[]}) {
  return items.length ? <div className="tag-row">{items.map((item) => <span className="tag" key={item}>{item}</span>)}</div> : <span className="field-value muted">Not provided</span>;
}

function Field({name, value}: {name: string; value: string | null | undefined}) {
  return <div className="field-card"><p className="field-name">{name}</p><p className={`field-value ${value ? "" : "muted"}`}>{display(value)}</p></div>;
}

function ErrorPanel({error, onRetry}: {error: ApiClientError; onRetry: () => void}) {
  return <div className="notice" role="alert"><strong>Canon entity unavailable</strong><p>{error.payload.error.message}</p><span className="notice-meta">{error.payload.error.code}</span><div className="reference-actions"><button className="button-secondary" onClick={onRetry}>Retry</button></div></div>;
}

function DetailBody({detail}: {detail: CanonEntityDetailResponse}) {
  const faction = detail.sections.faction;
  const lore = detail.sections.lore;
  const character = detail.sections.character;
  const story = detail.sections.story;
  const registry = detail.sections.project ?? detail.sections.case ?? detail.sections.incident;
  return <div className="stack">
    <div className="field-grid">
      <Field name="Entity type" value={detail.entity_type} />
      <Field name="Visibility" value={detail.visibility} />
      <Field name="Canonical ID" value={detail.entity_id} />
      <Field name="Aliases" value={detail.aliases.join(", ")} />
    </div>
    <div className="field-card full"><p className="field-name">Summary</p><p className="field-value">{detail.summary}</p></div>
    {faction && <><div className="detail-section-heading"><h2>Faction profile</h2></div><div className="field-grid"><Field name="Type" value={faction.faction_type} /><Field name="Status" value={faction.status} /><Field name="Core function" value={faction.core_function.description} /><Field name="Public identity" value={faction.public_identity.description} /><Field name="Public reputation" value={faction.public_reputation.description} /><div className="field-card"><p className="field-name">Typical member roles</p><TagList items={faction.member_profile.typical_roles} /></div><Field name="Recruitment context" value={faction.member_profile.recruitment_description} /><Field name="Culture" value={faction.member_profile.culture} /></div></>}
    {lore && <><div className="detail-section-heading"><h2>Public lore</h2></div><div className="field-grid"><Field name="Title" value={lore.title} /><Field name="Canon level" value={lore.canon_level} /><Field name="Category" value={lore.category} /><Field name="Sensitivity" value={lore.sensitivity} /><Field name="Statement" value={lore.statement} /></div></>}
    {character && <><div className="detail-section-heading"><h2>Canonical character</h2></div><div className="field-grid"><Field name="Occupation" value={character.occupation} /><Field name="Combat role" value={character.combat_role} /><Field name="First impression" value={character.first_impression} /><Field name="Public reputation" value={character.public_reputation} />{character.faction_id && <div className="field-card"><p className="field-name">Faction</p><CanonicalEntityLink entity_id={character.faction_id} entity_type="faction" display_name={character.faction_id} /></div>}</div></>}
    {registry && <><div className="detail-section-heading"><h2>Registry entry</h2></div><div className="field-grid"><Field name="Name" value={registry.name} /><Field name="Status" value={registry.status} /><Field name="Description" value={registry.description} /></div></>}
    {story && <><div className="detail-section-heading"><h2>Story canon</h2></div><div className="field-grid"><Field name="Canon status" value={story.canon_status} /><Field name="Setting" value={[story.city_id, story.district_name].filter(Boolean).join(" · ")} /><Field name="Premise" value={story.premise} /></div><div className="field-card full"><p className="field-name">Objective facts</p><ol className="list">{story.objective_facts.map((item) => <li key={item}>{item}</li>)}</ol></div></>}
    <div className="field-card full"><p className="field-name">Tags</p><TagList items={detail.tags} /></div>
    <div className="detail-section-heading"><h2>Relationships</h2><span className="workspace-meta">Outgoing links preserve source direction.</span></div>
    {detail.relationships.length ? <div className="relationship-list">{detail.relationships.map((relation) => <article className="field-card relationship-card" key={`${relation.relation_type}:${relation.target_entity_id}`}><div className="audit-row"><span>{relation.direction} · {relation.relation_type}</span><strong>{relation.status ?? "linked"}</strong></div>{relation.available && isCanonEntityType(relation.target_entity_type) ? <CanonicalEntityLink entity_id={relation.target_entity_id} entity_type={relation.target_entity_type} display_name={relation.target_name} /> : <p className="field-value">{relation.target_name} <span className="muted">({relation.target_entity_id})</span></p>}{relation.description && <p className="field-value muted">{relation.description}</p>}</article>)}</div> : <div className="empty-state compact-empty"><div><strong>No outgoing relationships.</strong><span>This public entity does not expose navigable related records.</span></div></div>}
    <div className="detail-section-heading"><h2>Provenance</h2></div>
    {detail.provenance.length ? <div className="stack">{detail.provenance.map((source, index) => <article className="field-card" key={`${source.source_type}:${index}`}><div className="audit-row"><span>Source type</span><strong>{source.source_type}</strong></div>{source.references.length > 0 && <div className="audit-row"><span>References</span><strong>{source.references.join(", ")}</strong></div>}</article>)}</div> : <div className="field-value muted">No public provenance details provided.</div>}
  </div>;
}

export function CanonEntityDetail({entityId}: {entityId: string}) {
  const [detail, setDetail] = useState<CanonEntityDetailResponse | null>(null);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    void apiClient.getCanonEntity(entityId).then(setDetail).catch((caught: unknown) => {
      setError(caught instanceof ApiClientError ? caught : new ApiClientError({error: {code: "CANON_DETAIL_ERROR", message: "The Canon entity could not be loaded.", stage: "frontend", retryable: true, details: {}, audit: null}}, 0));
    }).finally(() => setLoading(false));
  }, [entityId]);

  useEffect(() => { void Promise.resolve().then(() => load()); }, [load]);

  return <main className="canon-shell canon-detail-shell"><Link className="button-ghost reference-back" href="/canon">← Back to Canon</Link>{loading && <div className="reference-loading loading" role="status"><span className="loading-dot" />Loading Canon entity...</div>}{error && <ErrorPanel error={error} onRetry={load} />}{detail && !loading && !error && <><header className="reference-detail-header"><div><p className="workspace-kicker">{detail.entity_type} · public Canon</p><h1 className="workspace-title">{detail.name}</h1><p className="workspace-meta">{detail.entity_id}</p></div><span className="reference-contract">{detail.schema_version}</span></header><DetailBody detail={detail} /></>}</main>;
}
