# Reference Selection Quality Benchmark v0.4

Status: `READY_FOR_REVIEW`

This benchmark is diagnostic. It measures the frozen reference selector and
does not change selector weights, ranking behavior, the reference corpus,
`CharacterDraft`, Canon Checker, Character Repair, or v0.3 diversity behavior.

## Problem statement

Repeated live authoring runs selected Furina, Keqing, and Nahida across briefs
that differed in occupation, life stage, personality, and authoring hook.
Repetition is not treated as a failure by itself. v0.4 separates sensitivity,
relevance-review preparation, diversity/concentration, and deterministic
stability so selector bias, feature collapse, corpus coverage, and tie behavior
are not conflated.

The benchmark is offline and requires no `NPC_LLM_API_KEY`, provider, or model.

## Current selector architecture

Selector entry point:
`agents.official_character_authoring.load_reference_grounding`.

The path is:

1. Load the corpus manifest, game catalog, and `CharacterReferenceRepository`.
2. Load all corpus records. The repository returns them sorted by
   `reference_id`.
3. Build a compact summary containing `reference_id`, canonical display name,
   `game_id`, analysis/taxonomy role labels, occupation, ability categories,
   and native taxonomy.
4. Tokenize the brief and JSON summary using the existing `_tokens` helper.
5. Score each candidate as the count of distinct brief tokens present in its
   summary token set.
6. Sort by descending total score, then ascending `reference_id`.
7. Return the first three candidates.

There is no candidate filtering, score normalization, embedding, vector
database, RAG, provider/model selection, randomization, or component scoring.
The current implementation has one real total score; this benchmark reports
no invented role, ability, personality, or detail sub-scores.

Selected summaries are passed into generation as `reference_context`, and the
generation audit records selected `reference_ids`. Current audit output does
not expose full ranking, scores, gaps, or ties; this benchmark adds those
diagnostics without changing the production selection result.

### Selector investigation

| Field | Evidence-backed result |
|---|---|
| Selector entry | `agents.official_character_authoring.load_reference_grounding` |
| Candidate count | 10 |
| Top-k | 3 by default |
| Scoring inputs | Tokenized brief and tokenized JSON summary |
| Scoring formula | `sum(1 for token in query if token in haystack)` |
| Score normalization | None |
| Candidate filtering | None |
| Tie-breaking | Descending score, then ascending `reference_id` |
| Corpus-order dependence | None in explicit reverse-order test |
| Deterministic | Yes under fixed corpus and code |
| Role sensitivity | Present for exact role/taxonomy tokens such as `on_field_dps`, `support` |
| Occupation sensitivity | Present for exact tokens such as `researcher`, `magistrate` |
| Ability sensitivity | Present for exact ability-category tokens; no normalized fantasy model |
| Personality sensitivity | No selector-visible personality field |
| Life-stage sensitivity | No selector-visible age/life-stage field |
| Hook sensitivity | No selector-visible character-hook field |
| Game/source sensitivity | `game_id` is in the summary and can match exact tokens |
| Current audit visibility | Selected IDs and passed summaries; no full score/rank audit |

### Evidence-supported reasons the repeated trio can occur

1. The selector uses a shallow summary and treats every matching token as one
   equal unit; it has no semantic relation between “repair worker” and an
   occupation or between “quiet” and a personality field.
2. Personality, life stage/age, character hook, and detail granularity are not
   exposed by the selector summary.
3. Equal totals are deterministically ordered by ascending `reference_id`.
   The reverse-order test shows current ordering is ID-dominated for ties, not
   dependent on file/list iteration order.
4. There is no score normalization or component attribution. A token match in
   an occupation, taxonomy value, or ability category is indistinguishable in
   the total from any other token match.

These are selector/corpus observations, not claims that any selected
reference caused a generated character feature.

## Corpus audit

The frozen manifest reports `character-reference-corpus/0.1` and the
repository loads 10 records. The table uses only fields visible to the current
selector. `Personality tags` and `detail granularity` are unavailable because
they are not exposed by the selector summary; they are not fabricated from
external character knowledge.

