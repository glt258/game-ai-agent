# Canon Checker v0.1

## Purpose

Canon Checker validates a generated `CharacterDraft` before any human decision
to accept it as Canon:

```text
CharacterDraft + Current Canon + CharacterDesignRequest
    -> deterministic checks
    -> CanonCheckReport
    -> PASS / WARN / FAIL
```

It only reports findings. It does not repair the draft, approve a character,
write Canon, change authorization, or mutate story state.

## Architecture

```text
CharacterDesignRequest
        |
CharacterGenerationAgent
        |
CharacterDraft
        |
CanonChecker
        +-- reference integrity
        +-- Canon support validation
        +-- proposal / Canon separation
        +-- World Rules and Forbidden Patterns
        +-- faction and authority boundaries
        +-- knowledge-scope boundaries
        +-- story and relationship boundaries
        +-- request hard constraints
        |
CanonCheckReport
        |
PASS / WARN / FAIL
```

`CanonChecker` consumes the existing frozen `CharacterDraft` DTO. It reads the
same validated faction, character, Lore, case, incident, project, and story
repositories already used by runtime code. World Rules and Forbidden Patterns
come from the existing read-only authoring view. There is no second Markdown
parser and no provider dependency.

## Why no LLM judge

Character generation is probabilistic and benefits from creative variation.
Canon validation must instead be reproducible: identical input and Canon must
produce the same ordered report. v0.1 therefore uses only structured records,
stable lexical guards, and the existing polarity-aware extractive support
primitive. It never calls `AgentModel`, `LiveLLMAdapter`, OpenAI, DeepSeek, or
OpenCode Go.

This separation also means the generator's `canon_basis` is a claim to check,
not proof that the draft is correct.

## Finding model

Every `CanonFinding` contains:

- `code`: stable `CanonFindingCode` enum value.
- `severity`: `info`, `warning`, or `error`.
- `field_path`: the precise draft or request field that needs review.
- `evidence_ids`: existing Canon source IDs supporting the check.
- `message`: deterministic template output, never LLM-written prose.

Findings are deduplicated by code, field path, and evidence IDs. They are
ordered by severity, field path, code, evidence, and message.

`CanonCheckSummary` counts errors, warnings, and infos. Report status is derived
without judgment calls:

```text
one or more errors   -> FAIL
no errors + warning  -> WARN
otherwise            -> PASS
```

## Implemented deterministic rules

### Reference integrity

Validates faction, Canon basis, story/case/incident links, and relationship
targets against their real registries. A source ID with the wrong declared
type is also invalid. Unknown references do not cascade into faction or story
semantic findings.

### Canon support

Checks every non-generic `canon_basis.supports` value against the cited source.
The check reuses Grounding v0.3's normalization and negative-polarity guard, so
a Canon statement such as “not an independent administrative body” cannot
support the positive claim “independent administrative body.” Structured
faction-role conflicts also invalidate an occupation support claim.

### Proposal / Canon separation

Compares explicit `new_design_elements` and `proposed_new_content` with
`background`, `story_hook`, and `design_pitch`. A proposed named activity or
outcome repeated as an accomplished fact produces
`PROPOSAL_PRESENTED_AS_CANON` with warning severity. New names, personalities,
personal histories, and ability expressions are otherwise allowed.

### World Rules and Forbidden Patterns

The checker loads official World Rules and Forbidden Patterns. v0.1 has narrow,
deterministic guards for:

- an ability replacing professional knowledge, training, or resources;
- unbounded control instead of a limited personal bias rule;
- a secret centralized ability-governance institution;
- formal secret-government, repeated-secret-facility, single-conspiracy, and
  elemental-attribute forbidden-pattern signatures.

The signatures only activate when the corresponding formal rule/pattern exists
in the loaded World Bible.

### Faction and authority boundaries

Checks explicit organization-wide/city-wide leadership, independent authority,
enforcement, and cross-domain command claims. It also rejects a small set of
clear faction-role mismatches, such as an academic research center's role being
“city police commander.” It does not judge career seniority or social realism.

### Knowledge-scope boundaries

Rejects blanket access to all city-wide ability files, complete internal
records, or all incident conclusions. Explicit claims to non-public Lore IDs
also fail without Canon authorization. The checker performs read-only
validation and never creates a synthetic authorization record.

### Story and relationship boundaries

A story/case/incident target existing does not establish that a new draft
participated in it. `canon_backed` links and relationships must already exist in
Canon; otherwise they fail. Proposed relationships are allowed. Claims that the
new draft was the core leader, sole witness, true culprit, or final resolver of
an established target produce `STORY_ROLE_OVERREACH`.

### Hard constraints

Checks deterministic age ranges, explicit forbidden elements, required or
forbidden faction IDs, non-core story-role requirements, and explicit combat
role requirements. Soft preferences do not fail a draft.

### Draft and existing-character identity

Requires `status == "draft"` and no canonical character ID. Reusing an existing
character ID fails. Exact duplication of both an existing display name and
occupation is also rejected; v0.1 does not perform fuzzy similarity scoring.

## Examples

### Valid conservative draft

A 23-year-old research assistant using only public information, with a bounded
support ability and clearly new personal details, returns `PASS` with no
findings.

### Shen Zhao regression

The static Shen Zhao fixture is broadly compatible with the university faction,
age constraint, support position, and indirect incident connection. However,
“南栈观察项目” and “时间线记录被复盘引用” are listed as new design while the
background/story hook describe them as completed facts. The result is `WARN`
with two `PROPOSAL_PRESENTED_AS_CANON` findings.

### Blatantly invalid draft

The bad fixture is age 17, claims the public-safety coordination mechanism's
highest office, leads a secret regulatory department, accesses all city ability
files, replaces professional emergency work with an ability, and takes the
core resolution role in the established Nanzhan incident. The checker returns
`FAIL` and reports the independent issues in one pass.

## CLI

```bash
py scripts/demo_canon_checker_v0_1.py --case good
py scripts/demo_canon_checker_v0_1.py --case subtle
py scripts/demo_canon_checker_v0_1.py --case bad
py scripts/demo_canon_checker_v0_1.py --case subtle --json
py scripts/run_canon_checker_evals.py
```

## Known limitations

v0.1 does not decide whether a character is charming, commercially valuable,
visually differentiated, or balanced for combat. It does not detect every
implicit literary contradiction, measure thematic similarity, use embeddings,
judge the full social plausibility of age versus seniority, or understand all
natural-language paraphrases. Its lexical guards are deliberately narrow to
avoid turning the checker into an always-rejecting subjective reviewer.

## Future repair loop

The report shape is ready for a later flow:

```text
CharacterDraft
    -> CanonChecker
    -> CanonFinding[]
    -> future CharacterRepairAgent
    -> revised CharacterDraft
    -> CanonChecker
```

No repair prompt, repair model, automatic retry, or Canon acceptance exists in
v0.1.
