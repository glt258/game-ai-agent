import type {CharacterDraft} from "../../../../lib/api/types";
import {CanonicalEntityLink} from "../../../canon/CanonicalEntityLink";

function Field({name, value, full = false}: {name: string; value: string | null; full?: boolean}) {
  return <div className={`field-card ${full ? "full" : ""}`}><p className="field-name">{name}</p><p className={`field-value ${value ? "" : "muted"}`}>{value || "Not provided"}</p></div>;
}

export function CharacterView({draft, affiliationName}: {draft: CharacterDraft; affiliationName?: string | null}) {
  return (
    <div className="field-grid">
      <Field name="Name" value={draft.name} />
      <Field name="Draft ID" value={draft.draft_id} />
      <Field name="Occupation" value={draft.occupation} />
      <Field name="Social role" value={draft.social_role} />
      {affiliationName && draft.faction_id ? <div className="field-card"><p className="field-name">Affiliation</p><CanonicalEntityLink entity_id={draft.faction_id} entity_type="faction" display_name={affiliationName} /></div> : <Field name="Affiliation" value={draft.faction_id} />}
      <Field name="Gender" value={draft.gender} />
      <Field name="Age" value={draft.age === null ? null : String(draft.age) + " years"} />
      <Field name="Age range" value={draft.age_range} />
      <div className="field-card full"><p className="field-name">Personality</p><div className="tag-row">{draft.personality.length ? draft.personality.map((item) => <span className="tag" key={item}>{item}</span>) : <span className="field-value muted">Not provided</span>}</div></div>
      <Field name="Design pitch" value={draft.design_pitch} full />
      <Field name="Background" value={draft.background} full />
      <Field name="Story hook" value={draft.story_hook} full />
      <Field name="Ability concept" value={draft.ability_concept} full />
      <Field name="Knowledge scope" value={draft.knowledge_scope} full />
    </div>
  );
}
