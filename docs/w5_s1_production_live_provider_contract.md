# W5-S1A Production Live Provider Contract v0.1

W5-S1A architecture audit and W5-S1B production provider contract freeze.
Audited source: `e4bf2b20acbe14bd2d8cf7b4eeaf7e4543bbfb71` (2026-09-06).
This document changes no runtime behavior. “Current” means that exact committed
tree; “Frozen target” means work still required in W5-S1B–E. Readiness means the
audit is ready for implementation, not that production integration already works.

## A. Verdict and scope

`W5_S1A_READY` was satisfied by the prior audit candidate and remote CI.
Decision: **EVOLVE_EXISTING**, **PARTIALLY_SHARED**, **PROVIDER_UNIFICATION_GAP**.
Reuse `ProviderChatClient`, `ProviderCompletion`, `ProviderClientError`,
`LiveLLMSettings`, `ProviderProfile`, and `ModelInvocationAudit`. Preserve
`AgentModel` and the Hybrid domain seam. Do not create another provider system.

S1A had no production code changes. S1B changes only the provider routing/config
seams described below; there are no live model calls, migrations, frontend
feature changes, W5-S2 work, or tags.

## S1B implementation update

The S1B implementation evolves this contract in the existing seams. `ProviderRoute`
and `resolve_provider_route` now resolve the five actual operation roles using
trusted runtime overrides, operation-specific environment pairs, or the
default `NPC_LLM_PROVIDER`/`NPC_LLM_MODEL` route. `LiveLLMSettings` exposes the
resolved route and renders its credential as `<redacted>`; route objects never
carry credentials. Character generation and repair factories receive explicit
operation roles, and the Hybrid live factory uses the same `skill_generation`
resolver while retaining `OpenCodeGoHybridProvider`.

S1B deliberately leaves retry/deadline policy, job cancellation/cleanup,
usage aggregation, Character async jobs and the full error taxonomy to S1C–E.

## W5-S1E-F4 update — OpenCode Go session affinity

OpenCode Go Chat Completions requires the server-controlled
`x-opencode-session` request header. The existing parent `InvocationContext`
now owns one opaque `uuid4().hex` provider-session ID for the lifetime of one
logical live operation. Character and Skill live jobs create that context once;
retries, structural recovery and repair reuse the same ID, while a new job gets
a new ID. Synchronous live adapters establish the same local parent context
when called without one.

`OpenAIChatClient` injects the header through the OpenAI SDK's `extra_headers`
argument only when the resolved provider is `opencode_go`. Other providers do
not receive it, and request bodies, routing, retry policy, deadlines, usage and
F3 safe error metadata remain unchanged. The session ID is generated only on
the server, is never accepted from browser or prompt input, is not logged,
persisted or exposed in Web DTOs/Inspector, and OpenCode calls fail closed if
they reach the transport without a parent invocation context.

## S1C implementation update — reliability contract

W5-S1C closes the shared live-invocation reliability boundary on the existing
provider and job seams. Each logical live operation owns one monotonic absolute
deadline and one cooperative `CancellationToken`; every attempt receives the
minimum of the configured timeout, the policy cap and remaining operation time.
The shared `InvocationPolicy` defines at most three attempts (two retries) with
bounded cancellation-aware backoff. Only normalized transient timeout, network,
rate-limit and unavailable failures are retryable; authentication, malformed
provider envelopes, context-limit and refusal failures fail fast. Failure audits
contain sanitized metadata only.

## W5-S1E-F7 update — finalization response diagnostics

Character finalization continues to request `response_format={"type":"json_object"}`
with no tools, `tool_choice`, thinking override or speculative output limit. JSON
Object mode guarantees transport syntax only; the root `CharacterDraft` schema and
`CharacterDraft.from_mapping()` remain authoritative for required fields, types,
nullability and extra-field policy. The prompt and runtime schema are generated
from the same repository-owned contract and its complete root example validates.

Malformed finalization responses remain fail-closed as `MODEL_RESPONSE_INVALID`,
with the response stage recorded as `finalization_response`. Safe diagnostics may
report content presence/length, JSON parse success, top-level shape, allowlisted
known keys, missing required keys, unknown-key count and a finite contract reason
(`FINALIZATION_EMPTY`, `FINALIZATION_INVALID_JSON`,
`FINALIZATION_WRONG_TOP_LEVEL`, `FINALIZATION_MISSING_REQUIRED`,
`FINALIZATION_INVALID_FIELD_TYPE` or `FINALIZATION_SCHEMA_MISMATCH`). They never
store raw response text, field values, arbitrary generated key names, prompts,
reasoning, tool arguments or credentials. Parser strictness, recovery boundaries,
retry/deadline policy, routing and provider thinking policy are unchanged.

## W5-S1E-F8 update — finalization context boundary

`finalization_context` is the pre-provider seam that reconstructs the bounded
Canon Evidence Bundle from successful action history. If that construction
fails, Web mapping emits `GENERATION_CONTEXT_FAILED` with the context stage and
safe reason/count metadata. This remains distinct from
`MODEL_RESPONSE_INVALID` at `finalization_response`, which is reserved for a
provider response received after the finalization request begins.

`LiveJobRegistry` separates logical state from physical worker settlement. A
timed-out or cancelled job stops publishing results immediately, but its worker
continues cooperatively until the provider returns or its shared deadline
expires. The unsettled worker still consumes admission capacity, preventing late
results from bypassing `max_in_flight`. Shutdown closes admission, cancels queued
work and signals running work; Python threads are never force-killed. Submission
after shutdown returns `LIVE_EXECUTION_SHUTDOWN`. This slice covers provider,
Hybrid, Character generation and Skill Playground live contexts plus safe Web
projections; public Character async routes and usage aggregation remain S1D–E.

## B. Baseline and evidence precedence

