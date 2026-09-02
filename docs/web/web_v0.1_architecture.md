# Game AI Agent Studio — Web v0.1 前后端架构

状态：Architecture Freeze 候选稿
审计仓库：`D:\game-ai-agent`
审计日期：2026-08-31

## 1. Repository Audit 结论

当前是 Python 3.10+ package，`pyproject.toml` 只声明 `PyYAML`、`openai` 运行依赖，未配置 Node/package.json 或 Web server。核心 runtime 位于 `src/`，数据位于 `src/along_street_resources/data/`，测试位于 `tests/`，离线演示和评估入口位于 `scripts/` / `evals/`。

可复用的事实：

- `CharacterGenerationAgent.generate()` 是同步、bounded 的一轮角色生成接口；`CharacterGenerationResult` 包含 `CharacterDraft`、sources、`CharacterGenerationAudit`，并可带 `CharacterDesignPlan` 和 opt-in Skill shadow。
- `CharacterDesignRequest` 是现有生成输入；`CharacterDraft` 是严格的、approval-independent 的候选结构，具有显式 `to_dict()`/`from_mapping()`。
- `DeterministicCharacterDesignIntentParser` 和 `CharacterDesignPlan` 已存在，但 Intent layer 在 generation API 上是 opt-in，解析结果 advisory。
- `CharacterAuthoringToolbox` 提供只读、bounded 的 lore/faction/character/story/world 查询视图；它不暴露 repository、resolver 或文件系统给模型。
- `CanonChecker.check()` 是纯确定性、只读、无模型的 Canon 检查接口，返回 `CanonCheckReport`、findings、checked source IDs。
- `CharacterRepairAgent` / `CharacterAuthoringWorkflow` 已定义 evidence projection、repair scope、immutable fields、最多一次 repair 和 full re-check。
- `EvaluationRunner` 已定义 `EvaluationSubject`、`EvaluationContext`、`EvaluationResult`，当前默认包含 request-alignment 和 representation-completeness validators。
- Combat semantics 的 canonical roles 是 `main_dps`、`sub_dps`、`support`、`healer`、`control`、`defense`；`CombatRoleProfile` 是现有结构化接口。
- Skill v0.8 已有 `SkillValidationContext`、Semantic IR schema/validator、deterministic compiler、canonical `ProtocolSkillKitCandidate`、`evaluate()` 和 bounded semantic repair；手工入口为 `scripts/skill_playground.py`。
- provider 通过 `AgentModel`、`ProviderChatClient`、`LiveLLMAdapter` 和 `model_factory` 管理；当前支持 offline fixture 与 live provider 配置，API key 从服务端环境读取。
- filesystem/package data loader 已提供 schema/registry 校验；reference corpus 使用 Pydantic models、manifest 和 file-backed repository。

本轮定向核验（不是全量回归）通过：Character CLI/generation/repair/Canon/Skill Playground 相关测试共 166 passed；offline Character CLI 与 Skill Playground `--help` 可启动。仓库 README 记录的最近 clean-checkout CI 基线是 `1602 passed, 1 skipped`，本轮不机械重跑全量 pytest。

## 2. Repository Capability Map

