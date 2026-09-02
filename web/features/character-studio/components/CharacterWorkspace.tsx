import type {CharacterDraft, CharacterGenerationResponse, CharacterKitRoleCoverageResponse, CharacterSkillAssociation, CharacterSkillContextRequest, CharacterSkillContextResponse, CharacterSkillDesignResponse, CharacterSkillSlot, CharacterValidationResponse, ValidatorResult} from "../../../lib/api/types";
import type {DraftEdit, EditableDraftField} from "../studio-state";
import {CanonBasisView} from "./views/CanonBasisView";
import {CharacterView} from "./views/CharacterView";
import {CombatView} from "./views/CombatView";
import {PlanView} from "./views/PlanView";
import {RawDebugView} from "./views/RawDebugView";
import {CharacterEditForm} from "./CharacterEditForm";
import {SkillsView} from "./SkillsView";

export type StudioTab = "character" | "plan" | "combat" | "skills" | "canon" | "raw";
export type SaveState = "idle" | "saving" | "saved" | "error";

const tabs: Array<{id: StudioTab; label: string}> = [
  {id: "character", label: "Character"},
  {id: "plan", label: "Plan"},
  {id: "combat", label: "Combat"},
  {id: "skills", label: "Skills"},
  {id: "canon", label: "Canon Basis"},
  {id: "raw", label: "Raw Debug"},
];

