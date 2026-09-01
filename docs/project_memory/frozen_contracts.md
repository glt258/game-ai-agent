# Frozen Contract Index

This file indexes contracts; the implementation and tests remain authoritative.

| Contract | Graph node | Source | Tests / freeze evidence |
|---|---|---|---|
| CharacterDraft is a reviewable proposal, not Canon | `contract.character_draft` | `src/agents/character_generation.py` | `tests/test_character_generation.py`; `docs/runtime_freeze_v0.6.6.md` |
| CanonChecker is deterministic and read-only | `component.canon_checker` | `src/agents/canon_checker.py` | `tests/test_canon_checker.py`; runtime freeze |
| Repair is bounded to one attempt and fully rechecked | `component.character_repair_workflow` | `src/agents/character_repair.py` | `tests/test_character_repair.py`; `docs/character_repair_loop_v0.1.1.md` |
| Six canonical combat roles with bounded legacy input seam | `component.combat_role_profile` | `src/combat_semantics/roles.py` | B12/B15 combat-role tests |
| Semantic IR precedes deterministic SkillKit compilation | `component.semantic_skill_ir`, `component.skillkit_compiler` | `src/character_intelligence/semantic_ir`, `src/character_intelligence/compiler` | `docs/character_generation/character_skill_design_v1_freeze_v1.0.md` |
| Reference Corpus is separate from Project Canon | `component.reference_corpus` | `src/reference_corpus/repository.py` | reference-corpus tests; corpus baseline doc |
