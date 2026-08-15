# Along the Street — Knowledge Resolver

This repository contains the read-only NPC knowledge boundary and authoring
agents for *Along the Street*.

## Current Status

Character Authoring Pipeline v0.6.6
Runtime Freeze: READY_FOR_DEMO

See [docs/runtime_freeze_v0.6.6.md](docs/runtime_freeze_v0.6.6.md) for the
frozen baseline, acceptance evidence, invariants, and post-freeze change policy.

## Character Generation Agent

Generate a Canon-aware, reviewable draft without changing formal Canon:

```bash
py scripts/demo_character_generation_v0_1.py --model offline
py scripts/run_character_generation_evals.py
```

See [docs/character_generation_agent_v0.1.md](docs/character_generation_agent_v0.1.md)
for the request, tool, grounding and limitation details.

## Canon Checker

Validate a `CharacterDraft` against structured Canon and the original design
request without an LLM judge or Canon writes:

```bash
py scripts/demo_canon_checker_v0_1.py --case good
py scripts/demo_canon_checker_v0_1.py --case subtle
py scripts/demo_canon_checker_v0_1.py --case bad
py scripts/run_canon_checker_evals.py
py scripts/run_canon_checker_live_language_evals.py
```

The authoring flow is now:

```text
CharacterDesignRequest
    -> CharacterGenerationAgent
    -> CharacterDraft
    -> CanonChecker
    -> CanonCheckReport (PASS / WARN / FAIL)
    -> CharacterRepairAgent (at most one bounded repair)
    -> CanonChecker (full re-check)
```

The repair loop never writes Canon and never approves a character.  It keeps
the original `CharacterDesignRequest`, accepts only a complete `CharacterDraft`
root object, validates the deterministic changed-field scope, and recommends
the repaired draft only when the second check improves the result:

```bash
py scripts/demo_character_repair_v0_1.py --case subtle
py scripts/demo_character_repair_v0_1.py --case bad
py scripts/demo_character_repair_v0_1.py --case unrepairable
py scripts/demo_character_repair_v0_1.py --case relationship --json
py scripts/run_character_repair_evals.py
py scripts/run_character_repair_redteam.py
```

See [docs/character_repair_loop_v0.1.md](docs/character_repair_loop_v0.1.md)
for the evidence boundary, one-attempt semantics, scope rules, and offline
fixtures. v0.1.1 adds cross-field hard-constraint preservation, immutable
relationship serialization, clause-local authority detection, and sensitive
internal-material detection.

See [docs/canon_checker_v0.1.md](docs/canon_checker_v0.1.md) for finding codes,
implemented deterministic rules, examples, and known limitations. Canon Checker
v0.1.6 unifies compound absence polarity across literal and generic forbidden
matching paths; the offline Live-derived matrix contains 91 cases with zero
false positives or false negatives.

## Live providers

The shared OpenAI Chat Completions transport supports the logical providers
`openai`, `deepseek`, `opencode_go`, and `openai_compatible`. OpenCode Go has a
default gateway URL; generic compatible gateways require an explicit Base URL.
See [docs/provider_capability_layer.md](docs/provider_capability_layer.md) for
provider/model/transport separation, capability negotiation, and configuration.
