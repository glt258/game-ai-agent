# Character Skill CS-S1 Blind Review and Freeze Report v0.1.1

Status: **CS-S1 FROZEN**

## Freeze metadata

- Review-input commit (Commit A): `c578b091f47dee3a0410fbc4bb5d1176bc2e28d4`
- Blind case input: `evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json`
- Reviewer prompt: `evals/fixtures/character_skill_s1_blind_review_prompt_v0.1.1.md`
- Output schema: `evals/fixtures/character_skill_s1_blind_review_output_schema_v0.1.1.json`
- Input manifest: `evals/fixtures/character_skill_s1_blind_review_input_manifest_v0.1.1.json`
- DeepSeek result: `evals/results/character_skill_s1_blind_review_deepseek_v0.1.1.json`
- MiMo result: `evals/results/character_skill_s1_blind_review_mimo_v0.1.1.json`
- Frozen contract: `docs/character_generation/character_skill_interface_options_v0.1.1.md`

Both result objects bind the same full Commit A SHA and the same three raw-byte
input digests. The public input contains the 19 structured candidates and
validation contexts but omits the private `expected` oracle mapping.

## Reviewer source and retained artifacts

The two results are user-supplied Hermes final-response artifacts. Their embedded
provenance identifies provider `opencode-go`, models `deepseek-v4-flash` and
`mimo-v2.5`, generation times `2026-08-23T14:10:45Z` and
`2026-08-23T14:22:13Z`, and redacted request identifier
`redacted:manual-hermes-review`.

| Reviewer | Supplied attachment SHA-256 | Stored result SHA-256 |
| --- | --- | --- |
| `deepseek-v4-flash` | `0a8c70040807baff1b665313b90b681a026a163ca79b797862cc1a0979a93169` | `682dfdc58a43b0c44fe48cd8976fcf14b60c9378d4f76f3d18f138118152d5ee` |
| `mimo-v2.5` | `af2720a6f2fd16728aeffc1058b98b86570f370ff9679ef5e50fdef669c40b91` | `d97aebe31c4a8b401864bb184825b82dddb377bec4aa953bd6a60507958cf490` |

The stored files contain the exact supplied JSON text plus one repository final
LF. No JSON token, verdict, reason, finding code, or repair plan was changed.
No independent Hermes usage file or public provider request ID was retained, so
provider/model identity is retained as artifact provenance rather than claimed
as independently attested HTTP transport provenance.

## Contract validation

Both results pass the frozen output contract:

- exact schema version, Commit A, reviewer identity, and three input digests;
- 19 unique cases in `case_01` through `case_19` order;
- closed `PASS | REPAIR | FAIL` verdict vocabulary;
- `PASS` uses `primary_finding = NONE`;
- every `REPAIR` has non-empty `preserve` and `changes` arrays;
- `PASS` and `FAIL` omit `repair_plan`; and
- both artifacts declare `normalization: none`.

## Agreement

Finding labels were deliberately reviewer-derived rather than supplied as a
case-to-code oracle. Agreement below therefore compares verdicts; Sol maps the
case-local reasoning to the frozen finding registry during adjudication.

| Comparison | Verdict agreement |
| --- | ---: |
| `deepseek-v4-flash` vs frozen oracle | 18/19 |
| MiMo v2.5 vs frozen oracle | 14/19 |
| `deepseek-v4-flash` vs MiMo v2.5 | 15/19 |
| All three agree | 14/19 |

The reviewers disagree on verdict for `case_02`, `case_04`, `case_06`, and
`case_17`. Both reviewers also disagree with the oracle on `case_15`.

## Sol adjudication

