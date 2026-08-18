# REFERENCE CORPUS v0.4.1a
# METADATA REPRESENTATION REPORT

Status: `MIXED`

This is a design and backfill-planning report only. No reference character,
corpus record, selector, benchmark case, production schema, generation path,
Canon, Repair, or tag was changed.

The frozen evidence is:

- corpus version: `character-reference-corpus/0.1`;
- facts schema: `character-facts/0.3`;
- sources schema: `character-sources/0.2`;
- analysis schema: `character-analysis/0.1`;
- v0.4 selector classification: `LIMITED_SENSITIVITY`;
- v0.4 parity: confirmed for the deterministic pre-generation selector.

## Current Architecture

### Reference metadata architecture

| Layer | Current implementation |
|---|---|
| Production record format | One directory per character with required `facts.yaml` and `sources.yaml`; optional `analysis.yaml` |
| Facts representation | `CharacterFacts`: identity, combat facts/mechanics, narrative facts, presentation facts |
| Analysis representation | Optional `CharacterAnalysis`: combat design, character design, product design, differentiation, design patterns, similarity features, confidence, and analysis metadata |
| Selector input representation | Compact Python mapping built by `_reference_summary()` |
| Selector-visible fields | `reference_id`, canonical display name, `game_id`, roles/role-like taxonomy, occupation, first six ability categories, native taxonomy |
| Selector-invisible fields | Faction, affiliations, public identity, detailed ability descriptions, mechanics, team effects, analysis fantasy, personality, hooks, motifs, confidence, provenance, quality scores |
| Validation layer | Pydantic model validation, exact schema-version checks, repository duplicate checks, fact/provenance validation, deterministic corpus validation |
| Serialization | YAML is loaded into strict Pydantic models; benchmark and authoring audits serialize bounded Python mappings/JSON. `ReferenceModel` forbids unknown fields. |
| Backward compatibility | `analysis.yaml` is optional; absent analysis remains valid with `AnalysisStatus.MISSING`. Versioned loaders require exact supported schema versions and do not silently retain unknown fields. |

The production loader constructs `CharacterReference` from facts, optional
analysis, provenance, and computed quality. `analysis.yaml` is not Canon: it is
derived design analysis with `analysis_metadata` containing analyzer, model,
prompt version, and timestamp.

### Dimension matrix

| Dimension | Current representation | Selector visible today? | Backfillable without a new facts schema? | Gap type |
|---|---|---:|---:|---|
| Personality | `analysis.character_design.personality_archetypes`; currently empty in all 10 records | NO | YES, as analysis data | `EXISTING_NOT_VISIBLE` + `DATA COMPLETENESS GAP` |
| Hook / contrast | Existing `identity_hooks`, `narrative_hooks`, product gameplay/narrative hooks; structured surface-vs-contrast pair does not exist | NO | PARTIAL; existing lists can be populated, but contrast semantics need a bounded convention or small analysis extension | `EXISTING_NOT_VISIBLE` |
| Gameplay fantasy | `analysis.character_design.character_fantasy`; combat facts and mechanics are separate factual inputs | NO | YES for the four analysis-rich records; partial from facts for the remaining six | `EXISTING_NOT_VISIBLE` + `DATA COMPLETENESS GAP` |
| Life/social identity | Facts have faction, occupation, affiliations, public identity; analysis identity hooks also exist. Only occupation reaches selector | PARTIAL | YES for factual identity context; analytic categories need a bounded analysis convention | `EXISTING_PARTIALLY_VISIBLE` |
| Life-stage | No field in `CharacterFacts` or `CharacterAnalysis`; CharacterDraft age semantics are a separate system and must not be reused implicitly | NO | NO as a typed corpus dimension without an analysis-schema extension | `NOT_REPRESENTED` / `SCHEMA REPRESENTATION GAP` |
| Authority | No explicit authority field. Titles, faction membership, occupation, and hooks provide clues but do not encode authority | NO | PARTIAL only for evidence-bearing analysis; a bounded authority profile needs an analysis extension | `NOT_REPRESENTED` / `SCHEMA REPRESENTATION GAP` |
| Visual / behavioral motif | Facts have official visual tags/keywords; analysis has `visual_motifs` and presentation signatures; all are empty in current production records | NO | YES where sources support it; existing analysis home is adequate | `EXISTING_NOT_VISIBLE` + `DATA COMPLETENESS GAP` |

