# Character Skill Design CS-S1.1: Frozen SkillKit Interface Contract (v0.1.1)

Status: **CS-S1 FROZEN**

## Status and authority

This document supersedes `character_skill_interface_options_v0.1.md` as the
CS-S1.1 design contract. The v0.1 file remains unchanged as the historical option
analysis. This revision freezes the provider-facing `Protocol Surface` and the
validator-owned `Derived Graph Core`; it is still an `evals/` prototype contract
and does not authorize changes under `src/`.

The contract inherits the CS-S0.1 v0.1.1 19-case oracle and CI-B1.5 canonical combat
role boundary. It incorporates the independent `deepseek-v4-flash` and Mimo v2.5 reviews.
They agreed on 18/19 cases and on the critical case 13, 14, 18, and 19
boundaries. For case 05, Sol retains the frozen adjudication
`REPAIR / TRIGGER_SUBJECT_AMBIGUOUS`: a causal direction exists, while the event
class and subject distinction remain locally clarifiable.

CS-S1.1 freezes interfaces and deterministic semantics only. It does not freeze
provider prompts, balance values, production persistence, or a production
repair implementation.

Post-review adjudication is incorporated in this revision. Sol accepts the
empty-feedback-target counterexample: a relation that points to a protocol with
`causes=[]` is declaration-only and cannot satisfy required feedback. Sol also
freezes the previously ambiguous repairability, lifecycle-topology, and corpus
fingerprint details below. These are contract clarifications, not permission to
integrate the prototype into `src/`.

## 1. Authority boundaries

Four inputs remain separate and cannot certify one another:

1. The request adapter produces `SkillIntent` and content-verifiable
   `MechanicRequirement` objects.
2. The provider produces a shape-valid `ProtocolSkillKitCandidate` only.
3. The validator compiles the candidate to a typed graph and alone emits
   findings, repairability, authorized paths, and outcome.
4. The patch provider may change only paths authorized by one digest-bound
   validation report.

`CombatRoleProfile` is supplied through validation context and remains the sole
role authority. SkillKit contains duty evidence, not a second role taxonomy.
The candidate contains no verdict, finding, request requirement, corpus match,
or repairability declaration.

The provider surface MUST NOT contain `implements`,
`request_requirement_ids`, `satisfies`, or an equivalent self-attestation
field. Such a declaration is neither evidence nor a hint to the matcher.

## 2. Closed provider surface

The selected public shape is the v0.1 behavior protocol plus lifecycle lease,
with the following CS-S1.1 changes:

- every cross-object reference uses the single typed-reference syntax in
  section 3;
- `Trigger.event` is a closed enum;
- feedback is an independent typed relation rather than an array of effect IDs;
- lifecycle slots accept only operation-compatible effect references;
- role evidence carries typed effect references and centrality only;
- request matching, lifecycle matching, role matching, and corpus fingerprinting
  are all derived by the validator.

Normative shape:

