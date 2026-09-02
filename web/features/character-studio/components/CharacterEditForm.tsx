import type {CharacterDraft, ValidatorResult} from "../../../lib/api/types";
import type {DraftEdit, EditableDraftField} from "../studio-state";

interface CharacterEditFormProps {
  draft: CharacterDraft;
  fieldErrors: Map<EditableDraftField, ValidatorResult[]>;
  sectionErrors: Set<string>;
  onChange: (edit: DraftEdit) => void;
}

function FieldErrorList({errors, id}: {errors: ValidatorResult[] | undefined; id: string}) {
  if (!errors?.length) {
    return null;
  }
  return (
    <div id={id} className="field-errors" role="alert">
      {errors.map((error, index) => (
        <p key={`${error.name}-${error.code ?? "issue"}-${index}`}>
          <span className="error-symbol" aria-hidden="true">!</span>
          {error.code ?? error.name}: {error.message}
        </p>
      ))}
    </div>
  );
}

function TextEditor({
  field,
  label,
  value,
  errors,
  multiline = false,
  onChange,
}: {
  field: EditableDraftField;
  label: string;
  value: string | null;
  errors: ValidatorResult[] | undefined;
  multiline?: boolean;
  onChange: (edit: DraftEdit) => void;
}) {
  const id = `draft-${field}`;
  const errorId = `${id}-errors`;
  return (
    <div className={`editor-field ${errors?.length ? "has-error" : ""}`}>
      <label className="section-label" htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea id={id} className="draft-input draft-textarea" value={value ?? ""} aria-invalid={errors?.length ? true : undefined} aria-describedby={errors?.length ? errorId : undefined} onChange={(event) => onChange({field, value: event.target.value})} />
      ) : (
        <input id={id} className="draft-input" value={value ?? ""} aria-invalid={errors?.length ? true : undefined} aria-describedby={errors?.length ? errorId : undefined} onChange={(event) => onChange({field, value: event.target.value})} />
      )}
      <FieldErrorList errors={errors} id={errorId} />
    </div>
  );
}

export function CharacterEditForm({draft, fieldErrors, sectionErrors, onChange}: CharacterEditFormProps) {
  const identityError = sectionErrors.has("identity");
  const narrativeError = sectionErrors.has("narrative");
  const personalityError = sectionErrors.has("personality");
  return (
    <div className="edit-form">
      <p className="edit-helper">Structured fields below update the in-memory draft only. Session changes are not persisted. Validate Changes is the server-side source of truth.</p>
      {identityError && <p className="section-alert" role="alert">Identity section has validation findings. Review the highlighted fields and validator details.</p>}
      <section className="editor-section" aria-labelledby="identity-heading">
        <h3 id="identity-heading" className="subheading">Identity & role</h3>
        <div className="editor-grid">
          <TextEditor field="name" label="Name" value={draft.name} errors={fieldErrors.get("name")} onChange={onChange} />
          <TextEditor field="occupation" label="Occupation" value={draft.occupation} errors={fieldErrors.get("occupation")} onChange={onChange} />
          <TextEditor field="social_role" label="Social role" value={draft.social_role} errors={fieldErrors.get("social_role")} onChange={onChange} />
          <TextEditor field="faction_id" label="Affiliation ID" value={draft.faction_id} errors={fieldErrors.get("faction_id")} onChange={onChange} />
          <TextEditor field="gender" label="Gender" value={draft.gender} errors={fieldErrors.get("gender")} onChange={onChange} />
          <div className={`editor-field ${fieldErrors.get("age")?.length ? "has-error" : ""}`}>
            <label className="section-label" htmlFor="draft-age">Age</label>
            <input id="draft-age" className="draft-input" type="number" value={draft.age ?? ""} aria-invalid={fieldErrors.get("age")?.length ? true : undefined} aria-describedby={fieldErrors.get("age")?.length ? "draft-age-errors" : undefined} onChange={(event) => onChange({field: "age", value: event.target.value === "" ? null : Number(event.target.value)})} />
            <FieldErrorList errors={fieldErrors.get("age")} id="draft-age-errors" />
          </div>
          <TextEditor field="age_range" label="Age range" value={draft.age_range} errors={fieldErrors.get("age_range")} onChange={onChange} />
        </div>
      </section>

      {personalityError && <p className="section-alert" role="alert">Personality section has validation findings. Review the highlighted field and validator details.</p>}
      <section className="editor-section" aria-labelledby="personality-heading">
        <h3 id="personality-heading" className="subheading">Personality</h3>
        <div className={`editor-field ${fieldErrors.get("personality")?.length ? "has-error" : ""}`}>
          <label className="section-label" htmlFor="draft-personality">Personality tags</label>
          <input id="draft-personality" className="draft-input" value={draft.personality.join(", ")} aria-invalid={fieldErrors.get("personality")?.length ? true : undefined} aria-describedby={fieldErrors.get("personality")?.length ? "draft-personality-errors" : undefined} onChange={(event) => onChange({field: "personality", value: event.target.value})} />
          <p className="editor-hint">Separate entries with commas.</p>
          <FieldErrorList errors={fieldErrors.get("personality")} id="draft-personality-errors" />
        </div>
      </section>

      {narrativeError && <p className="section-alert" role="alert">Narrative section has validation findings. Review the highlighted fields and validator details.</p>}
      <section className="editor-section" aria-labelledby="narrative-heading">
        <h3 id="narrative-heading" className="subheading">Narrative & capability</h3>
        <div className="editor-grid">
          <TextEditor field="design_pitch" label="Design pitch" value={draft.design_pitch} errors={fieldErrors.get("design_pitch")} multiline onChange={onChange} />
          <TextEditor field="background" label="Background" value={draft.background} errors={fieldErrors.get("background")} multiline onChange={onChange} />
          <TextEditor field="story_hook" label="Story hook" value={draft.story_hook} errors={fieldErrors.get("story_hook")} multiline onChange={onChange} />
          <TextEditor field="ability_concept" label="Ability concept" value={draft.ability_concept} errors={fieldErrors.get("ability_concept")} multiline onChange={onChange} />
          <TextEditor field="knowledge_scope" label="Knowledge scope" value={draft.knowledge_scope} errors={fieldErrors.get("knowledge_scope")} multiline onChange={onChange} />
        </div>
      </section>

      <section className="editor-section" aria-labelledby="readonly-heading">
        <h3 id="readonly-heading" className="subheading">Read-only contract fields</h3>
        <div className="readonly-grid">
          <p><strong>Draft ID</strong><span>{draft.draft_id}</span></p>
          <p><strong>Status</strong><span>{draft.status}</span></p>
          <p><strong>Combat profile</strong><span>{draft.combat_role_profile.primary_role ?? "Not specified"}</span></p>
          <p><strong>Nested authoring data</strong><span>Relationships, Canon basis, story link, and proposed content remain read-only in v0.1.</span></p>
        </div>
      </section>
    </div>
  );
}
