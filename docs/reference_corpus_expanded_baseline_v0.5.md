# Reference Corpus Baseline reference-corpus-v0.5 — Expanded Baseline Freeze

Namespace: Reference Corpus Baseline
Identifier: `reference-corpus-v0.5`

Status: **FROZEN**

Freeze scope: the current 16-record Production Reference Corpus after Wave 3
HI3 ingestion. This document records the data baseline and its boundaries; it
does not change corpus records, selector behavior, schema, or vocabulary.

## Frozen corpus

The production corpus contains exactly **16 characters**.

| IP | Characters |
| --- | --- |
| Genshin Impact | Furina, Keqing, Nahida |
| Wuthering Waves | Aalto, Jinhsi, Mortefi, Shorekeeper |
| Zenless Zone Zero | Astra Yao, Jane Doe, Nicole, Piper Wheel, Qingyi |
| Neverness to Everness | Fadia, Shinku |
| Honkai Impact 3rd | Vita, Songque |

Canonical reference IDs:

```text
genshin-impact:furina
genshin-impact:keqing
genshin-impact:nahida
honkai-impact-3rd:songque
honkai-impact-3rd:vita
neverness-to-everness:fadia
neverness-to-everness:shinku
wuthering-waves:aalto
wuthering-waves:jinhsi
wuthering-waves:mortefi
wuthering-waves:shorekeeper
zenless-zone-zero:astra-yao
zenless-zone-zero:jane-doe
zenless-zone-zero:nicole
zenless-zone-zero:piper-wheel
zenless-zone-zero:qingyi
```

No additional character is part of this freeze. Li Sushang, Senadina, Mint,
Zero, Hathor, and Corin remain outside the production corpus.

## IP distribution

| IP | Records | Share |
| --- | ---: | ---: |
| Zenless Zone Zero | 5 | 31.25% |
| Wuthering Waves | 4 | 25.00% |
| Genshin Impact | 3 | 18.75% |
| Neverness to Everness | 2 | 12.50% |
| Honkai Impact 3rd | 2 | 12.50% |
| **Total** | **16** | **100.00%** |

HI3 is the fifth formal IP in the corpus. This is a corpus-diversity
observation, not a claim of improved model or generation quality.

## Source-policy freeze

Production PRIMARY evidence must come from an official source: an official
domain, official API, official CDN mapped to a canonical official page, or an
official article/profile source.

The following rule remains binding:

```text
SECONDARY_HOST_FIRST_PARTY_TEXT != PRIMARY
```

Wiki, Moegirl, Fandom, third-party databases, guides, search snippets, leaks,
datamines, and model memory are not promoted to PRIMARY. Existing records
retain only the source evidence recorded in their `sources.yaml` files.

Provenance remains limited to the existing kinds:

- `source_fact`
- `brief`
- `analyst_derivation`

The HI3 records use the validated HoYoverse `content_v2` family with
`iAppId=35`, `appSn=5fcd2aa439ca4aea`, GET pagination, `sLangKey`, and the
recovered 520/521/767 channel family. Vita (`iInfoId=126475`) and Songque
(`iInfoId=124932`) use official channel 767 roster evidence. Their
`itinerant_traveler` and `non_career_identity` values are analyst-derived
authoring interpretations, not quoted source facts.

## Known gaps and boundaries

### Covered semantic precedents

- `itinerant_traveler`: covered by Vita.
- `non_career_identity`: covered by Songque.
- `performer`: covered by Astra Yao.
- `ordinary_urban_worker`: covered by Piper Wheel.

### Remaining gaps

- `community_embedded_local`: **UNCOVERED**. Songque's Langqiu evidence is
  regional loyalty and a promise, not a small-scale reciprocal local network.
- Detailed PRIMARY kit text remains intentionally sparse for several records.
- Ordinary-member and low-formal-authority interpretations remain bounded and
  partial; absence of a leadership title is not itself a PRIMARY low-authority
  fact.
- Life-stage evidence remains sparse. Age is not inferred from appearance,
  body type, tone, or archetype.
- Life/social identity concepts may be represented in corpus metadata while
  remaining invisible to the active production selector.

### HOLD pool

| Candidate | Status | Boundary |
| --- | --- | --- |
| Li Sushang | OPTIONAL / HOLD | Same-slot-different-flavor versus Vita |
| Senadina | HOLD | Thin non-career adventure framing |
| Mint | HOLD | NTE gameplay PRIMARY gap |
| Zero | HOLD | NTE gameplay PRIMARY gap |
| Hathor | HOLD | NTE gameplay PRIMARY gap |
| Corin | HOLD | ZZZ concentration / redundancy |

## Selector state

The production selector is frozen exactly as configured:

- active domains: `personality`, `gameplay_fantasy`, `authority`;
- identity scoring: **DISABLED**;
- identity contribution: `0`;
- inactive domains: `life_social_identity`, `authority_scope`, `hook`,
  `life_stage`, and `motif`.

No selector weights, cases, briefs, expected references, active domains, or
selector implementation were changed for this freeze. Reference explainability
remains selection-level only: a selected reference may be reported for a case,
but it is not claimed to have caused a generated field.

## Frozen benchmark baseline

The formal offline selector benchmark uses the unchanged 18 diagnostic cases
and top-k = 3. The current 16-record baseline is:

| Metric | Frozen value |
| --- | ---: |
| Corpus records | 16 |
| Unique selected | 11 |
| Average top-k overlap | 0.346970 |
| HHI | 0.136488 |
| Benchmark cases | 18 |
| Classification | `LIMITED_SENSITIVITY` |

Top-k usage in the frozen run:

| Reference | Appearances |
| --- | ---: |
| Nicole | 12 |
| Shorekeeper | 10 |
| Shinku | 6 |
| Keqing | 5 |
| Jinhsi | 4 |
| Mortefi | 4 |
| Jane Doe | 3 |
| Furina | 1 |
| Aalto | 1 |
| Astra Yao | 1 |
| Piper Wheel | 7 |
| Vita | 0 |
| Songque | 0 |
| Qingyi | 0 |

Vita and Songque have `ZERO_SELECTION_USAGE`. This is recorded as a selector
observability limitation because their strongest authoring value is in
life/social identity dimensions that are currently inactive. It is not a
production corpus failure and does not justify a selector change.

The benchmark metrics describe selection diversity and concentration only;
they do not claim generation-quality improvement.

## Freeze boundary

This baseline freeze modifies documentation only. The following remain
unchanged:

- all `facts.yaml` files;
- all `sources.yaml` files;
- selector implementation and configuration;
- schema and canonical vocabulary;
- Character Generation Agent, Canon Checker, Repair Workflow, Live Adapter,
  and Model Adapter;
- benchmark cases, briefs, and expected semantic references;
- `IDEA.md` and `manual_character_test.py`.

Recommended next work is a separately scoped benchmark or gap-research task;
this v0.5 baseline should not be reopened by adding characters without a new
source-gated decision.
