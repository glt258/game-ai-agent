# Historical Report Persistence Contract v0.1

W4-S4D stores three typed, append-only historical observations in the same
SQLite store as W4-S4A–S4C:

- Skill Evaluation (`SkillValidationReport`);
- Character-Skill Alignment (`CharacterSkillAlignmentResult`);
- CharacterKit Role Coverage (`CharacterKitEvaluationResult`).

The repository accepts reports produced by the existing domain evaluators. It
does not run an evaluator, call a provider, repair a report, or expose Web
routes.

## Identity and payloads

Every row has an opaque durable UUID4 `report_id`, which is never a content or
input identity. Each row also stores canonical UTF-8 JSON for the exact typed
report and indexed identity/version columns. The row insertion sequence gives
deterministic historical ordering.

Skill Evaluation binds `artifact_record_id`, `artifact_digest`, the immutable
Artifact contract version, and an evaluator version. By default the evaluator
version is the version already recorded on the Artifact; callers may explicitly
record another evaluator version without mutating the Artifact.

Alignment binds `character_id`, an immutable `character_revision_id`, the exact
`artifact_record_id` and digest, `source_context_fingerprint`, the frozen
Alignment version, and the Character projection version. The persistence
digest is computed from the existing stable Alignment mapping because the
frozen Alignment result has no semantic report-digest field.

Role Coverage binds `character_id`, an immutable Character revision, the exact
Kit content record and `kit_digest`, the role evaluation context fingerprint,
and the evaluator version already present in the result.

## Append-only and idempotency

SQLite uniqueness constraints define one deterministic observation per exact
immutable target and evaluator/context version. Saving the same canonical
payload again returns the original row and does not create a duplicate. A
different payload for the same deterministic target/version raises a typed
write conflict. Database triggers reject UPDATE and DELETE for all three
report tables. Re-evaluation, re-alignment, and role-coverage re-runs therefore
append a new row only when their immutable identity/version changes.

## Integrity and migration

Before saving and after loading, the adapter verifies the typed contract,
canonical JSON, report digest where the domain contract provides one, indexed
metadata, and referenced Artifact/Character/Kit rows. Digest, foreign-key,
payload, contract, and cross-Character ownership mismatches fail closed.

Schema migration is additive and transactional: `v1 → v2 → v3 → v4`,
`v2 → v3 → v4`, and `v3 → v4` remain supported. Existing Artifact, Character,
Binding, Association, Kit, and assignment rows are preserved. The migration
does not backfill embedded Artifact Evaluation or Binding Alignment snapshots
as fabricated historical events; future explicit report saves populate the
history tables.

Historical rows do not define current truth. They do not store `is_current`,
freshness, compatibility, or structural validation authority. Those values are
derived by the current runtime contracts. Existing embedded evaluation and
Alignment snapshots remain immutable and valid independently of queryable
history.

## Boundaries and limitations

The implementation uses only stdlib `sqlite3`, `Path`, and UTF-8 JSON. It does
not add Web history APIs, Saved Characters UI, autosave, live-job persistence,
Repair, RAG, provider response storage, prompts, secrets, PostgreSQL,
SQLAlchemy, Alembic, Redis, report pagination, compaction, or garbage
collection.
