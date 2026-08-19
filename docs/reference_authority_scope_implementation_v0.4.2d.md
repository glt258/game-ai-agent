# Reference Selector v0.4.2d
# Authority Scope Implementation

Status: **READY_FOR_REVIEW**

This implementation adds the approved authoring representation only. Production
selector scoring remains disabled; the frozen 18-case benchmark and the frozen
12 diagnostic briefs are unchanged.

## Approved representation

The existing `authority` field remains the authority form/relationship signal:

- `formal_leadership`;
- `operational_responsibility`;
- other existing authority values.

The optional scalar `authority_scope` field is orthogonal to `authority` and
has exactly three canonical values:

| Value | Meaning |
| --- | --- |
| `private_group` | Real leadership over a small private or independent group. |
| `institutional` | Real authority bounded to an organization, institution, collective governance structure, department, or organizational executive context. This intentionally covers portfolio/collective governance and organizational/custodial executive authority at the same reach level. |
| `state_scale` | Public governance reaching city, regional, national, sovereign, or equivalent scale. |

Portfolio/collective governance and organizational/custodial executive
authority are not separate tokens. Their split remains deferred until corpus
expansion demonstrates selector confusion that adjacent authoring features
cannot resolve.

Missing scope is represented by absence/`None` and means **UNKNOWN / NO SCORE
EVIDENCE**. It is not a default small, ordinary, institutional, or low-authority
value.

Temporal/effective concepts remain out of scope. `former`, `nominal`,
`ceremonial`, `interrupted`, `restored`, `effective`, `ineffective`, and
`confined` remain orthogonal provenance/analysis notes rather than scope
tokens.

## Schema and normalized profile

`AuthoringFeatureBlock` now accepts:

```yaml
authority: [formal_leadership]
authority_scope: state_scale
```

`authority_scope` is optional, validated against the exact canonical domain,
and remains separate from `authority`. Normalized
`DiagnosticFeatureProfile` values expose it as a deterministic tuple, matching
the existing profile representation:

```python
profile.authority == ("formal_leadership",)
profile.authority_scope == ("state_scale",)
```

The diagnostic vocabulary version is
`reference-feature-vocabulary/0.4.2d`.

## Deterministic brief extraction

Extraction is bounded lexical normalization only. It uses no LLM, embedding,
free-text semantic score, or general-purpose negation parser.

Positive extraction requires explicit authority-reach context:

- `private_group`: `small private team`, `small independent team`, `tiny
  independent crew`, `small private agency`, or equivalent bounded phrases;
- `institutional`: `formal organization executive`, `institutional leadership`,
  `governing portfolio`, `portfolio within a council`, `department leadership`,
  or explicit custodial/organizational executive language;
- `state_scale`: `governs the city`, `city-state institution`, `broad public
  responsibilities`, `head of state`, `national governance`, `regional public
  governance`, or `sole governing authority`.

Conservative guards include:

- `team`, `group`, `agency`, `organization`, `member`, `official`, and
  `magistrate` alone do not assign scope;
- organization membership alone does not assign `institutional`;
- title-only `magistrate` does not assign `state_scale`;
- explicit bounded negative phrases such as `no state or government office`
  and `no government authority` suppress state-scale extraction;
- explicit state-scale phrases take precedence over institutional phrases;
- institutional context takes precedence over a generic small-department
  phrase;
- ambiguous or conflicting scope evidence returns missing scope.

## Approved Same-10 migration

Exactly five production `analysis.yaml` records gained the optional field.
Every value uses an existing source ID and existing `narrative` fact path; no
facts or sources were changed.

| Character | Authority form | Authority scope | Existing provenance basis |
| --- | --- | --- | --- |
| Nicole | `formal_leadership` | `private_group` | `official-character-page-en`, `narrative` |
| Keqing | `formal_leadership` | `institutional` | `official-character-page`, `narrative` |
| Nahida | `formal_leadership` | `state_scale` | `official-character-page`, `narrative` |
| Jinhsi | `formal_leadership` | `state_scale` | `official-introduction`, `narrative` |
| Shorekeeper | `formal_leadership` | `institutional` | `official-profile-reveal`, `narrative` |

Scope remains absent for:

- Furina;
- Mortefi;
- Jane;
- Fadia;
- Shinku.

Coverage: **5/10**.

The migration does not infer scope for operational expertise, consultant or
operative responsibility, organization membership, enforcer responsibility,
or Furina's historical/public-performance role.

## Diagnostic before/after

Before v0.4.2d classification counts:

```text
VOCABULARY_REPRESENTATION_GAP: 2
MULTI_REFERENCE_COLLISION: 4
CORPUS_COVERAGE_GAP: 3
PASS_CURRENT_REPRESENTATION: 2
EXPECTED_SHARED_TRAIT: 1
BRIEF_EXTRACTION_GAP: 0
```

After v0.4.2d classification counts are unchanged:

```text
VOCABULARY_REPRESENTATION_GAP: 2
MULTI_REFERENCE_COLLISION: 4
CORPUS_COVERAGE_GAP: 3
PASS_CURRENT_REPRESENTATION: 2
EXPECTED_SHARED_TRAIT: 1
BRIEF_EXTRACTION_GAP: 0
```

Changed diagnostic classifications: **NONE**. The representation improved
without pretending that a shadow distinction is a production selector result.

The intended authority distinctions now appear in the non-scoring shadow
representation:

| Pair | Scope representation after implementation | Result |
| --- | --- | --- |
| Small private team vs city/state institution | `private_group` vs `state_scale` | Distinguishable |
| Portfolio/council governance vs sovereign authority | `institutional` vs `state_scale` | Distinguishable |
| Operational member vs formal organization leader | missing vs `institutional` | Existing form distinction retained |
| Custodial executive vs field enforcer | `institutional` vs missing | Existing form distinction retained |

Remaining intentional collisions include `state_scale` between Nahida/Jinhsi
and `institutional` between Keqing/Shorekeeper. These are shared scope
semantics; adjacent personality, hook, fantasy, and identity features remain
responsible for further distinction.

Shadow overlap remains `non_scoring: true`. No shadow top match is treated as a
production-selected reference.

## Frozen core and production invariants

The frozen core remains unchanged:

- cases: 18;
- unique: 8;
- overlap: `0.448485`;
- HHI: `0.159808`;
- classification: `LIMITED_SENSITIVITY`;
- ranking parity: `PASS`;
- changed core top-k cases: `NONE`;
- order: `ORDER_INDEPENDENT`.

Production authoring-feature score contribution remains exactly `0`. Ranking
logic, tie-breaks, selector behavior, and scoring weights were not changed.

## Validation

- focused authority-scope tests: `14 passed`;
- feature and diagnostic regression tests: `34 passed`;
- full test suite: `701 passed, 1 skipped`;
- `git diff --check`: PASS.

## Deferred items

- temporal/effective authority modeling;
- Furina `authority_scope`;
- operational-responsibility sub-scopes;
- institutional subtype split;
- hook vocabulary revision;
- personality vocabulary revision;
- identity vocabulary revision and corpus expansion.

No character was added. The production corpus remains exactly 10 records.
