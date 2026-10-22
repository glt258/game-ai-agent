# Reference Feature Vocabulary & Provenance Contract v0.4.1c

Status: `PARTIAL` / ready for review

Recommendation: `NEEDS_SCHEMA_REVISION`

This task adds a bounded, deterministic diagnostic feature layer. It does not
change the frozen selector score, ranking, benchmark cases, corpus records, or
generation behavior. Diagnostic overlap is reported for review only and has a
production score contribution of zero.

## 1. Decision

The smallest useful vocabulary is now defined in
`src/reference_corpus/features.py`. It is intentionally an authoring
vocabulary, not a psychological taxonomy, combat-stat ontology, labor
classification, or art metadata system.

The implementation provides:

- canonical tokens and bounded aliases;
- deterministic extraction from an author brief;
- deterministic normalization from existing facts and `analysis.yaml`;
- structured hook diagnostics (`surface`, `contrast`, `behavioral_pattern`);
- in-memory provenance evidence with explicit `brief`, `source_fact`, and
  `analyst_derivation` labels;
- benchmark diagnostics and coverage metrics;
- no feature contribution to `rank_reference_summaries()`.

The result is not yet ready for metadata backfill because persistent
`analysis.yaml` fields for life-stage, authority, structured hooks, and
analysis derivation evidence have not been added. Unknown values are already
valid in the diagnostic layer; the remaining gap is safe storage and
cross-file validation for the next task.

## 2. Vocabulary

Canonical tokens are snake_case. Aliases are short, explicit, and deterministic.
No alias is inferred from combat power, rarity, popularity, appearance, or
generic prose.

### Personality

| Canonical token | Bounded aliases |
|---|---|
| `restrained` | quiet, reserved, 克制, 安静 |
| `expressive` | expressive, flamboyant, showperson, 表现力强, 张扬 |
| `practical` | practical, pragmatic, 务实 |
| `idealistic` | idealistic, 理想主义 |
| `guarded` | guarded, 防备 |
| `warm` | warm, socially warm, 亲和 |
| `confrontational` | confrontational, 对抗性 |
| `conciliatory` | conciliatory, 调和 |
| `disciplined` | disciplined, 自律 |
| `impulsive` | impulsive, 冲动 |
| `playful` | playful, 顽皮 |
| `serious` | serious, 严肃 |
| `socially_embedded` | socially embedded, community embedded, 嵌入社区 |
| `socially_isolated` | socially isolated, socially detached, 社会孤立 |

`aggressive` is not normalized as personality because the current corpus uses
it primarily as a combat descriptor. `charismatic` is not normalized as
`warm`; it belongs in explicit social-influence language when authority or
social identity is being described.

### Gameplay fantasy

| Canonical token | Bounded aliases |
|---|---|
| `direct_frontline_pressure` | frontline, direct combat, `on_field_dps`, 前线压制 |
| `protective_stabilization` | protective, protection, defensive, healing, healer, shielding, stabilization, 防护, 稳定 |
| `team_enabling` | team enabling, team enablement, `team_fed`, team buff, 团队赋能 |
| `battlefield_control` | battlefield/spatial/crowd/area control, control, 战场控制 |
| `mobility_repositioning` | mobility, repositioning, 机动, 重新定位 |
| `information_investigation` | information gathering, investigation, investigator, fact checker, 信息调查 |
| `routing_coordination` | routing, route planner, crowd routing, coordination, 路径协调 |
| `setup_payoff` | setup, payoff, build and spend, 铺垫回收 |
| `reactive_support` | reactive support, reactive, support healer, 支援反应 |

Combat facts such as damage, cooldown, energy, crit, and weapon class are not
authoring fantasy features. They remain in the existing facts/analysis model.

### Life/social identity

| Canonical token | Bounded aliases |
|---|---|
| `formal_professional` | professional, researcher, magistrate, 正式职业 |
| `ordinary_urban_worker` | ordinary urban worker, ordinary worker, urban worker, repair shop, 普通都市劳动者 |
| `informal_worker` | informal worker, informal work, 非正式劳动者 |
| `independent_operator` | independent operator, independent, works alone, 独立行动者 |
| `performer` | performer, stage performer, public performer, stage identity, 演出者 |
| `investigator` | field investigator, investigator, criminal investigation, 调查者 |
| `organization_member` | organization member, faction member, team member, 机构成员 |
| `community_embedded_local` | community social role, community, neighbor, local, 社区邻里 |
| `itinerant_traveler` | itinerant traveler, traveler, courier, 旅居者 |
| `non_career_identity` | non-career identity, non-professional, ordinary neighbor, 非职业身份 |

This is an authoring identity vocabulary, not a real-world labor taxonomy.

### Life-stage

| Canonical token | Bounded aliases |
|---|---|
| `youthful_presentation` | youthful presentation, youthful, 年轻呈现 |
| `mature_presentation` | mature presentation, mature, 成熟呈现 |
| `older_presentation` | older presentation, older, 年长呈现 |
| `age_ambiguous` | age ambiguous, age-ambiguous, age unspecified, age unknown, 年龄模糊 |
| `unspecified` | life-stage unspecified, 阶段未说明 |

