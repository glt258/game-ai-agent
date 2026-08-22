# 沿街领域词汇

## Character Canon

角色 Canon 是可供剧情、NPC Agent、Knowledge Resolver、RAG 与角色设计共同使用的稳定人物事实。它优先记录一个人在城市关系网络中的社会身份、职业、生活、能力边界与表达方式，而不是营销文案或完整剧情简介。

## Player-defined protagonist

玩家自定义主角拥有协理人的正式职业身份，但不预设 Canon 本名。主角的能力只能把亲自理解并承担过后果的解决问题方法固定为行动框架，不能复制他人能力。

## Fixed character

固定角色拥有稳定的玩家可识别身份、生活与社会关系。固定角色可以是普通职业者、学生、研究者或艺人，不因进入可玩系统而获得超出 Canon 的社会权限。

## Individual bias

能力是由稳定自我认知形成的、有限且可描述的现实偏置。每项能力都需要个人规则、触发条件与限制；能力不替代职业训练，也不是元素、武器或数值战斗体系。

## Knowledge Boundary

Knowledge Boundary 表示角色在正常制度路径下是否有资格接触某条 Lore。访问资格不等于角色已经记住、理解或相信该信息；实际知识由角色身份、知识规则与运行时上下文共同解析。

## Role, responsibility, assignment

`role` 表示正式知识权限角色，`responsibility` 表示可由组织明确分配并问责的制度职责，`assignment` 表示与特定 Lore 直接相关的正式项目或任务。职业名称、阵营成员身份与游戏稀有度都不会自动替代这三种资格。

Knowledge Responsibility 必须是可被组织明确分配、承担、撤销、轮换和审计的制度职责；它不是 Lore 标签、职业名称、查询关键词、Role 的别名或临时 access flag。每个责任只属于一个 faction，并且不能自动授予该 faction 的全部高权限。

## Gameplay rarity

`A` 与 `S` 只表示产品层面的可玩角色稀有度，不表示世界内能力强弱、社会等级、知识权限或剧情重要性。玩家自定义主角位于普通 A/S 抽卡稀有度体系之外。

## 角色技能设计

**Skill Kit Concept（技能组概念）**：围绕一个角色的行动表达、因果关系与限制组织起来的整体技能设计意图。它描述角色如何参与场景，不等同于一组数值或装备配置。
_Avoid_: 技能清单、数值表

**Ability Entry（能力条目）**：技能组中可被单独理解的一个能力表达，包含其触发、作用、限制及与其他能力的关系。它不是脱离角色语境的效果标签。
_Avoid_: 效果标签、伤害条目

**Trigger Subject（触发主体）**：导致能力开始、转变或结束的角色、队友、敌方、召唤物或场景事件主体。它必须能与被能力改变的作用主体区分开。
_Avoid_: 触发条件、目标位置

**Effect Subject（作用主体）**：能力实际施加影响、承受变化或参与结果的角色、实体或状态主体；它不表示空间位置，也不是含混的泛化目标称呼。
_Avoid_: 目标位置、泛化目标

**Resource Loop（资源循环）**：资源从产生、持有到消耗、转化或离场清理的可追踪闭环。循环必须说明资源如何进入和离开角色的行动关系。
_Avoid_: 资源条、能量条

**State Lifecycle（状态生命周期）**：状态从建立到生效、更新、退出或被替换的完整变化过程。没有可理解的退出关系的状态生命周期是不完整的。
_Avoid_: 常驻状态、状态标签

**Summon Lifecycle（召唤物生命周期）**：召唤物从出现、承担作用到离场、被替换或受上限约束的完整存在过程。召唤物不是只在描述中出现的一次性名词。
_Avoid_: 召唤名词、独立单位标签

**Team Interaction（队友交互）**：角色与明确队友或队伍事件主体之间可追踪的触发、作用和反馈关系。队友交互不把“队友”当作无边界的效果位置。
_Avoid_: 队伍加成、队友目标位

**Mechanic Relation（机制关系）**：触发主体、作用主体、资源、状态、召唤物与能力条目之间的因果或时序关系。它要求关系可以被复述和检查，而不是只靠风格化修辞成立。
_Avoid_: 机制标签、风格文案

**Repairable Defect（可修复缺陷）**：不改变角色技能设计意图、只需补齐或澄清局部关系即可消除的设计缺陷。它与需要推翻请求或拒绝候选的矛盾不同。
_Avoid_: 小问题、可忽略问题

## 角色技能设计 S0.1（v0.1.1）

**Mechanic Skeleton（机制骨架）**：请求指定机制与具体 trigger→effect 因果/时序关系之间的可复述锚点；仅出现机制名称、回响/共鸣等修辞，不构成机制骨架。

**MECHANIC_SKELETON_ABSENT**：请求核心机制仅剩名称或修辞，没有与请求绑定的具体 trigger→effect 因果/时序关系；`repairable=false`，恢复需要重新创建设计而非局部补齐。

**REQUESTED_MECHANIC_UNREPRESENTED**：仅在已有具体 causal edge/设计锚点、但缺少反馈、退出或替换等一环时使用；该缺环可局部 `REPAIR`，不能只按机制名词计数。

**Canonical taxonomy boundary（canonical taxonomy 边界）**：B1.5 对跨 taxonomy 输入采用 fail closed。非 canonical 角色值进入 `combat_role_profile` 属边界违规；legacy flat alias seam 不适用于该 canonical profile，禁止自动 normalization，非法值不得写入 request 的 canonical profile。
