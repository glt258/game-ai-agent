# Reference Corpus Expansion Roster v0.1

## Status

```text
EXPANSION ROSTER READY
CONTROLLED INGESTION PLAN FROZEN
```

This document records the Human Review-approved 16-Record Expansion Roster,
its wave order, selection principles, conditional and reserve policy, coverage
intent, watch-item pressure, and expansion gates.

The 16 records are planned slots. They are not completed CharacterReferences,
and no Wave 1 ingestion has started.

The source of truth for the Expansion Roster is this document. The Golden Pilot
freeze remains recorded in `pilot_freeze_v0.1.md` and is not modified by this
checkpoint.

## Frozen Baseline

The Expansion baseline is the frozen tag `reference-corpus-pilot-v0.1` at
commit `562e47d`. The frozen versions are:

```text
CharacterFacts:    character-facts/0.3
CharacterSources:  character-sources/0.2
CharacterAnalysis: character-analysis/0.1
GameCatalog:       game-catalog/0.1
Golden Pilot:      FROZEN
```

The current Expansion target is:

```text
4 games × 5 characters = 20 CharacterReferences
4 Golden Records + 16 Expansion Records = 20 total planned records
```

The four Golden Records are already accepted and catalog-backed:

```text
genshin-impact:keqing
wuthering-waves:jinhsi
zenless-zone-zero:jane-doe
neverness-to-everness:shinku
```

The frozen schema is the Expansion baseline. Expansion work must first classify
friction as `DATA ISSUE`, `SOURCE ISSUE`, `ANALYSIS ISSUE`, `SCHEMA CANDIDATE`,
or `BLOCKING SCHEMA DEFECT`. A schema change is permitted only when a confirmed
commercial fact cannot be represented honestly without distortion or invention.
Theoretical elegance alone is not a reason to modify the frozen Schema.

## Selection Principles

This is not a popularity roster, tier-list roster, favorite-character list,
sales ranking, or meta ranking.

It is a:

> Design-space coverage + Schema stress + Provenance stress + Source feasibility driven sampling plan.

The core objective is:

> Use 16 Expansion records to widen the design space of the 20-record Reference Corpus as much as possible, while avoiding unreviewed bulk ingestion into the frozen schema.

Selection balances mechanic novelty, team architecture, state and resource
pressure, provenance complexity, source feasibility, and the ability to learn
from each stopped Wave review. Roster planning does not pre-decide the final
Facts, Sources, or Analysis representation.

## Existing Golden Records

| Game | Golden Record | Existing coverage role |
| --- | --- | --- |
| Genshin Impact | Keqing | Baseline / on-field damage |
| Wuthering Waves | Jinhsi | Complex state-heavy carry and team-fed resource graph |
| Zenless Zone Zero | Jane Doe | Evasion-driven resource, self/target state, temporal provenance |
| Neverness to Everness | Shinku / 真红 | Sparse multi-source evidence, secondary-heavy combat evidence, honest unknowns |

These records define the current pilot baseline and are not replaced by the
Expansion slots.

## Final 16-Record Roster

### Genshin Impact

Golden: Keqing

Expansion:

1. Furina
2. Nahida
3. Zhongli
4. Childe

Keqing covers baseline/on-field damage. The Expansion adds party/team hybrid,
off-field, healing/buffs, summon or mode behavior, linked targets, shielding,
constructs, stance/form switching, target-state propagation, handoff and
time-cost candidates, plus historical naming/provenance pressure.

### Wuthering Waves

Golden: Jinhsi

Expansion:

1. Shorekeeper
2. Mortefi
3. Carlotta
4. Brant

Jinhsi covers a complex state-heavy carry and team-fed resource graph. The
Expansion adds sustain/support, healing, buffs, summon/auto-track behavior,
coordinated off-field attacks, meter/resource pressure, burst-oriented damage,
multi-resource and mode replacement, target conditions/debuffs, shielding,
mobility, and hybrid defensive/offensive behavior.

### Zenless Zone Zero

Golden: Jane Doe

Expansion:

