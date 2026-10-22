# Reference Selector v0.4.2b
# Feature Discrimination Diagnostic Benchmark Report

Status: **READY_FOR_MINIMAL_VOCAB_REVISION**

This report has two deliberately separate suites:

1. the immutable 18-case frozen core benchmark; and
2. a 12-case diagnostic extension for feature discrimination.

The extension never changes production selector scoring, ranking, or the core
benchmark metrics. It has no expected character winners.

## Frozen Core

The Reference Selection Quality Benchmark v0.4 remains immutable:

- Cases: **18**
- Unique selected: **8**
- Average overlap: **0.448485**
- HHI: **0.159808**
- Classification: `LIMITED_SENSITIVITY`
- Ranking parity: **PASS**
- Changed core cases: **NONE**
- Order: `ORDER_INDEPENDENT`
- Authoring feature score contribution: **0**

The original benchmark case definitions and production selector source were
not edited. The extension lives in
`src/agents/reference_feature_discrimination_diagnostic.py`.

## Diagnostic Extension

- Cases: **12**
- Counterfactual pairs: **6**
- Authority-focused cases: **8**
- Hook-focused cases: **4**
- Identity/organization separation cases: **2**
- Personality-focused cases: **4**
- Motif cases: **0**
- Life-stage cases: **0**
- Feature score contribution: **0**

The family counts overlap because secondary dimensions are intentionally
recorded on each case. Cases are authoring requirements, not character-name
proxies. The suite contains no expected reference winner.

Reference matchability means an exact subset match across every non-empty
expected feature domain. Shadow overlap is a diagnostic count of shared
canonical features and domains; its top matches are never selected references.

## Case Design

Every case records its purpose, primary and secondary dimensions,
counterfactual partner, expected deterministic features, held-constant
features, failure meaning, and classification in the runnable module.

### Authority scope and form

#### `authority-scope-small-private-team`

Brief: “A practical professional whose formal leadership covers a small
private team and a few direct reports, with no state or government office.”

Expected/extracted features: `personality: practical`,
`life_social_identity: formal_professional`,
`authority: formal_leadership`.

Partner: `authority-scope-state-institution`.

Matchability: `0_MATCHES`. Top diagnostic matches are Keqing, Nahida,
Jinhsi, Mortefi, Shorekeeper, and Nicole in a six-way score tie at 2 shared
features / 2 domains. Zero-overlap references: Furina and Fadia.

Classification: `MULTI_REFERENCE_COLLISION`. The private-team scope is not
represented by the current authority token.

#### `authority-scope-state-institution`

Brief: “A practical professional whose formal leadership covers a city-state
institution and its broad public responsibilities.”

Expected/extracted features are identical to the partner. Matchability is
`0_MATCHES`; the same six-way top diagnostic tie occurs, with Furina and Fadia
at zero overlap.

Classification: `MULTI_REFERENCE_COLLISION`. State-scale scope is not
represented by the current authority token.

#### `authority-form-portfolio-governance`

Brief: “A restrained professional whose formal leadership is a governing seat
and portfolio within a council, sharing decisions rather than ruling alone.”

Expected/extracted features: `restrained`, `formal_professional`,
`formal_leadership`.

Partner: `authority-form-sovereign`.

Matchability: `MULTIPLE_MATCHES`: Keqing, Nahida, Jinhsi, and Shorekeeper.
They tie at 3 shared features / 3 domains. Furina and Fadia have zero overlap.

Classification: `MULTI_REFERENCE_COLLISION`.

#### `authority-form-sovereign`

Brief: “A restrained professional whose formal leadership carries broad
responsibility for a city-state institution as its sole governing authority.”

Expected/extracted features and shadow distribution are identical to the
portfolio partner.

Classification: `MULTI_REFERENCE_COLLISION`.

#### `authority-form-operational-member`

Brief: “A serious practical specialist who is an organization member with
operational responsibility for field execution, but has no command authority.”

Expected/extracted features: `serious`, `practical`,
`organization_member`, `operational_responsibility`.

Partner: `authority-form-formal-organization-leader`.

Matchability: `0_MATCHES`. Mortefi is the top diagnostic match at 3 shared
features / 2 domains; Fadia is next at 2 / 2. Five references have zero
overlap.

