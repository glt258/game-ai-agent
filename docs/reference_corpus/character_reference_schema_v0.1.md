# Character Reference Corpus Schema v0.1

## Purpose

Character Reference Corpus stores structured design references for external commercial
game characters. It is an input boundary for future analysis and retrieval work; it is
not the project's world Canon and is never copied into the Canon Store automatically.

The current implementation stops at loading, validating, and indexing records. It does
not include a crawler, RAG, embeddings, similarity search, Pattern Extractor, or Agent
integration.

## Physical layout

Each character directory contains two required documents and one optional document:

```text
<characters>/<game-id>/<character-id>/
├── facts.yaml       # externally supportable facts only
├── analysis.yaml    # optional design analysis and inference
└── sources.yaml     # provenance and field evidence
```

The catalog files live under `data/reference_corpus/characters/_catalog/`. No real
commercial character records are included in this phase. Synthetic records used by
tests live only under `tests/reference_corpus/fixtures/`.

## Separation rules

`facts.yaml` contains concise facts supported by sources: identity, native taxonomy,
ability summaries, narrative facts, and explicitly published presentation keywords.
Unknown facts remain `null` or `[]`.

`analysis.yaml` contains normalized roles, loops, archetypes, design patterns, product
design observations, and similarity signatures. These are analysis, not claims about a
publisher's internal business decisions. In particular, `product_design` means an
external analysis of public design evidence.

`sources.yaml` contains source records, reliability, verification status, conflicts,
and a `field_evidence` mapping from fact paths to source IDs. It never stores a copied
web page or a long source transcript.

## Loader behavior

`CharacterReferenceLoader.load(path)` performs the following deterministic sequence:

1. Requires `facts.yaml` and `sources.yaml`.
2. Parses YAML and validates each document with Pydantic models using `extra=forbid`.
3. Requires the exact v0.1 schema version for each document.
4. Validates the game against the Game Catalog when a catalog is supplied.
5. Checks that all `reference_id` values agree.
6. Verifies source IDs and supported non-indexed field-evidence paths.
7. Computes quality and returns one `CharacterReference` object.

Missing files, invalid YAML, schema failures, unsupported versions, ID mismatches, and
provenance failures use separate error types.

## Quality behavior

Quality is computed rather than stored as a fourth YAML file. Scores are deterministic:

| Section | Rule |
| --- | --- |
| identity | `game_id` and canonical name populated, divided by 2 |
| combat | native taxonomy and at least one ability populated, divided by 2 |
| narrative | faction, occupation, affiliations, and public identity populated, divided by 4 |
| presentation | official visual tags and official keywords populated, divided by 2 |
| analysis | eight top-level analysis sections present, divided by 8; absent analysis is 0 |

Scores are rounded to four decimal places and constrained to `[0.0, 1.0]`. Missing
analysis produces a warning and `AnalysisStatus.missing`; source conflicts are preserved
in quality and do not silently become verified.

## Minimal example

```yaml
# facts.yaml
schema_version: "character-facts/0.1"
reference_id: "game-id:character-id"
identity:
  game_id: game-id
  native_character_id: null
  names:
    canonical: "Character Name"
    localized: {en-US: "Character Name"}
  release: null
  rarity: null
combat:
  native_taxonomy:
    labels: {weapon_type: "native label"}
  abilities: []
  mechanics: {}
  team_mechanics: {}
narrative: {}
presentation: {}
```
