# Character Skill CS-S2 Shadow Migration Execution Plan v0.2

Status: **PLAN LOCKED; IMPLEMENTATION INCOMPLETE**

This document is the execution contract for CS-S2 Commit 1. It authorizes
staged implementation work only. It does not mark CS-S2 complete, activate a
new provider contract, change the production `CharacterDraft`, or authorize
consumer migration.

## 1. Authority, objective, and locked inputs

### Authority

The normative interface and deterministic semantics are frozen by
`docs/character_generation/character_skill_interface_options_v0.1.1.md`, whose
status is **CS-S1 FROZEN**. That contract owns the Protocol Surface / Derived
Graph Core shape, the four public seams, finding codes, repairability,
digest-bound patches, one-way rendering, and the 19-case outcomes. This plan
does not redesign or relitigate that schema.

The retained evidence and adjudication are
`evals/results/character_skill_s1_blind_review_report_v0.1.1.md`. Its frozen
decisions include case 13 as non-repairable `MECHANIC_SKELETON_ABSENT`, case 19
as repairable `REQUESTED_MECHANIC_UNREPRESENTED`, and case 14 as fail-closed
`CROSS_TAXONOMY_ROLE_LABEL`.

The historical option and migration analysis is
`docs/character_generation/character_skill_interface_options_v0.1.md`. Its
Phase 1-4 sequence is retained here as the implementation order: shadow
sidecar, versioned dual representation, localized repair, and consumer
migration. The engineering readiness and collaboration constraints are in
`docs/character_skill_design_readiness_report_2026-08-22.md`.

If this plan conflicts with the frozen S1.1 contract, the frozen S1.1 contract
and its deterministic tests take precedence. A later change requires a new
versioned contract and a separately reviewed plan.

### Objective

Introduce a production `src/character_skill/` deep module behind an explicitly
injected shadow configuration. The first implementation must observe an
independent structured skill candidate beside the existing character
generation path, parse and evaluate it through the frozen S1 seams, and retain
only a sanitized observation. The existing draft, display text, verdict,
repair behavior, provider call path, and consumers remain authoritative while
the shadow is `OFF` or `RECORD_ONLY`.

The objective is to establish a reversible seam with measurable locality and
depth before any dual representation or consumer migration is considered.

## 2. Non-goals

CS-S2 does not include any of the following:

- numerical balance, damage multipliers, cooldown fields, frame fields, or
  other numerical combat parameters;
- runtime combat simulation, battle execution, or game-state integration;
- changes to project Canon or Canon authority;
- changes to, additions to, or copied templates from the Reference Corpus;
- weapons or equipment design;
- role taxonomy changes, new role aliases, or a second role scalar;
- provider prompt tuning or provider-specific schema invention outside the
  frozen response contract;
- reverse inference from `ability_concept` into structured mechanic facts;
- adding `skill_kit` to the strict legacy `CharacterDraft` root during shadow
  mode;
- making shadow findings authoritative for the legacy verdict or repair loop;
- declaring CS-S2 or the overall skill contract frozen; or
- removing `ability_concept` before the dual-representation exit conditions in
  this plan are independently reviewed.

## 3. Current production seams

The migration must attach at existing seams and preserve their current
contracts. The following inventory is the starting point for implementation:

1. `CharacterGenerationAgent.generate(request, *, use_intent_layer=False)` is
   the generation seam. It calls the existing `AgentModel` provider seam,
   requests the strict `character_draft` response contract, constructs a
   `CharacterDraft`, performs existing checks, and returns a
   `CharacterGenerationResult`.
2. `response_contract_for(response_format)` is the response-contract
   selection seam. `character_draft` currently resolves to a strict schema
   with `additionalProperties: false`; all declared root properties are
   required, and `ability_concept` is the only current ability field.
3. `CharacterDraft` is the strict, approval-independent legacy candidate. Its
   `from_mapping` parser is the legacy deserialization seam. The existing
   bounded legacy `combat_role` crosswalk remains restricted to that seam and
   is not a SkillKit input authority.
