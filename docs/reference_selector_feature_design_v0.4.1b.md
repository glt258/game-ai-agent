# Reference Selector Feature Design v0.4.1b

Status: design-only recommendation

Classification: `NEEDS_MORE_FEATURE_DESIGN`

Repository: `D:\\game-ai-agent`

Date: 2026-08-18

## 1. Decision summary

The current reference selector is a deterministic lexical selector. It is small, stable, and order-independent, but it only sees a narrow projection of each reference record. Analysis metadata is loaded and validated by the corpus layer, yet the selector currently reads only `combat_design.normalized_roles` from analysis. Personality, identity hooks, narrative hooks, gameplay fantasy, product hooks, and visual motifs are selector-invisible.

The architecture can support an optional feature profile without changing the corpus facts model or the frozen benchmark cases. It is not safe to enable an effective feature score in this task, however, because the brief-side feature vocabulary, the authority/life-stage representation, and the weighting policy are not yet specified well enough to distinguish measured signal from hand-tuned assumptions. The existing four analysis-rich records would also make an immediate experiment a partial, unbalanced exposure rather than a controlled same-10 feature test.

Therefore this task adds the design boundary and experiment contract only. It does not add selector code, change the benchmark, backfill records, add characters, or change generation behavior.

The next safe implementation target is a feature-plumbing change with explicit per-dimension diagnostics and an opt-in score contribution. It should remain disabled until the same-10 metadata representation and a small approved brief vocabulary are fixed.

## 2. Current selector architecture

### 2.1 Data path

1. `load_reference_grounding()` loads the manifest and catalog, then reads the file-backed corpus repository.
2. `_reference_summary()` projects each `CharacterReference` into a compact summary containing reference ID, display name, game ID, roles, occupation, ability categories, and taxonomy.
3. `rank_reference_summaries()` tokenizes the brief and the JSON representation of each summary with the same deterministic tokenizer.
4. Each candidate receives one score: the number of distinct brief tokens also present in the candidate summary.
5. Candidates are sorted by `(-score, reference_id)` and the first three are selected.
6. The selected summaries are passed as reference context to character generation. They are precedent context, not Canon and not character facts.

### 2.2 Existing behavior

- Tokenization is lowercase and exact-match based: ASCII words, ASCII hyphen/underscore terms, and Chinese runs of at least two characters.
- The brief is converted to a set, so repeated query words do not increase score.
- Reference JSON keys and values are both tokenized. This means field names can match a brief as well as field values.
- There are no aliases, synonym expansion, semantic similarity, embeddings, vector search, reranking, learned weights, randomness, or LLM calls.
- Missing fields contribute no tokens and therefore no score evidence.
- Ties are resolved by stable `reference_id` order, making repeated and permuted-input runs deterministic.
- Analysis currently contributes only normalized combat roles. `character_design` and `product_design` are not read by the selector.

Relevant implementation files:

- `src/reference_corpus/loader.py`
- `src/reference_corpus/models.py`
- `src/reference_corpus/normalizer.py`
- `src/agents/official_character_authoring.py`
- `src/agents/reference_selection_benchmark.py`

## 3. Frozen baseline

The v0.4 benchmark remains the comparison point:

| Metric | Frozen v0.4 baseline |
|---|---:|
| Unique selected references | 8 |
| Average pairwise overlap | 0.448485 |
| Selection HHI | 0.159808 |
| Classification | `LIMITED_SENSITIVITY` |
| Repeat stability | stable |
| Input-order behavior | `ORDER_INDEPENDENT` |
| Zero-score candidates across all cases | 114 |
| Cases containing a zero-score tie group | 17 / 18 |

No Stage 0.5 replay was run because no feature integration was enabled. Consequently, there is no claimed before/after improvement and the frozen baseline is unchanged.

## 4. Feature design

The selector should consume a separate, optional `ReferenceFeatureProfile` rather than flattening all corpus YAML into the existing summary. This preserves the distinction between facts, analysis, and selector evidence and prevents feature-only fields from silently becoming generation facts.

### 4.1 Proposed profile

