import type {Combat} from "../../../../lib/api/types";

export function CombatView({combat}: {combat: Combat}) {
  const profile = combat.combat_role_profile;
  return (
    <div className="stack">
      <div className="field-card"><p className="field-name">Primary role</p><p className="field-value">{profile.primary_role ?? "Not specified"}</p></div>
      <div className="field-card"><p className="field-name">Secondary roles</p><div className="tag-row">{profile.secondary_roles.length ? profile.secondary_roles.map((role) => <span className="tag" key={role}>{role}</span>) : <span className="field-value muted">None</span>}</div></div>
      <div className="field-card"><p className="field-name">Skill shadow</p><p className="field-value">{combat.skill_shadow_available ? combat.skill_shadow_status : "Unavailable — not part of this generation result."}</p></div>
      {combat.skill_summary && <div className="field-card full"><p className="field-name">Skill summary</p><p className="field-value">{combat.skill_summary}</p></div>}
    </div>
  );
}
