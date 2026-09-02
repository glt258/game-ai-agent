# Game AI Agent Studio — Web v0.1 实施计划与 ADR

状态：冻结为受控 implementation slices；W1-S1/W1-S2 backend foundation 与 Character contract、W2-S1 Character Studio、W2-S2 human-in-the-loop validation、W3-S1 Reference Corpus Browser、W3-S2 Canon Explorer、W4-S1 Skill Playground Web Integration 已实现。

## 1. W0 — Architecture Freeze

验收物：

- 本目录四份文档冻结：product spec、architecture、API contract、implementation plan；
- 确认 `src/web/` 是后端 adapter，顶层 `web/` 是 Next.js frontend；保留现有 domain package 不变；
- 定义 Web DTO、safe error envelope、pipeline step DTO、audit allowlist；
- 冻结同步 POST、No DB、feature-local state、无 SSE/WebSocket 的选择；
- 写出 domain → application seam → HTTP → frontend 的 contract tests 计划；
- 明确 `Character Studio` 是 P0，其他页面不得阻塞 MVP。

本轮状态：完成。下一阶段不应“开始开发整个 Web”，而应执行一个可单独验收的 backend slice。

## 2. W1 — Backend Web Adapter

状态：已实现 W1-S1 foundation 与 W1-S2 contract/validation seam。

范围：

- 新增最小 FastAPI app factory、CORS/input limits/error mapper；
- 新增 `GET /api/system/health`；
- 新增 `POST /api/characters/generate` 的 request DTO、application facade、success/failure response DTO；
- 在 facade 中显式构造现有 `CharacterDesignRequest`，启用现有 Intent/Plan layer，复用 `CharacterGenerationAgent` 与 `CharacterAuthoringWorkflow`；
- 将 `CharacterDraft`、`CharacterDesignPlan`、tool audit、Canon/repair/model audit 映射为安全 DTO；
- offline mode 作为 deterministic smoke path；live mode 仍从后端环境读取 provider 配置；
- 不做数据库，不做 streaming，不动核心 runtime。
- W1-S2 增加 `POST /api/characters/validate`；只接收 request context + edited draft，复用 `CharacterDraft.from_mapping()`、`CanonChecker`、`EvaluationRunner`，不调用 provider、不自动 Repair；冻结 `CHARACTER_GENERATE_CONTRACT_V0_1` 与 `CHARACTER_VALIDATE_CONTRACT_V0_1`。

实际文件：`src/web/app.py`、`src/web/routes/`、`src/web/schemas/`、`src/web/services/`、`src/web/mappers/character_generation.py`、`src/web/errors.py`、`tests/test_web_api.py`、`tests/fixtures/web/character_contract_v0_1.json`。

验收：health 可读；offline generation 通过真实 `CharacterGenerationAgent`/`CharacterAuthoringWorkflow` 返回稳定 JSON；edited draft validation 通过现有 checker/evaluator 返回 pass/fail；provider/agent/validation failure 使用安全 error envelope；OpenAPI 仅暴露三个本轮 endpoint；contract fixture 覆盖 generate success/failure/repair 与 validate pass/fail；未泄露 secret/path/raw output；domain 相关测试和 adapter targeted tests 通过。

## 3. W2 — Character Studio MVP

状态：W2-S1/W2-S2 已实现；后端未修改，前端已形成 Generate → Edit → Validate → PASS/FAIL 闭环。

范围：

- 顶层 `web/` 最小 Next.js/TypeScript/Tailwind shell；
- 左侧 Brief + 可执行 Advanced Mode；
- 中央 Character/Plan/Combat/Canon Basis/Raw Data tabs；
- 右侧 Inspector：pipeline、validator findings、repair、grounding、model audit；
- 使用已冻结的 `POST /api/characters/validate`，支持浏览器本地编辑后重新验证；
- Regenerate 重新提交 request，并在 dirty draft 时要求确认；
- Character 使用 structured fields 编辑，保留 generatedDraft/editedDraft、dirty、discard 和 stale validation 状态；
- validate 结果独立展示 generation pipeline，基于稳定 validator name/code/field_path 做字段/section 关联；
- Raw Debug 分组展示 generation response 与 validation response，不驱动核心 UI；
- Export、Approve 和 persistence 仍为后续范围，不写假 persistence。

验收：一个 offline 角色从 brief 到 draft/plan/check/audit 可观察；人工修改后能调用真实 checker，正常 PASS/FAIL 与 runtime error 分离；dirty regenerate 不静默丢失；UI 不显示隐藏思维链和敏感 debug 数据。

## 4. W3 — Knowledge Views