interface CharacterWorkspaceProps {
  result: CharacterGenerationResponse | null;
  draft: CharacterDraft | null;
  affiliationName: string | null;
  activeTab: StudioTab;
  isEditing: boolean;
  isDirty: boolean;
  validationState: "idle" | "validating" | "passed" | "failed" | "error" | "stale";
  validationResult: CharacterValidationResponse | null;
  validationStale: boolean;
  fieldErrors: Map<EditableDraftField, ValidatorResult[]>;
  sectionErrors: Set<string>;
  regenerateConfirm: boolean;
  exitConfirm: boolean;
  onTabChange: (tab: StudioTab) => void;
  onEdit: () => void;
  onDraftChange: (edit: DraftEdit) => void;
  onDiscard: () => void;
  onValidate: () => void;
  onExitEdit: () => void;
  onConfirmExit: () => void;
  onCancelExit: () => void;
  onRegenerate: () => void;
  onConfirmRegenerate: () => void;
  onCancelRegenerate: () => void;
  characterSkillInput: CharacterSkillContextRequest | null;
  characterSkillContext: CharacterSkillContextResponse | null;
  skillSlots: CharacterSkillSlot[];
  attachedSkills: CharacterSkillAssociation[];
  skillsDesignerOpen: boolean;
  onDesignSkill: () => void;
  onDesignAgain: () => void;
  onAttachSkill: (result: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => void;
  onDetachSkill: (associationId: string) => void;
  roleCoverage: CharacterKitRoleCoverageResponse | null;
  roleCoverageLoading: boolean;
  roleCoverageError: string | null;
  saveState: SaveState;
  saveError: string | null;
  onSave: () => void;
}

export function CharacterWorkspace({
  result,
  draft,
  affiliationName,
  activeTab,
  isEditing,
  isDirty,
  validationState,
  validationResult,
  validationStale,
  fieldErrors,
  sectionErrors,
  regenerateConfirm,
  exitConfirm,
  onTabChange,
  onEdit,
  onDraftChange,
  onDiscard,
  onValidate,
  onExitEdit,
  onConfirmExit,
  onCancelExit,
  onRegenerate,
  onConfirmRegenerate,
  onCancelRegenerate,
  characterSkillInput,
  characterSkillContext,
  skillSlots,
  attachedSkills,
  skillsDesignerOpen,
  onDesignSkill,
  onDesignAgain,
  onAttachSkill,
  onDetachSkill,
  roleCoverage,
  roleCoverageLoading,
  roleCoverageError,
  saveState,
  saveError,
  onSave,
}: CharacterWorkspaceProps) {
  const activeLabel = tabs.find((tab) => tab.id === activeTab)?.label ?? "Character";
  return (
    <section className="column column-center" aria-labelledby="workspace-title">
      {!draft ? (
        <div className="empty-state">
          <div>
            <strong>Character workspace</strong>
            <span>Enter a brief and generate a candidate to inspect the frozen result contract.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="workspace-header">
            <div>
              <p className="workspace-kicker">{isEditing ? "Editing draft" : "Completed candidate"}</p>
              <h2 id="workspace-title" className="workspace-title">{draft.name}</h2>
              <span className="workspace-meta">{draft.draft_id}</span>
            </div>
            <div className="workspace-actions">
              {isEditing && isDirty && <span className="dirty-indicator" role="status">Unsaved changes</span>}
              {!isEditing && <button className="button-secondary" onClick={onEdit}>Edit</button>}
              <button className="button-primary" disabled={saveState === "saving"} onClick={onSave}>
                {saveState === "saving" ? "Saving..." : saveState === "saved" ? "Saved" : "Save Character"}
              </button>
              <button className="button-secondary" onClick={onRegenerate}>Regenerate</button>
            </div>
          </div>
          {saveError && <p className="notice" role="alert"><strong>Save failed</strong><span>{saveError}</span></p>}
          {regenerateConfirm && <div className="confirm-strip" role="alertdialog" aria-label="Confirm regeneration"><span>Regenerating will discard your current edits.</span><button className="button-primary" onClick={onConfirmRegenerate}>Regenerate</button><button className="button-ghost" onClick={onCancelRegenerate}>Keep editing</button></div>}
          {isEditing && isDirty && <p className="context-notice" role="note">This draft has been edited. Generation plan, Canon basis and audit describe the original generated candidate.</p>}
          {isEditing && validationStale && <p className="stale-notice" role="status">This draft has been edited. The previous validation result is outdated.</p>}
          <div className="tabs" role="tablist" aria-label="Character workspace tabs">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                className="tab"
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                id={`tab-${tab.id}`}
                onClick={() => onTabChange(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="tab-panel" role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
            {activeTab === "character" && (isEditing ? <CharacterEditForm draft={draft} fieldErrors={fieldErrors} sectionErrors={sectionErrors} onChange={onDraftChange} /> : <CharacterView draft={draft} affiliationName={affiliationName} />)}
            {activeTab === "plan" && <PlanView plan={result?.plan ?? null} />}
            {activeTab === "combat" && (result ? <CombatView combat={result.combat} /> : <p className="column-subtitle">Combat metadata is not available for this saved revision.</p>)}
            {activeTab === "skills" && characterSkillInput && <SkillsView characterInput={characterSkillInput} context={characterSkillContext} slots={skillSlots} attachedSkills={attachedSkills} designerOpen={skillsDesignerOpen} onDesignSkill={onDesignSkill} onDesignAgain={onDesignAgain} onAttach={onAttachSkill} onDetach={onDetachSkill} roleCoverage={roleCoverage} roleCoverageLoading={roleCoverageLoading} roleCoverageError={roleCoverageError} />}
            {activeTab === "canon" && (result ? <CanonBasisView basis={result.canon_basis} /> : <p className="column-subtitle">Canon basis is not stored with this revision.</p>)}
            {activeTab === "raw" && (result ? <RawDebugView raw={result.raw_data} validation={validationResult} /> : <p className="column-subtitle">Raw generation metadata is not stored with this revision.</p>)}
            <span className="sr-only">Active tab: {activeLabel}</span>
          </div>
          {isEditing && activeTab === "character" && (
            <div className="edit-toolbar">
              <button className="button-secondary" disabled={!isDirty} onClick={onDiscard}>Discard Changes</button>
              <button className="button-primary" disabled={!isDirty || validationState === "validating"} onClick={onValidate}>{validationState === "validating" ? "Validating..." : "Validate Changes"}</button>
              <button className="button-ghost" onClick={onExitEdit}>Exit Edit Mode</button>
            </div>
          )}
          {exitConfirm && <div className="confirm-strip" role="alertdialog" aria-label="Confirm exit edit mode"><span>Discard current unsaved edits and exit edit mode?</span><button className="button-primary" onClick={onConfirmExit}>Discard & Exit</button><button className="button-ghost" onClick={onCancelExit}>Stay editing</button></div>}
        </>
      )}
    </section>
  );
}
