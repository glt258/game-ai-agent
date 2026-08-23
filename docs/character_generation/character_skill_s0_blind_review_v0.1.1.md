# Character Skill CS-S0.1 Blind Review Report

## Freeze metadata

This report records the blind-review evidence used to freeze the Character Skill
CS-S0.1 contract (v0.1.1).

- Commit A: `f96b45023e844e501a07b4426ef7fa963285a054`
- Authority fixture: `evals/fixtures/character_skill_failure_cases_v0.1.1.json`
- Blind input: `evals/fixtures/hermes_character_skill_s0_blind_cases_v0.1.1.json`
- Frozen specification: `docs/character_generation/character_skill_failure_cases_v0.1.1.md`
- `deepseek-v4-flash` output: `evals/results/character_skill_s0_blind_review_deepseek_v0.1.1.json`
- MiMo v2.5 output: `evals/results/character_skill_s0_blind_review_mimo_v0.1.1.json`

The reviewer IDs are `deepseek-v4-flash` and `mimo-v2.5` (MiMo v2.5).
Both result files carry the same full Commit A SHA.

## Review method

`deepseek-v4-flash` and MiMo v2.5 independently judged the same exact
non-oracle projection. The projection contains each request, candidate summary,
and declared facts, while omitting expected outcomes, finding codes, signals,
and rationale. Neither reviewer is the final specification judge. Codex/Sol
adjudicates against the frozen oracle, reproducible case evidence, and focused
tests.

The MiMo response contained presentation-layer escaping errors in the raw
transport (including an escaped underscore and an incorrectly escaped quotation
in the case_05 reason). The stored result applies syntax-only normalization.
No verdict, reason meaning, or repair plan was changed.

The raw transport artifact is not included in the repository. This limits
independent byte-level provenance checks for the original response; the stored
normalized JSON, its source_commit, the blind input, the authority fixture, and
the focused tests provide the retained semantic provenance.

## Validation

| Check | `deepseek-v4-flash` | MiMo v2.5 |
| --- | ---: | ---: |
| Cases present, unique, and ordered | 19/19 | 19/19 |
| Verdict vocabulary valid | 19/19 | 19/19 |
| Every REPAIR has a non-empty repair plan | Pass | Pass |
| PASS and FAIL omit repair plans | Pass | Pass |
| Stored normalized JSON parses | Pass | Pass |

## Agreement

| Comparison | Agreement |
| --- | ---: |
| `deepseek-v4-flash` vs CS-S0.1 oracle | 19/19 |
| MiMo v2.5 vs CS-S0.1 oracle | 18/19 |
| `deepseek-v4-flash` vs MiMo v2.5 | 18/19 |
| All three agree | 18/19 |

The only reviewer disagreement is `case_05`. The CS-S0.1 boundary cases introduced
or clarified by the revision are stable across the review:

- `case_13`: all three classify the absent mechanism skeleton as
  `FAIL / MECHANIC_SKELETON_ABSENT`.
- `case_14`: all three preserve canonical taxonomy fail-closed behavior as
  `FAIL / CROSS_TAXONOMY_ROLE_LABEL`.
- `case_18`: all three retain the complete control-role near-neighbor as
  `PASS`.
- `case_19`: all three classify the existing trigger-to-effect skeleton with
  a missing feedback relation as `REPAIR`.

## Adjudication: case_05

| Source | Verdict |
| --- | --- |
| CS-S0.1 oracle | `REPAIR / TRIGGER_SUBJECT_AMBIGUOUS` |
| deepseek-v4-flash | `REPAIR` |
| MiMo v2.5 | `FAIL` |

The candidate already states a causal direction in which a teammate-related
event triggers the character's response. That is a preservable mechanism
skeleton. The defect is that “teammate is affected” does not identify the
concrete event class or distinguish the trigger subject from the effect subject.
Those relations can be clarified locally.

MiMo v2.5 treated the ambiguous trigger subject as if no trigger-to-effect
relation existed. That collapses the distinction between
`TRIGGER_SUBJECT_AMBIGUOUS` and `MECHANIC_SKELETON_ABSENT`, so the `FAIL`
verdict is rejected.

Final adjudication: `case_05 = REPAIR / TRIGGER_SUBJECT_AMBIGUOUS`.

## Freeze decision

The blind review supports the CS-S0.1 semantic revision. The authority fixture
and blind input are the machine-readable inputs frozen against Commit A; both
are byte-identical to their Commit A versions. Commit A remains the input
provenance recorded by both reviewer outputs through `source_commit`.

The English specification is a later translation of the Commit A Chinese
specification. It is semantically frozen, not byte-frozen: focused tests validate
case IDs, outcomes, finding codes, and boundary statements, without claiming
byte identity with Commit A's Chinese version.

CS-S0.1 contract v0.1.1 is frozen by Commit B once this report, the normalized reviewer
outputs, and the provenance test are committed together. CS-S1 must begin from
that frozen commit.