状态：W3-S1/W3-S2 已实现；W3 read-only knowledge views 已形成稳定边界。

范围：

- `GET /api/canon/entities` 与 `/api/canon/entities/{entity_id}`，提供 typed public-safe Canon list/detail（W3-S2）；
- `GET /api/reference-characters` / detail（W3-S1）；
- Characters 页面先提供冻结 Reference Corpus 的只读 summary/detail browser；Canon Characters、当前 session Generated Draft 和 unavailable Approved Character（后续 slice）；
- Canon Explorer 按后端返回的实际 entity types 浏览，支持 search/type filter、detail、outgoing relationship 与 provenance navigation（W3-S2）；
- W3-S1 只读 summary/detail projection，显式 Facts/Abilities/Combat Analysis/Sources tabs，不返回 raw YAML。

验收：页面数据来自现有 loader/repository；任意路径/任意 YAML 访问被拒绝；reference manifest/schema metadata 可追溯。

## 5. W4 — Skill Playground

### W4-S1 状态：已实现

范围：

- 新增 `src/character_intelligence/hybrid_ir/playground.py` 共享 one-shot application seam，Web adapter 不重复实现 pipeline；
- 新增 `GET /api/skills/playground/meta` 与 `POST /api/skills/playground/run`，复用 Semantic IR、deterministic compiler、canonical parser/evaluator、safe diagnostics；
- Web 输入为 family/brief/mode/constraints/language 的 structured form，结果展示 Semantic IR、SkillKit、Evaluation、真实 pipeline stages 与 safe evidence；
- evaluator 业务 FAIL 为 HTTP 200 且保留 SkillKit，provider/runtime failure 为 safe error envelope；不默认 live provider，fixture preset 仅用于离线 smoke；
- 顶层 `/skills` route 与 sidebar 已接入，typed client 已冻结 response guard；不启用自动 repair、persistence、streaming 或 character integration。

验收：七个 authoritative family 可选；至少三个现有 v2 fixture 通过完整 pipeline；业务 evaluator FAIL 保留 SkillKit；UTF-8 中文输入保持；`PASS/FAIL/NOT_REACHED`、first failure layer、diagnostics 可追溯；不新增 Semantic IR/SkillKit schema。

## 6. Testing strategy

### Backend

- Adapter unit tests：DTO validation、mapping、failure sanitization、pipeline status projection、no-secret/no-path assertions；
- API integration tests：FastAPI TestClient + injected offline model/fake provider，覆盖 health、generation success/fail、validate edited draft、Canon detail；
- Domain regression：只运行被 adapter 直接调用的相关测试文件；不为 HTTP 文案重跑全量 Python suite；
- Full pytest 只在跨越大部分架构、发布/合并前明确要求或定向测试暴露广泛回归时运行。

### Frontend

- component tests：Brief、tabs、status mapping、Inspector、Raw Data redaction；
- API contract tests：固定 Web DTO fixtures 与 error envelope；
- `test`（Node test + tsx）：编辑模型、dirty/discard、validate request shape、200 business failure、422 safe error；
- `typecheck`、`lint`、`build`：仅在 frontend skeleton/配置存在后执行；
- Critical E2E smoke：W2-S2 覆盖打开 Studio、offline generate、编辑、validate PASS/FAIL、错误展示；W3/W4 增加各自一个只读/技能 smoke，不铺开全量浏览器测试。

### 变更范围规则

| 改动 | 最小验证 |
|---|---|
| 纯 Markdown | `git diff --check` |
| Web DTO/mapper | 对应 adapter unit + API integration；必要时 domain targeted tests |
| Character generation/repair/checker 核心 | 对应现有 generation/repair/Canon tests；如横跨 runtime 再说明并扩大范围 |
| Frontend component/API client | frontend typecheck/lint/component contract tests |
| Layout/critical user flow | 上述检查 + critical E2E smoke |

## 7. Architecture Decision Records

### ADR-001 Frontend framework

Decision：Next.js App Router + React + TypeScript + Tailwind CSS。
Context：仓库没有 frontend package；v0.1 需要桌面工作台、feature route 分组、typed API client，业务仍在 Python。
Alternatives：Vite React、Jinja/HTMX、服务端渲染 Python templates。
Reason：Next.js 对页面壳和桌面 feature 组织足够成熟，TypeScript 能在 API seam 捕获 DTO 漂移；不把 domain logic 搬进 JS。
Consequences：增加独立 `web/package.json` 和 Node toolchain；必须保持 frontend 是 consumer，不允许成为业务规则来源。

### ADR-002 Backend API framework

