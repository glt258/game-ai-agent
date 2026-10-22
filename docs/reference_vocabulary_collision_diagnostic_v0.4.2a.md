# Reference Selector v0.4.2a
# Vocabulary Collision Diagnostic

Status: **BENCHMARK_COVERAGE_INSUFFICIENT**

This is a diagnostic/design report only. Production vocabulary, records,
schema, selector scoring, benchmark cases, and generation behavior are
unchanged.

## Current Vocabulary

Vocabulary version: `reference-feature-vocabulary/0.4.1c`.

The implementation in `src/reference_corpus/features.py` uses a bounded
canonical-token map. Canonical tokens and their aliases are listed below.

### Personality

| Canonical token | Aliases |
|---|---|
| `restrained` | restrained; quiet; reserved; 克制; 安静 |
| `expressive` | expressive; flamboyant; showperson; 表现力强; 张扬 |
| `practical` | practical; pragmatic; 务实 |
| `idealistic` | idealistic; 理想主义 |
| `guarded` | guarded; 防备 |
| `warm` | warm; socially warm; 亲和 |
| `confrontational` | confrontational; 对抗性 |
| `conciliatory` | conciliatory; 调和 |
| `disciplined` | disciplined; 自律 |
| `impulsive` | impulsive; 冲动 |
| `playful` | playful; 顽皮 |
| `serious` | serious; 严肃 |
| `socially_embedded` | socially embedded; community embedded; 嵌入社区 |
| `socially_isolated` | socially isolated; socially detached; 社会孤立 |

### Gameplay fantasy

| Canonical token | Aliases |
|---|---|
| `direct_frontline_pressure` | direct frontline pressure; frontline; direct combat; on_field_dps; 前线压制 |
| `protective_stabilization` | protective stabilization; protective; protection; defensive; healing; healer; shielding; stabilization; 防护; 稳定 |
| `team_enabling` | team enabling; team enablement; team_fed; team buff; 团队赋能 |
| `battlefield_control` | battlefield control; spatial control; crowd control; area control; control; 战场控制 |
| `mobility_repositioning` | mobility repositioning; mobility; repositioning; 机动; 重新定位 |
| `information_investigation` | information investigation; information gathering; investigation; investigator; fact checker; information; 信息调查 |
| `routing_coordination` | routing coordination; crowd routing; route planner; coordination; routing; 路径协调 |
| `setup_payoff` | setup payoff; setup and payoff; build and spend; setup; payoff; 铺垫回收 |
| `reactive_support` | reactive support; reactive; support healer; 支援反应 |

### Life/social identity

| Canonical token | Aliases |
|---|---|
| `formal_professional` | formal professional; professional; magistrate; researcher; 正式职业 |
| `ordinary_urban_worker` | ordinary urban worker; ordinary worker; urban worker; repair shop; 普通都市劳动者 |
| `informal_worker` | informal worker; informal work; 非正式劳动者 |
| `independent_operator` | independent operator; independent; works alone; 独立行动者 |
| `performer` | performer; stage performer; public performer; stage identity; 演出者 |
| `investigator` | field investigator; investigator; criminal investigation; 调查者 |
| `organization_member` | organization member; faction member; team member; 机构成员 |
| `community_embedded_local` | community embedded local; community social role; community; neighbor; local; 社区邻里 |
| `itinerant_traveler` | itinerant traveler; traveler; courier; 旅居者 |
| `non_career_identity` | non career identity; non professional; ordinary neighbor; 非职业身份 |

### Life-stage

| Canonical token | Aliases |
|---|---|
| `youthful_presentation` | youthful presentation; youthful; 年轻呈现 |
| `mature_presentation` | mature presentation; mature; 成熟呈现 |
| `older_presentation` | older presentation; older; 年长呈现 |
| `age_ambiguous` | age ambiguous; age-ambiguous; age unspecified; age unknown; 年龄模糊 |
| `unspecified` | life stage unspecified; life-stage unspecified; 阶段未说明 |

### Authority

| Canonical token | Aliases |
|---|---|
| `low_formal_authority` | low formal authority; limited authority; low authority; 有限正式权力 |
| `ordinary_member` | ordinary member; 普通成员 |
| `independent` | independent authority; independent operator; 独立 |
| `operational_responsibility` | operational responsibility; field responsibility; operations responsibility; 运营职责 |
| `public_social_influence` | public social influence; social influence; influential without office; 社会影响力 |
| `formal_leadership` | formal leadership; formal leader; governing official; magistrate; 正式领导 |

### Hook surface

`public_performance`, `ordinary_work_identity`, `formal_role_identity`,
`organization_member_identity`.

