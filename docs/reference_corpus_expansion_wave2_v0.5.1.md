# Reference Corpus Production Expansion Wave 2 — v0.5.1

Status: **FROZEN**

This wave ingests the approved `ADD_3` set: Astra Yao, Piper Wheel, and
Qingyi. It changes production data, provenance, benchmark results, and this
documentation only. It does not change selector code, benchmark cases,
briefs, expected semantic cases, identity scoring, Character Authoring,
Canon Checker, Repair Workflow, or Live Adapter behavior.

## ADD_3 rationale

The three records were already approved after candidate research, MIMO
shortlisting, and final PRIMARY provenance verification. They close distinct
authoring gaps while preserving honest sparsity:

| Character | Game | Production value |
| --- | --- | --- |
| Astra Yao | Zenless Zone Zero | public performer / singer / idol identity; public-performance hook; Support gameplay floor |
| Piper Wheel | Zenless Zone Zero | vehicle-oriented ordinary-worker precedent; organization membership; competence without leadership |
| Qingyi | Zenless Zone Zero | formal/public institutional investigator precedent; Public Security team relation |

No new character research was performed in this ingestion wave.

## PRIMARY provenance summary

All three records use the official HoYoverse `content_v2` API locator:

```text
app id:             3e9196a4b9274bd7
character channel:  iChanId=287
faction channel:    iChanId=286
```

Character records are selected from `data.list[iInfoId=...]` with
`iInfoId=127387` (Astra), `124310` (Piper), and `124660` (Qingyi). The
record-level `sChanId` relation is preserved as `998`, `889`, and `782`.
The source files also record the associated official faction records:
`127385` Stars of Lyra, `124305` Sons of Calydon, and `122783` Criminal
Investigation Special Response Team.

Stable fields used were `sTitle`, `sContent`, `sChanId`, `iInfoId`,
`sExt.chara-name-en`, `sExt.level-icon`, `sExt.prop-icon-1`,
`sExt.prop-icon-2`, and `sExt.chara-line`. The API URLs, language, retrieval
time, locator parameters, and field paths are stored in each `sources.yaml`.

Primary fact boundary:

- Astra: public music performer/idol identity; Ether, Support, S-rank.
- Piper: vehicle expert/driver identity; Sons of Calydon relation; Physical,
  Anomaly, A-rank.
- Qingyi: Public Security officer and Criminal Investigation Special Duty
  Team relation; Electric, Stun, S-rank.

## Honest sparsity and metadata

Detailed kit abilities and mechanics were not filled from secondary sources.
No Moegirl-only fact was promoted to PRIMARY. Astra does not claim that
performance literally empowers allies. Piper does not claim a vehicle-parts
axe or vehicle maintenance. Qingyi does not claim the three-section staff,
daze loop, or specific mechanics.

Analysis metadata uses only the current vocabulary and the existing
`source_fact`, `brief`, and `analyst_derivation` provenance contract:

- Astra: `performer`, `public_performance`, `team_enabling`, and bounded
  `public_social_influence`. The authority token is explicitly analyst-derived
  from public idol/concert reach and is not formal leadership.
- Piper: `ordinary_urban_worker` and `organization_member`, with
  `ordinary_member` as a bounded analyst-derived structural precedent. This
  does not infer low authority from Caesar's leadership, nor from competence.
  The rationale records the gap between the vehicle-oriented concept and the
  existing legal worker token.
- Qingyi: `formal_professional`, `investigator`, and `organization_member`,
  with `ordinary_member` as a bounded structural interpretation and
  `formal_role_identity` as the hook. Qingyi is a formal/public institutional
  investigator precedent; Jane remains a separate covert/undercover
  investigator precedent. This is authoring analysis, not factual canon.

Personality, life stage, visual motifs, authority scope, and unsupported kit
fantasy remain absent where evidence is insufficient.

## Selector boundary

The production selector remains exactly:

- active domains: `personality`, `gameplay_fantasy`, `authority`;
- identity scoring: **DISABLED**, contribution `0`;
- non-active domains: `life_social_identity`, `authority_scope`, `hook`,
  `life_stage`, and `motif`.

No case, brief, expected semantic output, or selector implementation was
changed to favor the new records. Explainability remains selection-level only:
the benchmark can report that a reference was selected for a case, not that it
caused a generated field.

## Benchmark before/after

| Metric | Frozen v0.5 baseline | Wave 2 | Delta |
| --- | ---: | ---: | ---: |
| Corpus records | 11 | 14 | +3 |
| Unique selected | 10 | 11 | +1 |
| Average top-k overlap | 0.304545 | 0.346970 | +0.042425 |
| HHI | 0.137174 | 0.136488 | -0.000686 |
| Diagnostic cases | 12 | 12 | 0 |

The benchmark ran against the unchanged cases and production selector. The
metrics are selection diversity/concentration observations only; this report
does not claim improved model generation quality.

### New-character selection usage

| Character | Top-k appearances | Cases | Rank / legacy / feature-secondary |
| --- | ---: | --- | --- |
| Astra Yao | 1 | `case-g-expressive-performer` | 3 / 1 / 0.0 |
| Piper Wheel | 7 | `case-b-spatial-control`, `case-e-mobility-repositioning`, `case-i-youthful-ambiguous`, `case-k-charisma-low-authority`, `case-l-quiet-practical`, `contrast-personality-researcher`, `contrast-personality-magistrate` | 3 / 1 / 0.0 in each |
| Qingyi | 0 | `ZERO_SELECTION_USAGE` | — |

Qingyi remains in the corpus despite zero selection usage; the benchmark was
not modified to make her win. The expanded run still has 11 unique selected
references, and the selector's active-domain contract is unchanged.

## ZZZ concentration

| Game | Records |
| --- | ---: |
| Wuthering Waves | 4 |
| Genshin Impact | 3 |
| Zenless Zone Zero | 5 |
| Neverness to Everness | 2 |

ZZZ share is `5 / 14 = 35.7143%`: **HIGH BUT ACCEPTED**. Subsequent
expansion should prefer non-ZZZ candidates unless a new ZZZ candidate closes
an irreplaceable gap.

## Remaining gaps

- `community_embedded_local`: unresolved;
- `itinerant_traveler`: unresolved;
- `non_career_identity`: unresolved;
- detailed PRIMARY kit text for the three new records: intentionally sparse;
- authority boundary evidence remains partial for ordinary members.

## HOLD pool

- Corin: `DESIGN_APPROVED / HOLD`;
- Mint: `PLAYABILITY / GAMEPLAY HOLD`;
- Lumi: `GAMEPLAY PRIMARY HOLD`;
- Chiz: `PLAYABILITY HOLD`;
- Ayla: `SOURCE HOLD`.

## Source-policy reminder

`SECONDARY_HOST_FIRST_PARTY_TEXT != PRIMARY`. A secondary wiki, database, or
guide remains secondary even when it reproduces official text verbatim. New
production facts must resolve to an official site, official API, official CDN
mapped to a canonical official page, or official article/profile source.