Decision：FastAPI 作为薄 HTTP adapter。
Context：现有 domain/agent 全部 Python，同步调用、Pydantic 主要存在于 reference corpus，且需要 request/response validation。
Alternatives：Flask、Django、Jinja-only CLI bridge、Node API proxy。
Reason：同语言调用成本最低，Pydantic/FastAPI 对 DTO 和状态码清晰；routes 可以保持薄。
Consequences：需要新增 `src/web` application seam、同步 worker/timeout 策略和安全 exception mapper；不改变 `src/agents` 核心接口。

### ADR-003 Generation execution model

Decision：v0.1 使用 synchronous POST；不使用 WebSocket/SSE/job polling。
Context：现有 `generate()` 同步且 audit 只在完成/失败后返回，没有 event callback、job store 或可恢复状态。
Alternatives：SSE、job + polling、WebSocket。
Reason：同步 contract 最小、可观察且可靠；SSE 目前没有真实事件来源，job 需要 persistence。
Consequences：provider 慢时 HTTP 请求会等待；未来若实际 latency 超过 Demo 可接受范围，新增 job seam 和 polling，不在前端猜造进度。

### ADR-004 State management

Decision：feature-local `useReducer`/`useState` + typed fetch client。
Context：No DB、单用户本地 session、v0.1 只有一个核心 Studio 工作流。
Alternatives：Redux、Zustand、TanStack Query、GraphQL cache。
Reason：局部状态足够，依赖更少，减少把 API cache 当 domain state 的机会。
Consequences：跨页面最近结果不自动持久化；需要时以明确的 provider/context 或未来 server resource 扩展，不提前引入全局框架。

### ADR-005 Persistence

Decision：No DB for Web v0.1。
Context：YAML/package data 是只读；generated draft 没有 repository/history/approval state。
Alternatives：SQLite、PostgreSQL、browser-only IndexedDB。
Reason：当前 MVP 是可审计 Demo/内部工作台，数据库会扩大 scope；浏览器 session + JSON export 足够支持 Generate/Edit/Revalidate。
Consequences：刷新后不保证保留 draft，不能实现真正 Approve/Reject/history；SQLite 是 review persistence 的后续 prerequisite。

### ADR-006 API DTO boundary

Decision：使用 API-specific Pydantic DTO，显式映射到现有 dataclass/Pydantic/domain models。
Context：现有 runtime 同时使用 dataclass、Mapping 和 Pydantic；内部对象包含 implementation details 和可能不安全的异常/审计字段。
Alternatives：直接暴露 Python dataclass/asdict、共享一套前后端 schema generator、GraphQL schema。
Reason：DTO 是稳定外部 interface；domain schema 仍是事实来源，Web DTO 只负责 transport/sanitization，不产生第二套业务规则。
Consequences：需要维护 mapper 和 contract tests；domain 字段变更可能要求显式 DTO 版本更新，但安全和 locality 更好。

### ADR-007 Frontend/backend repository layout

Decision：后端放 `src/web/`，前端放顶层 `web/`；现有 `src/agents`、`knowledge`、`character_skill` 等不移动。
Context：仓库目前没有 web directory，Python package 使用 `src` layout，前端需要独立 Node workspace。
Alternatives：把 routes 放 `src/agents`、顶层单一 `app/`、另建独立 repo。
Reason：`src/web` 明确是 consumer adapter，保持 domain locality；顶层 `web` 清晰隔离 frontend toolchain，便于本地 Demo。
Consequences：有两个名为 web 的语义层但目录不同；README/启动脚本需明确 backend/frontend commands，禁止前端直接 import Python internals。

## 8. Architecture blockers / prerequisites

1. 当前没有 FastAPI/application service seam；W1 必须新增薄 facade。
2. 当前 generation failure 主要通过 exception 携带 audit；W1 必须统一 safe failure response，但不能更改核心 failure semantics。
3. 当前没有 runtime event stream；因此 Pipeline 只能在同步完成后派生，若要实时状态需未来新增 domain event seam。
4. 当前没有 draft/history/approval persistence；因此 Approved Character、GET draft、跨刷新 review 不能在 v0.1 假装支持。
5. W4-S1 已将 Skill Playground 的 one-shot application seam 放入 `src/character_intelligence/hybrid_ir/playground.py`；后续 integration 仍不得把 private pipeline 细节复制到前端。

## 9. Recommended next implementation slice

下一步最适合单独交给 Codex 的 implementation slice：

```text
W4-S1：Skill Playground Web Integration；保持现有 Skill contract，先抽取 public application seam。
```

W3-S2 已完成：复用现有 Canon registry/resolver 的安全 projection，补齐 entity list/detail、关系与 Canon navigation；不把任意 YAML/path 暴露给前端，不引入 persistence 或 Canon write。
