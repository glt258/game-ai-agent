# Skill Design v1 Feature Freeze

Status: `SKILL_DESIGN_V1_FEATURE_FROZEN`

Milestone: `CS-S2`

Freeze review: `APPROVED_FOR_FEATURE_FREEZE`

Runtime baseline: `9e2e8efac7544f2aa644a4c729e48540f7b7fc8d`

This document freezes the implemented Skill Design v1 scope. It records the
architecture, bounded offline verification, real live observations, known
limitations, and safety boundaries. It does not enable a production feature or
change runtime behavior.

## Frozen architecture

Skill Design v1 covers seven role/mechanic families:

- Support
- Main DPS
- Control
- Reaction / Healer
- Sub-DPS
- Defense
- Basic Passive

The supported semantic shapes are triggered mechanics, triggered mechanics
with optional feedback, and true triggerless `always_on` passives. The closed
semantic responsibilities include direct output, follow-up output, ally
enablement, control, recovery/mitigation, and threat protection.

The responsibility boundary is explicit:

> LLM owns gameplay semantics. Deterministic compiler owns representation mechanics.

The model supplies role responsibility, trigger/effect intent, passive versus
triggered choice, and feedback semantics where applicable. It does not supply
canonical IDs, `TypedRef` values, graph wiring, or other deterministic
representation details. Semantic IR remains a high-level gameplay semantic
representation, not a battle scripting DSL.

## Version matrix

| Component | Frozen version |
|---|---|
| Semantic IR | `semantic-skill-plan-ir/0.2.0` |
| Generation Contract | `semantic-skill-plan-ir-contract/0.7.0` |
| Context Projection | `hybrid-semantic-context-projection/0.3.0` |
| Compiler | `skillkit-compiler/0.2.0` |
| Diagnostics | `hybrid-safe-evaluator-diagnostics/0.2.0` |
| Repair Contract | `semantic-skill-ir-repair-contract/0.3.0` |
| Canonical SkillKit | `skill-kit-candidate/0.1.1` |

Runtime production settings remain `feature_flag=OFF` and `RECORD_ONLY=true`.
The bounded live configuration used for evidence was
`opencode_go / deepseek-v4-pro`, timeout 60 seconds, retries 0.

## Supported v1 coverage

The pipeline is:

```text
Authoritative Request / Plan Context
  → LLM
  → Semantic IR
  → IR Validation
  → Deterministic Compiler
  → Canonical SkillKit
  → Canonical Parser
  → Reference Integrity
  → Evaluator
  → Safe Evidence
```

For an evaluator semantic failure, the bounded repair path is:

```text
Evaluator FAIL → Semantic Repair (max 1) → Full Revalidation → Evaluator
```

Sub-DPS uses `deal_follow_up_damage → follow_up_output`; its core proof is
action-completed triggered follow-up output, not main-DPS direct output.

Defense uses `protect_ally → threat_protection`; healing, mitigation-as-healer,
and ally enablement do not substitute for the defense responsibility.

Basic Passive uses `kind=passive`, `persistence=always_on`, `mode=passive`, and
an effect with no activation trigger, feedback, continuation, lifecycle, or
resource mechanism. The compiler lowers this to a canonical protocol with
`when=null` and no feedback relation.

## Semantic Repair

Semantic Repair v1 remains bounded to one attempt and applies only after a
validated Semantic IR reaches evaluator failure. Provider failures, malformed
JSON, IR parse/validation failures, compiler failures, and reference-integrity
failures are not automatically repaired.

Historical Reaction evidence proves real bounded repair feasibility:
initial evaluator failure → one repair → full pipeline revalidation → PASS.
This is feasibility evidence, not a universal repair success-rate claim.

## Offline verification

The frozen runtime was verified before this documentation-only freeze:

- Focused tests: `92 passed`
- Full pytest: `1636 passed, 1 skipped`
- Clean tracked-only checkout: `1636 passed, 1 skipped`
- Ruff: PASS
- `compileall src scripts`: PASS
- `git diff --check`: PASS

