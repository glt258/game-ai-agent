# 角色技能设计 S0：失败案例与规格冻结

## 状态与目的

S0 是角色技能设计的规格资产阶段。它冻结可观察的领域语言、失败边界与验收案例，供后续模型协作和 S1 接口设计使用；它不声称当前角色生成已经拥有结构化的生产技能组。

当前生产角色输出仍以自由文本 `ability_concept` 表达能力概念。S0 不把它替换成新的生产字段，也不决定未来 `Skill Kit` 的生产 schema、provider、validator 或 repair 接口。

## Scope

S0 只覆盖以下内容：

- 用 `Skill Kit Concept`、`Ability Entry`、`Trigger Subject`、`Effect Subject`、`Resource Loop`、`State Lifecycle`、`Summon Lifecycle`、`Team Interaction` 和 `Mechanic Relation` 描述技能设计的可观察因果关系。
- 冻结 `PASS`、`REPAIR`、`FAIL` 三种规格判定及 finding code 的含义。
- 以 18 个脱离生产技能字段形状的 observation/oracle 案例验证资源、状态、召唤、队友交互、角色职责、机制表达和请求一致性。
- 给 DeepSeek 生成候选、给 Ox Alpha 做匿名盲审提供相同的领域边界和可比较的验收口径。

## Non-goals

S0 不做以下工作：

- 不修改当前生产能力表达；`ability_concept` 仍是现状。
- 不冻结或实现未来生产 `SkillKit` schema，不新增 production validator，不接入 provider，也不改变 repair loop。
- 不修改 Character Canon、Reference Corpus、角色来源词汇或 Canon Checker。
- 不做伤害、倍率、帧数、精确冷却、资源上限等数值平衡。
- 不设计装备、武器、WeaponModule、Artifact Set 或其他可装备系统。
- 不把 Reference Corpus 的 taxonomy 当作本项目的角色技能 taxonomy；Reference Corpus 只能提供抽象先例，不能被逐字或近乎逐字复制。
- 不把 `main_dps`、`sub_dps`、`support`、`healer`、`control`、`defense` 以外的词写入 `combat_role_profile`。`on_field_dps`、`crowd_control` 等跨 taxonomy 标签在该位置拒绝。

## 领域不变量

1. 任何可接受的技能组概念都能指出能力的触发主体、作用主体和二者之间的机制关系；风格化修辞不能单独替代因果关系。
2. 资源循环必须能说明资源进入、被持有、被消耗或转化以及清理/离场的关系；只有名称没有循环关系是不完整的。
3. 状态必须有建立、生效和退出/替换关系；召唤物还必须有出现、作用、离场/替换或约束关系。
4. 队友交互必须明确哪一类队友或队友事件是触发主体，不能把“队友”当作含混的效果位置。
5. 角色职责是请求中的硬约束。能力效果若与职责核心相冲突，属于不可由局部补写解决的失败。
6. 请求指定的核心机制必须在可观察关系中出现；只保留修辞而没有机制关系属于可修复缺陷。
7. `combat_role_profile` 只接受六个 canonical role；Reference Corpus taxonomy、伤害模式和队伍构成词不进入该角色集合。
8. 互相矛盾的硬约束属于请求级失败，不能靠改写候选绕过。
9. `PASS` 是完整且无 finding 的规格控制；`REPAIR` 是有阻断但局部可修复的候选；`FAIL` 是有阻断且至少存在不可修复 finding 的候选或请求。

## Fixture 字段合同

fixture 顶层固定包含 `schema_version`、`outcomes`、`finding_codes` 和按顺序排列的 `cases`。`schema_version` 固定为 `character-skill-failure-cases/0.1`。