| Item | Evidence |
| --- | --- |
| Requested baseline | main / `e4bf2b20acbe14bd2d8cf7b4eeaf7e4543bbfb71` |
| Primary workspace observed | `D:/game-ai-agent`, main at `744a1b5d4202cd6da35c73d375818616eccd72f6`, dirty/untracked; untouched |
| Audit candidate | `New/w5-s1a-provider-audit-v2`, independent clean worktree at the requested commit; baseline captured with 0 dirty paths |
| Remote baseline CI | [run 34007537175](https://github.com/glt258/game-ai-agent/actions/runs/34007537175), exact SHA, completed/success; verified via GitHub Actions API |
| W4-S5 | COMPLETE as supplied; baseline contains final platform acceptance and portability fixes; remote baseline CI is green |
| Persistence | `CURRENT_SCHEMA_VERSION = 4`, `src/persistence/sqlite_store.py` |
| EKL provenance | graph still records reviewed working tree on main at `d1e511e…`, v0.8, release_equivalent=false; not a new release claim |

Runtime source > protecting tests > freeze contracts > architecture docs > status
docs > historical evidence > local artifacts, following
`docs/project_memory/current_state.md`. Local untracked benchmark files are not
evidence of implementation in this candidate.

## Baseline status supplied by the task

| Status | Value |
| --- | --- |
| UX-S1 | REMOTE CLOSED |
| UX-S2 | REMOTE CLOSED |
| CE-S1 | REMOTE CLOSED |
| CHARACTER_GAMEPLAY_PERSONALITY_ALIGNMENT_GAP | CLOSED; fixed deterministic validator is present in `e4bf2b2` |
| Schema | v4 |
| EKL | IN_SYNC (graph provenance warnings retained below) |

## C. Engineering Knowledge preflight

Executed `py scripts/project_preflight.py --task "W5-S1A Provider Model Adapter Character Generation Skill Generation Character Repair Evaluation Model Invocation Audit Async Live Jobs Web Adapter Runtime Diagnostics Unified CLI Runtime Path Resolution Persistence architecture audit contract freeze" --capture-baseline`.
Result: **READY_WITH_WARNINGS**, **TASK_BASELINE_CAPTURED**.

Enumerated actual IDs in `knowledge/project_graph.yaml`, then queried
`scripts/query_project_graph.py --graph knowledge/project_graph.yaml` using repeated
`--topic` arguments, rather than guessing node names:

| Concept | Actual queried node / coverage |
| --- | --- |
| Provider / adapter | `contract.provider_protocol`; preflight also matched `component.live_llm_settings`, `component.provider_profiles`, `component.openai_compatible_adapter` |
| Character generation / repair | `component.character_generation_agent`, `component.character_repair_workflow` |
| Skill generation / artifact | `component.semantic_skill_ir`, `contract.skill_design_artifact`; related compiler/validator nodes inspected |
| Evaluation | `component.character_evaluation`, `component.canonical_skill_evaluator` |
| Model invocation audit | literal `ModelInvocationAudit` query: no dedicated node; actual owner is `src/agents/models.py`, within the existing provider architecture, not a reason to invent a new subsystem |
| Jobs / Web | `component.live_execution_job`, `component.web_adapter` |
| Doctor / CLI / paths | `component.runtime_diagnostics`, `component.unified_cli`, `component.runtime_path_resolution` |
| Persistence | `component.persistence_foundation`; related Character, Skill, historical report and Kit persistence nodes |

Relevant real edges: generation **produces** CharacterDraft and **retrieves_from**
authoring toolbox; repair **repairs** CharacterDraft and **depends_on** CanonChecker;
Character evaluation **evaluates** CharacterDraft; semantic validator **validates**
Semantic Skill IR; canonical evaluator **evaluates** canonical SkillKit;
OpenAI-compatible adapter **implements** provider protocol; Web **adapts** generation
and live jobs; live jobs **depends_on** provider protocol; CLI **exposes** diagnostics
and Studio startup; diagnostics, Studio and persistence **depends_on** runtime paths.
The job→provider edge is architectural dependence through application work, not a
direct `LiveJobRegistry` import of the provider.

Frozen contracts inspected: CharacterGenerationAgent, CharacterDraft, authoring
toolbox, CanonChecker, one-attempt Character Repair, Semantic IR, compiler,
canonical SkillKit/evaluator, KnowledgeResolver, runtime Canon boundary,
SkillDesignArtifact, Binding, Alignment and CharacterKit. Evidence includes
`docs/runtime_freeze_v0.6.6.md`, `docs/character_repair_loop_v0.1.1.md`,
`docs/character_generation/character_skill_design_v1_freeze_v1.0.md`,
`docs/live_web_execution_contract_v0.1.md`,
`docs/cross_platform_runtime_contract_v0.1.md`, and their graph-listed tests.

Constraints preserved: drafts remain reviewable and never self-publish;
CanonChecker is deterministic/read-only; semantics precede compilation; graph
does not duplicate Canon records; experimental work is not a v0.8 release;
jobs are ephemeral; verification must use committed clean content.
Known limits: KL-001–005, KL-SKILL-001/004, KL-ENG-001 and KL-PERSISTENCE-001.

Warnings: graph review base predates architecture, candidate branch differs from
graph main, and reviewed-working-tree snapshot is not release-equivalent.
No GRAPH_INVALID conflict. These are existing provenance warnings, not permission
to rewrite history. No graph modification is needed for an audit-only design;
future routing/runtime work must not be marked implemented in the graph.

## D. Repository-wide usage map and provider inventory

Tracked-tree scan used all required terms: `provider adapter model llm live
opencode deepseek mimo openai api_key token base_url timeout retry usage audit job
invocation`. Follow-up searches covered all tracked Python (including `evals/`),
frontend, scripts, tests, config, graph, fixtures and historical documents.
AST call-site inventory in Appendix 1 disambiguates methods from prose matches.
No second external model network sink was found: live model paths converge on
`OpenAIChatClient.complete → self._client.chat.completions.create`.
`urllib` in Studio/CI is local readiness HTTP, not another model client.

| Path / symbol | Responsibility and callers | Current status |
| --- | --- | --- |
| `src/agents/model_protocol.py::AgentModel` | `generate(AgentPrompt) → ModelTurn`; Character generation/repair, NPC, shadow consumers | stable runtime domain seam |
| `src/agents/provider_protocol.py::ProviderChatClient` | provider-neutral synchronous completion; called by live and Hybrid adapters, diagnostic adapters | stable transport protocol |
| `src/agents/openai_provider.py::OpenAIChatClient` | sole implemented live HTTP adapter using OpenAI SDK; model factories, Hybrid factories and eval diagnostics | shared runtime transport; production hardening pending |
| `src/agents/live_llm.py::LiveLLMAdapter` | AgentPrompt translation, capabilities, retry, ModelTurn normalization/audit; factories and eval subclasses | existing live runtime/pilot |
| `src/agents/model_factory.py::LiveLLMSettings` | parse/validate NPC_* env; both factory families and diagnostic runners | canonical existing config |
| same file: `model_from_environment`, `character_model_from_environment` | construct offline fixture or injected/live adapter; NPC/demo and Character app/CLI respectively | runtime factories; duplicated construction |
| `src/agents/provider_profiles.py::ProviderProfile`, `ProviderCapabilities` | logical provider, transport, capability and options resolution; settings/adapter consumers | runtime config, compatibility profiles |
| same file: `resolve_provider_profile`, `apply_structured_output_override`, `TransportFamily` | resolve known profiles, transport and explicit structured mode | runtime; only Chat Completions implemented |
| `src/character_intelligence/hybrid_ir/runner.py::HybridProvider` | `complete(request_text) → object`, counters/outcome properties; Hybrid pipeline | separate domain seam |
| same file: `OpenCodeGoHybridProvider` | wraps shared client, retries/counters, returns text; both Hybrid factories | pilot live adapter; supports non-OpenCode provider despite name |
| same file: `_default_hybrid_provider_factory` | hard-coded opencode_go, model default deepseek-v4-pro, 60s/0 retry; formal runner and manual CLI | PILOT_ONLY |
| same file: `live_hybrid_provider_from_environment` | env-backed factory plus explicit provider/model override; Web Skill service | S3F/S3G integration seam, pilot |
| `src/agents/demo_model.py::DeterministicDemoModel` | offline NPC tool/evidence responses; NPC factory | offline runtime |
| `src/agents/character_generation.py::DeterministicCharacterGenerationModel` | deterministic draft fixture; Character factory, demos/tests | offline runtime |
| `src/agents/character_repair.py::DeterministicCharacterRepairModel` | offline bounded repair fixture; apps/demo | offline runtime |
| `src/agents/model_protocol.py::ScriptedAgentModel` | finite queued ModelTurns, records prompts in memory; tests/evals | test/eval-only |
| Hybrid runner `FakeProvider` | deterministic supplied IR/response, call counters; offline presets, tests, repair revalidation | offline/test fixture |
| `evals/character_skill_s2_shadow_evidence.py::ShadowEvidenceModelRouter` | deterministic legacy generation + independent live shadow call; shadow cohort runners | historical pilot, not production routing |
| same file: `_MinimalTransportAdapter`, `_FullInputTinyOutputAdapter` | LiveLLMAdapter subclasses with isolated diagnostic prompts/normalization; tiny/enum/nested/compact probes | pilot-only |
| `scripts/audit_live_character_authoring_latency.py::_InstrumentedModel` | delegates model and captures safe latency; audit runner | diagnostic-only |
| recording/fixture generation wrappers | `_RecordingGenerationAgent`, `_InstrumentedGenerationAgent`, `_FixtureGenerationAgent`; delegate/retain domain result | application/diagnostic glue, not transports |
| test clients and SDK doubles | named inventory in Appendix 1; enclosing tests are callers | TEST_ONLY; no real API |

DeepSeek is a **profile on the shared adapter**, not a separate DeepSeek SDK.
MIMO is a model entry under `opencode_go`; there is no dedicated MIMO adapter.
Profiles: `openai`, `deepseek`, `openai_compatible`, `opencode_go`.
OpenCode known Chat models: glm-5.3/5.2/5.1, kimi-k3/k2.7-code/k2.6,
mimo-v2.5/v2.5-pro, hy3, deepseek-v4-pro/v4-flash. Grok-4.5 and gpt-5.6-luna
select recognized-but-unimplemented Responses transport. Minimax-m3/m2.7/m2.5
and qwen3.8-max/3.7-max/3.7-plus/3.6-plus select recognized-but-unimplemented
Anthropic Messages. These are pinned repository declarations, not claims about
today's remote model catalog or successful live verification.

## E. Existing interfaces and structures

`ProviderChatClient.complete` keyword request: `model`, `messages`, `tools`,
`timeout_seconds`, `response_contract` (default text), optional `tool_choice`
and optional `thinking`. No request dataclass,
operation role, correlation ID, deadline, cancellation or typed output limit.
`ProviderCompletion`: nullable `text`, tuple `tool_calls`, nullable `finish_reason`,
`usage`, `request_id`. `ProviderToolCall`: `id`, `name`, `arguments`.
`ResponseContract` (agent-owned) → `negotiate_response_contract` →
`NegotiatedResponseContract` with TEXT/JSON_OBJECT/JSON_SCHEMA. Strict unsupported
capabilities fail before network; OpenAI profile conservatively uses JSON object.
OpenCode MIMO profiles declare tools-only, yet Hybrid currently forces JSON_OBJECT.

`ProviderClientError(kind, retryable, status_code)` kinds are only authentication,
timeout, rate_limit, provider. `ModelError` adds optional `.audit`; subclasses:
ModelConfigurationError, ModelCapabilityError, ModelAuthenticationError,
ModelTimeoutError, ModelRateLimitError, ModelProviderError,
ModelMalformedResponseError. `HybridProviderInvocationError` exposes only
TIMEOUT/TRANSPORT_FAILURE. AgentExecutionError/AgentToolError are domain failures.

`AgentPrompt` holds safe views, conversation, tools, session/turn, optional
authoring payload/response format/purpose and provider-neutral tool invocation
intent. `ModelTurn` holds text/tools,
structured output, segments and optional invocation. Hybrid uses
`ModelFacingRequest` in `hybrid_ir/contract.py`, `HybridGenerationContext`,
`HybridExperimentIdentity`, `HybridEvidence`, `HybridLiveResult` and
`FakePipelineResult`; these are domain/research structures, not competing HTTP SDKs.

## F. Exact Character live flow

```text
create_app(generation_mode='live')
  → CharacterGenerationApplication.__init__
  → character_model_from_environment(mode_override='live')
  → LiveLLMSettings → profile → OpenAIChatClient → LiveLLMAdapter
POST /api/characters/generate [sync FastAPI def]
  → CharacterGenerationApplication.generate → to_domain_request
  → CharacterAuthoringWorkflow.run → _RecordingGenerationAgent.generate
  → CharacterGenerationAgent.generate(use_intent_layer=True)
  → deterministic intent/plan projection
  → up to 6 model-loop action rounds + deterministic toolbox execution
  → exact FINALIZE → _build_finalization_context
  → final AgentPrompt(response_format='character_draft', no tools)
  → AgentModel.generate → LiveLLMAdapter.generate
  → _provider_messages/_provider_tools/contract negotiation
  → ProviderChatClient.complete → OpenAIChatClient.complete
  → OpenAI SDK chat.completions.create [external HTTP]
  → ProviderCompletion → LiveLLMAdapter._normalize / ModelInvocationAudit
  → _normalize_character_draft_payload → optional missing-field recovery (1)
  → CharacterDraft.from_mapping → _validate_draft / grounding
  → CharacterGenerationAudit
  → CanonChecker → CharacterRepairAgent (at most 1) → CanonChecker
  → EvaluationRunner → Web mapper → CharacterGenerationResponseDTO
```

Provider/model chosen during app construction from NPC_* settings, not per
Character browser request; app default is offline. Live construction without
config raises before app creation completes. Current `game-ai-agent studio`
does not offer Character live mode; it launches the default offline Web app.
CLI `OfficialCharacterAuthoringDemo.make_demo` allows explicit local provider/model
arguments over env and reuses generation model for live repair.

Prompts live in Character generation system contracts and `AgentPrompt` assembly;
adapter serializes views/payload. Retrieval defaults to `model_loop`; the existing
`retrieval_strategy='deterministic'` alternative executes deterministic retrieval
then one finalize-signal model action (`_run_deterministic_retrieval`), followed by
final generation. Do not silently switch strategies during provider work.

Character action semantics keep tool availability separate from tool invocation
requirement. The initial action turn is marked `required` only when the request's
deterministic retrieval plan proves a Canon dependency; the transport maps that
intent to `tool_choice="required"`. Later action turns remain provider-auto so the
model can emit the exact `FINALIZE` signal. Finalization uses no tools and keeps
`tool_choice` absent while requesting structured JSON; structural recovery, repair,
NPC and Skill paths retain their existing optional/disabled behavior.

DeepSeek V4 thinking defaults to enabled, but the current provider-neutral
conversation model does not retain or replay `reasoning_content`. The verified
OpenCode Go DeepSeek Flash/Pro profiles therefore declare a disabled-thinking
compatibility policy for every tool-bearing request. The adapter preserves the
application's `tool_choice="required"` intent and transports the provider
compatibility choice as `extra_body={"thinking":{"type":"disabled"}}`.
No-tools finalization is not given this adapter override, and no reasoning
content is persisted, logged, or exposed. DeepSeek's official tool-call
guidance requires full `reasoning_content` round-trip when thinking is enabled;
the current DeepSeek Agent integration guidance additionally records
`supportsToolChoice: false` and `requiresReasoningContentForToolCalls: true` for
V4 thinking integrations
([DeepSeek Agent integrations](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)).
Supporting that larger history contract remains out of scope.

Timeout/retry: adapter 30s, 2 retries, backoff .5s then 1s; no whole Character
operation deadline, no Character job. A successful call gets audit in `_normalize`;
recognized transport and normalization failures attach `.audit`. Generation
attaches the accumulated `.model_invocations` to **any** propagating exception.
This preserves prior calls; it cannot invent an audit for an unhandled SDK decoding
failure that escaped before adapter normalization. Repair stores failures in its
result rather than throwing away the original draft.

## G. Exact Skill live flow and S3F/S3G

```text
SkillPlayground.tsx explicit execution_mode=live
  → POST /api/skills/playground/jobs (202)
    or POST /api/characters/skill-design/jobs (202)
  → service.submit_live_job → LiveJobRegistry.submit
  → ThreadPoolExecutor → _execute → work()
  → SkillPlaygroundApplication.run
    or CharacterSkillDesignApplication.design → run_character_skill_design
  → provider_for → live_hybrid_provider_from_environment
  → LiveLLMSettings → OpenAIChatClient → OpenCodeGoHybridProvider
  → execute_playground/run_playground_context_pipeline → _run_pipeline
  → build_model_facing_request(context, language)
  → HybridProvider.complete(request.text)
  → ProviderChatClient.complete(JSON_OBJECT, no tools)
  → OpenAIChatClient → SDK chat.completions.create
  → response.text → JSON parse → parse_semantic_ir → validate_skill_semantic_ir
  → compile_skill_semantic_ir → parse_candidate → validate_reference_integrity
  → deterministic canonical evaluate → FakePipelineResult / HybridEvidence
  → Character-specific Alignment (Character Skill path only)
  → build_skill_design_artifact_from_pipeline_result → optional Binding
  → normal result DTO stored in job → GET jobs/{job_id} (200 with result/error)
```

Evaluation precedes immutable SkillDesignArtifact assembly; it is not a separate
LLM call after artifact creation. Character Skill context is projected from the
provided draft/request/plan without generating another Character.

**PARTIALLY_SHARED**: settings, profiles, transport protocol and SDK client shared;
AgentModel/LiveLLMAdapter vs HybridProvider differ in request handling, retries,
error taxonomy, capabilities, metadata and audit. Character's optional legacy
`_generate_skill_shadow` instead uses its own AgentModel, default feature OFF,
separate shadow result/audit; it is not the current formal Semantic IR Web path.

S3G is implemented by `src/web/services/live_jobs.py`, both service submit methods,
both route modules, live-job DTOs, frontend polling and
`tests/test_live_web_execution.py`. S3F provenance survives in the Web/Hybrid
factory's 60s/0-retry baseline, that test's
`test_web_live_provider_default_matches_the_benchmark_timeout_baseline`, and
`docs/live_web_execution_contract_v0.1.md`. The supplied primary worktree has
untracked `scripts/benchmark_skill_live_provider.py`,
`src/character_intelligence/hybrid_ir/live_benchmark.py`,
`tests/test_live_skill_benchmark.py`, `docs/live_skill_provider_benchmark_v0.1.md`;
**none belongs to the audited commit**. Do not claim a committed S3F benchmark
or fresh live result from this evidence. Recover/review benchmark provenance before
the uncommitted benchmark; this audit does not import it.

Additional live entry points: NPC CLI/tool loop and grounding repair; Character
demos and latency audit; `HybridSemanticIRRunner.run_live`; manual Skill CLI;
historical CS-S2 cohort/probe runners (Appendix 1). They use explicit live/probe
gates, except manual Skill CLI is inherently a live tool gated by credentials.
No normal deterministic evaluation runner is a hidden LLM judge.

## H. Repair and evaluation boundaries

| Path | LLM / abstraction / routing | Bound and audit |
| --- | --- | --- |
| Character missing-field structural recovery | same AgentModel as generation; `character_draft_recovery` purpose | max 1 extra call, no independent timeout/retry; preserves valid fields; failure attached to generation |
| Character semantic repair | `CharacterRepairAgent.repair → AgentModel.generate`; live app/CLI shares generation model, injection can supply a different one; no hard-coded vendor in agent | max 1; shared adapter retry/timeout; `model_audit` retained on ModelError; generic exceptions store `str(error)` internally |
| Skill semantic repair | `SemanticRepairSession.run(Callable[[SemanticRepairRequest], object])`; manual CLI passes same provider.complete; live-capable callback, no factory/model owned by session | max 1, only evaluator FAIL with validated IR; no independent timeout/retry; exception becomes REPAIR_UNAVAILABLE without invocation audit |
| Skill Web repair | neither `execute_playground` nor Character Skill Web auto-repairs | exactly 1 generation pass; no separate repair endpoint |
| canonical SkillKit patch | `character_skill._repair.repair_once(..., patch_provider)` | deterministic authorization, atomic patch and reevaluation; one callback, can be supplied externally; no built-in live binding; not formal IR repair |
| NPC grounding repair | `NpcConversationAgent._repair_once`, same AgentModel | max 1 repair per final answer; failure audit retained, safe grounding fallback |

Current evaluators are deterministic: `EvaluationRunner` invokes
RequestAlignmentValidator, IdentityCoherenceValidator,
RepresentationCompletenessValidator and
PersonalityGameplayAlignmentValidator; `CanonChecker.check` performs read-only
Canon checks; `character_skill.evaluation.evaluate` checks canonical SkillKit;
`evaluate_character_skill_alignment` and
`evaluate_character_kit_role_coverage` inspect context/artifact evidence.
IR validation and compiler reference-integrity validation are deterministic too.
The personality/gameplay guard is deterministic and fixed in the audited HEAD;
no implemented production LLM evaluator/judge was found. Keep all these gates.
Future Multi-Agent Judge is **W5-S4**, not a production route in S1.

## I. Live jobs, timeout reality and concurrency

Current model: **SESSION_ASYNC_JOB**, process-local dict, ephemeral, not persisted.
Real states: **PENDING → RUNNING → SUCCEEDED/FAILED**; timer can fail PENDING or
RUNNING; TTL removal yields 404, not an EXPIRED state. Work success means a normal
result DTO exists; its domain `status` may still be failed. Domain PASS and job
SUCCEEDED must remain distinguishable.

`LiveJobRegistry`: RLock protects registry state, ThreadPoolExecutor defaults to
2 workers, in-flight limit 2, submit-time timer 90s (includes queue wait), terminal
TTL 900s, poll hint 1500ms. Environment ranges in J. No per-user/session ownership
field or per-session quota; UUID lookup is possession-based, and either polling
route currently retrieves either kind. “Session” describes lifecycle, not access
control. Multi-tenant authentication/orchestration is outside this local Studio.

The timeout marks FAILED, discards late results, **does not stop running HTTP**.
Capacity counts only PENDING/RUNNING: timed-out workers can still occupy threads
while new jobs are admitted, so executor backlog can grow under repeated timeouts.
Shutdown cancels queued futures (`wait=False, cancel_futures=True`), not running
HTTP; it does not explicitly cancel every timer or terminalize cancelled queued
jobs. Client abandonment only aborts fetch/polling, not backend work. Registry
state is thread-safe, but cancellation/resource accounting is incomplete.

Sync/async: providers, agents and live business operations are synchronous;
FastAPI business routes are `def` (framework worker thread); job work runs in its
dedicated executor. Async error handlers do no provider work. No blocking model
network call on the event loop was found. Keep domain synchronous. Character
live calls via `/generate` bypass the job admission limit; no shared Character/
Skill capacity contract today. Hybrid adapter mutable last-call metadata/counters
must not be shared between jobs. LiveLLMAdapter has no conversation cache, but
client shutdown/reuse ownership is not explicit.

## J. Actual configuration and frozen precedence

No repository provider file loader and no python-dotenv dependency. `.env` is
gitignored and can be sourced manually; it is not automatically read.

| Actual name / object field | Default / range / effect | Classification |
| --- | --- | --- |
| `NPC_AGENT_MODEL` | offline; explicit mode_override wins; accepts offline/live | CANONICAL (historical NPC prefix retained) |
| `NPC_LLM_PROVIDER` | openai; profile selection | CANONICAL |
| `NPC_LLM_MODEL` | required, no generic default | CANONICAL |
| `NPC_LLM_API_KEY` | required only for live settings; sole app credential env | CANONICAL secret |
| `NPC_LLM_BASE_URL` | explicit HTTP(S) URL else profile; required for openai_compatible | CANONICAL, trusted server config |
| `NPC_LLM_TIMEOUT_SECONDS` | factory 30, range 1–300; Web Hybrid setdefault 60 | CANONICAL with PILOT_ONLY seam default divergence |
| `NPC_LLM_MAX_RETRIES` | factory 2, range 0–3; Web Hybrid setdefault 0 | CANONICAL with PILOT_ONLY seam default divergence |
| `NPC_LLM_TRANSPORT` | profile default; aliases chat_completions/responses/messages and full enum values | CANONICAL; only Chat Completions implemented |
| `NPC_LLM_STRUCTURED_OUTPUT` | profile default; json_schema/json_object/none overrides capabilities | CANONICAL local override, not verified remote support |
| `NPC_WEB_LIVE_MAX_WORKERS` | 2, range 1–4 | CANONICAL current job config |
| `NPC_WEB_LIVE_MAX_IN_FLIGHT` | 2, range 1–8, must cover workers | CANONICAL current job config |
| `NPC_WEB_LIVE_JOB_TIMEOUT_SECONDS` | 90, range 1–300 | CANONICAL current job config |
| `NPC_WEB_LIVE_JOB_TTL_SECONDS` | 900, range 1–86400; counted after finish | CANONICAL retention config |
| `NPC_WEB_LIVE_POLL_AFTER_MS` | 1500, range 250–10000 | CANONICAL hint; UI waits at least 1000 |
| `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` | Doctor presence aliases only; not LiveLLMSettings credential fallback | LEGACY diagnostic recognition, not functional route aliases |
| `NPC_RUN_LIVE_SMOKE` | optional real test gate; CI sets 0 | TEST_ONLY / explicit probe |
| `GAME_AI_AGENT_DB_PATH` | SQLite path only | CANONICAL persistence; not provider registry |
| `LiveLLMAdapter.backoff_seconds` | .5; constructor-only, exponential | CANONICAL adapter option, no env name |
| `OpenAIChatClient.request_options` / profile.provider_options | direct DeepSeek extra_body.thinking.type=disabled; verified OpenCode Go DeepSeek tool turns use the adapter thinking option; reserved core fields rejected | CANONICAL trusted options; not browser input |
| `OpenAIChatClient.complete(response_mode=...)` | legacy text/structured_json alias | LEGACY direct-call compatibility |
| `SkillPlaygroundRequestDTO` | mode offline; provider opencode_go; model web-offline-fixture | PILOT_ONLY browser selection; model allowlist below |
| `_default_hybrid_provider_factory` | opencode_go, deepseek-v4-pro, 60s, 0 retries, JSON object, only key copied from process | PILOT_ONLY |

Profile base URLs: direct DeepSeek `https://api.deepseek.com`; OpenCode Go
`https://opencode.ai/zen/go/v1`; openai/compatible have no profile URL (OpenAI SDK
default for direct openai). SDK environment such as `OPENAI_BASE_URL`, logging and
proxy settings can influence SDK behavior independently of the project loader;
S1 must make the effective endpoint explicit and review SDK settings, not assume
that passing `None` establishes a trusted fixed endpoint.

Before S1B, supplied environment mapping **replaced** os.environ for settings;
mode_override > NPC_AGENT_MODEL > offline. CLI and Hybrid Web could overwrite
provider/model on copied environment values, and no production role routes existed.

S1B precedence: trusted runtime override > operation-specific configured route >
default configured route > environment-backed route. Operation-specific pairs use
`NPC_LLM_<OPERATION>_PROVIDER` and `NPC_LLM_<OPERATION>_MODEL`; existing
NPC_* names stay supported; OPENAI_API_KEY/DEEPSEEK_API_KEY are not promoted to
aliases. Unknown/invalid explicit values fail typed configuration validation;
they never silently fall back. Lower-priority conflicts select the higher source;
contradictory definitions at the same source fail. Effective routes must be
resolved once per operation. Doctor reports presence only (configured / not
configured), never values and never a network request; distinguish its current
presence heuristic from actual usable configuration.

## K. Production gaps

| Priority | Gap / evidence | Slice |
| --- | --- | --- |
| Critical | timed-out job does not stop work and releases logical admission capacity while worker still runs; queue can grow | S1C/E |
| High | PROVIDER_UNIFICATION_GAP: duplicate transport retry/error/audit paths above shared client | S1B/C/D |
| High | no operation deadline; 30s×3+backoff already exceeds 90s job; env allows attempt 300s > browser 120s | S1C/E |
| High | Hybrid loses typed auth/network/unavailable and invocation audit; playground and Character Skill expose different mappings | S1C/D/E |
| High | Hybrid forces JSON_OBJECT despite profile capability; model route/provenance may claim default opencode_go even when actual provider is DeepSeek | S1B/D |
| High | SDK response attribute/JSON decoding outside normalized exceptions may escape without a failed-call audit | S1B/C |
| High | secret-bearing dataclass repr, raw generic repair exception strings, unbounded provider metadata and inherited SDK debug behavior | S1B/C |
| High | no server-owned role routing; browser overrides env; Character live config is eagerly required at startup | S1B/D/E |
| Medium | Character has no live jobs; separate capacity from Skill; sync live Skill endpoints remain callable | S1E |
| Medium | no explicit SDK client close/lifecycle; Hybrid stores mutable last-call metadata | S1B/E |
| Medium | `ModelCapabilityError` branch in Web mapper is shadowed by earlier ModelConfigurationError branch | S1C |
| Medium | Inspector omits existing usage/latency/retry metadata; Skill DTO lacks unified invocation metadata | S1E |
| Medium | S3F benchmark not in committed baseline; research evidence identity assumes Git/default provider | S1D |
| Deferred | streaming, price registry, durable usage/jobs, distributed scheduling, W5-S2 conditioning, W5-S4 judge | outside S1 |

No assertion here that an actual credential was leaked. Risks are code-derived;
no real secrets/config values were read into audit evidence.

## L. Frozen production provider contract

**EVOLVE_EXISTING**: `ProviderChatClient.complete` remains the transport interface.
Use its existing keyword request contract; do not add a parallel ModelProvider
hierarchy or vendor SDK-shaped request. `LiveLLMAdapter` remains the AgentModel
bridge, with domain parsing on the agent-facing side. Hybrid becomes a thin
consumer of the same shared invocation policy and audit; its domain pipeline and
callback contract remain intact. One retry owner, one invocation audit structure.

| Request concept | Frozen meaning |
| --- | --- |
| operation/task role | required at application invocation boundary: four roles in O; carry existing purpose for sub-steps |
| provider_id / model_id | separate resolved, non-empty identities; preserve existing `provider` / `model` names as compatibility serialization, never infer vendor from model string |
| messages / tools | existing provider-neutral message and tool mappings; app constructs prompts; provider transports them |
| structured expectation | existing negotiated response contract; generic schema supplied by caller only, no Character/Skill schema imported into transport |
| timeout | positive attempt budget bounded by remaining absolute operation deadline |
| max output / temperature | optional typed, capability-checked local options; nullable/unset preserves current behavior; unsupported explicit request fails capability validation |
| correlation | operation/session ID, job ID nullable for CLI, turn/invocation purpose; no credentials in identity |
| provider-specific options | trusted profile allowlist only; cannot override model/messages/tools/timeout/format, auth, endpoint, retry or streaming policy |

`ProviderCompletion` remains the neutral response; add neutral metadata at the
existing completion/audit seam as needed, not another result family:
resolved provider_id/model_id, nullable text or generic payload, tool calls,
nullable finish_reason/usage/provider_request_id, observed latency, attempt count.
Expose actual attempted number (1-based) and terminal total; pre-network config
failure has attempt count 0. Unknown usage is null, including individual fields.
Bound additional metadata to an allowlist of scalar diagnostics (no raw headers,
bodies, prompts, SDK objects). Runtime-measured latency is valid without vendor
usage. Provider-reported model may be nullable separate metadata, never overwrite
configured route identity without explanation.

Capability negotiation is shared before every live call. Keep the existing
profiles as non-secret config; extend with configured route/default model and
timeout policy where necessary. No provider registry database. Credentials
remain separate from serializable profile settings, excluded from repr/export.
Only the existing OpenAI Chat Completions transport is in S1's minimum scope.

## M. Frozen typed errors and Web mapping

Extend existing ProviderClientError/ModelError taxonomy; classification uses
status and safe structured provider codes, never arbitrary exception text.

| Category | Definition | Transport retry | Synchronous HTTP / safe user message |
| --- | --- | --- | --- |
| configuration_missing | missing required route/model/secret | no | 503 / Provider is not configured |
| configuration_invalid / capability_unavailable | invalid config or unsupported explicitly requested capability | no | 503 / Provider configuration cannot satisfy this request |
| authentication | upstream 401/403 credential/permission rejection | no | 502 / Provider authentication failed |
| rate_limit | upstream 429 | bounded yes | 429 / Provider rate limit reached |
| timeout | attempt deadline; operation timeout separately marked stage | yes only while operation budget remains | 504 / Model request timed out |
| network | connection/DNS/reset failure | bounded yes | 503 / Provider is unavailable |
| provider_unavailable | upstream transient 5xx | bounded yes | 503 / Provider is unavailable |
| context_limit | known structured context/token limit error | no | 422 / Model request exceeds the configured context limit |
| provider_bad_response | malformed HTTP/SDK envelope, impossible completion structure | no | 502 / Provider returned an invalid response |
| model_refusal | explicit provider refusal metadata | no | 422 / Model declined this request |
| cancelled | shutdown/explicit local cancellation | no | 503 with cancelled category if response still possible; terminal FAILED for job |
| unknown | unclassified upstream/runtime failure, safely normalized | no | 502 for upstream, 500 only genuine unexpected application defect |
| domain_output_invalid | valid provider response but malformed Character/Skill JSON/shape | no transport retry | 502 / Model returned invalid structured output |

Semantic validation findings remain normal domain result reports (200 for
completed evaluation, possibly failed), not provider errors. Client payload shape
errors remain 422. Canon/repair unresolved results preserve draft and findings.
Do not turn every failure into 500 or every 400 into context_limit.

For accepted async jobs, polling HTTP is **200** with terminal state and safe
error envelope; the table is the error's mapped status/category, not a promise
that polling becomes HTTP 429/504. Creation preflight config failures return 503;
capacity rejection 429; expired/missing polling 404. Safe details include category,
stage, retryable, identity and bounded invocation audit; no traceback. Frontend
must use category and preserve error meaning rather than infer every non-timeout
as 503. Human retry is explicit, never an automatic whole-job replay.

## N. Retry and timeout ownership

Current transport retry: SDK **0**; Character LiveLLMAdapter **2 retries** default
(3 attempts), permitted 0–3 retries, .5×2^retry backoff; Hybrid Web **0 retries**
default, env can raise to 3, no backoff in its own loop. No automatic whole-job
retry. Semantic repair is an additional bounded call, not the same transport retry.

Current upper envelopes (not measured wall-clock guarantees): Character model-loop
6 action calls + finalization + structural recovery + semantic repair = at most
9 logical calls (10 if explicit optional shadow enabled), ×3 default attempts
= 27 (30 with shadow). Configured max retries=3 permits 36/40. Deterministic
retrieval changes action-call count to 1, not provider timeout. NPC defaults to
4 tool rounds; `range(1, self.max_tool_rounds + 2)` permits up to 5 generation turns
plus one grounding repair. Skill Web is one call ×(1+retries); manual confirmed
semantic repair adds one call with same transport policy, up to 8 physical
attempts at retries=3. No current Character→Skill nested automatic job multiplier.
Research cohorts may make multiple explicit samples; they are not implicit job
retry and must remain out of normal runtime.

| Current layer | Actual source value and owner |
| --- | --- |
| Character/NPC attempt | 30s LiveLLMSettings/LiveLLMAdapter → OpenAIChatClient.complete |
| one Character invocation with defaults | approximately 91.5s worst attempt-budget sum (3×30+.5+1), not a strict wall-clock SLA |
| Hybrid Web attempt | 60s/0 retry via live_hybrid_provider_from_environment; timeout cast to int |
| formal Hybrid/manual CLI | 60s/0 retry via _default_hybrid_provider_factory |
| historical shadow cohorts | 30s/2 retries; TimeoutSuitability/ModelSuitability probes 60s/2; minimal/tiny/enum/nested/compact/minimal-SkillKit/O1 probes 60s/0 (eval constants, not production defaults) |
| Agent operation | no elapsed-time budget in Character/Skill agents or repair |
| Web job execution | 90s from submit, includes queued time |
| terminal retention | 900s after finish, distinct from execution budget |
| frontend polling | MAX_LIVE_WAIT_MS=120000, checked after polling returns; sleep max(poll_after_ms,1000) |
| browser individual fetch / Next rewrite | no configured per-fetch application deadline / no project proxy timeout override |

The current 120s polling loop is not a hard bound if one fetch hangs. SDK timeout
is a request/socket control, not proof of a whole operation deadline. Current
default 60 < 90 < 120 relation only holds for the single-attempt Skill path.

Frozen target: shared invocation runtime alone owns transient retry. Maximum
**2 attempts total** (1 retry), default 1 for Skill, 2 for Character; SDK retries
stay 0. Retry timeout/network/rate_limit/provider_unavailable only; one backoff
of .5s, bounded safe Retry-After may extend it up to 2s if deadline permits.
No semantic retry in transport, no HTTP-client hidden retry, no implicit job retry.
Character structural recovery <=1 and semantic repair <=1 remain distinct;
Skill repair <=1 remains explicitly invoked; budget does not reset on repair.
Legacy retry env maps retries+1; a value exceeding the production cap must return
typed invalid config, not silently multiply calls or silently clamp.

Frozen default budgets (targets, not today's values):

| Route | Attempt | Whole operation, including repair/backoff/validation | Job from submission | Browser horizon |
| --- | --- | --- | --- | --- |
| Skill generation/repair within one operation | 60s | 75s | 90s | 120s |
| Character generation/recovery/repair | 30s | 240s | 270s | 300s |

Formal relation: `attempt < operation <= job execution budget < browser horizon`;
TTL is orthogonal. Queue time reduces the remaining job/operation allowance;
calls use remaining absolute deadline, never replenish the operation budget.
These are ceilings, not a guarantee that every allowed turn/repair fits. Refuse
new attempts when insufficient budget remains, retain prior audit, report the
correct stage. Explicit overrides must satisfy the relation and a finite bound.
Per-fetch timeout must fit within remaining browser horizon. A longer Character
budget requires Character jobs; no promise that a proxy holds a 240s POST.

Cancellation minimum: deadline + shutdown signal; stop admitting work, cancel
queued work, prevent new attempts/repair after cancellation, discard late results,
close invocation-owned client resources and retain active-worker capacity until
work truly ends. Running synchronous HTTP cannot be assumed killed by a Future
or Timer. S1C/E must verify bounded resource release under stalled/slow local HTTP,
not merely a changed job status; no distributed cancellation or global queue.

## O. Role routing and Hermes/OpenCode boundary

Frozen route: `task role → trusted configured route → provider_id + model_id`.
Roles: **character_generation**, **character_structural_recovery**,
**character_repair**, **skill_generation**, **skill_repair**. Character
structural recovery uses the character_structural_recovery route with
its existing recovery purpose; semantic repair keeps its own scope. Absent
explicit repair route may inherit the corresponding generation route, resolved
and recorded before operation start. Evaluation is deterministic; no S1 evaluator
route. NPC and historical probes preserve compatibility and are not rerouted into
these domain roles by guesswork.

**DEFER arbitrary browser provider/model/base_url override**. Current limited
pilot selector must migrate to server-owned routes in S1E; legacy submitted
provider/model may only match the resolved route, mismatch returns 422 with a safe
message. Local explicit application/CLI configuration remains allowed. Never
hard-code Character→DeepSeek / Skill→MIMO in an agent.

Does game-ai-agent know Hermes directly? **NO** as a runtime integration.
Hermes appears in historical review docs and offline regression labels, not a
Hermes SDK/import/subprocess/protocol. Does live transport only know a
provider-compatible HTTP protocol? **YES**: OpenAI Chat Completions via SDK.
It also has explicit OpenCode Go profile/model compatibility knowledge; that is
endpoint/capability configuration, not Hermes internals or the OpenCode CLI.
The eval `ShadowEvidenceModelRouter` is an in-process experiment router, not a
Hermes gateway. No assumption is made about any privately deployed gateway.

## P. Secret, endpoint and logging boundaries

Frozen: API keys/tokens **never repository, Project Graph, Character SQLite,
browser response, normal logs or invocation audit**. Secret comes from trusted
server/local environment or explicitly injected secret value. Endpoint is trusted
server config; no frontend `base_url`/`api_key`. WebModel extra=forbid already
rejects those additions. Do not add a browser-to-arbitrary-URL proxy (SSRF).
Validate schemes/host, reject embedded credentials/query secrets, resolve selected
route before dispatch and prevent endpoint/auth override via provider options or
uncontrolled cross-origin redirects. Local fake endpoints are allowed only by
explicit trusted local configuration; no blanket prohibition on localhost.

Current positive boundaries: transport exceptions omit raw SDK text (`from None`);
normal LiveLLMAdapter logs only invocation fields; Web maps safe messages and
positive DTO allowlists, strips traceback/raw invocation error strings; Hybrid
evidence exports positive metadata allowlists; API has no secret fields.

Current risks: `LiveLLMSettings` dataclass repr includes api_key; no automatic safe
repr/redactor. Generic CharacterRepairAgent exception stores `str(error)` and CLI
authoring.to_dict serializes repair error (Web RepairDTO omits it). SDK DEBUG
logging is not controlled by application code. finish_reason/request_id/provider/
model and most audit strings are not bounded/redacted at construction; only HTTP
status/retryable are type-sanitized. Malformed provider/SDK attribute access can
escape normalized handlers. Existing tests cover several secret fixtures but do
not prove every possible SDK debug/exception path safe. Fix at shared seams.

Full prompts: assembled in memory; no full prompt in normal adapter logs or Web
DTOs. ScriptedAgentModel retains prompts in test memory. CLI output may contain
user request/domain draft/reference summaries; these are domain exports, not raw
provider transcripts. Explicit Saved Character persistence stores user request
and domain artifacts, not the fully assembled invocation prompt. Raw provider
envelope/body: not persisted/logged by default project code. Web `raw_data` is a
mapped domain result, not raw HTTP. Production debug must remain metadata-only;
no “debug mode” exception to secret/prompt/body exclusion.

## Q. Usage and ModelInvocationAudit freeze

Decision: **EXTEND**, never replace. Existing fields:
session_id, turn_number, provider, model, outcome, latency_ms, retry_count,
finish_reason, tool_call_count, usage, provider_request_id, transport,
response_contract, error_message, purpose, provider_status_code, provider_retryable.
ModelUsage fields: nullable input_tokens/output_tokens/total_tokens.

Reuse existing provider/model fields as distinct identities. Add only operation/
job correlation and typed error category/attempt observation where absent.
Keep aggregate invocation entry compatibility (`retry_count`, total elapsed
latency including backoff); an explicit attempt count is retries+1 for an invoked
call, zero for preflight failure. If individual attempt records are needed, use
the same ModelInvocationAudit type with attempt index; do not fabricate timings
for attempts not measured. Hybrid must stop overwriting the only last-call audit:
append invocation records for generation and repair, success and failure.

| Failure | Current Character/NPC | Current formal Skill |
| --- | --- | --- |
| auth / timeout / unavailable | normalized adapter audit attached to ModelError, retained by generation or repair | kind reduced; counters/last outcome survive, no ModelInvocationAudit |
| malformed HTTP/SDK envelope | caught SDK errors get audit; exceptions from post-SDK parsing/attribute access may escape without this call's audit | same transport gap plus no unified audit |
| empty/invalid model JSON | normalization failure audit attached; domain failures keep preceding success audit | JSON/IR failure evidence retained, no unified invocation audit |
| repair exhausted/failed | <=1 attempt; result keeps available model_audit and original draft | semantic evidence/one-call count only; callback exception loses typed provider details |
| job deadline/shutdown | no Character job currently | timer error has no partial call audit; late output discarded |

Production failure audit must be captured at invocation completion/exception,
retained through agent/service/job envelopes and sanitized before all logging.
Pre-call configuration records “not invoked” (0 attempts), not fake usage.
Record supplied usage only; missing stays null. Do not infer tokens from text
length, sum unknowns into zero or invent failed-attempt token usage. If only final
attempt usage is supplied, label its scope; aggregate remains unknown for missing
attempts. Latency uses monotonic measurement. Cost accounting **DEFER**: no pricing
registry exists, no hard-coded model price or token-to-currency calculation.

## R. Actual Web/API surface and target behavior

| Method / path | Request → response | Current mode / failure |
| --- | --- | --- |
| POST `/api/characters/generate` | CharacterGenerationRequestDTO → CharacterGenerationResponseDTO | server startup mode; sync only; maps known provider errors 502/503/504 |
| POST `/api/skills/playground/run` | SkillPlaygroundRequestDTO → SkillPlaygroundResponseDTO | sync; accepts explicit live as well as offline; provider failure TIMEOUT 504, others generally connection 503 |
| POST `/api/characters/skill-design` | CharacterSkillDesignRequestDTO (character+skill) → CharacterSkillDesignResponseDTO | sync; can accept live; provider result mapper retains timeout/rate-limit/provider distinctions but auth generic |
| POST `/api/skills/playground/jobs` | same Skill request → LiveJobAcceptedDTO, 202 | requires execution_mode=live; 422 invalid/offline, 429 busy |
| GET `/api/skills/playground/jobs/{job_id}` | ID → LiveJobStatusDTO, 200 | includes result or safe error; 404 unknown/TTL |
| POST `/api/characters/skill-design/jobs` | same Character Skill request → LiveJobAcceptedDTO, 202 | same registry, kind character_skill_design |
| GET `/api/characters/skill-design/jobs/{job_id}` | ID → LiveJobStatusDTO, 200 | result retrieval/failure is this poll endpoint; no distinct result endpoint |
| GET `/api/skills/playground/meta` | no request → SkillPlaygroundMetaDTO | reports injected/offline_fixture, not route readiness |
| GET `/api/system/health` | no request → HealthResponseDTO | no provider probe |

Character skill-context/meta, skill-kit/validate, character-kit/evaluate and
edited-draft validation routes are deterministic, not live entry points.
Current Character mapper: auth 502, timeout 504, rate_limit 503, config 503,
malformed response 502, and generic `ModelProviderError` maps to the typed
`PROVIDER_FAILURE` 502 response at stage `generation_provider_invocation`.
The response keeps provider/model and sanitized attempt/status/retryability
metadata; missing upstream status, retryability and usage remain null/unknown.
Unexpected app errors 500. Job timer maps BACKEND_REQUEST_TIMEOUT internally to
504 but GET remains 200. The Studio terminal-job client continues to display
non-timeout failed jobs as HTTP 503, an intentional UI abstraction over the
200 poll response and its typed error body.

Frozen target: keep offline synchronous endpoints first-class; explicit live uses
the existing job model, adding Character generation kind/routes in S1E, not S1A.
Legacy sync endpoints should reject explicit live with a clear job-required error
rather than bypass live admission. Keep current uppercase states; expiration
continues 404 and cancellation is FAILED with typed error (no extra orchestration
states). Poll endpoint must verify expected kind; job identity is operation-owned.
Capacity remains a small process-local bound shared across Character/Skill;
no automatic retry or reattachment of generated artifacts.

## S. Inspector and failure UX

`web/features/character-studio/components/AgentInspector.tsx` shows status,
pipeline, validators, repair, invocation provider/model/purpose/outcome and report
history. Failed Character jobs now expose a read-only safe diagnostics panel with
error code, workflow stage, provider/model, attempts, usage, upstream status and
retryability. `ModelInvocationDTO` already transports latency_ms, retry_count,
usage, finish_reason, tool_call_count and safe provider status/retryability.
ErrorNotice has the user-safe provider failure message and retry action.
SkillPlayground shows provider/model selection, job state, elapsed time, evidence,
transport count and outcome, but has no shared invocation/usage panel.

## S1E-F1 provider failure mapping update

`ModelProviderError` is a normalized provider invocation failure whose upstream
subtype may be unknown. It maps to `PROVIDER_FAILURE` with the safe message
`模型服务调用失败，请稍后重试。` and stage
`generation_provider_invocation`; it must not fall through to `AGENT_FAILURE`.
The generic `AGENT_FAILURE` fallback remains reserved for otherwise-unmapped
agent failures. Failed live jobs carry only allowlisted audit metadata: no
prompt, provider body, headers, credentials or stack trace. This change does not
alter routing, retry/deadline/cancellation policy, parser/recovery, Canon,
evaluation, repair, usage semantics or persistence schema (v4).
The top-level `retryable` field remains the boolean Web/UI automatic-action
policy. `provider_retryable` is a separate nullable upstream fact: when it is
unknown, the UI policy may conservatively remain `false`, but that does not
claim that the provider reported a non-retryable failure.

S1 minimum: render provider, model, attempt count, observed latency, outcome,
usage if available and error category for both success/failure, preserving repair
context. Unknown usage displays unknown, not 0. No fake progress percentage,
secrets, full prompts, raw HTTP body or traceback. Existing safe messages in M
are the user-facing contract. No streaming UI work is required.

## T. Persistence, domain and offline protection

Schema **v4 unchanged**. Secrets persisted NO; jobs persisted NO; provider registry
persisted NO; provider config persisted NO. Safe provider/model/run_id can already
occur in SkillArtifactProvenance; that is existing domain provenance, not settings
or a durable invocation history. Correcting route provenance must not rewrite
historical artifacts or change content identity.

CharacterDraft, SkillDesignArtifact, Binding, Association, CharacterKit,
Evaluation reports, Alignment and Role Coverage keep their existing schemas,
digests, approval and freshness semantics. Canon retrieval, grounding and checker
remain semantically unchanged. Runtime provider infrastructure must not inject
reference characters. Existing explicitly selected reference summaries in the
official Character CLI remain existing behavior; S1 adds no Reference Pool
conditioning or automatic reference selection (W5-S2).

Offline remains default; API key presence never turns an offline request live.
No-config Studio/Doctor and existing offline Character/Skill fixture paths remain
available with normal local prerequisites. Current Skill offline presets use
repository test fixtures and Hybrid evidence uses Git; installed no-checkout
Skill execution is not newly guaranteed by this audit. Default injected providers
are trusted test/application dependencies: an arbitrary live factory supplied to
an offline service could violate mode intent, so production route resolution must
honor explicit offline mode before constructing live clients. Explicit live
failure is typed, never silently downgraded to a fake/offline success.

## U. Cross-platform and HTTP stack

Use existing `runtime_paths.resolve_app_data_directory` for any future local
non-secret config. No new platform directory resolver. A provider config filename/
format is not introduced in S1A; S1B can remain env + injected config only.
Windows resolves LOCALAPPDATA (fallback home/AppData/Local), Linux XDG_DATA_HOME
(fallback home/.local/share), macOS home/Library/Application Support, each with
game-ai-agent suffix. `resolve_database_path`: explicit > GAME_AI_AGENT_DB_PATH
> app-data/studio.db; unchanged, never used to store provider credentials.
Paths resolve without creating directories; UTF-8 file rules stay unchanged.

Model HTTP stack is installed **OpenAI SDK** (`openai>=1.0,<3`), internally HTTPX;
httpx is also declared in dev dependencies for tests. No requests transport or
bespoke urllib model adapter. Reuse this stack for fake HTTP and production.
Do not async-convert all domain code; enforce bounded worker/client lifetimes
at the existing application/invocation boundary.

## V. Verification and future test matrix

S1C adds targeted reliability tests and requires the repository's full
collect-only/full pytest, frontend, browser, pre-commit, Postflight and clean
checkout gates. No external provider calls are permitted.

Candidate verification commands:

```powershell
py -m pre_commit run --files docs/w5_s1_production_live_provider_contract.md
py -m pytest -q tests/test_project_graph.py tests/test_project_preflight.py tests/test_project_postflight.py tests/test_ci_quality.py
git diff --check
py scripts/project_postflight.py --from-baseline
py scripts/project_postflight.py --clear-baseline
```

The task report/work log records actual results and candidate SHA; commands here
are not a substitute for execution evidence. No provider live calls are permitted.
Baseline remote CI evidence in B is separate from candidate local verification.

| Future test case | Minimum layer / existing tests to extend |
| --- | --- |
| offline fake success / structured fake success | model_factory/provider_contracts + Hybrid pipeline tests; no credentials |
| missing config / invalid capability / precedence / role selection | test_model_factory.py; no network construction or secret output |
| auth 401/403, rate limit 429, 503 unavailable, timeout, network exception | test_openai_provider.py / test_live_llm_errors.py; exact typed category and retryability |
| bad HTTP/envelope vs valid HTTP malformed domain JSON | shared transport test vs Character/Hybrid parser tests; correct failure stage and preserved audit |
| semantic validation failure and bounded repair | existing Character repair / Hybrid semantic repair tests; deterministic gates retained |
| transient retry / non-retryable / deadline/backoff | actual attempt count <=2, no nested multiplier or retry after cancellation |
| usage/latency/request ID/audit | success + failure + repair + pre-call failure + expired job; unknown fields stay null |
| secret redaction | repr(settings), provider metadata, SDK/HTTP log capture, exception, CLI, Web error, graph and SQLite boundaries with synthetic secret only |
| offline preservation | explicit offline wins despite configured key; no-config Studio/Doctor; live config error never becomes fake success |
| concurrency/cancellation | delayed worker, timeout then resubmit, queue expiry, shutdown during active call, late result ignored, kind mismatch, capacity held until actual completion |
| Web / Inspector | explicit live→202→poll result/error; stable domain result; safe category/attempt/usage; no browser endpoint override |

Use a small stdlib localhost fake HTTP server for real SDK HTTP serialization,
Authorization header checks with a synthetic token, response parsing, 429/503,
delays, malformed bodies and connection close; complements injected doubles and
needs no new HTTP dependency. Keep tests offline/local only; “CI network calls 0”
means **external model-provider calls 0**, not package downloads or loopback fake
HTTP. No GitHub Actions API key dependency. Real provider verification is manual,
explicitly authorized integration probe only, with frozen route/limits and safe
metadata; not executed in S1A. Quality/model behavior studies are separate evidence.

## W. Production readiness scorecard

| Area | Status | Evidence / boundary |
| --- | --- | --- |
| provider abstraction | PARTIAL | Shared `ProviderChatClient` exists; Hybrid path still carries a parallel policy seam |
| routing | IMPLEMENTED | `ProviderRoute` resolves five server-owned operation roles with trusted precedence and request mismatch rejection |
| secret handling | IMPROVED | `LiveLLMSettings` redacts credentials in `repr`/`str`; endpoint credentials are rejected; remaining SDK logging risk is deferred |
| timeouts | IMPLEMENTED | One monotonic operation deadline caps provider, adapter, workflow and job attempts |
| retry | IMPLEMENTED | Shared bounded attempt policy and cancellation-aware backoff cap transient retries |
| errors | IMPLEMENTED | Provider, reliability, Hybrid and Web layers preserve safe typed categories |
| async jobs | PARTIAL | Skill jobs are process-local and TTL-bounded; Character public async routes remain S1E |
| cleanup | IMPLEMENTED | Timeout/cancel suppresses publication while physical workers settle before capacity is released |
| concurrency | IMPLEMENTED | Admission counts unsettled physical workers, including timed-out work |
| structured output | IMPROVED | Hybrid negotiates its contract against the resolved route profile capabilities |
| invocation audit | PARTIAL | `ModelInvocationAudit` records core attempts; Hybrid and some repair failures omit it |
| usage/cost | MISSING | Usage can be nullable on completions; no durable usage or pricing contract |
| doctor | READY | Configuration presence only, no live call, no secret values |
| frontend errors | PARTIAL | Safe job error envelope exists; Inspector does not render all audit/usage fields |
| offline compatibility | READY | Explicit offline mode remains default and is tested |
| CI / cross-platform | READY | Local quality gates and runtime path contract cover committed docs/runtime paths |

## X. Implementation slices and ownership

| Slice | Small deliverable / acceptance boundary | Owner |
| --- | --- | --- |
| W5-S1B — Production Provider Runtime & Configuration | evolve settings/profile/ProviderChatClient; separate secret values from repr/export; resolved provider/model route; canonical config precedence and capability validation; fake tests | Codex |
| W5-S1C — Shared Error / Retry / Timeout / Audit Policy | one invocation policy on existing boundary; typed taxonomy; bounded retry/deadline and failure audit; SDK malformed-envelope/local HTTP checks; physical job lifecycle | Codex |
| W5-S1D — Character / Skill / Repair Integration | remaining shared policy/audit and taxonomy work after S1B route wiring | Codex |
| W5-S1E — Web Job + Inspector Productionization | reuse registry, Character job support, effective worker admission/shutdown, safe HTTP mapping, server routing, finite polling/failure metadata | Codex |

Each slice requires its own Preflight, bounded tests, Postflight and reviewable
commit. If S1C or E spans too much, split invocation policy from lifetime handling
within that slice before editing; do not bundle model research into runtime code.
S1B and S1C implementation are complete in their candidate commits; S1D–E remain separate slices.

## Y. Deferred

Streaming/SSE/WebSocket/token output: DEFERRED; async final-result jobs suffice.
Monetary cost/pricing, usage history, persistent jobs, provider registry DB,
distributed queue/cancellation, global rate limiter, arbitrary browser overrides,
new vendor SDK/Responses/Anthropic transport, fine-tuning: DEFERRED.
Reference Character Pool conditioning: W5-S2. Multi-Agent Judge: W5-S4.
Do not expand S1 into either. No schema v5 for jobs.

## Z. Engineering Knowledge postflight

Graph changed: **NO**. Run against this task's captured baseline, never whole-tree
fallback. Required task verdict **IN_SYNC**, while separately retaining the C
snapshot warnings. A missing/mismatched baseline requires recapture; a
KNOWLEDGE_UPDATE_REQUIRED verdict requires explanation/review before completion.
Clear the task baseline after verification. Future contract design here does not
automatically update graph nodes, decisions, limitations or lifecycle status.

## AA. Git and next

One commit: `feat: harden live invocation reliability`. Stage only the S1C
implementation, tests and this contract update. Commit SHA, clean verification
and work-log location belong in the task completion report. Primary workspace
remains untouched. Push **NO**; tag **NO**.

## Appendix 1. Exhaustive source symbol and call-site index

This static index covers the committed Python tree, including nested test doubles.
Class declarations with complete/generate/create methods and live-adapter subclasses
are listed; forwarding agents are identified as glue, not additional transports.
For test-only entries, the enclosing test function/module is the caller. Fake SDK
create methods are transport doubles. Functions/lambdas used as repair callbacks
are caller-supplied behavior; they do not constitute an installed provider client.

| Source locator | Symbol | Boundary / responsibility | Status |
| --- | --- | --- | --- |
| `evals/character_skill_s2_shadow_evidence.py:577` | `ShadowEvidenceModelRouter` | model/client boundary: generate | PILOT_ONLY |
| `evals/character_skill_s2_shadow_evidence.py:3566` | `_MinimalTransportAdapter` | model/client boundary: inherited | PILOT_ONLY |
| `evals/character_skill_s2_shadow_evidence.py:3905` | `_FullInputTinyOutputAdapter` | model/client boundary: inherited | PILOT_ONLY |
| `scripts/audit_live_character_authoring_latency.py:647` | `_InstrumentedModel` | model/client boundary: generate | PILOT_ONLY |
| `scripts/audit_live_character_authoring_latency.py:716` | `_InstrumentedGenerationAgent` | forwarder/domain agent | PILOT_ONLY |
| `scripts/demo_character_repair_v0_1.py:52` | `_FixtureGenerationAgent` | forwarder/domain agent | PILOT_ONLY |
| `src/agents/character_generation.py:1995` | `CharacterGenerationAgent` | forwarder/domain agent | runtime seam / see D |
| `src/agents/character_generation.py:3006` | `DeterministicCharacterGenerationModel` | model/client boundary: generate | offline/test runtime |
| `src/agents/character_repair.py:699` | `DeterministicCharacterRepairModel` | model/client boundary: generate | offline/test runtime |
| `src/agents/demo_model.py:10` | `DeterministicDemoModel` | model/client boundary: generate | offline/test runtime |
| `src/agents/live_llm.py:60` | `LiveLLMAdapter` | model/client boundary: generate | runtime seam / see D |
| `src/agents/model_protocol.py:9` | `AgentModel` | model/client boundary: generate | runtime seam / see D |
| `src/agents/model_protocol.py:15` | `ScriptedAgentModel` | model/client boundary: generate | offline/test runtime |
| `src/agents/official_character_authoring.py:148` | `_RecordingGenerationAgent` | forwarder/domain agent | runtime seam / see D |
| `src/agents/openai_provider.py:20` | `OpenAIChatClient` | model/client boundary: complete | runtime seam / see D |
| `src/agents/provider_protocol.py:98` | `ProviderChatClient` | model/client boundary: complete | runtime seam / see D |
| `src/character_intelligence/hybrid_ir/runner.py:179` | `HybridProvider` | model/client boundary: complete | runtime seam / see D |
| `src/character_intelligence/hybrid_ir/runner.py:200` | `OpenCodeGoHybridProvider` | model/client boundary: complete | runtime seam / see D |
| `src/character_intelligence/hybrid_ir/runner.py:394` | `FakeProvider` | model/client boundary: complete | offline/test runtime |
| `src/web/services/character_generation.py:37` | `_RecordingGenerationAgent` | forwarder/domain agent | runtime seam / see D |
| `src/web/services/character_generation.py:53` | `CharacterGenerationApplication` | forwarder/domain agent | runtime seam / see D |
| `tests/test_character_authoring_latency_audit.py:107` | `ScriptedModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_authoring_latency_audit.py:284` | `test_conditional_repair_adds_one_repair_invocation_and_final_check.RepairingModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_authoring_latency_audit.py:333` | `test_failure_returns_sanitized_partial_audit_without_exception_text.FailingModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_authoring_latency_audit.py:422` | `test_invalid_api_retrieval_strategy_fails_before_model_or_provider.ExplodingModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_deterministic_retrieval.py:61` | `FakeProviderClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_character_draft_recovery.py:219` | `test_failed_recovery_audit_uses_sanitized_diagnostic.RecoveryFailureModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_generation.py:449` | `FakeProviderClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_character_repair.py:168` | `_StaticGenerationAgent` | forwarder/domain agent | TEST_ONLY |
| `tests/test_character_repair_redteam.py:195` | `test_hidden_authority_triggers_repair_workflow.StaticGenerator` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_enum_stepdown.py:14` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_enum_stepdown.py:81` | `test_l1_timeout_is_unavailable_without_retry.TimeoutModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_integration_gate.py:172` | `_GateShadowModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_nested_shape_stepdown.py:14` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_nested_shape_stepdown.py:82` | `test_l2_timeout_is_unavailable_without_retry.TimeoutModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_shadow_evidence.py:52` | `_CandidateModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_shadow_evidence.py:67` | `_MalformedModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_s2_shadow_evidence.py:74` | `_WireClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_character_skill_shadow_generation.py:46` | `_ShadowModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_shadow_generation.py:65` | `_RecoveryProbeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_character_skill_shape_diagnostics.py:136` | `_DiagnosticModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_compact_model_facing_contract_v2.py:88` | `test_v2_live_fake_observation_is_single_and_sanitized.FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_compact_model_facing_contract_v2.py:121` | `test_v2_complete_cohort_blocks_second_sample.CompleteModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_deepseek_provider.py:45` | `FakeDeepSeekClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_fixed_contract_compliance_cohort.py:28` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_full_input_tiny_output.py:15` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_full_input_tiny_output.py:95` | `test_timeout_is_unavailable_and_not_retried.TimeoutModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_grounding.py:187` | `RecordingModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_hybrid_formal_live_executor.py:93` | `CountingProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_hybrid_formal_live_executor.py:117` | `test_shared_opencode_transport_adapter_is_single_attempt_and_json_object.Client` | model/client boundary: complete | TEST_ONLY |
| `tests/test_hybrid_formal_live_executor.py:138` | `test_shared_opencode_transport_adapter_maps_timeout_without_raw_error.Client` | model/client boundary: complete | TEST_ONLY |
| `tests/test_live_llm_adapter.py:135` | `FakeProviderClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_live_llm_errors.py:44` | `ErrorFakeClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_live_web_execution.py:33` | `DelayedProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_live_web_execution.py:46` | `TimeoutProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_minimal_transport_sanity.py:15` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_minimal_transport_sanity.py:104` | `test_timeout_is_unavailable_without_retry.TimeoutModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_model_factory.py:18` | `NeverCalledClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_model_suitability_probe.py:25` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_official_character_authoring.py:79` | `test_demo_does_not_turn_a_failed_checker_result_into_pass.StaticGenerationAgent` | forwarder/domain agent | TEST_ONLY |
| `tests/test_official_character_authoring.py:113` | `test_scope_violation_is_not_presented_as_applied_or_accepted.StaticGenerationAgent` | forwarder/domain agent | TEST_ONLY |
| `tests/test_openai_provider.py:17` | `FakeCompletions` | SDK completion double | TEST_ONLY |
| `tests/test_provider_contracts.py:250` | `ContractClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_skill_playground.py:187` | `test_evaluator_fail_can_use_one_bounded_repair.SequenceProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_skill_playground.py:223` | `test_chinese_fake_e2e_localizes_presentation_but_keeps_protocol_values.CaptureProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_skill_playground.py:296` | `test_repair_inherits_chinese_language_without_translation_call.SequenceProvider` | model/client boundary: complete | TEST_ONLY |
| `tests/test_skill_playground.py:417` | `test_provider_unavailable_is_safe_and_does_not_repair.Unavailable` | model/client boundary: complete | TEST_ONLY |
| `tests/test_timeout_suitability_probe.py:27` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_timeout_suitability_probe.py:51` | `_FakeClient` | model/client boundary: complete | TEST_ONLY |
| `tests/test_v2_minimal_skillkit.py:49` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_v2_output_stepdown_o1.py:28` | `_FakeModel` | model/client boundary: generate | TEST_ONLY |
| `tests/test_web_api.py:149` | `_ExplodingModel` | model/client boundary: generate | TEST_ONLY |

### Live-capable call sites and forwarding entry points

Every non-test direct generate/complete call and recognized live factory construction
is below. This includes offline-capable forwarding calls; the resolved mode/factory
determines whether they reach HTTP. The sole SDK network sink is explicitly listed.

| Source locator | Enclosing symbol / caller | Called symbol |
| --- | --- | --- |
| `evals/character_skill_s2_shadow_evidence.py:613` | `ShadowEvidenceModelRouter.generate` | `self.legacy_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:619` | `ShadowEvidenceModelRouter.generate` | `self.shadow_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:1702` | `ShadowEvidenceRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:1730` | `ShadowEvidenceRunner.run` | `agent.generate` |
| `evals/character_skill_s2_shadow_evidence.py:2077` | `RetryUnavailableCohortRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:2098` | `RetryUnavailableCohortRunner.run` | `agent.generate` |
| `evals/character_skill_s2_shadow_evidence.py:2326` | `ShapeDiagnosticCohortRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:2351` | `ShapeDiagnosticCohortRunner.run` | `agent.generate` |
| `evals/character_skill_s2_shadow_evidence.py:3283` | `TimeoutSuitabilityProbeRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:3296` | `TimeoutSuitabilityProbeRunner.run` | `agent.generate` |
| `evals/character_skill_s2_shadow_evidence.py:3507` | `ModelSuitabilityProbeRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:3520` | `ModelSuitabilityProbeRunner.run` | `agent.generate` |
| `evals/character_skill_s2_shadow_evidence.py:3776` | `MinimalTransportSanityRunner.run` | `OpenAIChatClient` |
| `evals/character_skill_s2_shadow_evidence.py:3796` | `MinimalTransportSanityRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:4133` | `FullInputTinyOutputRunner.run` | `OpenAIChatClient` |
| `evals/character_skill_s2_shadow_evidence.py:4138` | `FullInputTinyOutputRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:4473` | `EnumExpansionStepdownRunner.run` | `OpenAIChatClient` |
| `evals/character_skill_s2_shadow_evidence.py:4482` | `EnumExpansionStepdownRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:4819` | `NestedShapeStepdownRunner.run` | `OpenAIChatClient` |
| `evals/character_skill_s2_shadow_evidence.py:4828` | `NestedShapeStepdownRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:5609` | `OutputStepdownRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:5625` | `OutputStepdownRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:5897` | `CompactContractV2Runner.run` | `OpenAIChatClient` |
| `evals/character_skill_s2_shadow_evidence.py:5906` | `CompactContractV2Runner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:6069` | `MinimalSkillKitRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:6090` | `MinimalSkillKitRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:6385` | `O1SafeDiagnosticRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:6397` | `O1SafeDiagnosticRunner.run` | `provider_model.generate` |
| `evals/character_skill_s2_shadow_evidence.py:6698` | `O2LocalStructureRunner.run` | `character_model_from_environment` |
| `evals/character_skill_s2_shadow_evidence.py:6708` | `O2LocalStructureRunner.run` | `provider_model.generate` |
| `scripts/audit_live_character_authoring_latency.py:656` | `_InstrumentedModel.generate` | `self.delegate.generate` |
| `scripts/audit_live_character_authoring_latency.py:724` | `_InstrumentedGenerationAgent.generate` | `self.delegate.generate` |
| `scripts/audit_live_character_authoring_latency.py:824` | `audit_live_character_authoring` | `character_model_from_environment` |
| `scripts/demo_character_generation_v0_1.py:31` | `main` | `character_model_from_environment` |
| `scripts/demo_character_generation_v0_1.py:39` | `main` | `CharacterGenerationAgent(model).generate` |
| `scripts/demo_character_repair_v0_1.py:73` | `main` | `character_model_from_environment` |
| `scripts/demo_npc_agent_v0_1.py:46` | `main` | `model_from_environment` |
| `scripts/run_character_generation_evals.py:68` | `main` | `CharacterGenerationAgent(DeterministicCharacterGenerationModel(), resolver=resolver).generate` |
| `scripts/run_character_generation_evals.py:82` | `main` | `CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(tool_calls=(ToolCall('x', 'write_character', {}),))])).generate` |
| `scripts/run_character_generation_evals.py:90` | `main` | `CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL), ModelTurn(text=json.dumps(_payload(story_link={'target_id': 'incident_999', 'relation': 'related_context', 'status': 'canon_backed'}), ensure_ascii=False))])).generate` |
| `scripts/run_character_generation_evals.py:101` | `main` | `CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL), ModelTurn(text=json.dumps(_payload(proposed_new_content=['秘密政府组织']), ensure_ascii=False))])).generate` |
| `scripts/run_character_generation_evals.py:112` | `main` | `CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL), ModelTurn(text=json.dumps(_payload(faction_id='faction_999'), ensure_ascii=False))])).generate` |
| `scripts/run_character_generation_evals.py:123` | `main` | `CharacterGenerationAgent(ScriptedAgentModel([ModelTurn(text=CHARACTER_AUTHORING_ACTION_FINALIZE_SIGNAL), ModelTurn(text=json.dumps({'age': 'twenty three'}))])).generate` |
| `scripts/skill_playground.py:354` | `execute_playground` | `provider.complete` |
| `scripts/skill_playground.py:594` | `main` | `_default_hybrid_provider_factory` |
| `src/agents/character_generation.py:2088` | `CharacterGenerationAgent.generate` | `self.model.generate` |
| `src/agents/character_generation.py:2176` | `CharacterGenerationAgent.generate` | `self.model.generate` |
| `src/agents/character_generation.py:2302` | `CharacterGenerationAgent._run_deterministic_retrieval` | `self.model.generate` |
| `src/agents/character_generation.py:2492` | `CharacterGenerationAgent._generate_skill_shadow` | `self.model.generate` |
| `src/agents/character_generation.py:2645` | `CharacterGenerationAgent.generate_with_intent` | `self.generate` |
| `src/agents/character_generation.py:2756` | `CharacterGenerationAgent._recover_character_draft_payload` | `self.model.generate` |
| `src/agents/character_repair.py:495` | `CharacterRepairAgent.repair` | `self.model.generate` |
| `src/agents/character_repair.py:682` | `CharacterAuthoringWorkflow.run` | `self.generation_agent.generate` |
| `src/agents/live_llm.py:127` | `LiveLLMAdapter.generate` | `self._client.complete` |
| `src/agents/model_factory.py:125` | `model_from_environment` | `OpenAIChatClient` |
| `src/agents/model_factory.py:131` | `model_from_environment` | `LiveLLMAdapter` |
| `src/agents/model_factory.py:164` | `character_model_from_environment` | `OpenAIChatClient` |
| `src/agents/model_factory.py:170` | `character_model_from_environment` | `LiveLLMAdapter` |
| `src/agents/npc_agent.py:117` | `NpcConversationAgent.chat` | `self.model.generate` |
| `src/agents/npc_agent.py:298` | `NpcConversationAgent._repair_once` | `self.model.generate` |
| `src/agents/official_character_authoring.py:156` | `_RecordingGenerationAgent.generate` | `self.delegate.generate` |
| `src/agents/official_character_authoring.py:443` | `make_demo` | `character_model_from_environment` |
| `src/agents/openai_provider.py:104` | `OpenAIChatClient.complete` | `self._client.chat.completions.create` |
| `src/character_intelligence/hybrid_ir/runner.py:238` | `OpenCodeGoHybridProvider.complete` | `self._client.complete` |
| `src/character_intelligence/hybrid_ir/runner.py:557` | `_run_pipeline` | `provider.complete` |
| `src/character_intelligence/hybrid_ir/runner.py:876` | `_default_hybrid_provider_factory` | `OpenAIChatClient` |
| `src/character_intelligence/hybrid_ir/runner.py:919` | `live_hybrid_provider_from_environment` | `OpenAIChatClient` |
| `src/web/routes/characters.py:89` | `generate` | `_service(request).generate` |
| `src/web/services/character_generation.py:46` | `_RecordingGenerationAgent.generate` | `self.delegate.generate` |
| `src/web/services/character_generation.py:72` | `CharacterGenerationApplication.__init__` | `character_model_from_environment` |
| `src/web/services/skill_playground.py:211` | `SkillPlaygroundApplication.provider_for` | `live_hybrid_provider_from_environment` |

## Appendix 2. Search coverage and research configuration

The broad usage scan was rerun with `git grep -l -I -i -E` over the tracked tree,
using all 18 requested terms (442 matching tracked files). Matches in packaged lore/reference source URLs,
JSON evidence, CSS, package locks and graph prose are not executable provider
implementations. Follow-up Python AST and transport/factory caller scans above
cover execution, and J covers the application configuration loader.

Historical eval-only configurations in `evals/character_skill_s2_shadow_evidence.py`
are literal experiment contracts, not new production defaults. Actual scalar
provider/model/timeout/retry/transport constants are indexed here:

| Constant | Pinned value |
| --- | --- |
| `PROVIDER_NAME` | `opencode_go` |
| `MODEL_REQUESTED` | `deepseek-v4-flash` |
| `TRANSPORT` | `openai_chat_completions` |
| `STRUCTURED_OUTPUT_MODE` | `json_object` |
| `TIMEOUT_SECONDS` | `30` |
| `MAX_TRANSPORT_RETRIES` | `2` |
| `TIMEOUT_SUITABILITY_PROVIDER` | `opencode_go` |
| `TIMEOUT_SUITABILITY_MODEL` | `deepseek-v4-flash` |
| `TIMEOUT_SUITABILITY_TRANSPORT` | `openai_chat_completions` |
| `TIMEOUT_SUITABILITY_STRUCTURED_OUTPUT_MODE` | `json_object` |
| `TIMEOUT_SUITABILITY_TIMEOUT_SECONDS` | `60` |
| `TIMEOUT_SUITABILITY_MAX_TRANSPORT_RETRIES` | `2` |
| `MODEL_SUITABILITY_PROVIDER` | `opencode_go` |
| `MODEL_SUITABILITY_MODEL` | `deepseek-v4-pro` |
| `MODEL_SUITABILITY_TRANSPORT` | `openai_chat_completions` |
| `MODEL_SUITABILITY_STRUCTURED_OUTPUT_MODE` | `json_object` |
| `MODEL_SUITABILITY_TIMEOUT_SECONDS` | `60` |
| `MODEL_SUITABILITY_MAX_TRANSPORT_RETRIES` | `2` |
| `MINIMAL_TRANSPORT_SANITY_PROVIDER` | `opencode_go` |
| `MINIMAL_TRANSPORT_SANITY_MODEL` | `deepseek-v4-pro` |
| `MINIMAL_TRANSPORT_SANITY_TRANSPORT` | `openai_chat_completions` |
| `MINIMAL_TRANSPORT_SANITY_STRUCTURED_OUTPUT_MODE` | `json_object` |
| `MINIMAL_TRANSPORT_SANITY_TIMEOUT_SECONDS` | `60` |
| `MINIMAL_TRANSPORT_SANITY_MAX_TRANSPORT_RETRIES` | `0` |
| `FULL_INPUT_TINY_OUTPUT_PROVIDER` | `opencode_go` |
| `FULL_INPUT_TINY_OUTPUT_MODEL` | `deepseek-v4-pro` |
| `FULL_INPUT_TINY_OUTPUT_TIMEOUT_SECONDS` | `60` |
| `FULL_INPUT_TINY_OUTPUT_MAX_TRANSPORT_RETRIES` | `0` |
| `ENUM_STEPOWDOWN_PROVIDER` | `opencode_go` |
| `ENUM_STEPOWDOWN_MODEL` | `deepseek-v4-pro` |
| `ENUM_STEPOWDOWN_TIMEOUT_SECONDS` | `60` |
| `ENUM_STEPOWDOWN_MAX_TRANSPORT_RETRIES` | `0` |
| `NESTED_SHAPE_STEPOWDOWN_PROVIDER` | `opencode_go` |
| `NESTED_SHAPE_STEPOWDOWN_MODEL` | `deepseek-v4-pro` |
| `NESTED_SHAPE_STEPOWDOWN_TIMEOUT_SECONDS` | `60` |
| `NESTED_SHAPE_STEPOWDOWN_MAX_TRANSPORT_RETRIES` | `0` |
| `COMPACT_V2_PROVIDER` | `opencode_go` |
| `COMPACT_V2_MODEL` | `deepseek-v4-pro` |
| `COMPACT_V2_TIMEOUT_SECONDS` | `60` |
| `COMPACT_V2_MAX_TRANSPORT_RETRIES` | `0` |
| `MINIMAL_SKILLKIT_PROVIDER` | `opencode_go` |
| `MINIMAL_SKILLKIT_MODEL` | `deepseek-v4-pro` |
| `MINIMAL_SKILLKIT_TIMEOUT_SECONDS` | `60` |
| `MINIMAL_SKILLKIT_MAX_TRANSPORT_RETRIES` | `0` |
| `O1_ROOT_ONLY_PROVIDER` | `opencode_go` |
| `O1_ROOT_ONLY_MODEL` | `deepseek-v4-pro` |
| `O1_ROOT_ONLY_TIMEOUT_SECONDS` | `60` |
| `O1_ROOT_ONLY_MAX_TRANSPORT_RETRIES` | `0` |

Historical pilot models/timeout settings above must not be copied into runtime
role selection. `ShadowEvidenceModelRouter` preserves offline Character work while
calling the selected live shadow model; tiny diagnostic subclasses reuse transport
and ModelInvocationAudit but deliberately bypass normal domain output parsing.
# W5-S1D Invocation Audit and Usage Contract

The production boundary records one `ModelInvocationAudit` per logical model
invocation. Retries remain inside that record as ordered, typed attempt
summaries (`attempt_number`, outcome/error code, latency, safe request ID,
finish reason, and usage). `retry_count` is retained as the number of retries
for compatibility; it is never a substitute for the attempt list.

Usage is optional and normalized at the provider seam. Invalid, negative, or
boolean token values become unknown. Aggregation sums only reported fields and
never converts unknown or partial data to zero or derives `total_tokens` from
input plus output. A zero-invocation summary is explicitly empty; a summary
with missing or partial provider usage is marked incomplete.

The Web projection is an explicit allowlist: provider/model, purpose, outcome,
latency, retries, safe provider request ID, finish reason, tool-call count,
typed attempts, and usage summary. Prompts, raw request/response bodies,
headers, credentials, cookies, costs, and secrets are never projected or
persisted. Character generation, repair/recovery, Hybrid skill generation,
success, retry exhaustion, malformed response, cancellation, deadline, and
configuration/capability failures preserve the audit when an invocation object
exists. Offline fixtures report zero model invocations and do not invent a
fake usage record.

# W5-S1E Live Web Contract

Character live generation uses the existing `LiveJobRegistry` through
`POST /api/characters/generate/jobs` and
`GET /api/characters/generate/jobs/{job_id}`. The worker calls the existing
Character generation application, including structural recovery, Canon,
evaluation, and repair, then serializes the normal
`web-character-generation/0.1` response. The existing synchronous
`POST /api/characters/generate` endpoint remains for offline/manual callers.

Skill Playground and Character live jobs share the same process-local registry,
bounded capacity, terminal states (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`),
90-second server budget, 900-second terminal TTL, and 1500 ms poll hint. The
browser waits at most 120 seconds, stops on terminal or unknown jobs, and does
not claim that client timeout cancelled the provider. Backend restart loses
ephemeral jobs; the browser receives a safe expired-job error and can submit a
new explicit request.

The Character Studio keeps offline generation unchanged and adds an explicit
offline/live mode choice. Live submission disables Generate while active and
uses the shared bounded polling helper. Provider and model remain backend-owned;
the browser cannot route a request or provide credentials. Live job IDs,
deadlines, worker state, audit, and usage are transient and are not persisted
in Character, Skill, CharacterKit, or schema v4 storage.

S1E local acceptance uses fake or local fixtures only. Production live-provider
acceptance is a separate post-remote-green step and is not part of this
candidate.

## Safe upstream provider failure metadata

Provider failures may expose only this nullable allowlist when the
OpenAI-compatible SDK supplies the fields structurally: `upstream_status`,
`upstream_error_type`, `upstream_error_code`, `upstream_error_param`, and
`provider_request_id`. Values are bounded printable scalars; unknown or unsafe
values remain `null`. The adapter never projects raw response bodies, error
messages, headers, credentials, request payloads, prompts, tool payloads, or
stack traces. HTTP status remains the upstream status even when the Web layer
maps the failure to HTTP 502/503.