Sub-DPS, Defense, and Basic Passive each have a hand-authored v2 golden,
formal FakeProvider E2E PASS, negative tests, and bounded repair smoke. These
fixtures prove pipeline acceptance and deterministic system correctness; they
do not prove universal real-model elicitation reliability.

## Real live evidence

Historical families:

| Family | Real observation |
|---|---|
| Support | E2E PASS evidence exists |
| Main DPS | Recurrent evaluator semantic misses in mechanic skeleton, feedback relation, and role evidence |
| Control | E2E PASS evidence exists |
| Reaction / Healer | Continuation-family semantic miss; historical bounded repair reached PASS |

Final three-family initial-generation gate, source commit
`9e2e8efac7544f2aa644a4c729e48540f7b7fc8d`, used exactly three real provider
calls with no retry and no repair:

| Family | Provider | Furthest layer | Evaluator | Classification |
|---|---|---|---|---|
| Sub-DPS | PASS | `IR_PARSE` | NOT_RUN | `IR_PARSE_FAIL` |
| Defense | PASS | `IR_PARSE` | NOT_RUN | `IR_PARSE_FAIL` |
| Basic Passive | PASS | `EVALUATOR` | PASS | `E2E_PASS` |

The Sub-DPS and Defense observations support only the statement that
real-model structured Semantic IR elicitation failed at IR parsing for these
N=1 observations. They do not support claims about an exact invalid field or
value. The Basic Passive observation is stronger: a real model produced valid
triggerless Semantic IR v2 that traversed the deterministic compiler,
canonical parser, reference-integrity check, and evaluator successfully.

## Known limitations

### KL-SKILL-001 — DPS first-pass semantic reliability

Small real samples contain recurrent DPS evaluator semantic misses. Offline
golden and FakeProvider paths pass; DPS is not claimed to be ineligible.

### KL-SKILL-002 — Sub-DPS real-model IR elicitation

The final N=1 observation stopped at `IR_PARSE`. Offline architecture support is
proven, but real E2E success is not yet demonstrated.

### KL-SKILL-003 — Defense real-model IR elicitation

The final N=1 observation stopped at `IR_PARSE`. Offline architecture support is
proven, but real E2E success is not yet demonstrated.

### KL-SKILL-004 — Provider latency / repair availability

DeepSeek V4 Pro has historical bounded timeout/unavailable signals under the
existing 60-second configuration. Compact repair requests reduce request
burden, but repair availability remains only partially evidenced.

### KL-SKILL-005 — Small-sample live evidence

All live observations are controlled small-sample evidence. They do not imply
benchmark superiority, universal model quality, production success rate, or
statistical reliability.

## Deferred v2 scope

The freeze does not implement summon, resource engines, stacks, generic states,
transformations, multi-stage skills, multi-role composition, complex passive
procs, chained feedback, cooldown economy, aura systems, periodic ticks, proc
probability, numeric formulas, scaling, arbitrary conditions DSL, custom
operations, or script expressions.

Basic Passive v1 intentionally remains limited to a static, triggerless,
always-on, role-supporting effect. Conditional passive engines, timed or
periodic procs, stacks, resources, and state-machine passives are future scope,
not defects in this freeze.

## Evidence and safety policy

Live evidence remains local, ignored, untracked, and uncommitted. Evidence
stores only identities, bounded stage outcomes, safe diagnostics, latency, and
provider audit metadata. Raw prompts, raw responses, raw IR, canonical
candidates, and secrets are not stored. Historical evidence, cohorts, and run
IDs are immutable and were not migrated or rewritten.

## Git and release marker

This freeze is documentation-only. The freeze commit contains only this
document and the minimal README status/link update; no `src/`, `tests/`,
`evals/`, or runtime configuration changes are included.

The annotated local tag is `skill-design-v1`. It points to the freeze commit,
not the pre-freeze runtime commit. Push is intentionally not performed.

Feature Complete means:

> V1 architecture and intended coverage are implemented, validated offline, and bounded live evidence has been collected.

It does not mean that every supported family has demonstrated reliable
first-pass real-model E2E generation.
