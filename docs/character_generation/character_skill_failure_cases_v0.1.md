# Character Skill Design S0: Failure Cases and Specification Freeze

## Status and Purpose

S0 is the specification-asset stage for character skill design. It freezes the observable domain language, failure boundaries, and acceptance cases used by later model collaboration and S1 interface design. It does not claim that current character generation already has a structured production skill kit.

The current production character output still expresses ability concepts through the free-text `ability_concept` field. S0 does not replace it with new production fields or decide the future production schema, provider, validator, or repair interface for `SkillKit`.

## Scope

S0 covers only the following:

- Describe observable causal relationships in skill design through `Skill Kit Concept`, `Ability Entry`, `Trigger Subject`, `Effect Subject`, `Resource Loop`, `State Lifecycle`, `Summon Lifecycle`, `Team Interaction`, and `Mechanic Relation`.
- Freeze the meanings of the three specification outcomes, `PASS`, `REPAIR`, and `FAIL`, and their finding codes.
- Validate resources, states, summons, teammate interactions, role responsibilities, mechanic representation, and request consistency through 18 observation/oracle cases that are independent of any production skill-field shape.
- Give DeepSeek and MiMo v2.5 the same domain boundaries and comparable acceptance criteria for candidate generation and anonymous blind review.

## Non-goals

S0 does not:

- Change the current production ability representation; `ability_concept` remains the current contract.
- Freeze or implement a future production `SkillKit` schema, add a production validator, connect a provider, or change the repair loop.
- Change the Character Canon, Reference Corpus, character-source vocabulary, or Canon Checker.
- Define numerical balance such as damage, multipliers, frame counts, exact cooldowns, or resource caps.
- Design equipment, weapons, `WeaponModule`, Artifact Sets, or any other equippable system.
- Treat the Reference Corpus taxonomy as this project's character-skill taxonomy. The Reference Corpus may provide abstract precedents but must not be copied verbatim or near-verbatim.
- Put any term other than `main_dps`, `sub_dps`, `support`, `healer`, `control`, or `defense` into `combat_role_profile`. Cross-taxonomy labels such as `on_field_dps` and `crowd_control` are rejected at that boundary.

## Domain Invariants

1. Every acceptable skill-kit concept must identify the trigger subject, the effect subject, and the mechanic relationship between them. Stylized rhetoric alone cannot replace causality.
2. A resource loop must state how a resource enters, is held, is consumed or transformed, and is cleared or removed on exit. A name without loop relationships is incomplete.
3. A state must have establishment, effect, and exit or replacement relationships. A summon must additionally have appearance, effect, departure or replacement, and constraint relationships.
4. A teammate interaction must identify the teammate class or teammate event that acts as the trigger subject; “teammate” cannot be used as an ambiguous effect location.
5. Role responsibility is a hard request constraint. A core ability effect that conflicts with that responsibility is not repairable through a local textual addition.
6. A core mechanic requested by the user must appear in observable relationships. Rhetoric without a mechanic relationship is a repairable defect in the v0.1 contract.
7. `combat_role_profile` accepts only the six canonical roles. Reference Corpus taxonomy terms, damage modes, and team-composition terms do not enter this set.
8. Mutually contradictory hard constraints are request-level failures and cannot be bypassed by rewriting the candidate.
9. `PASS` is a complete specification control with no findings. `REPAIR` is a blocked but locally repairable candidate. `FAIL` is a blocked candidate or request with at least one non-repairable finding.

## Fixture Field Contract

The fixture has exactly four top-level fields: `schema_version`, `outcomes`, `finding_codes`, and the ordered `cases` list. `schema_version` is fixed as `character-skill-failure-cases/0.1`.

