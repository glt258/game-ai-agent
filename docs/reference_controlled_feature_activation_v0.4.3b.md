# Reference Selector v0.4.3b — Controlled Feature Activation

Status: **READY_FOR_ACTIVATION_FREEZE**

This gate activates exactly the previously approved ready domains in
production: `personality`, `gameplay_fantasy`, and `authority`. The corpus
remains the existing 10 reference records.

## Ordering contract

Production ordering is the tuple:

```text
(-legacy_score, -feature_secondary_score, reference_id)
```

`legacy_score` is the existing non-negative integer count of brief tokens
present in the tokenized JSON reference summary. It remains the primary key.
The feature score is consulted only when legacy scores are exactly equal. The
existing ascending `reference_id` tie-break remains final. Thus legacy 3
always ranks above legacy 2, even when the latter has maximum feature score.
Top-k remains the first three records after full ranking, and zero-score ties
use the same deterministic final tie-break.

## Feature semantics

Each active domain uses the frozen v0.4.3a bounded normalized Jaccard:

```text
J(B, R) = |B ∩ R| / |B ∪ R|
```

An empty brief or reference domain contributes `0` and is neutral: there is
no missing-data penalty, completeness multiplier, or metadata-density bonus.
The three active domain scores are averaged over domains with brief evidence,
so each domain has the same bounded maximum contribution. Legacy and feature
values are never added or weighted together.

Production and shadow use the shared helper in
`src/agents/reference_feature_ordering.py`. Production structurally passes
only the three ready domains.

## Explicitly non-active domains

The following produce zero production feature contribution:

- `authority_scope` — represented and diagnostic-only; authority form alone is active.
- `life_social_identity` — diagnostic-only; the known corpus gap remains.
- `hook_surface`, `hook_contrast`, `hook_behavioral_pattern` — deferred.
- `life_stage` — deferred; no production reference coverage.
- `visual_behavioral_motif` — deferred.

Changing only Nicole's `private_group` versus Jinhsi's `state_scale` scope
cannot change the production feature secondary score. Hook, identity,
life-stage, and motif evidence are likewise ignored by the production helper.

## Selection audit

`ReferenceGrounding.selection_audit` is an additive, backward-compatible
selection-level trace for all candidates. Each row exposes `legacy_score`,
`personality_match`, `gameplay_fantasy_match`, `authority_match`,
`feature_secondary_score`, the bounded per-domain trace, missing-neutral flags,
and one of `LEGACY_SCORE`, `FEATURE_SECONDARY_TIEBREAK`, or
`DETERMINISTIC_FINAL_TIEBREAK`.

This is selection attribution only. It does not claim that a reference caused
any particular generated field. Generation, Canon Checker, and Repair are
unchanged.

## Metrics

Historical legacy baseline, preserved separately:

| Metric | Value |
|---|---:|
| Unique | 8 |
| Overlap | 0.448485 |
| HHI | 0.159808 |
| Classification | `LIMITED_SENSITIVITY` |

Controlled activation:

| Metric | Value |
|---|---:|
| Unique | 9 |
| Overlap | 0.360606 |
| HHI | 0.146776 |
| Changed | 10/18 |
| Plausibly better | 4 |
| Plausibly worse | 0 |
| Ambiguous | 6 |

No changed core case crossed a legacy-score boundary, so the hard review gate
is clear: `PLAUSIBLY_WORSE = 0`.

## Changed frozen core cases

The frozen 18-case inputs remain unchanged. The following top-k changes are
inside equal-legacy-score groups and reproduce frozen shadow Model 3.

| Case | Legacy top-k | Activated top-k | Classification |
|---|---|---|---|
| `case-a-urban-support` | Shinku, Mortefi, Shorekeeper | Mortefi, Nicole, Shinku | `PLAUSIBLY_BETTER` |
| `case-b-spatial-control` | Shorekeeper, Nicole, Furina | Shorekeeper, Nicole, Nahida | `AMBIGUOUS` |
| `case-e-mobility-repositioning` | Shorekeeper, Nicole, Furina | Shorekeeper, Nicole, Keqing | `AMBIGUOUS` |
| `case-g-expressive-performer` | Shorekeeper, Nicole, Furina | Nicole, Shorekeeper, Furina | `PLAUSIBLY_BETTER` |
| `case-h-mature-active` | Jinhsi, Mortefi, Nicole | Jinhsi, Nicole, Mortefi | `AMBIGUOUS` |
| `case-l-quiet-practical` | Shorekeeper, Nicole, Furina | Shorekeeper, Nicole, Jane Doe | `AMBIGUOUS` |
| `contrast-occupation-role-onfield` | Keqing, Shinku, Jinhsi | Jane Doe, Keqing, Mortefi | `PLAUSIBLY_BETTER` |
| `contrast-role-quiet` | Keqing, Shinku, Jinhsi | Jane Doe, Keqing, Shinku | `PLAUSIBLY_BETTER` |
| `contrast-personality-researcher` | Mortefi, Nicole, Furina | Mortefi, Nicole, Jane Doe | `AMBIGUOUS` |
| `contrast-personality-magistrate` | Jinhsi, Nicole, Furina | Jinhsi, Nicole, Keqing | `AMBIGUOUS` |

The four plausibly better changes are supported by ready-domain signals. The
six ambiguous changes are retained as human-review context; none is
plausibly worse.

## Diagnostic extension and counterfactual pairs

All 12 frozen diagnostic cases ran unchanged, forming six pairs. Scope-only,
identity-only, and hook-only changes are not presented as successful
production feature activation. A production ordering change with no legacy tie
is attributed to the legacy selector rather than to feature activation.

| Pair | Changed dimension | Legacy tie | Ready difference | Ordering changed | Responsible domain | Explainability |
|---|---|---:|---:|---:|---|---|
| authority scope: small private / state institution | authority scope | NO | NO | NO | NONE | PASS |
| portfolio governance / sovereign | authority form and scope | YES | NO | YES | NONE | PASS |
| operational member / organization leader | identity authority | YES | YES | YES | authority | PASS |
| custodial executive / field enforcer | authority form and fantasy | NO | YES | YES | NONE | PASS |
| theatrical mask / playful danger | hook contrast | YES | YES | YES | personality | PASS |
| disciplined official / hope composure | hook contrast | YES | YES | YES | personality | PASS |

`authority_scope` remains represented but non-scoring. Identity remains
diagnostic-only because of `CORPUS_COVERAGE_GAP`; it is not compensated for by
activation. Hook-family scoring remains deferred.

## Shadow parity and determinism

Production activation matches frozen shadow Model 3 for all 18 core cases. The
same input is repeatable, reversing corpus order does not change ranking, and
reversing canonical feature token order does not change ranking. Selection
audit reasons remain within the three documented reason values.

## Validation and scope

Focused activation tests cover leapfrog protection, equal-legacy ordering,
all three ready domains, every non-active domain, missing-neutral semantics,
metadata density, tie-break stability, order independence, shadow parity,
audit traces, immutable corpus size, and the review metrics. The full suite is
run before handoff together with `git diff --check`.

No canonical vocabulary, corpus schema, facts, sources, production metadata,
benchmark inputs, character records, Generation, Canon Checker, or Repair
were changed. The additive selection audit is runtime reporting only.
`IDEA.md` and `manual_character_test.py` are protected and preserved.

Remaining gaps are intentionally deferred: identity requires corpus
expansion, authority scope is represented but non-scoring, and hook,
life-stage, and motif signals remain deferred. No commit, tag, or push is
created by this task.
