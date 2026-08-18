# REFERENCE CORPUS v0.4.1
# GAP-DRIVEN EXPANSION PLAN

Status: planning only. No corpus records were added or changed. The selector,
v0.4 benchmark, generation pipeline, Canon, Repair, and schema are unchanged.

Frozen evidence used:

- benchmark tag: `reference-selection-benchmark-v0.4`;
- corpus manifest: `character-reference-corpus/0.1`;
- current corpus: 10 production records;
- v0.4 classification: `LIMITED_SENSITIVITY`;
- parity: confirmed for the deterministic production reference-selection path.

## Current Corpus

### Record matrix

The matrix below reports repository fields only. An em dash means the field is
absent or empty in the production record; it does not mean the character lacks
that trait in external source material.

| Reference / character | Game/source | Gameplay role | Ability / fantasy categories | Personality | Hook / contrast | Occupation / life identity | Social position | Life-stage / age | Authority | Visual / behavioral motif | Selector-visible metadata | Missing selector-relevant metadata |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `genshin-impact:furina` / Furina | Genshin Impact | — | Ability facts: Normal Attack, Elemental Skill, Elemental Burst, passives; team buffs/healing/off-field effects; no analysis fantasy | — | — | — | Faction/affiliation: Fontaine | — | — | — | game, ability categories, taxonomy: Hydro/Sword/5-star | role, occupation, personality, hooks, life-stage, authority, visual motif |
| `genshin-impact:keqing` / Keqing | Genshin Impact | `on_field_dps`; melee; high field time; high mobility | Analysis fantasy: mobility-driven melee; archetypes include sustained DPS, mobility attacker, infusion attacker; reposition/mark/attack conversion | Personality list empty | Identity/narrative/product hooks include Yuheng, governing official, personal combat presence, teleport/recast | Occupation: Yuheng; public identity: Yuheng of the Liyue Qixing | Faction/affiliation: Liyue Qixing | — | High-ranking/governing terms are present in hooks; no normalized authority field | — | game, role, occupation, ability categories, taxonomy: Electro/Sword/5-star | personality, life-stage, explicit authority field, visual motif |
| `genshin-impact:nahida` / Nahida | Genshin Impact | — | Ability facts: Normal Attack, Elemental Skill, Elemental Burst, passives; targeting, buff, and off-field effects; no analysis fantasy | — | — | Occupation: Dendro Archon of Sumeru; public identity: Lesser Lord Kusanali | Faction/affiliation: Sumeru | — | Authority-bearing title text exists, no normalized authority field | — | game, occupation, ability categories, taxonomy: Dendro/Catalyst/5-star | role, personality, hooks, life-stage, explicit authority field, visual motif |
| `neverness-to-everness:fadia` / Fadia | Neverness to Everness | — | Ability facts and team effects; no analysis fantasy | — | — | — | Faction/affiliation: Bureau of Anomaly Control / ETD | — | — | — | game, ability categories, taxonomy: Psyche/Synthesis/S-Class | role, occupation, personality, hooks, life-stage, authority, visual motif |
| `neverness-to-everness:shinku` / Shinku | Neverness to Everness | `on_field_dps`; melee; high field time; low team dependency | Analysis fantasy: resource/state escalation; archetypes include resource-fueled state attacker and stance striker; resource/state conversion | Personality list empty | Hooks include UAC-2 affiliation, resource-fed empowered mode, patience stance, team energy conduit | — | Faction/affiliation: UAC-2 de la ACA | — | — | — | game, role, ability categories, taxonomy: Cosmos/Synthesis/S-Class | personality, occupation, life-stage, authority, visual motif |
| `wuthering-waves:jinhsi` / Jinhsi | Wuthering Waves | `on_field_dps`; melee; high field time; medium mobility; high team dependency | Analysis fantasy: staged airborne state progression; team-fed resource and empowered skill | Personality list empty | Hooks include Magistrate, governing official, personal combat presence, aerial/state/handoff loop | Occupation/public identity: Magistrate of Jinzhou | Affiliation: Jinzhou | — | Governing title text exists, no normalized authority field | — | game, role, occupation, ability categories, taxonomy: Spectro/Broadblade/5-star | personality, life-stage, explicit authority field, visual motif |
| `wuthering-waves:mortefi` / Mortefi | Wuthering Waves | — | Ability facts, targeting, team buffs, off-field coordinated effects; no analysis fantasy | — | — | Occupation: researcher / expert in Applied Tacetite Study | Faction/affiliations: Huaxu Academy, Department of Safety, Jinzhou | — | Expertise appears in public identity; no authority field | — | game, occupation, ability categories, taxonomy: Fusion/Pistols/4-star | role, personality, hooks, life-stage, authority, visual motif |
| `wuthering-waves:shorekeeper` / Shorekeeper | Wuthering Waves | Native taxonomy includes Support and Healer, Traction, DMG Amplification; normalized analysis role absent | Ability facts, healing, buffs, grouping, off-field effects, mobility/targeting mechanics; no analysis fantasy | — | — | Occupation/public identity: Guardian of the Black Shores | Faction/affiliation: Black Shores | — | Guardian title exists; no authority field | — | game, taxonomy including combat roles, occupation, ability categories | normalized role analysis, personality, hooks, life-stage, authority, visual motif |
| `zenless-zone-zero:jane-doe` / Jane Doe | Zenless Zone Zero | `on_field_dps`; melee; high field time; medium mobility; low team dependency | Analysis fantasy: evasion-fueled resource/state attacker; anomaly/target-condition archetypes | Personality list empty | Hooks include criminal investigation team membership, personal combat presence, evasion/resource/target-state loop | — | Faction: Public Security - Criminal Investigation Special Response Team | — | — | — | game, role, ability categories, taxonomy: Physical/Anomaly/S/faction | occupation, personality, life-stage, authority, visual motif |
| `zenless-zone-zero:nicole` / Nicole Demara | Zenless Zone Zero | Native taxonomy specialty: Support; normalized analysis role absent | Ability facts, debuff, grouping/energy-field effects; no analysis fantasy | — | — | Occupation: Leader of the odd-job agency Cunning Hares | Faction: Cunning Hares | — | Leader term exists; no authority field | — | game, occupation, ability categories, taxonomy: Ether/Support/A/faction | normalized role analysis, personality, hooks, life-stage, authority, visual motif |

