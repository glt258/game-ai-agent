# Game AI Agent Studio — Web v0.1 API Contract

状态：Architecture Freeze；W1-S1/W1-S2 contract 已冻结；W3-S1/W3-S2 与 W4-S1 Skill Playground contract 已实现
原则：HTTP layer 是 adapter；domain logic 仍由现有 Python modules 承担。

```text
CHARACTER_GENERATE_CONTRACT_V0_1 = FROZEN
CHARACTER_VALIDATE_CONTRACT_V0_1 = FROZEN
```

## 1. 通用约定

- Base path：`/api`。
- JSON UTF-8；request/response 只使用 Web DTO。
- 生成失败也返回结构化安全错误，不把 Python exception 直接序列化。
- 每个响应可带 `schema_version`，便于前端拒绝未知 contract。
- 没有数据库时，生成结果只在本次 HTTP response 和浏览器 session 中存在；不要把 `draft_id` 解释为可长期 `GET` 的 resource ID。

通用错误：

```json
{
  "code": "GENERATION_FAILED",
  "message": "Character generation did not complete safely.",
  "stage": "generation",
  "retryable": false,
  "details": {"provider": "opencode_go", "model": "deepseek-v4-flash"}
}
```

`details` 只允许已脱敏、allowlist 字段。绝不包含 API key、local path、stack trace、raw prompt、raw provider body、restricted lore 或完整异常文本。

## 2. DTO 规则

### 2.1 `CharacterGenerationRequest`

```json
{
  "brief": "设计一名临洲市公共安全联席体系所属的新角色。",
  "hard_constraints": ["不允许新增组织"],
  "soft_preferences": ["冷静但并不冷漠"],
  "forbidden_elements": ["秘密实验体"],
  "desired_connections": ["faction_005"],
  "request_id": "web_20260831_001",
  "combat_role_profile": {"primary_role": "support", "secondary_roles": []}
}
```

这些字段映射现有 `CharacterDesignRequest`；`combat_role_profile` 使用现有 canonical schema。Intent layer 在 W1-S1 application service 中固定显式启用，以确保返回真实 `CharacterDesignPlan`；offline/live mode 是 app factory/server configuration，不是请求参数。请求不能携带 secret、base URL 或 provider credential。

输入限制：`brief` 非空且有限长；数组是有限数量的非空字符串；`request_id` 遵守现有安全 ID 约束；role 只能是六个 canonical combat roles。检索策略和 provider 选择由后端 runtime 配置决定，不作为本轮 HTTP request 字段。

### 2.2 `CharacterGenerationResponse`

```json
{
  "schema_version": "web-character-generation/0.1",
  "request": {"request_id": "web_20260831_001"},
  "status": "completed",
  "draft": {},
  "plan": {},
  "canon_basis": [],
  "pipeline": [],
  "validators": [],
  "repair": {},
  "model_invocations": [],
  "audit": {}
}
```

`draft` 是现有 `CharacterDraft.to_dict()` 的显式 Web projection；`plan` 是现有 `CharacterDesignPlan.to_dict()`，当前 service 默认有值；`combat` 是现有 `CombatRoleProfile` 和可选 Skill shadow 的安全 projection；`canon_basis` 是安全 source projection；`pipeline`、`validators`、`repair`、`model_invocations`、`audit`、`raw_data` 是 API-specific DTO，避免前端依赖 Python 内部对象。

字段分类：

- STABLE：`schema_version`、`status`、`request`、`draft`、`plan`、`combat`、`canon_basis`、`validators`、`repair`、`pipeline`；
- OPTIONAL：`plan` 的 nullable 形态、`combat.skill_shadow_*`、`model_invocations`、`audit`；
- DEBUG_ONLY：`raw_data`，只能用于 Developer/Raw Data tab，核心 UI 不得依赖；
- DEFERRED：持久化 resource ID、history、approval、stream event 和 provider raw payload。

`validators[].name` 是稳定的 machine-readable validator identity（例如 `request_alignment`、`representation_completeness`、`canon_checker`、`evaluation_runner`）；`message` 只用于展示，前端不得按 message 做逻辑判断。

成功 response 的 `status` 为 `completed` 且 HTTP 200；pipeline 没有安全完成时不返回伪造 draft，统一使用安全 `error` envelope，当前状态码按错误类型为：

- 422：request DTO 不合法；
- 502：provider/agent 失败；
- 503：provider 配置/能力不可用或被限流；
- 504：provider bounded timeout；
- 500：未预期但已脱敏的 adapter failure。

## 3. `POST /api/characters/generate`

Purpose：调用真实 `CharacterGenerationAgent`，可选地包入现有 `CharacterAuthoringWorkflow`，返回 reviewable draft 和 audit。

Backend mapping：

```text
Web DTO → CharacterDesignRequest
        → CharacterAuthoringWorkflow
             → CharacterGenerationAgent.generate(use_intent_layer=True)
             → CanonChecker / bounded CharacterRepairAgent
        → EvaluationRunner
        → explicit Web DTO mapper
```

