# Reference Enriched Metadata Baseline v0.4.1f

Status: **FROZEN**

THIS IS A REFERENCE DATA/REPRESENTATION BASELINE.
IT IS NOT A SELECTOR SCORING RELEASE.

## Lineage

- Previous Same-10 metadata baseline: `reference-same10-metadata-v0.4.1e`
- v0.4.1f1 targeted fact enrichment: Jinhsi's primary-source Loong Scales
  fact was added to `facts.yaml` and registered in `sources.yaml`.
- v0.4.1f2 metadata unlock: Jinhsi received the existing canonical
  `signature_object` authoring token in `analysis.yaml`.

## Jinhsi evidence chain

The metadata chain is:

`official-developer-notes-jinhsi` (registered PRIMARY source)
→ `presentation.official_visual_tags`
→ source-backed `Loong Scales` fact
→ valid `source_fact` evidence
→ bounded `analyst_derivation`
→ `visual_behavioral_motifs: [signature_object]`

No symbolic interpretation is encoded. No new source, fact, schema, or
vocabulary entry was added in the metadata unlock.

## Metadata coverage

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
| Motif | 1/10 | 0/18 | 0/18 |

These are separate diagnostics, not a combined quality score.

## Honest sparsity and deferred evidence

`HONEST_SPARSITY_ACCEPTED`: life-stage remains 0/10 and motif coverage is
only 1/10. Coverage was not pursued as a target.

The following remain intentionally deferred or held:

- Jinhsi life-stage evidence
- Mortefi life-stage evidence
- Mortefi lighter motif
- Furina temporal civilian identity and former-authority distinctions
- Shorekeeper non-aging life-stage

## Production selector and benchmark

Authoring feature score contribution remains **0**. Authoring metadata is
diagnostic-only and does not affect production score, ranking, top-k
selection, or tie-breaking.

The frozen v0.4 benchmark remains identical:

- Unique selected: **8**
- Average overlap: **0.448485**
- HHI: **0.159808**
- Classification: `LIMITED_SENSITIVITY`
- Ranking parity: **PASS**
- Changed cases: **NONE**
- Order: `ORDER_INDEPENDENT`

## Remaining vocabulary pressure

The reviewed vocabulary issues remain unchanged and are not solved here.

P0:

- `formal_leadership` scope collapse
- `restrained` overuse
- `competence_without_spectacle` overuse

P1:

- `formal_professional` compression
- `organization_member_identity` default/filler behavior

Known hook gaps remain: Furina's honest contrast token, Fadia's honest
contrast token, and the Keqing/Jinhsi canonical hook collision.

Next phase: **MINIMAL VOCABULARY REVISION**.
