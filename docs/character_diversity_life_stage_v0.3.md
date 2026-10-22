# Character Diversity & Life-Stage Coverage v0.3

## Goal

Character authoring should produce different kinds of people without hidden
templates such as `young -> student`, `adult -> formal worker`, or
`playable -> secret fighter`. Life-stage presentation is a plausibility input,
not a mechanical assignment of occupation, faction, authority, or narrative
importance.

## Investigation

The authoring draft already contains nullable `age` and `age_range`, plus
`occupation`, `social_role`, `faction_id`, `relationships`, `knowledge_scope`,
`background`, and `story_hook`. The formal character record has
`basic_profile.age`, `age_band`, and `legal_age_status`, but those formal fields
are not required by the draft-only authoring contract.

Exact age is therefore optional in a draft. `null` means the brief or Canon
does not establish an exact value; it is not permission to guess from face,
height, voice, body proportions, clothing, or behavior. The authoring draft
has no dedicated age-presentation or authority enum. Presentation and social
position stay in the existing narrative fields until a concrete representation
gap justifies schema expansion.

Current Canon also has a narrow `RULE-024`: an explicitly numeric minor must
not default to professional high-risk frontline work. It does not prohibit a
younger-presenting or age-ambiguous character from a dangerous role, and it
does not make `minor` the creative center of this feature.

`identity.faction_id` is formal organization identity. It is distinct from
geography and does not grant leadership, unrestricted knowledge, or every
possible organization role. The generation contract now tells the model to
keep prose and the structured faction field aligned.

The observed cross-field issue was a draft carrying a faction ID while its
prose said the character was not a member of any organization. This pass fixes
the authoring contract wording and test coverage for the narrow case: a formal
member is described as a member with bounded authority, while a non-member
keeps `faction_id: null`. A general semantic consistency engine is deferred.

## Design contract

- Preserve exact age as unknown when the brief or Canon leaves it unknown.
- Keep age presentation, Canon age facts, life/social position, and authority
  separate.
- Do not infer school attendance from youthful presentation alone.
- Do not infer formal employment from adulthood or mentor/retirement status
  from mature presentation.
- Permit dangerous occupations when practical experience, support, limits, and
  the project world make them plausible.
- Preserve the asymmetry of practical competence with limited formal authority
  where appropriate.
- Do not turn playability into prodigy, secret training, hidden bloodline,
  experiment, command authority, or world-truth knowledge.
- Build appeal from identity, personality, relationships, motifs, tension,
  agency, and gameplay fantasy, without sexualized or adultized framing for
  younger-presenting characters.

## Implementation

No CharacterDraft, formal Character Schema, Canon Checker, or repair schema was
expanded. The generation and repair contracts carry the new distinctions. The
preservation validator rejects exact age, legal-age status, and
self-referential historical life-stage claims only when the request explicitly
keeps age unknown. It also has a separate school-history guard for briefs that
explicitly keep past school attendance unknown. Claims about another person,
work duration, family responsibilities, youthful presentation, and ordinary
school history under a current-non-student brief remain allowed. Validated Canon
age support may preserve a structured age fact.

The existing Canon Checker and bounded repair loop remain the authority for
Canon, world-rule, authority, knowledge-scope, faction-role, and playable
combat-fantasy regressions.

## Test matrix

`tests/test_character_diversity_life_stage.py` covers deterministic cases for:

1. age-unspecified younger-presenting field work;
2. younger-presenting non-school everyday life;
3. adult life without formal career identity;
4. mature active playable identity;
5. explicit age ambiguity through serialization;
6. younger-presenting organization membership with limited authority;
7. exact, legal, relative, and contextual age preservation;
8. separate current-school and historical-school semantics;
9. duration/family non-inference and Canon-supported age.

The tests also cover explicit numeric-age rejection under an ambiguity
constraint, dangerous-role plausibility, membership versus authority, the
existing playable contract, repair candidate protection, and the existing
character-generation repair benchmark.

## Live acceptance results

The accepted live evidence was run with provider `opencode_go` and model
`deepseek-v4-flash`. This records the observed outcomes only; it does not claim
that all providers or models were tested.

| Case | Observed result |
| --- | --- |
| Young field character — 土屑 | Youthful and age-unspecified; no current school identity; dangerous independent field role plausible; no secret prodigy, experiment, or hidden training; authority bounded; Canon PASS; ACCEPTED |
| Young everyday character — 梅林 | Ordinary non-school identity and authority boundaries succeeded; invented `从十几岁起` and unnecessary `离开学校后` history; Canon final FAIL; NEEDS_REVIEW; pipeline remained honest |
| Mature playable character — 覃雪岫 | Active mature adult identity preserved without mentor/retired-master collapse; playable fantasy PASS; Canon final FAIL; NEEDS_REVIEW; pipeline remained honest |
| Strict age unknown — 环溪 | No numeric age, legal-age label, or historical age-stage invented; Canon final WARN; NEEDS_REVIEW; pipeline remained honest |
| Final age-preservation retest — 沈蓝枝 | Exact/legal/historical age and school history remained unknown; youthful presentation, work-years, family responsibility, and playable fantasy preserved; Canon PASS; ACCEPTED |

The 梅林 result was the direct evidence for the Age Information Preservation
patch. The deterministic acceptance matrix and all Canon/repair regressions
also pass. Reference-selection repetition remains a deferred benchmark.

## Known limitations and deferred backlog

- There is no dedicated structured age-presentation, life-stage, or authority
  field in `CharacterDraft`; the current contract uses existing fields.
- Freeform prose can still express subtle contradictions that are outside the
  current deterministic checker. A general cross-field semantic consistency
  engine is deferred.
- Reference retrieval quality is observed only. Repeated selection of the
  same references should feed a future **Reference Selection Quality
  Benchmark**; retrieval is not changed here.
- A future **Character Visual Design Stage** and **Character Authoring Model
  Benchmark: DeepSeek vs MiMo** remain deferred.
- Legal-age policy, demographic classification, appearance-age estimation,
  romance systems, and new combat or balance systems are out of scope.