Each case has exactly the following fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable, ordered case identifier. S0 uses `skill_s0_01_...` through `skill_s0_18_...`. |
| `title` | Reviewer-facing case title. |
| `category` | Domain coverage category, such as `resource_loop` or `role_alignment`. |
| `request` | Production-decoupled request observation: `brief`, `hard_constraints`, `forbidden_elements`, and `combat_role_profile`. |
| `candidate_observation` | Observable candidate summary: `summary`, `declared_facts`, and `signals`. It is not a field contract for a future `SkillKit`. |
| `expected` | Oracle decision: `outcome`, `blocking`, `repair_allowed`, and `findings`. |
| `coverage_tags` | Stable tags used by the acceptance matrix. |
| `rationale` | Explanation of why the case belongs on that decision boundary. |

Each finding has exactly `code`, `field_path`, `blocking`, and `repairable`. `field_path` points to an observable location in the observation or request and does not imply a production implementation path. The registry value of `repairable` is a fixed property of each code.

## Outcome Semantics

| outcome | blocking | repair_allowed | Meaning |
| --- | --- | --- | --- |
| `PASS` | `false` | `false` | Relationships are complete, role responsibilities match the request, and there are no findings. |
| `REPAIR` | `true` | `true` | A local relationship is missing, ambiguous, or incomplete. Completing it preserves the design intent, and every finding is repairable. |
| `FAIL` | `true` | `false` | The request or candidate has a contradiction, cross-taxonomy role contamination, Reference Corpus copying, role-responsibility conflict, or another problem that cannot be resolved through a local addition. At least one finding is non-repairable. |

## Finding Code Registry

| Code | Meaning | Repairable |
| --- | --- | --- |
| `RESOURCE_LOOP_INCOMPLETE` | The resource production, consumption, transformation, or cleanup relationships do not form a closed loop. | Yes |
| `FORBIDDEN_RESOURCE_INTRODUCED` | The candidate introduces a dedicated resource explicitly forbidden by the request. | No |
| `STATE_EXIT_MISSING` | A state has an establishment or effect relationship but no exit or replacement relationship. | Yes |
| `TRIGGER_SUBJECT_AMBIGUOUS` | The trigger subject cannot be distinguished from teammate, enemy, character, or other subjects. | Yes |
| `SUMMON_LIFECYCLE_INCOMPLETE` | A summon lacks a required appearance, effect, departure, replacement, or constraint relationship. | Yes |
| `ROLE_EFFECT_MISMATCH` | The core effect of an ability conflicts with the canonical role responsibility specified by the request. | No |
| `REQUESTED_MECHANIC_UNREPRESENTED` | The requested core mechanic remains only as rhetoric and has no observable mechanic relationship. | Yes |
| `CROSS_TAXONOMY_ROLE_LABEL` | A Reference Corpus or other cross-domain taxonomy label contaminates `combat_role_profile`. | No |
| `REFERENCE_COPYING` | The candidate copies a specific skill relationship from the Reference Corpus verbatim or near-verbatim. | No |
| `HARD_CONSTRAINT_CONFLICT` | The request's own hard constraints cannot all be satisfied. | No |
| `MULTI_SKILL_LOOP_INCOHERENT` | Resource reads/writes or trigger ordering across multiple abilities conflict and cannot form a traceable relationship. | Yes |

## 18-case Acceptance Matrix

Case order is a stable contract and must remain `01` through `18`:

