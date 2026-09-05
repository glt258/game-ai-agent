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
      <p className="edit-helper">以下字段只修改当前会话中的角色方案，不会自动保存。点击“检查修改”后，以服务端结果为准。</p>
      {identityError && <p className="section-alert" role="alert">身份信息存在检查结果，请查看标记字段和检查详情。</p>}
      <section className="editor-section" aria-labelledby="identity-heading">
        <h3 id="identity-heading" className="subheading">身份与定位</h3>
        <div className="editor-grid">
          <TextEditor field="name" label="姓名" value={draft.name} errors={fieldErrors.get("name")} onChange={onChange} />
          <TextEditor field="occupation" label="职业" value={draft.occupation} errors={fieldErrors.get("occupation")} onChange={onChange} />
          <TextEditor field="social_role" label="社会身份" value={draft.social_role} errors={fieldErrors.get("social_role")} onChange={onChange} />
          <TextEditor field="faction_id" label="所属组织编号" value={draft.faction_id} errors={fieldErrors.get("faction_id")} onChange={onChange} />
          <TextEditor field="gender" label="性别" value={draft.gender} errors={fieldErrors.get("gender")} onChange={onChange} />
          <div className={`editor-field ${fieldErrors.get("age")?.length ? "has-error" : ""}`}>
            <label className="section-label" htmlFor="draft-age">年龄</label>
            <input id="draft-age" className="draft-input" type="number" value={draft.age ?? ""} aria-invalid={fieldErrors.get("age")?.length ? true : undefined} aria-describedby={fieldErrors.get("age")?.length ? "draft-age-errors" : undefined} onChange={(event) => onChange({field: "age", value: event.target.value === "" ? null : Number(event.target.value)})} />
            <FieldErrorList errors={fieldErrors.get("age")} id="draft-age-errors" />
          </div>
          <TextEditor field="age_range" label="年龄范围" value={draft.age_range} errors={fieldErrors.get("age_range")} onChange={onChange} />
        </div>
      </section>

      {personalityError && <p className="section-alert" role="alert">性格信息存在检查结果，请查看标记字段和检查详情。</p>}
      <section className="editor-section" aria-labelledby="personality-heading">
        <h3 id="personality-heading" className="subheading">性格</h3>
        <div className={`editor-field ${fieldErrors.get("personality")?.length ? "has-error" : ""}`}>
          <label className="section-label" htmlFor="draft-personality">性格关键词</label>
          <input id="draft-personality" className="draft-input" value={draft.personality.join(", ")} aria-invalid={fieldErrors.get("personality")?.length ? true : undefined} aria-describedby={fieldErrors.get("personality")?.length ? "draft-personality-errors" : undefined} onChange={(event) => onChange({field: "personality", value: event.target.value})} />
          <p className="editor-hint">多个关键词请用逗号分隔。</p>
          <FieldErrorList errors={fieldErrors.get("personality")} id="draft-personality-errors" />
        </div>
      </section>

      {narrativeError && <p className="section-alert" role="alert">叙事信息存在检查结果，请查看标记字段和检查详情。</p>}
      <section className="editor-section" aria-labelledby="narrative-heading">
        <h3 id="narrative-heading" className="subheading">背景与能力</h3>
        <div className="editor-grid">
          <TextEditor field="design_pitch" label="角色定位" value={draft.design_pitch} errors={fieldErrors.get("design_pitch")} multiline onChange={onChange} />
          <TextEditor field="background" label="背景经历" value={draft.background} errors={fieldErrors.get("background")} multiline onChange={onChange} />
          <TextEditor field="story_hook" label="剧情钩子" value={draft.story_hook} errors={fieldErrors.get("story_hook")} multiline onChange={onChange} />
          <TextEditor field="ability_concept" label="能力构想" value={draft.ability_concept} errors={fieldErrors.get("ability_concept")} multiline onChange={onChange} />
          <TextEditor field="knowledge_scope" label="知识范围" value={draft.knowledge_scope} errors={fieldErrors.get("knowledge_scope")} multiline onChange={onChange} />
        </div>
      </section>

      <section className="editor-section" aria-labelledby="readonly-heading">
        <h3 id="readonly-heading" className="subheading">只读技术字段</h3>
        <div className="readonly-grid">
          <p><strong>draft_id</strong><span>{draft.draft_id}</span></p>
          <p><strong>status</strong><span>{draft.status}</span></p>
          <p><strong>combat_role_profile</strong><span>{draft.combat_role_profile.primary_role ?? "未指定"}</span></p>
          <p><strong>其他技术字段</strong><span>关系、世界观依据、剧情关联和新增内容在当前版本保持只读。</span></p>
        </div>
      </section>
    </div>
  );
}
