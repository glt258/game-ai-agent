# Character Authoring Pipeline v0.6.6 — Runtime Freeze

## Status

```text
Character Authoring Pipeline v0.6.6

Status:
READY_FOR_DEMO

Runtime:
FROZEN
```

This manifest freezes the already accepted Runtime baseline. It does not
introduce Runtime behavior changes.

## Frozen Baseline

```text
Branch: codex/character-generation-agent
Runtime baseline commit: e85569b1638fe48e8d2857ac60bef1f67a1deb5b
Freeze commit: see final freeze report; intentionally not embedded here
Version: 0.6.6
Date: 2026-08-15
```

The Runtime baseline is the `e85569b fix: unify compound absence resolution`
commit. At freeze preparation, the only pre-existing working-tree item was the
user-owned untracked `IDEA.md`; it was not modified, staged, or committed.

## Frozen Components

- `CharacterGenerationAgent`
- `CanonChecker v0.1.6`
- `CharacterRepairAgent`
- `CharacterAuthoringWorkflow`
- Hard Constraint Preservation
- Repair Scope Validation
- Recommended Draft Selection
- Provider Capability Layer
- Structured Output Contract
- NPC Permission Runtime
- NPC Grounding Runtime

## Pipeline

```text
CharacterDesignRequest
        ↓
CharacterGenerationAgent
        ↓
CharacterDraft
        ↓
CanonChecker
        ↓
PASS / WARN / FAIL
        ↓
CharacterRepairAgent (max once)
        ↓
CanonChecker
        ↓
Recommended Draft
        ↓
Human Review
```

Passing Checker does **not** promote a Draft to Canon.

## Freeze Invariants

### Canon

```text
CharacterDraft != Canon
No automatic Canon writes.
Human approval remains authoritative.
```

### Generator

```text
Generator may propose.
Generator may not promote proposals into Canon.
```

### Checker

```text
CanonChecker remains deterministic.
No LLM Judge.
No embedding similarity.
```

### Repair

```text
At most one semantic repair attempt.
Repair may not silently violate hard constraints.
Repair may not escape editable scope.
```

### Runtime

```text
LLM proposes.
Runtime validates.
Permission Resolver authorizes.
Tool executes.
Grounding validates.
```

## Acceptance Evidence

The following results were freshly executed before freeze documentation was
created:

| Check | Result |
| --- | --- |
| `py -m pytest -q` | `466 passed, 1 skipped` |
| NPC eval | `23/23 passed` |
| Character Generation eval | `13/13 passed` |
| Canon Checker eval | `14/14 passed` |
| Canon Live-language eval | `91/91 correct; 0 false positives; 0 false negatives` |
| Canon Red-Team | `22/23 correct; H2 is the sole known limitation` |
| Character Repair eval | `16/16 passed` |
| Character Repair Red-Team | `21/21 correct` |

## Validation and Integrity Evidence

Fresh pre-freeze checks:

```text
compileall: PASS
knowledge/data validator: PASS
story validator: PASS
project validator: PASS
case validator: PASS
incident validator: PASS
authorization validator: PASS
scope validator: PASS
responsibility validator: PASS
git diff --check: PASS
secret-pattern scan: PASS (no high-confidence matches)
```

Canon/Data integrity uses a deterministic SHA-256 manifest of all 18 files
under `data/`, sorted by normalized relative path, followed by a SHA-256 of
the path-and-file-hash lines:

```text
Canon/Data tree hash before:
614c25d213799a97aef954e16145c587826768e828eba5f38523c8d5c7e4f487
```

The after hash is recorded in the final freeze report and must equal the value
above.

## Final Live Acceptance Reference

Live acceptance was completed before this freeze. This section records that
existing evidence; no Live API is called as part of the freeze.

```text
Final Live Acceptance: PASS
Provider: opencode_go
Model: deepseek-v4-flash
Live Smoke: PASS
Normal L1: PASS, 0 findings
Repair: not required
Recommended Draft: original
```

Previously observed acceptance evidence:

```text
Repairable L2: real findings → one minimal repair → PASS
Impossible Brief: remained FAIL
Adversarial Repair: scope violation rejected
```

## Known Limitations

These are frozen as backlog items. They are not being fixed in this freeze.

### KL-001 — H2 extractive support contract

`canon_basis.supports` uses a deterministic extractive support contract.
Free paraphrase or composed support may produce `UNSUPPORTED_CANON_CLAIM`.

```text
Status: KNOWN LIMITATION
NOT A DEMO BLOCKER
```

### KL-002 — Canon entity-resolution recall

Partial/exact-name Canon entity resolution recall is limited; some partial
names or aliases may not be found by the deterministic inventory.

```text
Status: BACKLOG
NOT A CURRENT DEMO BLOCKER
```

### KL-003 — Embedded proposal phrase

Phrases such as `拟议新角色：<existing division>资深导师` can still reach
proposal-classification edge cases when an entity is embedded in a complex noun
phrase.

```text
Status: BACKLOG
```

### KL-004 — Retrieval efficiency

Real Live runs previously observed roughly 20–30+ tool calls and roughly
28–42 sources. These are observations, not a strict SLA.

```text
Status: EFFICIENCY BACKLOG
CORRECTNESS NOT BLOCKED
```

### KL-005 — Provider transients

Timeouts, empty assistant responses, and tool-loop exhaustion were observed in
real Live operation. The Runtime fails closed for these conditions.

```text
Status: OPERATIONAL BACKLOG
```

## Deferred / Post-Freeze Work

The following work is recorded only and is not implemented by this freeze:

- H2 support-key / semantic support evolution
- Canon entity alias resolution
- Retrieval budget / stop condition
- Source-use efficiency
- Provider resilience tuning
- Demo packaging
- Portfolio documentation

## Change Policy

### Allowed without unfreezing core

The following are allowed when they do not change Runtime behavior:

- README edits
- Documentation
- Architecture diagrams
- Demo wrapper
- CLI presentation
- Logging presentation
- Examples
- CI configuration
- Packaging metadata

### Requires Runtime unfreeze

- Generator behavior change
- Checker semantic change
- Repair behavior change
- Provider contract change
- Grounding behavior change
- Permission behavior change
- Canonical schema change
- Hard-constraint behavior change
- Tool-loop policy change

## Bug Severity Policy

After Runtime freeze, only P0/P1 correctness or safety issues automatically
warrant consideration of an unfreeze, including Canon mutation, hard-constraint
bypass, security-boundary bypass, incorrect recommended Draft selection, or a
systematic happy-path failure.

Isolated wording edge cases, efficiency issues, cosmetic output, and
non-blocking provider transients do not automatically unfreeze the Runtime.

## Release and Tag Policy

Version remains `0.6.6`; freeze does not bump the Runtime version. If `v0.6.6`
is absent, the freeze commit receives this annotated tag:

```text
git tag -a v0.6.6 -m "Character Authoring Pipeline v0.6.6 - READY_FOR_DEMO"
```

An existing `v0.6.6` tag must not be overwritten or force-moved. Nothing is
pushed by this freeze.

## Scope Confirmation

```text
No Generator changes.
No Canon Checker behavior changes.
No Repair changes.
No Provider changes.
No Retrieval changes.
No Grounding changes.
No Permission changes.
No Canon/Data changes.
No schema changes.
No H2 fix.
No entity-resolution redesign.
No second Repair.
No Planner.
No Memory.
No Multi-Agent.
```

## Final Verdict

```text
Character Authoring Pipeline v0.6.6
READY_FOR_DEMO
RUNTIME FROZEN
```