| ID | Category | Design Boundary | Outcome | Finding |
| --- | --- | --- | --- | --- |
| `skill_s0_01_resource_loop_complete` | `resource_loop` | Complete resource production, holding, consumption, and cleanup | `PASS` | — |
| `skill_s0_02_resource_loop_incomplete` | `resource_loop` | Resource lacks a production or reset relationship | `REPAIR` | `RESOURCE_LOOP_INCOMPLETE` |
| `skill_s0_03_forbidden_resource` | `resource_loop` | Introduces a dedicated resource that the request explicitly forbids | `FAIL` | `FORBIDDEN_RESOURCE_INTRODUCED` |
| `skill_s0_04_state_exit_missing` | `state_lifecycle` | State has no exit or replacement relationship | `REPAIR` | `STATE_EXIT_MISSING` |
| `skill_s0_05_teammate_trigger_ambiguous` | `team_interaction` | Trigger subject for a teammate event is ambiguous | `REPAIR` | `TRIGGER_SUBJECT_AMBIGUOUS` |
| `skill_s0_06_summon_lifecycle_incomplete` | `summon_lifecycle` | Summon lacks destruction, replacement, or constraint relationships | `REPAIR` | `SUMMON_LIFECYCLE_INCOMPLETE` |
| `skill_s0_07_main_dps_mismatch` | `role_alignment` | Hard `main_dps` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_08_sub_dps_mismatch` | `role_alignment` | Hard `sub_dps` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_09_support_mismatch` | `role_alignment` | Hard `support` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_10_healer_mismatch` | `role_alignment` | Hard `healer` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_11_control_mismatch` | `role_alignment` | Hard `control` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_12_defense_mismatch` | `role_alignment` | Hard `defense` responsibility conflicts with the candidate's core effect | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_13_requested_mechanic_missing` | `mechanic_representation` | Core mechanic remains only as rhetoric | `REPAIR` | `REQUESTED_MECHANIC_UNREPRESENTED` |
| `skill_s0_14_cross_taxonomy_role` | `taxonomy_boundary` | `on_field_dps` or `crowd_control` contaminates the role profile | `FAIL` | `CROSS_TAXONOMY_ROLE_LABEL` |
| `skill_s0_15_reference_copying` | `reference_integrity` | Copies a Corpus skill relationship verbatim or near-verbatim | `FAIL` | `REFERENCE_COPYING` |
| `skill_s0_16_hard_constraint_conflict` | `constraint_consistency` | The request contains hard constraints that cannot be satisfied together | `FAIL` | `HARD_CONSTRAINT_CONFLICT` |
| `skill_s0_17_multi_skill_loop` | `multi_skill_coherence` | Multi-ability resource read/write ordering is inconsistent | `REPAIR` | `MULTI_SKILL_LOOP_INCOHERENT` |
| `skill_s0_18_control_near_neighbor_pass` | `team_interaction` | Control near-neighbor with an explicit teammate-event subject and complete summon lifecycle | `PASS` | — |

Cases 07–12 must use `main_dps`, `sub_dps`, `support`, `healer`, `control`, and `defense`, respectively, as their primary roles. Case 18 is an intentional positive `control` example that prevents all control-related designs from being rejected. The complete case set must cover every registry code, all three outcomes, every domain category, and all six canonical roles.

## Multi-model Collaboration

### DeepSeek: Candidate Generation

DeepSeek reads the `request`, domain glossary, and non-oracle case observation to generate a candidate skill-kit concept for each case. A candidate only needs to describe observable subjects, relationships, lifecycles, and constraints. It must not invent new role vocabulary, numerical balance fields, verbatim Corpus content, or future production fields. The output must retain the case ID for later blind-review pairing.

### MiMo v2.5: Anonymous Blind Review

MiMo v2.5 receives only the request, candidate observation, and necessary domain definitions after the `expected` outcome and finding codes have been removed. It independently assigns `PASS`, `REPAIR`, or `FAIL` and provides a reason. It does not modify the repository, decide the production schema, or serve as the final specification authority. Its purpose is to identify an oracle that is too broad or too narrow and cases where stylistic differences are incorrectly treated as structural defects.

### Codex/Sol: Specification Reconciliation and the S1 Gate

Codex compares the DeepSeek candidate, MiMo v2.5 blind review, and S0 oracle to confirm that the domain vocabulary and case boundaries do not conflict with production reality. S1 begins only when all of the following are true:

1. Every oracle/reviewer disagreement across the 18 cases has been explained, especially ensuring that the case 18 positive `control` example is not universally rejected.
2. Every finding code, all six role responsibilities, and cross-taxonomy isolation have stable evidence.
3. Domain discussion has confirmed the minimum observable ability relationships needed in the future without prematurely expressing them as production fields.
4. S1 interface candidates can evolve incrementally through the existing `ability_concept` compatibility path and clearly separate provider, repair, and evaluation responsibilities.

The first S1 deliverable must be interface candidates plus a migration and compatibility strategy. Only then should a Luna worker implement it test-first. S0 itself does not commit production code.
