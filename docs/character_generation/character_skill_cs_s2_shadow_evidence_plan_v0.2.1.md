# Character Skill CS-S2 Shadow Evidence and Rollout Protocol v0.2.1

Status: **PROTOCOL LOCKED; LIVE EVIDENCE PENDING**

This document is the incremental evidence contract for CS-S2. It records the
inputs, projections, provider boundary, evidence shape, gates, and rollback
rules required before a production rollout decision. It does not call a live
provider, enable a feature flag, change the legacy generation path, or
authorize consumer migration.

The historical execution plan remains unchanged and remains the staged
implementation authority. This document adds the evidence protocol; it does
not replace, rewrite, or re-version that historical plan.

## 1. Authority and current gaps

### Normative authority

The CS-S1.1 interface contract owns the provider surface, the
`skill-kit-candidate/0.1.1` schema, typed references, evaluator-owned findings,
repairability, digest-bound patches, one-way rendering, and the 19-case
semantics:

`docs/character_generation/character_skill_interface_options_v0.1.1.md`

The retained S1 review and Sol adjudication are recorded in:

`evals/results/character_skill_s1_blind_review_report_v0.1.1.md`

The historical CS-S2 implementation sequence and exclusions are recorded in:

`docs/character_generation/character_skill_cs_s2_execution_plan_v0.2.md`

If this protocol conflicts with the S1.1 contract or the historical plan, the
earlier authority wins and this protocol must be revised as a separately
reviewed version.

### Recomputed input and authority digests

The following SHA-256 values were recomputed from the repository bytes at the
start of Commit A. They are provenance anchors, not provider input by
themselves.

| Role | Path | SHA-256 |
| --- | --- | --- |
| Private S0 oracle fixture; evaluator-only | `evals/fixtures/character_skill_failure_cases_v0.1.1.json` | `5c9c19d816c4824408c5265bc885a27716b6e29425f668a00864a82f8e63ed2b` |
| S0 non-oracle request/observation input | `evals/fixtures/hermes_character_skill_s0_blind_cases_v0.1.1.json` | `055505916bf82fc60cb55d2deb84b9aaacd7028431ac5d38d2f84791dd77fe90` |
| S1 public candidate/context projection | `evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json` | `11e936df853927154ace426c3a22e073b739b9b1dce536817851f70cf855ec04` |
| S1 private candidate/context fixture; evaluator-only | `evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.json` | `931c4293f9f6f6e66b3635aca744bb1253f3a8f003b86b98b9657d3096d1eacd` |
| S1 blind-review prompt | `evals/fixtures/character_skill_s1_blind_review_prompt_v0.1.1.md` | `1df9184f9bd681e814a54abbd9f63c137887897ed4faec7937f7e5fd4954435` |
| S1 blind-review output schema | `evals/fixtures/character_skill_s1_blind_review_output_schema_v0.1.1.json` | `9989ea7c20feadbbd2c54b8cd18cfcdbcb18b8047711df511c8beb5ade46e661` |
| S1 input manifest | `evals/fixtures/character_skill_s1_blind_review_input_manifest_v0.1.1.json` | `4c405367318a085ce2c65e6ae10367bde5927cfef9382986c4506a30761d0e1b` |
| S0.1 frozen specification | `docs/character_generation/character_skill_failure_cases_v0.1.1.md` | `ae08585ee42d8c1cbd3c0ac694d245c948d5894a0b4b4453eec55d27809392ef` |
| S1.1 contract | `docs/character_generation/character_skill_interface_options_v0.1.1.md` | `4f6fd4d8f63498b7d56df42c8ee4f15a979fb1e65b091d84ed2a6d1fad01f0b3` |
| S1 review/adjudication | `evals/results/character_skill_s1_blind_review_report_v0.1.1.md` | `a1959e6cc30c9d48639cc57ecb8f4948ba3ff36c74e2251631d6e5b7396a1433` |
| Historical CS-S2 plan | `docs/character_generation/character_skill_cs_s2_execution_plan_v0.2.md` | `62b479f7f5acc710bbcc6e8721c5ebc2bdb57a389c3e542ac7d768ef495f65c1` |

The evidence runner must record the source commit and the exact fixture
digests it used. A digest mismatch is a stop condition, not a reason to
silently refresh a fixture.

### What is true in the current repository

