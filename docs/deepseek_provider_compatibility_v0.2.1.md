# DeepSeek Provider Compatibility v0.2.1

核对日期：2026-08-14

范围：仅核对 DeepSeek 官方 API 文档与 OpenAI 官方 Python SDK 文档；不涉及第三方代理端点。

## 结论

| 项目 | 当前官方结论 | 对现有普通 tool loop 的影响 |
| --- | --- | --- |
| OpenAI-compatible Base URL | `https://api.deepseek.com` | 将它传给 `OpenAI(base_url=...)`；SDK 会调用 `/chat/completions`。不要把 Beta 的 `/beta` 当作普通端点。 |
| 当前模型 ID | `deepseek-v4-flash`、`deepseek-v4-pro` | 新配置应使用其中之一。`deepseek-chat` / `deepseek-reasoner` 是已过停用日期的旧名称。 |
| Tool Calling | 使用 OpenAI Chat Completions 的 `tools` / `tool_calls` 格式 | 现有工具 schema、call ID、字符串 JSON arguments、`role: tool` 回传结构可复用。 |
| Thinking 默认值 | V4 的 thinking 默认 `enabled` | 现有 loop 不保存和回传 `reasoning_content`，不能安全地直接采用默认 thinking。 |
| 当前最小兼容策略 | 显式发送 `thinking: {"type": "disabled"}` | 在增加完整的 `reasoning_content` round-trip 之前，应关闭 thinking。 |
| OpenAI Python SDK 扩展字段 | 通过 `extra_body` 发送 SDK 未建模的 JSON body 字段 | 使用 `extra_body={"thinking": {"type": "disabled"}}`。 |

## 1. Base URL 与模型 ID

DeepSeek 当前 Quick Start 明确给出的 OpenAI-format Base URL 是：

```text
https://api.deepseek.com
```

官方 Python 示例同样使用：

```python
OpenAI(
    api_key="...",
    base_url="https://api.deepseek.com",
)
```

来源：[DeepSeek — Your First API Call](https://api-docs.deepseek.com/)、[DeepSeek — Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

截至核对日期，当前文档只列出 `deepseek-v4-flash` 与 `deepseek-v4-pro`。DeepSeek 在 2026-04-24 的更新中宣布旧名称 `deepseek-chat` 和 `deepseek-reasoner` 将于 2026-07-24 15:59 UTC 停用；当前 Quick Start 和 API Reference 已不再把它们列为可用模型。因此新 Provider 配置不应继续以 `deepseek-chat` 为默认模型。来源：[DeepSeek — Change Log](https://api-docs.deepseek.com/updates/)、[DeepSeek — V4 announcement](https://api-docs.deepseek.com/news/news260424/)、[DeepSeek — Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

历史上（退役前）`deepseek-chat` 映射 V4 Flash 的 non-thinking mode，`deepseek-reasoner` 映射 thinking mode；不能把这两个旧别名的历史语义套用到当前 V4 模型 ID 的默认参数行为上。

## 2. Tool / Function Calling 格式

DeepSeek 的普通 Tool Calling 使用 OpenAI Chat Completions 结构：

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "...",
        "parameters": {
          "type": "object",
          "properties": {}
        }
      }
    }
  ]
}
```

模型请求工具时，结果位于 `choices[0].message.tool_calls[]`：

```json
{
  "id": "call_...",
  "type": "function",
  "function": {
    "name": "get_weather",
    "arguments": "{\"location\":\"Hangzhou\"}"
  }
}
```

执行工具后，调用方把原 assistant tool-call message 加入历史，再追加：

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "content": "24℃"
}
```

`function.arguments` 是模型生成的 JSON **字符串**。官方 API Reference 明确提醒它可能不是有效 JSON，或包含 schema 未定义参数，因此 Runtime 仍必须解析、白名单校验和参数校验，不能直接执行。来源：[DeepSeek — Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[DeepSeek — Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

普通工具请求不需要 DeepSeek 专属的 function-calling 参数；存在 `tools` 时，API Reference 记载 `tool_choice` 的默认值为 `auto`。Beta strict mode 另需 `https://api.deepseek.com/beta` 和每个 function 的 `strict: true`，不属于当前普通 Provider 兼容范围。

## 3. Thinking mode 与现有 tool loop

当前 `deepseek-v4-flash` 和 `deepseek-v4-pro` 都同时支持 thinking / non-thinking，且官方模型页和 API Reference 都写明 thinking 默认开启。开关格式是：

```json
{"thinking": {"type": "enabled"}}
```

或：

```json
{"thinking": {"type": "disabled"}}
```

在 thinking mode 中，assistant 除 `content` 和 `tool_calls` 外还可能返回同级的 `reasoning_content`。如果该 assistant turn 发起了工具调用，DeepSeek 要求在后续请求中完整回传该 `reasoning_content`；遗漏会得到 HTTP 400。来源：[DeepSeek — Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)、[DeepSeek — Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[DeepSeek — Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

Tool Calling 本身并不要求关闭 thinking；限制来自消息历史契约。现有普通 loop 只保留 assistant 的 `content`、`tool_calls` 和 tool result，不保留 DeepSeek 专属 `reasoning_content`。因此当前最小、确定的兼容配置是：

```python
client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    tools=tools,
    extra_body={"thinking": {"type": "disabled"}},
)
```

关闭 thinking 时不需要发送 `reasoning_effort`。若未来要支持 thinking tool loop，则不能只删除上面的关闭参数；必须同时：

1. 从 Provider response 读取 `reasoning_content`；
2. 把它保存在对应 assistant tool-call message 中；
3. 在后续 tool round 以及官方要求的后续 user interaction 中完整回传；
4. 为缺失回传导致的 400 增加兼容测试。

### 官方示例歧义

当前 Tool Calls 指南把一段示例列在 “Non-thinking Mode” 下，但示例本身没有传 `thinking: {"type": "disabled"}`。这与同日的模型页和 API Reference 所写“默认 thinking”不一致。不能据此把“省略 thinking”解释为“关闭 thinking”；对于不实现 `reasoning_content` 的现有 loop，应使用显式关闭参数。

## 4. `extra_body` 的官方用法

DeepSeek 官方 Thinking Mode 示例要求在 OpenAI Python SDK 中把 DeepSeek 专属 `thinking` 字段放入 `extra_body`。OpenAI 官方 Python SDK README 也说明，SDK 方法未直接建模的额外 JSON request 参数应通过 `extra_body` 传递。来源：[DeepSeek — Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)、[OpenAI — openai-python README](https://github.com/openai/openai-python/blob/main/README.md#undocumented-request-params)。

因此，当前 Provider 仅需为 DeepSeek 请求添加：

```python
extra_body={"thinking": {"type": "disabled"}}
```

无需为普通 tool calling 发送其他 DeepSeek 扩展字段。

本结论只覆盖 DeepSeek 官方端点。第三方 OpenAI-compatible Gateway 是否接受或透传 `thinking` 属于该 Gateway 自己的兼容契约，不能从 DeepSeek 官方端点行为推定。

## 建议的 v0.2.1 兼容基线

- Base URL：`https://api.deepseek.com`
- Model：`deepseek-v4-flash`（或按产品需要选择 `deepseek-v4-pro`）
- API：OpenAI-compatible Chat Completions
- Tool schema / response：沿用现有 OpenAI translation 和 Runtime 二次校验
- Thinking：显式 `disabled`
- `reasoning_effort`：不发送
- Beta strict mode：暂不启用
- 后续若启用 thinking：先扩展 Provider-neutral message / history，完整支持 `reasoning_content` round-trip