```python
RefKind = Literal["protocol", "effect", "resource", "state", "summon"]

@dataclass(frozen=True)
class TypedRef:
    kind: RefKind
    id: str

@dataclass(frozen=True)
class Subject:
    kind: Literal["self", "ally", "team", "enemy", "scene", "summon"]
    selector: str | None
    entity_ref: TypedRef | None

@dataclass(frozen=True)
class Trigger:
    subject: Subject | None
    event: TriggerEvent | None
    source_ref: TypedRef | None
    qualifier: str | None

@dataclass(frozen=True)
class Effect:
    effect_id: str
    subject: Subject | None
    operation: EffectOperation | None
    object_ref: TypedRef | None
    description: str

@dataclass(frozen=True)
class BehaviorProtocol:
    protocol_id: str
    when: Trigger | None
    causes: tuple[Effect, ...]

@dataclass(frozen=True)
class FeedbackRelation:
    feedback_id: str
    source_effect: TypedRef          # kind == "effect"
    target_protocol: TypedRef        # kind == "protocol"
    event: FeedbackEvent
    operation: Literal["enables", "modifies", "terminates"]

@dataclass(frozen=True)
class AbilityEntry:
    ability_id: str
    name: str
    mode: Literal["active", "passive", "reaction"]
    protocols: tuple[BehaviorProtocol, ...]
    display_text: str

@dataclass(frozen=True)
class ResourceLease:
    resource_id: str
    opened_by: tuple[TypedRef, ...]
    used_or_transformed_by: tuple[TypedRef, ...]
    closed_by: tuple[TypedRef, ...]

@dataclass(frozen=True)
class StateLease:
    state_id: str
    established_by: tuple[TypedRef, ...]
    active_effects: tuple[TypedRef, ...]
    ended_or_replaced_by: tuple[TypedRef, ...]

@dataclass(frozen=True)
class SummonLease:
    summon_id: str
    spawned_by: tuple[TypedRef, ...]
    active_effects: tuple[TypedRef, ...]
    departed_or_replaced_by: tuple[TypedRef, ...]
    repeat_policy: Literal["replace", "refresh", "reject"] | None

@dataclass(frozen=True)
class RoleEvidence:
    effect_refs: tuple[TypedRef, ...]
    centrality: Literal["core", "secondary"]

@dataclass(frozen=True)
class ProtocolSkillKitCandidate:
    schema_version: Literal["skill-kit-candidate/0.1.1"]
    entries: tuple[AbilityEntry, ...]
    feedback_relations: tuple[FeedbackRelation, ...]
    resources: tuple[ResourceLease, ...]
    states: tuple[StateLease, ...]
    summons: tuple[SummonLease, ...]
    role_evidence: tuple[RoleEvidence, ...]
    display_summary: str
```

Every property appears in the strict provider schema. Nullable or empty
semantic slots remain parseable so cases 05, 06, 13, and 19 reach semantic
evaluation. Unknown properties, unknown enum values, malformed IDs, duplicate
IDs in the same kind namespace, and wrong reference shapes fail at parsing.

## 3. One typed-reference syntax

Every internal reference is exactly this JSON object:

```json
{"kind": "effect", "id": "echo/resolve/apply_echo"}
```

No bare ID, path-like string, `event:` sentinel, or mixed reference form is
accepted. IDs use ASCII lower snake-case path segments:

- protocol: `<ability_id>/<protocol_id>`;
- effect: `<ability_id>/<protocol_id>/<effect_id>`;
- resource/state/summon: the kit-local entity ID.

The declared `kind` selects the namespace and MUST equal the resolved object's
kind. References are kit-local. Reference Corpus objects never enter the
candidate namespace and cannot be targeted by provider-authored `TypedRef`.
A live ID in another namespace emits `REFERENCE_KIND_MISMATCH`; an ID absent
from every permitted namespace emits `REFERENCE_DANGLING`. Lifecycle and
feedback slots retain their more specific codes from sections 6 and 7.

Subject continuity is explicit: a summon subject MUST use a live `entity_ref`
of kind `summon`; every non-summon subject MUST have `entity_ref=None`. An
effect that operates on a resource, state, or summon uses `object_ref` of that
exact kind.
Text in `selector`, `qualifier`, `description`, `display_text`, or
`display_summary` never resolves a reference.

## 4. Content-verifiable `MechanicRequirement`

`MechanicRequirement` is request-owned and describes observable predicates. It
is not an opaque label plus a provider assertion.

```python
@dataclass(frozen=True)
class TriggerPredicate:
    subject_kinds: frozenset[SubjectKind]
    events: frozenset[TriggerEvent]
    source_kinds: frozenset[RefKind]

@dataclass(frozen=True)
class EffectPredicate:
    subject_kinds: frozenset[SubjectKind]
    operations: frozenset[EffectOperation]
    object_kinds: frozenset[RefKind]

@dataclass(frozen=True)
class FeedbackPredicate:
    required: bool
    events: frozenset[FeedbackEvent]
    operations: frozenset[Literal["enables", "modifies", "terminates"]]

@dataclass(frozen=True)
class MechanicRequirement:
    requirement_id: str
    trigger: TriggerPredicate
    effect: EffectPredicate
    feedback: FeedbackPredicate
```

