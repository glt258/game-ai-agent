# Versioning and Namespace Policy

This project has several independently evolving artifacts. A runtime freeze,
reference corpus expansion, Character Intelligence compatibility boundary, and
Character Skill design contract do not advance in lockstep. Separate namespaces
make those histories readable and prevent a subsystem milestone from being
mistaken for a project release or an interface version.

## Project Release

Use Project Release for the version of the whole repository:

```text
v0.7.0
v0.8.0
0.8.0.dev0
```

The development version is declared in `pyproject.toml`. A subsystem must not
use a bare `v0.x` as its public name.

## Runtime Baseline

Runtime Baseline identifies a frozen executable/runtime capability set:

```text
runtime-v0.6.6
```

The historical file `docs/runtime_freeze_v0.6.6.md` and the historical Git tag
`v0.6.6` remain unchanged for compatibility. Current prose should use the
canonical identifier and make the namespace explicit:

```text
Namespace: Runtime Baseline
Identifier: runtime-v0.6.6
```

## Reference Corpus Baseline

Reference Corpus Baseline identifies a frozen reference-data checkpoint:

```text
reference-corpus-v0.5
```

The current expanded 16-record baseline is `reference-corpus-v0.5`. Older pilot,
wave, and production checkpoints retain their historical names and meanings.
For example, `Reference Corpus v0.5 Expanded Baseline` should be understood as
the named baseline `reference-corpus-v0.5`, not as a project release.

## Character Intelligence Milestones

Character Intelligence milestones use the `CI-` prefix:

```text
CI-B1.2
CI-B1.3
CI-B1.4
CI-B1.5
CI-B2
```

`CI-B1.5` is the current repository milestone for the canonical combat-role
taxonomy boundary. Historical descriptions may say `formerly B1.5`, but a
canonical identifier must include `CI-`.

## Character Skill Milestones

Character Skill development milestones use the `CS-` prefix:

```text
CS-S0
CS-S0.1
CS-S1
CS-S1.1
```

`CS-S0.1` is the frozen failure-case/specification milestone and `CS-S1.1`
is the current frozen interface-design milestone in this repository. Stable
fixture case IDs such as `skill_s0_14_cross_taxonomy_role` are data identifiers,
not canonical milestone names, and are retained when compatibility depends on
them.

The Commit A frozen CS-S0.1 specification and authority fixture also retain
their historical literal `S0.1`/`B1.5` wording byte-for-byte because provenance
tests treat those freeze assets as immutable evidence. New explanatory prose
around them must use `CS-S0.1` and `CI-B1.5`.

## Schema / Contract / Interface Versions

Schema, contract, and interface versions have their own namespace and must be
bound to an object name:

```text
character-skill-interface-v0.1.1
combat-vocabulary-v0.x
character-intent-v0.x
```

At minimum, write `Character Skill Interface v0.1.1` or the canonical named
identifier. Do not turn `character-skill-interface-v0.1.1` into `CS-S1.1`:
the former is an interface/contract version, while the latter is a Character
Skill development milestone.

## Git tag compatibility policy

Git tags are historical identifiers and are immutable under this policy. Do not
delete, force-move, recreate, or rename an existing tag. If a legacy tag does
not follow the current namespace, record it in the audit and use the canonical
identifier in new explanatory prose.

## File names and canonical identifiers

A file name is a compatibility and navigation surface; it is not automatically
the canonical identifier. Rename a file only when its name creates genuine
ambiguity and update every Markdown link, test fixture reference, and script
path. A descriptive existing name such as
`character_skill_interface_options_v0.1.1.md` already binds its version to the
interface object and does not need an unnecessarily long replacement.

## Naming a new milestone

First classify the artifact, then use the namespace-specific form. Use Project
Release only for a whole-project release, `runtime-v...` for a runtime baseline,
`reference-corpus-v...` for a corpus baseline, `CI-B...` for Character
Intelligence, and `CS-S...` for Character Skill. Use an object-bound name for
schema, contract, and interface versions. Record the new identifier in the
README Version Matrix and, when it changes the repository's namespace map, in
`docs/version_namespace_audit.md`.

A bare identifier such as `B1.3`, `S0.1`, or `v0.1` must not be introduced in
new documentation when its namespace cannot be inferred unambiguously from the
same heading or sentence.
