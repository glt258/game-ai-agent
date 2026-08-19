# Reference Selector v0.4.2c
# Authority Scope Minimal Representation Design

Status: **APPROVED_FOR_IMPLEMENTATION**

This document is a design review artifact only. It does not change the
production vocabulary, schema, records, selector, scoring, diagnostic cases,
Generation, Canon, Repair, or corpus.

## Decision summary

Recommendation: **ORTHOGONAL_SCOPE_RECOMMENDED**

MIMO review: **APPROVE_WITH_MINIMAL_CHANGE**. This finalization adds one
documentation-only clarification to the `institutional` scope description;
the architecture and canonical vocabulary are unchanged.

Keep the existing authority form as the shared signal and add one optional,
scalar `authority_scope` domain beside it. The smallest useful domain has
three canonical values:

| Canonical value | Meaning |
| --- | --- |
| `private_group` | Leadership reach limited to a small private team, crew, or agency. |
| `institutional` | Authority bounded by an organization or institution, including a council portfolio or custodial executive role. |
| `state_scale` | Broad public governance at city, state, or sovereign scale. |

Missing `authority_scope` means **UNKNOWN / NO SCORE EVIDENCE**. It does not
mean `private_group`, low authority, ordinary membership, or a smaller reach.

The design deliberately keeps Keqing's council/portfolio distinction and
Shorekeeper's custodial executive distinction in provenance notes rather than
creating two more scope tokens. Those are reusable analytical subpatterns, but
the current evidence does not require them as separate canonical values.

## Frozen evidence and design boundary

The current frozen baseline is:

- production corpus: 10 records;
- frozen core: 18 cases, 8 unique, overlap `0.448485`, HHI `0.159808`;
- core classification: `LIMITED_SENSITIVITY`;
- ranking parity: `PASS`;
- core order: `ORDER_INDEPENDENT`;
- diagnostic extension: 12 cases and 6 counterfactual pairs;
- authority revision evidence: **YES**;
- hook revision evidence: **NO**;
- personality revision evidence: **NO**;
- identity: **CORPUS EXPANSION REQUIRED**.

The authority evidence is not reopened here. The design question is whether
the minimum architecture-correct representation is a token split, an
orthogonal axis, or a structured profile.

The actual production metadata matters for one edge case: Furina currently has
an empty authoring `authority` list, and her facts record has no occupation or
public identity. Her public-performance analysis does not authorize inventing
an active state-governance token. This document therefore keeps Furina's scope
unknown and records the nominal/former/performative issue as provenance.

## Semantic axes

### Authority form

Authority form describes the relationship that exists:

- `formal_leadership`: a formal leadership or governing relationship;
- `operational_responsibility`: assigned execution or professional
  responsibility without inferred command;
- other existing authority values remain unchanged.

The existing form vocabulary remains the shared leadership signal. A form
token must not silently acquire scale semantics.

### Authority scope

Authority scope describes the reach of a supported authority relationship:

- `private_group`: small private-group leadership;
- `institutional`: bounded organization/institutional authority. It
  intentionally covers multiple governance/executive subpatterns at the same
  authority reach level, including portfolio/collective governance and
  organizational/custodial executive authority. These are not separate scope
  tokens in v0.4.2c. Revisit the distinction only if future corpus expansion
  demonstrates selector confusion between these subtypes that adjacent
  authoring features cannot resolve;
- `state_scale`: city/state/sovereign public governance.

Scope is an optional single axis, not a list of every organization, title, or
historical role. It is intentionally a bounded semantic category and does not
encode exact headcount, named game factions, or game-specific titles.

### Temporal and effective status

Temporal/effective status is not part of v0.4.2c. `former`, `nominal`,
`interrupted`, and `restored` describe when or how fully authority was
exercisable; they do not describe its reach.

Furina's nominal/former/performative authority and Nahida's confinement and
restoration remain in source provenance and analyst notes. A future status axis
would require a separate diagnostic showing that temporal/effective status is
needed for authoring discrimination. The current 12 cases do not establish
that need.

## Option comparison

### Option A — Split the current authority tokens

Conceptual replacements for `formal_leadership` would include small-group,
portfolio/institutional, custodial executive, and state-scale leadership
tokens.

Strengths:

- direct surface semantics;
- simple pairwise token comparison once every record is migrated.

Costs:

- breaks the useful shared `formal_leadership` signal;
- forces the authority form and authority scope into one vocabulary;
- requires broad migration of existing records and brief aliases;
- encourages one token per observed title or organization;
- has no clean place for missing scope or temporal/effective status;
- risks making `operational_responsibility` acquire accidental scope meaning.