| Reference | Game | Primary role/category | Ability categories | Other selector-visible fields | Missing selector-visible fields |
|---|---|---|---|---|---|
| Furina | `genshin-impact` | — | Normal Attack; Elemental Skill; Elemental Burst; 1st/4th Ascension Passive; Utility Passive | taxonomy: Hydro, Sword, 5-star; occupation: null | roles, occupation |
| Keqing | `genshin-impact` | `on_field_dps` | Normal Attack; Elemental Skill; Elemental Burst; 1st/4th Ascension Passive; Utility Passive | Yuheng; taxonomy: Electro, Sword, 5-star | — |
| Nahida | `genshin-impact` | — | Normal Attack; Elemental Skill; Elemental Burst; 1st/4th Ascension Passive; Utility Passive | Dendro Archon of Sumeru; taxonomy: Dendro, Catalyst, 5-star | roles |
| Fadia | `neverness-to-everness` | — | Basic Attack; Basic Passive; Charged Basic; Dodge Counter Basic; Redirect Skill; Ultimate | taxonomy: Psyche, Synthesis, S-Class; occupation: null | roles, occupation |
| Shinku | `neverness-to-everness` | `on_field_dps` | Basic Attack; Redirect Skill; Ultimate; Support Skill; Passive; Special Trait | taxonomy: Cosmos, Synthesis, S-Class, Blushing Mirage; occupation: null | occupation |
| Jinhsi | `wuthering-waves` | `on_field_dps` | Normal Attack; Resonance Skill ×2; Resonance Liberation; Inherent Skill ×2 | Magistrate of Jinzhou; taxonomy: Spectro, Broadblade, 5-star | — |
| Mortefi | `wuthering-waves` | — | Normal Attack; Resonance Skill; Resonance Liberation; Forte Circuit; Intro Skill; Inherent Skill | Researcher / expert in Applied Tacetite Study; taxonomy: Fusion, Pistols, 4-star | roles |
| Shorekeeper | `wuthering-waves` | Support and Healer; Traction; DMG Amplification | Normal Attack; Resonance Skill; Resonance Liberation; Forte Circuit; Intro Skill; Outro Skill | Guardian of the Black Shores; taxonomy includes Support and Healer, Spectro, Rectifier, 5-star | — |
| Jane Doe | `zenless-zone-zero` | `on_field_dps` | Basic Attack; Dodge; Assist; Special Attack; Chain Attack; Ultimate | taxonomy includes Criminal Investigation Special Response Team, Physical, Anomaly, S | occupation |
| Nicole Demara | `zenless-zone-zero` | — | Basic Attack; Dodge; Assist; Special Attack; EX Special Attack; Chain Attack | Leader of the odd-job agency Cunning Hares; taxonomy includes Support, Ether, A | roles |

Selector-visible coverage counts are: roles 5/10, occupation 6/10,
ability categories 10/10, taxonomy 10/10. No component score fields are
exposed.

## Benchmark matrix

The benchmark runs 12 broad deterministic cases: ordinary urban support;
control/spatial coordination; aggressive frontline direct combat;
defensive/protective; mobility/repositioning; information/investigation;
performer/expressive identity; mature active playable; youthful/age-ambiguous;
ordinary non-professional; high charisma/low authority; and quiet practical
low spectacle.

Three contrast pairs are included:

1. Same researcher occupation, `on_field_dps` versus support/healer role.
2. Same `on_field_dps` role, quiet/practical versus flamboyant/performer
   personality and hook.
3. Same quiet/practical personality, researcher versus magistrate occupation.

Four one-dimension counterfactual pairs are included: support → control,
quiet → flamboyant, repair worker → performer, and mature → youthful
age-ambiguous.

## Metrics and machine results

The machine output is in
[`docs/reference_selection_quality_benchmark_v0.4.json`](reference_selection_quality_benchmark_v0.4.json).
It contains all 10 candidates in every full ranking, with real total score,
rank, source/game, score gaps, and tie groups.

Definitions:

- Top-1 and top-k frequency count actual selector outputs.
- Unique selected counts distinct references in selected top-k slots.
- Overlap is Jaccard overlap of selected top-k sets across all pairs of the 12
  broad cases.
- Concentration is HHI: `sum((reference selected slots / all selected slots)^2)`.
- Counterfactual rank sensitivity reports per-candidate before/after rank and
  score, plus mean absolute rank delta.
- Stability reruns each case twice with the same corpus and selector.
- Source concentration counts selected slots by actual `game_id` and reports
  source HHI.

Observed results from the deterministic run:

| Metric | Result |
|---|---|
| Total cases | 18 (12 broad + 6 contrast briefs) |
| Contrast pairs | 3 |
| Counterfactual pairs | 4 |
| Unique selected | 8 |
| Average broad-case top-k overlap | 0.448485 |
| Selection HHI | 0.159808 |
| Source HHI | 0.27915 |
| Stability | All cases stable on repeat |
| Corpus-order test | `ORDER_INDEPENDENT` |
| Classification | `LIMITED_SENSITIVITY` |

Top-1 frequency: `Keqing 4; Shinku 1; Jinhsi 2; Mortefi 1; Shorekeeper 9;
Jane Doe 1`.

Top-k frequency: `Furina 9; Keqing 5; Shinku 7; Jinhsi 6; Mortefi 3;
Shorekeeper 11; Jane Doe 1; Nicole Demara 12`.