The request adapter MUST provide at least one allowed subject kind and event for
the trigger, and at least one allowed subject kind and operation for the effect.
Empty predicates are request-shape errors, not candidate findings. Prose labels
may be retained in request provenance but are not match inputs.

The validator derives a requirement match only when one protocol contains:

1. a non-null trigger subject with an allowed kind and non-null controlled
   event;
2. a non-null effect subject and operation satisfying the effect predicate;
3. any required typed object/source kinds with live references; and
4. causal containment: the matching effect is in that protocol's `causes`.

If no such trigger-to-effect edge exists, emit non-repairable
`MECHANIC_SKELETON_ABSENT`. Candidate names, descriptions, `qualifier`, display
prose, repeated theme words, and unrelated complete protocols do not count.

If the edge exists but required feedback is absent, emit repairable
`REQUESTED_MECHANIC_UNREPRESENTED`. Feedback is present only when section 7's
relation rules pass. This preserves the frozen case 13/case 19 distinction.

## 5. Controlled event and operation vocabularies

`Trigger.event` is exactly one of:

```text
ability_invoked
action_completed
damage_received
healing_received
resource_gained
resource_spent
state_entered
state_exited
summon_spawned
summon_acted
summon_departed
scene_entered
scene_exited
feedback_received
```

`FeedbackEvent` is exactly one of:

```text
effect_resolved
resource_changed
state_changed
summon_changed
```

Event prose has no fallback. For example, `event=null` plus qualifier
`"after an ally finishes an action"` remains an absent controlled event. An
unknown event string is a shape error.

`EffectOperation` is exactly one of:

```text
direct_output              follow_up_output
ally_enablement            recover_or_mitigate
enemy_action_control       threat_protection
resource_gain              resource_use
resource_transform         resource_clear
state_enter                state_apply
state_exit                 state_replace
summon_spawn               summon_act
summon_exit                summon_replace
emit_event
```

There is no `custom` operation or free-form parameters map. Creative expression
belongs in description fields and cannot satisfy hard constraints.

## 6. Lifecycle operation constraints

Every lifecycle slot contains only `TypedRef(kind="effect", ...)`. Each
referenced effect MUST exist, use one allowed operation for that slot, and have
an `object_ref` whose kind and ID equal the lease entity:

| Lease slot | Allowed effect operation |
| --- | --- |
| `resource.opened_by` | `resource_gain` |
| `resource.used_or_transformed_by` | `resource_use`, `resource_transform` |
| `resource.closed_by` | `resource_clear`, `resource_transform` |
| `state.established_by` | `state_enter` |
| `state.active_effects` | `state_apply` |
| `state.ended_or_replaced_by` | `state_exit`, `state_replace` |
| `summon.spawned_by` | `summon_spawn` |
| `summon.active_effects` | `summon_act` |
| `summon.departed_or_replaced_by` | `summon_exit`, `summon_replace` |

A dangling effect ref emits `LIFECYCLE_REFERENCE_DANGLING`. A live effect with
the wrong operation or object target emits `LIFECYCLE_OPERATION_MISMATCH`.
Neither counts toward closure. After invalid slot members are discarded, the
existing CS-S0.1 completeness findings are derived from the remaining valid graph:
`RESOURCE_LOOP_INCOMPLETE`, `STATE_EXIT_MISSING`,
`SUMMON_LIFECYCLE_INCOMPLETE`, and `MULTI_SKILL_LOOP_INCOHERENT`.

The closure predicates and resource finding split are exact:

- a resource is closed only when all three valid sets are non-empty;
- a state with valid establish and active sets but no valid end/replace set
  emits `STATE_EXIT_MISSING`;
- a summon is closed only when spawn, active, and depart/replace sets are all
  non-empty and its repeat rule is satisfied;
- an incomplete resource emits `MULTI_SKILL_LOOP_INCOHERENT` only when live
  effects whose `object_ref` targets that resource span at least two distinct
  ability IDs; otherwise it emits `RESOURCE_LOOP_INCOMPLETE`;
