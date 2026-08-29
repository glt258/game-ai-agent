# Character Skill Hybrid Semantic IR — End-to-End Success Baseline

## Freeze Status

```text
END_TO_END_SUCCESS = YES
MULTI_CASE_GENERALIZATION = NOT YET PROVEN
Production activation = OFF
Feature flag = OFF
RECORD_ONLY = true
```

This document freezes one real provider observation that passed the complete
Hybrid Semantic IR pipeline, including deterministic evaluation. It is a
shadow-evaluation baseline, not a production activation or a claim of
cross-case reliability.

## Git Baseline

```text
Branch: codex/cs-s2-role-refactor-compat-gate
Source HEAD: 93b77482e3d10e4678bf7566b136117a4c1f212b
Freeze commit: the Git commit that adds this document and the minimal README status update
Tag: hybrid-semantic-ir-e2e-v0.1
```

The source HEAD is the committed runtime/configuration baseline used for the
successful observation. No runtime or source logic is changed by this freeze.

## Architecture

```text
Request / Character Plan
    → Provider
    → SkillSemanticIR
    → IR Validator
    → Deterministic Semantic Compiler
    → Canonical Parser
    → Reference Integrity
    → Evaluator
    → Safe Evidence
```

The model supplies semantic design. The compiler supplies deterministic
mechanical representation. The evaluator remains strict and authoritative.

## Final Configuration

```ini
case = case_13_support_alignment_v1
provider = opencode_go
model = deepseek-v4-pro
timeout_seconds = 60
max_transport_retries = 0
repair_calls = 0
feature_flag = OFF
record_only = true

model_facing_contract = semantic-skill-plan-ir-contract/0.4.0
model_facing_contract_digest = 8af9427e06dc45b84c833510791c95522802c013c4be7ea5e63d423c4e8b1c5d
context_projection = hybrid-semantic-context-projection/0.2.0
context_projection_digest = 0362eebe8ed22e00ebdb627dda3c2475cb9a8be8f9ef648831825f409643691f
request = 1710 chars / 1710 bytes
ir_schema = semantic-skill-plan-ir/0.1.0
compiler = skillkit-compiler/0.1.0
canonical_schema = skill-kit-candidate/0.1.1
evidence = character-skill-s2-hybrid-ir-shadow/0.3.0
diagnostics = hybrid-safe-evaluator-diagnostics/0.1.0
```

## Real Provider Observation

```ini
run_id = cs-s2-hybrid-semantic-ir-v1-sample-01-40224fa07e23f4fe9c948d2bc06e292c4e4967f2ded3c308d6029f530e06224e
provider_calls = 1
transport_attempts = 1
latency = 25547 ms
```

Evidence remains local, ignored, append-only, and is not committed:

```text
evals/results/character_skill_s2_hybrid_ir_contract_v0_4_sample_01_v0.3.0.json
SHA-256: d52018d24f96899aa63eac2bea1d8318a9e2126e32aba6e229731f9c621dd8a3
```

Raw prompt, response, IR, candidate, expected values, and secrets are not
stored in the evidence.

## Full Pipeline PASS

```text
Provider               PASS
JSON                   PASS
IR_PARSE               PASS
IR_VALIDATION          PASS
COMPILER               PASS
CANONICAL_PARSER       PASS
REFERENCE_INTEGRITY    PASS
EVALUATOR              PASS
```

## Validation Baseline

```text
Full pytest: 1596 passed, 1 skipped
Intentional skip: tests/test_live_smoke.py
Ruff: PASS
compileall: PASS
git diff --check: PASS
```

## Engineering Integrity

- Evaluator strictness is preserved.
- No expected-answer leakage or hard-coded PASS behavior is used.
- No case-specific evaluator bypass was introduced.
- `feedback_received` remains a canonical structural trigger.
- Semantic capability is preserved; mechanical representation remains deterministic.
- The Hybrid Semantic IR architecture remains unchanged.

## Historical Evidence Integrity

The following evidence is permanently frozen and unchanged:

```text
Old H3:                57467dc9b24ffccc68fabfb8e40c6ef4bab845ae72de7b793f7a43e91114715a
Corrected baseline:    1f04b044806844ff724a08f21d395b0d5b4fe31aa498ee45d81f64d17b9e2efa
Replication sample-01: ff1b5a2b1563dc279b50b2dd007a13d6a335870bb2737190221145f7c78bdfd0
Replication sample-02: 421e329a25843dc96fe42a1498b58201a300e455cc66ed2af3a1554444ae18aa
Successful sample:    d52018d24f96899aa63eac2bea1d8318a9e2126e32aba6e229731f9c621dd8a3
```

```text
mutated = NO
```

## Known Scope Boundary

This baseline proves one real `case_13_support_alignment_v1` observation can
pass the complete Hybrid Semantic IR pipeline. It does not prove stability
across cases, roles, prompts, providers, models, or repeated observations.

## Production Status

```text
Feature flag: OFF
Production activation: OFF
RECORD_ONLY: true
```

Uploading this documentation and its tag does not activate the feature or
promote any candidate to production.

## Next Stage

```text
READY_FOR_MULTI_CASE_GENERALIZATION_VALIDATION
```

The next stage is multi-case generalization validation. It is not started by
this freeze.