Classification: `CORPUS_COVERAGE_GAP`. The representation distinguishes the
requested member/operational role, but no current reference contains the full
combination.

#### `authority-form-formal-organization-leader`

Brief: “A serious practical specialist who has formal leadership within an
organization and command responsibility for field execution.”

Expected/extracted features: `serious`, `practical`,
`formal_leadership`.

Matchability: `0_MATCHES`. Nicole is the top diagnostic match at 2 shared
features / 2 domains; Mortefi is next at 2 / 1. Three references have zero
overlap.

Classification: `CORPUS_COVERAGE_GAP`.

#### `authority-form-custodial-executive`

Brief: “A restrained socially isolated professional with formal leadership and
protective stabilization, responsible for quiet custodial system
maintenance.”

Partner: `authority-form-field-enforcer`.

Expected/extracted features: `restrained`, `socially_isolated`,
`formal_professional`, `formal_leadership`, `protective_stabilization`.

Matchability: `1_MATCH`, Shorekeeper. It is the top diagnostic match at 5
shared features / 4 domains; Nahida and Shinku follow at 4 / 3. Furina and
Fadia have zero overlap.

Classification: `PASS_CURRENT_REPRESENTATION`.

#### `authority-form-field-enforcer`

Brief: “A restrained socially isolated professional with operational
responsibility and protective stabilization, responsible for quiet frontline
enforcement without command.”

Expected/extracted features: `restrained`, `socially_isolated`,
`formal_professional`, `operational_responsibility`,
`protective_stabilization`, `direct_frontline_pressure`.

Matchability: `1_MATCH`, Shinku. It is the top diagnostic match at 6 shared
features / 4 domains; Shorekeeper and Jane Doe follow at 4 / 3. Furina and
Nicole have zero overlap.

Classification: `PASS_CURRENT_REPRESENTATION`.

### Hook contrast

#### `hook-contrast-theatrical-mask`

Brief: “An expressive public performer whose public performance and theatrical
confidence conceal insecurity and a guarded private self.”

Expected/extracted features: `expressive`, `guarded`, `performer`,
`public_performance` surface and behavioral hook values.

Partner: `hook-contrast-playful-danger`.

Matchability: `0_MATCHES`. Furina is the top diagnostic match at 4 shared
features / 3 domains; Nicole follows at 2 / 2. Six references have zero
overlap.

Classification: `VOCABULARY_REPRESENTATION_GAP`. The current representation
captures performance and guardedness but has no contrast for performance as a
vulnerability mask.

#### `hook-contrast-playful-danger`

Brief: “An expressive playful public performer whose public performance and
teasing surface carry real danger in open view, not hidden competence.”

Expected/extracted features: `expressive`, `playful`, `performer`,
`public_performance` surface and behavioral hook values.

Matchability: `0_MATCHES`. Furina is the top diagnostic match at 3 shared
features / 3 domains; Fadia and Nicole follow at 2 / 2. Seven references have
zero overlap.

Classification: `VOCABULARY_REPRESENTATION_GAP`. The current representation
captures playfulness and performance but has no contrast for visible danger.

#### `hook-contrast-disciplined-official`

Brief: “A restrained disciplined professional governing official with personal
combat presence and practical field decisions.”

Partner: `hook-contrast-hope-composure`.

Expected/extracted features: `restrained`, `practical`, `disciplined`,
`formal_professional`, `formal_leadership`, `formal_role_identity`, and
`formal_role_personal_action`.

Matchability: `0_MATCHES`. Keqing is the top diagnostic match at 6 shared
features / 5 domains; Jinhsi follows at 5 / 5. Furina and Fadia have zero
overlap.

Classification: `CORPUS_COVERAGE_GAP`. Existing features represent the
distinction, but no current reference has the complete requested combination.

#### `hook-contrast-hope-composure`

Brief: “A restrained idealistic professional governing official who maintains
public hope through symbolic composure and institutional duty.”

Expected/extracted features: `restrained`, `idealistic`,
`formal_professional`, `formal_leadership`, and `formal_role_identity`.

Matchability: `MULTIPLE_MATCHES`: Nahida and Jinhsi tie at 5 shared features /
4 domains. Keqing follows at 4 / 4. Furina and Fadia have zero overlap.

Classification: `EXPECTED_SHARED_TRAIT`. The pair is intentionally close,
but the existing idealistic versus disciplined/practical and hook features
provide a deterministic difference.

