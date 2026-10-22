# Reference Corpus Pilot Freeze v0.1

## Freeze Status

```text
REFERENCE CORPUS PILOT READY
SCHEMA FROZEN FOR EXPANSION
```

This Freeze records the Reference Corpus Golden Pilot as the stable baseline
for controlled expansion. It does not mean that the schema can never change.
A schema revision is justified only when real commercial data cannot be
represented honestly by the frozen version.

## Scope

The pilot covers the persisted Character Reference structure:

```text
CharacterReference
├── facts.yaml
├── sources.yaml
└── analysis.yaml
```

`facts.yaml` stores source-supported commercial-game facts, `sources.yaml`
stores provenance, evidence, and verification, and `analysis.yaml` stores
normalized external design analysis.

## Frozen Schema Versions

```text
CharacterFacts:    character-facts/0.3
CharacterSources:  character-sources/0.2
CharacterAnalysis: character-analysis/0.1
GameCatalog:       game-catalog/0.1
```

Freeze decisions:

```text
CharacterFacts v0.3:     FROZEN
CharacterSources v0.2:   FROZEN
CharacterAnalysis v0.1:  FROZEN
GameCatalog v0.1:        FROZEN FOR PILOT EXPANSION
```

No model, loader, manifest-version, or schema migration is part of this
checkpoint.

## Production Game Catalog

The catalog currently registers:

```text
test-game-alpha
test-game-beta
genshin-impact
wuthering-waves
zenless-zone-zero
neverness-to-everness
```

The first two entries are synthetic test games. The four commercial entries
are the games represented by the Golden Records below.

## Golden Character References

The four accepted, catalog-backed Golden Records are:

```text
genshin-impact:keqing
wuthering-waves:jinhsi
zenless-zone-zero:jane-doe
neverness-to-everness:shinku
```

```text
Four Golden Records: 4 / 4 ACCEPTED
Catalog-backed validation: 4 / 4 PASS
Golden Pilot Schema: READY_FOR_EXPANSION
Bulk Ingestion Infrastructure: READY
```

## Golden Stress-Test Coverage

The records are retained as schema stress tests, not as a comparative
explanation of their gameplay:

| Golden | Validated design space |
| --- | --- |
| Keqing | Baseline / simple representation |
| Jinhsi | Complex mechanic graph with Resource, State, Ability, TeamInteraction, and multi-stage MechanicRelation edges |
| Jane Doe | Temporal provenance, including `clarifies` versus `supersedes`, plus self-state versus target-state scope |
| Shinku | Sparse multi-source evidence, secondary-heavy combat evidence, honest `unknown`/`null`, and sparse CharacterAnalysis |

## Provenance Semantics

`field_evidence` supports the **current** `CharacterFacts` value. It is not a
list of every historical source that mentioned the field. Historical sources
may remain in `sources`, but a superseded source must not remain current
evidence for the superseded field.

`supersedes` means that an old valid fact was replaced by a newer valid fact;
`superseded != conflicted`.

`clarifies` means that wording or meaning was clarified without changing the
underlying behavior; `clarifies != gameplay change`.

## Facts Semantics

Native and normalized vocabularies remain separate:

```text
Native taxonomy       → CharacterFacts
Normalized taxonomy   → CharacterAnalysis
```

Unknown facts remain `null`, `[]`, or `unknown` as appropriate. They are not
inferred into Facts. The provisional state subject vocabulary is currently:

```text
self
target
unknown
```

The mechanic graph uses `AbilityFact`, `ResourceFact`, `StateFact`,
`TeamInteractionFact`, and `MechanicRelation`. Relation types remain
validated provisional snake_case strings rather than a permanent enum.

## Analysis Semantics

Analysis is normalized design inference derived from Facts and Sources. It
does not backfill inferred values into Facts.

`PrimaryLoop` describes mechanic flow, not an optimal rotation.

Sparse evidence follows this rule:

```text
missing evidence != low
```

When supported by the schema, use `unknown` or `null` rather than converting
missing evidence into a low ordinal or score.

