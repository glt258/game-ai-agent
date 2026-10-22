# Knowledge Responsibility Vocabulary v0.2 / v0.2.1 semantic cleanup

## 1. Purpose

This document records the institutional design review for the original nine Responsibility candidates and the v0.2.1 semantic cleanup. It defines only reusable Knowledge-facing duties; it does not create characters, projects, cases, incidents, datasets, artist teams, contracts, or permissions.

## 2. Responsibility definition

A Knowledge Responsibility is an institutional duty that an organization can explicitly assign, revoke, rotate, and audit. It describes accountable work, not merely exposure to a topic. A responsibility is always bound to exactly one `faction_id` in this vocabulary.

It must not be inferred from occupation, faction membership, tags, `agent_profile`, or a character's narrative description. It also does not imply every Lore record, dataset, model parameter, or restricted authorization owned by that faction.

## 3. Difference from Role

`role` is a formal position or identity used directly by a Knowledge Rule. `responsibility` is the institutional duty carried by a person or team. A `model_governance_lead` Role is not interchangeable with `model_governance_duty`, and the latter cannot lower or bypass a Role restriction.

## 4. Difference from Assignment

`assignment` is a concrete project or task. A Responsibility is a durable or institutional duty that can be reused across multiple projects and Lore Rules. `hengxin_explainability_pilot` remains an Assignment and is not converted into a Responsibility.

## 5. Design criteria

Every candidate was tested against six questions:

1. Who can be assigned and held accountable for it?
2. Which faction owns and audits it?
3. What institutional work does it cover?
4. How is it different from ordinary faction membership?
5. Can it be assigned, revoked, or rotated without changing the Canon occupation?
6. Can multiple Lore Rules reuse it stably?

IDs use an institutional duty noun/action shape. Names ending in `_context`, `_knowledge`, `_access`, `_permission`, or `_lore` are not registered.

## 6. Candidate review after v0.2.1 semantic cleanup

The v0.2.1 review separates Lore relevance from evidence that an accountable institutional duty actually exists.

| rule | lore | faction | actual scope need | candidate institutional duty | faction evidence | decision |
|---|---|---|---|---|---|---|
| 003 | 003 | 001 | case coordination or standards/training governance | `mediation_case_coordination` plus `professional_standards_governance` | the case coordination division and professional standards committee explicitly own these functions | KEEP_RESOLVED |
| 008 | 008 | 002 | professional relevance to an internal longitudinal-assessment judgment | none | the research divisions establish research directions, but no method-review office, committee, or assignable interpretation duty | DEFER |
| 009 | 009 | 002 | research ethics and data-use governance | `research_ethics_data_governance` | the research ethics and data office explicitly owns ethics review, data permission, and external compliance | KEEP_RESOLVED |
| 014 | 014 | 003 | risk-model design/maintenance or model governance | `risk_model_development_maintenance` plus `model_governance_duty` | the ability-risk actuarial division designs and maintains risk models; the model-governance and compliance division reviews use, bias, authorization, and regulatory risk | REGISTER + USE_EXISTING |
| 015 | 015 | 003 | job/case relevance and ordinary-employee data-access policy | none | no single Responsibility can represent the required job, case, assignment, and policy boundaries | KEEP_UNRESOLVED |
| 020 | 020 | 004 | artist public-label and reputation-risk work | `artist_risk_management` | the public-relations and artist-support division owns public-label risk and crisis communication | KEEP_RESOLVED |
| 021 | 021 | 004 | project, contract, artist-team, and assignment context | none | these are contextual boundaries, not artist-risk-management duties | KEEP_UNRESOLVED |
| 030 | 030 | 006 | member context | none | the cooperative is intentionally loose and has no matching accountable duty | KEEP_UNRESOLVED |
| 031 | 031 | 006 | member context | none | no division or accountable office owns the debate | KEEP_UNRESOLVED |

## 7. Registered responsibilities reviewed in v0.2.1

| id | faction | evidence and boundary |
|---|---|---|
| `professional_standards_governance` | faction_001 | The professional standards committee owns professional rules, continuing education, and safety guidance; this is not administrative force or all case-data access. |
| `research_ethics_data_governance` | faction_002 | The research ethics and data office owns ethics, data permission, and external compliance; this is not automatic dataset access. |
| `risk_model_development_maintenance` | faction_003 | The ability-risk actuarial division explicitly designs and maintains ability-liability, occupational, and event risk models. This duty is not `model_governance_lead`, `chief_actuary`, or `manager`, and grants neither model-data access nor model-governance authority. |
| `model_governance_duty` | faction_003 | The model-governance and compliance division reviews model use, bias, applicability, authorization, and regulatory risk; this is not model development or all model-data access. |
| `artist_risk_management` | faction_004 | The public-relations and artist-support division handles public-label risk and crisis communication; this is not artist identity, legal role, or project/contract scope. |

Rule 003 accepts `mediation_case_coordination` and `professional_standards_governance` with `match: any`. Rule 014 accepts `risk_model_development_maintenance` and `model_governance_duty` with `match: any`. In both cases, the Responsibility condition remains ANDed with the Rule subject match.

## 8. Decision history and deferred candidates

The semantic cleanup retains the v0.2 decisions and records why three of them were reversed rather than deleting their history.

| item | v0.2 decision | v0.2.1 decision | reason |
|---|---|---|---|
| `research_methodology_duty` / rule 008 | REGISTER / resolved | DEFER / unresolved | Insufficient institutional evidence. Lore 008 proves that a research conclusion exists, not that a separately assignable methodology-review duty exists. |
| risk-model design/maintenance duty / rule 014 | not separately modeled | REGISTER `risk_model_development_maintenance`; keep resolved | faction_003 division_007 explicitly designs and maintains the relevant risk models. The Rule now covers either development/maintenance or governance duty. |
| rule 015 | resolved by `model_governance_duty` | KEEP_UNRESOLVED | The policy concerns ordinary employees' job- and case-related data boundary. Future modeling likely needs institutional role mapping, case/assignment context, and data-access policy scope. |
| rule 021 | resolved by `artist_risk_management` | KEEP_UNRESOLVED | The policy depends on project, contract, artist-team, and assignment context, not an artist-risk-management duty. |

The following historical or draft IDs remain rejected: `insurance_claims_context`, `model_review_context`, `artist_project_context`, `community_member_coordination`, and `research_project_leadership`. They are context labels, access labels, assignments, or unsupported broad concepts rather than Canon-backed institutional duties. `research_methodology_duty` now joins the deferred set until stronger faction evidence exists.

No Case, Incident, Dataset, Artist Team, Contract, or Role Assignment Registry is introduced by this cleanup.

## 9. Scope impact

Before the v0.2.1 cleanup, the v0.2 working tree had 12 valid resolved bindings and 20 unresolved bindings out of 32.

Rule 008, rule 015, and rule 021 return to unresolved. Rule 014 stays resolved and gains a second valid Responsibility. The resulting inventory is 9 valid resolved bindings and 23 unresolved bindings out of 32, with no missing or invalid binding. No Rule subject was broadened.

## 10. Known gaps

Rule 008 remains an `insufficient_responsibility_vocabulary` gap because current faction Canon lacks an assignable institutional duty for the professional context. Rules 015 and 021 are `insufficient_context_model` gaps: resolving them requires combinations of institutional role, case/assignment, project/contract/artist-team, and data-policy context rather than new generic Responsibilities.

All unresolved bindings remain fail-closed. Occupation, tags, `agent_profile`, and faction membership cannot substitute for `identity.responsibilities`. Canon, project, and authorization data are unchanged.
