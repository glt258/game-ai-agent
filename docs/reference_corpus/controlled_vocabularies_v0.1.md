# Controlled Vocabularies v0.1

The following values are frozen for this schema version:

- `SourceType`: `official`, `wiki`, `database`, `media`, `guide`, `video`, `other`
- `SourceReliability`: `primary`, `secondary`, `tertiary`, `unknown`
- `VerificationStatus`: `verified`, `partially_verified`, `unverified`, `conflicted`
- `AnalysisStatus`: `missing`, `partial`, `completed`
- `NormalizedRole`: `on_field_dps`, `off_field_dps`, `burst_dps`, `support`, `sustain`, `control`, `hybrid`, `unknown`
- `OrdinalBand`: `low`, `medium`, `high`, `variable`, `unknown`
- `AttackRange`: `melee`, `ranged`, `hybrid`, `variable`, `unknown`

Native game taxonomy remains a free-form mapping under
`facts.combat.native_taxonomy.labels`. It is not translated into a universal RPG
taxonomy. Cross-game normalized design language belongs under `analysis.combat_design`.

`archetypes`, design-pattern labels, mechanic tags, selling points, and visual hooks
remain constrained non-empty strings but are deliberately not frozen into large enums
in v0.1. The archetype vocabulary has not been finalized.