Execution：同步 POST；v0.1 不使用 SSE/WebSocket/job polling。成功 response 包含完整 request、draft、plan、combat、retrieval/tool audit、Canon/evaluation findings、repair summary、pipeline、safe raw-compatible data 和可用的 model invocation metadata。

Required：WEB_V0_1_MVP P0。

## 4. `POST /api/characters/validate`

Purpose：对 Studio 人工编辑后的 candidate 重新进行现有 parsing、grounding/Canon check，并运行已有 deterministic evaluation；前端不得自行实现 Canon validation。

Request：

```json
{
  "request": {
    "brief": "设计一个新的辅助角色。",
    "hard_constraints": [],
    "soft_preferences": [],
    "forbidden_elements": [],
    "desired_connections": [],
    "request_id": "web_validate_001"
  },
  "draft": {"draft_id": "draft_web_001", "status": "draft", "...": "typed CharacterDraft fields"}
}
```

`request` 和 `draft` 是唯一的重验证输入；客户端不上传或影响 plan、Canon basis、validator state、audit、provider config。Backend mapping：先调用 `CharacterDesignRequest` adapter 和 `CharacterDraft.from_mapping()`，服务端从 brief 重新构造 deterministic intent context，再调用 `CanonChecker.check(draft, request=...)` 与 `EvaluationRunner`。不调用 provider，不触发 repair，不写 Canon。

Response schema：`web-character-validation/0.1`，包括 `status`、`request_id`、`draft_id`、`validators`、`canon`、`combat`、`pipeline`、`summary`。`status=passed|failed`；正常完成但 checker/evaluator 判定失败时仍返回 HTTP 200 和 `status=failed`，不能把业务 validation failure 伪装成 HTTP 500。warnings 仍通过 validator/canon DTO 暴露。

错误：422 表示 request 或 domain CharacterDraft contract 不能解析；500 表示 validation runtime/adapter failure。错误 envelope 不返回 raw exception。validate response 不包含 generation-only `model_invocations`、`repair` 或 `raw_data`。

Required：W1-S2；是 Human Edit → Revalidate 的最小后端 seam。默认只验证，不自动 Repair。

## 5. `GET /api/characters/{draft_id}`

v0.1 **不提供**。当前没有 draft repository、history 或稳定持久化 resource。浏览器应使用最近一次 generate response；若未来引入 SQLite/approval state，再定义 resource contract，避免现在伪造 REST 资源。

## 6. `GET /api/canon/entities`

Purpose：浏览现有 Canon 中可公开展示的实体摘要。W3-S2 只读、同步，不创建数据库或第二套 Canon。

Query：可选 `q`、`type`、`limit`。`q` 在稳定实体 ID、类型、名称、aliases、摘要和 tags 上由后端检索；`type` 使用后端返回的 `entity_types` 元数据，不能由前端通过 ID 前缀猜测。`limit` 有 1–100 的上限。

Response schema：`web-canon-entity-list/0.1`。

```json
{
  "schema_version": "web-canon-entity-list/0.1",
  "entities": [{
    "entity_id": "faction_005",
    "entity_type": "faction",
    "name": "...",
    "aliases": [],
    "summary": "...",
    "tags": [],
    "relation_count": 5,
    "visibility": "public"
  }],
  "entity_types": ["faction", "lore", "character", "project", "case", "incident", "story"],
  "total": 30
}
```

实际 W3-S2 families 来自现有 loader/resolver：`faction | lore | character | project | case | incident | story`。当前 inventory 为 faction 6、public lore 13、character 7、project 1、case 1、incident 1、story 1；locations 没有稳定的 resolver browse seam，因此不加入。

## 7. `GET /api/canon/entities/{entity_id}`

Purpose：读取一个 public-safe Canon entity detail，供 Canon Explorer、Studio affiliation 和 Canon Basis 导航使用。

`entity_id` 只作为稳定 ID lookup；没有 arbitrary path、YAML 文件读取或 source type/ID 拼接。Response schema：`web-canon-entity/0.1`，包含显式的 common summary、与 `entity_type` 对齐的 typed `sections`、保持 source direction 的 `relationships`、以及经过过滤的 `provenance`。关系目标包含 `target_entity_type`、`target_name`、`available`；只有可解析且后端确认是 Canon family 的目标才可点击。

Faction detail 暴露 name/aliases/type/status/core function/public identity/public reputation/member profile/tags；不暴露 `internal_structure`、`knowledge_boundary`、`actual_goal`、secret/restricted fields。Lore 只暴露 `sensitivity=public` 的记录；restricted/internal/secret 记录统一安全返回 `404 CANON_ENTITY_NOT_FOUND`，不泄露原文或路径。Canonical character 与 Reference Corpus character 保持不同 family 和 route。

Status：200、404、422、500。错误 envelope 不包含内部异常；unknown 或不可公开实体使用 `CANON_ENTITY_NOT_FOUND`。Required：W3-S2。

## 8. `GET /api/reference-characters`

Purpose：列出 frozen Reference Corpus 的 bounded summaries。

