# Reference Same-10 Metadata Baseline v0.4.1e

Status: **FROZEN**

This is a data baseline, not a selector-scoring release. The same ten
production characters remain unchanged while `analysis.yaml` authoring
metadata is backfilled. Facts, sources, schema, vocabulary, selector,
benchmark cases, generation, Canon, and Repair remain unchanged.

## Production roster

Furina, Keqing, Nahida, Fadia, Shinku, Jinhsi, Mortefi, Shorekeeper, Jane
Doe, and Nicole.

## Provenance audit

- `source_fact`: 68
- `analyst_derivation`: 65
- Source IDs/paths rejected: 0
- Source facts without `fact_path`: 7
- Valid document-level source evidence: 7
- Fact evidence gaps: 0
- Invalid provenance: 0

All seven pathless entries reference source IDs already registered in the
production corpus. The current schema explicitly permits document-level
`source_fact` evidence with `source_id` and no scalar `fact_path`. No
fact paths were invented, and no Hermes/MIMO scratch material is used as
production provenance.

## Diagnostic snapshot

| Dimension | Reference-side | Brief-side | Shared |
|---|---:|---:|---:|
| Personality | 10/10 | 10/18 | 9/18 |
| Gameplay fantasy | 10/10 | 9/18 | 9/18 |
| Life/social identity | 9/10 | 12/18 | 8/18 |
| Life-stage | 0/10 | 2/18 | 0/18 |
| Authority | 9/10 | 3/18 | 2/18 |
| Hook surface | 9/10 | — | — |
| Hook contrast | 8/10 | — | — |
| Hook behavioral | 10/10 | — | — |
| Motif | 0/10 | 0/18 | 0/18 |

These are separate diagnostics, not a combined quality score.

## Honest sparsity

`HONEST_SPARSITY_ACCEPTED`: life-stage remains 0/10 and motifs remain 0/10.
Furina's civilian identity and authority remain absent. No life-stage or
motif facts were added to make metadata appear complete.

Vocabulary compression remains unresolved, including coarse authority and
hook tokens. That pressure is intentionally deferred to a separate review.

## Selector and benchmark

- Authoring feature score contribution: **0**
- Unique selected: **8**
- Average overlap: **0.448485**
- HHI: **0.159808**
- Classification: `LIMITED_SENSITIVITY`
- Ranking parity: `PASS`
- Changed top-k cases: none
- Order: `ORDER_INDEPENDENT`

Authoring metadata remains diagnostic-only and does not affect reference
ranking, top-k selection, or tie-breaking.

## Validation

- Focused reference-corpus tests: `96 passed`
- Full test suite: `682 passed, 1 skipped`
- `git diff --check`: passed

## Remaining evidence-import gaps

Future targeted fact enrichment may support Furina's post-4.2 civilian
identity, explicit life-stage evidence for Jinhsi/Mortefi/Shorekeeper, and
source-grounded motif features. Those changes are outside this frozen data
baseline.