4. `CharacterGenerationResult` contains the legacy `draft`, source IDs, and
   `CharacterGenerationAudit` (and the optional design plan). Its shape and
   audit semantics remain unchanged while shadow mode is being evaluated.
5. `EvaluationRunner` runs the fixed validator collection and produces the
   legacy `EvaluationResult`. Its current default validators are
   `RequestAlignmentValidator` and `RepresentationCompletenessValidator`.
   The former checks requested canonical roles; the latter checks legacy
   representation fields including `ability_concept`. Neither is silently
   replaced by the SkillKit evaluator in this plan.
6. `CharacterRepairAgent.repair(repair_request)` is the existing one-attempt
   legacy repair seam. Its Canon evidence, hard-constraint preservation,
   allowed-field scope, regression protection, and full recheck remain intact.
   SkillKit repair is a separate seam using the frozen digest-bound patch
   contract; it must not be smuggled into the legacy `ability_concept` repair
   scope.

The first implementation must wrap these seams at the composition root or a
new narrow adapter. It must not make the deep module import the legacy
orchestrator, read process state, or own Canon, provider policy, or legacy
verdict policy.

## 4. Deep-module decision and public interface

### Deep-module shape

The planned package is `src/character_skill/`. Its implementation should have
high depth: callers provide a candidate and explicit evaluation context, while
the module owns normalization, typed-reference resolution, derived-graph
construction, lifecycle checks, finding accumulation, repair authorization,
digest verification, and deterministic rendering. The graph and its compiler
remain private implementation details.

The pure in-process core needs no new adapter or port. It is deterministic and
does not perform transport, persistence, environment lookup, Canon lookup, or
provider calls. The provider reuses the existing `AgentModel`/provider seam
through a thin response-contract adapter owned by the orchestration layer.

### Frozen public interface

Tests and production callers use only these four seams:

```python
parse_candidate(payload)
evaluate(candidate, context)
apply_patch(candidate, patch, report, context)
render_ability_concept(candidate)
```

The expected conceptual signatures are:

```python
parse_candidate(payload: Mapping[str, object]) -> ProtocolSkillKitCandidate
evaluate(
    candidate: ProtocolSkillKitCandidate,
    context: SkillKitEvaluationContext,
) -> SkillKitValidationReport
apply_patch(
    candidate: ProtocolSkillKitCandidate,
    patch: SkillKitPatch,
    report: SkillKitValidationReport,
    context: SkillKitEvaluationContext,
) -> SkillKitPatchResult
render_ability_concept(candidate: ProtocolSkillKitCandidate) -> str
```

The exact frozen S1.1 value objects, closed vocabularies, field paths, finding
codes, and digest rules are reused from the S1.1 document. No caller may use a
private graph type, a `compile` helper as a replacement public seam, a
provider-authored verdict, or a prose-to-graph convenience parser.

## 5. Shadow sidecar dataflow

The shadow uses an independent response contract keyed by the stable
`CharacterDraft.draft_id`. It does not add `skill_kit` to the strict legacy
`CharacterDraft` root. A sidecar observation may be held beside the
`CharacterGenerationResult`, or in a separate keyed observation store, but it
must not mutate the legacy result.

```text
                         +-----------------------------------------------+
request                  | existing AgentModel / provider seam            |
  |                      +----------------------+------------------------+
  v                                             |
CharacterGenerationAgent.generate              |
  |                                             v
  |                         strict character_draft response contract
  |                                             |
  |                                             v
  |                                     CharacterDraft
  |                                             |
  |                                             v
  |                                  CharacterGenerationResult
  |                                             |
  |                         EvaluationRunner -> legacy validators -> verdict
  |                                             |
  |             legacy draft, ability_concept, verdict, repair, consumers
  |                                             |
  |                         remain authoritative and unchanged
  |
  +-- RECORD_ONLY only: independent character_skill_shadow response contract
                              keyed by draft_id
                                           |
                                           v
                                  parse_candidate(payload)
                                           |
                                           v
                                  evaluate(candidate, context)
                                           |
                                           v
                                sanitized shadow observation/audit
                                           |
                                           v
                         sidecar keyed by the same stable draft_id

  OFF: the lower branch is not invoked.
```

