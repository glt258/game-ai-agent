# CS-S2 Multi-Case Generalization Pilot v0.1

This offline pilot tests the shared Hybrid Semantic IR pipeline against four
authoritative semantic families without calling a real provider:

| Case | Family | Distinguishing semantic path |
| --- | --- | --- |
| `generalization_support_alternate_v1` | Alternate Support | ally action completion → team enablement → modified continuation |
| `generalization_dps_v1` | DPS | self invocation → enemy direct output → enabled continuation |
| `generalization_control_v1` | Control | scene entry → enemy action control → modified continuation |
| `generalization_reaction_heal_v1` | Passive/Reaction | ally damage received → ally mitigation → recovery continuation |

The cases are defined by `build_authoritative_case_registry` and share the
same generation-context, semantic IR validator, compiler, canonical parser,
reference-integrity check, evaluator, diagnostics, and identity machinery.
The hand-authored Semantic IR goldens are test-only fixtures and are never
included in the model-facing request.

The frozen aligned contract `semantic-skill-plan-ir-contract/0.4.0` remains
unchanged for the historical support configuration. The pilot uses
`semantic-skill-plan-ir-contract/0.5.0`, a generic vocabulary correction that
adds only the cross-family effect intents `deal_damage`, `control_enemy`, and
`mitigate_ally`. The canonical compiler remains deterministic and owns all
IDs, references, and schema fields.

Each future live cohort is independent: purpose
`multi-case-generalization-pilot`, target `N=1`, sample index `1`, and a
case-bound deterministic run identity. This document and its tests do not
enable a provider or create live evidence.