- the two resource codes are mutually exclusive for one lease defect and are
  not selected merely because the candidate contains an unrelated second
  ability.

`summon.repeat_policy` is required whenever a summon can be spawned more than
once or has no valid `summon_replace` edge. A prose exit such as `scene_exit`
must be represented by a protocol triggered by `scene_exited` whose effect uses
the appropriate clear/exit operation; it is never a string sentinel in a lease.

## 7. Independent typed feedback relation

Feedback is not an effect-ID list and is not established by a self-reference.
A valid `FeedbackRelation` MUST satisfy all of the following:

- both typed endpoints resolve and have the required kinds;
- `source_effect` is a matching cause in the requirement's matched skeleton;
- `target_protocol` is not the source effect's enclosing protocol;
- the target protocol has `when.event == feedback_received`;
- the target trigger's `source_ref` equals the relation's `source_effect`;
- the relation event and operation satisfy the request's feedback predicate;
- source effect and target trigger have the same non-null subject kind; when
  that kind is `summon`, their summon `entity_ref` values are identical; and
- `target_protocol.causes` contains at least one downstream effect with a
  non-null subject and an operation allowed by the relation-operation matrix.

The downstream operation matrix is exact:

| Feedback operation | Allowed downstream effect operations |
| --- | --- |
| `enables` | `direct_output`, `follow_up_output`, `ally_enablement`, `recover_or_mitigate`, `enemy_action_control`, `threat_protection`, `resource_gain`, `state_enter`, `summon_spawn` |
| `modifies` | `direct_output`, `follow_up_output`, `ally_enablement`, `recover_or_mitigate`, `enemy_action_control`, `threat_protection`, `resource_transform`, `state_apply`, `summon_act` |
| `terminates` | `resource_clear`, `state_exit`, `state_replace`, `summon_exit`, `summon_replace` |

A downstream lifecycle operation also MUST carry a live `object_ref` of the
matching resource/state/summon kind. `emit_event` is deliberately insufficient
as downstream evidence in CS-S1.1 because `Effect` has no typed event object.

A dangling endpoint emits `FEEDBACK_REFERENCE_DANGLING`. A same-protocol loop,
an unrelated source effect, a target that does not consume the exact source, or
a target with no compatible downstream cause, or a relation outside every
matched requirement subgraph emits
`FEEDBACK_RELATION_INVALID`. Invalid feedback never changes
`MECHANIC_SKELETON_ABSENT` to a repairable result and never satisfies
`REQUESTED_MECHANIC_UNREPRESENTED`.

When the context contains no `MechanicRequirement`, every candidate feedback
relation is outside a matched requirement subgraph and therefore invalid; it is
not inert. For a repairable feedback gap, the report authorizes
`/feedback_relations/-` and, only when a pre-existing exact consumer protocol
has no compatible cause, that protocol's exact `/causes/-` path. A patch must
add both the compatible cause and relation atomically when both are missing.

## 8. Canonical role evidence matrix

Role evidence proves an external canonical profile; it never declares a role.
Each evidence ref must resolve to an effect and the enclosing protocol's trigger
must satisfy the complete row below.

| Canonical role | Required duty | Effect operation | Effect subject | Allowed trigger subject/event | Required centrality |
| --- | --- | --- | --- | --- | --- |
| `main_dps` | direct output | `direct_output` | `enemy` | `self/ability_invoked` | `core` |
| `sub_dps` | follow-up output | `follow_up_output` | `enemy` | `ally/action_completed`, `team/action_completed` | `core` |
| `support` | ally enablement | `ally_enablement` | `ally`, `team` | `self/ability_invoked`, `ally/action_completed`, `team/action_completed` | `core` |
| `healer` | recovery or mitigation | `recover_or_mitigate` | `ally`, `team` | `self/ability_invoked`, `ally/damage_received`, `team/damage_received` | `core` |
| `control` | enemy action control | `enemy_action_control` | `enemy` | `self/ability_invoked`, `ally/action_completed`, `summon/summon_acted`, `scene/scene_entered` | `core` |
| `defense` | threat protection | `threat_protection` | `ally`, `team` | `self/ability_invoked`, `ally/damage_received`, `team/damage_received` | `core` |

