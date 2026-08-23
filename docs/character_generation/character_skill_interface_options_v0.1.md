# Character Skill Design CS-S1: SkillKit Interface Candidates and Recommended Scheme (contract v0.1)

## Status

This document is CS-S1's interface-design and prototype-execution contract; it is not a production schema freeze. It inherits the 19 cases, finding registry, and CI-B1.5 canonical-taxonomy boundaries from CS-S0.1 contract v0.1.1. For now, it does not modify `src/`, the production provider, the production validator, or the existing repair loop.

CS-S1 must answer this question: what is the smallest structure that can express the observable relationships in a skill mechanic while allowing the validator to distinguish an unrepairable design omission from a relation gap that can be completed locally?

## 1. Current-State Inventory and Compatibility Constraints

### 1. Current data flow

Character requests are carried by `CharacterDesignRequest`. The canonical combat role in the request is expressed only through `combat_role_profile`, and becomes `CombatRoleProfile` before entering the generation flow.

During generation, the `character_draft` response contract requests a complete `CharacterDraft` root object. The current JSON Schema uses `additionalProperties: false` and requires every property to appear in provider output; the only ability field is still the required string `ability_concept`. Therefore, under the current contract, the provider cannot emit an unknown `skill_kit` field in advance.

`CharacterDraft.from_mapping()` is the current deserialization boundary. The old flat `combat_role` passes through a bounded crosswalk only at this restricted legacy seam; canonical `combat_role_profile` itself accepts neither aliases nor cross-taxonomy normalization. Serialization emits only the canonical profile.

The current representation validator checks only that `ability_concept` is non-empty. The request-alignment validator checks only the primary and secondary canonical roles; it cannot prove that the specific skill mechanics in the request have entered the candidate.

The current repair loop performs at most one bounded repair. The ABILITY hard-constraint domain and repair dependency both map to the entire `ability_concept` field; there is no local edit address at relation, entity, or lifecycle granularity. Existing Character repair also owns Canon, safety evidence, frozen fields, and regression protection. SkillKit repair must not bypass those boundaries.

The Reference Corpus already contains ability/resource/state/team-interaction/relation types, but it is a reference fact model, not the production CharacterDraft contract and not a copyable skill template. CS-S1 borrows only the abstract precedent that explicit entities and relationships can be validated.

### 2. Boundaries CS-S1 must retain

- `ability_concept` remains a compatibility display field until migration is complete.
- `CombatRoleProfile` remains the sole authority for character positioning. SkillKit stores no second role profile and provides no legacy alias seam.
 - The provider candidate must allow semantically missing or ambiguous states. If the schema requires a complete trigger/effect/lifecycle during parsing, cases 05, 06, 13, and 19 collapse into the same malformed-response category and the CS-S0.1 findings can no longer hold.
- “Allow semantic incompleteness” does not mean relaxing structure: the field set, IDs, tagged unions, and reference shapes still fail closed. Nullable/empty slots are used only so the deterministic validator can locate relation gaps.
- Do not add multipliers, damage values, attack power, critical-hit rate, frame counts, exact cooldowns, exact durations, resource caps, or other numerical balance fields.
- Request, provider candidate, validation report, and repair patch are four different kinds of data; none may impersonate a source of facts for another.

## 2. Shared Evaluation Vocabulary

All three candidates must be assessable from the same context:

```python
@dataclass(frozen=True)
class SkillIntent:
    mechanic_requirements: tuple[MechanicRequirement, ...]
    forbidden_mechanic_families: tuple[str, ...]
    hard_constraint_conflicts: tuple[str, ...]

@dataclass(frozen=True)
class SkillValidationContext:
    intent: SkillIntent
    combat_role_profile: CombatRoleProfile
    reference_review_context: ReferenceReviewContext | None = None
```

`SkillIntent` is produced by the request adapter, not declared by the provider candidate. The validator treats the CS-S0.1 registry as the sole authority for findings and outcomes. Reference copying requires an external read-only review context; a candidate cannot self-certify.

## 3. Candidate A: Ability-local Causal Aggregate

### 1. Shape

Candidate A makes each ability the smallest author-facing unit and embeds trigger→effect relations directly inside the ability:

```python
@dataclass(frozen=True)
class SubjectRef:
    kind: Literal["self", "ally", "team", "enemy", "scene", "summon"]
    selector: str | None
    ref: str | None = None

@dataclass(frozen=True)
class MechanicRelation:
    relation_id: str
    mechanic_id: str
    mechanic_kind: Literal["action", "resource", "state", "summon", "team_interaction"]
    operation: str
    trigger_subject: SubjectRef | None
    trigger_event: str | None
    effect_subject: SubjectRef | None
    effect_change: str | None
    request_requirement_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class AbilityEntry:
    ability_id: str
    name: str
    concept: str
    relations: tuple[MechanicRelation, ...]

@dataclass(frozen=True)
class AggregateSkillKitCandidate:
    schema_version: Literal["skill-kit-candidate/0.1"]
    entries: tuple[AbilityEntry, ...]
    role_evidence: tuple[RoleEvidence, ...]
    display_summary: str
```

Resources, states, summons, and team interactions use the same relation shape and operation vocabulary. Internally, the validator builds a cross-ability index by mechanic ID.

### 2. Usage

A summon-control ability contains, in the same ability, a relation where an ally event triggers a spawn, an act relation where the summon changes enemy actions, and a relation where scene exit or a second summon triggers replacement. Role evidence points to the relation that changes enemy actions.

### 3. Strengths and weaknesses

The provider generates and reads by skill, so common single-skill mechanics stay compact; one relation shape is also enough to cover all CS-S0.1 lifecycle and mechanic relations.

The main weakness is that a cross-skill resource loop is scattered across multiple abilities, so the same mechanic identity is repeated in multiple relations. The validator must rebuild the global graph and handle conflicting duplicate declarations. If the canonical role profile were also placed in SkillKit, it would create a second authority for character positioning; therefore this candidate permits role evidence only and does not store profile values.

## 4. Candidate B: Normalized Typed Causal Graph

### 1. Shape

Candidate B normalizes abilities, events, resources, states, and summons into nodes, and represents mechanics as global typed edges:

```python
@dataclass(frozen=True)
class MechanicNode:
    node_id: str
    kind: Literal["ability", "event", "resource", "state", "summon"]
    subject: SubjectRef | None

@dataclass(frozen=True)
class MechanicEdge:
    edge_id: str
    ability_id: str
    kind: Literal["causes", "requires", "enables", "feedback", "ends", "replaces"]
    phase: Literal["skeleton", "feedback", "exit", "replacement"]
    source_id: str | None
    target_id: str | None
    operation: str | None
    semantic_class: str | None
    request_requirement_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class GraphSkillKitCandidate:
    schema_version: Literal["skill-kit-candidate/0.1"]
    entries: tuple[AbilityEntrySummary, ...]
    nodes: tuple[MechanicNode, ...]
    edges: tuple[MechanicEdge, ...]
    role_evidence_edge_ids: tuple[str, ...]
```

### 2. Usage

Resource create/hold/consume/clear, state enter/effect/exit, and summon spawn/act/exit/replace are controlled edges on the same graph. A coherent multi-skill loop can be checked directly through reachability and producer/consumer topology.

### 3. Strengths and weaknesses

This is the most expressive option. Case 13 and case 19, cross-ability resource loops, dangling references, and relation-level repair can all be located precisely; SkillKit does not need a parallel lifecycle source of truth.

The cost is longer provider output and a larger surface for ID/reference errors. Complex discriminated unions also increase adaptation pressure across structured-output providers. For most simple abilities, the model must first learn a graph-database-style representation, making the authoring experience heavy. CS-S1 has no evidence that this complexity needs to be exposed in the public/provider interface.

## 5. Candidate C: Behavior Protocol + Lifecycle Lease

### 1. Shape

Candidate C expresses common mechanics as behavior protocols: a clear subject experiences an event, produces an ordered set of effects, and may optionally produce feedback. Resources, states, and summons use typed lifecycle leases that reference those effects.

