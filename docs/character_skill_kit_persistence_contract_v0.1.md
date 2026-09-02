# Character Skill and Kit Persistence Contract v0.1

W4-S4C persists the Character-specific relationship between immutable
`SkillDesignArtifact` content and a durable Character. It keeps the existing
domain separation:

```text
SkillDesignArtifact
≠ CharacterSkillArtifactBinding
≠ CharacterSkillAssociation
≠ CharacterKit
```

## Identity and ownership

- `binding_id` is an opaque UUID4 for one immutable Character-context binding.
- A binding references the exact `skill_artifact_records.record_id` and also
  stores/verifies its `artifact_digest`.
- `association_id` is an opaque durable UUID4. It is separate from the
  session-only `session-skill:<slot>:<artifact_digest>` domain key.
- Association identity belongs to one Character and remains stable across
  placement revisions.
- `association_revision_id` identifies an immutable placement/metadata
  snapshot. Placement changes append a revision.
- `kit_digest` is the existing domain Kit content identity; `kit_record_id` is
  a separate SQLite storage identity.
- `assignment_id` identifies one historical Character → Kit assignment.

```text
Character C1
│
├─ Character Revision R3
│
├─ Association A1
│    ├─ Binding B1
│    │    └─ Artifact Record AR1
│    │           └─ artifact_digest D1
│    └─ Association Revision A1R1
│
├─ Association A2
│    ├─ Binding B2
│    │    └─ Artifact Record AR2
│    │           └─ artifact_digest D2
│
└─ Current Kit Assignment KA2
     └─ Kit Content K2
          kit_digest = ...
```

`CharacterRevision` ≠ `AssociationRevision` ≠ Kit assignment identity ≠
`SkillDesignArtifact`.

## Binding contract

The complete existing `CharacterSkillArtifactBinding` mapping is stored as a
versioned JSON snapshot. It includes the binding contract version, artifact
digest, source context fingerprint, Alignment result, Alignment version, and
Character projection version. The exact artifact authoring record is retained;
the persistence layer never chooses an arbitrary record with the same digest.

Bindings are immutable. A new Character context or Alignment result creates a
new binding. The stored Alignment is historical evidence against its stored
fingerprint; it is never rewritten after a Character edit.

## Association lifecycle

The normal lifecycle is an immutable revision chain behind a mutable current
pointer:

```text
Association A1
│
├─ AR1  placement = primary
├─ AR2  placement = utility
└─ current_revision_id = AR2
```

Attach creates a new association and its first revision. Placement change
keeps the durable `association_id` and appends a new revision. Detach clears
the association current pointer and records its close metadata while retaining
all historical revisions. Replace ends the old association and creates a new
association identity, because the attachment lifecycle now refers to a new
artifact/binding.

The authoritative placement vocabulary remains `primary`, `secondary`,
`passive`, and `utility`. Primary and secondary allow one active association;
passive and utility support multiple ordered associations. Ordinals are
recomputed from the existing Kit canonical ordering and persisted in Kit
assignment relations; old association revisions are never mutated.

## Kit snapshots and assignments

`CharacterKit` is immutable aggregate content. The persistence adapter calls
the existing Kit builder and structural validator; it does not create a second
ordering or digest algorithm. Kit content snapshots are deduplicated by the
existing `kit_digest`, allowing the same Kit content to be assigned to multiple
Characters. Assignments and assignment-member relations remain Character-
specific and preserve exact association revisions and artifact records.

Loading verifies both sides of the contract:

```text
persisted Kit snapshot
        +
current association relations
        ↓
rebuild CharacterKit
        ↓
verify kit_digest and structural validation
```

Snapshot/relation mismatch, duplicate artifacts, invalid placement, unknown
contracts, digest mismatch, or tampering fails closed. An initial Character
has no Kit assignment. Detaching its final association creates an explicit
empty Kit assignment, which is distinct from no assignment.

## Transaction and concurrency semantics

Attach, Detach, Replace, and placement change are single transactions. Each
operation guards the expected Character revision and the expected current Kit
assignment. The assignment pointer uses compare-and-swap semantics; stale
operations raise `CharacterSkillPersistenceConflictError` and perform no
automatic merge.

Attach verifies the artifact record, binding, Skill Evaluation `PASS`,
Alignment `PASS`, current context fingerprint, and current artifact
compatibility before writing. Detach never deletes the shared Skill artifact.

## Derived state

Freshness is derived by comparing the current Character Skill projection
fingerprint with each stored binding fingerprint. Compatibility is derived by
`inspect_skill_artifact_compatibility` against current runtime versions.
Structural status is recomputed by `CharacterKitStructuralValidator`.
The separate W4-S4D HistoricalReportRepository can explicitly record typed
Skill Evaluation, Alignment, and Role Coverage observations; this S4C
repository does not auto-record them and does not treat them as current truth.

## Migration and boundaries

Schema v2 migrates transactionally to v3 by adding binding, association,
association revision, Kit content, assignment, current-pointer, and assignment
member tables. W4-S4D then adds the v4 historical report tables. The
v1 → v2 → v3 → v4 chain and direct v2 → v3 → v4 path preserve all existing
artifact and Character revision data. Unknown future schema versions fail
closed.

W4-S4C does not add Web Save/Open, React changes, autosave, approval/publish,
live-job persistence, deletion/archive, export/import, Redis, PostgreSQL, SQLAlchemy,
Alembic, Repair, RAG, LoRA, or fine-tuning.
