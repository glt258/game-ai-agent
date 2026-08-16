# Character Sources Schema v0.2

`character-sources/0.2` adds field-aware temporal provenance to the persisted
source package. Facts use `character-facts/0.3`; analysis remains
`character-analysis/0.1`.

## Source time context

`SourceRecord` may include:

```yaml
published_at: "2025-04-22"
version_context: "1.7"
```

`published_at` is the formal publication date when known. `version_context` is
an intentionally free-form game/version label such as `1.1`, `2.7`, `3.1`, or
`current roster`. Unknown values remain `null`; version strings are not parsed
or compared as SemVer.

## Source relations

`CharacterProvenance.source_relations` stores directed, field-aware relations
between sources:

```yaml
source_relations:
  - relation_id: version-2-7-supersedes-faction
    source_id: official-version-2-7
    relation_type: supersedes
    target_source_id: official-version-1-1
    field_paths: [combat.native_taxonomy.labels.faction]
```

`relation_type` is a provisional non-empty `snake_case` string and is **not
frozen**. This version uses `supersedes` and `clarifies`.

- `supersedes` means a later source replaces the earlier value for the listed
  fields. The target source cannot remain current evidence for those fields.
- `clarifies` means later wording removes ambiguity without invalidating the
  underlying fact. Both sources may remain current evidence.

Every relation must reference known source IDs, have a unique relation ID, use
at least one resolvable CharacterFacts field path, and point from a source no
earlier than its target when both publication dates are known. Self-relations
are invalid.

## Current evidence policy

`field_evidence` means evidence supporting the **current CharacterFacts value**.
It is not a list of every source that historically mentioned the field.

Historical official sources remain available in `sources` and
`source_relations`, but a source superseded for field `X` must not remain in
`field_evidence[X]`. This is field-aware: the same source may remain evidence
for another field that was not superseded.

`superseded != conflicted`: resolved temporal precedence does not require
`VerificationStatus.conflicted`. Conflict is reserved for cases where the
current value cannot be resolved. Likewise, `clarified != changed`, and a
newer source is not automatically superseding merely because it is newer.

## Authority watch item

First-party hosting does not imply equal objective-fact authority. System
records, patch notes, developer statements, marketing copy, and character
dialogue may differ in authority. Statement-authority fields are intentionally
not implemented in v0.2; this remains a watch item for a future Golden Record
that needs the distinction.