Aliases are respectively: public performance/public performer/stage identity;
ordinary work identity/ordinary urban worker/repair shop; formal role
identity/governing official/magistrate; organization member identity/faction
member.

### Hook contrast

`formal_role_personal_action` (formal role personal action; official who fights
in person; governing official with personal combat presence),
`charisma_without_office` (charisma without office; influential without office;
无正式职位的影响力), and `competence_without_spectacle` (competence without
spectacle; low spectacle daily identity; 低调日常身份).

### Hook behavioral pattern

`public_performance` (public performance; stage performer; public-facing
creative), `low_spectacle_routine` (low spectacle routine; low-spectacle daily
identity), `restraint_for_payoff` (restraint for payoff; patience stance; 克制后回收),
and `routine_problem_solving` (routine problem solving; patient problem solving;
日常解决问题).

### Visual/behavioral motif

`signature_object` (signature object; 标志性物件), `repeated_gesture`
(repeated gesture; recurring gesture; 重复手势), `occupational_tool`
(occupational tool; work tool; 职业工具), `performance_behavior`
(performance behavior; stage behavior; 演出行为), and
`recurring_spatial_behavior` (recurring spatial behavior; spatial routine;
recurring route; 空间行为).

Normalization lowercases text, replaces underscores and hyphens with spaces,
removes non-word punctuation, and matches Latin/digit aliases on whitespace
boundaries. Chinese aliases use substring matching. Canonical tokens are
bounded, deduplicated, and emitted in input/discovery order. Unknown values
remain absent; they are never forced into a category.

## Same-10 Feature Profiles

The following matrix is produced from the current production records and
`reference_feature_profile`; `—` means an empty normalized domain.

| Character | Personality | Fantasy | Life identity | Life-stage | Authority | Hook surface | Hook contrast | Hook behavioral | Motif |
|---|---|---|---|---|---|---|---|---|---|
| Furina | expressive, guarded | setup_payoff, team_enabling | — | — | — | public_performance | — | public_performance | — |
| Keqing | restrained, disciplined | direct_frontline_pressure, mobility_repositioning | formal_professional | — | formal_leadership | formal_role_identity | formal_role_personal_action | routine_problem_solving | — |
| Nahida | restrained, socially_isolated, idealistic | battlefield_control, information_investigation | formal_professional | — | formal_leadership | formal_role_identity | charisma_without_office | routine_problem_solving | — |
| Fadia | playful, confrontational | direct_frontline_pressure, battlefield_control | organization_member | — | operational_responsibility | organization_member_identity | — | public_performance | — |
| Shinku | restrained, socially_isolated, disciplined | protective_stabilization, direct_frontline_pressure, setup_payoff | formal_professional | — | operational_responsibility | organization_member_identity | competence_without_spectacle | low_spectacle_routine, restraint_for_payoff | — |
| Jinhsi | restrained, idealistic, socially_embedded | direct_frontline_pressure, setup_payoff, team_enabling | formal_professional | — | formal_leadership | formal_role_identity | formal_role_personal_action | restraint_for_payoff | signature_object |
| Mortefi | serious, practical, confrontational | direct_frontline_pressure, battlefield_control | formal_professional | — | operational_responsibility | — | competence_without_spectacle | routine_problem_solving | — |
| Shorekeeper | restrained, socially_isolated, disciplined | protective_stabilization, team_enabling | formal_professional | — | formal_leadership | organization_member_identity | competence_without_spectacle | low_spectacle_routine | — |
| Jane Doe | guarded, practical, restrained | mobility_repositioning, information_investigation, direct_frontline_pressure, protective_stabilization | investigator | — | operational_responsibility | organization_member_identity | competence_without_spectacle | restraint_for_payoff | — |
| Nicole Demara | expressive, impulsive, practical | team_enabling, setup_payoff | independent_operator | — | formal_leadership | organization_member_identity | charisma_without_office | public_performance | — |

## Token Frequency

`Briefs` is the number of the 18 frozen briefs whose deterministic extraction
recognizes the token. `Shared cases` counts those recognized briefs where the
token is present in at least two production references. `Potential collision`
is a review flag, not a quality label: `HIGH_REVIEW` means reference and
brief-side overlap is material; `MEDIUM_REVIEW` means a smaller but visible
collision; `REFERENCE_ONLY_PRESSURE` means the references carry the token but
the current briefs cannot express it.