No numeric age, minor/adult inference, appearance-to-legal-age inference,
school inference, or occupation-to-life-stage inference is performed. An empty
profile means unknown; it is not automatically `unspecified`.

### Authority

| Canonical token | Bounded aliases |
|---|---|
| `low_formal_authority` | low formal authority, limited authority, low authority, 有限正式权力 |
| `ordinary_member` | ordinary member, 普通成员 |
| `independent` | independent authority, independent operator, 独立 |
| `operational_responsibility` | operational responsibility, field responsibility, operations responsibility, 运营职责 |
| `public_social_influence` | social influence, influential without office, 社会影响力 |
| `formal_leadership` | formal leadership, formal leader, governing official, magistrate, 正式领导 |

Authority is not competence. `member`, `strong`, `rare`, `popular`, and combat
role terms do not become authority features. `magistrate` and `governing
official` are accepted only because they explicitly name a formal office.

### Structured hook

Hook is not one keyword. The diagnostic profile has three independent slots:

```text
hook.surface_traits
hook.contrast_traits
hook.behavioral_patterns
```

The current bounded hook tokens are:

- surface: `public_performance`, `ordinary_work_identity`,
  `formal_role_identity`, `organization_member_identity`;
- contrast: `formal_role_personal_action`, `charisma_without_office`,
  `competence_without_spectacle`;
- behavioral pattern: `public_performance`, `low_spectacle_routine`,
  `restraint_for_payoff`, `routine_problem_solving`.

The representation can preserve a future surface/contrast/motif distinction
without flattening an entire hook into one adjective. Existing free-form
analysis prose remains untouched.

### Visual/behavioral motif

This remains lower priority. The diagnostic tokens are:

- `signature_object`;
- `repeated_gesture`;
- `occupational_tool`;
- `performance_behavior`;
- `recurring_spatial_behavior`.

Terms such as `light`, `motion`, `bright`, and `armored` are not automatically
converted into these motifs. A concrete object, gesture, tool, performance
behavior, or recurring spatial behavior must be explicit.

## 3. Brief-side extraction

Extraction is deterministic phrase/keyword matching against the bounded alias
table. It uses no LLM, embedding, external NLP service, randomness, or network
call. Multiple canonical features per domain are allowed; duplicates are
removed while preserving deterministic vocabulary order.

| Domain | Extraction status | Expected failure mode |
|---|---|---|
| Personality | YES | Free prose, irony, or ambiguous adjectives remain unknown |
| Gameplay fantasy | YES | Exact combat-stat language is intentionally ignored |
| Life/social identity | YES | Generic `occupation` without an explicit identity pattern is ignored |
| Life-stage | PARTIAL | Only explicit presentation phrases match; no age inference |
| Authority | PARTIAL | Only explicit authority/office phrases match; competence is ignored |
| Hook | PARTIAL | Only explicit structured-like phrases match; arbitrary prose is not flattened |
| Visual/behavioral motif | PARTIAL | Generic visual adjectives do not create motifs |

Unsupported ambiguous aliases remain unsupported. This is intentional: a lower
coverage diagnostic is preferable to an apparently precise but invented
feature.

## 4. Reference-side normalization

`reference_feature_profile(reference)` creates a separate in-memory profile:

- personality comes only from `analysis.character_design.personality_archetypes`;
- gameplay fantasy uses analysis character fantasy, normalized roles, bounded
  archetypes, and gameplay hooks;
- life/social identity uses explicit narrative facts and bounded analysis
  hooks;
- authority uses explicit office/authority language from narrative facts only;
- life-stage remains empty until a dedicated presentation field exists;
- hooks use identity, narrative, and product hooks without deleting original
  prose;
- motifs use explicit analysis motifs and official presentation labels only.

No `CharacterReference`, `CharacterAnalysis`, or YAML object is mutated. The
normalized profile is derived metadata, not a replacement for analysis prose.

## 5. Provenance contract

Each normalized feature may carry a `FeatureEvidence` record:

```text
FeatureEvidence(
    domain,
    canonical_token,
    provenance_kind,
    source_path,
    source_ids,
    raw_value,
    support_status,
)
```

`provenance_kind` has three explicit values:

- `brief`: extracted from the author brief; it is user intent, not evidence;
- `source_fact`: normalized from a fact path such as
  `facts.narrative.occupation`; source IDs are taken from existing
  `field_evidence` when available;
- `analyst_derivation`: normalized from `analysis.yaml`; current analysis
  documents do not have field-level derivation evidence, so the result is
  marked `analysis_only` rather than treated as a direct fact.

`validate_feature_provenance()` rejects unknown source IDs and validates
`facts.*` paths against `CharacterFacts` when a reference is supplied. Empty
source IDs are legal only when evidence is genuinely unavailable; they do not
claim support. A future persistent contract should add optional analysis
derivation evidence keyed by normalized feature path, for example:

```yaml
analysis_derivation_evidence:
  character_design.authoring_features.personality: [official-source-id]
```

