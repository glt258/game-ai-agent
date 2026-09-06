# Character Personality × Gameplay Alignment v0.1

## Scope

This guard is one deterministic validator in the existing Character Evaluation
Runner. It checks only explicit, high-confidence conflicts between authored
personality text and authored gameplay behavior. It does not infer a complete
personality ontology, use an LLM, change combat-role semantics, or participate
in generation, Canon checking, repair, Provider selection, persistence, or the
reference corpus.

## Contract

The validator uses existing `CharacterDraft` fields and the existing parsed
intent context. It recognizes four bounded conflict families:

| Personality signal | Gameplay signal |
| --- | --- |
| risk avoidance | deliberate high-risk exposure or health trade |
| confrontation avoidance | active close/direct confrontation |
| attention avoidance | deliberate enemy aggro attraction |
| low initiative | constant proactive combat initiation |

Each match requires an explicit signal on both sides. `main_dps`, `support`,
or another combat role by itself is never gameplay-conflict evidence.

## Decision rules

- A matched family with no explicit bridge emits
  `PERSONALITY_GAMEPLAY_CONFLICT` as an `ERROR` and `blocking=True`, producing
  `FAIL` in the existing runner.
- Explicit bridges such as safe-distance/ranged preparation, conditional
  activation, or risking oneself to protect an ally suppress the blocking
  finding. These are productive tension, not automatic inconsistency.
- When the request contains a strict-consistency constraint, the finding
  message records that constraint; the validator remains deterministic.
- No new repairability field is introduced. The existing Character repair
  contract is not extended; this conflict is generally a regeneration/design
  decision rather than an automatic repair.
- `EvaluationFinding` has no evidence-reference field. The legal existing
  `field_path` carries the participating draft fields, while the message
  records the bounded signal patterns that matched. No fabricated evidence
  IDs are emitted.

## Known boundary

This is intentionally a bounded lexical guard. It is explainable and portable,
but it does not judge subtle, metaphorical, or unrecognized personality and
gameplay language. Expand the signal table only with a demonstrated regression
case and a corresponding false-positive test.