| Token | Domain | Count | Characters | Briefs | Shared cases | Potential collision |
|---|---|---:|---|---:|---:|---|
| restrained | personality | 6 | Jane Doe, Jinhsi, Keqing, Nahida, Shinku, Shorekeeper | 6 | 6 | HIGH_REVIEW |
| expressive | personality | 2 | Furina, Nicole Demara | 2 | 2 | MEDIUM_REVIEW |
| practical | personality | 3 | Jane Doe, Mortefi, Nicole Demara | 7 | 7 | HIGH_REVIEW |
| idealistic | personality | 2 | Jinhsi, Nahida | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| guarded | personality | 2 | Furina, Jane Doe | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| warm | personality | 0 | — | 1 | 0 | — |
| confrontational | personality | 2 | Fadia, Mortefi | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| conciliatory | personality | 0 | — | 0 | 0 | — |
| disciplined | personality | 3 | Keqing, Shinku, Shorekeeper | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| impulsive | personality | 1 | Nicole Demara | 0 | 0 | — |
| playful | personality | 1 | Fadia | 0 | 0 | — |
| serious | personality | 1 | Mortefi | 0 | 0 | — |
| socially_embedded | personality | 1 | Jinhsi | 0 | 0 | — |
| socially_isolated | personality | 3 | Nahida, Shinku, Shorekeeper | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| direct_frontline_pressure | fantasy | 6 | Fadia, Jane Doe, Jinhsi, Keqing, Mortefi, Shinku | 4 | 4 | HIGH_REVIEW |
| protective_stabilization | fantasy | 3 | Jane Doe, Shinku, Shorekeeper | 2 | 2 | MEDIUM_REVIEW |
| team_enabling | fantasy | 4 | Furina, Jinhsi, Nicole Demara, Shorekeeper | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| battlefield_control | fantasy | 3 | Fadia, Mortefi, Nahida | 1 | 1 | MEDIUM_REVIEW |
| mobility_repositioning | fantasy | 2 | Jane Doe, Keqing | 1 | 1 | MEDIUM_REVIEW |
| information_investigation | fantasy | 2 | Jane Doe, Nahida | 1 | 1 | MEDIUM_REVIEW |
| routing_coordination | fantasy | 0 | — | 2 | 0 | — |
| setup_payoff | fantasy | 4 | Furina, Jinhsi, Nicole Demara, Shinku | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| reactive_support | fantasy | 0 | — | 1 | 0 | — |
| formal_professional | identity | 6 | Jinhsi, Keqing, Mortefi, Nahida, Shinku, Shorekeeper | 6 | 6 | HIGH_REVIEW |
| ordinary_urban_worker | identity | 0 | — | 1 | 0 | — |
| informal_worker | identity | 0 | — | 0 | 0 | — |
| independent_operator | identity | 1 | Nicole Demara | 1 | 0 | — |
| performer | identity | 0 | — | 2 | 0 | — |
| investigator | identity | 1 | Jane Doe | 1 | 0 | — |
| organization_member | identity | 1 | Fadia | 0 | 0 | — |
| community_embedded_local | identity | 0 | — | 2 | 0 | — |
| itinerant_traveler | identity | 0 | — | 1 | 0 | — |
| non_career_identity | identity | 0 | — | 1 | 0 | — |
| youthful_presentation | life-stage | 0 | — | 1 | 0 | — |
| mature_presentation | life-stage | 0 | — | 1 | 0 | — |
| older_presentation | life-stage | 0 | — | 0 | 0 | — |
| age_ambiguous | life-stage | 0 | — | 1 | 0 | — |
| unspecified | life-stage | 0 | — | 0 | 0 | — |
| low_formal_authority | authority | 0 | — | 1 | 0 | — |
| ordinary_member | authority | 0 | — | 0 | 0 | — |
| independent | authority | 0 | — | 0 | 0 | — |
| operational_responsibility | authority | 4 | Fadia, Jane Doe, Mortefi, Shinku | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| public_social_influence | authority | 0 | — | 1 | 0 | — |
| formal_leadership | authority | 5 | Jinhsi, Keqing, Nahida, Nicole Demara, Shorekeeper | 2 | 2 | HIGH_REVIEW |
| public_performance | hook surface | 1 | Furina | 1 | 0 | — |
| ordinary_work_identity | hook surface | 0 | — | 1 | 0 | — |
| formal_role_identity | hook surface | 3 | Jinhsi, Keqing, Nahida | 2 | 2 | MEDIUM_REVIEW |
| organization_member_identity | hook surface | 5 | Fadia, Jane Doe, Nicole Demara, Shinku, Shorekeeper | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| formal_role_personal_action | hook contrast | 2 | Jinhsi, Keqing | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| charisma_without_office | hook contrast | 2 | Nahida, Nicole Demara | 1 | 1 | MEDIUM_REVIEW |
| competence_without_spectacle | hook contrast | 4 | Jane Doe, Mortefi, Shinku, Shorekeeper | 3 | 3 | HIGH_REVIEW |
| public_performance | hook behavioral | 3 | Fadia, Furina, Nicole Demara | 2 | 2 | MEDIUM_REVIEW |
| low_spectacle_routine | hook behavioral | 2 | Shinku, Shorekeeper | 3 | 3 | MEDIUM_REVIEW |
| restraint_for_payoff | hook behavioral | 3 | Jane Doe, Jinhsi, Shinku | 0 | 0 | REFERENCE_ONLY_PRESSURE |
| routine_problem_solving | hook behavioral | 3 | Keqing, Mortefi, Nahida | 1 | 1 | MEDIUM_REVIEW |
| signature_object | motif | 1 | Jinhsi | 0 | 0 | — |
| repeated_gesture | motif | 0 | — | 0 | 0 | — |
| occupational_tool | motif | 0 | — | 0 | 0 | — |
| performance_behavior | motif | 0 | — | 0 | 0 | — |
| recurring_spatial_behavior | motif | 0 | — | 0 | 0 | — |

