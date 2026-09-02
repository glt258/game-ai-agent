import type {
  CharacterDraft,
  CharacterGenerationRequest,
  CharacterValidationRequest,
  ValidatorResult,
} from "../../lib/api/types";

export type EditableDraftField =
  | "name"
  | "occupation"
  | "social_role"
  | "faction_id"
  | "gender"
  | "age"
  | "age_range"
  | "design_pitch"
  | "personality"
  | "background"
  | "story_hook"
  | "ability_concept"
  | "knowledge_scope";

export type DraftEdit = {
  field: EditableDraftField;
  value: string | number | null | string[];
};

export type ValidationTarget = {
  field: EditableDraftField | null;
  section: "identity" | "personality" | "narrative" | "combat" | "canon" | "evaluation" | "request" | "general";
};

export type ValidationState = "idle" | "validating" | "passed" | "failed" | "error" | "stale";

export type ValidationTargets = {
  fields: Map<EditableDraftField, ValidatorResult[]>;
  sections: Set<ValidationTarget["section"]>;
};

export function cloneDraft(draft: CharacterDraft): CharacterDraft {
  return structuredClone(draft);
}

export function draftsEqual(left: CharacterDraft, right: CharacterDraft): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function isDraftDirty(generatedDraft: CharacterDraft | null, editedDraft: CharacterDraft | null): boolean {
  if (!generatedDraft || !editedDraft) {
    return false;
  }
  return !draftsEqual(generatedDraft, editedDraft);
}

export function applyDraftEdit(draft: CharacterDraft, edit: DraftEdit): CharacterDraft {
  const next = cloneDraft(draft);
  switch (edit.field) {
    case "age":
      next.age = typeof edit.value === "number" ? edit.value : edit.value === null ? null : Number(edit.value);
      break;
    case "personality":
      next.personality = Array.isArray(edit.value) ? edit.value : String(edit.value).split(",").map((item) => item.trim()).filter(Boolean);
      break;
    case "name":
      next.name = String(edit.value);
      break;
    case "occupation":
      next.occupation = String(edit.value);
      break;
    case "social_role":
      next.social_role = String(edit.value);
      break;
    case "faction_id":
      next.faction_id = edit.value === null || edit.value === "" ? null : String(edit.value);
      break;
    case "gender":
      next.gender = edit.value === null || edit.value === "" ? null : String(edit.value);
      break;
    case "age_range":
      next.age_range = edit.value === null || edit.value === "" ? null : String(edit.value);
      break;
    case "design_pitch":
      next.design_pitch = String(edit.value);
      break;
    case "background":
      next.background = String(edit.value);
      break;
    case "story_hook":
      next.story_hook = String(edit.value);
      break;
    case "ability_concept":
      next.ability_concept = String(edit.value);
      break;
    case "knowledge_scope":
      next.knowledge_scope = String(edit.value);
      break;
  }
  return next;
}

export function buildValidationRequest(
  request: CharacterGenerationRequest,
  editedDraft: CharacterDraft,
): CharacterValidationRequest {
  return {
    request: structuredClone(request),
    draft: cloneDraft(editedDraft),
  };
}

export function validationStateAfterEdit(state: ValidationState): ValidationState {
  return state === "idle" || state === "stale" ? state : "stale";
}

export function invalidateValidationOnEdit(state: ValidationState = "idle"): ValidationState {
  return validationStateAfterEdit(state);
}

const EDITABLE_FIELDS = new Set<EditableDraftField>([
  "name",
  "occupation",
  "social_role",
  "faction_id",
  "gender",
  "age",
  "age_range",
  "design_pitch",
  "personality",
  "background",
  "story_hook",
  "ability_concept",
  "knowledge_scope",
]);

export function validationTarget(finding: Pick<ValidatorResult, "name" | "code" | "field_path">): ValidationTarget {
  const pathParts = finding.field_path?.replace(/^\/+/, "").split(/[/.\[\]]/).filter(Boolean) ?? [];
  const fieldPart = pathParts.find((part) => EDITABLE_FIELDS.has(part as EditableDraftField));
  if (fieldPart) {
    const field = fieldPart as EditableDraftField;
    if (field === "personality") {
      return {field, section: "personality"};
    }
    if (["background", "story_hook", "design_pitch", "ability_concept", "knowledge_scope"].includes(field)) {
      return {field, section: "narrative"};
    }
    return {field, section: "identity"};
  }
  if (finding.name === "canon_checker" || finding.code?.startsWith("CANON")) {
    return {field: null, section: "canon"};
  }
  if (finding.name === "evaluation_runner") {
    return {field: null, section: "evaluation"};
  }
  if (finding.name === "request_alignment") {
    return {field: null, section: "request"};
  }
  return {field: null, section: "general"};
}

export function collectValidationTargets(validators: ValidatorResult[]): ValidationTargets {
  const fields = new Map<EditableDraftField, ValidatorResult[]>();
  const sections = new Set<ValidationTarget["section"]>();
  for (const finding of validators) {
    if (finding.status !== "failed" && finding.status !== "warning") {
      continue;
    }
    const target = validationTarget(finding);
    sections.add(target.section);
    if (target.field) {
      const existing = fields.get(target.field) ?? [];
      fields.set(target.field, [...existing, finding]);
    }
  }
  return {fields, sections};
}