For each secondary canonical role, the same duty/operation/subject/trigger row
is required with `centrality=secondary`. Core evidence does not automatically
satisfy a secondary role and vice versa. A correct operation applied to the
wrong subject, or placed under the wrong trigger, emits `ROLE_EFFECT_MISMATCH`.
The `description` cannot repair the mismatch.

Raw role values are parsed before SkillKit evaluation. Only `main_dps`,
`sub_dps`, `support`, `healer`, `control`, and `defense` are accepted. The
canonical profile MUST NOT call the legacy flat-alias normalizer. A noncanonical
value emits non-repairable `CROSS_TAXONOMY_ROLE_LABEL`, cannot enter repair, and
does not get rewritten into candidate evidence.

## 9. Reference Corpus structural fingerprint

Reference-copy detection uses validator-owned external evidence. The candidate
cannot submit copied IDs, match booleans, or corpus fingerprints.

`ReferenceReviewContext` contains:

```python
@dataclass(frozen=True)
class ReferenceReviewContext:
    corpus_version: str
    corpus_digest: str
    structural_fingerprints: tuple[ReferenceFingerprint, ...]

@dataclass(frozen=True)
class ReferenceFingerprint:
    record_id: str
    scope: Literal["protocol", "connected_component"]
    sha256: str
```

The fingerprint algorithm is frozen as the following cross-implementation
procedure. `canonical_json` means UTF-8 JSON with object keys sorted, arrays
preserved, no insignificant whitespace, and Unicode emitted without ASCII
escaping.

1. Compile node records. Protocol tags are
   `[trigger_subject_kind|null, trigger_event|null]`; effect tags are
   `[operation|null, effect_subject_kind|null, object_ref_kind|null,
   sorted(role_evidence centralities)]`; resource/state lease tags are empty;
   summon lease tags are `[repeat_policy|null]`.
2. Compile directed labelled edges: `causes`, `targets`, lifecycle slot names,
   and `feedback:<event>:<operation>`. Preserve parallel-edge multiplicity.
3. Remove ability/protocol/effect/entity IDs, names, descriptions, selectors,
   qualifier/display prose, and Reference Corpus record IDs.
4. Initialize each node color as
   `sha256(canonical_json({"kind": kind, "tags": tags}))`.
5. Perform exactly `max(1, node_count)` refinement rounds. Each new color is
   `sha256(canonical_json({"kind": kind, "tags": tags,
   "incoming": sorted([[edge_label, source_color], ...]),
   "outgoing": sorted([[edge_label, target_color], ...])}))`.
6. Serialize `nodes` as the sorted multiset of `[kind, final_color]` and
   `edges` as the sorted multiset of
   `[source_final_color, edge_label, target_final_color]`; hash the object
   `{"nodes": nodes, "edges": edges}` with lowercase SHA-256.
7. A `protocol` scope includes the protocol, its caused effects, directly
   targeted leases, and edges induced by those nodes. A `connected_component`
   scope is each maximal weakly connected component, not the whole candidate by
   default. Compare candidate fingerprints only with corpus fingerprints having
   the same scope.

This makes an isomorphic external relation copy retain the same fingerprint
even after IDs and prose are renamed. A candidate protocol or connected
component exactly matching a controlled corpus fingerprint emits non-repairable
`REFERENCE_COPYING`. Fuzzy semantic similarity is not frozen in CS-S1.1 and cannot
be inferred from prose. The complete `ReferenceReviewContext`, including
`corpus_digest`, is part of the validation-context digest in section 10.

## 10. Findings, outcomes, and deterministic accumulation

Shape errors are exceptions and do not produce semantic reports. Once parsing
succeeds, evaluation accumulates every independently provable finding; it MUST
NOT stop after taxonomy, requirement, lifecycle, role, or copying failure.

The only suppressions are causal duplicates:

- for the same requirement, `MECHANIC_SKELETON_ABSENT` suppresses
  `REQUESTED_MECHANIC_UNREPRESENTED` because feedback cannot be missing from a
  skeleton that does not exist;