In `RECORD_ONLY`, the optional skill-side provider call is separate from the
strict legacy draft call. Its response is parsed only by the SkillKit response
contract. A shadow failure produces a contained observation and never replaces
the legacy `CharacterGenerationResult`, legacy `EvaluationResult`, draft,
`ability_concept`, repair recommendation, or downstream consumer input.

## 6. Feature configuration and containment

The composition root injects a validated configuration with this shape:

```python
@dataclass(frozen=True)
class CharacterSkillShadowConfig:
    mode: Literal["OFF", "RECORD_ONLY"] = "OFF"
```

The default is `OFF`. The configuration is passed through the orchestration
seam; the `src/character_skill/` deep module does not read environment
variables, global flags, command-line state, or configuration files. The
composition root owns mode selection and dependency injection.

The mode invariants are strict:

- `OFF` performs no SkillKit provider call, creates no shadow audit, and has
  identical legacy provider call count, legacy provider output, legacy audit,
  draft, verdict, repair path, and consumer input compared with the main path
  before CS-S2.
- `RECORD_ONLY` may perform the independent sidecar call and record a
  sanitized result, but cannot affect the legacy draft, `ability_concept`,
  `EvaluationRunner` verdict, `CharacterRepairAgent` input or result, or any
  consumer.
- A malformed sidecar, provider/transport failure, parse exception, evaluator
  exception, or audit serialization failure is caught at the shadow adapter.
  It becomes a sanitized shadow error record; it is not allowed to abort a
  successful legacy generation.
- The sidecar is keyed by `draft_id` and may be discarded without a data
  migration. No shadow record is a source of Canon, role taxonomy, or legacy
  approval.

## 7. Compatibility invariants

The following invariants are required for every CS-S2 implementation commit:

1. The strict legacy `CharacterDraft` response contract remains unchanged in
   shadow mode. No `skill_kit` root field is added to it, and no unknown field
   is accepted through a permissive fallback.
2. There is no reverse parser from `ability_concept` to SkillKit. Legacy prose
   may be displayed and audited as legacy text, but it cannot satisfy a
   structured mechanic, lifecycle, feedback, or role-evidence finding.
3. The legacy `CharacterGenerationResult`, existing audit, and legacy
   `EvaluationRunner` verdict remain authoritative until a separately reviewed
   versioned dual-representation gate is passed.
4. Structured facts become the source of mechanic truth only in that versioned
   gate. The gate must be required-but-nullable for old payloads and must
   define explicit handling for `skill_kit=None`; it must not infer a graph
   from legacy prose.
5. `render_ability_concept(candidate)` is deterministic and one-way. Once a
   structured candidate is authoritative, `ability_concept` is rendered or
   consistency-checked from it; text cannot override structured findings.
6. `draft_id` is the stable join key across the legacy draft, independent
   response contract, sidecar observation, sanitized provenance, repair
   report, and future dual representation.
7. `CombatRoleProfile` remains the sole canonical role authority. SkillKit
   role evidence proves duties against externally supplied context; it does
   not add a role taxonomy or call the legacy alias normalizer.
8. Reference Corpus records remain external review context only. The provider
   cannot submit a corpus match, copied ID, or self-attested verdict.

## 8. Error model and sanitized audit

The shadow adapter translates failures into a stable record without changing
the frozen S1 evaluator semantics. Each record has at least:

```text
schema_version
draft_id
phase
code
field_path
severity
blocking
repairability
message
provenance
```

`field_path` uses the frozen JSON Pointer paths when a candidate field exists;
otherwise it is `"/"` or the stable input location. `severity` is one of
`INFO`, `WARNING`, or `ERROR`. `blocking` describes the SkillKit observation,
not the legacy generation result. `repairability` is one of
`REPAIRABLE`, `NON_REPAIRABLE`, or `NOT_APPLICABLE`. `message` is a stable,
sanitized explanation and must not contain raw provider text.

