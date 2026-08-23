# Character Data README

Character records use the contract in [character_schema.yaml](character_schema.yaml) and the naming policy in [naming_rules.yaml](naming_rules.yaml). The contract is the shared data shape for character planning, NPC Agent expression, Knowledge Resolver inputs, Story Agent hooks and future combat integration. It does not create characters or replace the World Bible, faction canon, lore canon or knowledge rules.

## 1. Character Schema purpose

Every fixed character record has a stable `id`, naming data, a basic profile, institutional identity, social life, personality, ability boundary, narrative hooks, combat participation rationale, agent expression profile, canon constraints and retrieval tags. Required structure does not mean every field must contain invented information: optional identity layers and social background may be `null`, and collections may be empty when nothing is canonized.

## Gameplay Metadata

`gameplay` is product metadata for playable-character and gacha systems. Its rarity has exactly two values:

- `A`: lower-base-rarity formal playable character.
- `S`: higher-base-rarity formal playable character.

`A / S = game rarity`, not `world rank`. Rarity does not mean a character is weak, powerful, socially important, high-status, a leader, more important to the story, more knowledgeable, or a higher-rated ability user. It must not be inferred from ability strength, faction position, knowledge access, age, occupation, story importance, social class or nationality. It also must not change the character's canon, ability, secrets or narrative role.

The only Source of Truth for this metadata is `gameplay.rarity`. Do not add stars, SSR/UR labels, alternate rarity fields or post-progression rarity changes. A/S is never an in-world term: NPCs and characters do not call someone an “S-rank ability user” because the game record uses `rarity: S`.

```yaml
gameplay:
  playable: true
  rarity: S
  release_status: launch
```

An NPC-only record has no gameplay rarity:

```yaml
gameplay:
  playable: false
  rarity: null
  release_status: npc_only
```

The player-defined protagonist is outside the ordinary A/S gacha rarity system and may be playable without a rarity:

```yaml
gameplay:
  playable: true
  rarity: null
  release_status: launch
```

`release_status` has only these meanings:

- `launch` = currently formally playable character.
- `planned` = confirmed future playable character, not yet released.
- `unreleased` = planned as a playable character, but its release time or version is not yet determined.
- `npc_only` = currently NPC-only and outside the playable-character system.

Formal playability is owned by `gameplay.playable`; `combat` does not contain a duplicate `playable_candidate` field. When `gameplay.playable` is `true`, `combat.combat_participation_reason` must explain why this person can reasonably enter dangerous scenes. This is a narrative plausibility requirement, not a combat power rating.

`social_identity` is intentionally optional because a character may not yet have all social-background details fixed. `codename_design` and `naming_review` are also nullable under the rules described below.

## 2. Naming System purpose

The central rule is: **identity first, meaning second; use references when they help, never force them.** A display name is the player's primary identity and does not need to equal the legal name. Legal, native, localized, alias, codename, stage and online identities are separate layers because they serve different social contexts.

`name.mode` supports two cases:

- `fixed`: `display_name` is required and the record receives a fixed-name Naming Review.
- `player_defined`: `display_name` may be `null`; legal, native and localized names must not be forced. A player-defined protagonist may use `common_address: "协理人"`, empty identity arrays and `naming_review: null` without acquiring a Canon name.

## Character record outline

The following example shows the top-level record structure only. It is not a complete record that can directly pass Schema Validation; required nested fields are abbreviated intentionally.

```yaml
id: character_001
name:
  mode: fixed
  display_name: ""
  legal_name: null
  native_name: null
  localized_name: null
  aliases: []
  codename: null
  stage_name: null
  online_handle: null
  common_address: ""
name_design:
  strategy: [natural_naming]
  references: []
  linguistic_notes: ""
  thematic_connection: ""
  public_identity_connection: ""
  design_notes: ""
codename_design: null
address_rules: {}
naming_review:
  display_name: ""
  legal_or_native_name: ""
  codename_or_stage_name: ""
  naming_strategy: ""
  reference: "Reference: none"
  transformation: ""
  character_fit: ""
  player_memory_fit: ""
  naturalness_check: ""
basic_profile: {}
geography: {}
phenotype: {}
identity: {}
character_hook: {}
personality: {}
life: {}
ability: {}
narrative: {}
gameplay:
  playable: true
  rarity: A
  release_status: launch
combat:
  combat_participation_reason: ""
  tentative_role: none
  notes: ""
agent_profile: {}
canon_constraints: []
tags: []
```

Do not add a codename, alias or literary reference merely to fill a field. A codename must have a concrete social origin and current users. A reference must describe the extracted element and the transformation into this character's own identity.

## 3. Identity and Knowledge Resolver

`identity` records institutional position, not personality or the complete list of things a character knows:

```yaml
identity:
  faction_id: null
  division_ids: []
  roles: []
  responsibilities: []
  assignments: []
  explicit_grants: []
```

`faction_id` and `division_ids` reference `data/factions/factions.yaml`. Divisions must belong to the selected faction. Knowledge-facing `roles`, `responsibilities` and `assignments` must reference the corresponding vocabularies in `data/knowledge/knowledge_rules.yaml`. These are cross-file checks reserved for a future `scripts/validate_data.py`; this contract does not duplicate those source files.

Occupation is separate from Knowledge role. Being a researcher does not automatically grant `principal_investigator`; a formal role must be explicitly present in `identity.roles`.

`explicit_grants` is a string array for exceptional story authorization. Character records must not contain `known_lore`; knowledge is resolved from identity, `knowledge_rules.yaml` and explicit grants.

## 4. Ability and World Bible

`ability` describes a finite personal rule with a trigger, limitation, ordinary uses, professional uses and risks. It is not an elemental or universal power system and must not replace training or professional competence. When `ability.status` is `none`, its rule, trigger and limitation may be `null` and its use/risk arrays are empty.

The ability module follows the World Bible's model of an individual bias: it should remain bounded, contextual and testable. Risks may include fatigue, failure, cognitive confusion or scene-specific danger; they should not default to melodramatic loss-of-control language.

## 5. Agent profile and knowledge authorization

`agent_profile` controls how a character expresses information: speech style, communication habits, default information behavior and sensitive topics. It does not decide what the character knows. Do not add `known_lore` or a manually enumerated complete knowledge list; that would bypass the Knowledge Resolver and its access boundaries.

The schema records static `address_rules` only. It does not implement relationship progression or choose an address dynamically.

## 6. Player-defined protagonist

The player-defined protagonist does not receive a generated Canon name. A valid shape is:

```yaml
name:
  mode: player_defined
  display_name: null
  legal_name: null
  native_name: null
  localized_name: null
  aliases: []
  codename: null
  stage_name: null
  online_handle: null
  common_address: "协理人"
name_design:
  strategy: []
  references: []
  linguistic_notes: ""
  thematic_connection: ""
  public_identity_connection: ""
  design_notes: ""
naming_review: null
```

The remaining required Character modules still provide the Agent Identity structure; only the fixed-name requirements are relaxed. No formal character record is created by this README.

## Geography and Multi-City World

Character records do not assume that every person permanently lives in Linzhou. Use the `geography` module to describe where a character currently lives and acts:

```yaml
geography:
  current_city_id: city_linzhou
  home_district_id: null
  primary_activity_areas:
    - city_id: city_linzhou
      district_id: null
      location_id: null
  origin_context: null
```

`geography.current_city_id`, `geography.home_district_id` and `geography.primary_activity_areas` are geographic references, validated against the city, district and location source files when those files exist. `origin_context` is only for necessary growth or relocation context; it is not a nationality label. `identity.faction_id` remains organizational identity and must not be merged with geography.

The world supports multiple cities. `city_linzhou` / 临洲市 is currently the only formally established City Canon and the primary launch city, not the only city in the world. Future city records are added only when they are actually designed; do not create placeholder city IDs.

## Population Phenotype

The world contains multiple stable population phenotypes. These internal categories are data and design terms, not social ranks:

- `baseline_humanoid`
- `partial_theriomorphic`
- `full_theriomorphic`

`phenotype` is separate from `ability`, `rarity`, `personality`, `faction` and `nationality`:

```yaml
phenotype:
  category: partial_theriomorphic
  visible_traits:
    - 长耳结构
    - 短尾
  design_notes: >
    稳定生理表型，不属于个体偏置。
```

Animal-like visible traits do not automatically grant abilities, personality traits, professions, combat mechanics or A/S rarity. Full theriomorphic characters are ordinary members of society, not monsters or a secret population by default. Do not add species-power, racial-bonus or species-class fields.

## Minor Character Rule

Minor characters are allowed to be formal playable characters, students, family members, friends and city residents. Set `basic_profile.legal_age_status: minor` so Story Agent, Quest Agent and Combat Narrative can recognize the character's legal and everyday status. A minor must not be assumed to be a professional high-risk frontline worker; dangerous-scene participation requires a concrete `combat.combat_participation_reason` grounded in the story. No sexualized minor-specific data fields are part of this schema.

## Active Character Canon Status

The rejected v0.1 roster remains inactive in the explicitly marked archive. The current active fixed-character Canon is `data/characters/characters.yaml`, which contains seven launch fixed playable characters. The player-defined protagonist remains separate and is not one of these seven records. `launch_roster_concepts_v0.2.2.md` is design provenance, not the runtime Source of Truth.
