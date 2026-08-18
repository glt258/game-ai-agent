# Official Character Authoring Demo v0.1.1

## Goal

This CLI demo presents the planner workflow: a brief is turned into a
structured `CharacterDraft`, checked against the project Canon, repaired once
when the existing repair policy allows it, and returned with a compact audit.
It is a proposal for human review; it never writes Canon.

## Pipeline

```text
Planner brief
  -> CharacterGenerationAgent
  -> CharacterDraft
  -> CanonChecker
  -> CharacterRepairAgent (at most one attempt)
  -> CanonChecker
  -> human-readable proposal and audit
```

The demo loads the existing 10-record Reference Corpus through
`CharacterReferenceRepository`. It passes only bounded role/mechanic summaries
to the generation runtime as design context. Reference data is not Canon
evidence and is not copied into the generated character.

## Run it

From the repository root:

```powershell
py -m agents.official_character_authoring --scenario valid --model offline
py -m agents.official_character_authoring --scenario conflict --model offline
py -m agents.official_character_authoring --brief "设计一个新的都市辅助角色。" --model offline
py -m agents.official_character_authoring --brief-file .\my_brief.txt --model live
```

Exactly one of `--scenario`, `--brief`, and `--brief-file` is required.
Scenario inputs are reproducible fixtures; custom text and file inputs enter
the same generation, Canon validation, bounded repair, and audit pipeline.

Offline mode uses the existing deterministic authoring model and is suitable
for CI, regression checks, and demos without network access. Live mode reuses
the existing provider configuration and adapter:

```powershell
py -m agents.official_character_authoring --scenario valid --model live
```

Configure `NPC_LLM_PROVIDER`, `NPC_LLM_MODEL`, `NPC_LLM_API_KEY`, and the
other existing `NPC_LLM_*` settings before using live mode. Add `--json` for a
machine-readable report.

Offline mode is a deterministic pipeline fixture, not an open-ended character
quality model. Use live mode when evaluating arbitrary briefs as generation
quality.

## Scenarios

The valid scenario uses a modern-city support-character brief and should pass
the real checker without repair.

The conflict scenario deliberately asks for a secret centralized ability
governance institution. That conflicts with World Bible RULE-008. The output
shows the initial `FAIL`, the real bounded repair, and the post-repair check.
If a repair cannot preserve the request or scope, the workflow remains failed
and the report says `NOT APPLIED` / `NEEDS_REVIEW`.

Reference output is selection-level grounding. It displays real IDs, names,
and bounded context scope, but does not claim that a particular reference
caused a particular generated field. Canon PASS output is limited to the
dimensions actually represented by the Canon Checker result.

Auto-repair is bounded by an authorized editable scope. If a safe repair
cannot be applied, the system returns `NEEDS_REVIEW` rather than silently
rewriting protected fields.

## Current limitations

- The reference selection is bounded lexical grounding, not RAG or vector search.
- Offline deterministic model audits expose generation turns; provider-level
  invocation details are available when the live adapter supplies them.
- The demo does not approve or publish proposals, perform balance simulation,
  or provide a web UI.
