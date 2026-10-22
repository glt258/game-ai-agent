# Character Reference Corpus Schema v0.3

v0.3 is a persisted `CharacterFacts` schema change from
`character-facts/0.2`. Existing Facts records are explicitly migrated; the
loader accepts `character-facts/0.3` and does not silently accept v0.2 Facts.
`character-sources/0.2` and `character-analysis/0.1` remain unchanged.

## StateFact.subject_scope

`subject_scope` identifies the subject that carries or is affected by the state.
It does not identify the entity that created or applied the state. Application
source remains represented by `MechanicRelation`, for example:

```yaml
states:
  - state_id: empowered-mode
    subject_scope: self
  - state_id: marked-target
    subject_scope: target
```

The provisional controlled vocabulary is:

- `self`: the character's own empowered, transformed, or status state.
- `target`: a state or condition applied to an ability target.
- `unknown`: current evidence does not establish the subject.

This is a Golden Pilot provisional vocabulary, not a permanent exhaustive
ontology. Values such as `ally`, `party-wide`, `field-state`, or
`summon-state` require a future review based on real records.

Collection-level evidence at `combat.mechanics.states` continues to cover the
state collection, including `state_id`, `native_name`, `subject_scope`, and
`description_summary`. No indexed or ID-specific evidence selector is added.

## Boundaries

Do not infer scope from who applies a state. If a character applies Status X to
an enemy, the state subject is `target`, not `self`. When evidence does not
establish the subject, record `unknown` rather than guessing.

`subject_scope` is a Fact because it answers who the state affects. A conclusion
such as “marked-target is a target-condition payoff gate” belongs in
`analysis.yaml`.
The model does not add `application_source`, `target_scope`, or a general
combat-event DSL. `MechanicRelation`, `AbilityFact`, and `ResourceFact` are
unchanged.
