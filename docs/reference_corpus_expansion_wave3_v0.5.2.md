# Reference Corpus Production Expansion Wave 3 — v0.5.2

Status: **FROZEN**

Wave 3 adds the MIMO-approved `ADD_2` set to the production reference
corpus:

| Character | Game | Official record | Production precedent |
| --- | --- | ---: | --- |
| Vita | Honkai Impact 3rd | `iInfoId=126475` | interplanetary itinerancy / sparse native gameplay taxonomy |
| Songque | Honkai Impact 3rd | `iInfoId=124932` | non-career-centered social identity / hope-producing deception |

No runtime component, selector implementation, schema, or vocabulary was
changed. Li Sushang and Senadina remain outside production ingestion.

## HI3 source recovery summary

The validated official source family is HoYoverse `content_v2` for the HI3
global app:

- `iAppId=35`;
- `appSn=5fcd2aa439ca4aea`;
- GET list pagination with `iPage` and `iPageSize`;
- language parameter `sLangKey`;
- role roster channel `iChanId=767` for the persisted Vita and Songque
  records;
- the recovered channel family also includes `520` (`ROLES.VALKYRIES`) and
  `521` (`ROLES.ROLE`).

The source locator is the official
`sg-public-api-static.hoyoverse.com/content_v2_user/app/...` endpoint. The
persisted PRIMARY records use the exact official `iInfoId` selectors and
stable `sExt` fields from channel 767. Official fastcdn URLs appear in the
API payload but are not needed as independent evidence for the sparse facts
stored here. No Wiki, Moegirl, Fandom, or third-party database fact was
promoted.

## ADD_2 rationale

Vita and Songque were selected after HI3 source-access recovery, production
candidate research, and MIMO semantic shortlist review. They add the fifth
formal IP to the corpus while covering distinct semantic gaps:

- Vita provides the source-grounded pattern of a lone survivor wandering
  through the universe and traveling from planet to planet. The canonical
  `itinerant_traveler` value is an authoring interpretation of that source
  pattern, not a quoted official label.
- Songque provides deceptive persona, hope-producing social action, and a
  personal promise toward the people of Langqiu. The canonical
  `non_career_identity` value is an authoring interpretation because the
  relevant role text does not state a profession or formal title.

## PRIMARY source integrity

Both records pass the three production gates:

| Record | Identity PRIMARY | Playable PRIMARY | Gameplay PRIMARY |
| --- | --- | --- | --- |
| Vita | PASS | PASS | PASS |
| Songque | PASS | PASS | PASS |

Gameplay facts remain intentionally sparse. Vita stores Lightning, Mecha,
Drive Core, Lone Planetfarer, and Rite of Oblivion. Songque stores Physical,
Stardust, Trick Staff, Jovial Deception: Shadowdimmer, and Wheel of Destiny.
No full kit was copied into the corpus, and no unsupported mechanic such as
illusion, doppelganger, or deception combat was promoted.

The records also preserve the following boundaries:

- Vita does not claim low authority from the absence of a leadership title or
  organization.
- Songque does not claim `community_embedded_local`; Langqiu evidence is
  regional loyalty and a promise, not a small-scale reciprocal local network.
- No life stage is inferred from appearance, body type, tone, or archetype.
- Metadata provenance uses only `source_fact` and `analyst_derivation`.

## MIMO semantic decision

| Gap concept | Wave 3 result | Record | Provenance boundary |
| --- | --- | --- | --- |
| `itinerant_traveler` | COVERED | Vita | source-backed wandering pattern → analyst derivation |
| `non_career_identity` | COVERED | Songque | source-backed role framing → analyst derivation |
| `community_embedded_local` | UNCOVERED | — | no token claimed |

These are corpus semantic coverage outcomes, not selector active-feature
coverage outcomes.

## Corpus and IP distribution

The corpus grows from 14 to 16 records:

| IP | Records | Share |
| --- | ---: | ---: |
| Zenless Zone Zero | 5 | 31.25% |
| Wuthering Waves | 4 | 25.00% |
| Genshin Impact | 3 | 18.75% |
| Neverness to Everness | 2 | 12.50% |
| Honkai Impact 3rd | 2 | 12.50% |

HI3 is now the fifth formal IP. This documents improved IP diversity only;
it does not claim improved generation quality.

## Selector boundary and benchmark

The production selector remains frozen with active domains:

- `personality`
- `gameplay_fantasy`
- `authority`

Identity scoring remains **DISABLED**. `life_social_identity`,
`authority_scope`, `hook`, `life_stage`, and `motif` remain inactive. The
benchmark cases, briefs, expected references, selector weights, and active
domains were not changed.

The same formal selector benchmark was rerun against the expanded corpus:

| Metric | Before (14) | After (16) | Delta |
| --- | ---: | ---: | ---: |
| Unique selected | 11 | 11 | 0 |
| Average top-k overlap | 0.346970 | 0.346970 | 0.000000 |
| HHI | 0.136488 | 0.136488 | 0.000000 |

The unchanged metrics are selection observations only. They are not a model
quality claim.

### New-character usage

| Character | Top-k appearances | Cases | Rank observations | Legacy scores | Feature-secondary scores |
| --- | ---: | --- | --- | --- | --- |
| Vita | 0 | `ZERO_SELECTION_USAGE` | ranks 6–14 across the 18 unchanged cases | 1 in `case-j-informal-social-role`, otherwise 0 | 0.0 in every case |
| Songque | 0 | `ZERO_SELECTION_USAGE` | ranks 5–13 across the 18 unchanged cases | 1 in `case-j-informal-social-role`, otherwise 0 | 0.0 in every case |

This is recorded as `SELECTOR_OBSERVABILITY_LIMIT`: the new records' primary
authoring value is concentrated in life/social identity dimensions that the
active selector does not score. No selector change was made. Explainability
remains selection-level only; this report does not attribute generated fields
to either reference.

## HOLD pool

- Li Sushang: OPTIONAL / HOLD; same-slot-different-flavor versus Vita.
- Senadina: HOLD; thin non-career adventure framing.
- Mint: HOLD; NTE gameplay PRIMARY gap.
- Zero: HOLD; NTE gameplay PRIMARY gap.
- Hathor: HOLD; NTE gameplay PRIMARY gap.
- Corin: HOLD; ZZZ concentration / redundancy.

## Validation and final decision

The Wave 3 validation set covers reference corpus loading and validation,
source/provenance validation, metadata validation, the unchanged formal
selector benchmark, the full pytest suite, and `git diff --check`. Protected
files `IDEA.md` and `manual_character_test.py` remain unmodified and
untracked.

Final decision: **FROZEN**.