Frequency alone is not a revision criterion. The material cases are the
tokens with both reference-side multiplicity and current brief-side signal:
`restrained`, `practical`, `direct_frontline_pressure`,
`formal_professional`, `formal_leadership`, and
`competence_without_spectacle`. Several high-frequency reference tokens have
no brief-side signal and therefore are `REFERENCE_ONLY_PRESSURE`, not current
selector-representation failures.

## Pairwise Collision Matrix

The matrix below reports exact shared canonical values. `Hook` is expanded as
`surface / contrast / behavioral`. Classification is a deterministic diagnostic
heuristic: `LOW` = 0–1 shared signal domains, `MEDIUM` = 2–3, and `HIGH` = 4+
or identical full profiles. Hook components count as one aggregate signal for
classification, while remaining separate in the report. This is not a
production score.

| Pair | Shared personality | Shared fantasy | Shared identity | Shared authority | Shared hook | Shared motif | Class | Separation / collision note |
|---|---|---|---|---|---|---|---|---|
| Fadia / Furina | — | — | — | — | behavioral: public_performance | — | LOW | One behavioral overlap; identity, personality, fantasy, and surface separate them. |
| Fadia / Jane Doe | — | direct_frontline_pressure | — | operational_responsibility | surface: organization_member_identity | — | MEDIUM | Partial combat/role overlap; Jane's investigator identity and restraint-for-payoff behavior separate them. |
| Fadia / Jinhsi | — | direct_frontline_pressure | — | — | — | — | LOW | Shared frontline fantasy only; authority, identity, and hook semantics separate them. |
| Fadia / Keqing | — | direct_frontline_pressure | — | — | — | — | LOW | Shared frontline fantasy only; formal-role and personality features differ. |
| Fadia / Mortefi | confrontational | battlefield_control, direct_frontline_pressure | — | operational_responsibility | — | — | MEDIUM | Combat/operational overlap; serious/practical versus playful and distinct hooks separate them. |
| Fadia / Nahida | — | battlefield_control | — | — | — | — | LOW | Shared control fantasy only; formal authority and identity differ. |
| Fadia / Nicole Demara | — | — | — | — | surface: organization_member_identity; behavioral: public_performance | — | LOW | Shared organization/performance signals, but personality, fantasy, authority, and contrast differ. |
| Fadia / Shinku | — | direct_frontline_pressure | — | operational_responsibility | surface: organization_member_identity | — | MEDIUM | Shared operative combat/organization frame; personality, contrast, and behavior separate them. |
| Fadia / Shorekeeper | — | — | — | — | surface: organization_member_identity | — | LOW | Shared organization surface only; formal custodial authority and fantasy differ. |
| Furina / Jane Doe | guarded | — | — | — | — | — | LOW | Guarded is the only shared token; public performance versus operative restraint separates them. |
| Furina / Jinhsi | — | setup_payoff, team_enabling | — | — | — | — | LOW | Shared two fantasy tokens; formal authority, identity, and hook separate them. |
| Furina / Keqing | — | — | — | — | — | — | LOW | No shared current feature token. |
| Furina / Mortefi | — | — | — | — | — | — | LOW | No shared current feature token. |
| Furina / Nahida | — | — | — | — | — | — | LOW | No shared current feature token despite both having richer unnormalized narrative context. |
| Furina / Nicole Demara | expressive | setup_payoff, team_enabling | — | — | behavioral: public_performance | — | MEDIUM | The expressive/team/performance cluster overlaps; identity and contrast differ. |
| Furina / Shinku | — | setup_payoff | — | — | — | — | LOW | Shared setup-payoff only; role and personality differ. |
| Furina / Shorekeeper | — | team_enabling | — | — | — | — | LOW | Shared team-enabling only; custodial versus performative identity differs. |
| Jane Doe / Jinhsi | restrained | direct_frontline_pressure | — | — | behavioral: restraint_for_payoff | — | MEDIUM | Shared restrained frontline pattern; identity, authority, surface, and motif separate them. |
| Jane Doe / Keqing | restrained | direct_frontline_pressure, mobility_repositioning | — | — | — | — | MEDIUM | Shared restrained combat profile; investigator versus governing-official hooks separate them. |
| Jane Doe / Mortefi | practical | direct_frontline_pressure | — | operational_responsibility | contrast: competence_without_spectacle | — | HIGH | Multiple shared signals; investigator identity and behavior are the principal separators. |
| Jane Doe / Nahida | restrained | information_investigation | — | — | — | — | MEDIUM | Shared restraint/information profile; formal authority and contrast differ. |
| Jane Doe / Nicole Demara | practical | — | — | — | surface: organization_member_identity | — | MEDIUM | Practical organization surface overlaps; expressive independent-operator identity separates Nicole. |
| Jane Doe / Shinku | restrained | direct_frontline_pressure, protective_stabilization | — | operational_responsibility | surface: organization_member_identity; contrast: competence_without_spectacle; behavioral: restraint_for_payoff | — | HIGH | Broad shared operative profile; Shinku's formal-professional/organization framing and low-spectacle behavior still distinguish it. |
| Jane Doe / Shorekeeper | restrained | protective_stabilization | — | — | surface: organization_member_identity; contrast: competence_without_spectacle | — | MEDIUM | Shared restrained protective competence; authority, behavior, and identity scope differ. |
| Jinhsi / Keqing | restrained | direct_frontline_pressure | formal_professional | formal_leadership | surface: formal_role_identity; contrast: formal_role_personal_action | — | HIGH | Actual canonical hook collision; Jinhsi's idealistic/socially embedded setup-payoff and motif versus Keqing's disciplined mobility/routine profile separate them. |
| Jinhsi / Mortefi | — | direct_frontline_pressure | formal_professional | — | — | — | MEDIUM | Broad professional/frontline overlap; authority, personality, and hook behavior separate them. |
| Jinhsi / Nahida | restrained, idealistic | — | formal_professional | formal_leadership | surface: formal_role_identity | — | HIGH | Formal-role/authority collision; social isolation, charisma contrast, combat fantasy, and behavior separate them. |
| Jinhsi / Nicole Demara | — | setup_payoff, team_enabling | — | formal_leadership | — | — | MEDIUM | Authority and team-fantasy overlap; independent-operator/public-performance semantics differ. |
| Jinhsi / Shinku | restrained | direct_frontline_pressure, setup_payoff | formal_professional | — | behavioral: restraint_for_payoff | — | HIGH | Professional restrained combat overlap; authority, organization surface, and competence contrast separate them. |
| Jinhsi / Shorekeeper | restrained | team_enabling | formal_professional | formal_leadership | — | — | HIGH | Broad formal/custodial authority overlap; fantasy, surface, behavior, and motif separate them. |
| Keqing / Mortefi | — | direct_frontline_pressure | formal_professional | — | behavioral: routine_problem_solving | — | MEDIUM | Shared professional frontline routine; personality and contrast differ. |
| Keqing / Nahida | restrained | — | formal_professional | formal_leadership | surface: formal_role_identity; behavioral: routine_problem_solving | — | HIGH | Formal-role authority cluster overlaps; contrast, personality qualifiers, and fantasy separate them. |
| Keqing / Nicole Demara | — | — | — | formal_leadership | — | — | LOW | Shared leadership token only; scale, identity, personality, and hook differ. |
| Keqing / Shinku | restrained, disciplined | direct_frontline_pressure | formal_professional | — | — | — | MEDIUM | Shared restrained professional combat; organization/competence hook separates them. |
| Keqing / Shorekeeper | restrained, disciplined | — | formal_professional | formal_leadership | — | — | MEDIUM | Shared authority/professional personality; organization/custodial hook and fantasy differ. |
| Mortefi / Nahida | — | battlefield_control | formal_professional | — | behavioral: routine_problem_solving | — | MEDIUM | Shared professional problem-solving frame; personality, authority, and contrast differ. |
| Mortefi / Nicole Demara | practical | — | — | — | — | — | LOW | Practical is the only shared token. |
| Mortefi / Shinku | — | direct_frontline_pressure | formal_professional | operational_responsibility | contrast: competence_without_spectacle | — | HIGH | The competence/professional/operational cluster is broad; personality, surface, and behavior separate them. |
| Mortefi / Shorekeeper | — | — | formal_professional | — | contrast: competence_without_spectacle | — | MEDIUM | Shared professional competence contrast; authority, surface, and fantasy differ. |
| Nahida / Nicole Demara | — | — | — | formal_leadership | contrast: charisma_without_office | — | MEDIUM | Formal leadership/charisma contrast is semantically broad; scale and identity hooks separate them. |
| Nahida / Shinku | restrained, socially_isolated | — | formal_professional | — | — | — | MEDIUM | Shared reserved professional identity; authority and hook contrast differ. |
| Nahida / Shorekeeper | restrained, socially_isolated | — | formal_professional | formal_leadership | — | — | MEDIUM | Shared reserved formal authority; surface, contrast, behavior, and fantasy differ. |
| Nicole Demara / Shinku | — | setup_payoff | — | — | surface: organization_member_identity | — | MEDIUM | Shared setup/organization surface; personality, authority, and contrast differ. |
| Nicole Demara / Shorekeeper | — | team_enabling | — | formal_leadership | surface: organization_member_identity | — | MEDIUM | Shared team/leadership organization frame; personality, identity scope, and contrast differ. |
| Shinku / Shorekeeper | restrained, socially_isolated, disciplined | protective_stabilization | formal_professional | — | surface: organization_member_identity; contrast: competence_without_spectacle; behavioral: low_spectacle_routine | — | HIGH | Strongest current broad collision; Shinku's operational authority/direct pressure/setup and restraint-for-payoff behavior separate it from Shorekeeper. |

