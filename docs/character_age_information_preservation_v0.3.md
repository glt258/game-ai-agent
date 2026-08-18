# Character Diversity v0.3 — Age Information Preservation

## Investigation

Before this patch, `CharacterGenerationAgent` only rejected non-null
`CharacterDraft.age` and `age_range` when a brief explicitly kept exact age
unknown. Narrative fields were not checked, so a draft could preserve null
structured age while inventing a self-history such as `从十几岁起` or
`少年时期`. School history was not part of the age check.

The patch keeps the formal schema unchanged and adds a narrow, self-referential
preservation check at the generation boundary. The same check runs on bounded
repair candidates. It is not an age classifier and does not infer age from
appearance, occupation, work duration, family responsibilities, or school
attendance.

## Contract

When the brief explicitly keeps age unknown:

- exact age and age ranges remain unknown;
- legal categories such as minor/adult remain unknown;
- unsupported self-referential historical stages such as teenage years,
  childhood, adolescence, or adulthood-after claims remain unknown;
- youthful presentation remains allowed;
- claims about another person remain allowed;
- duration and family facts do not become age facts.

School history is separate. A current non-student constraint does not ban past
school history. A brief that explicitly keeps past school attendance unknown
does ban self-history such as `离开学校后，她……`.

Validated Canon support may preserve an explicit structured age fact. This does
not authorize inventing a relative life-stage history that Canon did not supply.

## Boundaries

The patch does not change `CharacterDraft`, the formal demographic schema,
Canon Checker architecture, reference selection, provider retry/timeout
behavior, combat fantasy, or the Contract Recovery behavior. Repair remains one
bounded candidate attempt; a candidate that retains an unsupported age or
school-history claim is rejected at the repair boundary.

## Regression coverage

`tests/test_character_diversity_life_stage.py` covers exact age, legal status,
relative life-stage claims, unrelated-person context, youthful presentation,
current versus historical school semantics, work duration, family facts,
mature-adult requests, and Canon-supported age. The repair red-team suite also
covers rejection of a candidate that retains unsupported age history.

## Live evidence

The final strict age-unknown retest used provider `opencode_go` with model
`deepseek-v4-flash` and produced 沈蓝枝. Exact age, legal-age status, historical
age-stage, and school history remained unknown; youthful presentation, work
duration, family responsibility, and playable fantasy remained valid. Canon
PASS; ACCEPTED.

The earlier 梅林 case remains recorded as Canon final FAIL / NEEDS_REVIEW and
is the evidence that motivated this patch. No claim is made that all
providers/models were tested.