The IDs must resolve against the existing `sources.yaml` source set. This is a
small mapping, not a graph system. It should say which source facts motivated
an analyst descriptor; it must not pretend the source literally used the
canonical token.

Hook contrast receives the same treatment. A future entry such as
`formal_role_personal_action` should identify the fact paths or source IDs
that motivated the contrast. It need not claim scientific proof, but an
unsupported free invention must remain visibly `analysis_only`.

## 6. Schema policy

No production reference record was edited in v0.4.1c. The existing optional
`analysis.yaml` remains backward compatible and all ten current records still
validate unchanged.

The next schema revision should add optional fields under existing
`analysis.character_design`, rather than introduce `selector_metadata.yaml`:

```yaml
authoring_features:
  personality: []
  gameplay_fantasy: []
  life_social_identity: []
  life_stage: []
  authority: []
  hook:
    surface_traits: []
    contrast_traits: []
    behavioral_patterns: []
  visual_behavioral_motifs: []
```

The next `sources.yaml` revision should add optional
`analysis_derivation_evidence`. Both additions must remain optional, reject
unknown canonical tokens once the enum contract is persisted, validate source
IDs, preserve existing analysis prose, and accept current records without
edits. Because these persisted structures are not yet present, the current
recommendation is `NEEDS_SCHEMA_REVISION` before same-10 backfill.

## 7. Diagnostic-only benchmark plumbing

The benchmark now reports per-case `diagnostic_features` and a top-level
`diagnostic_coverage` section. It computes brief features, reference features,
and per-domain overlap, but does not pass those values to
`rank_reference_summaries()` and does not modify its total score.

Every case records:

```text
diagnostic_features.score_contribution = 0
```

Coverage is reported independently for personality, gameplay fantasy,
life/social identity, life-stage, authority, the three hook slots, and visual
motifs. It is not collapsed into a quality score.

## 8. Stage 0.5 invariant proof

The exact v0.4 benchmark cases and ten production records were used. The
diagnostic layer produced the following unchanged production metrics:

| Metric | v0.4 frozen | v0.4.1c diagnostic run |
|---|---:|---:|
| Unique selected | 8 | 8 |
| Average top-k overlap | 0.448485 | 0.448485 |
| HHI | 0.159808 | 0.159808 |
| Classification | `LIMITED_SENSITIVITY` | `LIMITED_SENSITIVITY` |
| Ranking parity | — | PASS |
| Order independence | `ORDER_INDEPENDENT` | `ORDER_INDEPENDENT` |
| Feature score contribution | not applicable | 0 |

Current diagnostic coverage over 18 benchmark briefs and 10 references:

| Domain | Briefs recognized | References represented | Cases with shared feature |
|---|---:|---:|---:|
| Personality | 10 / 18 (55.56%) | 0 / 10 (0%) | 0 / 18 (0%) |
| Gameplay fantasy | 9 / 18 (50%) | 4 / 10 (40%) | 7 / 18 (38.89%) |
| Life/social identity | 12 / 18 (66.67%) | 3 / 10 (30%) | 7 / 18 (38.89%) |
| Life-stage | 2 / 18 (11.11%) | 0 / 10 (0%) | 0 / 18 (0%) |
| Authority | 3 / 18 (16.67%) | 1 / 10 (10%) | 2 / 18 (11.11%) |
| Hook surface | 4 / 18 (22.22%) | 4 / 10 (40%) | 2 / 18 (11.11%) |
| Hook contrast | 4 / 18 (22.22%) | 2 / 10 (20%) | 0 / 18 (0%) |
| Hook behavior | 5 / 18 (27.78%) | 1 / 10 (10%) | 0 / 18 (0%) |
| Visual/behavioral motif | 0 / 18 (0%) | 0 / 10 (0%) | 0 / 18 (0%) |

The low or zero reference coverage is an honest signal that the next task must
backfill metadata and extend the persisted schema. It is not a reason to make
the diagnostic layer score by default.

## 9. Current-10 backfill template

The next task may populate this template for each existing character. This
task intentionally populated none of the ten production records.

```text
Reference ID:

Personality:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:

Gameplay fantasy:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:

Life/social identity:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:

Life-stage:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:

Authority:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:

Hook:
Surface:
Contrast:
Behavioral pattern:
Derived from fact paths:
Derived from source IDs:

Visual/behavioral motifs:
Canonical features:
Analysis explanation:
Derived from fact paths:
Derived from source IDs:
```

## 10. Tests and production impact

Focused tests cover vocabulary bounds, unknown values, deterministic aliases,
age-unknown behavior, reference normalization, provenance validation,
analysis-prose preservation, diagnostic overlap, unchanged benchmark metrics,
and deterministic benchmark output.

Production impact:

- Selector ranking changed: **NO**
- Corpus records changed: **NO**
- Characters added: **NO**
- Generation changed: **NO**
- Canon changed: **NO**
- Repair changed: **NO**
- Live LLM/network dependency: **NO**

Next: revise the persisted analysis/provenance schema, then perform the
controlled same-10 metadata backfill. Only after that should feature scoring be
considered in a separate experiment.
