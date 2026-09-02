import type {
  ArtifactCompatibility,
  CharacterKitRoleCoverageRequest,
  CharacterKitEvaluationAssociation,
  CharacterSkillAssociation,
  CharacterSkillDesignResponse,
  CharacterSkillSlot,
  CombatRoleProfile,
  SkillFamily,
  SkillMode,
} from "../../lib/api/types";

export type SkillFreshness = "current" | "stale";

export function skillFreshness(
  artifactFingerprint: string,
  currentFingerprint: string | null,
): SkillFreshness {
  return currentFingerprint && artifactFingerprint !== currentFingerprint ? "stale" : "current";
}

export function canAttachSkill(result: CharacterSkillDesignResponse): boolean {
  return result.status === "completed"
    && result.freshness === "current"
    && result.evaluation.outcome === "PASS"
    && result.alignment.status === "PASS"
    && !result.alignment.blocking
    && result.artifact_compatibility === "CURRENT_COMPATIBLE"
    && result.artifact_versions !== null
    && result.artifact !== null
    && result.artifact !== undefined
    && result.binding !== null
    && result.binding !== undefined
    && typeof result.artifact_digest === "string"
    && result.artifact_digest.length > 0
    && result.skillkit !== null
    && result.semantic_ir !== null;
}

export function buildCharacterSkillAssociation(
  result: CharacterSkillDesignResponse,
  slot: CharacterSkillSlot,
): CharacterSkillAssociation | null {
  if (!canAttachSkill(result) || !result.artifact_digest || !result.semantic_ir || !result.skillkit || !result.artifact_versions || !result.artifact_compatibility || !result.artifact || !result.binding) {
    return null;
  }
  return {
    association_id: `session-skill:${slot.id}:${result.artifact_digest}`,
    artifact: result.artifact,
    binding: result.binding,
    artifact_compatibility: result.artifact_compatibility,
    slot: slot.id,
    order: slot.order,
    family: result.skill_input.family,
    mode: result.skill_input.mode,
    display_summary: String(result.semantic_ir.ability_name ?? result.skill_input.brief),
  };
}

export type CharacterKitEvaluationRequestBuildResult =
  | {ok: true; request: CharacterKitRoleCoverageRequest}
  | {ok: false; code: "MISSING_ARTIFACT" | "MISSING_BINDING" | "ARTIFACT_DIGEST_MISMATCH" | "BINDING_DIGEST_MISMATCH"; message: string};

export function buildCharacterKitEvaluationRequest(
  combatRoleProfile: CombatRoleProfile,
  associations: ReadonlyArray<CharacterSkillAssociation>,
): CharacterKitEvaluationRequestBuildResult {
  const ordered = [...associations].sort((left, right) => left.order - right.order || left.association_id.localeCompare(right.association_id));
  for (const association of ordered) {
    if (!association.artifact) {
      return {ok: false, code: "MISSING_ARTIFACT", message: "Role Coverage unavailable: attached Skill artifact data is incomplete."};
    }
    if (!association.binding) {
      return {ok: false, code: "MISSING_BINDING", message: "Role Coverage unavailable: attached Skill binding data is incomplete."};
    }
    if (association.artifact.identity.artifact_digest !== association.binding.artifact_digest) {
      return {ok: false, code: "BINDING_DIGEST_MISMATCH", message: "Role Coverage unavailable: Skill binding identity is inconsistent."};
    }
    if (association.association_id.startsWith("session-skill:")
      && association.artifact.identity.artifact_digest !== association.association_id.split(":").at(-1)) {
      return {ok: false, code: "ARTIFACT_DIGEST_MISMATCH", message: "Role Coverage unavailable: Skill artifact identity is inconsistent."};
    }
  }
  const transportAssociations: CharacterKitEvaluationAssociation[] = ordered.map((association) => ({
    // CharacterKit is a domain/session contract; durable identity stays in Saved Workspace state.
    association_id: association.association_id.startsWith("session-skill:")
      ? association.association_id
      : `session-skill:${association.slot}:${association.artifact.identity.artifact_digest}`,
    artifact: association.artifact,
    binding: association.binding,
    slot: association.slot,
    order: association.order,
    family: association.family,
    mode: association.mode,
    display_summary: association.display_summary,
  }));
  return {
    ok: true,
    request: {
      schema_version: "web-character-kit-role-coverage/0.1",
      kit: {
        contract_version: "character-kit/0.1.0",
        placement_schema_version: "character-kit-placement/0.1.0",
        associations: transportAssociations,
      },
      combat_role_profile: combatRoleProfile,
    },
  };
}

export type RoleCoverageEvaluationState =
  | {phase: "idle"; result: null; message: null}
  | {phase: "loading"; result: null; message: null}
  | {phase: "ready"; result: import("../../lib/api/types").CharacterKitRoleCoverageResponse; message: null}
  | {phase: "error"; result: null; message: string};

function isCurrentRoleCoverageResponse(
  result: import("../../lib/api/types").CharacterKitRoleCoverageResponse,
): boolean {
  return result.kit_digest === result.role_coverage.kit_digest
    && result.role_coverage.evaluation_context_fingerprint.length > 0;
}

export function createRoleCoverageEvaluationCoordinator(
  evaluate: (request: CharacterKitRoleCoverageRequest) => Promise<import("../../lib/api/types").CharacterKitRoleCoverageResponse>,
  onState: (state: RoleCoverageEvaluationState) => void,
) {
  let requestGeneration = 0;

  return {
    evaluate(combatRoleProfile: CombatRoleProfile, associations: ReadonlyArray<CharacterSkillAssociation>): void {
      const generation = ++requestGeneration;
      const built = buildCharacterKitEvaluationRequest(combatRoleProfile, associations);
      if (!built.ok) {
        onState({phase: "error", result: null, message: built.message});
        return;
      }
        onState({phase: "loading", result: null, message: null});
      void evaluate(built.request).then(
        (result) => {
          if (generation === requestGeneration) {
            if (!isCurrentRoleCoverageResponse(result)) {
              onState({phase: "error", result: null, message: "Role Coverage unavailable: the backend returned an inconsistent Kit identity."});
              return;
            }
            onState({phase: "ready", result, message: null});
          }
        },
        () => {
          if (generation === requestGeneration) {
            onState({phase: "error", result: null, message: "Role Coverage unavailable. The backend could not evaluate the current Kit."});
          }
        },
      );
    },
    reset(): void {
      requestGeneration += 1;
      onState({phase: "idle", result: null, message: null});
    },
  };
}

export function orderedAssociations(
  associations: CharacterSkillAssociation[],
): CharacterSkillAssociation[] {
  return [...associations].sort((left, right) => left.order - right.order || left.association_id.localeCompare(right.association_id));
}

export function artifactCompatibilityLabel(value: ArtifactCompatibility): string {
  return value.replaceAll("_", " ");
}

export function skillFamilyLabel(value: SkillFamily): string {
  return value === "basic_passive" ? "Basic Passive" : value.replaceAll("_", " ");
}

export function skillModeLabel(value: SkillMode): string {
  return value;
}