There are 15 low, 21 medium, and 9 high diagnostic pair classifications.
High does not mean indistinguishable: the all-feature ablation is fully unique.

## Domain Ablation

`Collapsed references` counts references belonging to a repeated equivalence
class; unique singleton profiles are not counted as collapsed.

| Signal kept | Unique profiles | Collapsed references | Largest repeated group |
|---|---:|---:|---|
| Personality only | 9 | 2 | Shinku / Shorekeeper |
| Fantasy only | 9 | 2 | Fadia / Mortefi |
| Life identity only | 5 | 6 | Jinhsi / Keqing / Mortefi / Nahida / Shinku / Shorekeeper |
| Authority only | 3 | 9 | Jinhsi / Keqing / Nahida / Nicole Demara / Shorekeeper; Fadia / Jane Doe / Mortefi / Shinku |
| Hook only (surface + contrast + behavioral) | 10 | 0 | — |
| Personality + hook | 10 | 0 | — |
| Identity + authority | 6 | 6 | Jinhsi / Keqing / Nahida / Shorekeeper; Mortefi / Shinku |
| Personality + identity + authority | 10 | 0 | — |
| Personality + hook + fantasy | 10 | 0 | — |
| All current authoring features | 10 | 0 | — |

The result is the central diagnostic: broad single domains can collide, but
the current adjacent dimensions already make all ten full profiles unique.
There is no production-score or ranking change in this analysis.

