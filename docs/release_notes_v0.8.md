# v0.8 — Skill Design v1 & Playground CLI

`v0.8` is a documented release of the current Skill Design v1 and Manual Skill
Playground capability. It describes the implemented deterministic pipeline and
its bounded model-assisted edges; it does not claim benchmark performance or
universal model reliability.

## Highlights

- Skill Design v1 coverage for Support, Main DPS, Sub-DPS, Control,
  Reaction / Healer, Defense, and Basic Passive families.
- Semantic IR → deterministic compiler → canonical SkillKit → evaluator
  pipeline with canonical parsing and reference-integrity checks.
- Manual Skill Playground CLI at `scripts/skill_playground.py` with natural-
  language requirements, role/mode selection, model selection, language
  selection, safe diagnostics, and one bounded repair opportunity.
- Simplified-Chinese and English human-readable playground output while
  machine-readable field names and enum values remain authoritative English
  protocol values.
- Triggered-v2 contract alignment: required `feedback`, explicit `null` when
  gameplay feedback is absent, and fail-closed handling for a missing
  discriminator.
- Generic actor semantics: `trigger.actor` identifies the event participant;
  `effect.actor` identifies the affected semantic subject. Request-owned subject
  constraints are supplied to generation and repair without hardcoding a role.

## Reliability and hardening

This release includes parser fail-closed behavior, safe provider/parser/
evaluator diagnostics, bounded semantic repair, and localized request cleanup.
The deterministic acceptance boundary, compiler semantics, evaluator semantics,
and provider transport behavior remain bounded and explicit.

## Validation

- Latest verified full offline suite: `1676 passed, 1 skipped`.
- Tracked-only clean-checkout suite: `1676 passed, 1 skipped`.
- Ruff, compile checks, and `git diff --check` passed at the validated runtime
  commit.
- The stable skipped test is an opt-in live smoke path; no live provider call
  is part of the offline release gate.

## Manual live observation

A manual Simplified-Chinese Support Passive run completed the full pipeline
successfully with DeepSeek V4 Flash. This is a verified manual live
observation, not a benchmark or a universal reliability claim. No provider
payload or evidence artifact is included in this release.

## Known limitations

- Real-model semantic reliability is not 100%, and live provider latency or
  timeout can make an invocation unavailable.
- Bounded repair depends on a second provider invocation being available.
- The live sample size remains small; Sub-DPS and Defense model elicitation
  need continued observation.
- Deferred v2 mechanics are not supported: summon, resource economy, stacks,
  states, transformations, complex multi-stage mechanics, multi-role,
  probability, formula/scaling DSL, aura/ticks, complex proc passives, and
  chained feedback.
- Human review remains authoritative; a passing generated SkillKit is not a
  claim of universal model quality.