## Failure Summary

| Classification | Count |
|---|---:|
| `PASS_CURRENT_REPRESENTATION` | 2 |
| `BRIEF_EXTRACTION_GAP` | 0 |
| `VOCABULARY_REPRESENTATION_GAP` | 2 |
| `CORPUS_COVERAGE_GAP` | 3 |
| `MULTI_REFERENCE_COLLISION` | 4 |
| `EXPECTED_SHARED_TRAIT` | 1 |

No case has an expected winner. All extracted features exactly match the
case-declared deterministic expectations.

## Authority Findings

The four scope/form cases are repeatable representation failures:

1. small private-team leadership and city/state leadership extract the same
   `practical + formal_professional + formal_leadership` profile;
2. portfolio governance and sole sovereignty extract the same
   `restrained + formal_professional + formal_leadership` profile.

This satisfies the authority revision gate: the briefs clearly express
different authority scopes, and current extraction maps each pair to the same
authority signal while adjacent features are held constant. The operational
member versus formal organization leader pair is representable, but the
current corpus lacks exact full-profile references. The custodial executive
versus field-enforcer pair is already discriminated by authority and fantasy.

Evidence for a future minimal authority revision: **YES**.

Recommended design direction: preserve broad `formal_leadership` for backwards
compatibility and investigate a small optional orthogonal authority-scope
representation. Do not split the token or change schema in this task.

## Hook Findings

The theatrical-mask and playful-danger cases both extract existing surface,
behavioral, and personality signals, but no current hook contrast represents
their requested semantic difference. They produce two repeatable
`VOCABULARY_REPRESENTATION_GAP` results and have plausible multi-reference
future applicability through the current public-performance, guarded, and
playful reference patterns.

However, the two gaps are not yet one stable reusable category. No exact hook
token name is proposed. More semantic design is required before adding a
contrast token.

The disciplined-official versus hope-composure pair is already separated by
existing personality and formal-role features; the no-match result is a corpus
coverage gap, not a hook extraction failure.

Evidence for immediate hook token revision: **NO**.

## Identity Findings

The organization-member versus formal-organization-leader cases extract
different existing identity/authority signals. Their exact matchability is
zero because the current ten references do not contain the complete requested
personality-plus-role combinations.

This is `CORPUS_COVERAGE_GAP`, not a vocabulary failure. Organization
membership is useful when contrasted with leadership or operational
responsibility, but one current reference and no prior core brief are not
enough to justify a new identity taxonomy.

Evidence for identity vocabulary revision: **NO**.

## Personality Findings

The extension uses personality only as a controlled held-constant or
secondary discriminator. The official-role pair separates restrained,
disciplined/practical execution from restrained, idealistic composure using
existing tokens. No split of `restrained` is supported.

Evidence for personality vocabulary revision: **NO**.

## Minimal Revision Evidence

| Domain | Evidence now? | Decision |
|---|---|---|
| Authority | YES | Begin a minimal orthogonal authority-scope design review; do not implement yet |
| Hook | NO | Keep current tokens; conduct further semantic design first |
| Personality | NO | Keep `restrained` unchanged |
| Identity | NO | Expand corpus before vocabulary changes |

New canonical tokens in this task: **0**. No schema, vocabulary, alias,
production record, selector, core benchmark, generation, Canon, or Repair
change is part of this extension.

## Production Invariant and Validation

The extension is shadow-only:

- Feature score contribution: **0**
- Production selector changed: **NO**
- Frozen core unique: **8**
- Frozen core overlap: **0.448485**
- Frozen core HHI: **0.159808**
- Frozen core classification: `LIMITED_SENSITIVITY`
- Core ranking parity: **PASS**
- Changed core cases: **NONE**
- Core order: `ORDER_INDEPENDENT`

Focused diagnostic tests: **5 passed**.

Full regression: **687 passed, 1 skipped**.

## Recommendation

**READY_FOR_MINIMAL_VOCAB_REVISION**

The extension establishes a specific, repeatable authority-scope
representation failure without changing production behavior. The next task
may design—but should still separately review—a minimal orthogonal authority
scope vocabulary. Hook gaps require more semantic design, and identity gaps
require corpus expansion. The frozen 18-case core remains permanently
unchanged and must continue to be reported separately.