This option would turn five current `formal_leadership` records into several
new authority forms, even though they still share the same relationship form.
It optimizes uniqueness rather than authoring-useful decomposition.

**Assessment: REJECT.**

### Option B — Orthogonal authority scope

Keep the existing authority form and add one optional `authority_scope` field.
Conceptually:

```yaml
authority: [formal_leadership]
authority_scope: state_scale
```

Strengths:

- preserves the shared leadership signal;
- separates relationship form from reach;
- distinguishes small-group leadership from state-scale governance;
- represents organizational executive authority without making it sovereign;
- gives missing values a neutral, explicit behavior;
- requires one optional field and one small bounded domain;
- permits deterministic brief extraction without LLMs or embeddings.

Costs:

- Keqing's portfolio and Shorekeeper's custodial executive remain the same
  canonical scope value and need provenance notes;
- only explicit scope language can populate the field;
- future scoring must define form/scope interaction separately.

**Assessment: RECOMMENDED.**

### Option C — Structured authority profile

Replace or wrap the current authority list with a profile such as:

```yaml
authority:
  form: formal_leadership
  scope: state_scale
```

Strengths:

- makes the semantic decomposition visually explicit;
- gives temporal/effective status a possible future home.

Costs:

- changes the shape of the existing `authority` field;
- creates migration and compatibility work for every consumer;
- is unnecessary while only one additional axis is justified;
- makes missing form/scope combinations more complex to validate;
- risks prematurely standardizing status fields that the diagnostics do not
  require.

**Assessment: REJECT for v0.4.2c.** A structured profile could be revisited
only after a second independent axis is proven necessary.

## Current 10-character representation

The following is a shadow design mapping from the current metadata and
provenance. No production records are edited.

| Character | Current form | Option A: split-token concept | Option B: orthogonal shadow representation | Option C: structured concept | Confidence / note |
| --- | --- | --- | --- | --- | --- |
| Furina | `[]` currently | No safe split assignment; nominal/former leadership would be mixed into a token | form unknown; scope unknown | form unknown; scope unknown; status remains provenance | **UNKNOWN**. Public-performance evidence is not active state-governance evidence. |
| Keqing | `formal_leadership` | `portfolio_leadership` | form `formal_leadership`; scope `institutional` | `{form: formal_leadership, scope: institutional}` | **HIGH_CONFIDENCE**. Council seat and portfolio are provenance subpattern. |
| Nahida | `formal_leadership` | `sovereign_leadership` | form `formal_leadership`; scope `state_scale` | `{form: formal_leadership, scope: state_scale}` | **HIGH_CONFIDENCE**. Confinement is a separate effective-status caveat. |
| Jinhsi | `formal_leadership` | `state_leadership` | form `formal_leadership`; scope `state_scale` | `{form: formal_leadership, scope: state_scale}` | **HIGH_CONFIDENCE**. Magistrate/head-of-state scope. |
| Nicole | `formal_leadership` | `small_group_leadership` | form `formal_leadership`; scope `private_group` | `{form: formal_leadership, scope: private_group}` | **HIGH_CONFIDENCE**. Small private-agency leadership. |
| Shorekeeper | `formal_leadership` | `custodial_executive_leadership` | form `formal_leadership`; scope `institutional` | `{form: formal_leadership, scope: institutional}` | **HIGH_CONFIDENCE**. Custodial/acting executive, not sovereign. |
| Mortefi | `operational_responsibility` | unchanged | form `operational_responsibility`; scope missing | `{form: operational_responsibility, scope: null}` | **UNKNOWN**. Expert responsibility does not imply command reach. |
| Jane | `operational_responsibility` | unchanged | form `operational_responsibility`; scope missing | `{form: operational_responsibility, scope: null}` | **UNKNOWN**. Consultant/operative scope is not command scope. |
| Fadia | `operational_responsibility` | unchanged | form `operational_responsibility`; scope missing | `{form: operational_responsibility, scope: null}` | **UNKNOWN**. Command scope is explicitly unknown. |
| Shinku | `operational_responsibility` | unchanged | form `operational_responsibility`; scope missing | `{form: operational_responsibility, scope: null}` | **UNKNOWN**. Combat-core/enforcer responsibility is not captaincy. |

### Scope assignments by migration status

If the design is later approved, only the following five records have enough
current evidence to gain the optional field:

| Status | Records | Proposed field | Reason |
| --- | --- | --- | --- |
| HIGH_CONFIDENCE | Keqing | `authority_scope: institutional` | Council seat and portfolio within institutional governance. |
| HIGH_CONFIDENCE | Nahida | `authority_scope: state_scale` | Sovereign Archon scope; effectiveness caveat stays separate. |
| HIGH_CONFIDENCE | Jinhsi | `authority_scope: state_scale` | Magistrate/head-of-state city-scale governance. |
| HIGH_CONFIDENCE | Nicole | `authority_scope: private_group` | Leader of a small private agency. |
| HIGH_CONFIDENCE | Shorekeeper | `authority_scope: institutional` | Custodial/acting executive institutional authority. |
| UNKNOWN, no migration | Furina | missing | Historical or performative public authority is not safely normalized from the current record. |
| UNKNOWN, no migration | Fadia | missing | Operational responsibility is supported; command reach is not. |
| UNKNOWN, no migration | Mortefi, Jane, Shinku | missing | Operational form alone does not provide scope evidence. |

No record with missing scope is forced into a low, small, ordinary, or
institutional category.

## Minimal brief-side extraction

This is a design contract, not an implementation. Extraction must use
normalized, bounded phrases and must return no scope when the phrase is only a
title, membership claim, or generic leadership claim.

| Canonical value | Recognizable normalized phrases | Frozen cases that trigger it | Ambiguous phrases | False-positive risk |
| --- | --- | --- | --- | --- |
| `private_group` | `small private team`; `tiny independent crew`; `small private agency`; `few direct reports` when attached to private/small leadership | `authority-scope-small-private-team` | `team`, `crew`, `group`, `direct reports`, `leader` without private/small bounds | A small department inside a large institution could be mistaken for the total authority reach. Require a private/small cue and a leadership relation. |
| `institutional` | `within an organization`; `organization leadership`; `governing seat`; `portfolio within a council`; `council governance`; `custodial system maintenance`; `organizational/custodial executive` | `authority-form-portfolio-governance`; `authority-form-formal-organization-leader`; `authority-form-custodial-executive` | `organization member`; `official`; `institution`; `maintenance`; `team` | Membership or assigned work could be mistaken for authority. `organization member` alone must never trigger scope. |
| `state_scale` | `city-state institution`; `broad public responsibilities`; `entire city`; `sole governing authority`; `sovereign` or `head-of-state` when in an explicit authority context | `authority-scope-state-institution`; `authority-form-sovereign` | `governing official`; `magistrate`; `public`; `state` in a non-governance context | Titles and public visibility can be mistaken for state reach. Require explicit public-governance semantics; state-scale matches take precedence over institutional matches. |

Extraction rules:

1. Normalize case, punctuation, hyphenation, and approved aliases.
2. Apply explicit negation before assignment; for example, `no state or
   government office` suppresses `state_scale`.
3. Match explicit `state_scale` phrases first, then `private_group`, then
   `institutional`.
4. Do not infer scope from `formal_leadership`, `governing official`,
   `organization member`, or `operational_responsibility` alone.
5. If multiple positive scopes remain after normalization, return UNKNOWN and
   retain the phrase in provenance for review rather than guessing.

The `authority-form-disciplined-official` and
`authority-form-hope-composure` cases intentionally remain UNKNOWN for scope:
`governing official` establishes form, not reach. This prevents the new axis
from turning every official into a state-scale record.

## Diagnostic pair improvement

This is a shadow comparison only. It produces no selector scores and does not
change the frozen diagnostic cases.

| Pair | Before | After proposed design | Expected distinction |
| --- | --- | --- | --- |
| `authority-scope-small-private-team` ↔ `authority-scope-state-institution` | Same: `formal_leadership` | `private_group` vs `state_scale` | **YES** |
| `authority-form-portfolio-governance` ↔ `authority-form-sovereign` | Same: `formal_leadership` | `institutional` vs `state_scale` | **YES** |
| `authority-form-operational-member` ↔ `authority-form-formal-organization-leader` | Already different: operational vs formal | missing scope vs `institutional`; existing form difference retained | **YES** |
| `authority-form-custodial-executive` ↔ `authority-form-field-enforcer` | Already different: formal vs operational | `institutional` vs missing scope; existing form difference retained | **YES** |
| `hook-contrast-theatrical-mask` ↔ `hook-contrast-playful-danger` | Same authority absence | Same scope absence | **NO; out of scope** |
| `hook-contrast-disciplined-official` ↔ `hook-contrast-hope-composure` | Same: `formal_leadership` | Both scope UNKNOWN because no reach phrase is present | **NO; correct conservative behavior** |