```python
@dataclass(frozen=True)
class Subject:
    kind: Literal["self", "ally", "team", "enemy", "scene", "summon"]
    selector: str | None
    ref: str | None = None

@dataclass(frozen=True)
class Trigger:
    subject: Subject | None
    event: str | None
    qualifier: str | None = None

@dataclass(frozen=True)
class Effect:
    effect_id: str
    subject: Subject | None
    operation: Literal[
        "direct_output", "follow_up_output", "ally_enablement",
        "recover_or_mitigate", "enemy_action_control", "threat_protection",
        "resource_gain", "resource_use", "resource_transform", "resource_clear",
        "state_enter", "state_apply", "state_exit", "state_replace",
        "summon_spawn", "summon_act", "summon_exit", "summon_replace",
        "emit_event"
    ] | None
    object_ref: str | None = None
    description: str = ""

@dataclass(frozen=True)
class BehaviorProtocol:
    protocol_id: str
    implements: tuple[str, ...]
    when: Trigger | None
    causes: tuple[Effect, ...]
    feedback_effect_refs: tuple[str, ...] = ()

@dataclass(frozen=True)
class AbilityEntry:
    ability_id: str
    name: str
    mode: Literal["active", "passive", "reaction"]
    protocols: tuple[BehaviorProtocol, ...]
    display_text: str = ""

@dataclass(frozen=True)
class ResourceLease:
    resource_id: str
    opened_by: tuple[str, ...]
    used_or_transformed_by: tuple[str, ...]
    closed_by: tuple[str, ...]

@dataclass(frozen=True)
class StateLease:
    state_id: str
    established_by: tuple[str, ...]
    active_effects: tuple[str, ...]
    ended_or_replaced_by: tuple[str, ...]

@dataclass(frozen=True)
class SummonLease:
    summon_id: str
    spawned_by: tuple[str, ...]
    active_effects: tuple[str, ...]
    departed_by: tuple[str, ...]
    repeat_policy: Literal["replace", "refresh", "reject"] | None

@dataclass(frozen=True)
class RoleEvidence:
    duty: Literal[
        "direct_output", "follow_up_output", "ally_enablement",
        "recover_or_mitigate", "enemy_action_control", "threat_protection"
    ]
    effect_refs: tuple[str, ...]
    centrality: Literal["core", "secondary"]

@dataclass(frozen=True)
class ProtocolSkillKitCandidate:
    schema_version: Literal["skill-kit-candidate/0.1"]
    entries: tuple[AbilityEntry, ...]
    resources: tuple[ResourceLease, ...] = ()
    states: tuple[StateLease, ...] = ()
    summons: tuple[SummonLease, ...] = ()
    role_evidence: tuple[RoleEvidence, ...] = ()
    display_summary: str = ""
```

Every property appears in the strict provider schema; semantically missing slots use `null` or empty arrays. The shape parser rejects only unknown fields, invalid tags, duplicate IDs, and wrong types. The semantic validator then evaluates ambiguous subjects, the mechanic skeleton, and lifecycle closure.

### 2. Usage

```json
{
  "schema_version": "skill-kit-candidate/0.1",
  "entries": [
    {
      "ability_id": "echo_field",
      "name": "Echo Device",
      "mode": "reaction",
      "protocols": [
        {
          "protocol_id": "ally_action_to_field",
          "implements": ["req_echo"],
          "when": {
            "subject": {"kind": "ally", "selector": "triggering_ally", "ref": null},
            "event": "requested_action_completed",
            "qualifier": null
          },
          "causes": [
            {
              "effect_id": "spawn_field",
              "subject": {"kind": "summon", "selector": "created_entity", "ref": "control_field"},
              "operation": "summon_spawn",
              "object_ref": "control_field",
              "description": "The control device appears"
            },
            {
              "effect_id": "restrict_enemy",
              "subject": {"kind": "enemy", "selector": "affected_enemy", "ref": null},
              "operation": "enemy_action_control",
              "object_ref": "control_field",
              "description": "The device changes the enemy's available actions"
            }
          ],
          "feedback_effect_refs": []
        }
      ],
      "display_text": "After a designated ally completes an action, the character deploys a device that changes enemy actions."
    }
  ],
  "resources": [],
  "states": [],
  "summons": [
    {
      "summon_id": "control_field",
      "spawned_by": ["echo_field/spawn_field"],
      "active_effects": ["echo_field/restrict_enemy"],
      "departed_by": ["event:scene_exit"],
      "repeat_policy": "replace"
    }
  ],
  "role_evidence": [
    {
      "duty": "enemy_action_control",
      "effect_refs": ["echo_field/restrict_enemy"],
      "centrality": "core"
    }
  ],
  "display_summary": "Responds to an explicit ally event and deploys a control device with exit/replacement rules."
}
```

### 3. Strengths and weaknesses

This best matches the provider's natural generation order: when it happens, who triggers it, and what it does to whom. Lifecycle gaps map to explicit lease slots, which suits typed local patches; role evidence is duty evidence, not a second role taxonomy.

The cost is a small amount of duplication between leases and effect references, so the validator must still check that they agree. The controlled event/operation vocabulary needs versioning. CS-S1 does not accept a generic `custom` operation: creative variation stays in description text, but description text alone cannot satisfy mechanic, role-duty, or lifecycle hard constraints.

