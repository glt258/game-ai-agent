# Character Skill Design Engineering Readiness and Multi-Model Collaboration Plan

Date: 2026-08-22
Baseline: [`011ad2e`](https://github.com/glt258/game-ai-agent/commit/011ad2e434fbe3ce6713d1b644724158b86b20f2) (`refactor: freeze combat role compatibility seam`)

## 1. Conclusion

The project is ready to begin the next phase of character skill design, but it is not yet suitable for letting a model freely generate complete skill kits. CI-B1.5 has frozen the combat-role compatibility boundary and solved consistency for role-semantic entry and serialization; skill design still lacks an independent, verifiable, repairable domain contract. The most reasonable next step is not to add more prompts or immediately balance numbers, but to define the conceptual skill-kit structure, failure cases, and acceptance criteria, then migrate the generation, validation, and repair pipeline incrementally.

The follow-up work should be divided into five phases, CS-S0 through CS-S4, with Codex as the primary engineer, `deepseek-v4-flash` responsible for candidate generation and real-provider observation through Hermes, and Mimo v2.5 responsible for independent red-team review and blind evaluation. There is currently no project evidence supporting Mimo v2.5’s specific engineering capabilities, so it should not own schema changes, code integration, or final adjudication. Its most valuable role is to independently find omissions, ambiguities, and false passes.

## 2. Existing capabilities and actual gaps

### 2.1 Stable character-semantic boundary

The current `CharacterDraft` and provider interface form a strict contract, and canonical combat roles are expressed only through `combat_role_profile`. The legacy flat `combat_role` exists only at a restricted compatibility entry point and is not part of canonical output. Shared parsing, alias restrictions, conflict handling, unknown-value rejection, and taxonomy isolation are centralized in [`src/combat_semantics/roles.py`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/combat_semantics/roles.py). Architectural policy is recorded in [`docs/character_generation/character_armament_architecture.md`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/docs/character_generation/character_armament_architecture.md), and frozen behavior is covered by [`tests/test_combat_role_compatibility_freeze_b15.py`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/tests/test_combat_role_compatibility_freeze_b15.py). Skill design can therefore depend on a unified role profile, but it must not reintroduce a second role scalar or expand the legacy alias.

### 2.2 Skill expression is still free text

Generated drafts currently have only the free-text `ability_concept` ([`CharacterDraft`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_generation.py#L145-L178); [provider schema](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/response_contracts.py#L41-L90)). It can describe a skill idea, but it cannot reliably represent skill subjects, trigger events, resource loops, state lifecycles, summon lifecycles, teammate interactions, or mechanic causality. The [representation validator](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/evaluation/validators/representation.py#L12-L59) mostly requires this field to be non-empty, so fluent prose may be mistaken for structural completeness. [Request alignment](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/evaluation/validators/request_alignment.py) currently validates combat roles mainly and cannot prove that the skill mechanic requested by the user is actually present in the draft.

This creates three direct risks. First, a model may write attractive but non-executable skill copy. Second, the validator cannot distinguish a missing mechanic from a misplaced subject or an unclosed lifecycle. Third, the [ABILITY repair domain still maps to the entire `ability_concept`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_repair.py#L65-L95), so it cannot locally repair one structured skill node. The next phase therefore needs not a longer `ability_concept`, but a small conceptual skill-kit representation with explicit boundaries.

### 2.3 Existing benchmarks already provide design signals

[Existing benchmark A/B](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_benchmark.py#L107-L138) already covers resource-loop prose, showing that the “gain—consume—recover—transform” loop is treated as part of generation quality. [Benchmark E/F](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_benchmark.py#L187-L208) records representation pressure explicitly: one class concerns who triggers a teammate event and who benefits, while another concerns a summon’s lifecycle from creation and existence through action, disappearance, or replacement. These pressures should no longer be handled through free-text special cases; they should become CS-S0 failure cases and drive the minimum field design for CS-S1.

### 2.4 Reference Corpus provides precedents, not Canon

Reference Corpus already contains structured [`AbilityFact`, `ResourceFact`, `StateFact`, `TeamInteractionFact`, and `MechanicRelation`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/reference_corpus/models.py#L128-L233). These types prove that skill facts can be decomposed and provide precedents for naming relationships and describing boundary cases. However, the [Corpus repository position](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/README.md#reference-corpus) is reference material, not project Canon and certainly not a skill template to copy directly. Design work may extract abstract structures and validation questions, but it must not copy existing character facts into a new character or modify or expand the Corpus for implementation convenience.

The [official authoring path](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/official_character_authoring.py#L128-L163) already exposes bounded reference summaries. This is suitable for controlled precedents: provide a small, request-relevant summary with source boundaries rather than placing the entire Corpus in context. The bounded-reference principle should remain in force so that one reference character does not steer every generated result.

## 3. Recommended roadmap

### CS-S0: Write failure cases and the specification first

Codex should first establish the skill-design specification and executable failure cases without changing the provider. At minimum, cover: a resource that is only consumed and never produced; a state with no end condition; an ambiguous teammate-event subject; a summon without destruction, replacement, or a cap; a skill effect that conflicts with `combat_role_profile`; a requested core mechanic that appears only as rhetoric; verbatim copying of a reference summary; and a non-character taxonomy contaminating the role profile. Every case must define the expected pass, rejection, or repairable result.

CS-S0 deliverables should be the specification document, glossary, acceptance matrix, and test fixtures rather than a production schema. `deepseek-v4-flash` may generate multiple failure candidates for the same request to expand case coverage. Mimo v2.5 should conduct a blind review without seeing Codex’s expected answer and identify specification ambiguity and potential false positives.

### CS-S1: Establish the conceptual skill-kit domain contract

Codex should design a minimal conceptual skill-kit contract. It should express concepts such as skill/passive entries, effect subjects, trigger or cast conditions, effects, resource reads and writes, state reads and writes, teammate interactions, summon lifecycles, mechanic relations, and display text. It should not prematurely introduce numerical balance fields such as multipliers, frame counts, or exact cooldown values. The contract should allow unknown or unspecified values while making clear which combinations must be closed.

The new interface should be a deep module: callers submit only a structured skill concept, while the module handles normalization, cross-field validation, and error localization. `ability_concept` may remain temporarily as a compatibility display or derived summary, but it must not remain the only source of truth. CS-S1 is complete when the schema, serialization, error model, and unit tests agree without breaking canonical `combat_role_profile`.

### CS-S2: Migrate generation, validation, and repair

Codex should connect the new contract in the order “generation → representation validation → request alignment → repair.” The generator emits a structured skill kit; the representation validator checks resources, states, subjects, and summon lifecycles; request alignment validates the user’s skill constraints rather than checking only combat roles; and repair accepts field-level diagnostics for local repair. If dual reads or compatibility conversion are needed during migration, define explicit exit conditions so that a second parallel representation does not persist indefinitely.

During this phase, `deepseek-v4-flash` runs candidate requests in Hermes’s real-provider environment and records format compliance, missing fields, repair stability, and repeated-call drift. It does not decide the schema directly; it returns real behavior evidence to Codex. Codex uses that evidence to modify the contract, code, and tests and owns final integration.

### CS-S3: Evaluate `deepseek-v4-flash` and Mimo v2.5 in the field

Establish a fixed input set and frozen scoring sheet. `deepseek-v4-flash` handles candidate generation, provider behavior tests, and repair-loop observation. Mimo v2.5 receives anonymized outputs and independently performs red-team and blind evaluation, focusing on misplaced subjects, fabricated loops, reference copying, role–skill inconsistency, and validator false passes. When their opinions conflict, the frozen specification, automated tests, and reproducible cases decide; model self-evaluation and majority vote do not.

Codex consolidates the evaluation, distinguishing schema defects, prompt defects, provider characteristics, and reviewer disagreement, and fixes only reproduced problems. Retain each failure case’s original input, structured output, diagnosis, repair output, and final decision so it becomes a reproducible regression asset.

### CS-S4: Freeze the skill contract

After focused tests, existing evals, the full test suite, and multi-model blind review have no blockers, freeze the canonical skill-kit contract, compatibility policy, and validator semantics. The freeze commit should use an allowlisted file scope and confirm that Reference Corpus, private scripts, and unrelated documents are not included. Only then decide whether the next milestone is content production, a numerical model, or runtime combat simulation; do not casually expand equipment, weapons, or Canon inside S4.

## 4. Model responsibility boundaries

| Participant | Primary responsibility | Must not own |
| --- | --- | --- |
| Codex | Specification, domain schema, code, tests, migration, integration, regression, and final engineering adjudication | Expanding scope without evidence or writing Canon directly |
| `deepseek-v4-flash` through Hermes | Candidate skill kits, failure samples, real-provider format behavior, and repair observation | Deciding the canonical schema alone or directly merging production code |
| Mimo v2.5 through Hermes | Independent red-team review, anonymous blind evaluation, counterexamples, and specification-ambiguity discovery | Code ownership or final acceptance; it should not own a critical path until its capabilities are established |

The recommended collaboration order is: Codex publishes the frozen CS-S0 input package; `deepseek-v4-flash` produces candidates and field logs; Mimo v2.5 performs an independent blind review; Codex turns reproducible issues into tests and advances CS-S1–CS-S2; CS-S3 runs a structurally identical evaluation; and Codex executes the CS-S4 freeze. This uses the models’ different generation and critique strengths while avoiding specification drift from three models editing the same interface at once.

## 5. Explicitly out of scope for this round

This roadmap does not include numerical balancing, damage multipliers, equipment or weapon-system design; it does not write to project Canon, modify or expand Reference Corpus, or broaden the legacy `combat_role` compatibility policy. The first execution card should be **CS-S0: Character Skill Design Failure Cases and Specification Freeze**. Only after CS-S0 can clearly answer what is structurally complete, what must be rejected, and what can be repaired should CS-S1 schema implementation begin.