### Selector-visible completeness

The current selector summary exposes only `reference_id`, display name,
`game_id`, roles, occupation, ability categories, and native taxonomy.

| Selector-visible field | Populated records |
|---|---:|
| `game_id` | 10/10 |
| Ability categories | 10/10 |
| Native taxonomy | 10/10 |
| Role or role-like taxonomy | 5/10 |
| Occupation | 6/10 |
| Personality | 0/10 exposed to selector |
| Character hook | 0/10 exposed to selector |
| Life-stage / age | 0/10 represented or exposed |

The broader reference schema does contain analysis fields for
`personality_archetypes`, `identity_hooks`, `narrative_hooks`,
`visual_motifs`, and `character_fantasy`, but only four records have analysis
documents and all four have empty personality-archetype lists. Those fields
are not currently included in the selector summary.

## Coverage Matrix

Coverage is based on actual normalized roles, taxonomy labels, occupations,
analysis fields, and mechanics in the repository. It is not based on external
character reputation.

| Benchmark dimension | Status | Current records providing evidence | Boundary |
|---|---|---|---|
| Frontline / aggressive direct combat | COVERED | Keqing, Shinku, Jinhsi, Jane Doe | Four `on_field_dps` analyses; no separate `frontline` vocabulary |
| Defensive / protective | COVERED | Furina, Nahida, Shorekeeper, Nicole Demara, Mortefi | Healing, buffs, support taxonomy, grouping, or off-field effects exist; “protective” is not a normalized role |
| Mobility / repositioning | PARTIAL | Keqing, Jinhsi, Jane Doe, Shorekeeper | Mobility/reposition evidence exists, but occupational/social mobility is absent |
| Investigation / information | COVERED | Jane Doe | Criminal Investigation appears in faction and hooks |
| Performer / expressive identity | NOT REPRESENTED | — | No performer, stage, expressive-identity, or equivalent field value |
| Quiet practical personality | NOT REPRESENTED | — | Personality field is empty across all records |
| High charisma / low authority | NOT REPRESENTED | — | No charisma or normalized authority field |
| Mature active | PARTIAL | Keqing, Shinku, Jinhsi, Jane Doe | Active/high field-time evidence exists for analyzed records; mature/life-stage evidence does not |
| Youthful / age-ambiguous non-student | NOT REPRESENTED | — | No age, school-status, or life-stage field |
| Informal / non-standard life identity | PARTIAL | Nicole Demara | Odd-job agency occupation is present; no general informal-life vocabulary |
| Strong personality contrast / hook | PARTIAL | Keqing, Shinku, Jinhsi, Jane Doe | Hook fields are populated for four records; personality remains empty |
| Ordinary urban profession | NOT REPRESENTED | — | Occupations are titles, leadership, guardianship, research, or archon/magistrate identities; no ordinary urban-worker value |
| High authority | COVERED | Keqing, Nahida, Jinhsi, Nicole Demara | Governing, archon, magistrate, and leader terms are present; no normalized authority scale |
| Low authority but high competence | PARTIAL | Mortefi; combat analyses for Keqing/Shinku/Jinhsi/Jane Doe | Expert/combat evidence exists, but authority level is not represented |
| Socially isolated / low-charisma | NOT REPRESENTED | — | No personality or social-isolation metadata |
| Non-support gameplay identity | COVERED | Keqing, Shinku, Jinhsi, Jane Doe | Four normalized `on_field_dps` records |

