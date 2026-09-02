# CharacterKit Role Coverage Evaluation Contract v0.1

## Purpose

`CharacterKit Role Coverage` is a deterministic, provider-free semantic layer after
Kit structural validation. It answers only whether the canonical Skill evidence in a
current `CharacterKit` covers the Character's declared `CombatRoleProfile`.

It does not answer whether a Kit is fun, balanced, creative, complete, synergistic,
well-rotated, or economically coherent.

## Evaluation stack

```text
Skill Evaluation
  one Skill's internal validity
        ↓
Single-Skill Alignment
  one Skill's Character role fit
        ↓
Kit Structural Validation
  membership, identity, ordering, placement integrity
        ↓
Kit Role Coverage
  aggregate canonical role evidence for the whole Kit
```

The evaluator does not mutate `CharacterKit`, `SkillDesignArtifact`, an association, or
`kit_digest`.

## Version and inputs

Evaluator version: `character-kit-role-coverage-evaluator/0.1.0`.

The immutable `CharacterKitEvaluationContext` contains only:

- `CombatRoleProfile`;
- `context_contract_version`;
- a deterministic `context_fingerprint` derived from those fields.

It intentionally excludes Character name, age, background, design pitch, affiliation,
Canon, Web DTOs and `CharacterDraft`. Therefore irrelevant Character edits do not change
the Kit evaluation context fingerprint; primary or secondary role edits do.

The Kit must be structurally valid. Each current member must have a digest-bound Skill
Evaluation with `outcome == PASS`, current compatible artifact versions, and valid
association/binding identity. An optional application-layer Skill design context
fingerprint check rejects stale associations without reusing it as the role-only context
fingerprint.

## Evidence model

Role evidence comes from the existing canonical operation-to-role extraction helper used
by Single-Skill Alignment. It is not reimplemented in this module. Current canonical
examples include:

| Canonical operation | Role evidence |
| --- | --- |
| `ally_enablement` | `support` |
| `enemy_action_control` | `control` |
| `recover_or_mitigate` | `healer`, `defense` |
| `threat_protection` | `support`, `defense` |
| `direct_output` | `main_dps` |
| `follow_up_output` | `sub_dps` |

Every coverage item preserves artifact digest, association id, operation, canonical
paths, centrality, family and mode. Family, mode and authoring placement are trace
metadata; none can override canonical operations. A passive Skill contributes equally,
and one artifact may support multiple roles.

No keyword matching, free-text similarity, LLM, embedding, subjective score or numeric
quality formula is used.

## Status semantics

`PASS` means the primary role is covered by canonical evidence, every declared secondary
role is covered, and no blocking contradiction exists. It means `Combat Identity Coverage:
PASS`, not `Complete Kit`.

`PARTIAL` means the primary role is covered but one or more declared secondary roles are
not covered. It is non-blocking authoring feedback.

`FAIL` means the preconditions are valid but the declared primary identity is not covered,
or all recognized evidence points outside the declared primary/secondary role set. This
is a blocking semantic mismatch.

`NOT_EVALUATED` means a current semantic claim is not trustworthy: structural failure,
empty authoring Kit, unspecified combat role, unusable Skill Evaluation, invalid binding,
artifact compatibility drift, stale association, or unavailable canonical role evidence.
It is not an automatic semantic FAIL.

## Findings

Findings are immutable and auditable. They contain a stable `code`, `kind`, `blocking`,
optional `character_role`, artifact evidence, artifact digests, field path and safe
message. v0.1 uses the small vocabulary:

- `KIT_PRIMARY_ROLE_SUPPORTED`;
- `KIT_PRIMARY_ROLE_UNSUPPORTED`;
- `KIT_SECONDARY_ROLE_SUPPORTED`;
- `KIT_SECONDARY_ROLE_UNSUPPORTED`;
- `KIT_UNSUPPORTED_ROLE_DOMINANCE`;
- `KIT_ROLE_PROFILE_UNSPECIFIED`;
- `KIT_ROLE_EVIDENCE_UNAVAILABLE`;
- `KIT_ROLE_COVERAGE_NOT_EVALUATED`.

Unsupported-role dominance is categorical: it blocks only when valid recognized evidence
exists, no evidence supports any declared role, and all recognized evidence is outside the
declared role set. One damage-oriented Skill does not invalidate a support/control Kit.

## Identity and history

The result binds:

- `kit_digest`;
- `evaluation_context_fingerprint`;
- `evaluator_version`;
- deterministic `report_digest`.

The semantic report never enters `kit_digest`. Historical results remain displayable, but
a report from another evaluator version, stale context or incompatible artifact does not
imply a current PASS; explicit reevaluation is required.

## HTTP adapter

The additive endpoint is:

```text
POST /api/characters/character-kit/evaluate
```

The typed request contains the full backend-owned CharacterKit mapping, a canonical
`CombatRoleProfile`, and optionally the current Skill design context fingerprint. The
typed response keeps `structural_validation` and `role_coverage` separate. A semantic
precondition failure is a successful business response with `role_coverage.status ==
NOT_EVALUATED`; malformed request structure is HTTP 422.

The adapter does not call a provider, compiler, Skill evaluator, Alignment evaluator,
database, repository, or persistence layer.

## Studio transport/integration architecture

The Character Studio keeps the current Kit in browser session state as formal transport
objects, not as a copy of the complete Skill Design HTTP response:

```text
AttachedCharacterSkill
├─ CharacterSkillAssociation
├─ SkillDesignArtifact
└─ CharacterSkillArtifactBinding
```

`SkillDesignArtifact` carries its identity, versions, semantic source, canonical
artifact, historical `original_evaluation` and safe compiler/provider provenance.
`CharacterSkillArtifactBinding` carries the artifact digest, source-context fingerprint,
full Character-Skill Alignment result and binding/projection versions. The association
adds only placement and display metadata; it does not make the Skill artifact own a
Character or persist it in a repository.

The pure frontend request builder transports these formal objects and intentionally does
not compute a Kit digest, role evidence, coverage, or semantic status. It orders only the
outgoing association list for deterministic transport. The role-coverage endpoint then
rebuilds the canonical `CharacterKit`, reuses the existing structural validator, and
invokes the provider-free evaluator. The backend remains authoritative for ordering,
identity verification, structural validity, digest calculation and role coverage.

Attach, detach, replace and CombatRoleProfile changes clear the old semantic snapshot and
start a new request. The coordinator ignores late responses from older request
generations and accepts a result only for the current Kit/context identity. Irrelevant
Character edits do not invalidate the role-only evaluation context. Missing artifact or
binding data, unsupported versions and digest inconsistencies fail closed as transport
errors; they are not converted into semantic `FAIL` or `NOT_EVALUATED`.

This is session-only state. It introduces no artifact repository, persistence, history,
database, Kit synergy model or evaluator semantic expansion.

## Deferred semantics

The following are explicitly outside v0.1:

- functional redundancy and diversity scoring;
- synergy, combo chains, timing and cooldown rotation;
- shared resources, states and summons;
- cross-Skill references and lifecycle identity;
- damage calculation, numerical balance and energy economy;
- gameplay-slot completeness;
- creativity, novelty, fun and selling-point quality;
- repair, generation, approval, publish and persistence.

## UI contract

Character Studio presents two independent labels:

```text
KIT STRUCTURE       PASS / FAIL
ROLE COVERAGE       PASS / PARTIAL / FAIL / NOT_EVALUATED
```

The Role Coverage panel shows primary and secondary support state, safe findings and
traceable evidence. It must not display a quality percentage or `Complete Kit` label.