每个 case 固定包含以下字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定、有序的案例标识；S0 使用 `skill_s0_01_...` 至 `skill_s0_18_...`。 |
| `title` | 面向审查者的案例标题。 |
| `category` | 领域覆盖类别，例如 `resource_loop` 或 `role_alignment`。 |
| `request` | 与生产字段解耦的请求观察：`brief`、`hard_constraints`、`forbidden_elements`、`combat_role_profile`。 |
| `candidate_observation` | 候选的可观察摘要：`summary`、`declared_facts`、`signals`；它不是未来 SkillKit 的字段合同。 |
| `expected` | oracle 判定：`outcome`、`blocking`、`repair_allowed`、`findings`。 |
| `coverage_tags` | 用于验收矩阵覆盖的稳定标签。 |
| `rationale` | 说明该案例为何落在该判定边界。 |

每个 finding 固定包含 `code`、`field_path`、`blocking`、`repairable`。`field_path` 指向 observation 或 request 中的可观察位置，不暗示生产实现路径。registry 中的 `repairable` 是该 code 的固定属性。

## 判定语义

| outcome | blocking | repair_allowed | 语义 |
| --- | --- | --- | --- |
| `PASS` | `false` | `false` | 关系完整、角色职责与请求一致，且没有 finding。 |
| `REPAIR` | `true` | `true` | 发现局部缺失、含混或不完整关系；补齐关系即可保留设计意图，所有 finding 都可修复。 |
| `FAIL` | `true` | `false` | 发现请求级矛盾、跨 taxonomy 角色污染、Reference Corpus 复制或角色职责冲突等不可由局部补写解决的问题；至少一个 finding 不可修复。 |

## Finding code registry

| code | 含义 | 可修复 |
| --- | --- | --- |
| `RESOURCE_LOOP_INCOMPLETE` | 资源的产生、消耗、转化或清理关系不闭合。 | 是 |
| `FORBIDDEN_RESOURCE_INTRODUCED` | 候选引入请求明确禁止的专属资源。 | 否 |
| `STATE_EXIT_MISSING` | 状态有建立或生效关系，但没有退出或替换关系。 | 是 |
| `TRIGGER_SUBJECT_AMBIGUOUS` | 触发主体无法与队友/敌方/角色等主体区分。 | 是 |
| `SUMMON_LIFECYCLE_INCOMPLETE` | 召唤物缺少出现、作用、离场、替换或约束中的必要关系。 | 是 |
| `ROLE_EFFECT_MISMATCH` | 能力的核心效果与请求指定的 canonical 角色职责冲突。 | 否 |
| `REQUESTED_MECHANIC_UNREPRESENTED` | 请求的核心机制只剩修辞，没有可观察机制关系。 | 是 |
| `CROSS_TAXONOMY_ROLE_LABEL` | Reference Corpus 或其他跨域 taxonomy 标签污染 `combat_role_profile`。 | 否 |
| `REFERENCE_COPYING` | 候选逐字或近乎逐字复制 Reference Corpus 的特定技能关系。 | 否 |
| `HARD_CONSTRAINT_CONFLICT` | 请求自身的硬约束无法同时满足。 | 否 |
| `MULTI_SKILL_LOOP_INCOHERENT` | 多个能力之间的资源读写或触发顺序互相矛盾，无法形成可追踪关系。 | 是 |

## 18-case 验收矩阵

案例顺序是稳定合同，必须保持 `01` 到 `18`：

