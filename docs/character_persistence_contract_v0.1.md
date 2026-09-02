# Character Persistence Contract v0.1

W4-S4B adds durable Character identity and immutable authored revisions behind
the existing SQLite persistence seam. `CharacterDraft` remains the runtime
candidate contract; it is mapped into a versioned revision payload and is not
given persistence fields.

## Identity and revision contract

- `character_id` is an opaque UUID4 owned by the persisted Character entity.
- `revision_id` is an independent opaque UUID4 for one authored snapshot.
- The revision contract is `character-revision/0.1.0`.
- The only revision kinds are `GENERATED` and `EDITED`.
- A revision is immutable after commit.
- Revision IDs are not content hashes.
- `created_at` is UTC operational metadata and is not identity.

The persisted Character entity stores only its durable identity, timestamps,
and `current_revision_id`. Authored Character state exists authoritatively in
`character_payload_json`; there is no duplicate `characters.name` or other
authored column.

```text
Character C1
│
├─ R1 GENERATED
│    parent = null
│
├─ R2 EDITED
│    parent = R1
│
└─ R3 EDITED
     parent = R2

current_revision_id = R3
```

`CharacterRevision` is not a `CharacterKit` revision. Kit persistence does not
exist in W4-S4B and will be introduced separately in W4-S4C.

## Payload authority

The mapper starts from the existing `CharacterDraft.to_dict()` representation
and persists the authored fields, including name, age information, occupation,
social role, role profile, design pitch, personality, background, story hook,
relationships, ability concept, knowledge scope, Canon basis, new design
fields, open questions, constraints, and story link.

The runtime `draft_id` and `status` are excluded. Generation requests, plans,
model/retrieval/validation audit, HTTP IDs, browser state, live jobs, provider
state, CharacterSkillDesignContext, attached Skills, CharacterKit, and UI state
are also excluded. Loading uses `CharacterDraft.from_mapping()` with a
reconstruction-only draft ID and `status="draft"`.

Reference Corpus and full Canon data are never copied into a Character
revision. Existing Canon IDs and Character-owned references remain ordinary
authored fields when they are already part of the CharacterDraft contract.

## Lifecycle and concurrency

`CharacterRepository.create()` atomically writes the Character, its initial
`GENERATED` revision, and the current pointer. Edited saves use
`expected_current_revision_id` and an atomic compare-and-swap pointer update.
The normal save path is:

```text
expected current check
→ compare authored payload
→ return current revision when identical
→ insert new EDITED revision with parent=current
→ CAS current_revision_id
```

An identical authored payload creates no new revision. Any changed authored
payload creates a new revision. A stale expected revision raises a typed
conflict containing only expected/current revision IDs; there is no automatic
merge.

Historical revisions remain loadable and are listed with revision ID, kind,
parent, UTC timestamp, and current status. Revision ownership is checked on
every historical load.

## Schema migration and integrity

W4-S4A schema version 1 is migrated transactionally to schema version 2. The
existing Skill artifact tables and rows remain unchanged. Schema migration is
owned by `PersistenceUnitOfWork`, not by `CharacterRepository`.

Malformed JSON, invalid Character payloads, wrong ownership, unsupported
revision contracts, missing current revisions, and unknown Characters fail
closed through typed persistence errors. No automatic migration, repair,
merge, or rewrite occurs.

## Scope exclusions

W4-S4B does not persist CharacterSkillArtifactBinding,
CharacterSkillAssociation, CharacterSkillCollection, CharacterKit, Kit
assignments, historical reports, Web Save/Open routes, Saved Characters UI,
autosave, approval/publish state, export/import, live jobs, or provider raw
material.
