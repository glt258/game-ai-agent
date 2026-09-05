import type {CharacterDraft, CharacterGenerationResponse, CharacterKitRoleCoverageResponse, CharacterSkillAssociation, CharacterSkillContextRequest, CharacterSkillContextResponse, CharacterSkillDesignResponse, CharacterSkillSlot, CharacterValidationResponse, ValidatorResult} from "../../../lib/api/types";
import type {DraftEdit, EditableDraftField} from "../studio-state";
import {CanonBasisView} from "./views/CanonBasisView";
import {CharacterView} from "./views/CharacterView";
import {CombatView} from "./views/CombatView";
import {PlanView} from "./views/PlanView";
import {CharacterEditForm} from "./CharacterEditForm";
import {SkillsView} from "./SkillsView";
import {DesignChecksView} from "./views/DesignChecksView";
import {TechnicalDetailsView} from "./views/TechnicalDetailsView";
import {projectCharacterPlanner, projectSavedCharacterDraft} from "../character-planner-view";

export type StudioTab = "character" | "plan" | "combat" | "skills" | "canon" | "evaluation" | "raw";
export type SaveState = "idle" | "saving" | "saved" | "error";

const tabs: Array<{id: StudioTab; label: string}> = [
  {id: "character", label: "角色方案"},
  {id: "plan", label: "设计规划"},
  {id: "combat", label: "战斗设计"},
  {id: "skills", label: "技能设计"},
  {id: "canon", label: "世界观依据"},
  {id: "evaluation", label: "设计检查"},
  {id: "raw", label: "技术详情"},
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
  const activeLabel = tabs.find((tab) => tab.id === activeTab)?.label ?? "角色方案";
  const affiliationId = draft?.faction_id ?? null;
  const planner = draft
    ? result
      ? projectCharacterPlanner(result, affiliationName)
      : projectSavedCharacterDraft(draft, affiliationName)
    : null;
  return (
    <section className="column column-center" aria-labelledby="workspace-title">
      {!draft ? (
        <div className="empty-state">
          <div>
            <strong>尚未生成角色方案</strong>
            <span>填写左侧角色设计需求后，点击“生成角色”查看角色方案与设计检查结果。</span>
          </div>
        </div>
      ) : (
        <>
          <div className="workspace-header">
            <div>
              <p className="workspace-kicker">{isEditing ? "编辑角色方案" : "角色方案"}</p>
              <h2 id="workspace-title" className="workspace-title">{draft.name}</h2>
              <span className="workspace-meta">角色方案已生成</span>
            </div>
            <div className="workspace-actions">
              {isEditing && isDirty && <span className="dirty-indicator" role="status">有未保存修改</span>}
              {!isEditing && <button className="button-secondary" onClick={onEdit}>编辑</button>}
              <button className="button-primary" disabled={saveState === "saving"} onClick={onSave}>
                {saveState === "saving" ? "正在保存…" : saveState === "saved" ? "已保存" : "保存角色"}
              </button>
              <button className="button-secondary" onClick={onRegenerate}>重新生成</button>
            </div>
          </div>
          {saveError && <p className="notice" role="alert"><strong>保存失败</strong><span>{saveError}</span></p>}
          {regenerateConfirm && <div className="confirm-strip" role="alertdialog" aria-label="确认重新生成"><span>重新生成会放弃当前未保存的编辑。</span><button className="button-primary" onClick={onConfirmRegenerate}>重新生成</button><button className="button-ghost" onClick={onCancelRegenerate}>继续编辑</button></div>}
          {isEditing && isDirty && <p className="context-notice" role="note">当前方案已编辑；设计规划、世界观依据和技术详情仍描述最初生成的角色方案。</p>}
          {isEditing && validationStale && <p className="stale-notice" role="status">当前方案已编辑；上一次检查结果已过期。</p>}
          <div className="tabs" role="tablist" aria-label="角色工作区标签">
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
            {activeTab === "character" && (isEditing ? <CharacterEditForm draft={draft} fieldErrors={fieldErrors} sectionErrors={sectionErrors} onChange={onDraftChange} /> : planner && <CharacterView projection={planner} />)}
            {activeTab === "plan" && <PlanView plan={result?.plan ?? null} />}
            {activeTab === "combat" && (planner ? <CombatView projection={planner} /> : <p className="column-subtitle">暂未提供战斗设计。</p>)}
            {activeTab === "skills" && characterSkillInput && <SkillsView characterInput={characterSkillInput} context={characterSkillContext} slots={skillSlots} attachedSkills={attachedSkills} designerOpen={skillsDesignerOpen} onDesignSkill={onDesignSkill} onDesignAgain={onDesignAgain} onAttach={onAttachSkill} onDetach={onDetachSkill} roleCoverage={roleCoverage} roleCoverageLoading={roleCoverageLoading} roleCoverageError={roleCoverageError} />}
            {activeTab === "canon" && (result ? <CanonBasisView basis={result.canon_basis} affiliationId={affiliationId} affiliationName={affiliationName} /> : <p className="column-subtitle">该保存版本未保存世界观依据。</p>)}
            {activeTab === "evaluation" && (result ? <DesignChecksView result={result} affiliationName={affiliationName} /> : <p className="column-subtitle">该保存版本未保存设计检查结果。</p>)}
            {activeTab === "raw" && (result ? <TechnicalDetailsView result={result} validation={validationResult} /> : <p className="column-subtitle">该保存版本未保存技术详情。</p>)}
            <span className="sr-only">Active tab: {activeLabel}</span>
          </div>
          {isEditing && activeTab === "character" && (
            <div className="edit-toolbar">
              <button className="button-secondary" disabled={!isDirty} onClick={onDiscard}>放弃修改</button>
              <button className="button-primary" disabled={!isDirty || validationState === "validating"} onClick={onValidate}>{validationState === "validating" ? "正在检查…" : "检查修改"}</button>
              <button className="button-ghost" onClick={onExitEdit}>退出编辑</button>
            </div>
          )}
          {exitConfirm && <div className="confirm-strip" role="alertdialog" aria-label="确认退出编辑"><span>放弃当前未保存的修改并退出编辑？</span><button className="button-primary" onClick={onConfirmExit}>放弃并退出</button><button className="button-ghost" onClick={onCancelExit}>继续编辑</button></div>}
        </>
      )}
    </section>
  );
}