### Existing analysis mechanism

There is already one optional, formally validated analysis block. It is not a
parallel `reference_metadata_v2` or `selector_tags_v2` system.

`CharacterDesignAnalysis` already contains:

- `character_fantasy`;
- `personality_archetypes`;
- `identity_hooks`;
- `narrative_hooks`;
- `visual_motifs`;
- gameplay-identity alignment.

`CombatDesignAnalysis` already contains normalized roles, primary loop,
archetypes, core mechanics, mobility, field time, survivability, and team
dependency. `NarrativeFacts` already contains factual occupation, faction,
affiliations, and public identity.

The smallest architecture-correct direction is therefore to extend the
existing analysis architecture only where it cannot express the requested
dimensions. Do not create a parallel metadata document or duplicate facts into
selector-specific YAML.

## Fact vs Analysis Boundary

`facts.yaml` contains externally supported observations: ability facts,
mechanics, identity, occupation, faction, affiliation, public identity, and
official presentation fields. These remain source-grounded and are validated
against `sources.yaml` field evidence.

`analysis.yaml` contains analyst derivations: normalized role, combat loop,
character fantasy, personality archetypes, hooks, motifs, differentiators, and
similarity signatures. These must not be copied into facts or presented as
source Canon.

The current provenance boundary is asymmetric:

- `CharacterProvenance.field_evidence` resolves paths against `CharacterFacts`;
- source relations also validate fact field paths;
- `analysis_metadata` records analyzer/model/prompt/timestamp;
- there is no field-level evidence map from an analysis conclusion back to
  fact paths and their source IDs.

Therefore a later backfill must retain two layers: source facts remain in
`facts.yaml`, while derived authoring descriptors remain in `analysis.yaml`.
If analysis provenance needs to be made auditable, the smallest future change
is an optional derivation-evidence structure inside the existing analysis
schema, for example an analysis path mapped to the fact paths used and a short
derivation note. It must not turn derived analysis into Canon or pretend that
an analysis tag is a direct quote.

## Proposed Metadata Contract

This is a design proposal, not an implementation. It reuses existing fields
where possible and adds only the smallest missing concepts.

### Existing fields to reuse

| Authoring dimension | Existing home | Contract guidance |
|---|---|---|
| Personality | `character_design.personality_archetypes` | Zero to three bounded authoring descriptors; no MBTI, diagnosis, or long prose |
| Hook | `identity_hooks`, `narrative_hooks`, product hooks | Keep identity, narrative, and gameplay hooks distinct; do not use “cool”, “cute”, or “interesting” as tags |
| Gameplay fantasy | `character_design.character_fantasy` plus `combat_design` | One bounded play-experience summary tied to factual mechanics; no invented damage, cooldown, weapon, or combat system |
| Visual motif | `character_design.visual_motifs` and existing presentation fields | Short observable visual/behavioral motifs only; optional and lower priority |
| Life/social facts | `facts.narrative` | Keep occupation, faction, affiliations, and public identity factual; do not collapse social identity into occupation |

### Small future analysis extension

If approval confirms these dimensions are required, extend
`CharacterDesignAnalysis` in a future version rather than creating a parallel
schema:

```text
life_identity_patterns: list[str]       # bounded analysis descriptors
life_stage_presentation: enum            # youthful | mature | older | age_ambiguous | unspecified
authority_profile: enum/list             # formal_leader | ordinary_member |
                                         # independent_operator |
                                         # low_formal_authority |
                                         # public_influence_without_office |
                                         # unspecified
hook_contrast: optional structured value  # surface_impression + revealed_contrast
```

The exact field names and enum names require schema review before
implementation. The important constraints are:

- life-stage describes presented or source-supported stage, not inferred exact
  age or legal status;
- `unspecified` and `age_ambiguous` remain valid values;
- authority is not a numeric power score;
- competence, formal authority, and knowledge access remain separate;
- `hook_contrast` describes precedent structure, not a causal claim about a
  generated character;
- `life_identity_patterns` describes analysis-level patterns while factual
  occupation/faction/affiliation remain in `facts.yaml`.

### Bounded descriptor guidance

Personality descriptors should be a small controlled vocabulary with room for
multiple descriptors, such as `quiet_practical`, `flamboyant_expressive`,
`warm_guarded`, `highly_social`, `socially_isolated`, `disciplined`,
`impulsive`, `confrontational`, and `conciliatory`. A descriptor must be
supported by the analyzed record and should not reduce a character to one
generic archetype.