## Root Causes

### Missing character coverage

The corpus has direct combat, support/protection, investigation, high-authority,
and non-support role coverage. It lacks explicit precedents for performer
identity, quiet practical personality, charisma/authority contrast, youthful
or age-ambiguous identity, ordinary urban work, and social isolation.

### Missing metadata

This is a `DATA COMPLETENESS GAP` for fields the schema can already represent:

- personality archetypes: 0/10 populated;
- analysis-level character fantasy: 4/10 populated;
- identity/narrative/product hooks: 4/10 populated;
- visual tags, keywords, visual motifs: 0/10 populated;
- normalized gameplay roles: 5/10 populated or role-like through taxonomy.

The ability facts themselves are much stronger: all 10 records contain ability
categories and detailed combat facts, while only four expose analysis-level
fantasy summaries.

### Schema representation gaps

This is a `SCHEMA/METADATA REPRESENTATION GAP` for:

- life-stage / age presentation;
- explicit authority level;
- explicit social position or authority-vs-competence dimensions;
- a selector-visible personality field;
- a selector-visible character-hook field.

The broader analysis schema has personality and hook fields, but the current
selector does not consume them. Adding records alone cannot make v0.4
personality, hook, or life-stage counterfactuals sensitive unless those fields
become selector-visible in a later, separately authorized design change.

### Source imbalance

| Source/game | Records | Selector top-k slots in frozen v0.4 |
|---|---:|---:|
| Genshin Impact | 3 | 14 |
| Wuthering Waves | 3 | 20 |
| Neverness to Everness | 2 | 7 |
| Zenless Zone Zero | 2 | 13 |
| **Total** | **10** | **54** |

Wuthering Waves leads selected-slot frequency, while Genshin Impact has the
most historically discussed repeated references. This is a measurement, not
a quality judgment. The corpus is not severely record-count imbalanced, but
metadata richness is uneven: analysis documents exist for only Keqing, Shinku,
Jinhsi, and Jane Doe.

### Other root cause

The selector remains shallow lexical matching over a compact summary. When
brief tokens do not occur in selector-visible metadata, candidates collapse to
equal scores and deterministic ascending `reference_id` order decides the
ranking. Corpus expansion can reduce this only when new records expose tokens
through fields the selector already reads.

## Expansion Slots

These are target profiles, not character choices. A future candidate must be
selected only after passing the acceptance rules below.

### SLOT-01

- Priority: P0
- Primary gap: mature active playable identity
- Secondary gap: ordinary or mid-level life identity; low formal authority
- Role: direct combat or non-support role distinct from existing `on_field_dps`
- Personality: restrained, practical, self-directed
- Life/social identity: ordinary urban or mid-level occupation
- Life-stage: explicit mature-active presentation, without mentor/retired-master collapse
- Authority: low or bounded authority with demonstrated competence
- Hook: work-practice contrast, not prestige
- Preferred source characteristics: prefer a source underrepresented in analysis metadata, especially NTE or ZZZ, or a new source with reliable primary material
- Reason: fills mature, ordinary, low-authority, personality, and hook gaps together

### SLOT-02

