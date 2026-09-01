# Agent Development Rules

Before modifying architecture-sensitive code, run the repository-local Engineering Preflight and capture the task baseline:

```powershell
py scripts/project_preflight.py --task "<task description>" --capture-baseline
```

Read the reported canonical sources, frozen contracts, constraints, related tests and snapshot warnings before editing.

Do not create parallel canonical definitions. If Preflight returns `GRAPH_INVALID`, do not proceed with architecture-sensitive edits. If it returns `INSUFFICIENT_CONTEXT`, inspect the repository rather than guessing.

Architecture-sensitive areas include Character Generation, CanonChecker, Character Repair, Combat Semantics, Semantic Skill IR, Skill Compiler, Canonical SkillKit, Skill Evaluator, KnowledgeResolver, Story Canon, Reference Corpus boundaries, Provider abstraction, Web adapter boundaries and CharacterKit/W4 association.

README typos, comment typos and formatting-only changes do not require Preflight.

After architecture-sensitive edits and targeted tests, run Postflight against the captured task baseline:

```powershell
py scripts/project_postflight.py --from-baseline
```

`--from-baseline` is the normal task audit: it reports only files changed after Preflight. If the baseline is missing or belongs to another branch, stop and recapture with Preflight; do not fall back to a whole-tree audit. Use `py scripts/project_postflight.py --clear-baseline` after the task, or before replacing a deliberately stale baseline.

Do not commit when Postflight returns `GRAPH_INVALID`. Review the Engineering Knowledge Layer before committing when it returns `KNOWLEDGE_UPDATE_REQUIRED`; `REVIEW_RECOMMENDED` is not a hard blocker.

Development workflow:

```text
Preflight + Capture Baseline → Inspect → Implementation → Targeted Tests → Postflight from Baseline → Review Current Task Impact → Review EKL if Required → Clear/Replace Baseline → Commit
```

Postflight only detects and reports possible knowledge drift. It never updates the graph, writes an ADR, resolves a limitation, or changes lifecycle status automatically.