| Dimension | Reference-side source | Current availability | Brief-side extraction | Initial status |
|---|---|---:|---|---|
| `personality` | `analysis.character_design.personality_archetypes` | 0 / 10 populated | Approved exact descriptors and aliases only | Design needed |
| `hooks` | identity, narrative, gameplay, and product hooks | 4 / 10 analysis records have some hook/fantasy content | Explicit hook terms; no inferred biography | Partial |
| `gameplay_fantasy` | `character_fantasy`, normalized roles, and approved archetypes | 4 / 10 have character-analysis values; roles are broader | Explicit fantasy terms mapped to controlled categories | Partial |
| `life_social_identity` | facts narrative occupation, faction, affiliations, public identity | Facts are uneven but present in several records | Explicit occupation/social-identity wording | Partial |
| `life_stage` | Future explicit analysis field or fact-backed field | 0 / 10 represented | Explicit stage terms only; no age inference | Not representable yet |
| `authority` | Future explicit analysis field or fact-backed field | 0 / 10 represented | Explicit authority terms only; no status inference | Not representable yet |
| `visual_behavior_motifs` | `official_visual_tags`, `official_character_keywords`, `visual_motifs` | Existing facts exist; analysis motif lists are empty in current analysis-rich records | Explicit motif terms only | Partial |

The first implementation should not derive personality, age, authority, or motifs from occupation, faction, display name, prose proximity, or model output. A missing value is neutral evidence; it must not become a negative feature or an inferred default.

### 4.2 Canonical representation

The profile should expose normalized, deduplicated evidence while retaining its source dimension:

```text
ReferenceFeatureProfile(
    personality: tuple[str, ...],
    hooks: tuple[str, ...],
    gameplay_fantasy: tuple[str, ...],
    life_social_identity: tuple[str, ...],
    life_stage: tuple[str, ...],
    authority: tuple[str, ...],
    visual_behavior_motifs: tuple[str, ...],
)
```

The record should also carry diagnostics, outside the score itself:

```text
FeatureEvidence(
    dimension: str,
    matched_terms: tuple[str, ...],
    reference_id: str,
    source_kind: Literal["facts", "analysis"],
)
```

The initial profile should be derived in memory. Do not persist a second copy of feature data until the canonical vocabulary and provenance policy are accepted.

### 4.3 Vocabulary policy

The brief side needs a small, versioned vocabulary. It should contain canonical descriptors and a deliberately short alias set, with English and Chinese terms added only when they are validated by benchmark cases or corpus evidence. Free-form prose should remain available to the legacy lexical scorer, but it must not be interpreted as a structured personality, life-stage, authority, or motif claim.

Each structured match should record the canonical term and the exact brief token(s) that produced it. This makes a score explainable and prevents a growing synonym dictionary from becoming an undocumented second model.

## 5. Facts versus analysis

The selector must preserve the following boundary:

| Layer | Examples | Selector use | Generation/CANON status |
|---|---|---|---|
| Facts | occupation, faction, affiliations, official visual tags, ability taxonomy | Evidence-backed identity and presentation signals | Never rewrite; still not generated character facts |
| Analysis | personality archetypes, hooks, character fantasy, normalized roles, visual motifs | Optional similarity features and diagnostics | Interpretive precedent only; never promoted to Canon |
| Brief | user intent and explicit design constraints | Query features and legacy lexical tokens | Input intent, not reference evidence |

Analysis metadata is already validated as a separate `character-analysis/0.1` document. Its analyzer, model, prompt version, and timestamp provide derivation metadata, but field-level evidence currently covers facts only. The next schema revision should add analysis derivation evidence before any high-impact feature is used for authoritative claims. Until then, feature matches must be labeled as analysis-derived precedent signals.

## 6. Proposed selector integration

The future integration should be a staged extension around the existing deterministic scorer:

1. Build the legacy summary exactly as today.
2. Build an optional feature profile from facts and analysis.
3. Extract a structured query profile from the brief using the versioned vocabulary.
4. Compute per-dimension overlap diagnostics.
5. Add a separately reported feature contribution only when its dimension, vocabulary version, and weight configuration are explicit.
6. Keep `(-total_score, reference_id)` as the final ordering rule.

The score shape should be explicit rather than hidden in a larger tokenized JSON blob:

```text
total_score = legacy_score + feature_score
feature_score = sum(weight[dimension] * overlap(query[dimension], reference[dimension]))
```

For the first experiment, `overlap` should be binary per canonical term or a bounded count with a documented cap. It should not use cosine similarity or unbounded free-text counts. If weights cannot be justified from the same-10 evidence, the implementation should expose `feature_score` and diagnostics but keep its configured contribution at zero until the next experiment is approved.

