# Current State

- Branch: `main`
- HEAD: `d1e511ebe82684867c3beff9ccc6bd1c36bbbbf6`
- Release tag: `v0.8`
- Working tree: `dirty`
- Graph snapshot kind: `reviewed_working_tree`
- Release equivalent: `false`
- Engineering Knowledge Layer: `engineering-knowledge-layer/0.1`

Stable/frozen systems include Character Generation, CanonChecker, the bounded repair loop, canonical combat-role semantics, Semantic Skill IR → compiler → canonical SkillKit, the provider boundary and the frozen Reference Corpus boundary.

Web and W4 CharacterKit are experimental working-tree architecture. They are not represented as released v0.8 architecture.

`src/knowledge/` is game runtime knowledge and knowledge-access code. Top-level `knowledge/` is the repository-local Engineering Knowledge Layer.

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