Gameplay fantasy should use bounded taxonomy terms such as frontline pressure,
protective stabilization, mobility/repositioning, information control, team
support, and battlefield routing. These are authoring precedents, not new game
mechanics.

## Current 10 Backfill Feasibility

Statuses mean:

- `SUPPORTED_FROM_EXISTING_CORPUS`: current facts/analysis already contain
  enough material for a bounded backfill;
- `PARTIALLY_SUPPORTED`: useful evidence exists, but a careful derivation or
  additional source support is needed;
- `REQUIRES_SOURCE_RESEARCH`: the current repository does not contain enough
  evidence for a responsible value;
- `NOT_APPROPRIATE`: assigning the value would require inference that the
  corpus contract forbids.

No external character knowledge was used.

| Character | Personality | Hook | Fantasy | Life identity | Life-stage | Authority | Motif | Research needed |
|---|---|---|---|---|---|---|---|---|
| Furina | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | Personality, hook, analysis fantasy, stage, authority, motif |
| Keqing | REQUIRES_SOURCE_RESEARCH | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, stage, motif; authority derivation review |
| Nahida | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, hook, stage, motif; authority derivation review |
| Fadia | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | Personality, hook, stage, authority, motif |
| Shinku | REQUIRES_SOURCE_RESEARCH | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | Personality, stage, authority, motif |
| Jinhsi | REQUIRES_SOURCE_RESEARCH | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, stage, motif; authority derivation review |
| Mortefi | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, hook, stage, motif; authority/competence separation |
| Shorekeeper | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, hook, stage, motif; authority derivation review |
| Jane Doe | REQUIRES_SOURCE_RESEARCH | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, stage, motif; authority derivation review |
| Nicole Demara | REQUIRES_SOURCE_RESEARCH | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | SUPPORTED_FROM_EXISTING_CORPUS | REQUIRES_SOURCE_RESEARCH | PARTIALLY_SUPPORTED | REQUIRES_SOURCE_RESEARCH | Personality, hook, stage, motif; authority derivation review |

Interpretation: life/social factual context is available for all records via
faction, affiliation, occupation, or public identity, but a richer analysis
category still needs bounded conventions. Ability facts are present for all
10; analysis-level fantasy is directly supported for only four. Personality,
life-stage, and motif cannot be safely backfilled from the current repository
alone. Unknown remains preferable to invention.

## Selector Visibility Check

| Proposed/current metadata | If populated today, current selector sees it? | Consequence |
|---|---:|---|
| Existing normalized roles | YES | Same-10 backfill can test role sensitivity now |
| Occupation | YES | Same-10 backfill can test exact occupation-token effects now |
| Ability categories / taxonomy | YES | Existing ability/category coverage can be measured now |
| Personality archetypes | NO | `SELECTOR REPRESENTATION GAP`; Stage 1 cannot test personality sensitivity |
| Identity/narrative/gameplay hooks | NO | `SELECTOR REPRESENTATION GAP`; Stage 1 cannot test hook sensitivity |
| Character fantasy | NO | `SELECTOR REPRESENTATION GAP`; Stage 1 cannot test fantasy-language sensitivity |
| Faction / affiliations / public identity | NO | Life/social facts remain invisible except occupation |
| Life-stage presentation | NO and not currently represented | `FEATURE_REDESIGN_REQUIRED_FOR_DIMENSION` |
| Authority profile | NO and not currently represented | `FEATURE_REDESIGN_REQUIRED_FOR_DIMENSION` |
| Visual/behavioral motif | NO | `SELECTOR REPRESENTATION GAP` |

Do not wire any of these fields into the selector in v0.4.1a. Visibility must
become a separately controlled variable in a future selector-feature design.

## Controlled Experiment

### Stage 0 — Frozen baseline

- 10 production characters;
- current facts and optional analysis;
- unchanged v0.4 selector and 18-case benchmark;
- frozen results: 8 unique selected, 0.448485 average top-k overlap,
  0.159808 HHI, stable rankings, corpus-order independent.

### Stage 1 — Same-10 metadata backfill

Use the same 10 characters, same selector algorithm, and same benchmark. Change
only the completeness of approved metadata in the existing analysis
architecture. Keep facts, source records, selector code, and benchmark cases
fixed.

