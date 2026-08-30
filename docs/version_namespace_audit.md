# Version Namespace Audit

Date: 2026-08-30

This audit covers version-like identifiers found in the repository, including
documentation, tests, evaluation fixtures, source comments, configuration, and
Git tags. The migration changes names only; it does not change runtime,
validator, schema, or corpus semantics.

| Existing Name | File / Location | Actual Meaning | Proposed Namespace | Rename Required | Notes |
|---|---|---|---|---|---|
| `0.8.0` | `pyproject.toml`, `README.md`, `README.zh-CN.md` | Current release for the whole project | Project Release | No | Project version for the `v0.8` public release. |
| `v0.8` | README files, Git tag | Current public project release | Project Release | No | Annotated release tag; immutable after publication. |
| `0.7.1` | `pyproject.toml`, `README.md` history | Previous public release | Project Release | No | Historical public release identifier; prior tag retained. |
| `v0.7.0` | `README.md`, Git tag | Previous public project release | Project Release | No | Historical public release identifier; tag retained. |
| `v0.6.6` | `docs/runtime_freeze_v0.6.6.md`, `README.md`, Git tag | Frozen Character Authoring runtime baseline | Runtime Baseline | No | File name and Git tag are historical identifiers; canonical body identifier becomes `runtime-v0.6.6`. |
| `v0.1` | `docs/reference_corpus/production_baseline_v0.1.md` and earlier corpus freeze docs | Historical pilot/production corpus checkpoints | Reference Corpus Baseline | No | Historical freeze identifiers are retained and labeled as legacy. |
| `v0.5` | `docs/reference_corpus_expanded_baseline_v0.5.md`, expansion-wave docs, Git tags | Current 16-record expanded reference corpus baseline and its historical waves | Reference Corpus Baseline | No | Canonical current identifier becomes `reference-corpus-v0.5`; wave identifiers remain historical. |
| `reference-corpus-expanded-baseline-v0.5` | Git tag and historical freeze references | Git compatibility identifier for the expanded corpus freeze | Reference Corpus Baseline | No | Legacy Git identifier — retained for compatibility. |
| `B1.2` | `tests/test_combat_role_alignment_b12.py` and test fixture display data | Character Intelligence combat-role alignment milestone | Character Intelligence | Yes | Body labels become `CI-B1.2`. |
| `B1.3` | `tests/test_combat_role_retirement_b13.py` and test fixture display data | Character Intelligence legacy-role retirement milestone | Character Intelligence | Yes | Body labels become `CI-B1.3`. |
| `B1.4` | `tests/test_combat_role_retirement_b14.py` and test fixture display data | Character Intelligence scalar-role retirement milestone | Character Intelligence | Yes | Body labels become `CI-B1.4`. |
| `B1.5` | `CONTEXT.md`, Character Skill docs, eval fixture rationale, prototype comment, `tests/test_combat_role_compatibility_freeze_b15.py` | Character Intelligence canonical taxonomy compatibility freeze | Character Intelligence | Yes | Body references become `CI-B1.5`; behavior and test meaning remain unchanged. |
| `S0` / `S0.1` | Character Skill specification, blind-review, readiness docs, tests | Character Skill specification and failure-case milestones | Character Skill | Yes | Active prose references become `CS-S0` / `CS-S0.1`. The Commit A frozen specification and authority fixture retain their exact legacy bytes because provenance tests require historical freeze assets to remain unchanged. Stable `skill_s0_*` case IDs are not milestone prose and remain unchanged. |
| `S1` / `S1.1` | Character Skill interface-option docs and prototype docstring | Character Skill interface-design/freeze milestones | Character Skill | Yes | Prose references become `CS-S1` / `CS-S1.1`. |
| `v0.1` / `v0.1.1` | Character Skill docs, fixtures, eval results, schema fields | Schema, contract, or interface versions attached to named objects | Schema / Contract / Interface | No | These are not Character Skill milestones. Named forms such as `character-skill-failure-cases/0.1.1` and `skill-kit-validator/0.1.1` remain independent. |
| `character_skill_interface_options_v0.1.1.md` | `docs/character_generation/` | Clearly named Character Skill interface contract document | Schema / Contract / Interface | No | Filename already identifies the object; no path rename is necessary. |
| `character_skill_s0_blind_review_v0.1.1.md` and related fixture/result paths | `docs/`, `evals/`, `tests/` | Clearly named historical Character Skill review assets and compatibility paths | Character Skill + Schema / Contract / Interface | No | Paths are unambiguous and are referenced by tests; retained to avoid unnecessary compatibility churn. |
| `v0.4`, `v0.4.1c`, `v0.4.3b`, etc. | Reference selector benchmark, feature diagnostics, schema docs | Reference-corpus component, diagnostic, or schema versions | Schema / Contract / Interface or Reference Corpus component | No | Object names in the same heading/file name disambiguate them; not CI/CS milestones. |
| `s1` | `src/agents/live_llm.py` | JSON `segment_id` example | Not a version | No | Ordinary data example, not a namespace identifier. |

## Git compatibility

Existing tags are immutable. In particular, `v0.6.6`, `v0.7.0`,
`reference-corpus-expanded-baseline-v0.5`, the reference-corpus wave tags, and
the Character Skill/Character Diversity tags are legacy Git identifiers retained
for compatibility. No tag is deleted, moved, recreated, or force-updated.

## Audit conclusion

No version-like reference was left semantically unresolved. Remaining legacy
forms are either named schema/contract versions, stable fixture IDs, clearly
scoped historical paths, ordinary data values, or immutable Git identifiers.
