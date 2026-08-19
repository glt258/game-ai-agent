# Reference Authority Scope v0.4.2d
# Freeze Baseline

Status: **FROZEN**

This is a representation baseline.

**It does not enable `authority_scope` or any other authoring feature in
production reference scoring.** The production authoring-feature score
contribution remains `0`.

## Approved design

The v0.4.2c MIMO-approved architecture is implemented without changing the
existing authority form vocabulary. `authority_scope` is one optional,
orthogonal authoring-feature domain.

Canonical values are exactly:

- `private_group`;
- `institutional`;
- `state_scale`.

Missing scope is optional and neutral:

```text
UNKNOWN / NO SCORE EVIDENCE
```

Missing scope is not inferred as low authority, private-group authority,
ordinary membership, or institutional authority.

## MIMO decision summary

MIMO approved the v0.4.2c design with `APPROVE_WITH_MINIMAL_CHANGE`. The
approved architecture keeps `formal_leadership` as the shared authority-form
signal and adds the one scalar `authority_scope` field.

`institutional` intentionally covers portfolio/collective governance and
organizational/custodial executive authority at the same modeled reach level.
Those are not separate scope tokens in v0.4.2d. A subtype split requires future
corpus evidence of selector confusion that adjacent authoring features cannot
resolve.

Temporal/effective authority is not structuralized. `former`, `nominal`,
`ceremonial`, `interrupted`, `restored`, `effective`, `ineffective`, and
`confined` remain orthogonal provenance or analysis notes.

## Production migration

Exactly five of ten production records have the optional field:

| Character | Authority form | Authority scope |
| --- | --- | --- |
| Nicole | `formal_leadership` | `private_group` |
| Keqing | `formal_leadership` | `institutional` |
| Nahida | `formal_leadership` | `state_scale` |
| Jinhsi | `formal_leadership` | `state_scale` |
| Shorekeeper | `formal_leadership` | `institutional` |

Scope remains absent for Furina, Mortefi, Jane, Fadia, and Shinku. Coverage is
**5/10**. No automatic inference was added for those records.

Every migrated value uses existing production source evidence and an existing
`narrative` fact path. Provenance validation reports zero invalid source IDs
and zero invalid fact paths. Facts and sources are unchanged.

## Deterministic brief extraction

Brief extraction is bounded lexical normalization. It uses no LLMs, embeddings,
or free-text semantic scoring.

- `private_group` requires explicit small/private leadership context such as
  `small private team`, `tiny independent crew`, `small private agency`, or
  `leads a few members`;
- `institutional` requires explicit organization/institution governance or
  executive context such as `formal organization executive`, `governing
  portfolio`, `department leadership`, or custodial system maintenance;
- `state_scale` requires explicit public-governance reach such as `governs the
  city`, `city-state institution`, `broad public responsibilities`, `head of
  state`, or `national governance`.

False-positive guards pass:

- organization membership alone does not imply `institutional`;
- title-only `magistrate` does not imply `state_scale`;
- generic `team`, `group`, `agency`, or `official` does not imply scope;
- bounded negative phrases such as `no state or government office` suppress
  state-scale extraction;
- no additional scope/status token was introduced.

## Diagnostic representation snapshot

The non-production shadow representation now distinguishes the intended
authority-scope counterfactuals:

| Counterfactual | Representation |
| --- | --- |
| Small-private leadership vs state-scale governance | `private_group` vs `state_scale` |
| Institutional/portfolio governance vs sovereign authority | `institutional` vs `state_scale` |

The v0.4.2d diagnostic classification totals remain unchanged:

```text
VOCABULARY_REPRESENTATION_GAP: 2
MULTI_REFERENCE_COLLISION: 4
CORPUS_COVERAGE_GAP: 3
PASS_CURRENT_REPRESENTATION: 2
EXPECTED_SHARED_TRAIT: 1
BRIEF_EXTRACTION_GAP: 0
```

This does not invalidate the representation improvement. The new scope
distinctions are visible in the diagnostic shadow layer; classification totals
are broader failure labels and are not production selector results. Shadow
matching remains non-production and non-scoring.

## Frozen core invariant

The original 18-case core remains immutable and unchanged:

- cases: `18`;
- unique: `8`;
- overlap: `0.448485`;
- HHI: `0.159808`;
- classification: `LIMITED_SENSITIVITY`;
- ranking parity: `PASS`;
- changed cases: `NONE`;
- order: `ORDER_INDEPENDENT`.

Production selector ranking logic and tie-breaking remain unchanged.

## Validation

- focused authority-scope tests: `14 passed`;
- feature and diagnostic regression tests: `34 passed`;
- full suite: `701 passed, 1 skipped`;
- `git diff --check`: `PASS`;
- authoring-feature score contribution: `0`.

## Deferred items

| Item | Status |
| --- | --- |
| Temporal/effective authority | DEFERRED |
| Furina scope | DEFERRED |
| Operational sub-scopes | DEFERRED |
| Institutional subtype split | DEFERRED |
| Hook revision | DEFERRED |
| Personality revision | DEFERRED |
| Identity vocabulary | NO REVISION |
| Identity corpus expansion | LATER |

No characters were added. Generation, Canon, Repair, selector ranking, and
production scoring remain unchanged.

## Next phase

**FEATURE SCORING ACTIVATION**
