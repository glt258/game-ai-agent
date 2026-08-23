# Character Skill Design S0.1: Failure Cases and Specification Freeze (v0.1.1)

## Status and purpose

S0.1 revises the specification-asset phase for character skill design. Building on the S0 domain language and failure boundaries, it freezes missing mechanic skeletons, locally incomplete mechanic links, and the canonical taxonomy boundary. It does not claim that current character generation already has a structured production skill kit.

Current production character output still expresses the ability concept as free text in `ability_concept`. S0 does not replace it with a new production field and does not decide the future production schema, provider, validator, or repair interface for `Skill Kit`.

## Scope

S0 covers only the following:

- Describe observable causal relationships in skill design using `Skill Kit Concept`, `Ability Entry`, `Trigger Subject`, `Effect Subject`, `Resource Loop`, `State Lifecycle`, `Summon Lifecycle`, `Team Interaction`, and `Mechanic Relation`.
- Freeze the meanings of `PASS`, `REPAIR`, and `FAIL`, together with their finding codes.
- Use 19 observation/oracle cases independent of the production skill-field shape to verify resources, states, summons, teammate interactions, role duties, mechanic expression, and request consistency.
- Give `deepseek-v4-flash` candidate-generation and Mimo v2.5 anonymous blind-review runs the same domain boundaries and comparable acceptance criteria.

## Non-goals

S0 does not do any of the following:

- It does not modify the current production ability representation; `ability_concept` remains the current state.
- It does not freeze or implement a future production `SkillKit` schema, add a production validator, connect a provider, or change the repair loop.
- It does not modify Character Canon, Reference Corpus, character-source vocabulary, or Canon Checker.
- It does not perform numerical balancing for damage, multipliers, frames, exact cooldowns, resource caps, or similar values.
- It does not design equipment, weapons, WeaponModule, Artifact Set, or any other equipable system.
- It does not treat Reference Corpus taxonomy as this project’s character-skill taxonomy. Reference Corpus may provide abstract precedents, but its content must not be copied verbatim or nearly verbatim.
- It does not write values other than `main_dps`, `sub_dps`, `support`, `healer`, `control`, and `defense` into `combat_role_profile`. Cross-taxonomy labels such as `on_field_dps` and `crowd_control` are rejected there.

## Domain invariants

1. Every acceptable skill-kit concept can identify the ability’s trigger subject, effect subject, and the mechanic relation between them; stylized rhetoric cannot replace a causal relationship by itself.
2. A resource loop must explain how a resource enters, is held, consumed or transformed, and cleared or leaves the loop; a name without loop relationships is incomplete.
3. A state must have establishment, activation, and exit or replacement relationships; a summon must additionally have appearance, effect, departure or replacement, or constraint relationships.
4. Team interaction must identify which teammate or teammate event is the trigger subject; “teammate” cannot be used as an ambiguous effect position.
5. Role duty is a hard request constraint. An ability effect that conflicts with the core duty is a failure that cannot be resolved by local completion.
6. The requested core mechanic must appear in observable relationships and include at least one concrete trigger→effect causal or temporal relationship bound to the request. A name or rhetoric without a mechanic skeleton is the non-repairable `MECHANIC_SKELETON_ABSENT`; an existing causal edge or design anchor missing only feedback, exit, or replacement is the locally repairable `REQUESTED_MECHANIC_UNREPRESENTED`.
7. `combat_role_profile` accepts only the six canonical roles; Reference Corpus taxonomy, damage patterns, and team-composition terms do not enter this role set.
8. Mutually contradictory hard constraints are request-level failures and cannot be bypassed by rewriting the candidate.
9. `PASS` is a complete specification result with no findings; `REPAIR` is a blocked but locally repairable candidate; `FAIL` is a blocked candidate or request with at least one non-repairable finding.

The S0.1 canonical taxonomy boundary follows B1.5’s fail-closed rule: a non-canonical role value entering `combat_role_profile` is a boundary violation; the legacy flat-alias seam does not apply to this canonical profile, automatic normalization is forbidden, and invalid values must not be written into the request’s canonical profile.

## Fixture field contract

The fixture top level always contains `schema_version`, `outcomes`, `finding_codes`, and an ordered `cases` array. `schema_version` is fixed to `character-skill-failure-cases/0.1.1`.

Each case always contains the following fields:

| Field | Meaning |
| --- | --- |
| `id` | A stable, ordered case identifier. S0.1 uses `skill_s0_01_...` through `skill_s0_19_...`; the original IDs 01–18 remain unchanged. |
| `title` | A case title intended for reviewers. |
| `category` | A domain-coverage category, such as `resource_loop` or `role_alignment`. |
| `request` | A request observation decoupled from production fields: `brief`, `hard_constraints`, `forbidden_elements`, and `combat_role_profile`. |
| `candidate_observation` | An observable candidate summary: `summary`, `declared_facts`, and `signals`; it is not the future SkillKit field contract. |
| `expected` | The oracle result: `outcome`, `blocking`, `repair_allowed`, and `findings`. |
| `coverage_tags` | Stable tags used by the acceptance-matrix coverage. |
| `rationale` | Why the case falls on that decision boundary. |