Source/game selected-slot frequency: `genshin-impact 14;
neverness-to-everness 7; wuthering-waves 20; zenless-zone-zero 13`.

### Contrast and counterfactual results

| Pair | Changed candidates | Mean absolute rank delta | Selected top-k Jaccard |
|---|---:|---:|---:|
| Same occupation, role change | 9 | 3.4 | 0.2 |
| Same role, personality/hook change | 0 | 0.0 | 1.0 |
| Same personality, occupation change | 2 | 1.4 | 0.5 |
| Counterfactual support → control | 9 | 2.2 | 0.2 |
| Counterfactual quiet → flamboyant | 0 | 0.0 | 1.0 |
| Counterfactual repair → performer | 0 | 0.0 | 1.0 |
| Counterfactual mature → youthful | 0 | 0.0 | 1.0 |

This is limited sensitivity: exact role, ability-category, investigation,
occupation, and taxonomy tokens can move rankings, while personality, hook,
life stage, and unrepresented ordinary-worker/performer terms do not.

### Repeated trio

In this benchmark matrix, the observed live-run trio is not reproduced as a
single dominant top-k trio:

| Reference | Top-1 | Top-k |
|---|---:|---:|
| Furina | 0 | 9 |
| Keqing | 4 | 5 |
| Nahida | 0 | 0 |

That result is diagnostic. Current output depends on exact brief tokens and
available metadata; it neither confirms nor refutes the live-run observation.

## Corpus coverage

Coverage is based only on exact terms in selector-visible summaries:

| Dimension | Status | Evidence |
|---|---|---|
| Mature character | NOT REPRESENTED | No `mature`/`adult` selector-visible term |
| Young / age-ambiguous | NOT REPRESENTED | No age/life-stage term |
| Frontline role | PARTIAL | Four records expose `on_field_dps`; no explicit `frontline` label |
| Support | COVERED | Shorekeeper and Nicole expose support/healer terms; Shinku has Support Skill |
| Performer | NOT REPRESENTED | No performer/stage term |
| Ordinary worker | NOT REPRESENTED | No worker/repair/courier term |
| Investigator | COVERED | Jane Doe taxonomy contains Criminal Investigation |
| High charisma | NOT REPRESENTED | No charisma term |

This is a diagnostic coverage result, not a reason to add corpus records in
v0.4.

## Corpus-order sensitivity

The benchmark reranks the same summaries in repository order and reverse order.
Full rankings and selected top-k are identical: `ORDER_INDEPENDENT`.

Ties are common and are resolved by the explicit ascending `reference_id` key.
The evidence points to deterministic ID tie-breaking rather than dependence on
YAML/file/list iteration order.

## Machine benchmark versus design-quality review

Machine measures stop at ranking, score, overlap, concentration, sensitivity,
and deterministic stability. The output contains a MIMO review packet with the
requested rubric, but every subjective evaluation is intentionally null:

- role relevance: 0 / 1 / 2;
- ability/fantasy relevance: 0 / 1 / 2;
- personality/hook relevance: 0 / 1 / 2;
- life/identity relevance: 0 / 1 / 2;
- redundancy: LOW / MEDIUM / HIGH;
- copy risk: LOW / MEDIUM / HIGH.

MIMO can review useful precedent, redundancy, misleading references, and
homogenization risk. Code does not fabricate reference-usefulness labels.

## Production Parity Investigation

### Production selector path

For `py -m agents.official_character_authoring`, the path is:

```text
CLI main
  -> request_from_inputs()
  -> make_demo(..., brief=request.brief)
  -> load_reference_grounding(request.brief)
  -> CharacterReferenceRepository.list_all()
  -> _reference_summary() for each of 10 records
  -> rank_reference_summaries(request.brief, summaries)
  -> ReferenceGrounding.selected (top-k = 3)
  -> CharacterGenerationAgent(reference_context=selected)
  -> CharacterGenerationAudit.reference_ids
```

Selection is invoked once, before generation starts and before the model/tool
loop. The selector input is the raw `request.brief` string. Hard constraints,
soft preferences, forbidden elements, desired connections, scenario labels,
and request ID are not passed to reference selection. Scenario and custom
brief inputs therefore affect selection only through the resulting brief
string.

The live model and authoring tool loop cannot influence this selection call.
The constructor has a fallback `load_reference_grounding("")` for manually
constructed demos without supplied grounding, but the CLI path supplies the
grounding explicitly and does not take that fallback.

### Benchmark selector path

`py -m agents.reference_selection_benchmark` loads the same corpus summaries
and calls the same `rank_reference_summaries()` implementation. It bypasses
the production wrapper only to expose full ranking diagnostics. For the same
brief and corpus, benchmark-side ranking, production `load_reference_grounding`
ranking, and direct selector ranking are identical.

Therefore:

