import type {CanonBasis} from "../../../../lib/api/types";
import {CanonicalEntityLink, isCanonEntityType} from "../../../canon/CanonicalEntityLink";

export function CanonBasisView({basis}: {basis: CanonBasis[]}) {
  return (
    <div className="stack">
      <p className="column-subtitle">Grounding references returned by the generation contract. Details are not fetched in this slice.</p>
      {basis.length === 0 ? <div className="empty-state"><div><strong>No Canon basis returned.</strong><span>This candidate has no source projection to display.</span></div></div> : basis.map((item) => (
        <article className="field-card" key={item.source_id}>
          <div className="audit-row"><span>Source ID</span><strong>{item.source_type && isCanonEntityType(item.source_type) ? <CanonicalEntityLink entity_id={item.source_id} entity_type={item.source_type} display_name={item.source_id} /> : item.source_id}</strong></div>
          <div className="audit-row"><span>Source type</span><strong>{item.source_type ?? "Not provided"}</strong></div>
          <div className="audit-row"><span>Supports</span><strong>{item.supports.join(", ") || "Not provided"}</strong></div>
        </article>
      ))}
    </div>
  );
}