The new field directly improves the two currently collapsing scope pairs. The
other authority pairs already differ by authority form; the optional field
does not manufacture extra segmentation where the brief does not support it.

## Backward compatibility and schema impact

The recommended future interface is one new optional scalar field on
`AuthoringFeatureBlock`:

```yaml
authority_scope: null | private_group | institutional | state_scale
```

Design constraints for a later implementation:

- existing `authority` remains valid and unchanged;
- records without `authority_scope` remain valid;
- the field is optional and scalar because scope is one bounded axis;
- unknown/missing is represented by absence or null, not a canonical token;
- only the new field's validator and canonical vocabulary domain are needed;
- brief extraction support is diagnostic/authoring support, not free-text
  scoring;
- facts schema, `CharacterDraft`, Canon, Repair, and generation schema are not
  touched;
- no forced migration is required for unsupported records.

This is intentionally a shallow external interface with a small bounded domain:
the complexity of phrase normalization and provenance remains inside the
future extraction module, while callers learn only one optional field and its
three values. The seam is the authoring-feature normalization layer, not the
selector. The selector should remain untouched until a separate scoring review.

## Future scoring semantics

No weights are proposed.

The semantic decomposition for a future, separately approved score is:

```text
authority form overlap + authority scope overlap
```

Scope overlap is evidence only when both sides have a known scope. Missing
scope contributes no evidence and must not be treated as a mismatch or as a
default category. Scope must remain subordinate to the broader authoring
feature system; this document does not decide its relative weight against
personality, hook, or gameplay fantasy.

## Out of scope

- personality revision;
- hook revision;
- life identity revision;
- life-stage revision;
- motif revision;
- identity corpus expansion;
- new characters;
- production scoring or selector changes;
- temporal/effective status vocabulary;
- production record migration.

## Final report

REFERENCE SELECTOR v0.4.2c
AUTHORITY SCOPE MINIMAL DESIGN

Status: **APPROVED_FOR_IMPLEMENTATION**

Evidence: frozen v0.4.2b diagnostics establish authority revision evidence;
the current 12 cases specifically support small-private-group versus
state-scale separation. Current metadata also supports an institutional middle
scope for Keqing and Shorekeeper without requiring separate canonical tokens.

Option A — Split: rejected because it conflates form and scope, breaks the
shared leadership signal, and creates migration/overfitting pressure.

Option B — Orthogonal Scope: recommended because it adds one optional axis,
preserves existing form semantics, supports neutral missing values, and
improves the two direct authority-scope counterfactual pairs.

Option C — Structured Profile: rejected for now because it changes the shape
of the existing authority field before a second axis is proven necessary.

Recommended: **ORTHOGONAL_SCOPE_RECOMMENDED**

Authority Form: existing `authority` values remain the relationship-form
signal, including shared `formal_leadership` and separate
`operational_responsibility`.

New Authority Scope Domain: **YES**, as one optional scalar field.

Proposed canonical values: `private_group`, `institutional`, `state_scale`.

Temporal/effective status: provenance/analysis notes only; no third axis in
v0.4.2c.

Current 10 mapping: five high-confidence optional assignments (Keqing,
Nahida, Jinhsi, Nicole, Shorekeeper); Furina, Mortefi, Jane, Fadia, and
Shinku remain UNKNOWN without migration.

Brief extraction: deterministic normalized aliases, explicit negation, scope
precedence, and neutral unknown behavior; no LLMs or embeddings.

Diagnostic pair improvement: direct YES for small-private versus state-scale
and portfolio/institutional versus sovereign; existing form distinctions are
preserved; hook/personality cases are unchanged.

Backward compatibility: existing records and the existing authority field
remain valid; missing scope means UNKNOWN / NO SCORE EVIDENCE.

Schema impact: one optional `AuthoringFeatureBlock.authority_scope` field and
one bounded vocabulary domain in a future implementation; no facts,
CharacterDraft, Canon, Repair, generation, selector, or scoring changes.

Migration: high-confidence records only; no forced migration for Furina,
Fadia, Mortefi, Jane, or Shinku.

Future scoring semantics: form overlap plus scope overlap, with no weights
defined and no score contribution enabled.

Recommendation: **ORTHOGONAL_SCOPE_RECOMMENDED**

Design status: **APPROVED_FOR_IMPLEMENTATION**
Implementation status: **NOT IMPLEMENTED**
Commit: **NONE**
Tag: **NONE**
Push: **NONE**
