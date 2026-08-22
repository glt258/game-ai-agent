# Character Skill S0.1 Blind Review Report

## Freeze metadata

This report records the blind-review evidence used to freeze the Character Skill
S0.1 contract (v0.1.1).

- Commit A: `f96b45023e844e501a07b4426ef7fa963285a054`
- Authority fixture: `evals/fixtures/character_skill_failure_cases_v0.1.1.json`
- Blind input: `evals/fixtures/hermes_character_skill_s0_blind_cases_v0.1.1.json`
- Frozen specification: `docs/character_generation/character_skill_failure_cases_v0.1.1.md`
- DeepSeek output: `evals/results/character_skill_s0_blind_review_deepseek_v0.1.1.json`
- MiMo output: `evals/results/character_skill_s0_blind_review_mimo_v0.1.1.json`

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

| Check | DeepSeek | MiMo |
| --- | ---: | ---: |
| Cases present, unique, and ordered | 19/19 | 19/19 |
| Verdict vocabulary valid | 19/19 | 19/19 |
| Every REPAIR has a non-empty repair plan | Pass | Pass |
| PASS and FAIL omit repair plans | Pass | Pass |
| Stored normalized JSON parses | Pass | Pass |

## Agreement

| Comparison | Agreement |
| --- | ---: |
| DeepSeek vs S0.1 oracle | 19/19 |
| MiMo vs S0.1 oracle | 18/19 |
| DeepSeek vs MiMo | 18/19 |
| All three agree | 18/19 |

The only reviewer disagreement is `case_05`. The S0.1 boundary cases introduced
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
| S0.1 oracle | `REPAIR / TRIGGER_SUBJECT_AMBIGUOUS` |
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

The blind review supports the S0.1 semantic revision. There is no evidence that
the authority fixture needs another content change. The authority fixture,
frozen specification, and blind input are verified to be byte-identical to their
Commit A versions after Commit A was created.

S0.1 v0.1.1 is frozen by Commit B once this report, the normalized reviewer
outputs, and the provenance test are committed together. S1 must begin from
that frozen commit.
