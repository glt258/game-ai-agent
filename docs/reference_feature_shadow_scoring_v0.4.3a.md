# Reference Selector v0.4.3a
# Authoring Feature Shadow Scoring

Status: **FROZEN / SHADOW-ONLY**

This document records a diagnostic-only shadow simulation. It does not
activate feature scoring, change the production selector, or change any
frozen benchmark case.

## Production selector audit

The current selector ranks the JSON reference summary produced by
`_reference_summary`. The summary exposes `reference_id`, display name,
`game_id`, normalized combat roles, narrative occupation, normalized ability
categories, and native taxonomy labels. It does not score rationale, evidence
notes, source text, or raw descriptions.

The exact production normalization is `_tokens`: lowercase text, then unique
ASCII tokens matching `[a-z0-9][a-z0-9_-]*` and Chinese runs of at least two
characters. For each reference, the legacy score is the integer count of
unique brief tokens that occur in the tokenized JSON summary. Role and
occupation therefore contribute only when their normalized values contain a
brief token; they have no separate weight. The score is non-negative and has
no completeness or metadata-density bonus.

The production `top_k` is 3. Sorting is descending integer legacy score,
then ascending `reference_id`. Zero-score references are therefore a fully
deterministic ID-ordered tie group. Across the frozen 18 cases, observed
scores are 0, 1, and 2. This scale is too coarse for an unbounded additive
feature score, so the shadow composition keeps legacy relevance primary.

## Domain readiness

Readiness was judged independently from benchmark winners using reference
coverage, brief extraction, canonical stability, known vocabulary findings,
missing-neutral behavior, determinism, and observable diagnostic signal.

| Domain | Reference coverage | Decision | Reason |
| --- | ---: | --- | --- |
| personality | 10/10 | READY_FOR_SCORING | Stable canonical vocabulary and full reference coverage. |
| gameplay_fantasy | 10/10 | READY_FOR_SCORING | Fact-grounded normalized combat fantasy with observable signal. |
| life_social_identity | 9/10 | SHADOW_ONLY | Identity corpus coverage gap remains. |
| authority | 9/10 | READY_FOR_SCORING | Canonical authority form is deterministic; scope remains a separate signal. |
| authority_scope | 5/10 | SHADOW_ONLY | Representation is valid, but half the corpus has no scope evidence. |
| hook_surface | 9/10 | SHADOW_ONLY | Vocabulary revision is not justified and hook dimensions need one family cap. |
| hook_contrast | 8/10 | SHADOW_ONLY | Diagnostic evidence exists, but production semantics are not yet stable enough. |
| hook_behavioral_pattern | 10/10 | SHADOW_ONLY | Coverage is broad, but hook remains a decomposed family. |
| life_stage | 0/10 | NOT_READY | Reference-side coverage is absent. |
| visual_behavioral_motif | 1/10 | NOT_READY | Reference-side coverage is too sparse. |

Only the three ready domains—personality, gameplay fantasy, and authority—are
used by Model 3. All other optional fields remain available in traces but do
not contribute to the ready-domain model.

## Shadow score semantics

Only canonical normalized feature values participate. A domain compares sets
of canonical values using one of five diagnostic primitives:

| Primitive | Semantics | Assessment |
| --- | --- | --- |
| raw intersection | Number of shared values | Unsafe as a default because metadata density can increase the score. |
| binary | 1 for any overlap, otherwise 0 | Bounded but discards partial similarity. |
| Jaccard | Shared values / union | Recommended bounded symmetric baseline. |
| overlap coefficient | Shared values / smaller set | Can over-credit a one-value subset. |
| capped token overlap | `min(1, shared / 2)` | Bounded, but less informative than Jaccard for larger sets. |

Jaccard is the selected primitive. A missing brief domain or missing
reference domain contributes exactly 0; it is never a negative penalty and
there is no completeness bonus. This keeps an unspecified brief neutral and
does not penalize references such as Furina for unknown `authority_scope`.

Authority form and `authority_scope` are scored independently. A brief with
formal leadership can match the authority form without receiving scope
evidence. An explicit `state_scale` brief matches only references with that
scope; unknown scope receives 0, not a negative score.

### Hook grouping

The hook surface, contrast, and behavioral-pattern values are traced
separately, but the family contributes at most one bounded score. The
simulation used Model 2 to compare grouping choices:

| Hook mode | Changed core cases | Unique | Overlap | HHI |
| --- | ---: | ---: | ---: | ---: |
| independent | 13 | 9 | 0.350000 | 0.163237 |
| family_max | 13 | 9 | 0.348485 | 0.156379 |
| family_capped_sum | 13 | 9 | 0.348485 | 0.156379 |

`family_max` is selected for the shadow baseline because it is the simplest
interpretation: three hook subdomains explain the trace, but cannot make the
hook family outweigh other domains merely because it is decomposed three
ways. The capped-sum variant produced the same frozen-core result here but
adds a second aggregation rule without current evidence that it is needed.

## Composition models

The feature subtotal is the mean of active brief domains, so missing domains
remain neutral rather than shrinking a reference's score through a penalty.
The feature subtotal is bounded to `[0, 1]`. Models are:

| Model | Composition | Purpose |
| --- | --- | --- |
| Model 0 | Legacy only | Production-equivalent control. |
| Model 1 | Feature subtotal only | Sensitivity diagnostic; not a production candidate. |
| Model 2 | Legacy primary + all candidate feature domains | Stress-test sparse and not-ready metadata. |
| Model 3 | Legacy primary + ready domains only | Smallest candidate for a controlled experiment. |

