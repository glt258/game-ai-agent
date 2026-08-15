# OpenCode Go Provider Contract Research

核对日期：2026-08-15

范围：OpenCode Go 的 Base URL、认证、模型与 transport 路由，以及 structured output、tool calling、thinking 对 Provider layer 的影响。只使用 OpenCode/Anomaly、协议所有者和所用官方 SDK 的一手资料；未进行付费 live call。

## 实现结论

1. OpenCode Go 的 SDK Base URL 是 `https://opencode.ai/zen/go/v1`。具体请求路径由模型决定，不能把所有模型都送到 `/chat/completions`。[OpenCode Go — Endpoints](https://opencode.ai/docs/go/#endpoints)
2. OpenCode Go 文档中的模型 ID 是裸 ID，例如 `deepseek-v4-flash`。`opencode-go/deepseek-v4-flash` 只是在 OpenCode 自身配置中的 `provider/model` 写法；直接调用 Gateway 时仍发送裸 ID。[OpenCode Go — Endpoints](https://opencode.ai/docs/go/#endpoints)
3. `GET https://opencode.ai/zen/go/v1/models` 是当前可用 ID 的动态发现端点，但响应只有 `id/object/created/owned_by`，没有 transport 或能力元数据。因此它不能替代集中、经过验证的 model profile；未知模型必须要求显式 transport override，不能默认成 Chat Completions。[OpenCode Go — Models](https://opencode.ai/docs/go/#models)、[live model discovery endpoint](https://opencode.ai/zen/go/v1/models)
4. 当前公开路由同时包含 OpenAI Chat Completions、OpenAI Responses 和 Anthropic Messages 三个不同协议族。它们的消息、工具调用与结构化输出字段不同；现有 Chat Completions client 不能安全地冒充另外两个 transport。[OpenCode Go — Endpoints](https://opencode.ai/docs/go/#endpoints)
5. 对本仓库当前范围，完整实现并 contract-test Chat Completions；把 Responses/Messages 识别为 transport family，但在有独立 adapter 与 contract tests 之前 fail fast，是符合官方资料的保守边界。
6. OpenCode 的 rich catalog 可以作为 capability/profile 的一手元数据来源，但 `structured_output: true` 只是粗粒度能力标记，不说明 Gateway 接受 `json_object`、OpenAI `json_schema`，还是 Anthropic `output_config.format`。OpenCode 当前导入 catalog 时也没有把该字段映射成 Runtime capability。不能据此给所有兼容模型自动开启 OpenAI strict JSON Schema。[OpenCode model catalog](https://models.opencode.ai/api.json)、[OpenCode catalog importer](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/opencode/src/provider/provider.ts#L1212-L1258)

## Base URL 与认证

| Transport | SDK Base URL | 最终路径 | 官方客户端族 | 认证形态 |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions | `https://opencode.ai/zen/go/v1` | `/chat/completions` | `@ai-sdk/openai-compatible` | `Authorization: Bearer <key>` |
| OpenAI Responses | `https://opencode.ai/zen/go/v1` | `/responses` | `@ai-sdk/openai` | `Authorization: Bearer <key>` |
| Anthropic Messages | `https://opencode.ai/zen/go/v1` | `/messages` | `@ai-sdk/anthropic` | `x-api-key: <key>` |

OpenCode Go 文档要求用户取得一个 OpenCode API key；官方 model registry 也把统一 credential 记为 `OPENCODE_API_KEY`，同时按模型切换 SDK package。[OpenCode Go — How it works](https://opencode.ai/docs/go/#how-it-works)、[OpenCode Go provider metadata](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/provider.toml)

认证头不是推测：OpenCode Go 三条 route 的官方源码分别从 Bearer token、Bearer token、`x-api-key` 读取同一把 key。[Chat route](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/go/v1/chat/completions.ts#L5-L13)、[Responses route](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/go/v1/responses.ts#L5-L13)、[Messages route](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/go/v1/messages.ts#L5-L13)

实现上应继续只读取统一的 `NPC_LLM_API_KEY`，由 transport adapter 转成正确 header，不新增第二份 OpenCode-specific secret 配置。

## 当前公开的 transport 路由

下表是公开 Go 页面在核对日明确列出的 model routing，不应视为永久 Canon；页面本身说明列表会变化。[OpenCode Go — current models](https://opencode.ai/docs/go/#how-it-works)

| Transport family | 当前文档列出的模型 ID |
| --- | --- |
| `OPENAI_RESPONSES` | `grok-4.5`, `gpt-5.6-luna` |
| `OPENAI_CHAT_COMPLETIONS` | `glm-5.3`, `glm-5.2`, `glm-5.1`, `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `mimo-v2.5`, `mimo-v2.5-pro`, `hy3` |
| `ANTHROPIC_MESSAGES` | `minimax-m3`, `minimax-m2.7`, `minimax-m2.5`, `qwen3.8-max`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.6-plus` |

核对日的动态 `/models` 响应还包含 `glm-5`、`kimi-k2.5`、`qwen3.5-plus`、`mimo-v2-pro`、`mimo-v2-omni`、`hy3-preview` 等未出现在公开 endpoint 路由表中的 ID；rich catalog 还把 `minimax-m2.5` 标为 deprecated。由于 discovery 响应不含 transport/status/capabilities，这些 ID 不应被静默猜测；它们只能由后续更新的已验证 profile 或显式 `NPC_LLM_TRANSPORT` 启用。[live model discovery endpoint](https://opencode.ai/zen/go/v1/models)、[models route source](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/go/v1/models.ts#L5-L12)、[OpenCode model catalog](https://models.opencode.ai/api.json)

## 为什么不能跨 transport 猜测兼容

OpenCode Gateway 只有在入站协议与所选 upstream provider 协议相同时才原样透传；格式不同时会经过一个刻意很窄的 common request/response shape。[Gateway converter](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/util/provider/provider.ts#L182-L227)

这个 common shape 只保留核心 messages/tools。以 OpenAI-compatible 输入转换为例，`reasoning_content` 不进入 assistant common message，`response_format` 也不在 `fromOaCompatibleRequest` 的返回值中。因此错误地把一个 Responses/Messages 模型送到 Chat endpoint，不能期待 Gateway 无损修复；structured output 与 thinking 字段可能被丢掉。[OpenAI-compatible converter](https://github.com/anomalyco/opencode/blob/4643e65ad6334de3e4e68dedc201d5fbb828c9fe/packages/console/app/src/routes/zen/util/provider/openai-compatible.ts#L83-L138)

## Structured output

### Chat Completions / DeepSeek V4

DeepSeek 当前官方 Chat Completions contract 的 `response_format.type` 只有 `text` 与 `json_object`；`json_object` 保证有效 JSON，但仍要求 prompt 明确要求 JSON，并且 `finish_reason=length` 时内容可能被截断。该 contract 没有声明 OpenAI `json_schema`。[DeepSeek — Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)

OpenCode/Anomaly metadata 把 OpenCode Go 的 `deepseek-v4-flash` 和 `deepseek-v4-pro` 标为 `structured_output: true`，但不区分具体 wire dialect。[DeepSeek V4 Flash model metadata](https://github.com/anomalyco/models.dev/blob/dev/models/deepseek/deepseek-v4-flash-0731.toml)、[DeepSeek V4 Pro OpenCode Go profile](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/models/deepseek-v4-pro.toml)

因此当前可辩护的 profile 是：

```text
OpenCode Go + deepseek-v4-*
transport = OPENAI_CHAT_COMPLETIONS
supports_json_object = true
supports_json_schema = false
runtime_schema_validation = always
```

不能因为 endpoint “OpenAI-compatible” 就发送 `response_format.type=json_schema`。正确 root schema 仍由 prompt 与 Runtime 严格 parser 共同执行；不能自动 unwrap 或 repair。

### 其他模型/transport

- OpenCode rich catalog 当前把部分模型标为 `structured_output: true`，例如 Chat 路径的 `glm-5.2/5.3`、`kimi-k2.7-code/kimi-k3`，Responses 路径的 `gpt-5.6-luna/grok-4.5`，以及 Messages 路径的 `qwen3.8-max`。缺少该字段的模型不应被当作已验证支持。[OpenCode model catalog](https://models.opencode.ai/api.json)
- OpenAI-compatible SDK 只有在 provider 明确启用 structured outputs 时才承诺 schema-based object generation；这仍不是 OpenCode Go 对某模型的 raw HTTP `json_schema` passthrough 保证。[AI SDK — OpenAI-compatible supported capabilities](https://ai-sdk.dev/providers/openai-compatible-providers)
- OpenAI Responses 的 structured output 与 Chat 的 `response_format` 不是同一个 adapter surface；Anthropic Messages 当前使用 `output_config.format.type=json_schema`。这两条都需要独立请求/响应 contract tests。[AI SDK — OpenAI Responses](https://ai-sdk.dev/providers/ai-sdk-providers/openai)、[Claude — Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)

所以在本轮未实现 Responses/Messages adapter 时，不应仅凭 metadata 宣称这两个 transport 已支持 strict structured response。

## Tool calling

当前 OpenCode rich catalog 的 OpenCode Go entries 对公开路由表中的 active 模型都声明 `tool_call: true`。[OpenCode model catalog](https://models.opencode.ai/api.json)

这只说明模型能力，不消除 transport 差异：

- Chat Completions 使用 `tools[].type=function`，返回 `choices[].message.tool_calls[]`；`function.arguments` 是 JSON 字符串，Provider 必须解析，Runtime 仍须白名单和 schema 校验。tool result 用 `role=tool` 与 `tool_call_id` 回传。[DeepSeek — Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- Anthropic Messages 返回 `tool_use` content block，参数已经是 JSON object；结果在下一条 user message 中以 `tool_result` block 回传，不存在 OpenAI 的 `role=tool` 消息。[Claude — Messages tool contract](https://platform.claude.com/docs/en/api/typescript/messages/create)、[Claude — Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- Responses API 也必须有自己的 output-item/tool-result translation。官方 OpenAI SDK path 与 Go endpoint 都把它列为独立 API，而不是 Chat Completions 的 URL alias。[OpenCode Go — Endpoints](https://opencode.ai/docs/go/#endpoints)、[AI SDK — OpenAI Responses](https://ai-sdk.dev/providers/ai-sdk-providers/openai)

结论：一个 provider-neutral `ToolCall` DTO 可以复用，但三种 wire translators 不能共用 Chat payload parser。未实现的 transport 应返回明确 capability/transport error。

## Thinking / reasoning

OpenCode/Anomaly metadata 当前记录：

- `deepseek-v4-flash`: effort `low/high/max`，并以 `reasoning_content` 作为 interleaved field；
- `deepseek-v4-pro`: effort `high/max`，同样需要 `reasoning_content`；
- `gpt-5.6-luna`: effort `none/low/medium/high/xhigh/max`，走 Responses；
- `qwen3.7-plus`: toggle + reasoning-token budget，走 Messages。

来源：[DeepSeek V4 Flash Go profile](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/models/deepseek-v4-flash.toml)、[GPT-5.6 Luna Go profile](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/models/gpt-5.6-luna.toml)、[Qwen3.7 Plus Go profile](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/models/qwen3.7-plus.toml)。

但同一个官方 provider metadata 文件明确警告：model reasoning options 不是由公开 Go HTTP 文档保证的 raw request contract。因此不能仅因 model ID 包含 `deepseek`，就把 direct DeepSeek 的私有字段注入 OpenCode Go 请求。[OpenCode Go provider metadata caveat](https://github.com/anomalyco/models.dev/blob/dev/providers/opencode-go/provider.toml)

直连 DeepSeek 的官方行为仍然清楚：thinking 默认 enabled；tool-call turn 必须在后续请求完整回传 `reasoning_content`，否则返回 400；也可显式发送 `thinking: {"type":"disabled"}` 关闭。[DeepSeek — Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)

实现边界应是：

```text
DeepSeek direct profile
  -> may own extra_body.thinking = disabled

OpenCode Go profile
  -> no DeepSeek-private option merely because of model name
  -> add an option only after OpenCode Go docs or reproducible gateway payload + regression test establish it
```

## 建议的本轮 profile 基线

| Profile | Transport | Tools | Strict response |
| --- | --- | ---: | --- |
| OpenCode Go `deepseek-v4-flash` | Chat Completions | yes | `json_object`; no `json_schema` |
| OpenCode Go `deepseek-v4-pro` | Chat Completions | yes | `json_object`; no `json_schema` |
| 其他公开 Chat 模型 | Chat Completions | model metadata says yes | only enable structured mode where the chosen profile has an explicit verified capability |
| `gpt-5.6-luna`, `grok-4.5` | Responses | metadata says yes | recognize; fail fast until Responses adapter has contract tests |
| MiniMax/Qwen Messages models | Anthropic Messages | metadata says yes | recognize; fail fast until Messages adapter has contract tests |
| unknown OpenCode Go model | explicit override required | conservative | conservative |

Profile resolution precedence:

```text
explicit transport override
> centralized known model profile
> configuration error
```

Live certification should be one representative smoke per implemented transport family, not one call per model. Deterministic contract tests cover translation and normalization; the dynamic model endpoint covers discovery, not protocol certification.