- duplicate instances with identical `(code, field_path, evidence_refs)` are
  collapsed;
- an invalid lifecycle ref does not itself suppress the resulting independent
  lifecycle-incomplete finding.

Findings sort deterministically by the following priority, then `code`,
`field_path`, and canonicalized `evidence_refs`:

| Priority | Finding family |
| ---: | --- |
| 0 | request conflict, canonical taxonomy, reference copying |
| 1 | mechanic skeleton absence, forbidden mechanic |
| 2 | dangling/wrong-kind reference, lifecycle operation mismatch, invalid feedback |
| 3 | lifecycle/topology incompleteness, trigger ambiguity, requested feedback gap |
| 4 | role effect mismatch |
| 5 | compatibility-only diagnostics |

Repairability is also frozen rather than inferred from priority:

| Repairable | Finding codes |
| --- | --- |
| yes | `RESOURCE_LOOP_INCOMPLETE`, `STATE_EXIT_MISSING`, `SUMMON_LIFECYCLE_INCOMPLETE`, `MULTI_SKILL_LOOP_INCOHERENT`, `TRIGGER_SUBJECT_AMBIGUOUS`, `REQUESTED_MECHANIC_UNREPRESENTED` |
| no | `HARD_CONSTRAINT_CONFLICT`, `CROSS_TAXONOMY_ROLE_LABEL`, `REFERENCE_COPYING`, `MECHANIC_SKELETON_ABSENT`, `FORBIDDEN_RESOURCE_INTRODUCED`, `REFERENCE_KIND_MISMATCH`, `REFERENCE_DANGLING`, `LIFECYCLE_REFERENCE_DANGLING`, `LIFECYCLE_REFERENCE_WRONG_KIND`, `LIFECYCLE_OPERATION_MISMATCH`, `FEEDBACK_REFERENCE_DANGLING`, `FEEDBACK_RELATION_INVALID`, `ROLE_EFFECT_MISMATCH`, `LEGACY_SKILL_KIT_UNVERIFIED` |

The request-side forbidden-family mapping is exact for the frozen families.
`resource` is present when any `ResourceLease` exists or any effect operation
starts with `resource_`; `state` and `summon` follow the same lease-or-operation
rule. A forbidden family present in the candidate emits the corresponding
non-repairable `FORBIDDEN_<FAMILY>_INTRODUCED` finding.

Outcome is derived after accumulation:

1. any non-repairable finding -> `FAIL`;
2. otherwise any repairable finding -> `REPAIR`;
3. otherwise a legacy-only candidate -> `LEGACY_UNVERIFIED`;
4. otherwise -> `PASS`.

`REPAIR` is allowed only when every finding is repairable. Finding priority
controls presentation and repair planning; it never hides a lower-priority
independent defect or changes repairability.

## 11. Digest-bound, path-authorized `SkillKitPatch`

The validation report contains three digests:

```python
candidate_digest = sha256(canonical_json(candidate))
context_digest = sha256(canonical_json({
    "intent": intent,
    "combat_role_profile": combat_role_profile,
    "reference_review_context": reference_review_context,
    "validator_contract": "skill-kit-validator/0.1.1",
}))
report_digest = sha256(canonical_json({
    "candidate_digest": candidate_digest,
    "context_digest": context_digest,
    "findings": findings,
    "outcome": outcome,
}))
```

Each repairable finding carries exact RFC 6901 JSON Pointer paths in
`authorized_paths`. Paths are limited to semantic gap slots under:

```text
/entries/<entry-index>/protocols/<protocol-index>/when
/entries/<entry-index>/protocols/<protocol-index>/causes/-
/feedback_relations/-
/resources/<index>/{opened_by,used_or_transformed_by,closed_by}/-
/states/<index>/{established_by,active_effects,ended_or_replaced_by}/-
/summons/<index>/{spawned_by,active_effects,departed_or_replaced_by}/-
/summons/<index>/repeat_policy
```

