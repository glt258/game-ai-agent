# SkillDesignArtifact Identity and Version Contract v0.1

This document freezes the W4-S2D contract for one Skill design result. It is
an in-memory, immutable contract only. It does not introduce persistence,
repositories, history, Skill Kits, slots, or a durable database identifier.

## Boundary and ownership

The implementation lives in
`src/character_intelligence/skill_artifact.py`.

`SkillDesignArtifact` is the standalone-compatible envelope:

```text
SkillDesignArtifact
├─ identity
├─ versions
├─ semantic_source
├─ canonical_artifact
├─ original_evaluation
└─ provenance
```

The envelope keeps these objects distinct:

| Object | Responsibility | Identity |
| --- | --- | --- |
| Semantic IR | Provider-produced authoring source and compiler input | `semantic_source_digest` |
| `ProtocolSkillKitCandidate` | Canonical Skill artifact | `artifact_digest` |
| `SkillValidationReport` | Historical validity report | `report_digest` |
| `CharacterSkillDesignContext` | Character semantic projection | `source_context_fingerprint` |
| `CharacterSkillAlignmentResult` | Derived Character ↔ Skill relationship | binding metadata and alignment version |

`ProtocolSkillKitCandidate` is not a Character Kit. It remains the existing
single Skill canonical envelope, and no multi-Skill collection or slot model is
defined here.

## Identity invariants

The content identity is frozen as:

```text
artifact_digest = ProtocolSkillKitCandidate.digest
```

Therefore the following are intentionally separate:

```text
artifact_digest ≠ semantic_source_digest
artifact_digest ≠ report_digest
artifact_digest ≠ source_context_fingerprint
artifact_digest ≠ run_id
```

Changing Character context, provider/model/run metadata, evaluation output, or
alignment must not change `artifact_digest` when the canonical candidate is
unchanged. The artifact has no `character_id`; Character ownership belongs to
`CharacterSkillArtifactBinding`.

The binding carries only the association needed at this seam:

```text
artifact_digest
source_context_fingerprint
alignment
alignment_version
character_context_projection_version
```

Freshness is derived by comparing the binding fingerprint with the current
context fingerprint. It is not stored in the immutable artifact.

## Version metadata and historical semantics

`SkillArtifactVersionMetadata` records the contracts used by the historical
run, not the newest runtime versions:

```text
semantic_ir_schema_version
compiler_version
canonical_skillkit_schema_version
skill_evaluator_version
character_alignment_version | null
character_context_projection_version | null
```

The compiler version is extracted from the actual `CompilerProvenance`, the
IR version from the retained Semantic IR, the canonical schema from the
candidate, and the evaluator version from `VALIDATOR_CONTRACT`. Standalone
artifacts leave Character alignment/projection versions null.

Historical evaluation remains historical. A report such as “PASS under
evaluator v1” is not a current PASS under evaluator v2 until a caller performs
an explicit reevaluation. Compiler drift likewise never silently recompiles an
immutable historical artifact.

`inspect_skill_artifact_compatibility` is deterministic and provider-free. It
only compares version metadata and returns structured findings:

- canonical schema drift → `UNSUPPORTED_VERSION`
- IR or compiler drift → `RECOMPILE_REQUIRED`
- evaluator drift → `REEVALUATION_RECOMMENDED`
- alignment drift → `REALIGNMENT_RECOMMENDED`
- Character projection drift → `CONTEXT_PROJECTION_DRIFT`
- no findings → `CURRENT_COMPATIBLE`

There is no percentage compatibility score, and inspection never recompiles,
reevaluates, realigns, or calls a provider.

## Character context fingerprint

The Character Skill projection version is
`character-skill-context/0.2`. `character_name` participates in the
projection because it is included in the actual Character Skill requirement
sent to the shared Skill pipeline. Every other field in the projection is
included only when it is a semantic input to that requirement. Trace-only
`source_draft_id` is excluded.

This prevents a context change from being incorrectly presented as current.
The projection version is part of the binding so a future projection algorithm
change is reported as projection drift rather than being treated as a simple
hash mismatch.

## Fail-closed binding safety

The lower-level alignment seam verifies:

```text
provided artifact_digest == candidate.digest
provided source_context_fingerprint == character_context.source_context_fingerprint
evaluation.candidate_digest == candidate.digest
```

The artifact factory repeats the candidate/evaluation checks and verifies the
identity, source, canonical schema, compiler provenance, and alignment
bindings. Mismatches raise stable `ArtifactBindingError.code` values instead
of allowing a misleading PASS result.

## Serialization and application use

`SkillDesignArtifact.to_mapping()` and
`SkillDesignArtifact.from_mapping()` provide deterministic round trips for
the frozen envelope. The existing Skill Playground and Character Skill Design
services use the factory; Web response fields remain compatible and no raw
provider prompt or response is placed in the artifact.

No save/load/list/delete API is implied. Persistence, version history, and
future explicit recompile/reevaluation workflows remain later decisions.