| ID | category | 设计边界 | outcome | finding |
| --- | --- | --- | --- | --- |
| `skill_s0_01_resource_loop_complete` | `resource_loop` | 完整资源产生、持有、消耗与清理 | `PASS` | — |
| `skill_s0_02_resource_loop_incomplete` | `resource_loop` | 资源缺少产出或重置关系 | `REPAIR` | `RESOURCE_LOOP_INCOMPLETE` |
| `skill_s0_03_forbidden_resource` | `resource_loop` | 明确禁止专属资源却引入资源 | `FAIL` | `FORBIDDEN_RESOURCE_INTRODUCED` |
| `skill_s0_04_state_exit_missing` | `state_lifecycle` | 状态没有退出或替换关系 | `REPAIR` | `STATE_EXIT_MISSING` |
| `skill_s0_05_teammate_trigger_ambiguous` | `team_interaction` | 队友事件触发主体含混 | `REPAIR` | `TRIGGER_SUBJECT_AMBIGUOUS` |
| `skill_s0_06_summon_lifecycle_incomplete` | `summon_lifecycle` | 召唤缺少销毁、替换或约束关系 | `REPAIR` | `SUMMON_LIFECYCLE_INCOMPLETE` |
| `skill_s0_07_main_dps_mismatch` | `role_alignment` | `main_dps` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_08_sub_dps_mismatch` | `role_alignment` | `sub_dps` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_09_support_mismatch` | `role_alignment` | `support` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_10_healer_mismatch` | `role_alignment` | `healer` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_11_control_mismatch` | `role_alignment` | `control` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_12_defense_mismatch` | `role_alignment` | `defense` 硬职责与候选核心效果冲突 | `FAIL` | `ROLE_EFFECT_MISMATCH` |
| `skill_s0_13_requested_mechanic_missing` | `mechanic_representation` | 核心机制只停留在修辞 | `REPAIR` | `REQUESTED_MECHANIC_UNREPRESENTED` |
| `skill_s0_14_cross_taxonomy_role` | `taxonomy_boundary` | `on_field_dps`/`crowd_control` 污染角色 profile | `FAIL` | `CROSS_TAXONOMY_ROLE_LABEL` |
| `skill_s0_15_reference_copying` | `reference_integrity` | 逐字或近乎逐字复制 Corpus 技能关系 | `FAIL` | `REFERENCE_COPYING` |
| `skill_s0_16_hard_constraint_conflict` | `constraint_consistency` | 请求内部硬约束不可同时满足 | `FAIL` | `HARD_CONSTRAINT_CONFLICT` |
| `skill_s0_17_multi_skill_loop` | `multi_skill_coherence` | 多技能资源读写顺序不一致 | `REPAIR` | `MULTI_SKILL_LOOP_INCOHERENT` |
| `skill_s0_18_control_near_neighbor_pass` | `team_interaction` | 明确队友事件主体且召唤生命周期完整的 control 近邻 | `PASS` | — |

07–12 必须分别以 `main_dps`、`sub_dps`、`support`、`healer`、`control`、`defense` 为 primary role；18 是有意保留的 `control` 正例，避免把 control 相关设计全部拒绝。全套案例必须覆盖 registry 中的每一个 code、三种 outcome、所有领域类别和六个 canonical role。

## 多模型协作方式

### DeepSeek：候选生成

DeepSeek 读取 `request`、领域 glossary 与非 oracle 的案例观察，为每个案例生成候选技能组概念。候选只需描述可观察的主体、关系、生命周期和限制，不得自行发明新的角色词汇、数值平衡字段、Corpus 原文或未来生产字段。输出应保留 case ID，便于后续盲审配对。

### Ox Alpha：匿名盲审

Ox Alpha 只接收去掉 `expected` 和 finding code 的请求、候选观察与必要的领域定义，以 `PASS`、`REPAIR` 或 `FAIL` 及理由独立判定。它不负责修改仓库、决定生产 schema 或成为最终规格裁判；其价值是发现 S0 oracle 过宽、过窄或误把风格差异当成结构缺陷的地方。

### Codex/Sol：规格合并与 S1 入口

Codex 对比 DeepSeek 候选、Ox Alpha 盲审和 S0 oracle，确认领域词汇、案例边界与生产现状没有冲突。只有在以下条件同时满足时才进入 S1：

1. 18 个案例的 oracle 与盲审分歧已经逐案解释，尤其是 18 的 control 正例没有被全拒绝。
2. 所有 finding code、六角色职责和跨 taxonomy 隔离都有稳定证据。
3. 未来要支持的最小可观察能力关系已由领域讨论确认，但仍未提前写成生产字段。
4. S1 的接口候选能在现有 `ability_concept` 兼容路径下增量演进，并明确 provider、repair 和 evaluation 的责任边界。

S1 的第一份产物应是接口候选与迁移/兼容策略，随后才由 Luna worker 以测试先行方式实现；S0 本身不提交生产代码。