The initial error families are:

| Phase | Stable code family | Meaning |
| --- | --- | --- |
| provider/transport | `SHADOW_PROVIDER_FAILURE` | The independent provider call failed or returned no usable response. |
| parsing | `SKILL_KIT_PARSE_FAILURE` | The response violated the strict S1.1 shape, closed vocabulary, ID, or reference form. |
| structural evaluation | frozen S1 finding codes | Typed references, lifecycle, feedback, copying, taxonomy, and graph-topology findings. |
| request alignment | frozen S1 requirement/role findings | The structured candidate does not satisfy request-owned mechanic predicates or external role duties. |
| repair | `SKILL_KIT_PATCH_REJECTED` | Digest, authorized-path, scope, full-recheck, no-improvement, or regression protection rejected a patch. |
| audit | `SHADOW_AUDIT_SANITIZATION_FAILURE` | The observation could not be safely serialized; retain only a minimal code and digest metadata. |

Shape errors remain parse failures rather than semantic reports. After parsing,
the evaluator accumulates all independently provable findings and sorts them
deterministically by the frozen priority, code, field path, and canonical
evidence references. Repairability comes from the frozen code registry; it is
not guessed from severity or model text.

Sanitized provenance may retain provider name, requested/reported model,
generation timestamp, redacted request identifier, response-contract version,
input/context/candidate/report digests, and a bounded call sequence number. It
must not retain passwords, tokens, cookies, API keys, private keys, complete
environment values, raw provider payloads, or unbounded prompt/response text.
The audit records the fact and digest of a failure, not its secret-bearing
transport body.

Containment is part of the error contract: every shadow error is observable in
the sidecar record, but no shadow error becomes a legacy exception, legacy
finding, legacy verdict, repair request, or consumer input while the mode is
`RECORD_ONLY`.

## 9. Planned file allowlists by staged commit

The allowlist is a scope control. A commit must not use an unlisted file as a
convenience edit. Each later stage requires its own review and focused tests.

| Stage | Allowed files | Explicit exclusions |
| --- | --- | --- |
| Commit 1: plan lock | `docs/character_generation/character_skill_cs_s2_execution_plan_v0.2.md` only | `src/`, `tests/`, `evals/`, config, and every existing file |
| Commit 2: deep module | New files under `src/character_skill/` for frozen contracts, pure implementation, errors, and the private derived graph; matching unit tests under `tests/` | Legacy orchestrator, Canon, Reference Corpus, provider prompts, and consumers |
| Commit 3: generation shadow seam | The independent shadow response-contract declaration and the smallest composition-root/generation seam files needed to invoke it; focused shadow tests | The strict legacy `CharacterDraft` root, `src/character_skill/` public seam, legacy verdict and repair policy |
| Commit 4: validation and repair shadow seams | `src/agents/evaluation/runner.py`, the two existing validator seam files or a new explicitly injected SkillKit validator adapter, `src/agents/character_repair.py` only for a separate SkillKit repair seam, and focused tests | Legacy validator semantics, legacy repair fields, Canon, Reference Corpus, and consumers |
| Commit 5: evidence and provider observation | Allowlisted `evals/` fixtures/results and narrowly scoped evidence documentation for real-provider behavior | Private fixtures in production, raw provider payloads, schema changes without a version, and `src/` opportunistic cleanup |
| Commit 6: consumer migration | Explicitly named consumer files after the dual-representation gate, plus migration tests and release notes | Reverse parser, deletion of `ability_concept`, weapons/equipment, Canon, and role taxonomy |

Commit 1 is exactly this document. It must not include any source, test,
evaluation, configuration, generated artifact, or unrelated documentation file.

## 10. Rollout order and entry/exit gates

The rollout order is fixed:

```text
generation -> representation validation -> request alignment -> repair -> consumer migration
```

