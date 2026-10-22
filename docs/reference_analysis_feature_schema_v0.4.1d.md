# Reference Analysis Feature Schema v0.4.1d

Status: `READY_FOR_REVIEW`

Recommendation: `READY_FOR_SAME10_BACKFILL`

## 1. Purpose

v0.4.1d turns the v0.4.1c diagnostic vocabulary into an optional validated
block inside the existing `analysis.yaml` architecture. It does not populate
the ten production records and does not change reference selection scoring or
ranking.

The architecture remains:

```text
facts.yaml
  source-supported factual content

analysis.yaml
  analyst-derived interpretation and normalized authoring features

sources.yaml
  source records and factual field evidence
```

No parallel `selector_metadata.yaml`, `authoring_tags.yaml`, or feature file
was added.

## 2. Optional authoring feature block

The existing `CharacterDesignAnalysis` model now accepts an optional
`authoring_features` block:

```yaml
character_design:
  authoring_features:
    personality: []
    gameplay_fantasy: []
    life_social_identity: []
    life_stage: []
    authority: []
    hook:
      surface_traits: []
      contrast_traits: []
      behavioral_patterns: []
    visual_behavioral_motifs: []
    evidence: {}
```

The entire block and every dimension are optional. An absent block means no
normalized authoring metadata is available. An empty list means no supported
feature was recorded for that dimension. Neither state implies a semantic
default.

The exact model names are:

- `AuthoringFeatureBlock`;
- `StructuredHookFeatures`;
- `AuthoringFeatureEvidence`.

The extension remains under the existing `character-analysis/0.1` document
because all new fields are optional and old documents remain valid. The model
still rejects unknown fields everywhere else.

## 3. Dimensions and vocabulary reuse

All normalized values are validated against the existing vocabulary in
`src/reference_corpus/features.py`. No second vocabulary was introduced.

| Dimension | Schema field | Canonical source |
|---|---|---|
| Personality | `personality` | `VOCABULARY["personality"]` |
| Gameplay fantasy | `gameplay_fantasy` | `VOCABULARY["gameplay_fantasy"]` |
| Life/social identity | `life_social_identity` | `VOCABULARY["life_social_identity"]` |
| Life-stage | `life_stage` | `VOCABULARY["life_stage"]` |
| Authority | `authority` | `VOCABULARY["authority"]` |
| Hook surface | `hook.surface_traits` | `VOCABULARY["hook_surface"]` |
| Hook contrast | `hook.contrast_traits` | `VOCABULARY["hook_contrast"]` |
| Hook behavior | `hook.behavioral_patterns` | `VOCABULARY["hook_behavioral_pattern"]` |
| Visual/behavioral motif | `visual_behavioral_motifs` | `VOCABULARY["visual_behavioral_motif"]` |

Lists are deduplicated by validation and arbitrary selector tokens are
rejected. Existing richer analysis prose remains in fields such as
`character_fantasy`, `identity_hooks`, `narrative_hooks`, and
`visual_motifs`; the normalized block does not replace or rewrite that prose.

Gameplay fantasy remains separate from `AbilityFact`. Ability facts continue
to store source/reference content such as ability categories and mechanics;
authoring features describe the design fantasy an author may learn from that
reference.

Life-stage accepts only the v0.4.1c presentation vocabulary. Numeric age,
minor/adult inference, appearance-to-legal-age inference, and occupation-to-
life-stage inference are not represented by this schema.

Authority remains separate from competence, combat power, rarity, popularity,
and knowledge access. No numeric authority field exists.

## 4. Provenance contract

Each evidence entry has this shape:

```yaml
evidence:
  personality:
    - kind: source_fact
      source_id: synthetic-official
      fact_path: narrative.occupation
    - kind: analyst_derivation
      note: "The source-backed identity was normalized to an authoring descriptor."
```

Supported kinds are:

### `source_fact`

References an existing `sources.yaml` source through `source_id`. An optional
`fact_path` is relative to `CharacterFacts`, for example
`narrative.occupation` or `combat.abilities`. The loader rejects unknown
source IDs and invalid fact paths.

### `analyst_derivation`

Marks the interpretive step. It requires a non-empty `note` and cannot carry a
`source_id` or `fact_path`; otherwise it would masquerade as direct source
support. A feature group can therefore contain both source-fact entries and an
analyst-derivation note.

### `brief`

Supported by the shared provenance contract for diagnostic/query contexts, but
it cannot reference a corpus source or fact path. Production reference
`analysis.yaml` should normally use `source_fact` plus
`analyst_derivation`; author briefs are not reference facts.

