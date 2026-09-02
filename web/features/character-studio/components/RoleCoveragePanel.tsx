import type {CharacterKitRoleCoverageResponse} from "../../../lib/api/types";

interface RoleCoveragePanelProps {
  result: CharacterKitRoleCoverageResponse | null;
  loading: boolean;
  error: string | null;
}

export function RoleCoveragePanel({result, loading, error}: RoleCoveragePanelProps) {
  const coverage = result?.role_coverage;
  const status = loading ? "EVALUATING" : coverage?.status ?? (error ? "UNAVAILABLE" : "NOT_EVALUATED");
  const statusClass = status === "PASS" ? "passed" : status === "FAIL" ? "failed" : "warning";

  return (
    <section className="session-notice" data-testid="character-kit-role-coverage" aria-live="polite">
      <strong>Role Coverage · <span className={`status-chip ${statusClass}`}>{status}</span></strong>
      {loading && <span>Evaluating role coverage for the current Kit…</span>}
      {!loading && error && <span>{error}</span>}
      {!loading && !error && !coverage && <span>Role coverage has not been evaluated for the current session.</span>}
      {coverage && (
        <>
          <span>{coverage.summary}</span>
          <div className="attached-skill-meta">
            <span>Primary: {coverage.coverage.primary.role} · {coverage.coverage.primary.supported ? "SUPPORTED" : "NOT COVERED"}</span>
            {coverage.coverage.secondary.map((item) => (
              <span key={item.role}>Secondary: {item.role} · {item.supported ? "SUPPORTED" : "NOT COVERED"}</span>
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
