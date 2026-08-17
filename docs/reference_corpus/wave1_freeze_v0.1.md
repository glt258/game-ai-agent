# Reference Corpus Wave 1 Freeze v0.1

```text
REFERENCE CORPUS WAVE 1 READY
WAVE 1 FROZEN
READY FOR WAVE 2
```

This document records the Human Review-approved Wave 1 Completion Gate. It
freezes the first four expansion records as a reviewed, catalog-backed sample;
it does not claim that the planned 20-record corpus is complete.

## 1. Scope and Commit

Wave 1 consists of four expansion records added after the Golden Pilot:

| Record | Commit |
| --- | --- |
| `genshin-impact:furina` | `156a1c3` |
| `wuthering-waves:shorekeeper` | `2370b8b` |
| `zenless-zone-zero:nicole` | `c1f4086` |
| `neverness-to-everness:fadia` | `ef52143` |

The freeze is documentation-only at the current baseline. Runtime, Canon,
CharacterGenerationAgent, NPC Agent, Canon Checker, and the Reference Corpus
schemas are unchanged.

## 2. Frozen Schemas

```text
CharacterFacts:    character-facts/0.3
CharacterSources:  character-sources/0.2
CharacterAnalysis: character-analysis/0.1
GameCatalog:       game-catalog/0.1
```

Wave 1 required no schema-version change. The frozen subject vocabulary
remains `self`, `target`, and `unknown`.

## 3. Corpus Inventory

```text
Golden:                   4
Wave 1 Expansion:         4
Total production records: 8
```

Golden records:

- `genshin-impact:keqing`
- `wuthering-waves:jinhsi`
- `zenless-zone-zero:jane-doe`
- `neverness-to-everness:shinku`

Wave 1 records:

- `genshin-impact:furina`
- `wuthering-waves:shorekeeper`
- `zenless-zone-zero:nicole`
- `neverness-to-everness:fadia`

All Wave 1 records have `facts.yaml` and `sources.yaml`. Their
`analysis.yaml` files are intentionally absent in this phase; `analysis
missing` is not a validation failure.

## 4. Main Finding: State Scope

| Record | Planning assumption | Actual committed representation |
| --- | --- | --- |
| Furina | party-wide state | `TeamInteraction + TeamMechanics` |
| Shorekeeper | field-state | `TeamInteraction + TeamMechanics + AbilityEffect` |
| Nicole | grouping/field behavior | `TeamMechanics.grouping + ability prose` |
| Fadia | party defensive state | `TeamInteraction + TeamMechanics` |

Wave 1 required a new `StateFact.subject_scope`: **NO**.

## 5. Summon Graphability

Two confirmed production cases establish repeated real-world friction:

1. Furina: Salon Members / Singer are stored in `mechanics.summons`, but
   cannot be `MechanicRef` targets.
2. Shorekeeper: butterfly entities are stored in `mechanics.summons`, but
   cannot be `MechanicRef` targets.

The current schema cannot directly represent `ability → creates → summon` or
the summon’s own attack/heal/target graph. This remains a **WATCH ITEM** and
**NON-BLOCKING**. `SummonFact` is not required by this freeze.

Iroi is a future Wave 2 research candidate for independent sample #3, not a
confirmed production case.

## 6. External Team-Event Graphability

Two confirmed production cases establish the same non-blocking friction:

1. Shorekeeper: a party member Intro action triggers Stellarealm evolution.
2. Fadia: ally damage intake triggers redirect/share behavior.

The current `MechanicRef` cannot directly represent an external teammate
action/event source. This remains a **WATCH ITEM** and **NON-BLOCKING**;
`TeamActionRef` is not created.

Mortefi and Trigger remain research-only future pressure samples and are not
counted as confirmed production cases.

## 7. TeamMechanics Coverage

This is actual committed Facts coverage, not roster-planning inference:

| Category | Wave 1 records |
| --- | --- |
| buffs | Furina, Shorekeeper, Fadia |
| debuffs | Nicole, Fadia |
| healing | Furina, Shorekeeper, Fadia |
| shielding | none |
| grouping | Shorekeeper, Nicole |
| off_field_effects | Furina, Shorekeeper |
| interactions | Furina, Shorekeeper, Nicole, Fadia |

## 8. Resource Coverage

