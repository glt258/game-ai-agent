# CharacterKit Contract v0.1

## Scope

`CharacterKit` is a thin, immutable, session-only aggregate over
`CharacterSkillAssociation` values. It owns membership ordering and the Kit
content digest. It does not own a Character, copy Skill contents, persist
state, or invoke a provider, compiler, Skill Evaluator, or Character-Skill
Alignment evaluator.

Contract version: `character-kit/0.1.0`
Placement schema: `character-kit-placement/0.1.0`

```text
CharacterKit
  │
  ├─ Association(primary)
  │      └─ SkillDesignArtifact A
  │
  ├─ Association(secondary)
  │      └─ SkillDesignArtifact B
  │
  ├─ Association(passive, ordinal 0)
  │      └─ SkillDesignArtifact C
  │
  └─ Association(passive, ordinal 1)
         └─ SkillDesignArtifact D
```

## Placement semantics

The current vocabulary is retained: `primary`, `secondary`, `passive`, and
`utility`. These are authoring placements and deterministic display-order
metadata, not gameplay slots or universal required positions.

| placement | order | max_items |
| --- | ---: | ---: |
| primary | 0 | 1 |
| secondary | 1 | 1 |
| passive | 2 | unbounded |
| utility | 3 | unbounded |

The existing `CharacterSkillCollection` remains compatible and continues to
enforce at most one association per placement. `CharacterKit` accepts an
association sequence so a Kit can author multiple passive associations without
changing that older collection contract. For repeated placements, the Kit
derives a deterministic zero-based ordinal after sorting by artifact digest.

Authoring cardinality is `0..N`; an empty Kit is structurally valid.

## Identity and validation

`kit_digest` is SHA-256 over the contract/version metadata and canonical
ordered members containing placement, placement order, derived placement
ordinal, and `artifact_digest`. It excludes Character context fingerprints,
Skill Evaluation, Alignment, freshness, provider/model/run metadata, display
labels, and frontend state. It also does not rehash nested SkillKit JSON.

`CharacterKitStructuralValidator` returns only `PASS` or `FAIL` with stable
finding codes. It checks contract/version, ordering, unique association and
artifact identity, placement/cardinality, Association binding, and digest
integrity. It does not perform semantic kit evaluation or aggregate freshness
evaluation; per-association freshness remains derived from each binding.

A `SkillDesignArtifact` is standalone immutable Skill content and has no
Character owner or placement. A `CharacterSkillAssociation` binds that artifact
to session context and owns placement, family, mode, and display metadata. A
`CharacterSkillCollection` is the legacy per-placement 0..1 session collection;
it is not a Kit. `CharacterKit` is the next thin aggregate over those
associations and may accept repeated passive/utility placements. Skill family,
Skill mode, and Character combat role remain separate vocabularies from Kit
placement.

## Web seam and lifecycle boundary

`POST /api/characters/skill-kit/validate` accepts a versioned full Kit mapping
with formal artifact and binding envelopes and returns the Kit contract,
association projections, `kit_digest`, and `structural_validation`. The
operation is build/validate only: it does not save, publish, create IDs, or
return a persistence record, and it calls no Provider, Compiler, Skill
Evaluator, or Alignment evaluator.

CharacterKit v0.1 does not model shared resources, shared states, shared
summons, cross-Skill references, gameplay-slot completeness, combat synergy, or
Kit quality. It is serialization-ready but has no repository or persistence
lifecycle.

Serialization is an exact versioned mapping round-trip. Unsupported versions,
unknown fields, malformed Associations, and digest tampering fail closed.