## 6. Scheme Comparison and Sol's Decision

### 1. Coverage of CS-S0.1's 19 cases

All three schemes have theoretical expressive power. A evaluates lifecycle through ability-local relations; B checks the global graph directly; C checks the protocol skeleton and lifecycle leases. Cases 07–12 all require mapping canonical-role duties to verifiable effect evidence; a provider's self-reported role tag is not sufficient.

B is the most direct for case 17's cross-skill resource topology; A and C need to build an internal graph first. C gives the clearest local-gap location for cases 04, 06, and 19 because each gap corresponds to an addressable lease/protocol slot.

### 2. `MECHANIC_SKELETON_ABSENT`

The freeze boundary must be “does a complete trigger→effect causal edge bound to a request requirement exist?”, not a count of mechanic nouns:

- Case 13 lacks the complete combination `when.subject + when.event + causes[*].subject + operation`. Even if display text repeats “echo/resonance,” it remains the unrepairable `MECHANIC_SKELETON_ABSENT`.
- Case 19 has the complete combination above and is bound to a request requirement; it lacks only the feedback requested by the request, so it is locally repairable as `REQUESTED_MECHANIC_UNREPRESENTED`.

The candidate layer must allow `when=null`, nullable subject/event, or `causes=[]`; otherwise these two boundaries disappear during parsing.

### 3. CI-B1.5 taxonomy fail-closed behavior

B's `profile_ref` idea is safest, while C's role evidence is best for authors. The recommendation is to combine them: SkillKit stores duty evidence only; the validator reads the already-constructed `CombatRoleProfile` from external context. Any raw invalid profile must be rejected at the existing canonical parser boundary, must not call `normalize_legacy_combat_role`, and must not enter SkillKit repair.

### 4. Incremental compatibility with `ability_concept`

A, B, and C cannot be added directly to the current strict provider root. The recommendation is to use a sidecar associated by `draft_id` for CS-S1/CS-S2 shadow evaluation. The old `ability_concept` is not automatically parsed into structured mechanics; that inference would incorrectly promote attractive prose to mechanic facts.

When the production contract is upgraded, `skill_kit` should be required-but-nullable in the new strict schema. Missing fields in old payloads are converted to `None` only by an explicit legacy deserialization seam. Once `skill_kit` exists, it is the source of mechanic facts; `ability_concept` is generated or checked by the renderer and continues serving old consumers.

### 5. Provider, validator, and repair boundaries

The provider generates only candidate shape, stable kit-local IDs, explicit subjects/events/effects, lifecycle references, and role evidence. It does not output verdicts, findings, or repairability; define request requirements; or perform taxonomy normalization.

The validator is the sole authority for the finding registry, cross-field relationships, role duties, request alignment, reference copying, and `PASS/REPAIR/FAIL`. It checks the request and canonical profile first, then the candidate graph; shape-valid does not mean semantic `PASS`.

Repair handles only reports in which every finding is repairable, and uses a typed patch with a base digest to modify authorized protocol/lease slots. Case 13, taxonomy issues, role mismatches, forbidden resources, copying, and request conflicts do not enter local repair. After a patch, the same validator must run a full recheck; if there is no improvement or a regression, retain the original candidate.

### 6. Avoiding premature numerical balance fields

None of the three schemes needs numerical fields to cover all 19 cases. CS-S1 expresses only event categories, subjects, operations, references, causality/ordering, resource entry/exit, state exit, summon replacement, and duty evidence. If numerical requirements genuinely arise later, discuss them in a separate version and separate balance contract; do not bypass this phase's boundary with a free `parameters` map.

## 7. Recommended Scheme: Protocol Surface / Derived Graph Core

Sol recommends candidate C as the provider-facing contract and derives candidate B's typed causal graph inside the module. The public surface follows the common authoring order, while reachability, lifecycle, and finding aggregation are hidden in the deep module.

The recommended public interface is:

```python
class SkillKitContract:
    def parse_candidate(self, payload: Mapping[str, object]) -> ProtocolSkillKitCandidate: ...

    def evaluate(
        self,
        candidate: ProtocolSkillKitCandidate,
        context: SkillValidationContext,
    ) -> SkillKitAssessment: ...

    def apply_patch(
        self,
        candidate: ProtocolSkillKitCandidate,
        patch: SkillKitPatch,
        report: SkillValidationReport,
        context: SkillValidationContext,
    ) -> SkillKitAssessment: ...

    def render_ability_concept(
        self,
        candidate: ProtocolSkillKitCandidate,
    ) -> str: ...
```

