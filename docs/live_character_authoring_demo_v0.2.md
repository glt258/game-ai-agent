# Live Character Authoring Demo v0.2 — Sanitized Run Report

## Purpose

Verify that a fresh user-written character brief enters the existing live
CharacterGenerationAgent, reference grounding, Canon Checker, bounded repair,
and authoring-audit pipeline without silently falling back to the offline
fixture.

## Command shape

```powershell
py -m agents.official_character_authoring `
  --brief-file .\demo_brief.txt `
  --model live
```

One-off provider/model overrides are available with `--provider` and
`--model-name`. Credentials remain environment configuration and are never
printed by the CLI.

## Run status

Accepted live execution: **COMPLETED**

The accepted live evidence below uses real provider calls through the live
pipeline. The CLI still fails closed when credentials or a live invocation are
unavailable: it does not fall back to the offline fixture or fabricate a draft
or Canon result.

Provider/model verified: `opencode_go` / `deepseek-v4-flash`

## Accepted Live Evidence (v0.2.1)

The following sanitized first-shot runs are accepted against the existing
generation, reference-grounding, CharacterDraft, Canon, bounded-repair, and
authoring-audit pipeline:

### 陈洁

- Real live generation completed.
- Initial Canon: `FAIL`.
- Bounded repair completed; final Canon: `PASS`.
- Final status: `ACCEPTED`.

### 岑婧

- Playable control fantasy: `PASS`.
- Character hook contract: `PASS`.
- Canon: `PASS`.
- Final status: `ACCEPTED`.

### 白莳

- Playable utility/support fantasy: `PASS`.
- Character hook contract: `PASS`.
- Canon: `PASS`.
- Final status: `ACCEPTED`.

### 麦嫂

- Post-reliability live CharacterDraft: `PASS`.
- Playable support fantasy: `PASS`.
- Character hook contract: `PASS`.
- Initial Canon: `FAIL`.
- Bounded repair completed; final Canon: `PASS`.
- Final status: `ACCEPTED`.
- This run reported `Normalized fields: none`; it did not exercise the
  `open_questions` normalization branch.

The `open_questions` normalization branch is covered by provider-neutral
regression tests, while the post-fix live pipeline is verified by the 麦嫂 run.
No provider-wide behavior claim is made beyond the provider/model pair listed
above.

## Generation Quality v0.2.1

The generation contract now strengthens two existing authoring expectations
without changing the `CharacterDraft` or formal Character Schema:

- playable briefs must retain an ordinary identity while explaining dangerous-
  scene participation and a concrete conceptual combat fantasy;
- `story_hook` is asked to surface the existing `first impression`,
  `visual_or_behavioral_motif`, and `memorable_contrast` semantics.

The contract explicitly forbids inventing elements, weapon taxonomies, damage
numbers, cooldowns, energy systems, or other unestablished combat systems. NPC-
only briefs are not forced into combat. Reference context is described as
bounded transformative precedent, not Canon evidence or a copying template.

The live acceptance set covers fresh playable support, control/utility, and
ordinary-identity briefs. It records qualitative contract and Canon outcomes;
it is not a provider-wide benchmark.

## CharacterDraft Reliability Note

When a provider returns an otherwise complete draft but omits only
`open_questions`, the CharacterDraft layer normalizes that one field to `[]`.
This represents “no unresolved questions declared” and is recorded in the
generation audit as a system-normalized field. Missing `canon_basis`,
`new_design_elements`, or multiple core fields still fail closed; this is not a
generic malformed-JSON fixer.

## Deferred Findings

- Repeated references to Furina, Keqing, or Nahida do not have field-level
  attribution; the Reference Selection Quality Benchmark remains deferred.
- A possible cross-field inconsistency involving `faction_006` and prose saying
  the character is not a member of any organization remains deferred to a
  cross-field semantic-consistency pass. The generated fixture and Canon logic
  are unchanged.
