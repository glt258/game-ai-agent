# Reference Corpus v0.5d1 — Aalto Production Ingestion

Status: **READY_FOR_REVIEW**

This record adds exactly one production reference character: Aalto from
*Wuthering Waves*. The expansion is gap-driven: the missing precedent is an
informal information broker whose external commercial operation coexists with
confirmed organizational membership.

## Scope and source reconciliation

The earlier assumption that Aalto was a purely unaffiliated outsider is not
production-safe. Kuro Games' primary material identifies Aalto as a Black
Shores member while also describing his Information/Intelligence Broker work,
personal pricing criteria, external information deals, and maneuvering-focused
combat. The record therefore preserves both sides of the identity:

- source facts: Information Broker, Black Shores faction/affiliation, ranged
  attacks, Mist Avatar decoy/taunt, Gate of Quandary ranged-attack enhancement,
  and Mistform movement/maneuvering;
- analysis: informal worker, organization member, and a partial
  independent-operator precedent;
- excluded: fully independent, unaffiliated, pure outsider, commander,
  captain, leader, authority scope, inferred age, and inferred personality.

## Primary provenance

| Source ID | Official article | Production use |
| --- | --- | --- |
| `official-developer-notes-aalto` | [Developer's Notes — Aalto, article 497](https://wutheringwaves.kurogames.com/en/main/news/detail/497) | Broker operation, personal pricing, Black Shores membership, combat and Mist mechanics |
| `official-profile-reveal-aalto` | [Profile Reveal: Mistcloak Strike — Aalto, article 475](https://wutheringwaves.kurogames.com/en/main/news/detail/475) | Information Broker profile identity and right-price information trade |

Both source records are official/primary. Their canonical URLs and article IDs
are preserved; the existing source schema has no separate CDN-locator field, so
the confirmed Kuro Games CDN host `hw-media-cdn-mingchao.kurogame.com` is
recorded in `version_context` and verification notes. No wiki or MIMO/Hermes
material is used as production provenance.

## Production metadata

Record path: `data/reference_corpus/characters/wuthering_waves/aalto/`

| Domain | Aalto value | Provenance boundary |
| --- | --- | --- |
| life/social identity | `informal_worker`, `organization_member`, `independent_operator` | First two are source-grounded normalization; independent operation is analyst derivation and partial because Black Shores membership remains explicit |
| authority | `low_formal_authority` | Analyst derivation only; no source claim of absent authority |
| authority scope | absent | Membership is not leadership or scope |
| gameplay fantasy | `mobility_repositioning`, `setup_payoff` | Minimal mapping from Mistform/decoy/Gate and ranged-attack payoff |
| personality | absent / neutral | The primary anchors do not require a conservative canonical personality token |
| hook | `organization_member_identity` surface | Bounded membership hook; no new token |
| life-stage | absent / unknown | No age inference |
| motif | absent | No density-driven addition |

`independent_operator` is **PARTIAL**, not a claim that Aalto is a pure
independent or that the independence gap is fully solved. `informal_worker` is
filled because the broker work has personal pricing, variable clientele,
non-standard transaction conditions, and self-directed commercial operation.

## Corpus and benchmark

Production corpus count: **10 → 11**. The historical 10-record baseline is
retained and not rewritten:

| Metric | 10-record baseline | 11-record expansion |
| --- | ---: | ---: |
| Unique selected | 9 | 10 |
| Average top-k overlap | 0.360606 | 0.304545 |
| HHI | 0.146776 | 0.137174 |

The selector and scoring implementation are unchanged. The 11-record run of
the frozen 18 benchmark cases has two changed top-k cases when compared with
the same selector over the original 10 records:

- `case-f-information-investigation`: Aalto enters at rank 2, replacing
  `zenless-zone-zero:nicole` at rank 3;
- `case-k-charisma-low-authority`: Aalto enters at rank 3, replacing
  `genshin-impact:furina`.

The frozen case definitions and historical 10-record snapshot remain
unchanged. The 12-case feature-discrimination diagnostic also remains frozen;
its production feature score contribution is **0**. Reference-side coverage
now includes Aalto's `informal_worker`, `organization_member`, and partial
`independent_operator` values, without making life/social identity production
scoring-active.

## Aalto selection audit

| Case | Legacy | Personality | Fantasy | Authority | Ordering reason | Classification |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `case-f-information-investigation` | 1 | 0.0 | 0.0 | 0.0 | `LEGACY_SCORE` | `EVIDENCE_BACKED_MATCH` / legacy role match |
| `case-k-charisma-low-authority` | 0 | 0.0 | 0.0 | 0.5 | `FEATURE_SECONDARY_TIEBREAK` | `EVIDENCE_BACKED_MATCH` / authority feature tie |

Aalto has two top-k appearances. No top-k case has legacy score 0, feature
score 0, and `DETERMINISTIC_FINAL_TIEBREAK`; the zero-evidence tie-break audit
is **NO**, severity **NONE**. There is no material selector-tie-break
exposure, so the task does not stop with `SELECTOR_TIEBREAK_EXPOSED`.

## Gap update

- `informal_worker`: 0 → 1
- Aalto ordinary-organization-member expansion precedent: 0 → 1
  (the existing corpus token count is preserved and Aalto adds one more
  `organization_member` record)
- `independent_operator`: partial precedent remains partial; Aalto does not
  establish a pure-independent gap solution
- low-authority/high-competence: Aalto adds a bounded analyst-derived
  `low_formal_authority` example

Held candidates remain untouched:

- Piper — `SECONDARY_ONLY_HOLD`
- Qingyi — `SECONDARY_ONLY_HOLD`
- Astra Yao — `SECONDARY_ONLY_HOLD`
- Ayla — `PRIMARY inaccessible HOLD`
- Performer slot — `OPEN`

## Regression and scope safety

- Existing 10 production records: unchanged
- Selector: unchanged
- Scoring: unchanged
- Vocabulary/schema: unchanged
- Frozen benchmark and diagnostic case definitions: unchanged
- Character Generation, Canon Checker, and Repair: unchanged
- Protected `IDEA.md` and `manual_character_test.py`: preserved
- Characters added: 1
- Git commit/tag/push: none

Validation target: focused Aalto tests, full `py -m pytest`, and
`git diff --check`.

Recommendation: **READY_TO_FREEZE_AALTO_EXPANSION**.
