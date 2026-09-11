# Current State

- Branch: `main`
- HEAD: `d1e511ebe82684867c3beff9ccc6bd1c36bbbbf6`
- Release tag: `v0.8`
- Working tree: `dirty`
- Graph snapshot kind: `reviewed_working_tree`
- Release equivalent: `false`
- Engineering Knowledge Layer: `engineering-knowledge-layer/0.1`

Stable/frozen systems include Character Generation, CanonChecker, the bounded repair loop, canonical combat-role semantics, Semantic Skill IR → compiler → canonical SkillKit, the provider boundary and the frozen Reference Corpus boundary.

The current authoritative production route is `opencode_go` with model
`deepseek-v4.1-flash` for Character and Skill operations. Earlier
`deepseek-v4-flash` runs remain historical evidence and are not current live
acceptance configuration.

Web and W4 CharacterKit are experimental working-tree architecture. They are not represented as released v0.8 architecture.

The W4-S5D unified CLI, runtime diagnostics and source-checkout Studio startup
orchestration are experimental working-tree components. The wheel exposes the
core runtime and Doctor; the Next.js Studio remains outside the wheel.

`src/knowledge/` is game runtime knowledge and knowledge-access code. Top-level `knowledge/` is the repository-local Engineering Knowledge Layer.

Live Web executions use a single process-local 90-second monotonic deadline
owned by `LiveJobRegistry`; the deadline starts at job registration and is
shared by queued work, provider retries, action rounds, finalization, and
evaluation. Timeout terminals freeze only finite progress metadata and retain
physical worker accounting until settlement. Browser polling remains a 120
second client horizon and is distinct from provider attempts.

W5-S1E-F13 adds bounded latency attribution to the same ephemeral progress
surface: queue wait, phase durations, logical invocation and provider-attempt
starts, final-provider start offset, and remaining budget are measured with
the operation's monotonic clock and frozen at terminal timeout. Historical F12
fine-grained phase timing is unavailable; the confirmed blocker remains
`FINAL_PROVIDER_COMPLETION_WITHIN_CANONICAL_DEADLINE`.

## Source Precedence

When facts conflict, use this order:

1. Executable runtime source and canonical packaged data.
2. Deterministic tests protecting explicit contracts.
3. Explicit freeze, compatibility and contract documentation.
4. Current architecture documentation.
5. README, CONTEXT and status documentation.
6. Release, benchmark and historical reports.
7. Local artifacts, `local-audit` and transient evidence.

Git snapshot provenance is independent of this content precedence. A dirty working-tree source can describe the current working tree, but does not automatically describe the tagged `v0.8` release.
