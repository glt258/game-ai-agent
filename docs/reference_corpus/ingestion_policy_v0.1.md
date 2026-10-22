# Reference Corpus Ingestion Policy v0.1

## Evidence and unknowns

- Every fact must be traceable to one or more source IDs in `sources.yaml`.
- Unknown facts stay `null` or `[]`; do not guess to improve completeness.
- AI inference, normalization, and design interpretation belong in `analysis.yaml`, not `facts.yaml`.
- Official/native taxonomy must remain separate from normalized cross-game analysis.
- A URL is required for every source record; a missing URL cannot be marked verified.

## Content limits

Do not store full web pages, long plot summaries, large copied ability descriptions, or
guide/wiki articles. Store short factual summaries and source metadata instead. The
corpus is a structured reference layer, not an offline mirror of third-party sites.

## Verification

Prefer primary official sources for identity and native taxonomy. If no official source
is publicly available, a reliable secondary source may be used with an appropriately
lower verification status. Conflicting sources must be represented explicitly under
`verification.conflicts`; they must not be flattened into a false `verified` result.

## Corpus boundary

Reference records remain outside the project's Canon data. Loading a reference never
changes `data/canon`, character Canon, NPC behavior, Character Generation behavior, or
Canon Checker behavior. This phase intentionally ends before crawler, RAG, embeddings,
Pattern Extractor, and agent integration work.

The catalog's `fixture_plan.yaml` records the intended first batch of 20 real records
(four games, five design-space slots each). It is a plan only; synthetic test fixtures
must not be presented as commercial character data.
