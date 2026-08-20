# Reference Corpus v0.5 — Expanded Baseline Closure

Status: **FROZEN**

## Objective

Reference Corpus v0.5 was a gap-driven expansion phase. The initial planning
direction considered growth from 10 toward approximately 20 references, but
`~20` was never a hard quota. The production rule was always:

> Evidence quality > roster size; gap-driven > roster-driven.

The final v0.5 Production Corpus is therefore frozen at **11 records**. No
further character is added merely to approach the abandoned size target.

## Final corpus and successful expansion

| Stage | Production records |
| --- | ---: |
| Initial v0.5 baseline | 10 |
| Final expanded baseline | 11 |

The only successful v0.5 Production ingestion was:

- **Aalto — Wuthering Waves**

Aalto completed candidate research, semantic reconciliation, official PRIMARY
provenance review, source-based identity correction, production ingestion, and
benchmark validation. The final record is stored under
`data/reference_corpus/characters/wuthering_waves/aalto/` and is frozen by
`reference-corpus-expansion-v0.5d1`.

## Wave 2 closure

Wave 2 closes with `STOP_WAVE2`. This is not a judgment that the remaining
characters lack design value. It means that no new candidate simultaneously
passed the complete Production Gate:

1. realtime action character eligibility;
2. design precedent value;
3. PRIMARY identity evidence; and
4. PRIMARY gameplay evidence.

| Candidate | Identity PRIMARY | Realtime-action eligibility | Gameplay PRIMARY | Status |
| --- | --- | --- | --- | --- |
| Lumi | PASS | — | MISSING | `IDENTITY_PRIMARY_GAMEPLAY_GAP` / HOLD |
| Mint | PASS | UNCONFIRMED | MISSING | `PLAYABILITY_UNCONFIRMED` / HOLD |
| Chiz | PASS | UNCONFIRMED | MISSING | `PLAYABILITY_UNCONFIRMED` / HOLD |

These candidates are not rejected. They remain HOLD until the missing gate
evidence becomes verifiable.

## Existing HOLD pool

The existing pool remains unchanged:

- Piper — HOLD; design value sufficient, HoYoverse per-character PRIMARY not
  currently verifiable.
- Qingyi — HOLD; same source-access boundary.
- Astra Yao — HOLD; same source-access boundary.
- Ayla — HOLD; PGR PRIMARY not currently verifiable.

When source access returns, these candidates may undergo short provenance
confirmation. They do not need to repeat the full candidate-research phase.

## Source-policy freeze

The v0.5 provenance policy is now closed and explicit:

`SECONDARY_HOST_FIRST_PARTY_TEXT != PRIMARY`

A secondary host remains secondary even when it reproduces first-party
in-game text verbatim. Production PRIMARY provenance must resolve to an
official domain, official API, official CDN mapped to a canonical official
page, official article, or official character/profile source.

Aalto follows this policy through the two official Kuro Games articles recorded
in its source file; no secondary wiki is used as production PRIMARY evidence.

## Action-game hard gate

Production Reference Corpus candidates must come from realtime action character
games. Non-realtime game characters may be retained as auxiliary design
references, but they are not eligible for the Production Reference Corpus.

This gate is a production eligibility boundary, not a claim that non-realtime
characters have no authoring value.

## Frozen benchmark baseline

The final 11-record selector baseline is:

| Metric | Frozen value |
| --- | ---: |
| Unique selected | 10 |
| Average top-k overlap | 0.304545 |
| HHI | 0.137174 |
| Diagnostic cases | 12 |
| Aalto top-k appearances | 2 |

Relative to the preserved 10-record activated baseline, unique selected
increased from 9 to 10, while average overlap decreased from 0.360606 to
0.304545 and HHI decreased from 0.146776 to 0.137174. These are selection
diversity/concentration changes only; they are not model-quality improvement
claims.

The selector boundary remains unchanged:

- active domains: `personality`, `gameplay_fantasy`, `authority`;
- non-active domains: `life_social_identity`, `authority_scope`, `hook`,
  `life_stage`, `motif`;
- identity production scoring: **DISABLED**;
- identity production contribution: **0**.

Frozen benchmark and diagnostic case definitions are not modified.

## Known remaining corpus gaps

The following are honest coverage gaps, not v0.5 blockers:

- `ordinary_urban_worker`: **UNRESOLVED**
- `community_embedded_local`: **UNRESOLVED**
- `performer`: **UNRESOLVED**
- `itinerant_traveler`: **UNRESOLVED**
- `non_career_identity`: **UNRESOLVED**
- ordinary organization member: **PARTIAL**
- low-authority/high-competence: **PARTIAL**

The corpus is closed with these gaps visible rather than filled by weak or
secondary evidence.

## Protected files and scope

`IDEA.md` and `manual_character_test.py` remain untouched, uncommitted, and
unstaged. This closure adds no character, does not alter selector design,
scoring, schema, vocabulary, benchmark cases, or identity scoring.

## Next stage

The recommended next stage is **Character Authoring Model Benchmark v0.6**.
The v0.5 expansion phase should not be reopened until a future candidate clears
the complete Production Gate with evidence quality sufficient for production.