## Authority Analysis

`formal_leadership` is carried by five references: Jinhsi, Keqing, Nahida,
Nicole Demara, and Shorekeeper. It combines materially different scopes:

- Jinhsi: Magistrate/head-of-state institutional scope.
- Keqing: council seat and portfolio governance.
- Nahida: sovereign authority with a temporal effective-authority caveat.
- Nicole: small private-agency leadership.
- Shorekeeper: custodial/acting executive organizational authority.

Authority-only representation collapses these five into one group, and
identity+authority still collapses Jinhsi, Keqing, Nahida, and Shorekeeper.
Hook surface separates Nicole from the formal-role group, while personality,
fantasy, contrast, and behavioral features separate the full profiles. Thus:

A. Yes, one token collapses materially different authority scopes.

B. Existing adjacent dimensions reliably separate the full same-10 records,
but not an authority-only or identity+authority comparison.

C. A future score using only `formal_leadership` could produce false-positive
similarity between a small informal team leader, a city/state governing
leader, and a former or ceremonial authority.

Design options:

| Option | Collision reduction | Complexity/backwards compatibility | Brief difficulty | Assessment |
|---|---|---|---|---|
| A. Split `formal_leadership` into several tokens | Direct, but risks overfitting five examples | Highest vocabulary churn; breaks broad-token continuity | High; briefs must name scope precisely | Reject for now |
| B. Add orthogonal `authority_scope` later | Preserves broad filter while representing scope | Moderate schema/vocabulary work; backwards-compatible if optional | Moderate to high | Best future direction, but benchmark gap blocks implementation |
| C. Keep current vocabulary | Zero churn; full profiles remain unique | Lowest | Lowest | Accept as current production state, not as a final authority design |