The selected context should continue to expose the existing summary shape. Feature diagnostics may be stored in benchmark output or an internal selection result, but analysis-derived feature fields must not silently become part of the generated character's Canon or authored facts.

## 7. Why implementation is deferred in v0.4.1b

Three blockers are architectural rather than cosmetic:

1. There is no brief-side representation for personality, hooks, life-stage, authority, or visual behavior motifs. Adding ad hoc keyword rules now would encode the designer's assumptions before the corpus vocabulary exists.
2. Life-stage and authority are not represented in the current schema at all. Treating occupation, faction, or role as a proxy would cross the facts/analysis boundary and create false evidence.
3. Existing analysis coverage is only 4 / 10, and the populated records are not balanced across the intended dimensions. Enabling the current free-form hooks/fantasy text immediately would change the same-10 benchmark using partially available data, without a defensible feature weight or ablation interpretation.

These blockers make an effective selector change unsafe for this task. A design-only result is preferable to a feature layer whose apparent gains come from arbitrary aliases, field-name matches, or incomplete metadata coverage.

## 8. Stage 0.5 experiment contract

Stage 0.5 should use the exact current ten records and exact current benchmark cases. It must not add records, backfill metadata, change `selected_top_k`, alter tie-breaking, or change generation-agent behavior.

Required runs:

- Frozen v0.4 selector, recorded as `before`.
- Feature-support selector with the same corpus and benchmark, recorded as `after`.
- Repeated run and permuted-input run for stability and order independence.
- Feature ablation by dimension, with no hidden fallback to the legacy score.
- A no-analysis control in which analysis documents are absent; all analysis-derived feature components must be neutral.
- A no-live-LLM check for the complete benchmark path.

Required measurements:

- unique selected references;
- average pairwise overlap;
- HHI;
- per-case top-k selections and ranks;
- zero-score tie frequency;
- feature component counts and matched terms;
- repeat stability and order independence;
- before/after selected-set delta.

The result should be classified as follows:

- `READY_FOR_SAME10_BACKFILL` only if the profile is representable, missing metadata is neutral, feature effects are explainable, and the run is stable.
- `NEEDS_MORE_FEATURE_DESIGN` if dimensions or weights remain ambiguous, as in this task.
- `FEATURE_DESIGN_UNLIKELY_TO_HELP` if controlled feature ablations show no meaningful sensitivity after representation and vocabulary are sound.

## 9. Test plan for the next implementation

Focused tests should be added before enabling feature contribution:

- absent analysis produces an empty profile and exactly the legacy score;
- absent values in one dimension do not affect other dimensions;
- personality, hooks, gameplay fantasy, life/social identity, life-stage, authority, and motif matches each affect only their declared component;
- facts and analysis sources remain distinguishable in evidence diagnostics;
- feature terms are deduplicated and aliases map to one canonical term;
- missing metadata is neutral, not penalized;
- ties remain resolved by `reference_id`;
- repeated runs and permuted inputs are identical;
- the benchmark path performs no live LLM/network calls;
- `Canon`, `Repair`, and `CharacterDraft` behavior is unchanged;
- generation context does not promote analysis-derived evidence to Canon.

The full suite and `git diff --check` remain the release gates. The v0.4 baseline was `665 passed, 1 skipped` before this design-only change.

## 10. Production implications

There is no production behavior change in v0.4.1b. The current selector remains the production selector, and the current generation path continues to receive the existing selected reference summaries. No benchmark case, reference record, schema version, or prompt contract is changed by this document.

The next implementation should use an explicit feature-support flag or versioned selector configuration so that rollback means selecting the frozen lexical configuration, not editing corpus records. Any feature-enabled production trial should log the selector configuration, query features, reference feature evidence, score components, selected IDs, and whether analysis was available.

## 11. Next experiment recommendation

First approve the canonical feature vocabulary and add the missing schema/provenance design for life-stage and authority. Then implement in-memory feature profiles and diagnostics with contribution disabled. Only after the diagnostics are reviewed should the same-10 feature contribution be enabled for Stage 0.5. Backfill remains a later experiment and must not be combined with feature-weight tuning.

Final recommendation: `NEEDS_MORE_FEATURE_DESIGN`.