| Capability | Existing Module | Current Entry Point | Input | Output | Web-ready? | Required Adapter | Notes |
|---|---|---|---|---|---|---|---|
| Character Generation | `src/agents/character_generation.py` | `CharacterGenerationAgent.generate()` | `CharacterDesignRequest`/brief | `CharacterGenerationResult` | B | `CharacterAuthoringApplication` + DTO mapper | 核心生成、retrieval、finalization、grounding 已有；异常是 exception carrier，需要统一 failure envelope |
| Intent / Character Plan | `src/character_intelligence/intent/`, `planner/` | `parse_character_design_intent()`, `CharacterDesignPlan.from_text()`；generation `use_intent_layer=True` | brief | `CharacterDesignIntent`, `CharacterDesignPlan` | B | facade 显式决定是否启用并序列化 | advisory，不是隐藏思维链，也不是第二套 draft schema |
| Canon Retrieval | `CharacterAuthoringToolbox`, `character_retrieval.py`, `knowledge/` | toolbox `execute()` 或 deterministic retrieval plan | bounded tool call / request | safe observations、tool audits、source IDs | B | read-only `CanonQueryModule` | 需把模型 authoring view 与浏览器 query 分开，不能暴露任意 resolver/filesystem |
| Canon Checker | `src/agents/canon_checker.py` | `CanonChecker.check(draft, request=...)` | parsed `CharacterDraft` + request | `CanonCheckReport` | A | 显式 response mapper | 纯确定性、无模型、只读；Web 不复制规则 |
| Character Repair | `src/agents/character_repair.py` | `CharacterAuthoringWorkflow.run()` / `CharacterRepairAgent.repair()` | draft + report + request | `CharacterAuthoringResult`, `CharacterRepairResult` | B | facade 编排并脱敏 audit | 最多一次；允许字段和 hard constraints 有边界；不批准、不写 Canon |
| Evaluation Framework | `src/agents/evaluation/` | `EvaluationRunner.run()` | `EvaluationSubject` | `EvaluationResult` | B | generation 后显式调用 | 当前默认 validators 不是全套 UI 标签；只有实际运行的 validator 才显示 |
| Combat Semantics | `src/combat_semantics/roles.py` | `CombatRoleProfile`, normalization helpers | canonical/legacy role | canonical role profile | A | DTO validation | 只使用六个 canonical role；不把 burst/sustain 当 role |
| Reference Corpus | `src/reference_corpus/` + packaged YAML | `CharacterReferenceRepository.list_all/get()`；`load_reference_grounding()` | reference ID / brief | Pydantic reference models / bounded summaries | B | projection/query adapter | frozen v0.5、16 records；不要直接向 UI 复制 YAML |
| Canon / World Data | `src/knowledge/`, `src/story/`, packaged data | `KnowledgeResolver()`, `load_story_repository()` | typed ID | registry records / story repo | B | allowlisted Canon query | 当前 registry 类型为 lore/faction/character/project/case/incident/story/world rules |
| Skill Design | `src/character_intelligence/hybrid_ir/`, `compiler/`, `character_skill/` | `scripts/skill_playground.py` → `execute_playground()` | role, mode, requirement, provider | `FakePipelineResult`/SkillKit/report/repair | C | 先抽取 application adapter | CLI shell 使用 private runner symbols；不能直接把脚本当 Web service |
| Provider / Model Adapters | `src/agents/model_protocol.py`, `provider_protocol.py`, `model_factory.py`, `live_llm.py` | factory + `AgentModel.generate()` | server-side env/config | model turn + sanitized invocation audit | B | server-only configuration module | 浏览器只看 provider/model/status，不接触 key/base credential |
| CLI / Demo | `src/agents/official_character_authoring.py`, `scripts/*.py` | PEP 621 script、module、manual playground | args/stdin | text/JSON presentation | C | reuse domain composition, do not call CLI renderer | CLI 输出不是稳定 HTTP contract；`official_character_authoring` 是 orchestration/demo shell |

分类含义：A=已有能力，可直接封装；B=已有能力，输出/错误/生命周期需适配；C=CLI-only，需要 service seam；本轮确认不存在的 capability 仍是 D=不应假装存在，例如持久化 Approved Character、实时 pipeline events、Multi-Agent orchestration、token cost analytics。

## 3. Deep Module 与 seam 设计

推荐新增的外部 seam 是 `src/web/services/` 中的少量 deep modules，而不是让 routes 了解每个 agent 的内部对象：

```text
HTTP route
  → CharacterAuthoringApplication.generate(request DTO)
      → CharacterGenerationAgent / CharacterAuthoringWorkflow
      → existing validators / Canon / provider adapters
  → explicit Web DTO response
```

`CharacterAuthoringApplication` 的 interface 应保持小而深：接收一个已校验的 Web generation request，返回一个成功结果或统一安全 failure；复杂的 request construction、intent opt-in、reference grounding、checker/repair composition、audit projection 都留在 implementation 内。测试通过这个 seam，不穿透 HTTP 也不复制 domain 规则。

`CanonQueryModule` 是另一个 seam：只接受固定 `source_type + safe ID` 或 bounded search parameters，返回安全 summary/detail。它不是通用文件读取器。`SkillPlaygroundApplication` 只有在 private CLI orchestration 被抽成可复用 interface 后才建立；否则 Skill API 先保持 deferred。

## 4. Backend architecture

选择 FastAPI 作为 HTTP layer。它与 Python runtime 同语言、便于依赖注入和 Pydantic request/response validation，能直接调用现有同步 agent，不需要把业务搬到另一种语言。FastAPI route 只处理 HTTP concerns：参数、状态码、CORS、错误 envelope；不在 route 中重写 retrieval、Canon、repair 或 compiler。

推荐目录：

```text
src/
  agents/                         # unchanged domain/agent implementation
  character_intelligence/         # unchanged intent/plan/skill IR/compiler
  character_skill/                # unchanged canonical SkillKit/evaluator
  knowledge/                      # unchanged read-only registries
  reference_corpus/               # unchanged corpus models/repository
  web/
    app.py                        # FastAPI app factory
    api/
      routes_health.py
      routes_characters.py
      routes_canon.py
      routes_references.py
      routes_skills.py             # deferred until adapter exists
    services/
      character_authoring.py       # deep application seam
      canon_query.py               # allowlisted read-only query seam
      reference_query.py
      skill_playground.py           # only after CLI seam extraction
    schemas/
      common.py
      characters.py
      canon.py
      references.py
      skills.py
    errors.py
    security.py

web/
  app/
  components/
  features/
    dashboard/
    character-studio/
    characters/
    canon-explorer/
    skill-playground/
  lib/                             # typed fetch client, error parser
  types/                           # Web DTO types, not Python internals
  package.json
```

