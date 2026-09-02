"use client";

import {useCallback, useEffect, useMemo, useRef, useState} from "react";

import {apiClient, ApiClientError} from "../../lib/api/client";
import type {CharacterGenerationRequest, CharacterGenerationResponse, CharacterPlan, CharacterSkillAssociation, CharacterSkillContextRequest, CharacterSkillContextResponse, CharacterSkillDesignResponse, CharacterSkillMetaResponse, CharacterSkillSlot, CharacterValidationResponse, HealthResponse, SavedCharacter, SavedCharacterHistorySummary} from "../../lib/api/types";
import {AgentInspector} from "../../features/character-studio/components/AgentInspector";
import {CharacterBriefPanel} from "../../features/character-studio/components/CharacterBriefPanel";
import {CharacterWorkspace, type SaveState, type StudioTab} from "../../features/character-studio/components/CharacterWorkspace";
import {applyDraftEdit, buildValidationRequest, cloneDraft, collectValidationTargets, isDraftDirty, validationStateAfterEdit, type DraftEdit, type ValidationState} from "../../features/character-studio/studio-state";
import {buildCharacterSkillAssociation, createRoleCoverageEvaluationCoordinator, orderedAssociations, type RoleCoverageEvaluationState} from "../../features/character-studio/skill-session";

const EXAMPLE_BRIEF = `设计一名临洲市公共安全联席体系所属的新角色。

要求：
- 女性
- 25 岁左右
- 性格冷静但并不冷漠
- 战斗偏向辅助控制
- 不允许新增组织
- 与现有世界观保持一致`;

type RequestState = "idle" | "loading" | "success" | "error";

function requestFromBrief(brief: string): CharacterGenerationRequest {
  const trimmedBrief = brief.trim();
  return {
    brief: trimmedBrief,
    hard_constraints: [],
    soft_preferences: [],
    forbidden_elements: [],
    desired_connections: [],
    request_id: null,
    combat_role_profile: trimmedBrief === EXAMPLE_BRIEF.trim()
      ? {primary_role: "support", secondary_roles: ["control"]}
      : null,
  };
}

function frontendError(message: string): ApiClientError {
  return new ApiClientError({
    error: {code: "FRONTEND_ERROR", message, stage: "frontend", retryable: false, details: {}, audit: null},
  }, 0);
}