- Priority: P0
- Primary gap: youthful / age-ambiguous non-student identity
- Secondary gap: independent dangerous field work; bounded authority
- Role: non-support mobility, investigation, or direct-combat identity
- Personality: self-reliant but not secret-prodigy coded
- Life/social identity: independent worker without school-status assumptions
- Life-stage: youthful presentation with exact age and school history left appropriately bounded
- Authority: low formal authority, clear operational competence
- Hook: ordinary independence under pressure
- Preferred source characteristics: source with explicit official identity/life-context evidence and not already dominant in selected slots
- Reason: directly targets the absent life-stage and authority dimensions

### SLOT-03

- Priority: P0
- Primary gap: quiet practical personality
- Secondary gap: ordinary urban profession; low spectacle
- Role: non-support practical control, mobility, or information fantasy
- Personality: quiet, patient, pragmatic, low-display
- Life/social identity: repair, logistics, maintenance, or another ordinary urban occupation
- Life-stage: non-school adult/age-ambiguous identity only where source facts support it
- Authority: low formal authority
- Hook: competence expressed through routine practice
- Preferred source characteristics: source with reliable occupation and personality-adjacent official material
- Reason: tests whether practical identity can move selection rather than support labels alone

### SLOT-04

- Priority: P0
- Primary gap: high charisma / low formal authority
- Secondary gap: performer or expressive social identity
- Role: expressive support, control, or non-support role, not another generic healer
- Personality: charismatic, socially effective, improvisational
- Life/social identity: performer, organizer, public-facing informal worker, or equivalent documented identity
- Life-stage: not required unless reliably documented
- Authority: explicitly low formal authority despite social influence
- Hook: social influence without office
- Preferred source characteristics: source with strong official personality/identity material and currently low source share
- Reason: supplies the missing charisma/authority contrast and tests hook sensitivity

### SLOT-05

- Priority: P0
- Primary gap: strong personality and character-hook contrast
- Secondary gap: visual/behavioral motif
- Role: any role not redundant with the four existing `on_field_dps` analyses
- Personality: clearly documented, distinctive, and behaviorally expressed
- Life/social identity: identity that explains the personality without relying on prestige
- Life-stage: optional, only if source-supported
- Authority: preferably bounded or ambiguous
- Hook: one primary identity hook plus one contrasting behavior/motif
- Preferred source characteristics: analysis-rich source record with primary evidence for personality and hook
- Reason: tests fields currently absent from all selector-visible summaries

### SLOT-06

- Priority: P1
- Primary gap: investigation / information outside law-enforcement framing
- Secondary gap: socially isolated or low-charisma identity
- Role: information, investigation, or control
- Personality: quiet, observant, or socially withdrawn only when explicitly supported
- Life/social identity: archivist, fact checker, researcher, or field investigator analogue
- Life-stage: bounded and non-invented
- Authority: low institutional authority but high factual competence
- Hook: information asymmetry or solitary practice
- Preferred source characteristics: source with reliable occupation and public-identity evidence; avoid another public-security duplicate
- Reason: broadens the one-record investigation coverage

### SLOT-07

- Priority: P1
- Primary gap: mobility / repositioning in ordinary life
- Secondary gap: courier, route, field-service, or practical movement identity
- Role: mobility or control; avoid another generic on-field damage record
- Personality: practical, alert, route-oriented, or socially adaptive
- Life/social identity: ordinary field worker or route planner
- Life-stage: optional, source-supported
- Authority: low or distributed authority
- Hook: movement as occupational identity rather than only combat teleportation
- Preferred source characteristics: source with explicit mobility mechanics and occupation metadata
- Reason: separates combat mobility coverage from ordinary-life mobility

### SLOT-08

- Priority: P1
- Primary gap: defensive/protective precedent with a distinct identity
- Secondary gap: non-healer protection or stabilization
- Role: protection, control, shielding, stabilization, or damage mitigation
- Personality: firm, dependable, or quietly responsible
- Life/social identity: practical caretaker, safety worker, or infrastructure role
- Life-stage: mature or age-ambiguous only if documented
- Authority: bounded operational authority
- Hook: protection through procedure or responsibility, not divine/guardian prestige
- Preferred source characteristics: source with explicit defensive mechanics and ordinary identity
- Reason: prevents current protection coverage from collapsing to support/healing examples

### SLOT-09