| Record | Character-specific resources |
| --- | --- |
| Furina | Fanfare |
| Shorekeeper | Empirical Data; Deductive Data |
| Nicole | none |
| Fadia | none |

Global/system resources are not incorrectly modeled. Character-specific
resources remain distinct from game-wide Energy, HP, and other combat stats.

## 9. Provenance Findings

| Record | Evidence pattern |
| --- | --- |
| Furina | primary-heavy + secondary detail |
| Shorekeeper | primary identity/native taxonomy + secondary kit |
| Nicole | primary identity/native taxonomy + secondary kit |
| Fadia | primary identity/availability + secondary-heavy kit |

Wave 1 confirms that completeness is not verification strength. Shinku and
Fadia both exhibit a secondary-heavy combat-evidence pattern; this is
**CONFIRMED FOR CURRENT SAMPLE**, not a claim about all NTE data.

## 10. Frozen Schema Health

### CharacterFacts 0.3

**STABLE WITH WATCH ITEMS**

Watch items:

- summon graphability;
- external team-event graphability;
- historical/current identity boundary;
- distribution/acquisition metadata has no dedicated field, but is non-blocking.

### CharacterSources 0.2

**STABLE**

`field_evidence` remains valid, current and historical sources remain
distinguishable, the source reliability model remains sufficient, temporal
source relations remain available, and there is no Wave 1 provenance blocker.

Blocking schema defect: **NO**.

## 11. Existing Known Limitations

The existing Pilot Freeze numbering is retained without additions:

- KL-RC-001 Statement Authority
- KL-RC-002 ResourceLoop Structure
- KL-RC-003 TeamDependency Nuance
- KL-RC-004 Evasion-Centric Representation
- KL-RC-005 Relation-Level Provenance Granularity
- KL-RC-006 State Subject Scope Vocabulary
- KL-RC-007 Completeness vs Evidence Strength
- KL-RC-008 Secondary-Heavy Analysis

Wave 1 adds observations to the existing watch-item record only:

- summon graphability: repeated watch observation;
- external team-event graphability: repeated watch observation.

No KL-RC-009 or KL-RC-010 is introduced.

## 12. Wave 2 and Future Research Status

Wave 2 production ingestion: **NOT STARTED**.

Research dossiers are ready for Nahida, Mortefi, Caesar King, and Iroi. These
are not production `CharacterReference` records; no corresponding production
YAML exists.

If Iroi production ingestion confirms summon entities that require graph
relations, `SummonFact` may become a **NARROW SCHEMA REVIEW CANDIDATE**. This
would not be an automatic schema revision. If Mortefi production ingestion
confirms teammate attack → coordinated attack behavior, it supplies another
external-team-event production sample.

Hotori remains **CONDITIONAL for Wave 4**. Official identity/release support
exists, but current research still lacks sufficient first-party combat wording
for the meter, time-manipulation, and counter mechanics. A Wave 4
source-feasibility gate remains required. Sakiri remains reserve.

## 13. Frozen Contract

```text
Facts:                  source-supported only
Sources:                field-aware provenance
Analysis:               normalized inference
Unknown:                null / [] / unknown
missing evidence !=     low
completeness !=         verification confidence
Native taxonomy !=      normalized analysis
Reference Corpus !=     Canon
PrimaryLoop =           mechanic flow, not optimal rotation
```

`PatternExtractor`, the Design Pattern Corpus, and Reference-to-Agent
integration are **NOT IMPLEMENTED**. Runtime and Canon remain separate from
the Reference Corpus.

## 14. Verification

Wave 1 Completion Gate and freeze verification:

```text
Reference Corpus tests:         81 passed
Production Catalog tests:        6 passed
Full project suite:            551 passed, 1 skipped
python -m compileall src tests:  PASS
git diff --check:                PASS
Clean checkout:                 PASS
8-record corpus:                VALID
Wave 2 production directories:  NONE
```

## 15. Git and Safety Boundary

```text
Branch: codex/character-generation-agent
Pre-freeze HEAD: ef52143
IDEA.md: untouched, untracked, unstaged, uncommitted
Push: NO
Wave 2: NOT STARTED
```

The freeze commit contains this document only. Existing tags
`reference-corpus-pilot-v0.1` and `v0.6.6` remain unchanged.
