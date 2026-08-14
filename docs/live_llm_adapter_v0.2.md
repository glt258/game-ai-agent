# Live LLM Adapter v0.2

## Purpose

v0.2 lets the existing NPC conversation runtime select either its deterministic
offline model or one live OpenAI-compatible Chat Completions endpoint. v0.2.1
adds `deepseek` as a first-class provider configuration without adding another
Agent adapter.
It does not give the model new authority. The external model remains an
untrusted planner and renderer inside the existing read-only runtime.

```text
ConversationSession
        |
        v
NpcConversationAgent --> AgentModel
        |                  |-- DeterministicDemoModel
        |                  `-- LiveLLMAdapter --> ProviderChatClient
        v
KnowledgeToolbox (fixed definitions + runtime validation)
        |
        v
KnowledgeResolver --> safe tool observation --> grounding validation
```

`NpcConversationAgent` depends only on `AgentModel`. `LiveLLMAdapter` knows only
safe prompts, allowed tool definitions, provider configuration, and an injected
`ProviderChatClient`. It has no Lore repository, Character database,
`StoryRuntime`, `StoryState`, resolver, or tool execution capability.

## Model selection

Offline remains the default and needs no API key or network:

```powershell
py scripts\demo_npc_agent_v0_1.py
py scripts\demo_npc_agent_v0_1.py --model offline
```

Live mode fails fast when its model or key is absent:

```powershell
$env:NPC_AGENT_MODEL = "live"
$env:NPC_LLM_PROVIDER = "openai"
$env:NPC_LLM_MODEL = "<model-id>"
$env:NPC_LLM_API_KEY = "<secret>"
py scripts\demo_npc_agent_v0_1.py
```

DeepSeek uses the same configuration interface and does not require a manual
Base URL:

```powershell
$env:NPC_AGENT_MODEL = "live"
$env:NPC_LLM_PROVIDER = "deepseek"
$env:NPC_LLM_MODEL = "<deepseek-model-id>"
$env:NPC_LLM_API_KEY = "<secret>"
py scripts\demo_npc_agent_v0_1.py
```

`--model live` can override `NPC_AGENT_MODEL` for the demo. There is no silent
fallback from live to offline. The live demo runs all four existing scenarios
and can make multiple paid requests; use the optional smoke test below for one
minimal request.

## Configuration

| Variable | Required | Default | Meaning |
|---|---:|---:|---|
| `NPC_AGENT_MODEL` | no | `offline` | `offline` or `live` |
| `NPC_LLM_PROVIDER` | live | `openai` | `openai` or `deepseek` |
| `NPC_LLM_MODEL` | live | none | Provider model ID; non-empty |
| `NPC_LLM_API_KEY` | live | none | Secret read from process environment |
| `NPC_LLM_BASE_URL` | no | provider default | Absolute HTTP(S) compatible endpoint |
| `NPC_LLM_TIMEOUT_SECONDS` | no | `30` | Request timeout, from 1 to 300 seconds |
| `NPC_LLM_MAX_RETRIES` | no | `2` | Additional retries, from 0 to 3 |

For `deepseek`, the default Base URL is `https://api.deepseek.com`. An explicit
`NPC_LLM_BASE_URL` always overrides that default for a proxy, gateway, or local
compatible endpoint. The model ID is always supplied by `NPC_LLM_MODEL`; the
factory does not guess or hardcode one.

`.env` and `.env.*` are ignored. `.env.example` contains placeholders only;
the project does not load it automatically or add a dotenv dependency.

## Provider translation

The runtime supplies `ToolDefinition` objects. The adapter translates exactly
those definitions to function schemas; it keeps no second hidden tool list.
The current definitions are `search_lore` and `get_lore`.

For every provider tool call the adapter:

1. preserves the provider call ID, or creates request-local `call_1`, `call_2` IDs;
2. parses string JSON or accepts an object;
3. rejects malformed JSON and non-object arguments without guessing repairs;
4. returns the internal `ToolCall` to `NpcConversationAgent`;
5. lets `KnowledgeToolbox` enforce the whitelist and strict argument rules;
6. sends only the sanitized tool observation back with the matching call ID.

The provider schema is guidance. Runtime validation and `KnowledgeResolver` are
the actual security boundaries.

DeepSeek's current thinking mode defaults to enabled and requires
`reasoning_content` to be preserved after tool calls. v0.2.1 intentionally does
not add that provider-specific state to `ModelTurn` or conversation history.
The shared OpenAI-compatible transport therefore sends
`extra_body={"thinking":{"type":"disabled"}}` only for logical provider
`deepseek`, selecting normal tool-calling mode. OpenAI requests are unchanged.

## Grounding and session behavior

Successful Lore IDs in current-turn tool observations become the live turn's
candidate source IDs. The existing runtime verifies that every candidate was
actually returned during that turn before committing the response. Denied
observations contain only status, a generic reason code, and the requested ID.

Assistant tool requests and matching tool results are now represented in the
internal conversation history. The runtime still commits user/tool/assistant
messages only after a final grounded response. Provider failures, malformed
responses, and loop-limit failures do not leave partial conversation messages.
Each `ConversationSession` owns its own messages and model audit; the adapter
has no conversation cache.

This preserves the v0.1 grounding limitation: the runtime validates Lore source
provenance, but it is not a semantic contradiction or arbitrary-prose Canon
checker.

## Error and retry policy

The OpenAI SDK has its automatic retries disabled. `LiveLLMAdapter` owns one
bounded retry policy with exponential delays of 0.5, 1, and 2 seconds as
applicable.

Retried:

- timeout;
- transient connection failure;
- rate limit (429);
- provider 5xx.

Not retried:

- authentication failure;
- non-retryable provider 4xx;
- malformed provider output;
- invalid tool arguments;
- permission denial;
- grounding failure.

Provider exceptions become `ModelAuthenticationError`, `ModelTimeoutError`,
`ModelRateLimitError`, `ModelProviderError`, or
`ModelMalformedResponseError`. Their messages do not include raw provider
headers, credentials, or request bodies.

## Observability

Each successful invocation is stored as `ModelInvocationAudit` on both the
response and its `ConversationSession`. It contains provider, model, session,
turn, outcome, monotonic latency, retry count, finish reason, tool-call count,
provider-reported token usage, and provider request ID. Failures emit the same
safe operational metadata to the logger.

Logs do not include the system prompt, conversation, tool observations, Lore
content, authorization headers, API key, or environment dump.

## Tests

Normal tests use injected fake clients and never call the network:

```powershell
py -m pytest
py scripts\run_npc_agent_evals.py
```

The optional smoke test is skipped unless explicitly enabled. It may incur API
cost:

```powershell
$env:NPC_RUN_LIVE_SMOKE = "1"
$env:NPC_AGENT_MODEL = "live"
$env:NPC_LLM_PROVIDER = "deepseek"
$env:NPC_LLM_MODEL = "<model-id>"
$env:NPC_LLM_API_KEY = "<secret>"
py -m pytest -m live tests\test_live_smoke.py
```