No patch may change IDs, names, display prose, role evidence, schema version,
request/context data, existing relation values, or a path not listed by the
report. `SkillKitPatch` contains one or more typed `add`/`replace` operations,
plus exact `candidate_digest`, `context_digest`, and `report_digest` bindings.

Before mutation, `apply_patch` MUST recompute all three digests from the supplied
candidate, report, and context and compare every binding. This prevents a patch
or report from being replayed against a different context, corpus snapshot,
candidate, or same-candidate/different-report evaluation. A mismatch emits a
patch rejection, never a semantic candidate finding.

After one atomic patch attempt, the validator performs a full re-evaluation. A
patch is accepted only if all targeted findings disappear, no new finding is
introduced, and the outcome strictly improves. Otherwise retain the original
candidate and report.

## 12. Legacy `ability_concept` compatibility

`ability_concept` remains a display compatibility field. It is never parsed
back into protocols, references, requirements, lifecycle facts, feedback, or
role evidence.

At the explicit legacy deserialization seam only, a payload without `skill_kit`
maps to `skill_kit=None`. SkillKit evaluation then emits
`LEGACY_SKILL_KIT_UNVERIFIED` and outcome `LEGACY_UNVERIFIED`, never `PASS`.
This state is not locally repairable because constructing a graph from prose is
new design work. Existing consumers may continue displaying the original text,
but CS-S1.1 callers must preserve the non-PASS status.

For a structured candidate, `render_ability_concept(candidate)` is deterministic
and one-way. Once SkillKit exists, it is the mechanic fact source and rendered
prose cannot override validator findings.

## 13. Acceptance mapping and freeze assertions

The CS-S0.1 19-case outcomes and primary finding codes remain:

| Case | Frozen result |
| ---: | --- |
| 01 | `PASS` |
| 02 | `REPAIR / RESOURCE_LOOP_INCOMPLETE` |
| 03 | `FAIL / FORBIDDEN_RESOURCE_INTRODUCED` |
| 04 | `REPAIR / STATE_EXIT_MISSING` |
| 05 | `REPAIR / TRIGGER_SUBJECT_AMBIGUOUS` |
| 06 | `REPAIR / SUMMON_LIFECYCLE_INCOMPLETE` |
| 07-12 | `FAIL / ROLE_EFFECT_MISMATCH` |
| 13 | `FAIL / MECHANIC_SKELETON_ABSENT` |
| 14 | `FAIL / CROSS_TAXONOMY_ROLE_LABEL` |
| 15 | `FAIL / REFERENCE_COPYING` |
| 16 | `FAIL / HARD_CONSTRAINT_CONFLICT` |
| 17 | `REPAIR / MULTI_SKILL_LOOP_INCOHERENT` |
| 18 | `PASS` |
| 19 | `REPAIR / REQUESTED_MECHANIC_UNREPRESENTED` |

The CS-S1.1 prototype is acceptable only if tests prove all of the following
through `parse_candidate`, `evaluate`, `apply_patch`, and the one-way renderer:

- all 19 cases match the frozen CS-S0.1 outcome and primary code;
- `implements`-only, prose-event, unrelated relation, and self-reference inputs
  cannot satisfy a mechanic requirement or feedback predicate;
- a feedback relation targeting a protocol with no compatible downstream cause
  emits `FEEDBACK_RELATION_INVALID`, retains the independent requested-feedback
  gap, and cannot produce `PASS`;
- dangling and operation-incompatible lifecycle references are located and do
  not count toward closure;
- all six role rows verify duty, operation, subject, trigger, and centrality;
- patch replay fails across context or report digests;
- isomorphic copying of a controlled external relation is detected after IDs
  and prose are renamed;
- CI-B1.5 remains fail closed and legacy `ability_concept` remains non-PASS; and
- multiple independent findings accumulate in deterministic priority order.

The prototype remains under `evals/` with contract tests under `tests/`. The
independent DeepSeek/MiMo evidence and Sol adjudication are frozen in
`evals/results/character_skill_s1_blind_review_report_v0.1.1.md`. CS-S1 is
**FROZEN**, but this result does not authorize production integration under
`src/`; that work belongs to the separately reviewed CS-S2 milestone.
