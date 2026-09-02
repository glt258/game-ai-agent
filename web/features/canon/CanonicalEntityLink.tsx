import Link from "next/link";

import type {CanonEntityType} from "../../lib/api/types";

const CANON_ENTITY_TYPES: readonly CanonEntityType[] = ["faction", "lore", "character", "project", "case", "incident", "story"];

export function isCanonEntityType(value: string | null | undefined): value is CanonEntityType {
  return value !== undefined && value !== null && CANON_ENTITY_TYPES.includes(value as CanonEntityType);
}
export function canonicalEntityHref(entityId: string): string {
  return `/canon/${encodeURIComponent(entityId)}`;
}

export function CanonicalEntityLink({
  entity_id,
  entity_type,
  display_name,
}: {
  entity_id: string;
  entity_type: CanonEntityType;
  display_name?: string;
}) {
  return (
    <Link className="canonical-link" href={canonicalEntityHref(entity_id)}>
      <span>{display_name || entity_id}</span>
      <small>{entity_type} · {entity_id}</small>
    </Link>
  );
}