The current production path already contains a bounded, optional shadow call:
`CharacterGenerationAgent._generate_skill_shadow` is invoked after the legacy
draft validates; it requests the `character_skill_kit` contract and keeps a
`CharacterSkillShadowResult` beside the legacy result. The current
`SkillShadowConfig` is a boolean `enabled=False`, not an `OFF`/`RECORD_ONLY`
mode enum. This document must not be read as claiming that the mode enum or a
production evidence runner already exists.

The current shadow evaluator supplies `combat_role_profile` when available,
but currently passes empty arrays for `mechanic_requirements`,
`forbidden_mechanic_families`, and `hard_constraint_conflicts`, and passes no
`reference_review_context`. Therefore current shadow observations do not prove
request-alignment coverage or reference-copying coverage. This is a real gap.

The current legacy `repair_once` path is not a SkillKit patch-provider
contract. There is no independent live patch response contract or complete
shadow repair orchestration authorized by this document. Those are future work
and must not be inferred from the existing legacy repair behavior.

The verified provider profile for the intended baseline is `opencode_go` with
model `deepseek-v4-flash`, transport family `openai_chat_completions`, and
`json_object` structured-output capability. The target request budget is a
30-second timeout with at most two transport retries. This profile does not
provide a basis for claiming wire-level `json_schema` support. Existing
`ModelInvocationAudit` fields and logs must not be treated as the normalized
CS-S2 evidence contract: in particular, this protocol does not claim that the
current shadow audit already has separate requested/reported model fields or
latency/token evidence fields.

## 2. Scope, non-goals, and rollout state

### In scope

This protocol locks the future sanitized evidence run for the DeepSeek
baseline. It fixes the provider role, input projections, run identity, resume
semantics, normalized evidence JSON, sanitization allowlist, quality gates,
stop conditions, and rollback target.

Real-provider evidence, when the later implementation gates are complete, is
run only in `RECORD_ONLY`. The feature remains disabled by default. Commit A
itself performs no live call.

### Explicit non-goals

CS-S2 evidence does not:

- change Canon, Canon authority, the Reference Corpus, or any reference record;
- tune numerical balance, damage, cooldown, frame, or runtime combat values;
- modify the legacy `CharacterDraft`, `ability_concept`, legacy verdict,
  legacy repair loop, or consumer input;
- send private oracle material, copying fingerprints, or raw evidence to a
  provider;
- make a provider-authored verdict or repairability claim authoritative;
- enable a default-on flag or begin consumer migration; or
- perform the CS-S3 independent MiMo blind review.

The final CS-S2 decision is not a new frozen schema state. The only permitted
final evidence decisions are `CS-S2 SHADOW EVIDENCE ACCEPTED` and
`CS-S2 SHADOW EVIDENCE NEEDS REPAIR`.

## 3. Roles and authority boundaries

| Actor or seam | Role in this protocol | Boundary |
| --- | --- | --- |
| Sol and deterministic tests | Interpret the S1.1 contract, adjudicate evidence, and make the final CS-S2 decision | Cannot silently widen the provider schema or treat model text as authority |
| Luna Worker | Implement only separately allowlisted Commit B/C/D/E/F work after review | Does not own Canon, schema authority, or final acceptance |
| `opencode_go` / `deepseek-v4-flash` | Baseline candidate generator and evidence source | Generates a candidate only; it is not a judge, oracle, repairability source, or merge authority |
| `mimo-v2.5` | Independent blind reviewer reserved for CS-S3 | Does not participate in CS-S2 implementation, prompt tuning, or acceptance |
| Provider transport adapter | Performs one bounded request using the locked transport budget | May report transport facts but cannot turn an error or model claim into a semantic verdict |
| SkillKit parser/evaluator | Owns shape parsing, deterministic findings, repairability, and report digests | Receives explicit context; never delegates semantic authority to the provider |
| Future patch provider | Generates one bounded `character_skill_patch` only under Commit E | Sees only authorized candidate/finding data and never oracle answers or reference fingerprints |

The provider cannot submit `expected`, finding codes, request requirement IDs,
`satisfies`, role labels outside the candidate contract, corpus matches,
copying fingerprints, verdicts, or repairability declarations.

## 4. Locked provider contract and transport budget

The future baseline cohort uses this exact profile:

| Field | Locked value | Meaning |
| --- | --- | --- |
| Logical provider | `opencode_go` | Provider profile used by the adapter |
| Requested model | `deepseek-v4-flash` | CS-S2 baseline generator; no MiMo in this cohort |
| Transport | `openai_chat_completions` | OpenAI-compatible chat-completions transport family |
| Wire structured-output mode | `json_object` | JSON object mode only; do not claim `json_schema` wire support |
| Response contract | `character_skill_kit` | Provider-facing contract name |
| Candidate schema version | `skill-kit-candidate/0.1.1` | Direct root candidate shape owned by S1.1 |
| Timeout | `30` seconds | Per transport attempt |
| Maximum transport retries | `2` | At most three total attempts for one logical observation |

