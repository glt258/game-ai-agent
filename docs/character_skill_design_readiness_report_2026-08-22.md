# 角色技能设计工程就绪度与多模型协作方案

日期：2026-08-22  
基线：[`011ad2e`](https://github.com/glt258/game-ai-agent/commit/011ad2e434fbe3ce6713d1b644724158b86b20f2)（`refactor: freeze combat role compatibility seam`）

## 一、结论

项目已经具备启动“角色技能设计”下一阶段的基础，但尚不适合直接让模型自由生成完整技能组。CI-B1.5 已冻结战斗角色兼容边界，解决的是角色语义入口与序列化一致性；技能设计仍缺少一层独立、可验证、可修复的领域合同。当前最合理的下一步不是增加更多提示词，也不是马上做数值平衡，而是先定义技能组的概念结构、失败案例和验收标准，再逐步迁移生成、验证与修复链路。

建议把后续工作划分为 CS-S0—CS-S4 五个阶段，并采用“Codex 主工程、Hermes DeepSeek 候选生成与真实 provider 观测、Ox Alpha 独立红队与盲审”的分工。Ox Alpha 的具体工程能力目前没有得到项目证据支持，因此不应让它承担 schema 修改、代码集成或最终裁决；它最有价值的位置是独立寻找遗漏、歧义与虚假通过。

## 二、现有能力与真实缺口

### 2.1 已经稳定的角色语义边界

当前 `CharacterDraft` 与 provider 之间是严格合同，canonical 战斗角色只通过 `combat_role_profile` 表达。旧 flat `combat_role` 仅存在于受限兼容入口，不属于 canonical 输出。共享解析、别名限制、冲突处理、未知值拒绝及 taxonomy 隔离集中在 [`src/combat_semantics/roles.py`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/combat_semantics/roles.py)，架构政策记录于 [`docs/character_generation/character_armament_architecture.md`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/docs/character_generation/character_armament_architecture.md)，冻结行为由 [`tests/test_combat_role_compatibility_freeze_b15.py`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/tests/test_combat_role_compatibility_freeze_b15.py)覆盖。这意味着技能设计可以依赖统一角色 profile，但不能重新引入第二套角色标量或扩大 legacy alias。

### 2.2 技能表达仍停留在自由文本

生成草稿目前只有自由文本 `ability_concept`（[`CharacterDraft`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_generation.py#L145-L178)；[provider schema](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/response_contracts.py#L41-L90)），它可以描述技能想法，却不能可靠表示技能主体、触发事件、资源循环、状态生命周期、召唤物生命周期、队友交互与机制因果关系。[representation validator](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/evaluation/validators/representation.py#L12-L59) 对该字段的约束基本只是非空，因此“文字通顺”可能被误认为“结构完整”。[request alignment](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/evaluation/validators/request_alignment.py) 目前主要校验 combat roles，也不能证明用户要求的技能机制真正落入草稿。

这会产生三个直接风险：第一，模型可能写出漂亮但不可执行的技能文案；第二，validator 无法区分机制缺失、主体错位和生命周期不闭合；第三，[repair 的 ABILITY 域仍映射到整个 `ability_concept`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_repair.py#L65-L95)，无法针对一个结构化技能节点做局部修复。因而，下一阶段需要的不是更长的 `ability_concept`，而是一个足够小、边界明确的概念技能组表示。

### 2.3 现有 benchmark 已经给出设计信号

[现有 benchmark A/B](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_benchmark.py#L107-L138) 已覆盖资源循环文本，说明“获得—消耗—恢复—转化”的闭环已被视为生成质量的一部分。[benchmark E/F](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/character_benchmark.py#L187-L208) 又明确记录了 representation pressure：一类是“队友事件由谁触发、谁受益”的主体问题，另一类是召唤物从生成、存在、行动到消失或替换的生命周期问题。这些压力不应继续以自由文本特判消化，而应转化为 CS-S0 失败案例，并驱动 CS-S1 的最小字段设计。

### 2.4 Reference Corpus 能提供先例，但不是 Canon

Reference Corpus 已包含结构化 [`AbilityFact`、`ResourceFact`、`StateFact`、`TeamInteractionFact` 与 `MechanicRelation`](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/reference_corpus/models.py#L128-L233)。这些类型证明技能事实可以被拆分，也为关系命名和边界案例提供先例。然而 [Corpus 的仓库定位](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/README.md#reference-corpus) 是参考材料，不是项目 Canon，更不是可直接复制的技能模板。设计时只能提炼抽象结构和验证问题，不能把现有角色事实复制成新角色，也不能因实现方便而修改或扩充 Corpus。

[官方 authoring 链路](https://github.com/glt258/game-ai-agent/blob/011ad2e434fbe3ce6713d1b644724158b86b20f2/src/agents/official_character_authoring.py#L128-L163) 已经暴露有界 reference summaries，这适合向模型提供受控先例：给出少量、与请求相关、带来源边界的摘要，而不是把整个 Corpus 塞入上下文。后续应继续保持这个“有界参考”原则，防止生成结果被单一参考角色牵引。

## 三、推荐路线图

### CS-S0：先写失败案例与规格

Codex 先建立技能设计规格和可执行失败案例，暂不改 provider。至少覆盖：资源只消耗不产生；状态无结束条件；队友事件主体混淆；召唤物无销毁、替换或上限；技能效果与 `combat_role_profile` 冲突；用户要求的核心机制只出现在修辞文本中；引用摘要被逐字复制；非角色 taxonomy 再次污染角色 profile。每个案例都要定义期望的通过、拒绝或可修复结果。

CS-S0 的交付物应是规格文档、术语表、验收矩阵和测试夹具，而不是生产 schema。DeepSeek 可针对同一请求生成多组失败候选，帮助扩充案例面；Ox Alpha 在看不到 Codex 预期答案的条件下做盲审，指出规格歧义和潜在假阳性。

### CS-S1：建立概念技能组领域合同

由 Codex 设计最小 conceptual skill-kit contract。建议表达“技能/被动条目、作用主体、触发或施放条件、效果、资源读写、状态读写、队友交互、召唤生命周期、机制关系和文本展示”这些概念，但不要提前引入倍率、帧数、冷却精确值等数值平衡字段。合同应允许未知或未指定，同时明确哪些组合必须闭合。

新接口应作为深模块：外部只需提交结构化技能概念，内部负责规范化、跨字段验证和错误定位。`ability_concept` 可暂时保留为兼容展示或派生摘要，但不能继续作为唯一事实源。CS-S1 完成条件是 schema、序列化、错误模型和单元测试达成一致，且不破坏 canonical `combat_role_profile`。

### S2：迁移生成、验证与修复链路

Codex 按“生成 → representation validation → request alignment → repair”顺序接入新合同。生成器输出结构化技能组；representation validator 检查资源、状态、主体及召唤生命周期；request alignment 校验用户技能约束，而不只检查战斗角色；repair 接收字段级诊断并做局部修复。迁移期间需要双读或兼容转换时，应明确退场条件，避免长期形成第二套平行表示。

此阶段 DeepSeek 负责在 Hermes 真实 provider 环境中运行候选请求，记录格式遵循、漏字段、修复稳定性和重复调用漂移。它不直接决定 schema，而是把真实行为证据反馈给 Codex。Codex 根据证据修改合同、代码和测试，并负责最终集成。

### S3：DeepSeek / Ox Alpha 现场评测

建立固定输入集和冻结评分表。DeepSeek 承担候选生成、provider 行为测试及 repair 循环观测；Ox Alpha 获得匿名化输出，独立进行红队和盲评，重点寻找主体错置、闭环伪造、参考复制、角色—技能不一致以及 validator 误放行。两者意见冲突时，以冻结规格、自动测试和可复现实例为裁决依据，不以模型自评或多数票裁决。

Codex 汇总评测，区分 schema 缺陷、提示词缺陷、provider 特性和评审分歧，并只对已复现的问题进行修复。建议保留每个失败案例的原始输入、结构化输出、诊断、修复输出及最终判定，以便形成可重复的回归资产。

### S4：冻结技能合同

当聚焦测试、现有 eval、全套测试及多模型盲评均无阻断项后，冻结 canonical skill-kit contract、兼容政策和 validator 语义。冻结提交应采用白名单文件范围，确认 Reference Corpus、私人脚本与无关文档未被带入。随后再决定下一里程碑是内容生产、数值模型还是运行时战斗模拟；不要在 S4 内顺手扩展设备、武器或 Canon。

## 四、模型职责边界

| 参与者 | 主责 | 不应承担 |
|---|---|---|
| Codex | 规格、领域 schema、代码、测试、迁移、集成、回归与最终工程裁决 | 无证据地扩大范围或直接写 Canon |
| Hermes DeepSeek | 候选技能组、失败样本、真实 provider 格式与 repair 行为观测 | 单独决定 canonical schema、直接合并生产代码 |
| Hermes Ox Alpha | 独立红队、匿名盲审、反例与规格歧义发现 | 代码所有权、最终验收；[官方当前仍将其标为限时 stealth preview](https://opencode.ai/docs/zen/)，能力未建立前不承担关键路径 |

推荐协作顺序是：Codex 发布冻结的 CS-S0 输入包；DeepSeek 产生候选和现场日志；Ox Alpha 独立盲审；Codex 将可复现问题转成测试并推进 CS-S1—CS-S2；CS-S3 再进行一次同构评测；最后由 Codex 执行 CS-S4 冻结。这样既利用不同模型的生成与批判差异，也避免三个模型同时修改同一接口造成规格漂移。

## 五、本轮明确不做

本路线不包含数值平衡、伤害倍率、装备或武器系统设计，不写入项目 Canon，不修改或扩展 Reference Corpus，也不扩大旧 `combat_role` 兼容政策。第一张执行卡应是 **CS-S0：角色技能设计 failure-case 与规格冻结**。只有当 CS-S0 能清楚回答“什么是结构完整、什么必须拒绝、什么可以修复”后，才进入 CS-S1 schema 实现。