| Case | Final decision | Adjudication basis |
| --- | --- | --- |
| 01 | `PASS` | Resource entry, use, exit, and no-resource fallback are closed. |
| 02 | `REPAIR / RESOURCE_LOOP_INCOMPLETE` | The resource has a typed use anchor but no entry or exit. MiMo's `PASS` ignores validator-owned lifecycle closure. |
| 03 | `FAIL / FORBIDDEN_RESOURCE_INTRODUCED` | A declared resource family conflicts with the request-side forbidden family. |
| 04 | `REPAIR / STATE_EXIT_MISSING` | Establishment and active effects survive; the missing exit/replacement slot is locally patchable. MiMo's `PASS` incorrectly makes closure conditional on an explicit mechanic requirement. |
| 05 | `REPAIR / TRIGGER_SUBJECT_AMBIGUOUS` | Both reviewers identify the null/ambiguous trigger while preserving the support effect path. The frozen registry retains the broader subject/event ambiguity code. |
| 06 | `REPAIR / SUMMON_LIFECYCLE_INCOMPLETE` | Spawn and active anchors survive. The contract explicitly authorizes bounded additions to departure/replacement and repeat-policy slots; MiMo incorrectly calls that redesign. |
| 07-12 | `FAIL / ROLE_EFFECT_MISMATCH` | The observable core effects do not satisfy their canonical role duties. |
| 13 | `FAIL / MECHANIC_SKELETON_ABSENT` | Both reviewers reject the unrelated trigger/effect path. Prose cannot establish the requested trigger-effect-feedback skeleton, and no local repair is authorized. |
| 14 | `FAIL / CROSS_TAXONOMY_ROLE_LABEL` | Both reviewers fail closed. Sol retains taxonomy contamination as the priority finding even though the candidate is also empty. |
| 15 | `FAIL / REFERENCE_COPYING` | Both reviewers judged only the visible structural validity and returned `PASS`. The candidate fingerprint cannot be recomputed from the blind packet without the validator's canonicalization algorithm. The validator-owned graph fingerprint test detects the isomorphic controlled external component after IDs and prose are renamed, so the reviewer verdicts are rejected. |
| 16 | `FAIL / HARD_CONSTRAINT_CONFLICT` | The same summon must be both forbidden and required; the request is unsatisfiable. |
| 17 | `REPAIR / MULTI_SKILL_LOOP_INCOHERENT` | The mark has use/read anchors but no producer or exit, so the multi-skill order cannot start. MiMo checks reference resolution but misses loop coherence. |
| 18 | `PASS` | The control duty, teammate-event trigger, summon lifecycle, and replacement path are complete. |
| 19 | `REPAIR / REQUESTED_MECHANIC_UNREPRESENTED` | The trigger-effect skeleton survives but the required typed feedback relation is absent. MiMo's claimed effect-subject mismatch contradicts its own observation that the requirement and candidate both use `self`; Sol rejects that sub-finding. |

### Case 15 review limitation

`case_15` does not reveal its oracle result, but it also does not provide the
validator's graph-canonicalization algorithm or a derived candidate fingerprint.
The external fingerprint alone is therefore insufficient for a language-model
reviewer to reproduce the hash comparison. This is an intentional authority
boundary: the provider emits candidate structure, while the deterministic
validator owns copying detection. The shared reviewer miss is retained as
evidence that copying must not be delegated to provider self-review; it is not
evidence that the deterministic interface contract accepts the copy.

## Freeze-gate decision

| Gate | Result |
| --- | --- |
| All 19 frozen outcomes and primary codes reproduced by the deterministic prototype | Pass |
| Case 13 cannot enter local repair; case 19 passes after one authorized feedback addition and full recheck | Pass |
| CI-B1.5 canonical taxonomy remains fail closed | Pass |
| Legacy `ability_concept` remains `LEGACY_UNVERIFIED`, never automatic `PASS` | Pass |
| Provider, validator, repair, and renderer authorities remain separate | Pass |
| Input digest and oracle-free projection tests | Pass |
| Independent DeepSeek and MiMo evidence retained and all disagreements adjudicated | Pass |
| `src/` remains unchanged | Pass |

Final decision: **CS-S1 FROZEN**.

The freeze covers Character Skill Interface v0.1.1 provider shape,
validator-owned derived graph semantics, finding repairability, digest-bound
patch authorization, one-way rendering, and legacy non-PASS behavior. It does
not authorize production integration under `src/`, freeze provider prompts or
balance values, or begin CS-S2 implementation.