Measure:

- unique selected references;
- reference and source HHI;
- average top-k overlap;
- zero-score tie frequency and score gaps;
- role and occupation sensitivity;
- personality, hook, and life-stage sensitivity only if a later selector
  feature design explicitly exposes those fields.

Stage 1 can test role, occupation, ability-category, and taxonomy backfill
immediately. It cannot test personality, hook, fantasy, life-stage, authority,
or motif sensitivity under the current selector because those values are not
in selector input.

### Stage 2 — Gap-driven expansion

Expand to approximately 20 characters using the same approved metadata
contract, same selector, and same 18 benchmark cases. This separates metadata
quality effects from corpus-size and coverage effects.

Evidence that Stage 1 or Stage 2 helped should be directional rather than an
arbitrary pass threshold:

- more relevant records receive non-zero scores;
- unexplained zero-score ties decrease;
- meaningful reference usage broadens without diversity constraints;
- role/occupation counterfactuals remain sensitive;
- newly represented dimensions gain candidates when the selector can see them;
- source concentration changes because of coverage, not forced balancing.

If a field is backfilled but invisible to the selector, report
`FEATURE_REDESIGN_REQUIRED_FOR_DIMENSION` rather than attributing a result to
the backfill.

## Metadata Completeness Target

This is a target for a production-quality reference, not a requirement that
every record have every value.

### Required when applicable

- source-grounded identity and ability facts;
- bounded gameplay-role/fantasy analysis where the record supports it;
- factual life/social context when documented;
- provenance and analysis metadata.

### Recommended

- bounded personality descriptors;
- at least one useful hook or contrast when source material supports it;
- clear separation between occupation and broader social identity;
- analysis derivation notes linking descriptors to fact fields.

### Optional

- life-stage presentation, including `unspecified`/`age_ambiguous`;
- bounded authority profile;
- visual/behavioral motif.

Optional or unknown values must remain valid. No exact age, legal status,
authority, personality, or motif may be inferred from appearance, occupation,
body, rarity, or external reputation.

## Schema Changes

### Required now

None. This task remains design-only.

### Future, if approved

- versioned extension of the existing `character-analysis/0.1` model for
  life-stage, authority, life-identity patterns, and a structured hook
  contrast;
- optional analysis derivation evidence so analysis paths can point to fact
  paths and source-backed inputs;
- explicit loader support and migration rules because `ReferenceModel` uses
  `extra="forbid"` and the loader requires exact schema versions.

### Avoided

- a parallel reference metadata schema;
- selector-specific duplicated YAML;
- numeric authority or power scores;
- exact-age requirements;
- personality diagnosis or MBTI;
- treating analysis as Canon facts;
- selector wiring before a separately controlled feature experiment.

## Selector Changes

Required now: **NO**.

Future dimensions requiring selector-feature redesign:

- personality;
- hook/contrast;
- gameplay fantasy language;
- life/social identity beyond occupation;
- life-stage presentation;
- authority profile;
- visual/behavioral motif.

The current selector can only test fields it already reads. Expanding the
corpus without exposing these fields would improve the stored corpus but not
their selection sensitivity.

## Research Work Needed

### Existing corpus backfill

- research personality only from reliable source material or leave unknown;
- backfill hooks/fantasy for records where current facts support a bounded
  derivation;
- preserve existing factual identity fields and do not rewrite them as
  analysis;
- decide whether the four analysis-rich records are sufficient pilots for the
  proposed contract;
- define field-level derivation evidence before large-scale backfill.

### Future candidate research

After this design is approved, research candidates against the 10 frozen slots
from `docs/reference_corpus_v0.4.1_gap_driven_expansion_plan.md`. Candidate
selection must remain separate from this metadata-contract task and must use
the acceptance rules already documented there.

## Recommendation

`DESIGN_SELECTOR_FEATURES_BEFORE_BACKFILL`

The existing analysis architecture is sufficient for a careful design of
personality, hooks, gameplay fantasy, and motifs, but those fields are not
selector-visible. Life-stage and authority also need a small, versioned
analysis representation. Approve the metadata/provenance contract first;
then run a controlled same-10 backfill for fields the selector can actually
measure, followed by the gap-driven 10-to-approximately-20 expansion.

Do not add characters. Do not modify records. Do not commit, tag, or push.
