# Persistence Foundation v0.1

W4-S4A established a deliberately small, storage-agnostic persistence seam for
`SkillDesignArtifact`. W4-S4B extended the same physical store with durable
Character identity and immutable authored revision snapshots. W4-S4C extends
it again with Character-specific Skill bindings, association history, Kit
snapshots, and current Kit assignments. The detailed contracts are
[character_persistence_contract_v0.1.md](character_persistence_contract_v0.1.md)
and
[character_skill_kit_persistence_contract_v0.1.md](character_skill_kit_persistence_contract_v0.1.md).

## Architecture decision

The physical store is SQLite through the Python standard-library `sqlite3`
module. W4-S4's historical audit recommended
`HYBRID_CONTENT_ADDRESSED_SQLITE`; W4-S4A refines that decision for the first
implementation slice and W4-S4D keeps historical reports in the same store:

> v0.1 uses SQLite as the single physical store while preserving
> content-addressed artifact semantics.

This avoids premature cross-store transactions, staged filesystem writes,
orphaned blob cleanup, and split backups. An external content store remains a
future adapter option and is not implemented here.

## Identity and schema

`artifact_digest` remains the SHA-256 identity of canonical SkillKit content.
It is not a database row identity. SQLite uses opaque integer `content_id` and
`record_id` values for storage relationships; neither is exposed as domain
identity.

Schema version `4` is recorded explicitly in `persistence_meta`. Version 1 was
the W4-S4A schema, version 2 added Character identity/revisions, and version 3
added Character Skill/Kit persistence. Opening an older database performs the
transactional additive chains `1 → 2 → 3 → 4`, `2 → 3 → 4`, or `3 → 4`. The
version 4 schema retains every earlier table and adds:

- `skill_artifact_contents`: one canonical JSON payload per unique
  `artifact_digest`.
- `skill_artifact_records`: complete versioned Artifact envelopes, allowing
  multiple authoring records and provenance values for one canonical content.
- `characters`: durable opaque Character identity and the current revision
  pointer.
- `character_revisions`: immutable versioned Character payload snapshots with
  explicit lineage and revision kind.
- `bindings`: immutable Character-specific binding snapshots referencing the
  exact Skill artifact authoring record.
- `associations` and `association_revisions`: durable relationship identity,
  current projection, and immutable placement history.
- `character_kit_contents`: deduplicated canonical Kit content snapshots.
- `character_kit_assignments`, `character_kit_current`, and
  `character_kit_assignment_members`: historical Character assignments,
  current assignment pointer, and persisted relation membership.
- `skill_evaluation_reports`: append-only reports bound to an exact Artifact
  authoring record and evaluator version.
- `character_skill_alignment_reports`: append-only reports bound to an exact
  Artifact record, Character revision, projection version, and source context.
- `character_kit_role_coverage_reports`: append-only reports bound to exact Kit
  content, Character revision, role context fingerprint, and evaluator version.

The W4-S4B, W4-S4C, and W4-S4D migrations do not rewrite or copy Skill
artifact, Character revision, Binding, Association, Kit, or assignment rows.
Existing embedded Alignment and Artifact evaluation snapshots are not invented
as new historical report events during migration. Unknown schema versions fail
closed; no destructive or automatic domain-data migration is attempted.

The canonical JSON payload is the existing
`ProtocolSkillKitCandidate.canonical_json()` representation. The full envelope
is serialized from `SkillDesignArtifact.to_mapping()` using the same stable
UTF-8 JSON conventions. Neither storage serialization changes domain digests.

## Repository and transactions

`PersistenceUnitOfWork` owns the configured SQLite connection, schema
bootstrap/version check, bounded busy timeout, foreign-key activation, and
commit/rollback lifecycle. `SkillArtifactRepository` exposes only the focused
operations needed by this slice:

- save a verified artifact;
- load one authoring record by `record_id`;
- list records by `artifact_digest`;
- inspect canonical content by digest;
- check content existence.

W4-S4B adds `CharacterRepository` and an application-level
`CharacterPersistenceService` for generated creation, edited CAS saves,
current loads, historical revision loads, and revision listing. `CharacterDraft`
remains unchanged; only its authored `to_dict()` fields are persisted.

W4-S4C adds `CharacterSkillRepository` and
`CharacterSkillPersistenceService` for explicit Attach, Detach, Replace,
placement changes, current Skill-state reconstruction, and runtime-derived
freshness, compatibility, and structural validation. W4-S4D adds the focused
`HistoricalReportRepository` and explicit
`HistoricalReportPersistenceService`. They accept typed reports already
produced by the provider-free domain evaluators; they never evaluate, repair,
or call a provider. W4-S4E adds `StudioSaveService` as the application-level
save/open seam: it coordinates Character revision, workspace request/plan
metadata, exact Skill authoring records, association deltas and current Kit
assignment inside one `PersistenceUnitOfWork`. The Web route does not issue
SQL, and the workspace metadata table is deliberately outside `CharacterDraft`.

Historical report rows contain typed indexed input identity/version columns and
canonical UTF-8 JSON payloads. `report_id` is an opaque UUID4 storage identity,
separate from all Artifact, Kit, context, and report digests. Exact duplicate
saves return the existing row. A different deterministic payload for the same
immutable target and evaluator version fails closed. Rows are protected by
append-only SQLite triggers and are ordered by a durable insertion sequence.

Historical reports record observations under a specific input set and contract;
they never define current truth. Freshness, Artifact compatibility, and Kit
structural validation remain runtime-derived. The existing immutable
`SkillDesignArtifact.original_evaluation`, Binding Alignment snapshot, and
CharacterKit contract are unchanged; re-evaluation, re-alignment, and role
coverage re-runs append independent history rather than mutating them.

Saving is idempotent for the exact same envelope. Same canonical content with
different provenance creates separate authoring records while sharing one
canonical content row. Different canonical content creates a separate content
row. Failed unit-of-work scopes roll back both content and record writes.

The adapter verifies the existing domain contract before writing and verifies
the envelope, semantic source digest, canonical content, contract versions, and
database relationships after loading. Malformed, tampered, or unsupported data
fails closed through typed persistence errors. No automatic recompile,
re-evaluation, repair, or domain migration occurs.

SQLite keeps its default journal mode in this local single-process slice; WAL
is deliberately deferred until a measured concurrency requirement exists.
Busy behavior is bounded through the configured SQLite busy timeout.

## Security and portability

The database path is caller-configured and may be outside the repository. Test
databases use temporary Unicode-capable paths. Records contain no API keys,
authorization headers, cookies, raw provider responses, full prompts, or secret
environment values. Provenance is limited to the existing bounded provider,
model, run, compiler, and contract metadata.

Runtime databases and generated test databases are not repository artifacts.
Portable export/import is deferred, but the schema stores UTF-8 JSON and
digest-based references so it can be added without changing domain identity.

## Explicit non-goals

This slice does not implement:

- autosave, approval/publish, or durable live jobs;
- report history pagination, compaction, or garbage collection;
- filesystem CAS, PostgreSQL, an ORM, Alembic, Redis, repair, RAG, or
  fine-tuning.
