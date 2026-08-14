# Case and Incident Registry v0.1

## 1. Purpose

This document records the evidence review, schema boundary, and Knowledge Scope
impact for the Case and Incident registries. The registries provide stable IDs
for validation and exact runtime matching; they do not create permissions,
StoryState assignments, Lore, or characters.

## 2. Case definition

A Case is a uniquely identifiable business, investigation, coordination,
review, or handling work unit that exists in current Canon. A growing case
category, a collection of examples, a character hook, or a possible future
commission is not a Case instance. `case_type`, if used later, is descriptive
metadata and cannot participate in permission matching.

## 3. Incident definition

An Incident is a uniquely identifiable event, accident, or on-site occurrence
that actually happened in current Canon. A policy for handling incidents, a
trend in accident counts, an aggregate set of review examples, or a possible
future event is not an Incident instance.

## 4. Case versus Incident

A Case may be opened because of an Incident, but they remain independent
entities with different IDs and runtime scopes. `active_cases` cannot satisfy
an Incident binding, and `active_incidents` cannot satisfy a Case binding.
Optional relationship fields are stored on both records and validators require
bidirectional consistency, preventing two drifting sources of truth.

## 5. Evidence criteria

A record requires evidence that the entity exists or occurred, is distinguishable
from other entities, has an organizational or business context, and can be
referenced by a stable StoryState ID. Established Story Canon may now provide
instance-level evidence through validated `story_refs`. Generic `lore_refs`
provide institutional context and must not be presented as if they already
described the concrete instance. Character `story_entry_points` remain hooks and
are never sufficient evidence by themselves.

## 6. Candidate inventory

| rule_id | lore_id | condition | evaluator | faction | referenced fact | specific instance exists? | uniquely identifiable? | supporting Lore evidence | supporting faction evidence | decision |
|---|---|---|---|---|---|---|---|---|---|---|
| knowledge_rule_005 | lore_005 | assigned_to_related_case | case_assignment_match | faction_001 | The association is aggregating cross-industry examples to assess long-term rating bias. | No; only a batch is established. | No. | Lore 005 says “一批跨行业案例” and provides no parties, date, commission, or case boundary. | Faction 001 confirms the batch and that division_002 coordinates cases, but names no instance. | KEEP_UNRESOLVED |
| knowledge_rule_022 | lore_022 | assigned_to_related_case | case_assignment_match | faction_004 | Legal staff may work on matters related to tracking a few artists after long-term persona fixation. | No concrete legal matter is established. | No. | Lore 022 describes ongoing tracking of “少数艺人,” without identifying an artist, dispute, contract, or legal case. | Faction 004 repeats the aggregate program and generic legal access requirement, but names no case. | KEEP_UNRESOLVED |
| knowledge_rule_027 | lore_027 | assigned_to_incident_review | incident_assignment_match | faction_005 | The review/training group handles internal examples where incorrect risk labels affected field decisions. | Multiple examples are asserted, not one incident. | No. | Lore 027 says “一批…内部复盘案例” and gives no event-specific facts. | Faction 005 confirms division_015 aggregates cross-department accident cases, but identifies none. | KEEP_UNRESOLVED |
| knowledge_rule_027 | lore_027 | assigned_to_related_incident | incident_assignment_match | faction_005 | A professional lead may be assigned to the incident related to the restricted review finding. | Multiple examples are asserted, not one incident. | No. | The same aggregate Lore cannot identify which event the runtime assignment would mean. | The access requirement says “涉案专业负责人” generically and does not establish a named incident. | KEEP_UNRESOLVED |
| knowledge_rule_032 | lore_032 | assigned_to_related_case | case_assignment_match | faction_001 / faction_006 | Cooperative members are collecting rating-dispute examples for an appeal-standard initiative. | No; only members' disputes as a collection are established. | No. | Lore 032 provides no member, counterparty, date, or case boundary. | Faction 006 confirms the collection and prospective cooperation with faction_001, not a specific referred Case. | KEEP_UNRESOLVED |

Character hooks such as a shop leak commission, performance-site accident,
campus event, insurance refusal, or large-event misjudgment were reviewed only
as explicit rejection evidence: none is a current StoryState fact or a formal
Case/Incident instance.

## 7. Created Cases

`data/cases/cases.yaml` now contains
`case_nanzhan_postshow_coordination_001`, the concrete coordination work unit
created by Story Canon `story_after_the_show_001`. It covers post-incident fact
checking, procedure, costs, and remediation; it is not an ability-rating research
sample or an artist-tracking legal matter.

## 8. Created Incidents

`data/incidents/incidents.yaml` now contains
`incident_nanzhan_postshow_route_conflict_001`, the concrete post-show route
conflict established by the same Story Canon. The optional Case/Incident links
are bidirectional. The event is not Canonically identified as one of Lore 027's
restricted risk-label review examples.

## 9. Rejected and deferred candidates

- Lore 005: DEFER — a research collection of cases is not one Case.
- Lore 022: DEFER — an artist cohort and monitoring activity is not a legal Case.
- Lore 027: DEFER — aggregate review findings cannot be collapsed into one Incident.
- Lore 032: DEFER — a collection of member disputes is not one jointly handled Case.
- All launch-character `story_entry_points`: REJECT as registry evidence; hooks
  do not assert that the event currently exists or occurred.
- 《散场之后》is accepted because a reviewed Story Canon record now asserts
  concrete parties, event boundaries, consequences, and stable registry IDs;
  it was not promoted from a character hook alone.

## 10. Knowledge Scope impact

All three Case bindings and both Incident bindings remain unresolved. A registry
instance existing somewhere is not evidence that it is the specific object of a
Lore condition. The new Story Case is unrelated to Lore 005, 022, and 032; the
new Incident is unrelated to Lore 027. Total coverage remains 9 of 32
resolved-valid bindings (28.125%, reported as 28.12% by the reporting script).
No Knowledge Rule, subject, responsibility, project, or authorization was
changed.

## 11. Runtime Context integration

The loader reads both registries once when a resolver is constructed. Resolved
Case and Incident scopes use exact set intersection against `active_cases` and
`active_incidents`. Unknown runtime IDs raise
`KnowledgeContextValidationError`; a known but nonmatching ID is an ordinary
`condition_not_satisfied` denial. A caller cannot supply evaluator booleans or
an access decision. Future StoryState adapters may provide active Case and
Incident IDs, but the resolver remains the access-decision trust boundary.

## 12. Known gaps

Current Canon now has one unrelated Case and Incident, but still lacks the
specific instances required by rules 005, 022, 027, and 032. Rule 022 may
eventually require a Contract, Artist Team, or legal-matter model in addition
to any Case. Rule 027 may need a separate Review assignment/authorization
registry. Rule 032 also lacks a concrete Project and rotating-role assignment.
These gaps must not be filled by theme matching or by wrapping Lore IDs as
Case/Incident IDs.