The recommended strategy is B as a future design direction, with C for this
diagnostic freeze. No authority token should be added now because the current
18 briefs contain `formal_leadership` language but do not deterministically
express the proposed scope distinctions.

## Personality Analysis

`restrained` is the most frequent personality token: 6/10 references and six
brief recognitions. The references do not all mean the same thing: Keqing's
discipline, Nahida/Shinku/Shorekeeper's isolation or reserve, Jinhsi's
leadership composure, and Jane Doe's low-key operative pattern are distinct
interpretations. Those differences are already carried by adjacent identity,
authority, hook, fantasy, and secondary personality tokens.

The personality-only ablation has only one repeated pair (Shinku/Shorekeeper),
while personality+hook is fully unique. The current quiet-to-flamboyant
counterfactual changes no selected candidates, and there is no evidence that
splitting `restrained` would improve the frozen selector representation.

Recommendation: choose personality option C, no vocabulary change. Avoid
personality ontology expansion; add orthogonal behavioral or motivation
features only if a future brief/reference benchmark demonstrates a failure
that hook and identity cannot solve.

## Hook Analysis

### `competence_without_spectacle`

The token is used by Jane Doe, Mortefi, Shinku, and Shorekeeper, and three
current briefs recognize it or its low-spectacle aliases. The semantic fit is:

- Jane Doe: strong; low-key professional competence and field work.
- Shinku: strong; social distance and dependable protection without spectacle.
- Shorekeeper: strong; dependable custodial capability rather than spectacle-first identity.
- Mortefi: a stretch; expert/prickly inventor competence is supported, but
  low-spectacle presentation is less explicit than for the other three.

This is a real broad-hook collision and a possible generic hidden-depth bucket,
but the current full profiles remain unique and the brief side already has a
usable low-spectacle signal. No replacement token is justified yet; changing
semantics would be riskier than retaining a transparent broad diagnostic.

### Empty and colliding contrasts

- Furina has an honest empty contrast. `spectacle_as_mask` would be a plausible
  future shadow concept from her expressive public performance plus guarded
  identity, but no current brief contains a deterministic masking/vulnerability
  signal. This is `REFERENCE_ONLY_PRESSURE`.
- Fadia has an honest empty contrast. A predatory/performance contrast could
  describe her source-grounded playful enforcement, but no current brief
  expresses that distinction. This is also `REFERENCE_ONLY_PRESSURE`.
- Keqing and Jinhsi share `formal_role_personal_action`. Their broader
  profiles differ, but the hook token itself cannot express council/portfolio
  governance versus magistrate/head-of-state scope. Current briefs do not test
  that distinction.
- `charisma_without_office` is shared by Nahida and Nicole. It is a useful
  contrast for Nicole; for Nahida it is explicitly a temporal/effective-power
  approximation, not literal absence of office. This is a semantic caveat,
  not enough evidence to rename the token.

Hook design options:

- A. Add 1–3 tokens: not yet; candidate directions lack current brief-side
  signal and risk one-character or two-character semantics.
- B. Change existing semantics: reject for now; it would erase useful
  low-spectacle and temporal-authority distinctions.
- C. Use surface + behavioral combinations more strongly: preferred current
  practice; hook-only and personality+hook profiles are already unique.
- D. No revision: correct for the current frozen benchmark, pending targeted
  brief coverage.

## Identity Analysis

`formal_professional` is carried by six references and recognized by six
briefs. It is a useful broad filter, not an empty default: it separates the
professional cluster from Nicole's independent operator, Jane Doe's
investigator, and Fadia's organization-member identity. However, it compresses
researcher, governing official, council executive, and custodial authority.

`organization_member` is carried by Fadia only in life identity, while
`organization_member_identity` is carried by five references as a hook surface.
The hook token has zero current brief recognitions, so its reference frequency
is `REFERENCE_ONLY_PRESSURE`, not evidence for immediate revision.

Identity+authority produces six profiles and personality+identity+authority
produces ten. These are useful broad filters with adjacent-domain support, not
a reason to create a job-title taxonomy. Keep both current tokens unchanged.

## Brief-Side Coverage

Current deterministic brief recognition counts relevant to the reviewed
pressure are:

| Existing signal | Brief recognitions | Interpretation |
|---|---:|---|
| `restrained` | 6/18 | Real personality-side signal, but no failure after hook/identity combination |
| `practical` | 7/18 | Broad signal; current contrasts add role/fantasy separation |
| `formal_professional` | 6/18 | Useful broad identity signal, but not scope-specific |
| `formal_leadership` | 2/18 | Authority signal exists, scope signal does not |
| `competence_without_spectacle` | 3/18 | Real low-spectacle signal, with Mortefi semantic stretch |
| `charisma_without_office` | 1/18 | Narrow but deterministic signal |
| `organization_member_identity` | 0/18 | Reference-only pressure |
| proposed authority scope distinctions | 0/18 | Reference-only pressure |
| proposed Furina masking contrast | 0/18 | Reference-only pressure |
| proposed Fadia predatory-performance contrast | 0/18 | Reference-only pressure |

A revision requires both reference-side and brief-side signal. The current
benchmark therefore supports auditing existing collisions but not prioritizing
new scope or contrast tokens for scoring.

## Benchmark Coverage Gaps

The frozen 18 cases and their diagnostic counterfactuals test combat role,
occupation, broad personality, and life-stage wording, but not authority
scope or the proposed hook contrasts.

Observed counterfactual structure:

- support → control: role/ability fantasy; 9 candidates change.
- quiet → flamboyant: personality; 0 candidates change.
- repair → performer: occupation; 0 candidates change.
- mature → youthful: life-stage; 0 candidates change.

The three contrast pairs similarly cover combat role, broad personality/hook,
and occupation; none isolates authority scope. This is a
`BENCHMARK_COVERAGE_GAP`, not a reason to edit the frozen benchmark. Future
diagnostic-only cases should test small-team leadership versus state/council
governance versus ceremonial/custodial authority, plus masking and predatory
performance, before any scoring revision.

## Minimal Revision Candidates

### Candidate 1: orthogonal authority scope

- Domain: authority
- Current problem: `formal_leadership` collapses five materially different scopes; authority-only collapses 9/10 references.
- Proposed distinction: a future optional orthogonal scope representation,
  not a split of the broad leadership token.
- Characters affected: Jinhsi, Keqing, Nahida, Nicole Demara, Shorekeeper;
  adjacent operational cases would need explicit scope handling too.
- Briefs affected: none of the current 18 express the required scope contrast.
- Collision reduced: likely meaningful for future authority-only briefs, but no
  benchmark outcome may be claimed now.
- New token required: **NO for this task**; future design may require a small
  scope vocabulary.
- Risk: schema/vocabulary expansion and difficult deterministic extraction;
  `BENCHMARK_COVERAGE_GAP`.

### Candidate 2: competence/low-spectacle refinement

- Domain: hook contrast
- Current problem: `competence_without_spectacle` covers four references and
  Mortefi is a semantic stretch.
- Proposed distinction: retain the broad token and test an orthogonal behavior
  or motivation distinction later.
- Characters affected: Jane Doe, Mortefi, Shinku, Shorekeeper.
- Briefs affected: three current low-spectacle/quiet-practical cases.
- Collision reduced: not demonstrated; hook-only and personality+hook are
  already fully unique.
- New token required: **NO**.
- Risk: hidden-depth ontology expansion and token renaming without a proven
  selector failure.

### Candidate 3: missing Furina/Fadia contrasts

- Domain: hook contrast
- Current problem: both records have honest empty contrast fields, while
  source-grounded interpretations suggest masking or predatory performance.
- Proposed distinction: future shadow concepts only; do not adopt names yet.
- Characters affected: Furina and Fadia, potentially more if a broad semantic
  family is found.
- Briefs affected: zero current briefs.
- Collision reduced: not testable in the frozen benchmark.
- New token required: **NO**.
- Risk: one-character tokens and `REFERENCE_ONLY_PRESSURE`.

## Revision Budget

- New tokens proposed now: **0**
- Tokens deprecated: **0**
- Tokens renamed: **0**
- Schema change required: **NO**

The best future strategy is: keep current broad authority, identity,
personality, and hook tokens; design an optional authority-scope axis only
after benchmark cases can express it; retain hook combinations before adding
new contrast tokens; and keep `restrained` unchanged.

## Production Benchmark

The diagnostic uses no production scoring and does not modify selection.
Expected production invariants remain:

- Unique selected: **8**
- Average overlap: **0.448485**
- HHI: **0.159808**
- Classification: `LIMITED_SENSITIVITY`
- Ranking parity: **PASS**
- Changed cases: **NONE**
- Order: `ORDER_INDEPENDENT`
- Authoring feature score contribution: **0**

## Recommendation

**BENCHMARK_DESIGN_REQUIRED_FIRST**

Do not implement vocabulary changes in v0.4.2a. The diagnostic finds a real
authority-scope representation pressure, but the current benchmark cannot
express the distinction. The current adjacent feature representation already
produces ten unique full profiles, so broad-token preservation is preferable
until targeted brief-side cases exist.