Each finding always contains `code`, `field_path`, `blocking`, and `repairable`. `field_path` points to an observable location in the observation or request and does not imply a production implementation path. `repairable` in the registry is a fixed property of that code.

## Outcome semantics

| outcome | blocking | repair_allowed | Meaning |
| --- | --- | --- | --- |
| `PASS` | `false` | `false` | Relationships are complete, role duty agrees with the request, and there are no findings. |
| `REPAIR` | `true` | `true` | A local missing, ambiguous, or incomplete relationship is found; completing it preserves the design intent, and every finding is repairable. |
| `FAIL` | `true` | `false` | A request-level contradiction, cross-taxonomy role contamination, Reference Corpus copying, role-duty conflict, or another locally unfixable problem is found; at least one finding is non-repairable. |

## Finding code registry

| code | Meaning | Repairable |
| --- | --- | --- |
| `RESOURCE_LOOP_INCOMPLETE` | The resource’s creation, consumption, transformation, or clearing relationships do not form a closed loop. | Yes |
| `FORBIDDEN_RESOURCE_INTRODUCED` | The candidate introduces a dedicated resource explicitly forbidden by the request. | No |
| `STATE_EXIT_MISSING` | A state has an establishment or activation relationship but no exit or replacement relationship. | Yes |
| `TRIGGER_SUBJECT_AMBIGUOUS` | The trigger subject cannot be distinguished from a teammate, enemy, character, or other subject. | Yes |
| `SUMMON_LIFECYCLE_INCOMPLETE` | The summon lacks a required appearance, effect, departure, replacement, or constraint relationship. | Yes |
| `ROLE_EFFECT_MISMATCH` | The ability’s core effect conflicts with the canonical role duty specified by the request. | No |
| `REQUESTED_MECHANIC_UNREPRESENTED` | The requested core mechanic has a concrete causal edge or design anchor but lacks one link such as feedback, exit, or replacement; local completion can repair it, and the mechanic name alone does not count. | Yes |
| `MECHANIC_SKELETON_ABSENT` | The requested core mechanic is only a name or rhetoric, with no concrete trigger→effect causal or temporal relationship bound to the request; recovery requires creating the design again rather than filling a local gap. | No |
| `CROSS_TAXONOMY_ROLE_LABEL` | Reference Corpus or another cross-domain taxonomy label contaminates `combat_role_profile`. | No |
| `REFERENCE_COPYING` | The candidate copies a specific skill relationship from Reference Corpus verbatim or nearly verbatim. | No |
| `HARD_CONSTRAINT_CONFLICT` | The request’s own hard constraints cannot all be satisfied at once. | No |
| `MULTI_SKILL_LOOP_INCOHERENT` | Resource read/write or trigger ordering across multiple abilities is contradictory and cannot form a traceable relationship. | Yes |

## 19-case acceptance matrix

Case order is a stable contract and must remain `01` through `19`; the original case IDs 01–18 remain unchanged:

| ID | category | Design boundary | outcome | finding |
| --- | --- | --- | --- | --- |
| `skill_s0_01_resource_loop_complete` | `resource_loop` | Complete resource creation, holding, consumption, and clearing | `PASS` | — |
| `skill_s0_02_resource_loop_incomplete` | `resource_loop` | Resource lacks a production or reset relationship | `REPAIR` | `RESOURCE_LOOP_INCOMPLETE` |
| `skill_s0_03_forbidden_resource` | `resource_loop` | A resource is introduced despite an explicit prohibition | `FAIL` | `FORBIDDEN_RESOURCE_INTRODUCED` |
| `skill_s0_04_state_exit_missing` | `state_lifecycle` | State has no exit or replacement relationship | `REPAIR` | `STATE_EXIT_MISSING` |
| `skill_s0_05_teammate_trigger_ambiguous` | `team_interaction` | Teammate-event trigger subject is ambiguous | `REPAIR` | `TRIGGER_SUBJECT_AMBIGUOUS` |
| `skill_s0_06_summon_lifecycle_incomplete` | `summon_lifecycle` | Summon lacks destruction, replacement, or constraint relationships | `REPAIR` | `SUMMON_LIFECYCLE_INCOMPLETE` |
| `skill_s0_07_main_dps_mismatch` | `role_alignment` | `main_dps` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_08_sub_dps_mismatch` | `role_alignment` | `sub_dps` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_09_support_mismatch` | `role_alignment` | `support` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_10_healer_mismatch` | `role_alignment` | `healer` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_11_control_mismatch` | `role_alignment` | `control` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_12_defense_mismatch` | `role_alignment` | `defense` hard duty conflicts with the candidate’s core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_13_requested_mechanic_missing` | `mechanic_representation` | Only mechanic name/rhetoric is present; trigger, effect, feedback, and causal/temporal relationships are absent | `FAIL` | `MECHANIC_SKELETON_ABSENT` |
| `skill_s0_14_cross_taxonomy_role` | `taxonomy_boundary` | Canonical taxonomy rejects a non-canonical role; the legacy flat-alias seam does not apply and automatic normalization is forbidden | `FAIL` | `CROSS_TAXONOMY_ROLE_LABEL` |
| `skill_s0_15_reference_copying` | `reference_integrity` | Corpus skill relationships are copied verbatim or nearly verbatim | `FAIL` | `REFERENCE_COPYING` |
| `skill_s0_16_hard_constraint_conflict` | `constraint_consistency` | Hard constraints inside the request cannot all be satisfied | `FAIL` | `HARD_CONSTRAINT_CONFLICT` |
| `skill_s0_17_multi_skill_loop` | `multi_skill_coherence` | Resource read/write ordering across abilities is inconsistent | `REPAIR` | `MULTI_SKILL_LOOP_INCOHERENT` |
| `skill_s0_18_control_near_neighbor_pass` | `team_interaction` | Control near-neighbor with an explicit teammate-event subject and complete summon lifecycle | `PASS` | — |
| `skill_s0_19_requested_mechanic_near_neighbor_repair` | `mechanic_representation` | Mechanic near-neighbor with an existing trigger→effect causal edge/design anchor but missing feedback | `REPAIR` | `REQUESTED_MECHANIC_UNREPRESENTED` |