1. Nicole
2. Caesar King
3. Astra Yao
4. Trigger

Jane covers evasion-driven resource, self-state, target-state, on-field anomaly
payoff, and temporal provenance. The Expansion adds grouping, debuff, low-field
support, shielding, defensive sustain, counter/parry, control/stun utility,
healing, buffs, off-field support, stance, targeting, and ally-action-triggered
follow-up candidates.

### Neverness to Everness

Golden: Shinku / 真红

Expansion:

1. Fadia
2. Iroi
3. Lacrimosa
4. Hotori — CONDITIONAL

Hotori is not an unconditional locked slot. Sakiri is the reserve for this
game's fourth Expansion slot.

## Character Selection Rationale

### Genshin Impact

- **Furina** — party/team hybrid, off-field behavior, healing and buffs, summon/mode behavior, and expected party-state stress.
- **Nahida** — linked-target conditions, off-field follow-up, buffs, and multi-target targeting.
- **Zhongli** — sustain/control, shielding, debuff, construct behavior, and historical provenance stress.
- **Childe** — stance/form switch, target-state propagation, handoff and time-cost behavior, and naming/history provenance.

### Wuthering Waves

- **Shorekeeper** — sustain/support, healing, buffs, summon/auto-track behavior, and expected field-state stress.
- **Mortefi** — off-field coordinated attacks, meter/resource, low-field-time architecture, and buffs.
- **Carlotta** — burst-oriented damage, multi-resource, mode replacement, target condition/debuff, and complex resource-loop pressure.
- **Brant** — hybrid defensive/offensive behavior, shielding, buffs, and mobility/hook behavior.

### Zenless Zone Zero

- **Nicole** — grouping, debuff, low-field support, and off-field utility.
- **Caesar King** — shielding, defensive sustain, counter/parry, and control/stun utility.
- **Astra Yao** — healing, buffs, off-field support, and self-state pressure.
- **Trigger** — off-field control, stance, targeting, ally-action-triggered follow-up, and high team-dependency pressure.

### Neverness to Everness

- **Fadia** — defensive/tank orientation, damage redirection, party defensive utility, and sustain stress.
- **Iroi** — summon-heavy behavior, healing, and independent/companion entity stress.
- **Lacrimosa** — mode switch, learn/copy mechanic candidate, targeting, and transformation/mode stress.
- **Hotori** — conditional meter, time-manipulation candidate, counter, and possible field-level mechanic stress.
- **Sakiri** — reserve grouping/control, mount/companion behavior, and stronger official-source feasibility fallback.

## Conditional Slot Policy

### Hotori — CONDITIONAL

Hotori has high design-space value: meter, time manipulation, and counter
behavior could add unique coverage. However, official-source feasibility is
currently weaker and the core kit may be secondary-heavy.

Before Wave 4 starts, perform a `SOURCE FEASIBILITY GATE`. Hotori may enter
ingestion only if at least one condition is satisfied:

- **A:** A clear first-party character or mechanics source supports the core meter/time mechanic Facts; or
- **B:** Sufficient first-party material exists so that the core Facts do not depend entirely on secondary-only data.

If neither condition is satisfied, Hotori is dropped and Sakiri is promoted
from reserve. High design novelty must not bypass the source standard.

### Sakiri — RESERVE

Sakiri is not part of the four active NTE slots unless the Hotori gate fails.
Sakiri becomes the fourth NTE Expansion record only through the documented
Hotori fallback decision.

## Ingestion Waves

Each Wave is a four-record controlled batch, one record per game. The order is
frozen for Expansion validation.

### Wave 1 — High Feasibility / High Novelty

| Game | Record |
| --- | --- |
| Genshin Impact | Furina |
| Wuthering Waves | Shorekeeper |
| Zenless Zone Zero | Nicole |
| Neverness to Everness | Fadia |

Purpose: first-round frozen-schema validation with expected party/field
semantic stress, grouping, sustain/tank coverage, and TeamMechanics coverage.

### Wave 2 — Team Architecture and Support