- Priority: P2
- Primary gap: informal / non-standard life identity
- Secondary gap: family/community responsibility
- Role: support, control, or information with a clear non-professional identity
- Personality: socially grounded, practical, or community-facing
- Life/social identity: odd-job, family business, neighborhood, or informal collective role only when source-supported
- Life-stage: unknown or bounded where appropriate
- Authority: low formal authority
- Hook: responsibility outside an institution
- Preferred source characteristics: source with occupation, affiliation, and public-identity evidence; do not duplicate Nicole solely by “odd-job” wording
- Reason: turns the currently single Nicole-like evidence point into a broader testable dimension

### SLOT-10

- Priority: P2
- Primary gap: source-diverse contrast record
- Secondary gap: non-support gameplay identity plus visual/behavioral motif
- Role: non-support role not already represented by `on_field_dps`
- Personality: deliberately contrasting with Slots 03 and 05, such as expressive or socially isolated
- Life/social identity: documented occupation or social position unlike current title/guardian/researcher set
- Life-stage: preferably a reliably documented stage not present in the corpus
- Authority: explicit level or bounded institutional position if the future representation supports it
- Hook: one strong contrast hook and one visual/behavioral motif
- Preferred source characteristics: new source/game if primary evidence and schema fit are strong
- Reason: tests whether expansion broadens both source usage and semantic coverage without a selector fix

## Candidate Acceptance Rules

A future character may fill a slot only when:

1. Reliable primary/official or strong corroborating reference sources document
   the relevant facts.
2. The character genuinely fills the slot's primary gap.
3. The character is not redundant with the current corpus unless personality,
   life identity, or hook adds a distinct documented dimension.
4. Enough factual material exists for a production-quality reference record,
   including bounded ability facts and provenance.
5. The requested metadata can be expressed using the current reference schema.
6. Inclusion does not require changing the formal schema merely to fit the
   candidate.
7. Source/game balance improves where possible without overriding evidence
   quality.
8. Reference value is bounded authoring precedent, not popularity, sales,
   rarity, or external reputation.
9. No field is filled by inference merely to satisfy a slot; unknown remains
   unknown.
10. A candidate is accepted only after the same corpus validation and
    provenance checks used by the current production records pass.

## Expansion Experiment

### Baseline

- Corpus: 10 records
- Selector: unchanged v0.4 deterministic lexical selector
- Benchmark: same 18 cases, same contrast pairs, same counterfactuals
- Frozen metrics: 8 unique selected, 0.448485 average top-k overlap,
  0.159808 HHI, stable rankings, `ORDER_INDEPENDENT`

### Expansion target

Approximately 20 records, implemented only after candidate selection and
acceptance review. Do not add records in this planning task.

### Controlled variables

- Selector changed: NO
- Selector weights changed: NO
- Benchmark changed: NO
- Schema changed: NO for the corpus-only experiment
- Generation/Canon/Repair changed: NO

### Metrics to compare

1. Unique selected references.
2. Top-k HHI and source/game HHI.
3. Average top-k overlap across materially different briefs.
4. Zero-score tie frequency and score-gap distribution.
5. Top-k source concentration.
6. Role sensitivity and occupation sensitivity.
7. Personality, hook, and life-stage sensitivity, with the pre-declared
   expectation that corpus expansion alone cannot improve dimensions absent
   from selector-visible input.
8. Coverage of the 16 semantic dimensions in the matrix above.
9. Repeat stability and corpus-order independence.

### Directional evidence that expansion helped

Expansion is useful if, under the same selector and benchmark:

- more records receive meaningful non-zero scores for relevant briefs;
- unexplained zero-score ties decrease;
- selected references broaden without artificial diversity constraints;
- counterfactual role/occupation changes remain sensitive and become better
  covered;
- cases previously lacking any relevant metadata gain real candidate coverage;
- source concentration changes as a consequence of better coverage rather than
  forced balancing.

Expansion is not sufficient if new records contain rich facts but do not expose
the dimensions the selector reads, or if personality/hook/life-stage cases
remain invisible because those fields remain outside the selector input.
No arbitrary pass/fail threshold is set in advance.

## Recommendation

`NEEDS_METADATA_DESIGN_FIRST`

The gap-driven expansion plan is ready, but full v0.4.1 success cannot be
attributed to corpus expansion alone: personality, hook, life-stage, and
authority are either underfilled or not represented in selector-visible input.
The next phase remains `GAP-DRIVEN REFERENCE CORPUS EXPANSION`, with candidate
selection gated by a metadata/selector representation decision for those
dimensions.

Do not add characters yet. Do not commit, tag, or push.