For Models 2 and 3, the reported numeric shadow value is
`legacy_score + 0.25 * feature_subtotal`, with a fixed interpretable cap.
The actual ordering key is `(legacy_score, feature_subtotal, reference_id)`.
Thus a feature-similar reference cannot leapfrog a reference with a higher
legacy score; features only resolve legacy ties, with the existing ID
tie-break still deterministic. The 0.25 cap was not tuned against winners.

## Frozen core shadow results

The frozen production baseline is:

```text
cases: 18
unique: 8
average top-k overlap: 0.448485
HHI: 0.159808
classification: LIMITED_SENSITIVITY
ranking parity: PASS
order: ORDER_INDEPENDENT
```

Shadow results:

| Model | Unique | Overlap | HHI | Changed |
| --- | ---: | ---: | ---: | ---: |
| Model 0 | 8 | 0.448485 | 0.159808 | 0 |
| Model 1 | 10 | 0.190909 | 0.112483 | 18 |
| Model 2 | 9 | 0.348485 | 0.156379 | 13 |
| Model 3 | 9 | 0.360606 | 0.146776 | 10 |

Model 3 changed:

```text
case-a-urban-support
case-b-spatial-control
case-e-mobility-repositioning
case-g-expressive-performer
case-h-mature-active
case-l-quiet-practical
contrast-occupation-role-onfield
contrast-role-quiet
contrast-personality-researcher
contrast-personality-magistrate
```

Model 3 changes classified as plausibly better:

```text
case-a-urban-support
case-g-expressive-performer
contrast-occupation-role-onfield
contrast-role-quiet
```

Plausibly worse: **none**. Ambiguous changes:
`case-b-spatial-control`, `case-e-mobility-repositioning`,
`case-h-mature-active`, `case-l-quiet-practical`,
`contrast-personality-researcher`, and `contrast-personality-magistrate`.
The ambiguous label means that no gold reference ID exists and the change
cannot be called an improvement from this benchmark alone.

The primitive experiment under Model 3 was also treated as a diagnostic,
not an optimization target:

| Primitive | Changed | Unique | Overlap | HHI |
| --- | ---: | ---: | ---: | ---: |
| raw intersection | 10 | 9 | 0.360606 | 0.148834 |
| binary | 8 | 9 | 0.368182 | 0.158436 |
| Jaccard | 10 | 9 | 0.360606 | 0.146776 |
| overlap coefficient | 10 | 9 | 0.360606 | 0.148834 |
| capped token overlap | 10 | 9 | 0.360606 | 0.148834 |

The choice of Jaccard is semantic: it avoids raw metadata-density reward,
preserves partial similarity, and is symmetric. It is not selected because
its concentration metric is highest or lowest.

## Diagnostic extension and counterfactuals

The 12 diagnostic cases and six pairs remain separate from the frozen core.
The v0.4.2b classification labels were not modified. Model 3 showed the
following pair-level shadow overlaps:

| Pair | Primary design dimension | Production overlap | Shadow overlap | Responsible shadow component |
| --- | --- | ---: | ---: | --- |
| small private team → state institution | authority_scope | 1.0 | 1.0 | authority_scope |
| portfolio governance → sovereign | authority_form, with scope evidence | 0.5 | 0.5 | authority_scope |
| operational member → formal organization leader | identity/authority | 0.5 | 0.2 | life_social_identity, authority, authority_scope |
| custodial executive → field enforcer | authority form / fantasy | 1.0 | 0.5 | gameplay_fantasy, authority, authority_scope |
| theatrical mask → playful danger | hook_contrast | 0.5 | 0.5 | personality |
| disciplined official → hope/composure | hook_contrast | 0.5 | 0.5 | personality, hook_contrast |

The authority-scope representation is observable, but the first pair remains
a shared top-k collision in the current 10-reference corpus. The portfolio
versus sovereign pair gets scope pressure, but the changed authority-form
distinction itself is not independently represented; this is evidence for
continued shadow-only evaluation rather than a vocabulary change. The
identity pair shows the existing corpus limitation. Hook and personality
remain diagnostic signals without a revision finding.

## Concentration, stability, and explainability

The ready-domain shadow model is deterministic and order-independent for both
corpus order and canonical feature order. Every row contains the legacy score,
feature subtotal, bounded bonus, score key, selected top-k, and per-domain
brief/reference/shared-value trace. No free prose, source text, or rationale
is scored.

The lower Model 3 HHI (`0.146776`) and higher unique count (`9`) are reported
only as concentration diagnostics. They are not treated as automatic quality
improvements. Model 3's lexicographic composition preserves legacy relevance
as the primary gate, so the shadow changes are tie-group changes rather than
lower-legacy-score leapfrogs.

## Production invariants

The simulation reports and tests these invariants:

```text
production feature contribution: 0
production selector touched: NO
production ranking logic changed: NO
production tie-breaking changed: NO
frozen core metrics changed: NO
diagnostic extension used for production ranking: NO
```

No vocabulary, schema, corpus record, fact, source, Generation, Canon, or
Repair file was changed.

## Recommendation

Result classification: **READY_FOR_CONTROLLED_ACTIVATION**.

The recommended future experiment is Model 3 with Jaccard, a single capped
hook-family rule if hooks are later admitted, missing-neutral semantics, and
legacy-first lexicographic composition. Activation is not performed in
v0.4.3a. `authority_scope`, identity, hooks, life-stage, and visual motif
remain shadow-only or not-ready, and corpus expansion is still required for
identity and scope coverage before those domains can contribute.

## Freeze note

This is a **SHADOW-SCORING BASELINE**. Production feature scoring remains
disabled. The accepted experiment is frozen as
`reference-feature-shadow-scoring-v0.4.3a`; no hook, authority-scope,
identity, life-stage, or motif scoring is activated by this freeze.
