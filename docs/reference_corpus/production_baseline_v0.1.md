# Reference Corpus Production Baseline v0.1

## Status

Status: **FROZEN FOR AGENT / EVAL BASELINE**

Baseline anchor commit: `90ee1e2` (`data: finalize Mortefi reference corpus`)

Production records: **10**

Expansion mode:

- ROSTER-DRIVEN: **PAUSED**
- GAP-DRIVEN: **ACTIVE**

The Reference Corpus is supporting infrastructure for the Character Generation
Agent, Canon Checker, Repair Loop, and evaluation. It is not the project's
primary product.

This is the frozen baseline for Character Generation evaluation work. Caesar
expansion stops here. The ten accepted production records are read-only
baseline data; the Reference Corpus is a precedent/oracle source, not a set of
answers to inject into generation prompts or a commercial-character imitation
target. The frozen Reference Corpus schema remains unchanged.

Future record #11 requires a demonstrated benchmark-driven coverage gap and
human approval. Benchmark failures alone do not authorize corpus expansion,
and no character may be added merely to increase the sample count.

## Production Characters

### Golden Pilot

- `genshin-impact:keqing`
- `wuthering-waves:jinhsi`
- `zenless-zone-zero:jane-doe`
- `neverness-to-everness:shinku`

### Wave 1

- `genshin-impact:furina`
- `wuthering-waves:shorekeeper`
- `zenless-zone-zero:nicole`
- `neverness-to-everness:fadia`

### Wave 2 Included in Baseline

- `genshin-impact:nahida`
- `wuthering-waves:mortefi`

Total: **10**

## Why Freeze at 10

The corpus has sufficient mechanism coverage to begin exercising the actual
Agent pipeline. This is not a claim of statistical dataset completeness.

The baseline is intended for mechanism coverage, schema pressure, Agent and
repair evaluation, and oracle/reference comparison. Existing pressure areas
include resources, conditional or gated abilities, passive-modified
relationships, `TeamInteraction`, buffs/debuffs/healing/grouping/off-field
behavior, target/state/resource distinctions, summon-graph friction, and
external teammate-event graph friction.

The project does not currently require a larger roster merely to increase the
character count. The strategy change shifts development effort back to the
Agent mainline; the previously planned 16-character roster is not considered a
failure.

## Expansion Policy

Future production characters are added only when a concrete Generator, Canon,
Repair, or Eval failure exposes a coverage gap that the existing 10-character
corpus cannot adequately represent.

Decision rule:

1. Agent/Eval failure.
2. Check whether the existing corpus contains a precedent.
3. If yes, fix the Agent, Eval, or modeling first.
4. If no, select a commercial character specifically for that gap and add
   Corpus N+1.

This is **GAP-DRIVEN CORPUS EXPANSION**, not roster-driven corpus expansion.

## Caesar and Paused Roster Work

Caesar expansion: **STOPPED** at this baseline

Remaining previously planned expansion characters remain **BACKLOG**. They are
not cancelled permanently and no longer have automatic priority.

## Next Phase

The next phase is:

1. Character Generation quality
2. Canon checking
3. Repair Loop
4. Eval / Lean Benchmark
5. Demo

The Reference Corpus should initially serve as a benchmark, oracle, and
precedent corpus.

The following are not implemented and are not part of this freeze task:

- PatternExtractor
- Design Pattern Corpus
- Embedding / RAG
- live retrieval/RAG integration

## External Team-Event Graphability

Confirmed production cases:

1. Shorekeeper
2. Fadia
3. Mortefi

Status: **NARROW SCHEMA REVIEW CANDIDATE**

Blocking: **NO**

Immediate schema modification: **NO**

The current schema preserves the relevant commercial facts using
`TeamInteraction` and prose without corrupting the data. Revisit this item
when Agent/Eval behavior or additional gap-driven examples provide more
pressure. No new KL number is created by this baseline.

## Frozen Boundaries

This baseline does not freeze the Reference Corpus forever. It freezes the
current 10 records as the first Agent/Eval production baseline, while allowing
future gap-driven additions.

This freeze does not authorize:

- schema changes
- PatternExtractor, RAG, or new analysis generation
- automatic Canon ingestion
- additional roster-driven character collection

Existing runtime freeze `v0.6.6` remains untouched. Existing Reference Corpus
tags `reference-corpus-pilot-v0.1` and `reference-corpus-wave1-v0.1` remain
untouched.
