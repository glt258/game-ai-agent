# ADR-001: Engineering Knowledge Snapshot Boundary

- Status: frozen
- Scope: Engineering Knowledge Layer v0.1
- Related graph decision: `ADR-001`

## Decision

Engineering Knowledge Graph v0.1 must represent an explicitly identified repository snapshot.

A dirty working tree must never be silently represented as the tagged release. Every graph snapshot records:

- branch;
- HEAD;
- release tag, when applicable;
- working-tree state;
- snapshot kind.

The first graph describes the reviewed working tree on `main`, not the clean `v0.8` release contents.

## Context

The repository currently has `HEAD` at the `v0.8` release tag while the working tree contains uncommitted Web, W4 CharacterKit, benchmark, documentation and test changes. Those files are useful current working-tree evidence, but they do not automatically belong to the release snapshot.

The graph therefore needs provenance independent of source precedence. Executable code remains the strongest evidence for current behavior, while Git metadata determines which repository state that behavior belongs to.

## Consequences

- Web and CharacterKit/W4 nodes are `experimental` in v0.1.
- Query output warns when the graph HEAD differs from current HEAD or when the working tree is dirty.
- A future clean release graph must be generated or reviewed as a separate snapshot.
- Existing historical documents are not rewritten solely to match this decision.