The module handles:

- compiling protocols/effects/leases into a normalized graph;
- validating IDs, references, subjects, event/effect causal edges, and lifecycle;
- validating that role evidence points to real, semantically matching effects;
- checking reachability for cross-ability producers/consumers;
- distinguishing case 13 from case 19;
- emitting stable field paths, repairability, and outcomes;
- validating patch scope and base digest, then checking the result again;
- deterministically rendering a compatible `ability_concept`.

Do not make `compile(payload, context)` the sole entry point. Shape errors, semantic findings, and request conflicts must remain separate error domains so provider retry, validator verdicts, and repair policy stay clear.

## 8. Acceptance Mapping for the 19 Cases

- 01: the resource lease has complete open/use-or-transform/close references; `PASS`.
- 02: the resource lease lacks a producer or close; `RESOURCE_LOOP_INCOMPLETE`.
- 03: the request forbids a dedicated resource but the candidate contains a resource lease/effect; `FORBIDDEN_RESOURCE_INTRODUCED`.
- 04: the state is established/active but has no exit/replace reference; `STATE_EXIT_MISSING`.
- 05: the ally trigger lacks a selector or event category; `TRIGGER_SUBJECT_AMBIGUOUS`.
- 06: the summon has spawn/act but no depart/replace/constraint; `SUMMON_LIFECYCLE_INCOMPLETE`.
- 07: `main_dps` has no core direct-output evidence; `ROLE_EFFECT_MISMATCH`.
- 08: `sub_dps` has no core follow-up-output evidence; `ROLE_EFFECT_MISMATCH`.
- 09: `support` has no core ally-enablement evidence; `ROLE_EFFECT_MISMATCH`.
- 10: `healer` has no core recovery/mitigation evidence; `ROLE_EFFECT_MISMATCH`.
- 11: `control` has no core enemy-action-control evidence; `ROLE_EFFECT_MISMATCH`.
- 12: `defense` has no core threat-protection evidence; `ROLE_EFFECT_MISMATCH`.
- 13: the requested mechanic is not bound to a complete protocol causal edge; `MECHANIC_SKELETON_ABSENT`, not repairable.
- 14: the raw role profile contains a non-canonical value and fails closed at the role boundary; `CROSS_TAXONOMY_ROLE_LABEL`; normalization is forbidden.
- 15: the candidate relation fingerprint nearly copies a controlled reference; `REFERENCE_COPYING`.
- 16: the request's required mechanics and prohibitions conflict with one another; `HARD_CONSTRAINT_CONFLICT`.
- 17: a cross-ability resource consumer/gate has no reachable producer; `MULTI_SKILL_LOOP_INCOHERENT`.
- 18: explicit ally event, enemy effect, complete summon lease, and control evidence; `PASS`.
- 19: a complete causal protocol is bound but the required feedback is missing; `REQUESTED_MECHANIC_UNREPRESENTED`, locally repairable.

## 9. Migration and Compatibility Strategy

### Phase 0: CS-S1 design and independent prototype

- Add this document and a throwaway prototype/contract tests under `evals/`/`tests/`.
- Do not modify `src/` or connect the provider, validator, or repair loop.
- Use the 19 frozen oracle cases to validate interface expressiveness and the case 13/19 and 14 boundaries.

### Phase 1: S2 shadow sidecar

- Create a production SkillKit domain module and an independent response contract.
- The provider may generate a sidecar behind an explicit feature flag; the existing CharacterDraft contract remains unchanged.
- The shadow validator records results but does not change the existing character-generation verdict.
- `ability_concept` remains the existing production field.

### Phase 2: Versioned dual representation

- Release a new CharacterDraft response-contract version with required-but-nullable `skill_kit`.
- The legacy input seam may map a missing field to `None`, but must not guess a graph from prose.
- A structured draft uses SkillKit as the source of mechanic facts; `ability_concept` is derived by the renderer or checked for consistency.

### Phase 3: Localized repair

- Add an independent SkillKit repair seam; typed patches cover only paths authorized by the report.
- Retain existing Character repair's Canon evidence, frozen fields, one-attempt, regression-protection, and full-recheck policies.
- Non-repairable findings do not enter the patch provider.

### Phase 4: Consumer migration

- Consumers gradually read SkillKit; old consumers continue reading the derived `ability_concept`.
- Do not remove the compatibility field until all consumers and offline fixtures have migrated.

## 10. Luna Prototype Execution Plan

