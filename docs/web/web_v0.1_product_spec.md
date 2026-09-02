# Game AI Agent Studio — Web v0.1 产品规格

状态：Architecture Freeze 候选稿（基于 2026-08-31 仓库审计）
产品名称：Game AI Agent Studio / 游戏角色设计工作台

## 1. 产品定位

Web v0.1 是面向游戏策划、AI/Agent 开发者和项目维护者的内部工作台。它把仓库中已经存在的 Character Generation、Intent/Plan、Canon Retrieval、Evaluation、Canon Checker、Bounded Repair、Combat Semantics 和 Skill Design 能力变成可观察、可人工干预、可复用的界面。

它不是游戏官网、玩家产品、社区，也不是只有一个 prompt 输入框的 ChatGPT Wrapper。核心体验是：

```text
Brief → Intent/Plan → Retrieval → Generation → Deterministic Evaluation
      → Canon Check → optional Repair → Human Review → export
```

模型提出候选；Canon 仍然是只读的；机器通过不等于 Canon 批准；人工审查仍是最终权威。

## 2. 用户与范围

主要用户：

1. 角色策划、系统策划、世界观策划；
2. AI/Agent 开发人员；
3. 项目维护者和演示观众。

一级模块固定为五个：

| 模块 | v0.1 角色 | 交付优先级 |
|---|---|---:|
| Dashboard | 运行状态、最近一次运行摘要、真实可计算的资源状态 | P1 |
| Character Studio | 角色生成、结构化结果、检查和审查 | P0 |
| Characters | Canon 角色与 Reference Corpus 浏览；不伪装成持久化草稿库 | P1 |
| Canon Explorer | 只读浏览现有 Canon registry | P1 |
| Skill Playground | 复用现有 Hybrid Semantic IR → Compiler → Evaluator 流程 | P2 |

## 3. Character Studio

### 3.1 三栏工作区

桌面端采用三栏布局：

```text
┌──────────────────┬──────────────────────────────┬───────────────────┐
│ Character Brief  │ Character Workspace          │ Agent Inspector   │
│ 输入与约束       │ Character / Plan / Combat    │ Pipeline / Checks  │
│                  │ Canon Basis / Raw Data       │ Repair / Audit     │
└──────────────────┴──────────────────────────────┴───────────────────┘
```

目标宽度为 1440/1920px；1024px 维持三栏的可用压缩布局；手机端只保证不破坏，不为手机重做 Studio 工作流。

### 3.2 Character Brief

默认入口是自然语言 brief。普通用户不需要填写 JSON/YAML。后端 request adapter 将它映射为现有 `CharacterDesignRequest`：

- `brief`：必填；
- `hard_constraints`：明确不可违反的要求；
- `soft_preferences`：偏好；
- `forbidden_elements`：禁止元素；
- `desired_connections`：希望关联的既有 Canon/故事对象；
- `request_id`：由客户端生成安全 ID 或由后端生成；
- `combat_role_profile`：只接受现有 `CombatRoleProfile` 的 canonical role 值。

Advanced Mode 只暴露这些已有输入真正消费的字段。`Affiliation Constraint` 映射到 `desired_connections` 或明确 hard constraint；`Combat Role` 映射到 `combat_role_profile`。Tone、Archetype、任意自定义 `Canon Dependency` 在没有对应 runtime 字段前不显示为可执行控件，避免假参数。

Intent/Plan 层当前是确定性、advisory 的解析器。Studio 为了展示结构化 Plan，可在生成 service 中显式启用现有 `use_intent_layer=True`；不能把 Plan 当成新的持久化 domain schema。

### 3.3 Workspace tabs

#### Character

展示最终选中的 `CharacterDraft` 可读视图：姓名、年龄/年龄范围、性别、组织、职业、社会角色、战斗角色、设计概念、性格、背景、故事钩子、能力概念、知识边界、约束备注和开放问题。`status=draft` 要显式标注为“候选草稿”，不能显示为已批准角色。

#### Plan

只展示项目定义的结构化 IR：`CharacterDesignIntent` 和 `CharacterDesignPlan` 的 `parsed_intent`、generation constraints、recommended traits、canonical combat role profile。不要展示隐藏 Chain of Thought、完整 prompt 或未处理模型输出。

#### Combat

第一层展示 `CombatRoleProfile` 的 primary/secondary role。若本次生成实际产生 Skill shadow，则展示其 canonical SkillKit 摘要和 evaluator 状态；没有 shadow 时显示 `NOT_AVAILABLE_YET`，不从自由文本猜测完整技能循环。

#### Canon Basis

展示每个 `canon_basis` 条目的 `source_id`、source type、supports，以及可通过只读 Canon query 安全投影的名称/摘要/来源标签。检索 audit 中的 source IDs 和实际 draft 的 Canon Basis 分开显示。

#### Raw Data

开发者查看 API 返回的、经过 allowlist 和脱敏的结构化 JSON。禁止把 Python repr、完整异常、环境变量、任意本地路径或 provider 原始响应直接塞进此 tab。

### 3.4 Agent Inspector

Inspector 只展示有真实来源的字段，并标注数据可用性：