| Game | Record |
| --- | --- |
| Genshin Impact | Nahida |
| Wuthering Waves | Mortefi |
| Zenless Zone Zero | Caesar King |
| Neverness to Everness | Iroi |

Purpose: expand team architecture and support/off-field/sustain coverage,
including target linking, coordinated off-field behavior, shielding, summons,
and healing.

### Wave 3 — Mechanic and Provenance Complexity

| Game | Record |
| --- | --- |
| Genshin Impact | Zhongli |
| Wuthering Waves | Carlotta |
| Zenless Zone Zero | Astra Yao |
| Neverness to Everness | Lacrimosa |

Purpose: validate higher mechanic and provenance complexity, including
historical source changes, multi-resource behavior, healing/buff support, and
precise learn/copy wording.

### Wave 4 — Unusual / High-Risk Mechanics

| Game | Record |
| --- | --- |
| Genshin Impact | Childe |
| Wuthering Waves | Brant |
| Zenless Zone Zero | Trigger |
| Neverness to Everness | Hotori — CONDITIONAL, or Sakiri — RESERVE |

Purpose: ingest unusual or higher-risk mechanics only after three Waves have
validated the frozen baseline. The Hotori source-feasibility review is
mandatory before Wave 4 begins.

## Wave Review Gate

Every completed Wave must STOP for Human Review. Continuous automatic
ingestion from Wave 1 through Wave 4 is prohibited. Each Wave requires a
separate approval before the next Wave can begin.

Review at each gate:

- Facts representability
- Provenance quality
- New Watch Items
- Schema friction
- Analysis consistency
- Completeness behavior
- Source reliability

Wave review may classify a finding, request correction, or block progression;
it does not automatically authorize a schema change.

## Expected Schema Stress

The following planning terms are hypotheses about likely stress, not frozen
interpretations of `StateFact.subject_scope` or any other Schema field:

```text
party-wide state  → EXPECTED SCHEMA STRESS / PLANNING HYPOTHESIS
field-state       → EXPECTED SCHEMA STRESS / PLANNING HYPOTHESIS
field-level state → EXPECTED SCHEMA STRESS / PLANNING HYPOTHESIS
ally-state        → EXPECTED SCHEMA STRESS / PLANNING HYPOTHESIS
summon-state      → EXPECTED SCHEMA STRESS / PLANNING HYPOTHESIS
```

Actual ingestion must determine whether a commercial fact belongs in
`StateFact`, `TeamMechanics.buff`, `ResourceFact`, `MechanicRelation`, or
another existing structure. Only a confirmed commercial fact that cannot be
represented honestly may become a `SCHEMA CANDIDATE`; only an unrepresentable
fact that blocks honest ingestion may become a `BLOCKING SCHEMA DEFECT`.

## Watch-Item Mapping

The following mappings are expected pressure points only:

| Watch Item | Expansion pressure candidates |
| --- | --- |
| KL-RC-001 Statement Authority | Zhongli; Childe; Lacrimosa |
| KL-RC-002 ResourceLoop | Furina; Carlotta; Trigger; Hotori if admitted |
| KL-RC-003 TeamDependency | Furina; Shorekeeper; Trigger |
| KL-RC-004 Evasion-Centric | Caesar King; Trigger |
| KL-RC-005 Relation-Level Provenance | Zhongli; Childe |
| KL-RC-006 State Subject Scope | Furina; Shorekeeper; Fadia; Hotori or Sakiri according to actual Facts |
| KL-RC-007 Completeness vs Evidence Strength | Neverness to Everness records |
| KL-RC-008 Secondary-Heavy Analysis | Neverness to Everness records; Hotori strongest candidate if admitted |

Every mapping in this section is `PLANNING HYPOTHESIS ONLY`. It must not be
converted into Facts, Sources, or Analysis before actual source-backed
ingestion.

## Source-Risk Classification

These are planning classifications only. Actual
`CharacterSources.reliability` and `verification_status` must be determined
from real sources during ingestion and must not be copied from this roster
into Facts or Sources.