Completeness is distinct from verification confidence. The current quality
calculation primarily represents completeness, not an evidence-quality score.

## Known Limitations / Watch Items

### KL-RC-001 — Statement Authority

**Status:** WATCH ITEM

Developer/system/patch-note/marketing/dialogue statements do not necessarily
have equal objective-fact authority. Future revision is triggered when
first-party statement-authority ambiguity creates an unresolved stored Fact
conflict. There is no blocking Golden case currently.

### KL-RC-002 — ResourceLoop Structure

**Status:** WATCH ITEM

`resource_loop` prose currently represents the Jinhsi, Jane Doe, and Shinku
analyses. Future revision is triggered when repeated machine queries require
structured resource-loop stages.

### KL-RC-003 — TeamDependency Nuance

**Status:** WATCH ITEM

The current `OrdinalBand` is sufficient for the present `high`/`low`
distinction. Repeated real records that lose a necessary distinction trigger
review.

### KL-RC-004 — Evasion-Centric Representation

**Status:** WATCH ITEM

Jane Doe is representable through MechanicRelation, PrimaryLoop,
CoreMechanics, Archetypes, and Mobility. A dedicated evasion schema is not
needed unless real records expose a missing representation boundary.

### KL-RC-005 — Relation-Level Provenance Granularity

**Status:** WATCH ITEM

Collection-level `combat.relations` evidence is sufficient for the current
Golden set. Review relation-ID-level evidence only if a specific relation's
provenance becomes disputed; do not introduce JSONPath preemptively.

### KL-RC-006 — State Subject Scope Vocabulary

**Status:** ACCEPTED LIMITATION

`self`, `target`, and `unknown` are a provisional vocabulary, not a complete
ontology. A real Golden requiring `ally`, `party`, `field`, `summon`, or
another scope triggers review.

### KL-RC-007 — Completeness vs Evidence Strength

**Status:** WATCH ITEM

Deterministic quality currently describes completeness more closely than
evidence confidence. Future evidence-quality, primary-coverage, or
verification-strength fields remain possible but are not current blockers.

### KL-RC-008 — Secondary-Heavy Analysis

**Status:** WATCH ITEM

Current `confidence` fields express analysis evidence strength. Review an
explicit evidence-tier field only if downstream decisions repeatedly need the
analysis source tier directly.

## Expansion Contract

The remaining 16 CharacterReferences may be ingested under this frozen
baseline after human review:

```text
May be ingested under frozen baseline: YES
Started in this checkpoint: NO
```

All expansion must preserve these boundaries:

```text
Facts:     source-supported only
Sources:   field-aware provenance
Analysis:  derived from Facts + Sources
Unknown:   remain null / [] / unknown
```

Model memory must not enter Facts. Normalized taxonomy must not enter native
Facts. Analysis inference must not be backfilled into Facts.

## Reference Corpus vs Canon

```text
Reference Corpus != Project Canon
```

Commercial-game reference data must never automatically enter Canon. The
Reference Corpus is external design reference data and can only influence
project generation through an explicit future conversion boundary.

The intended future flow is:

```text
External Sources
→ CharacterReference
→ PatternExtractor
→ Design Pattern Corpus
→ CharacterGenerationAgent
```

`PatternExtractor`, the Design Pattern Corpus, and agent integration are not
implemented in this checkpoint.

## Non-Goals

This Freeze does not start the remaining 16 records, implement
`PatternExtractor`, change runtime or Canon code, alter the schema, or create
a tag. It also does not claim production completion or permanent finality.

## Verification

Pre-Freeze baseline on the existing Golden commit:

```text
Reference Corpus tests:         81 passed
Production Catalog tests:        6 passed
Full project suite:            551 passed, 1 skipped
python -m compileall src tests:  PASS
git diff --check:                PASS
```

## Git Baseline

```text
Branch: codex/character-generation-agent
Baseline before Freeze commit: 77bbc60
```

The Freeze commit records this document as the reviewable pilot checkpoint.