The provider must return one direct root JSON object for the
`character_skill_kit` call. An envelope, markdown, prose, `ability_concept`,
`skill_kit` wrapper, unknown field, or unsupported schema version is not a
successful direct-root observation. The response is parsed by the strict
SkillKit contract and is never accepted because the provider calls it valid.

The timeout and retry values are protocol requirements for the future runner;
they do not prove that a current repository shadow observation has recorded
those metrics. Transport retries are bounded independently of any future
semantic repair call.

## 5. Frozen inputs and non-oracle projections

### Provider projection

For each case, the provider projection contains only the request-owned public
brief and constraints needed to generate a candidate:

- `brief`;
- `hard_constraints`;
- `forbidden_elements`; and
- the canonical `combat_role_profile`, when present.

The runner may carry `case_id` and the stable run metadata outside the prompt
for joining evidence, but the provider must not receive hidden expected
outcomes through that metadata.

The following are never sent to the provider, even when they exist in a local
fixture or an evaluator object:

- `candidate_observation` from the Hermes S0 input;
- the public S1 `candidate` object;
- the private oracle, including `expected`, finding codes, repairability, or
  adjudication rationale;
- any Reference Corpus text, record ID used as a copying fingerprint, or
  reference fingerprint; and
- any legacy draft, raw legacy provider response, or secret-bearing context.

The provider sees no oracle candidate. It generates a new candidate; it is not
asked to reproduce an S0/S1 observation.

### Evaluator projection

The evaluator receives the generated candidate and an explicit, request-owned
validation context. The public S1 fixture supplies the evaluator-side shape of
that context for the 19 case IDs. Private oracle material is retained for
deterministic adjudication and tests only; it is not a live provider input.

Until the explicit request-context seam is implemented, the current empty
mechanic/forbidden/conflict arrays mean that only the measured structural and
role portions of an observation can be described as covered. A report must
mark request alignment as unmeasured rather than claiming full coverage.

`reference_review_context` belongs to the evaluator only. If future copying
checks use it, the evaluator stores only the sanitized digest and finding
summary; no reference fingerprint crosses the provider boundary.

## 6. Cohort, smoke cases, run IDs, and resume rules

The baseline cohort is exactly 19 cases with three repeats each: **19 x 3 =
57 observations**.

The runner executes these smoke cases first:

- `case_01`: complete resource-loop control;
- `case_13`: missing mechanic-skeleton risk; and
- `case_19`: trigger/effect present but feedback risk.

The smoke run is a gate on projection, shape, sanitization, and evaluator
containment. It must not send the fixture's candidate observation to the
provider, and it must not force a generated candidate to match the fixture.
The frozen semantic distinction remains: an absent skeleton is not a locally
repairable missing feedback relation.

Future result files have fixed names:

```text
evals/results/character_skill_s2_shadow_deepseek_run_01_v0.2.1.json
evals/results/character_skill_s2_shadow_deepseek_run_02_v0.2.1.json
evals/results/character_skill_s2_shadow_deepseek_run_03_v0.2.1.json
```

The deterministic run-ID format is:

```text
cs-s2-shadow-deepseek-v0.2.1-<source_commit>-<manifest_sha256_12>-run-<01..03>
```

An observation ID is the run ID plus `case_id` and repeat number. A timestamp
or random UUID cannot be the identity. The runner records the complete source
commit and input manifest digest in addition to the compact run ID.

Resume is append-only and identity-preserving:

1. An existing observation with the same observation ID is never overwritten.
2. A valid existing observation is rechecked by digest and then skipped.
3. A missing observation may be generated with the same run ID and repeat
   number.
4. A present observation with a different source, input, or protocol digest
   stops the run; it is not replaced in place.
5. A partial or interrupted run preserves completed observations and records a
   stable sanitized failure for the incomplete item before resuming.

## 7. Normalized evidence JSON contract

Commit C must implement a versioned schema equivalent to the following
contract. The contract is a future evidence-run shape, not a claim about the
current `CharacterSkillShadowResult` or `ModelInvocationAudit` shape.