### LOW RISK / HIGH FEASIBILITY

```text
Furina, Nahida, Zhongli, Childe
Shorekeeper, Mortefi, Carlotta, Brant
Nicole, Caesar King, Astra Yao, Trigger
```

### MEDIUM

```text
Fadia, Iroi, Lacrimosa
```

### CONDITIONAL HIGHER RISK

```text
Hotori
```

### RESERVE

```text
Sakiri
```

## Global Coverage Intent

The 20-record combination is intended to sample the following axes. These are
coverage intents, not final CharacterAnalysis conclusions:

- **Role:** damage, off-field damage, burst, support, sustain, control, hybrid.
- **Field time:** high, medium, low, and variable field-time candidates.
- **Resources:** none, gauge, meter, multi-resource, team-fed, party-fed, and conditional.
- **State:** self, target, and possible party/field candidates.
- **Team direction:** self-contained, character-to-team, team-to-character, bidirectional, handoff, and ally-action-triggered.
- **Mechanics:** summons, stance, mode replacement, transformation, grouping, healing, shielding, debuff, counter, targeting, mobility, and off-field effects.

The terms `party-wide`, `field`, `ally`, and `summon` in this planning section
remain hypotheses until Facts ingestion establishes what the source actually
supports and what the frozen Schema can represent honestly.

## Known Coverage Holes

The current plan may still under-sample:

1. True ally-specific state
2. True summon-management gameplay
3. Pure healer
4. Enemy-fed resource
5. Broader hard-CC variety
6. High-complexity/high-execution quadrant
7. Classic DoT
8. Grouping, which remains lightly sampled
9. Resource retention across swap
10. Field-state sample count, which remains low

These are `KNOWN COVERAGE HOLES`. They are not reasons to modify the current
16-slot roster immediately, and they are not Schema blockers.

## Expansion Contract

All future Expansion ingestion is governed by the frozen Pilot contract:

```text
Facts     = source-supported only
Sources   = field-aware provenance
Analysis  = derived from Facts + Sources
Unknown   = null / [] / unknown
```

Additional boundaries:

- Missing evidence is not low evidence: `missing evidence != low`.
- Native taxonomy is not normalized taxonomy: native taxonomy belongs in Facts; normalized taxonomy belongs in Analysis.
- Analysis inference must never be backfilled into Facts.
- Model memory must never enter Facts.
- Actual source reliability and verification status are established during ingestion, not by roster risk labels.
- Reference Corpus is not Canon: `Reference Corpus != Canon`.
- Every Wave is independently reviewed and approved before the next Wave.
- The frozen Schema remains unchanged unless a confirmed commercial fact cannot be represented honestly without distortion or invention.

## Non-Goals

This checkpoint does not:

- create any new `CharacterReference`, `facts.yaml`, `sources.yaml`, or `analysis.yaml`;
- start Wave 1 or ingest Furina, Shorekeeper, Nicole, or Fadia;
- modify `CharacterFacts`, `CharacterSources`, `CharacterAnalysis`, or `GameCatalog` Schema versions;
- modify `games.yaml`;
- modify `README.md`;
- implement `PatternExtractor`;
- create a Design Pattern Corpus;
- add Embedding/RAG;
- modify CharacterGenerationAgent, NPC Agent, Canon Checker, Story runtime, or Knowledge tooling;
- create a tag or push to a remote.

The following remain explicitly not implemented:

```text
PatternExtractor:     NOT IMPLEMENTED
Design Pattern Corpus: NOT IMPLEMENTED
Embedding/RAG:         NOT IMPLEMENTED
```

## Git Baseline

The document was prepared from:

```text
Branch: codex/character-generation-agent
HEAD before roster commit: 562e47d
Tag: reference-corpus-pilot-v0.1 → 562e47d
Expected pre-change user file: IDEA.md (untracked, untouched)
```

Only this document is intended for the roster commit. `IDEA.md` must remain
untracked, unstaged, uncommitted, and untouched. No tag is created for this
roster in this checkpoint, and no push is performed.
