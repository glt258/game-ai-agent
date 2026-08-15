# Controlled Vocabularies v0.2

The existing source, verification, role, ordinal, and attack-range vocabularies
remain unchanged from v0.1. Native taxonomy and mechanic summaries remain
free-form, source-backed facts.

## Provisional relation vocabulary

These are recommended terms, not a frozen enum:

`generates`, `consumed_by`, `enters_state`, `transitions_to`, `grants`, `requires`,
`modifies`, `replaces`, `enables`, `triggers`

The schema only requires a non-empty `snake_case` string. New Golden Records may
justify additional terms without a schema migration.
