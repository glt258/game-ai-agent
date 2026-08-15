# Provider Capability Layer

## What changed

The runtime now treats four concepts separately:

```text
Agent requirement
    -> LiveLLMAdapter
    -> ProviderProfile + ProviderCapabilities
    -> capability negotiation
    -> TransportFamily
    -> external provider or gateway
```

- A **logical provider** is the service receiving the request (`openai`,
  `deepseek`, `opencode_go`, or `openai_compatible`).
- A **model** is the configured model ID. It does not select provider-specific
  request extensions by substring matching.
- A **transport family** is the wire protocol used to send the request.
- **Capabilities** declare whether that provider/model profile supports tools,
  JSON Object mode, strict JSON Schema, parallel tool calls, and a known
  thinking-mode policy.

Agents continue to request tools and strict domain results. They do not request
OpenAI SDK options and contain no provider/model conditionals.

## Supported logical providers

| Provider | Default URL | Transport | Structured-output default | Provider options |
| --- | --- | --- | --- | --- |
| `openai` | OpenAI SDK default | OpenAI Chat Completions | conservative JSON Object | none |
| `deepseek` | `https://api.deepseek.com` | OpenAI Chat Completions | JSON Object | thinking disabled |
| `opencode_go` | `https://opencode.ai/zen/go/v1` | per known model profile | JSON Object for verified Chat profiles | none |
| `openai_compatible` | must be configured | OpenAI Chat Completions | conservative JSON Object | none |

The direct DeepSeek `thinking={type: disabled}` option belongs only to the
direct `deepseek` profile. An OpenCode Go model whose ID contains `deepseek`
does not inherit that extension.

`NPC_LLM_BASE_URL` still overrides every provider default. Existing `openai`
and `deepseek` configuration remains valid.

## OpenCode Go routing

`KNOWN_OPENCODE_GO_MODEL_PROFILES` is a small compatibility map, not a permanent
copy of the gateway's model catalogue. Known models select a transport and
capabilities from that map. The application does not call a models endpoint at
startup and normal tests never probe the network.

The map currently records the official routing groups checked on 2026-08-15:

- Chat Completions: `glm-5.3`, `glm-5.2`, `glm-5.1`, `kimi-k3`,
  `kimi-k2.7-code`, `kimi-k2.6`, `deepseek-v4-pro`,
  `deepseek-v4-flash`, `mimo-v2.5`, `mimo-v2.5-pro`, and `hy3`;
- Responses: `grok-4.5` and `gpt-5.6-luna`;
- Messages: `minimax-m3`, `minimax-m2.7`, `minimax-m2.5`, `qwen3.8-max`,
  `qwen3.7-max`, `qwen3.7-plus`, and `qwen3.6-plus`.

Only the two DeepSeek Chat profiles have a built-in verified `json_object`
dialect. Other Chat entries declare their official transport and tools but fail
closed for this repository's strict final responses until their wire-level JSON
dialect is verified or explicitly configured. This keeps one shared Chat
transport without turning coarse catalogue metadata into an unsupported claim.
The dated primary-source review is in
`docs/opencode_go_provider_contract_2026-08-15.md`.

For an unknown OpenCode Go model, startup fails instead of guessing a
transport. A user who has verified the model contract can opt in explicitly:

```powershell
$env:NPC_LLM_TRANSPORT = "openai_chat_completions"
```

Aliases `chat_completions`, `responses`, and `messages` are accepted. The
explicit transport has priority over a known model profile.

## Transport families

| Family | State |
| --- | --- |
| `openai_chat_completions` | implemented and covered by provider contract tests |
| `openai_responses` | recognized; not implemented |
| `anthropic_messages` | recognized; not implemented |

Selecting a recognized but unimplemented transport raises a capability error
before client construction or a network request. No compatibility claim is
made for a transport without translation and contract tests.

## Structured-output negotiation

The Agent requests a provider-neutral `ResponseContract` such as
`character_draft` or `grounded_response`:

```text
strict response requested
    -> profile supports JSON Schema: send strict json_schema + schema
    -> otherwise profile supports JSON Object: send json_object
    -> otherwise: fail before network
```

There is no plain-text fallback for a strict response. JSON mode is only a
transport aid: `json.loads` and the runtime's exact domain validators remain
authoritative.

Built-in model-agnostic profiles deliberately do not assume strict OpenAI JSON
Schema support merely because an endpoint looks OpenAI-compatible. A verified
deployment can declare it explicitly with:

```powershell
$env:NPC_LLM_STRUCTURED_OUTPUT = "json_schema"
```

Accepted values are `json_schema`, `json_object`, and `none`. This is optional;
known profiles supply their normal capability defaults.

## CharacterDraft root contract

The Character Generation system prompt now carries the JSON Schema and a root
example generated from the same centralized schema metadata used to define
allowed `CharacterDraft` fields. It explicitly states that the JSON root itself
is the draft and forbids `character_draft`, `draft`, `result`, `data`,
`response`, `payload`, and every other envelope.

The parser does not unwrap, extract, strip Markdown, repair JSON, coerce domain
IDs, or retry a malformed draft. For example, this remains a schema violation:

```json
{"character_draft":{"draft_id":"draft_request_001"}}
```

Provider JSON Schema is an extra format constraint, not a replacement for
runtime validation.

## Tool capabilities and authority

When a prompt contains tool definitions and the selected profile does not
support tools, the adapter fails before a request. For supported profiles, all
transports still normalize calls to `call_id`, `name`, and `arguments`.

The Provider schema does not grant authority. Runtime argument validation, the
tool whitelist, the Permission Resolver, evidence checks, and grounding remain
unchanged.

## Adding compatibility

To add another OpenAI-compatible provider or verified model:

1. Add or update one centralized `ProviderProfile`/model compatibility entry.
2. Declare its default URL, transport, capabilities, and validated provider
   options.
3. Let it run through the parameterized provider contract matrix.
4. Optionally run one paid live smoke for the implemented transport family.

To add a new transport family, implement an isolated transport adapter that
normalizes completion text, tool calls, usage, request IDs, and errors. Do not
change either Agent runtime.

Deterministic profile/contract tests show that this repository constructs and
validates the protocol correctly. A representative live smoke shows that an
external endpoint currently integrates with that transport. Models behind a
gateway may change independently, so neither is presented as permanent
certification of every model.

## Configuration examples

OpenCode Go with its default URL:

```powershell
$env:NPC_AGENT_MODEL = "live"
$env:NPC_LLM_PROVIDER = "opencode_go"
$env:NPC_LLM_MODEL = "deepseek-v4-flash"
$env:NPC_LLM_API_KEY = "<secret>"
py scripts\demo_character_generation_v0_1.py --model live
```

Generic compatible gateway:

```powershell
$env:NPC_AGENT_MODEL = "live"
$env:NPC_LLM_PROVIDER = "openai_compatible"
$env:NPC_LLM_MODEL = "<model-id>"
$env:NPC_LLM_API_KEY = "<secret>"
$env:NPC_LLM_BASE_URL = "https://gateway.example/v1"
```

The live smoke remains opt-in and may incur cost:

```powershell
$env:NPC_RUN_LIVE_SMOKE = "1"
py -m pytest tests\test_live_smoke.py -q -s
```