| Question | Answer |
|---|---|
| Exact same selector implementation? | YES |
| Same effective input for the same brief? | YES |
| Same historical input? | UNKNOWN; exact historical briefs are not stored |
| Live-model influence on reference selection? | NO |
| Tool-loop influence on reference selection? | NO |

This means v0.4 is a faithful benchmark of the deterministic selector. It is
not a replay of the unavailable historical brief text.

### Historical replay fixtures

Four replay fixtures were added for 麦嫂 (P1), 土屑 (P2), 覃雪岫 (P3), and
沈蓝枝 (P4). Repository docs preserve their names, outcomes, and brief
characteristics, but not the exact original brief strings. Every fixture is
therefore marked `APPROXIMATE_BRIEF_REPLAY`; historical top-k is stored as
evidence only and is never asserted as the expected implementation result.

The JSON machine output contains, for every fixture:

- historical live top-k;
- approximate brief replay top-k;
- production-input replay top-k through `load_reference_grounding`;
- direct selector replay top-k through `rank_reference_summaries`;
- rank differences and replay scores;
- explicit unknown historical-score and exact-input status.

Observed replay results:

| Case | Historical live | Brief / production-input / direct replay | Match |
|---|---|---|---|
| 麦嫂 (P1) | Furina / Keqing / Nahida | Shinku / Nicole Demara / Shorekeeper | NO |
| 土屑 (P2) | Furina / Keqing / Nahida | Furina / Keqing / Nahida | EXACT list equality, but approximate brief only |
| 覃雪岫 (P3) | Furina / Keqing / Nahida | Furina / Keqing / Nahida | EXACT list equality, but approximate brief only |
| 沈蓝枝 (P4) | Furina / Keqing / Nahida | Shinku / Shorekeeper / Nicole Demara | NO |

For P2 and P3, the approximate replay has zero matching selector tokens, so
all candidates tie at score 0 and the existing ascending `reference_id`
tie-break produces Furina / Keqing / Nahida. This is evidence of tie behavior,
not proof that the historical live briefs were identical to the fixture.

### Audit semantics

The production `Selected references` output is not a model retrieval trace.
It represents the final deterministic pre-generation selector top-k. Those
same three bounded summaries are inserted into
`CharacterGenerationRuntimeView.reference_context`, and the generation audit
mirrors their IDs in `CharacterGenerationAudit.reference_ids`. There is no
second reference-selection stage, retrieval dedup stage, or post-draft
reference filter in the CLI path.

Thus the benchmark and Official Character Authoring report the same selection
stage. Generation itself remains outside this offline replay.

### Nahida discrepancy

The current broad benchmark reports Nahida top-k frequency 0, while historical
live reports repeatedly included Nahida. The code-supported explanation is:

1. The production and benchmark selector implementations are the same.
2. The production CLI selects before the model/tool loop, so model-generated
   retrieval queries cannot explain the discrepancy in this path.
3. Exact historical brief text and historical selector scores were not
   preserved, so the observed live trio cannot be deterministically reproduced
   from the repository evidence.
4. Approximate P2/P3 replays produce the trio only through zero-score ID
   tie-breaking; P1/P4 produce different rankings when selector-visible terms
   such as `support` match current corpus summaries.

The remaining uncertainty is historical input/version evidence, not a proven
second production selector. The benchmark therefore distinguishes
deterministic selector quality from historical live-case reconstruction.

### Parity classification and decision

Classification: `HISTORICAL_CASE_DIFFERENCE`.

- Can v0.4 be frozen as a faithful benchmark of the deterministic selector?
  **YES**.
- Does v0.4 fully represent live end-to-end reference retrieval? **YES for
  the production reference-selection stage; generation/provider behavior is
  intentionally out of scope**.
- Are benchmark and production selected references the same system layer?
  **YES**.

Recommendation: `FREEZE_V0.4_THEN_EXPAND_CORPUS`. Preserve the current
diagnostic result, then use actual captured historical briefs or expand corpus
coverage based on review evidence. Do not change the selector in this task.

## Known limitations

- The corpus has only 10 records and uneven metadata coverage.
- Lexical token presence is not semantic relevance.
- There is no causal component attribution because production exposes one
  total score only.
- The benchmark does not claim that a reference caused any generated feature.
- It does not measure downstream authoring quality; that is the MIMO review
  stage.
- The matrix is deterministic and small; it is not a statistical estimate of
  all possible briefs.

Explicitly: **selection-level evidence != field-level causal attribution**.

## CLI

```powershell
py -m agents.reference_selection_benchmark
py -m agents.reference_selection_benchmark --detailed
py -m agents.reference_selection_benchmark --json
py -m agents.reference_selection_benchmark --json-file docs\reference_selection_quality_benchmark_v0.4.json
```