Evidence paths are bounded to the authoring feature fields. Arbitrary evidence
maps are rejected. The contract is intentionally a small mapping from a
feature group to motivating source facts, not a graph system.

## 5. Loader and diagnostic integration

`CharacterReferenceLoader` now validates authoring-feature provenance after
loading facts, analysis, and sources. Existing factual provenance validation
remains unchanged.

`reference_feature_profile()` consumes schema-backed values first and also
retains compatibility with the older free-form analysis fields. When a
schema-backed feature has `source_fact` IDs, the diagnostic evidence is marked
`derived_from_fact`; without IDs it remains `analysis_only`.

The benchmark exposes the normalized features and per-domain overlap, but the
selector still calls the original lexical ranking path:

```text
diagnostic feature overlap → reported only
diagnostic feature overlap → score contribution: 0
```

No Canon, CharacterDraft, Character Generation, or Repair model consumes this
block as authoritative character data.

## 6. Missing-value and completeness policy

Every dimension is optional:

| State | Meaning |
|---|---|
| Block absent | No normalized authoring feature metadata supplied |
| Empty list | No supported feature or insufficient evidence for that dimension |
| `hook: null` | No structured hook evidence supplied |
| Partial hook | Only the supplied subfields are known |
| `life_stage: []` | Life-stage unknown; no inference permitted |
| `authority: []` | Authority unknown; no competence proxy permitted |

For Same-10 backfill review:

- `REQUIRED_FOR_BACKFILL_REVIEW`: canonical values must validate; each
  populated feature group needs a short rationale and evidence entries;
- `RECOMMENDED`: personality, gameplay fantasy, and life/social identity when
  the corpus supports them; explicit authority and life-stage when supported;
- `OPTIONAL`: visual/behavioral motifs and any unsupported dimension.

No character is required to fill every dimension. A sparse, source-honest
record is preferable to invented completeness.

## 7. Stage 0.6 regression

The exact v0.4 benchmark cases and unchanged ten-record corpus remain the
comparison. Schema-backed feature support is diagnostic only.

| Metric | Frozen v0.4 | v0.4.1d |
|---|---:|---:|
| Unique selected | 8 | 8 |
| Average top-k overlap | 0.448485 | 0.448485 |
| HHI | 0.159808 | 0.159808 |
| Classification | `LIMITED_SENSITIVITY` | `LIMITED_SENSITIVITY` |
| Ranking parity | — | PASS |
| Order independence | `ORDER_INDEPENDENT` | `ORDER_INDEPENDENT` |
| Feature score contribution | — | 0 |

This proves that schema acceptance and diagnostic visibility do not leak into
the selector score or top-k ordering.

## 8. Same-10 backfill template

The next task may populate the following block for each existing reference.
This task intentionally populated none of the ten production records.

```yaml
character_design:
  authoring_features:
    personality:
      - canonical_token
    gameplay_fantasy:
      - canonical_token
    life_social_identity:
      - canonical_token
    life_stage: []
    authority: []
    hook:
      surface_traits: []
      contrast_traits: []
      behavioral_patterns: []
    visual_behavioral_motifs: []
    evidence:
      personality:
        - kind: source_fact
          source_id: source-id
          fact_path: narrative.occupation
        - kind: analyst_derivation
          note: "Short interpretation rationale."
```

Backfill reviewers should preserve the original analysis prose and add only
bounded canonical values that the source material can support. Life-stage may
remain empty. Authority may remain empty. Hook subfields may be partial.

## 9. Quality review boundary

Code validates:

- canonical vocabulary membership;
- duplicate-free feature lists;
- optional block and partial hook structure;
- evidence kind shape;
- source IDs and fact paths where supplied;
- deterministic loading and serialization;
- compatibility of old analysis files;
- diagnostic visibility without selector scoring.

Code cannot validate whether a personality interpretation is insightful, a hook
is memorable, a gameplay fantasy is useful, or a source interpretation is
artistically strong. Those require MIMO or human review. The schema preserves
the evidence boundary so that such review can be performed honestly.

## 10. Implementation report

Git:

- Starting HEAD: `4f575f786c14fed2e10787a9aad2763350e69b46`
- Final HEAD: unchanged
- Branch: `main`
- Commit/tag/push: none

Compatibility:

- Existing ten records changed: **NO**
- Existing ten validate: **YES**
- CharacterDraft changed: **NO**
- Canon changed: **NO**
- Repair changed: **NO**

Tests:

- Focused schema/provenance tests: passing
- Full regression: `674 passed, 1 skipped`
- `git diff --check`: passing

Recommendation: `READY_FOR_SAME10_BACKFILL`.

Feature scoring remains deferred to a separate experiment after the backfill
and review are complete.
