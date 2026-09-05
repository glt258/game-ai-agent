import {useState} from "react";

import type {
  CharacterSkillContextRequest,
  CharacterSkillContextResponse,
  CharacterSkillDesignResponse,
  CharacterSkillAssociation,
  CharacterSkillSlot,
  CharacterKitRoleCoverageResponse,
} from "../../../lib/api/types";
import {SkillPlayground} from "../../skill-playground/SkillPlayground";
import {
  artifactCompatibilityLabel,
  skillFamilyLabel,
  skillFreshness,
  skillModeLabel,
  type SkillFreshness,
} from "../skill-session";
import {RoleCoveragePanel} from "./RoleCoveragePanel";

interface SkillsViewProps {
  characterInput: CharacterSkillContextRequest;
  context: CharacterSkillContextResponse | null;
  slots: CharacterSkillSlot[];
  attachedSkills: CharacterSkillAssociation[];
  designerOpen: boolean;
  onDesignSkill: () => void;
  onDesignAgain: () => void;
  onAttach: (result: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => void;
  onDetach: (associationId: string) => void;
  roleCoverage?: CharacterKitRoleCoverageResponse | null;
  roleCoverageLoading?: boolean;
  roleCoverageError?: string | null;
}

type ReplacementRequest = {
  result: CharacterSkillDesignResponse;
  slot: CharacterSkillSlot;
  existing: CharacterSkillAssociation;
};

export function SkillsView({
  characterInput,
  context,
  slots,
  attachedSkills,
  designerOpen,
  onDesignSkill,
  onDesignAgain,
  onAttach,
  onDetach,
  roleCoverage = null,
  roleCoverageLoading = false,
  roleCoverageError = null,
}: SkillsViewProps) {
  const [replacement, setReplacement] = useState<ReplacementRequest | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const orderedSkills = [...attachedSkills].sort((left, right) => left.order - right.order || left.association_id.localeCompare(right.association_id));
  const kitStructuralStatus = attachedSkills.every((association, index, values) => {
    const slot = slots.find((item) => item.id === association.slot);
    const count = values.filter((item) => item.slot === association.slot).length;
    return slot !== undefined
      && new Set(values.map((item) => item.artifact.identity.artifact_digest)).size === values.length
      && (slot.max_items === null || count <= slot.max_items)
      && association.order === slot.order
      && (association.association_id.startsWith("session-skill:") || association.association_id.length > 0);
  }) ? "PASS" : "FAIL";

  const requestAttach = (result: CharacterSkillDesignResponse, slot: CharacterSkillSlot) => {
    setNotice(null);
    const duplicate = attachedSkills.find((item) => item.artifact.identity.artifact_digest === result.artifact_digest);
    if (duplicate) {
      setNotice("This Skill artifact is already attached to this Character session.");
      return;
    }
    const existing = slot.max_items !== null && attachedSkills.find((item) => item.slot === slot.id);
    if (existing) {
      setReplacement({result, slot, existing});
      return;
    }
    onAttach(result, slot);
  };

  const confirmReplacement = () => {
    if (!replacement) return;
    onDetach(replacement.existing.association_id);
    onAttach(replacement.result, replacement.slot);
    setReplacement(null);
  };

  return (
    <div className="stack">
      <div className="session-notice" role="note">
        <strong>待保存的角色工作区</strong>
        <span>新的技能关联会暂存在当前工作区，点击“保存角色”后才会保存。</span>
      </div>
      <div className="session-notice" data-testid="character-kit-summary" role="status">
        <strong>角色技能组 · {kitStructuralStatus === "PASS" ? "通过" : "未通过"}</strong>
        <span>当前有 {attachedSkills.length} 个技能关联；结构检查与定位覆盖检查相互独立。</span>
      </div>
      <RoleCoveragePanel result={roleCoverage} loading={roleCoverageLoading} error={roleCoverageError} />
      {replacement && (
        <div className="confirm-strip" role="alertdialog" aria-label="确认替换技能槽位">
          <span>{replacement.slot.label} 已有技能，是否替换？</span>
          <button className="button-primary" onClick={confirmReplacement}>替换</button>
          <button className="button-ghost" onClick={() => setReplacement(null)}>取消</button>
        </div>
      )}
      {notice && <div className="error-notice" role="alert">{notice}</div>}
      {orderedSkills.length === 0 && (
        <div className="empty-state skills-empty-state">
          <div><strong>当前角色还没有关联技能。</strong><span>选择技能定位和类型，查看结果后再绑定到角色。</span></div>
          <button className="button-primary" onClick={onDesignSkill}>设计技能</button>
        </div>
      )}
      {orderedSkills.map((association) => {
        const placementIndex = orderedSkills.filter((item) => item.slot === association.slot).findIndex((item) => item.association_id === association.association_id) + 1;
        const freshness: SkillFreshness | null = context
          ? skillFreshness(association.binding.source_context_fingerprint, context.source_context_fingerprint)
          : null;
        const alignment = association.binding.alignment;
        return (
          <article className="field-card full attached-skill-card" key={association.association_id}>
            <div className="attached-skill-header">
              <div>
                <p className="field-name">{association.slot.toUpperCase()}{association.slot === "passive" ? ` ${placementIndex}` : ""} · 技能关联</p>
                <strong>{skillFamilyLabel(association.family)} · {skillModeLabel(association.mode)}</strong>
              </div>
              <span className="status-chip passed">{association.slot.toUpperCase()}</span>
            </div>
            <p className="field-value">{association.display_summary}</p>
            <div className="attached-skill-meta">
                <span>技能检查：{association.artifact.original_evaluation.outcome === "PASS" ? "通过" : "未通过"}</span>
              <span>角色适配：{alignment.status === "PASS" ? "通过" : "未通过"}</span>
              <span>角色上下文：{freshness === "current" ? "当前" : freshness === "stale" ? "已过期" : "检查中"}</span>
                <span>技能方案：{artifactCompatibilityLabel(association.artifact_compatibility)}</span>
            </div>
            {freshness === "stale" && <p className="stale-notice">角色上下文已变化，请重新设计技能以刷新关联。</p>}
            {freshness !== "stale" && <p className="alignment-inline-summary">{alignment.summary}</p>}
            <div className="reference-actions">
              <button className="button-secondary" onClick={onDesignAgain}>重新设计</button>
              <button className="button-ghost" onClick={() => onDetach(association.association_id)}>解除关联</button>
            </div>
            <details className="attached-skill-inspect">
              <summary>查看技术详情</summary>
              <pre className="json-view">{JSON.stringify({artifact: association.artifact, binding: association.binding}, null, 2)}</pre>
            </details>
          </article>
        );
      })}
      {orderedSkills.length > 0 && !designerOpen && <button className="button-primary" onClick={onDesignSkill}>再设计一个技能</button>}
      {designerOpen && context && <SkillPlayground key={context.source_context_fingerprint} embedded characterInput={characterInput} characterContext={context} slotOptions={slots} onAttach={requestAttach} />}
    </div>
  );
}