Cases 07–12 must use `main_dps`, `sub_dps`, `support`, `healer`, `control`, and `defense` respectively as their primary role. Case 18 is intentionally retained as a positive `control` example so that control-related designs are not all rejected. Case 19 is the neighboring `REPAIR` example for case 13, proving that a mechanic with a skeleton but one missing link remains repairable. All 19 cases must cover every registry code, all three outcomes, every domain category, and all six canonical roles.

## S0.1 adjudication changes

`skill_s0_13_requested_mechanic_missing` is now `FAIL` with only `MECHANIC_SKELETON_ABSENT`: the candidate contains only echo/resonance rhetoric, with no trigger, effect, feedback, or causal/temporal relationship; recovery requires creating the design again.

`skill_s0_19_requested_mechanic_near_neighbor_repair` is the positive neighbor for case 13: the candidate has an explicit trigger→effect causal edge and design anchor but lacks feedback/write-back or exit, so it remains `REPAIR` with `REQUESTED_MECHANIC_UNREPRESENTED`. This finding is no longer counted from a mechanic noun alone.

`skill_s0_14_cross_taxonomy_role` remains `FAIL` / `CROSS_TAXONOMY_ROLE_LABEL`. B1.5 freezes cross-taxonomy input as fail closed; a non-canonical role value entering `combat_role_profile` cannot be corrected by the legacy flat-alias seam or automatic normalization. Case 14’s request canonical profile remains valid, and the invalid value is not written into it.

The `REPAIR` content and verdict for `skill_s0_05_teammate_trigger_ambiguous` remain unchanged. `skill_s0_18_control_near_neighbor_pass` continues to serve as the positive control example for the control role.

## Multi-model collaboration

### deepseek-v4-flash: candidate generation

`deepseek-v4-flash` reads the `request`, domain glossary, and non-oracle case observation to generate a candidate skill-kit concept for each case. A candidate only needs to describe observable subjects, relationships, lifecycles, and constraints. It must not invent new role vocabulary, numerical balance fields, verbatim Corpus content, or future production fields. The output must retain the case ID for later blind-review pairing.

### Mimo v2.5: anonymous blind review

The actual S0.1 review flow uses `deepseek-v4-flash` and Mimo v2.5 (reviewer ID `mimo-v2.5`) to independently judge the same non-oracle projection. Mimo receives only the request and candidate observation with `expected`, finding codes, signals, and rationale removed, and returns `PASS`, `REPAIR`, or `FAIL` with a reason.

Both reviewers are evidence sources, not the final specification judge. Codex/Sol applies the frozen oracle, reproducible case evidence, and focused tests to adjudicate disagreements; neither reviewer changes the repository, production schema, or repair loop.

### Codex/Sol: specification merge and S1 entry point

Codex/Sol compares the `deepseek-v4-flash` candidates, Mimo v2.5 blind review, and the S0 oracle to confirm that domain vocabulary, case boundaries, and the production state do not conflict. S1 begins only when all of the following are true:

1. Oracle and blind-review disagreements for all 19 cases have been explained case by case, especially the mechanic-skeleton boundaries for cases 13/19, the canonical-taxonomy fail-closed boundary for case 14, and the positive control example in case 18.
2. Stable evidence exists for every finding code, all six role duties, and cross-taxonomy isolation.
3. The minimum observable ability relationships to support in the future have been confirmed by domain discussion without being prematurely written as production fields.
4. The S1 interface candidate can evolve incrementally through the existing `ability_concept` compatibility path, with clear responsibility boundaries for the provider, repair, and evaluation layers.

The first S1 deliverable should be the interface candidate and migration/compatibility strategy. Only afterward should a Luna worker implement it with a test-first workflow; S0 itself does not submit production code.