export default function StudioPage() {
  const [brief, setBrief] = useState("");
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [result, setResult] = useState<CharacterGenerationResponse | null>(null);
  const [generatedDraft, setGeneratedDraft] = useState<CharacterGenerationResponse["draft"] | null>(null);
  const [savedDraft, setSavedDraft] = useState<CharacterGenerationResponse["draft"] | null>(null);
  const [editedDraft, setEditedDraft] = useState<CharacterGenerationResponse["draft"] | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthState, setHealthState] = useState<"loading" | "ready" | "error">("loading");
  const [activeTab, setActiveTab] = useState<StudioTab>("character");
  const [validationState, setValidationState] = useState<ValidationState>("idle");
  const [validationResult, setValidationResult] = useState<CharacterValidationResponse | null>(null);
  const [validationError, setValidationError] = useState<ApiClientError | null>(null);
  const [validationStale, setValidationStale] = useState(false);
  const [regenerateConfirm, setRegenerateConfirm] = useState(false);
  const [exitConfirm, setExitConfirm] = useState(false);
  const [characterSkillContext, setCharacterSkillContext] = useState<CharacterSkillContextResponse | null>(null);
  const [characterSkillMeta, setCharacterSkillMeta] = useState<CharacterSkillMetaResponse | null>(null);
  const [attachedSkills, setAttachedSkills] = useState<CharacterSkillAssociation[]>([]);
  const [roleCoverageState, setRoleCoverageState] = useState<RoleCoverageEvaluationState>({phase: "idle", result: null, message: null});
  const [skillsDesignerOpen, setSkillsDesignerOpen] = useState(false);
  const [persistedIdentity, setPersistedIdentity] = useState<{characterId: string; currentRevisionId: string; currentKitAssignmentId: string | null} | null>(null);
  const [workspaceRequest, setWorkspaceRequest] = useState<CharacterGenerationRequest | null>(null);
  const [workspacePlan, setWorkspacePlan] = useState<CharacterPlan | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [history, setHistory] = useState<SavedCharacterHistorySummary[]>([]);
  const validationRequestRef = useRef(0);
  const openGenerationRef = useRef(0);
  const roleCoverageInputsRef = useRef<{associations: CharacterSkillAssociation[]; roleKey: string} | null>(null);

  const roleCoverageCoordinator = useMemo(() => createRoleCoverageEvaluationCoordinator(
    (request) => apiClient.evaluateCharacterKitRoleCoverage(request),
    setRoleCoverageState,
  ), []);

  const currentDraft = editedDraft ?? generatedDraft ?? result?.draft ?? null;
  const isDirty = isDraftDirty(savedDraft ?? generatedDraft, editedDraft);
  const combatRoleProfile = currentDraft?.combat_role_profile ?? null;
  const combatRoleProfileKey = JSON.stringify(combatRoleProfile);
  const characterSkillInput = useMemo<CharacterSkillContextRequest | null>(() => {
    if (!workspaceRequest || !currentDraft) {
      return null;
    }
    return {request: structuredClone(workspaceRequest), draft: cloneDraft(currentDraft), plan: workspacePlan};
  }, [currentDraft, workspacePlan, workspaceRequest]);

  const validationTargets = useMemo(() => {
    return collectValidationTargets(validationResult?.validators ?? []);
  }, [validationResult]);

  const loadHealth = useCallback(async () => {
    setHealthState("loading");
    try {
      setHealth(await apiClient.getHealth());
      setHealthState("ready");
    } catch {
      setHealth(null);
      setHealthState("error");
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiClient.getHealth().then(
      (response) => {
        if (active) {
          setHealth(response);
          setHealthState("ready");
        }
      },
      () => {
        if (active) {
          setHealth(null);
          setHealthState("error");
        }
      },
    );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (activeTab !== "skills" || !characterSkillInput) {
      return;
    }
    let active = true;
    apiClient.getCharacterSkillContext(characterSkillInput).then(
      (response) => {
        if (active) setCharacterSkillContext(response);
      },
      () => {
        if (active) setCharacterSkillContext(null);
      },
    );
    return () => {
      active = false;
    };
  }, [activeTab, characterSkillInput]);

  useEffect(() => {
    if (activeTab !== "skills") {
      return;
    }
    let active = true;
    apiClient.getCharacterSkillMeta().then(
      (response) => {
        if (active) setCharacterSkillMeta(response);
      },
      () => {
        if (active) setCharacterSkillMeta(null);
      },
    );
    return () => {
      active = false;
    };
  }, [activeTab]);

  useEffect(() => {
    const previous = roleCoverageInputsRef.current;
    const associationsChanged = previous?.associations !== attachedSkills;
    const roleChanged = previous?.roleKey !== combatRoleProfileKey;
    roleCoverageInputsRef.current = {associations: attachedSkills, roleKey: combatRoleProfileKey};
    if (previous && !associationsChanged && !roleChanged) {
      return;
    }
    if (!combatRoleProfile || attachedSkills.length === 0) {
      roleCoverageCoordinator.reset();
      return;
    }
    roleCoverageCoordinator.evaluate(combatRoleProfile, attachedSkills);
  }, [attachedSkills, combatRoleProfile, combatRoleProfileKey, roleCoverageCoordinator]);

  const generate = useCallback(async () => {
    if (!brief.trim() || requestState === "loading") {
      return;
    }
    validationRequestRef.current += 1;
    setRequestState("loading");
    setError(null);
    setValidationState("idle");
    setValidationResult(null);
    setValidationError(null);
    setValidationStale(false);
    setRegenerateConfirm(false);
    try {
      const response = await apiClient.generateCharacter(requestFromBrief(brief));
      const nextGenerated = cloneDraft(response.draft);
      setResult(response);
      setGeneratedDraft(nextGenerated);
      setSavedDraft(null);
      setEditedDraft(cloneDraft(nextGenerated));
      setWorkspaceRequest(structuredClone(response.request));
      setWorkspacePlan(response.plan ? structuredClone(response.plan) : null);
      setPersistedIdentity(null);
      setSaveState("idle");
      setSaveError(null);
      setHistory([]);
      setIsEditing(false);
      setValidationState("idle");
      setValidationResult(null);
      setValidationError(null);
      setValidationStale(false);
      setRegenerateConfirm(false);
      setExitConfirm(false);
      setCharacterSkillContext(null);
      setCharacterSkillMeta(null);
      setAttachedSkills([]);
      roleCoverageCoordinator.reset();
      setSkillsDesignerOpen(false);
      setRequestState("success");
      setActiveTab("character");
    } catch (caught) {
      const safeError = caught instanceof ApiClientError ? caught : frontendError("The Character Studio could not complete the request.");
      setError(safeError);
      setRequestState("error");
    }
  }, [brief, requestState, roleCoverageCoordinator]);

  const startEdit = useCallback(() => {
    if (editedDraft) {
      setIsEditing(true);
      setActiveTab("character");
      setExitConfirm(false);
    }
  }, [editedDraft]);

  const editDraft = useCallback((edit: DraftEdit) => {
    validationRequestRef.current += 1;
    setEditedDraft((current) => current ? applyDraftEdit(current, edit) : current);
    const nextValidationState = validationStateAfterEdit(validationState);
    setValidationStale(nextValidationState === "stale");
    setValidationState(nextValidationState);
    setValidationResult(null);
    setValidationError(null);
  }, [validationState]);

  const discardChanges = useCallback(() => {
    const baseline = savedDraft ?? generatedDraft;
    if (!baseline) {
      return;
    }
    validationRequestRef.current += 1;
    setEditedDraft(cloneDraft(baseline));
    setValidationState("idle");
    setValidationResult(null);
    setValidationError(null);
    setValidationStale(false);
  }, [generatedDraft, savedDraft]);

  const exitEdit = useCallback(() => {
    if (isDirty) {
      setExitConfirm(true);
      return;
    }
    setIsEditing(false);
  }, [isDirty]);

  const confirmExit = useCallback(() => {
    discardChanges();
    setIsEditing(false);
    setExitConfirm(false);
  }, [discardChanges]);

  const validate = useCallback(async () => {
    if (!workspaceRequest || !editedDraft || !isDirty || validationState === "validating") {
      return;
    }
    const requestToken = ++validationRequestRef.current;
    const draftToValidate = cloneDraft(editedDraft);
    setValidationState("validating");
    setValidationError(null);
    setValidationResult(null);
    setValidationStale(false);
    try {
      const response = await apiClient.validateCharacter(buildValidationRequest(workspaceRequest, draftToValidate));
      if (validationRequestRef.current !== requestToken) {
        return;
      }
      setValidationResult(response);
      setValidationState(response.status);
    } catch (caught) {
      if (validationRequestRef.current !== requestToken) {
        return;
      }
      const safeError = caught instanceof ApiClientError ? caught : frontendError("The edited draft could not be validated.");
      setValidationError(safeError);
      setValidationState("error");
    }
  }, [editedDraft, isDirty, validationState, workspaceRequest]);

  const requestRegenerate = useCallback(() => {
    if (isDirty) {
      setRegenerateConfirm(true);
      return;
    }
    void generate();
  }, [generate, isDirty]);

  const designSkill = useCallback(() => {
    setActiveTab("skills");
    setSkillsDesignerOpen(true);
  }, []);

  const attachSkill = useCallback((skill: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => {
    const association = buildCharacterSkillAssociation(skill, slot);
    if (!association) {
      return;
    }
    setAttachedSkills((current) => {
      if (current.some((item) => item.artifact.identity.artifact_digest === association.artifact.identity.artifact_digest
        || (item.slot === association.slot && slot.max_items !== null))) {
        return current;
      }
      return orderedAssociations([...current, association]);
    });
    roleCoverageCoordinator.reset();
    setSkillsDesignerOpen(false);
  }, [roleCoverageCoordinator]);

  const applySavedCharacter = useCallback((saved: SavedCharacter) => {
    openGenerationRef.current += 1;
    validationRequestRef.current += 1;
    const nextDraft = cloneDraft(saved.draft);
    setResult(null);
    setGeneratedDraft(nextDraft);
    setSavedDraft(nextDraft);
    setEditedDraft(cloneDraft(nextDraft));
    setWorkspaceRequest(structuredClone(saved.request));
    setWorkspacePlan(saved.plan ? structuredClone(saved.plan) : null);
    setPersistedIdentity({characterId: saved.character_id, currentRevisionId: saved.current_revision_id, currentKitAssignmentId: saved.current_kit_assignment_id});
    setAttachedSkills(saved.associations);
    setRequestState("success");
    setError(null);
    setSaveState("idle");
    setSaveError(null);
    setHistory(saved.history);
    setValidationState("idle");
    setValidationResult(null);
    setValidationError(null);
    setValidationStale(false);
    setIsEditing(false);
    setActiveTab("character");
    setSkillsDesignerOpen(false);
    roleCoverageCoordinator.reset();
  }, [roleCoverageCoordinator]);

  const openSavedCharacter = useCallback(async (characterId: string) => {
    const token = ++openGenerationRef.current;
    setRequestState("loading");
    setError(null);
    try {
      const saved = await apiClient.openSavedCharacter(characterId);
      if (openGenerationRef.current === token) applySavedCharacter(saved);
    } catch (caught) {
      if (openGenerationRef.current !== token) return;
      const safeError = caught instanceof ApiClientError ? caught : frontendError("Saved character could not be opened.");
      setError(safeError);
      setRequestState("error");
    }
  }, [applySavedCharacter]);

  useEffect(() => {
    const characterId = new URLSearchParams(window.location.search).get("character");
    if (characterId) queueMicrotask(() => void openSavedCharacter(characterId));
  }, [openSavedCharacter]);

  const save = useCallback(async () => {
    if (!editedDraft || !workspaceRequest || saveState === "saving") return;
    setSaveState("saving");
    setSaveError(null);
    const payload = {
      schema_version: "web-saved-character-save/0.1" as const,
      request: structuredClone(workspaceRequest),
      draft: cloneDraft(editedDraft),
      plan: workspacePlan ? structuredClone(workspacePlan) : null,
      associations: structuredClone(attachedSkills),
      expected_current_revision_id: persistedIdentity?.currentRevisionId ?? null,
      expected_current_kit_assignment_id: persistedIdentity?.currentKitAssignmentId ?? null,
    };
    try {
      const response = persistedIdentity
        ? await apiClient.updateSavedCharacter(persistedIdentity.characterId, payload)
        : await apiClient.createSavedCharacter(payload);
      applySavedCharacter(response.saved);
      setIsEditing(true);
      setSaveState("saved");
    } catch (caught) {
      const safeError = caught instanceof ApiClientError ? caught : frontendError("The saved Character workspace could not be saved.");
      setSaveError(safeError.message);
      setSaveState("error");
    }
  }, [applySavedCharacter, attachedSkills, editedDraft, persistedIdentity, saveState, workspacePlan, workspaceRequest]);

  const detachSkill = useCallback((associationId: string) => {
    setAttachedSkills((current) => current.filter((item) => item.association_id !== associationId));
    roleCoverageCoordinator.reset();
  }, [roleCoverageCoordinator]);

  const healthLabel = healthState === "ready" && health?.status === "ok"
    ? "Backend online"
    : healthState === "loading"
      ? "Checking backend"
      : "Backend unavailable";

  return (
    <main className="studio-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Game AI Agent</span>
          <span className="brand-context">/ Character Studio</span>
        </div>
        <div className={`health ${healthState === "ready" ? "online" : healthState === "error" ? "offline" : ""}`} role="status">
          <span className="health-dot" aria-hidden="true" />
          <span>{healthLabel}</span>
          {healthState === "error" && <button className="button-ghost" onClick={() => void loadHealth()}>Retry</button>}
        </div>
      </header>

      <div className="studio-grid">
        <CharacterBriefPanel
          brief={brief}
          loading={requestState === "loading"}
          exampleBrief={EXAMPLE_BRIEF}
          onBriefChange={setBrief}
          onGenerate={() => void generate()}
        />
          <CharacterWorkspace
          result={result}
          draft={currentDraft}
          affiliationName={workspacePlan?.affiliation_context?.name ?? result?.plan?.affiliation_context?.name ?? null}
          activeTab={activeTab}
          isEditing={isEditing}
          isDirty={isDirty}
          validationState={validationState}
          validationResult={validationResult}
          validationStale={validationStale}
          fieldErrors={validationTargets.fields}
          sectionErrors={validationTargets.sections}
          regenerateConfirm={regenerateConfirm}
          exitConfirm={exitConfirm}
          onTabChange={setActiveTab}
          onEdit={startEdit}
          onDraftChange={editDraft}
          onDiscard={discardChanges}
          onValidate={() => void validate()}
          onExitEdit={exitEdit}
          onConfirmExit={confirmExit}
          onCancelExit={() => setExitConfirm(false)}
          onRegenerate={requestRegenerate}
          onConfirmRegenerate={() => void generate()}
            onCancelRegenerate={() => setRegenerateConfirm(false)}
            characterSkillInput={characterSkillInput}
            characterSkillContext={characterSkillContext}
            skillSlots={characterSkillMeta?.slots ?? []}
            attachedSkills={attachedSkills}
            skillsDesignerOpen={skillsDesignerOpen}
            onDesignSkill={designSkill}
            onDesignAgain={designSkill}
            onAttachSkill={attachSkill}
            onDetachSkill={detachSkill}
          roleCoverage={roleCoverageState.phase === "ready" ? roleCoverageState.result : null}
          roleCoverageLoading={roleCoverageState.phase === "loading"}
          roleCoverageError={roleCoverageState.phase === "error" ? roleCoverageState.message : null}
          saveState={saveState}
          saveError={saveError}
          onSave={() => void save()}
          />
        <AgentInspector
          result={result}
          requestState={requestState}
          error={error}
          validationState={validationState}
          validationResult={validationResult}
          validationError={validationError}
          validationStale={validationStale}
          onRetry={() => void generate()}
          onRetryValidation={() => void validate()}
          history={history}
        />
      </div>
    </main>
  );
}
