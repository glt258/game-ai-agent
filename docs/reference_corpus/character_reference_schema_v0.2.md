# Character Reference Corpus Schema v0.2

v0.2 is a persisted Facts schema change from `character-facts/0.1`. Existing
records are explicitly migrated; the loader does not silently accept v0.1 facts.
Analysis remains `character-analysis/0.1`; source provenance is now
`character-sources/0.2` and is documented separately in
`character_sources_schema_v0.2.md`.

## Fact graph

`facts.yaml` stores externally supported observations. Mechanics use a small node
and relation graph:

- `AbilityFact`: an ability and its short factual summary.
- `ResourceFact`: a named resource, optional description, and source-supported cap.
- `StateFact`: a named state and short factual summary.
- `TeamInteractionFact`: a structured team interaction that is not adequately
  represented by the simple buff/debuff/healing/shielding/grouping fields.
- `MechanicRelation`: a directed connection between two mechanic nodes.

Nodes are observed mechanic entities; edges are externally supported mechanic
relations. `MechanicRef` uses `{kind, id}` with kinds `ability`, `state`, `resource`,
and `team_interaction`. Every reference must resolve to a node in the same
character. Node IDs and relation IDs are unique within a character.

```yaml
combat:
  mechanics:
    resources:
      - resource_id: focus
        native_name: null
        description_summary: "A source-supported combat resource."
        cap: null
    states: []
  team_mechanics:
    interactions: []
  relations:
    - relation_id: team-generates-focus
      source: {kind: team_interaction, id: team-charge}
      relation_type: generates
      target: {kind: resource, id: focus}
```

`relation_type` is intentionally a validated provisional snake_case string, not a
frozen enum. Recommended provisional terms are documented separately and may
change as more Golden Records are ingested.

## Provenance and boundaries

Field evidence may point to `combat.mechanics.resources`,
`combat.mechanics.states`, `combat.team_mechanics.interactions`, and
`combat.relations`. Evidence for a relation is required just like evidence for any
other fact. The resolver supports non-indexed paths; it does not infer evidence for
individual list elements.

Do not compress a supported node-to-node mechanic relationship into a long
`description_summary`. Conversely, a relation must remain a mechanic fact, not a
design conclusion. Statements such as `high_team_dependency` or
`resource_builder_spender` belong in `analysis.yaml`.

The simple team fields remain available for simple characters. `interactions` is an
additional structured field, not a replacement for those fields.

## Analysis guidance

`PrimaryLoop` means the observed mechanic flow, not an optimal rotation. Also,
official-hosted does not automatically mean primary: source reliability follows the
content producer and the content itself.

This version does not implement analysis generation, PatternExtractor, RAG,
crawling, or graph queries.