```json
{
  "schema_version": "character-skill-s2-shadow-evidence/0.2.1",
  "run_id": "cs-s2-shadow-deepseek-v0.2.1-<source_commit>-<manifest_sha256_12>-run-01",
  "protocol_version": "0.2.1",
  "source_commit": "<full git sha>",
  "input_manifest_digest": "<sha256>",
  "inputs": [{"path": "<repo-relative path>", "sha256": "<sha256>", "role": "provider|evaluator|oracle-only"}],
  "provider": {
    "name": "opencode_go",
    "model_requested": "deepseek-v4-flash",
    "model_reported": "<sanitized value or null>",
    "transport": "openai_chat_completions",
    "structured_output_mode": "json_object",
    "response_contract": "character_skill_kit",
    "candidate_schema_version": "skill-kit-candidate/0.1.1",
    "timeout_seconds": 30,
    "max_transport_retries": 2
  },
  "observation": {
    "observation_id": "<stable id>",
    "case_id": "case_01",
    "repeat": 1,
    "draft_id": "<legacy draft id>",
    "transport_outcome": "success|failure",
    "failure_stage": "<stable stage or null>",
    "failure_code": "<stable code or null>",
    "shape_compliant": true,
    "parse_outcome": "parsed|rejected|not_attempted",
    "outcome": "PASS|REPAIR|FAIL|UNAVAILABLE",
    "finding_codes": [{"code": "<frozen code>", "path": "<json pointer>"}],
    "candidate_digest": "<sha256 or null>",
    "context_digest": "<sha256>",
    "report_digest": "<sha256 or null>",
    "renderer_comparison": {"performed": false, "matches_legacy": null, "summary_code": "not_authoritative"},
    "legacy_impact": false
  },
  "audit": {
    "redacted_request_id": "redacted:<bounded value or null>",
    "retry_count": 0,
    "latency_ms": null,
    "token_usage": {"input": null, "output": null, "total": null}
  },
  "sanitization": {"raw_prompt_stored": false, "raw_response_stored": false, "secrets_detected": false}
}
```

The runner must keep `model_requested` and `model_reported` separate. A
reported model string is provenance only and cannot change the locked cohort.
`latency_ms` and token counts are nullable because a provider may not supply
them; their presence in this future contract must not be confused with an
existing shadow audit guarantee. Raw transport errors are mapped to stable
failure stages/codes. Raw response text, exception text, and unrestricted
provider messages are not fields in this contract.

`outcome` is an evaluator result, not provider output. The provider cannot
emit or override it. `legacy_impact` must be exactly `false` for every
observation; a true value is a hard stop.

## 8. Sanitization allowlist and forbidden material

Only the following bounded data may survive into an evidence artifact:

- protocol/schema version, run and observation IDs, case ID, repeat number,
  source commit, and fixture paths/digests;
- `draft_id` and a redacted request ID;
- provider name, requested/reported model, transport family, response mode,
  contract/schema versions, bounded retry count, and nullable numeric timing or
  usage values;
- transport outcome, stable failure stage/code, direct-root/shape/parse
  booleans, evaluator outcome, frozen finding code/path pairs, and bounded
  digest values;
- renderer comparison summary without either source text; and
- explicit containment booleans, including `legacy_impact=false`.

The artifact must contain none of the following:

- original prompts, message history, raw provider responses, raw tool output,
  candidate prose, or unbounded exception text;
- `candidate_observation`, public candidate payloads, private oracle fields,
  expected outcomes, adjudication rationale, or Reference Corpus text and
  fingerprints;
- API keys, passwords, access tokens, cookies, private keys, complete
  environment variables, authorization headers, or secret-bearing URLs; or
- a provider-authored verdict, repairability claim, or unauthorized patch.

Sanitization failure is itself a stable failure code. It cannot fall back to
writing the unsanitized body.

## 9. Acceptance gates

### Zero-tolerance containment gates

The following counts must all be zero across smoke and full cohorts:

- legacy draft changed by shadow;
- legacy verdict changed by shadow;
- shadow provider call while the feature is disabled;
- raw provider response or prompt leakage;
- secret, API key, cookie, private key, or complete environment leakage;
- an observation that cannot be joined to its `draft_id`;
- unauthorized repair-provider call;
- unauthorized patch accepted; and
- provider output treated as evaluator verdict or repairability fact.

Any non-zero count invalidates the cohort and triggers stop/rollback review.

### DeepSeek quality gates

For the 57-observation baseline cohort, all of the following are required:

- at least **55/57** direct-root JSON responses;
- at least **55/57** strict shape parses;
- at least **2/3** strict shape parses for every case;
- every successfully parsed candidate produces a deterministic evaluator
  report;
- repeated evaluation gives the same report digest and finding order for the
  same candidate/context;
- every case has the same outcome family in at least **2/3** repeats; and
- unknown fields, legacy envelopes, and missing required fields do not show a
  systematic concentration in one case.

The three repeats need not have identical candidate digests. The gate measures
contract compliance, semantic report stability, and bounded failure modes, not
forced generation sameness.

The smoke gate must explicitly preserve the S1.1 case-13/case-19 boundary and
retain case 01 as the complete resource-loop control. It must also show that
the case-13/14/15 repair-provider eligibility rule is not bypassed when Commit
E is later implemented.

## 10. Stop, rollback, and recovery

Stop the current run immediately on any zero-tolerance violation, fixture or
source digest mismatch, provider/model/transport drift, timeout or retry
budget violation, raw-material exposure, unstable resume identity, or evidence
file overwrite. Stop also when a smoke case cannot establish the required
projection and containment checks.

The rollback target is the legacy-authoritative path with the shadow disabled:

1. Set the composition-root shadow setting to its disabled value. Do not add
   an environment-variable escape hatch inside `src/character_skill/`.
2. Confirm that legacy provider calls, output, audit, `CharacterDraft`,
   verdict, repair behavior, and consumer inputs match the pre-shadow path.
3. Disable or revert only the reviewed rollout integration commits in reverse
   order. Do not delete the S1.1 contract, its evidence, or the historical
   plan.
4. Retain only sanitized sidecar evidence; no legacy data migration is
   required. A failed shadow record is ignored by legacy consumers.
5. A failed evidence cohort is reported as `CS-S2 SHADOW EVIDENCE NEEDS
   REPAIR`; it is not relabeled as a frozen state and does not authorize
   consumer migration.

## 11. Future commit boundaries

The following requirements are future implementation work. They are locked by
this protocol but are not claimed to exist in Commit A.

| Commit | Required work | Required boundary |
| --- | --- | --- |
| A (this document) | Lock the evidence protocol and digests | No live provider; no source/test/eval/config change |
| B | Add an explicit request-owned validation context seam, such as `generate(request, *, skill_shadow_context: SkillValidationContext | None = None)` | Flag-off behavior ignores the context; `None` may measure structure only and must mark request alignment unmeasured; context digest is audit metadata; reference context is evaluator-only; no reverse inference from `ability_concept` |
| C | Add a reproducible runner, manifest, output schema, smoke selection, `--live`, `--case-id`, append-only resume, stable run IDs, and sanitizer tests | Default runner never calls a live provider; requested/reported provenance and nullable latency/usage fields are normalized here, not retroactively claimed in current audits |
| D | Execute the DeepSeek baseline: smoke first, then 19 x 3 | Record-only evidence only; 57 observations; no default-on flag; no MiMo |
| E | Add independent `character_skill_patch` generation and bounded shadow repair | Call only for `REPAIR` with all findings repairable; case 13/14/15 calls are zero; maximum one patch-provider call; no oracle/reference fingerprint; full parse/evaluate after patch; only final `PASS` is retained; legacy remains untouched |
| F | Produce the sanitized report and Sol adjudication | Final status is exactly `CS-S2 SHADOW EVIDENCE ACCEPTED` or `CS-S2 SHADOW EVIDENCE NEEDS REPAIR` |

The future patch contract is independent of `character_skill_kit` and Canon
repair:

```json
{
  "base_digest": "<candidate digest>",
  "report_digest": "<report digest>",
  "operations": [
    {"op": "add", "path": "/feedback_relations/-", "value": {}}
  ]
}
```

Only evaluator-authorized paths are permitted. `remove`, `move`, `copy`, root
patches, path-prefix expansion, wrong digests, and patches outside the report
are rejected. A patch provider sees only the candidate digest, report digest,
finding code/path, and authorized paths. It never sees an oracle answer or
Reference Corpus fingerprint. A rejected or unsuccessful patch cannot affect
legacy repair or legacy output.

## 12. Protocol lock statement

This protocol locks the CS-S2 shadow evidence boundary for the next reviewed
implementation commits. At this point live evidence is pending, the feature
flag remains disabled by default, DeepSeek remains a baseline generator rather
than a judge, and MiMo remains reserved for CS-S3. No provider has been
called, no raw response is retained, and no consumer may trust the shadow
result until Sol records one of the two permitted final decisions.
