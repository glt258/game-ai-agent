# Character Repair Loop v0.1

## Purpose

This milestone closes the bounded authoring loop:

```text
CharacterDesignRequest
    -> CharacterGenerationAgent
    -> CharacterDraft v1
    -> CanonChecker
    -> CharacterRepairAgent (zero or one attempt)
    -> CharacterDraft v2
    -> CanonChecker (full deterministic re-check)
```

The Generator is creative, the Checker is deterministic, and the Repair Agent
is bounded. Passing the Checker does not promote a draft into Canon.

## Repair request and result

`CharacterRepairRequest` contains the immutable original request, the complete
current draft, the complete `CanonCheckReport`, and bounded projections of the
finding-related Canon sources.

`CharacterRepairResult` records the original and candidate drafts, both check
reports, `changed_fields`, the recommendation, model audit metadata, and a
stable status such as `REPAIRED_PASS`, `IMPROVED_BUT_FAILED`,
`REPAIR_SCOPE_VIOLATION`, or `REPAIR_MODEL_FAILED`.

## Minimum-change policy

The provider must return the complete CharacterDraft root object. Runtime then
computes a deterministic top-level diff. Only finding fields and a small,
explicit dependency map are editable. `draft_id`, `status`, and
`canonical_character_id` are always frozen. Identity fields and fields named by
the original hard constraints are frozen unless the request explicitly makes a
safe repair possible; the final Checker still evaluates all constraints.

New Canon source IDs must be in the original draft or the evidence allowlist.
Relationship targets are similarly allowlisted. Required design text cannot be
silently deleted to make a finding disappear.

## Evidence boundary

`RepairEvidenceBuilder` reads only real read-only registries through the
existing `CanonChecker` context. It includes finding evidence and directly
related draft sources, projected to small fields such as faction public role,
authority limits, Canon constraints, or a Lore statement. Player text, draft
claims, model history, fake tool results, and full Canon dumps are not repair
evidence. The repair prompt has `available_tools=()`.

## One-attempt and re-check semantics

`MAX_REPAIR_ATTEMPTS = 1`. PASS drafts skip the model; WARN and FAIL drafts are
eligible for one repair (INFO-only reports are not). Provider transport retries
remain the adapter's concern and do not create another semantic repair.

Every valid candidate is checked against the full deterministic rule set, not
just the original findings. A candidate that improves a FAIL but remains FAIL
is reported as `IMPROVED_BUT_FAILED`. A regression or invalid candidate leaves
the original draft as the recommendation. The workflow's final draft and final
report always correspond.

## Offline demo and tests

```powershell
py scripts/demo_character_repair_v0_1.py --case subtle
py scripts/demo_character_repair_v0_1.py --case bad
py scripts/demo_character_repair_v0_1.py --case unrepairable
py scripts/run_character_repair_evals.py
py -m pytest -q tests/test_character_repair.py
```

The deterministic repair model covers proposal separation, authority and
knowledge overreach, story-role overreach, RULE-024-style minor frontline
repair, forbidden structures, impossible briefs, scope violations, fake
sources, tool calls, malformed JSON, wrappers, and regressions.

## Known limitations

This version has one repair attempt, no semantic minimal-diff scoring, no LLM
judge, no automatic approval or Canon write, no Planner, no memory, no
multi-agent critique, and no automatic solution for impossible briefs. The
Canon Checker H2 limitation around free paraphrase in `canon_basis.supports`
remains unchanged.
