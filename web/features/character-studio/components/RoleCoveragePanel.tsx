import type {CharacterKitRoleCoverageResponse} from "../../../lib/api/types";
import {characterRoleLabel} from "../character-planner-view";

interface RoleCoveragePanelProps {
  result: CharacterKitRoleCoverageResponse | null;
  loading: boolean;
  error: string | null;
}

export function RoleCoveragePanel({result, loading, error}: RoleCoveragePanelProps) {
  const coverage = result?.role_coverage;
  const status = loading ? "正在检查" : coverage?.status === "PASS" ? "通过" : coverage?.status === "FAIL" ? "未通过" : error ? "不可用" : "未检查";
  const statusClass = status === "通过" ? "passed" : status === "未通过" ? "failed" : "warning";

  return (
    <section className="session-notice" data-testid="character-kit-role-coverage" aria-live="polite">
      <strong>定位覆盖 · <span className={`status-chip ${statusClass}`}>{status}</span></strong>
      {loading && <span>正在检查当前技能组是否支持角色定位…</span>}
      {!loading && error && <span>{error}</span>}
      {!loading && !error && !coverage && <span>当前会话还没有进行定位覆盖检查。</span>}
      {coverage && (
        <>
          <span>{coverage.summary}</span>
          <div className="attached-skill-meta">
            <span>主要定位：{characterRoleLabel(coverage.coverage.primary.role)} · {coverage.coverage.primary.supported ? "已覆盖" : "未覆盖"}</span>
            {coverage.coverage.secondary.map((item) => (
              <span key={item.role}>辅助定位：{characterRoleLabel(item.role)} · {item.supported ? "已覆盖" : "未覆盖"}</span>
            ))}
          </div>
          {coverage.findings.length > 0 && (
            <ul>
              {coverage.findings.map((finding) => <li key={`${finding.code}-${finding.field_path}`}>{finding.message}</li>)}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