| Stage | Entry gate | Required implementation | Exit gate |
| --- | --- | --- | --- |
| Generation | Commit 2 pure seams pass focused unit tests | Generate the independent sidecar candidate only in `RECORD_ONLY`; join it by `draft_id` | Legacy provider call/output/audit and draft are unchanged; malformed sidecars are contained; OFF has zero shadow calls |
| Representation validation | Frozen S1.1 seams are imported only through the four public functions | Parse and evaluate typed structure, lifecycle, feedback, role evidence, and copying context | The 19 frozen cases reproduce 19/19 outcomes and primary codes; case 13 remains non-repairable; case 19 remains locally repairable; case 14 remains fail-closed |
| Request alignment | Representation report is deterministic and independent of provider self-attestation | Supply request-owned `MechanicRequirement` and external `CombatRoleProfile` context | Requested mechanics are checked structurally; canonical role behavior is unchanged; independent findings accumulate in stable order |
| Repair | Every target finding is frozen repairable and carries authorized paths and digests | Apply one atomic typed patch, re-evaluate fully, and reject scope/digest/no-improvement/regression failures | Only an improved candidate is accepted; failed shadow repair cannot alter legacy repair or legacy draft |
| Consumer migration | Versioned dual-representation gate is approved and real-provider evidence is retained | Migrate named consumers to structured facts and one-way rendering in separate commits | All consumers read the structured source or renderer; no reverse parser remains; legacy compatibility removal is separately reviewed |

Before any mode is made default-on or any consumer is allowed to trust the
structured result, the following evidence is required:

- the frozen S1.1 19/19 parity test, including explicit case 13, case 19, and
  case 14 assertions;
- flag-off parity for provider call count, output, audit, draft, verdict,
  repair behavior, and consumer input;
- focused shadow, contract, error-containment, and repair tests;
- the full project test suite with no new failure;
- real-provider `deepseek-v4-flash` evidence covering format compliance,
  missing fields, repair stability, and repeated-call drift, retained as
  sanitized evidence; and
- independent review of the migration and evidence package before CS-S3. Mimo
  v2.5 is reserved for the CS-S3 blind review and does not approve this plan
  or own the implementation.

## 11. Dual-representation exit conditions

The sidecar phase may end only when all of these conditions are met in a
versioned, separately reviewed change:

1. A new strict response-contract version defines `skill_kit` as
   required-but-nullable. Legacy payloads are mapped to `skill_kit=None` only
   at the explicit legacy deserialization seam; they are never reverse-parsed.
2. For structured drafts, SkillKit is the sole source of mechanic facts,
   lifecycle facts, feedback relations, and role-duty evidence. The provider
   cannot supply verdicts or repairability.
3. `ability_concept` is deterministically derived by
   `render_ability_concept(candidate)` or checked for consistency by a defined
   versioned rule. It cannot override structured findings.
4. Every consumer that needs mechanic facts has migrated to SkillKit or the
   one-way renderer, and a consumer inventory plus regression evidence is
   complete.
5. The legacy `ability_concept` reverse-parser path does not exist, and tests
   prove that prose-only drafts remain `LEGACY_UNVERIFIED` rather than `PASS`.
6. Removal of the compatibility field, old response-contract version, or
   sidecar storage is a separate reviewed change with its own rollback plan.

Until all six conditions pass, the sidecar remains optional and the legacy
draft/result/verdict remains authoritative.

## 12. Rollback and recovery

Rollback is designed around the legacy path remaining intact:

1. Set the injected `CharacterSkillShadowConfig.mode` to `OFF` at the
   composition root. Do not add an environment-variable escape hatch inside
   the deep module.
2. Verify that the legacy provider call count, strict `CharacterDraft`,
   `CharacterGenerationResult`, `EvaluationRunner` result, repair path, and
   consumer inputs match the pre-shadow baseline.
3. Revert or disable the staged integration commits in reverse order. Do not
   delete the frozen S1.1 contract or its evidence.
4. No shadow data migration is required: sidecar observations are optional,
   keyed by `draft_id`, and can be retained as sanitized audit or ignored by
   legacy consumers.