Query：可选 `q`、`ip`、`combat_role`、`limit`；limit 有上限。`q` 由后端在稳定身份、游戏、关联组织和职业字段上检索，`ip` 支持 game id、catalog display name 和 aliases，`combat_role` 使用现有 `NormalizedRole`。Response 至少包含 `reference_id`、display name、game/IP、roles、occupation、ability categories、quality/completeness、schema/baseline metadata（不包含整份 YAML）。

Backend mapping：`CharacterReferenceRepository.list_all/list_by_game/list_by_role`、`ReferenceGrounding` summary/projection。

Status：200、400、404（unknown game/role）、500。Required：W3。

## 9. `GET /api/reference-characters/{reference_id}`

Purpose：展示一个 Reference Corpus record 的阅读视图和显式开发者 Raw Data。

Backend mapping：`CharacterReferenceRepository.get()`；通过 API-specific projection 输出 `facts`、`combat`、`narrative`、`sources/provenance`、`analysis` 和 quality。不得允许 arbitrary path；当前 Web DTO 不提供 raw YAML/debug 字段，核心 UI 不依赖原始数据。

Status：200、404、422、500。找不到记录时返回 `REFERENCE_CHARACTER_NOT_FOUND` 安全错误。Required：W3。

## 10. Skill Playground（W4-S1）

### 10.1 `GET /api/skills/playground/meta`

返回现有 Skill Design v1 的 authoritative family/mode vocabulary，不由前端维护第二套业务枚举。七个 family 为 `main_dps | sub_dps | support | healer | control | defense | basic_passive`；后者在现有 v2 runtime 中映射为 `role=support`、`mode=passive`、`mechanic.kind=passive`。mode 来自现有 `ABILITY_MODES`：`active | passive | reaction`。response schema 为 `web-skill-playground-meta/0.1`。

### 10.2 `POST /api/skills/playground/run`

请求为结构化 DTO，而不是 JSON 编辑器：

```json
{
  "family": "sub_dps",
  "mode": "active",
  "brief": "设计一个在队友行动后追加输出的技能。",
  "constraints": ["只能影响敌方"],
  "language": "zh-CN",
  "model": "web-offline-fixture",
  "preset_id": "generalization_sub_dps_v1"
}
```

response schema 为 `web-skill-playground/0.1`，包括 `semantic_ir`、`skillkit`、`evaluation`、真实流水线 `pipeline`、provider allowlist metadata 与 safe `evidence`。不返回 raw prompt、raw provider response、异常文本、路径或 secret。UI 的 Raw/Evidence tab 只能展示此安全 DTO。

Backend mapping：

```text
SkillPlaygroundRequestDTO
  → shared hybrid_ir.playground application seam
  → existing build_model_facing_request
  → provider adapter
  → parse Semantic IR
  → validate IR
  → deterministic compiler
  → canonical SkillKit parser
  → reference integrity
  → evaluator
  → Web DTO projection
```

业务失败（例如 evaluator `FAIL`）为 HTTP 200、`status=failed`，并保留已生成的 `skillkit` 与 evaluator findings；provider/runtime/configuration failure 使用既有 safe `error` envelope（通常 503/502），不伪装为业务结果。W4-S1 不自动 repair、不持久化、不 streaming。live provider 不由 Web 默认启用；本地浏览器 smoke 使用仓库既有合法 fixture preset，生产 provider 通过显式注入配置。

### 10.3 `POST /api/skills/generate`

Purpose：保留为后续兼容 route；W4-S1 使用 `/api/skills/playground/run`，避免在没有 character integration 需求时扩张 API。

Request 最小字段：`character_context?`、`role`、`mode`、`requirement`、`model`（仅 server allowlist/name，不含 credential）、`language`、`allow_repair`。`role`/`mode` 使用现有 choices；不定义第二套 Semantic IR/SkillKit schema。

Backend mapping：共享 seam 位于 `src/character_intelligence/hybrid_ir/playground.py`；CLI 与 Web 都复用现有 Hybrid contract、IR validator、compiler、canonical parser/evaluator。W4-S1 不启用自动 `SemanticRepairSession`。

Response：`SkillBrief`、semantic IR safe projection、compiled canonical SkillKit、evaluation report、first failure layer、repair status、safe diagnostics、provider/model metadata。raw prompt/raw response 永不返回。

Required：W4-S1，已实现；不阻塞 Character Studio MVP。

## 11. `GET /api/system/health`

Purpose：检查 API process、packaged Canon/story/reference resource loading 和 provider configuration status。

Response 只包括：`api=ok`、data resource status/counts、project/runtime version、provider configured/missing、supported execution modes；API key 值不返回。

Status：200 表示 process 和必需 read-only data 可用；503 表示必需 resource/load failure。该 endpoint 不发起 live model call。

Required：W1。

## 12. API 不提供的 route

v0.1 不提供 approval/publish、draft history、auth/user、arbitrary file/YAML、Canon write、stream events、WebSocket、GraphQL。添加 route 前必须先出现对应真实 domain/persistence capability，并补齐 DTO、security 和 targeted tests。