| 区域 | CURRENTLY AVAILABLE | DERIVABLE BY ADAPTER | NOT AVAILABLE YET |
|---|---|---|---|
| Generation Status | 成功结果的 draft/check 状态；失败时的安全 failure code | 统一 HTTP failure envelope | 实时百分比进度 |
| Pipeline | tool rounds、tool audit、finalization、Canon check、repair 结果 | 将 audit 和 result 映射为节点状态 | 生成过程中的逐节点实时状态 |
| Validators | `CharacterDraft` 解析/grounding、`CanonChecker`、可显式运行的 `EvaluationRunner` | 将 findings 按 validator 分组；Skill report 映射为 combat/representation finding | 未存在的 LLM critic/final judge |
| Repair | 是否尝试、最多一次、status、changed fields、initial/final check | 将 `RepairResultStatus` 映射为 UI 标签 | 多轮 repair、自动批准 |
| Grounding/Canon | source IDs、Canon Basis、checked source IDs、finding evidence IDs | source ID → 安全名称/类型 | confidence 分数、向量相似度 |
| Model Invocation | provider/model/outcome/turn/retry/latency/usage（字段存在且经过脱敏才展示） | 调用次数、purpose 分组 | 没有真实来源的 token cost、质量分、延迟均值 |

`ModelInvocationAudit` 当前包含 latency/retry/usage 等可选字段，但“可选字段为空”必须显示为 `NOT_REPORTED`，不能补 0 或猜测。provider secret 永远不进入浏览器。

### 3.5 Pipeline view

UI 数据结构使用通用节点数组，而不是把页面写死成单个 Generator：

```text
{ id, kind, label, status, attempt?, findings?, source_ids? }
```

v0.1 真实节点可为 `brief`、`intent`、`retrieval`、`generation`、`evaluation`、`canon`、`repair`、`final`。状态由完成后的真实结果推导：`pending | running | passed | failed | repaired | skipped`。同步 POST 期间只显示一个本地 `running` 总体状态，不伪造后端逐节点事件。未来可增加 Generator/Critic/Judge/Repair Agent 节点，不要求 v0.1 实现 Multi-Agent orchestration。

### 3.6 Human Review

架构支持以下顺序：

```text
AI Generate → Machine Evaluation → Human Edit → Revalidate
                                      ↘ Regenerate / Approve / Export
```

v0.1 可交付：前端本地编辑 draft、`POST /api/characters/validate`、再次生成、下载当前安全 JSON。由于没有 persistence 和 approval resource，`Approve`/`Reject`/云端保存在 UI 中属于 disabled/deferred action；不把“通过检查”写成“已批准”。

## 4. Characters / Canon Explorer

当前仓库真实有两类只读数据：

- Canon registry：`lore`、`factions`、`characters`、`projects`、`cases`、`incidents`、story canon 和 world rules；当前加载统计为 35 lore、6 factions、7 characters、1 project、1 case、1 incident、1 story；
- Reference Corpus：manifest 标记的 frozen `reference-corpus-v0.5`，16 条记录，5 个游戏，facts/sources/analysis 三种 schema。

Characters 页面分组展示：

1. Reference Corpus：名称、IP/游戏、战斗/机制摘要、质量/完整度、facts、abilities、sources、analysis、Raw Data；
2. Canon Characters：既有世界角色的只读记录；
3. Generated Draft：仅展示当前 Studio session 的 draft，不声称存在资产库；
4. Approved Character：v0.1 不存在真实 persistence/approval 状态，明确显示 `NOT_AVAILABLE_YET`。

Canon Explorer 的导航类型以实际 registry 为准：World Rules、Lore、Factions、Characters、Projects、Cases、Incidents、Story。所有 detail 访问通过 allowlist query module，禁止前端传任意文件路径或 YAML 路径。

## 5. Skill Playground

UI 映射现有手工 CLI 的真实流程：

```text
Character Context / Skill Brief
  → Hybrid Semantic IR model-facing contract
  → semantic IR parse/validate
  → deterministic compiler
  → canonical SkillKit parse
  → evaluator
  → user-confirmed bounded repair（最多一次）
```

Tab：Skill Brief、Semantic IR、Compiled Skill、Evaluation Result、Raw Data。当前 CLI 依赖 `scripts/skill_playground.py` 的 orchestration shell 和若干内部 runner seam；API 化前应抽取一个薄的 application adapter，不能复制或重写 compiler/evaluator，也不能为 Web 增加另一套 Skill schema。

## 6. Dashboard

v0.1 只展示真实可取得的摘要：最近一次 Studio 运行、最近一次失败、当前 Canon/Corpus 载入状态、provider 配置是否存在（只显示 configured/missing）、available Canon/Reference 数量。First-pass rate、repair success rate、平均 latency、token cost 在没有历史存储和统计来源前均为 Future Analytics，不显示假指标。

## 7. Non-goals

用户登录、权限体系、多人协作、实时协同编辑、支付、云同步、社区、分享平台、游戏客户端集成、完整世界观编辑器、复杂图数据库、复杂 Analytics、微服务、Kubernetes、Event Bus、GraphQL、WebSocket、Multi-Agent orchestration UI、Canonical publish/approval 均不属于 v0.1。

## 8. WEB_V0_1_MVP

当用户可以：

1. 打开 Character Studio；
2. 输入自然语言角色需求；
3. 调用真实现有 Character Generation runtime；
4. 查看最终 `CharacterDraft`；
5. 查看 `CharacterDesignIntent/Plan`；
6. 查看 Canon Basis 和检索 source IDs；
7. 查看现有 validator/checker results；
8. 查看是否触发 bounded repair；
9. 查看真实存在的 model invocation audit；
10. 查看安全的 Raw JSON，并能对人工编辑版本重新验证；

即定义为：

```text
WEB_V0_1_MVP
```

Characters、Canon Explorer 和 Skill Playground 可以作为同一版本的逐步接入模块，但不能阻塞 Character Studio 核心验收。