5. If a dual-representation or consumer migration has already been reviewed,
   reverse it through a separately reviewed integration commit. Do not restore
   structured facts by parsing old `ability_concept` prose.

The rollback target is always a legacy-authoritative generation path with
shadow mode `OFF`; a failed shadow observation is not a reason to mutate Canon,
provider prompts, or the frozen S1 schema.

## 13. Ownership and review roles

| Owner | Owns | Does not own |
| --- | --- | --- |
| Sol | Interface interpretation, disagreement adjudication, acceptance gates, and final migration decision | Unreviewed provider behavior claims or private schema changes outside the frozen contract |
| Luna Worker | Test-first implementation of the allowlisted module, seams, containment, and migration slices | Final schema authority, Canon, Reference Corpus, or acceptance adjudication |
| DeepSeek (`deepseek-v4-flash`) | Candidate generation and real-provider evidence: format compliance, missing fields, repair stability, and drift | Schema ownership, production code, verdicts, or merge authority |
| Mimo v2.5 | Independent blind review and red-team evidence in CS-S3 | CS-S2 schema/code ownership, implementation, or final acceptance |

Sol adjudicates evidence against the frozen S1 contract and deterministic
tests. Luna implements only the allowlisted result. DeepSeek evidence remains
evidence, not authority. Mimo's blind review is deliberately deferred to
CS-S3 so it cannot become a hidden dependency of the CS-S2 implementation.

## 14. Acceptance checklists

### Commit 1 acceptance

- [ ] The only project file changed is
      `docs/character_generation/character_skill_cs_s2_execution_plan_v0.2.md`.
- [ ] The document is written in English and states
      **PLAN LOCKED; IMPLEMENTATION INCOMPLETE**.
- [ ] The document cites the frozen S1.1 contract, S1 evidence/adjudication,
      readiness report, and historical Phase 1-4 migration.
- [ ] The document names all actual generation, response-contract, strict
      draft/result, evaluation, validator, and repair seams.
- [ ] The deep-module decision, four public functions, shadow diagram, feature
      modes, compatibility invariants, error model, allowlists, rollout gates,
      dual-representation exits, rollback, ownership, and acceptance criteria
      are present.
- [ ] `git diff --check` passes.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_ci_quality.py` passes.
- [ ] The diff has no changes under `src/`, `tests/`, `evals/`, or config.
- [ ] The commit contains exactly one file and the worktree is clean.

### Overall CS-S2 acceptance

- [ ] The pure `src/character_skill/` deep module passes focused tests through
      only the four frozen public seams.
- [ ] `OFF` proves identical legacy provider call count, output, audit, draft,
      verdict, repair behavior, and consumer input.
- [ ] `RECORD_ONLY` proves stable `draft_id` linkage, independent response
      parsing, sanitized audit, and failure containment.
- [ ] All 19 frozen cases reproduce 19/19 outcomes and primary codes,
      including the case 13/case 19 distinction and case 14 fail-closed role
      behavior.
- [ ] Representation validation, request alignment, and repair run in the
      stated order and retain independent findings.
- [ ] Digest-bound, path-authorized repair accepts only an improved candidate
      after full recheck and cannot change the legacy repair path.
- [ ] Focused tests and the full project suite pass; no `src/` change escapes
      the staged allowlist.
- [ ] Sanitized real-provider DeepSeek evidence is retained before activation;
      Mimo's independent blind review is completed in CS-S3.
- [ ] The versioned dual-representation exit conditions are all reviewed
      before any consumer trusts SkillKit or `ability_concept` is removed.
- [ ] Sol records the acceptance decision. This plan alone does not mark CS-S2
      complete or authorize CS-S3/S4.

## 15. Plan lock statement

This document locks the CS-S2 shadow migration contract and its staged scope.
It authorizes implementation to proceed only through reviewed, allowlisted
commits. It does not change `src/`, tests, evals, configuration, the frozen S1
schema, the legacy `CharacterDraft`, or any consumer, and it does not mark
CS-S2 complete.