没有现成 `src/web` 或 `web`，所以这是新增 adapter 层，不应移动或重命名现有 domain package。

## 5. Frontend architecture

推荐 Next.js App Router + React + TypeScript + Tailwind CSS：项目需要一个桌面工作台、清晰的 feature route 分组、TypeScript DTO 和可快速交付的本地 UI；现有 Python 仍是业务 backend，Next.js 只承担 UI shell 和 typed browser client。若实际部署环境无法接受 Next.js，Vite React 是可替代方案，但当前无需为替代方案同时搭建两套骨架。

- UI Component Layer：通用 panel、tabs、status badge、data table、JSON viewer；不包含 Canon 或 validator 规则。
- Feature Layer：`character-studio` 管 Brief、workspace tabs、inspector、local edit/revalidate；其他 feature 只消费 typed client。
- API Client Layer：`lib/api-client.ts`，集中 base URL、timeout、AbortController、problem parsing、JSON response validation。
- Domain DTO Layer：`types/` 对应公开 Web DTO；不把 Python dataclass、`repr` 或完整内部对象传给浏览器。
- State Management：v0.1 使用 feature-local `useReducer`/`useState`；一个 Studio session 的 request/result/edit buffer 足够，不引入 Redux、GraphQL 或全局 server cache。
- Streaming/Polling：第一版同步 POST，无 polling/WebSocket/SSE。请求期间显示整体 loading，响应后从 audit/result 计算节点。后端若未来提供 job ID，再增加 polling，而不是先建协议。
- Error Handling：后端统一 `{ code, message, stage?, retryable?, details? }`；`details` 仅 allowlist 字段。前端按 stage 展示可读错误，不展示 stack trace、prompt、原始 provider body。

## 6. Generation execution model

选择普通同步 POST：现有 `CharacterGenerationAgent.generate()` 是同步调用；model-loop 最多 6 个 action/tool rounds 后 finalization，deterministic retrieval 仍有 bounded calls；authoring workflow 在需要时最多一次 repair。运行耗时可能受 provider timeout/retry 影响，但当前没有 job store、event callback 或可恢复 execution state。

因此 v0.1：

- `POST /api/characters/generate` 在后端 worker 中完成一次完整 pipeline；
- 使用受控 server timeout，并把 provider failure/timeout 映射为安全失败；
- 返回完整 draft/audit/check/repair summary；
- 不伪造实时 pipeline 进度；
- 当实际 latency 已妨碍桌面 Demo、或引入 persistence 后，再评估 `job + polling`；SSE 只有在 runtime 有稳定 event seam 时才考虑，WebSocket 不在路线内。

## 7. Persistence decision

```text
Web v0.1 persistence: No DB
```

理由：Canon、world、story、reference corpus 当前是 YAML/package filesystem read-only；generated draft 是 runtime result，没有稳定 resource ID、history、approval store 或 review repository。v0.1 将 draft/result 保存在浏览器当前 session，人工修改后通过 validate endpoint 重新送入现有 parser/checker；Export 是下载安全 JSON，不是写回 Canon。

SQLite 只有在需要跨刷新保存 draft/review/history 时才作为下一阶段最小选择；PostgreSQL、多租户和云同步均推迟。

## 8. Security boundary

- Provider API key、base credential 和 private endpoint 只在 backend environment/factory；不出现在 DTO、browser bundle、logs 或 Raw Data。
- CORS 只允许配置的本地/开发 origin；生产部署不能使用 wildcard + credentials。
- 对 brief、array item、search query、raw JSON body 设置长度/深度/数组上限；拒绝超限输入。
- Canon query 只允许 allowlisted source types 和 validated IDs；禁止 arbitrary YAML/file path/filesystem access。
- 前端输入和 retrieved Canon 内容都视为 untrusted data；模型只能看到现有 authoring toolbox 的只读投影，不能让用户输入变成系统指令或 Canon evidence。
- exception mapper 只输出固定 error code、safe message、stage 和允许的 metadata；禁止 local Windows path、环境变量、stack trace、provider response body。
- debug/audit projection 只输出已有 `ModelInvocationAudit`/tool/check 字段；raw prompt、raw response、restricted lore 和 secrets 不得进入 Web DTO。

## 9. Human review 与未来 Multi-Agent

`CharacterDraft.from_mapping()` 是人工编辑输入的解析 seam，`CanonChecker.check()` 和 `EvaluationRunner.run()` 可对编辑后的 candidate 做重新验证；因此 Edit → Validate Changes 是可实现的，不需要前端复制规则。Regenerate 直接重新提交新的 request；Approve/Reject 需要 persistence 和 review state，v0.2 再实现。

Pipeline DTO 使用 `steps: PipelineStepDTO[]` 和 `invocations: ModelInvocationDTO[]`，每个 step 有 kind/status/attempt/findings/source IDs。v0.1 只填现有 generator/retrieval/evaluation/canon/repair 的真实节点；未来 Generator、Critic、Judge、Repair Agent 可以作为额外节点接入，当前不实现 orchestration framework。