Prototype question: can `Protocol Surface / Derived Graph Core` express and adjudicate all 19 CS-S0.1 boundaries through one public seam while preserving the frozen semantics of cases 13/19 and CI-B1.5 taxonomy?

Pre-confirmed test seams:

1. `parse_candidate(payload)`: validate only shape, closed vocabulary, IDs, and unknown fields; allow nullable/empty semantic slots.
2. `evaluate(candidate, context)`: derive a graph from protocols/leases and emit stable outcomes/findings/paths.
3. `apply_patch(candidate, patch, report, context)`: allow only the authorized slot for a repairable finding, then perform a full recheck.
4. `render_ability_concept(candidate)`: emit a stable compatibility summary; do not reverse-parse legacy prose.

Luna owns only the new prototype/contract-test files; it does not edit `src/` or revert other people's changes. Suggested files:

- `evals/character_skill_interface_prototype_v0_1.py`
- `evals/fixtures/character_skill_interface_prototype_cases_v0.1.json`
- `tests/test_character_skill_interface_prototype_v0_1.py`

Implement in vertical red→green slices:

1. Cases 13/19: first prove that absent skeleton and locally missing feedback are distinguishable.
2. Case 14: prove that a raw cross-taxonomy role fails closed and no normalization occurs.
3. Cases 01/02/03: prove resource lifecycle and forbidden-resource behavior.
4. Cases 04/06/18: prove state/summon lifecycle and the control positive case.
5. Case 05: prove that teammate-trigger subject ambiguity is locatable.
6. Cases 07–12: prove the six canonical role-duty evidence mappings.
7. Cases 16/17: prove request conflict and cross-skill topology.
8. Case 15: validate the copying seam with an explicit prototype reference fingerprint input; do not read or modify the Reference Corpus.
9. Typed patch: demonstrate one repairable case becoming `PASS` after gap completion, and reject patches for cases 13/14.
10. Renderer: verify that a structured candidate deterministically emits a non-empty `ability_concept`.

Because the user explicitly requires contract tests, this prototype intentionally includes tests; this is a task-level override of the general throwaway-prototype rule that defaults to no tests. Tests observe behavior only through the public seams above and do not mock the internal graph compiler.

The run command must remain single and require no new dependency:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_character_skill_interface_prototype_v0_1.py -q
```

### Luna prototype results (2026-08-22)

The Luna Worker completed the first prototype round in the three isolated files above. Sol then rechecked the frozen oracle and tightened two contract points: cases 07–12 use an observable core effect that exists but has the wrong duty, rather than an empty skill group; and a repair patch must carry a `base_digest` matching the report, with no convenience patch lacking digest protection.

The current prototype contract tests pass 9/9 and independently read the expected outcome/finding code from the CS-S0.1 fixture for each case; all 19/19 match. The prototype fixture itself does not store oracle expectations, and the implementation does not branch on case IDs. The case 13 patch is rejected; the authorized feedback patch for case 19 becomes `PASS` after a full recheck; case 14 remains canonical-profile fail closed. The validator also retains independent lifecycle/role findings and checks both primary and secondary role evidence; `src/` is unchanged.

## 11. Independent Review and the CS-S1 Freeze Gate

After the Luna prototype passes, DeepSeek and MiMo v2.5 each read the same non-oracle projection and review only:

- whether all 19 boundaries are expressible;
- whether cases 13/19 remain strictly separated;
- whether case 14 retains CI-B1.5 fail-closed behavior;
- whether any fields are difficult for the provider to generate reliably or impossible for repair to locate locally;
- whether numerical balance or a second role taxonomy was introduced accidentally.

The two reviewers provide evidence only and do not modify the repository. Codex/Sol adjudicates reviewer disagreements using the frozen oracle, Luna contract tests, and the review evidence. CS-S1 may be frozen only if all of the following conditions hold:

- the recommended interface reproduces the 19/19 oracle outcomes and finding codes;
- case 13 cannot be falsely repaired by a local patch, while case 19 passes after one authorized slot is filled and rechecked;
- a non-canonical role never enters SkillKit or repair;
- missing structured facts in legacy `ability_concept` are never automatically promoted to `PASS`;
- provider, validator, repair, and renderer responsibilities do not overlap;
- `src/` remains unchanged by the prototype.

CS-S1 is not frozen yet. Only after this gate passes can the work enter CS-S2. Luna Worker will then implement the production schema, validator, compatibility adapter, and repair seam test-first; production integration requires a separate review.
