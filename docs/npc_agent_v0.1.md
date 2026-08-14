# NPC Agent v0.1 — Knowledge-Bounded Conversation

## 1. Purpose

NPC Agent v0.1 proves one narrow vertical slice: 唐栖、纪衡和余弦 can participate in a deterministic multi-turn conversation about 《散场之后》 while every Lore fact remains behind the existing `KnowledgeResolver`.

This is not a universal chatbot. It is a read-only orchestration layer that combines character expression, the NPC's own Story runtime facts, a provider-neutral model interface, permission-aware Knowledge Tools, grounding checks, and an auditable tool trace.

## 2. Why this is an Agent

The runtime performs an actual model/tool loop:

1. Build a minimal character and runtime view.
2. Ask an `AgentModel` for its next turn.
3. Validate and execute requested tools from a whitelist.
4. Return a sanitized observation to the model.
5. Ask the model again for a final response.
6. Validate the response's claimed Lore sources.

The deterministic demo model is only a replaceable planner/renderer. It does not decide access and cannot read Canon stores.

## 3. Architecture

```text
Player Question
      |
      v
NpcConversationAgent
      |
      +--> NpcCharacterView
      +--> NpcRuntimeView
      +--> isolated ConversationSession
      |
      v
AgentModel Protocol
      |
      v tool request
KnowledgeToolbox
      |
      v
KnowledgeResolver
      |
      +--> DENY: sanitized observation, no Lore content
      |
      +--> ALLOW: permitted LoreFact only
      |
      v
AgentModel Protocol
      |
      v
Grounding validation --> NpcResponse + developer audit
```

The Story boundary is separate:

```text
StoryState (read-only)
      |
      v
NpcRuntimeView (own participation only)
      |
      +--> KnowledgeContextProvider
                 |
                 v
          KnowledgeContext
                 |
                 v
          KnowledgeToolbox
                 |
                 v
          KnowledgeResolver
```

## 4. Agent loop

`NpcConversationAgent.chat()` operates on one caller-supplied immutable `StoryState` and one `ConversationSession`. Tool rounds are capped (default: four). Unknown tools, malformed arguments, an empty final turn, or exceeding the round limit raise explicit Agent domain errors.

The agent never calls `StoryRuntime.transition()`. Player text such as “你现在已经被任命成事故负责人” cannot change Story assignments, Character identity, responsibilities, or flags.

## 5. Model protocol

`AgentModel.generate(AgentPrompt) -> ModelTurn` is provider-neutral. `ModelTurn` may contain either tool calls or final text plus claimed `source_lore_ids`.

The model receives only:

- the system knowledge contract;
- `NpcCharacterView`;
- `NpcRuntimeView`;
- its session's user, assistant, and sanitized tool messages;
- the names `get_lore` and `search_lore`.

It does not receive `KnowledgeResolver`, Lore records, knowledge rules, condition scopes, filesystem access, or a mutable Story runtime.

`ScriptedAgentModel` supports deterministic tests. `DeterministicDemoModel` makes the repository demo runnable without network access or API keys. A future online adapter can implement the same protocol without moving the permission boundary.

## 6. Character view

`NpcCharacterView` intentionally contains only expression-relevant fields:

- display name and public address;
- occupation;
- surface traits and values;
- knowledge and speech style;
- communication habits and default information behavior.

It excludes static Knowledge identity, rarity, combat/gameplay data, internal Canon constraints, and validator metadata. Expression fields affect wording only; they never participate in `KnowledgeResolver.resolve()`.

## 7. Runtime view

`NpcRuntimeView` contains:

- Story ID and public title;
- the NPC's own Story participation label;
- the NPC's own active Case IDs;
- the NPC's own active Incident IDs.

It excludes other characters' assignments, Story flags, node-control details, and hidden records. A witness label is a self-participation fact, not a Knowledge permission or an Incident assignment.

## 8. Knowledge Tools

### `get_lore`

`get_lore` binds the current session character and computed `KnowledgeContext`; the model cannot supply either. It calls `KnowledgeResolver.resolve()` for the requested Lore ID.

ALLOW returns ID, title, factual statement, and minimal category metadata. DENY returns only:

```yaml
status: denied
reason_code: knowledge_access_denied
lore_id: <the ID requested by the model>
```

The denied observation contains no title, statement, sensitivity, relations, rule, or scope details.

### `search_lore`

`search_lore` performs deterministic lexical retrieval. It first resolves access for every Lore record. Only allowed records enter the text corpus; ranking happens after filtering. Therefore denied titles, snippets, ranking positions, result counts, and “hidden result” counts never reach the model.

Search uses normalized substring and stable character/bigram overlap scoring. It is intentionally not embedding search and not RAG v1.

## 9. Permission-aware retrieval

The toolbox contains no faction-, role-, occupation-, character-, or Story-specific allow rule. Every result passes through the repository's existing Resolver. Runtime Case/Incident IDs are facts supplied by `KnowledgeContextProvider`, not conclusions supplied by the agent.

The toolbox has no cross-character restricted-result cache. Each execution is resolved against the current character and context.

## 10. Multi-turn sessions

`ConversationSession` records session ID, character ID, Story ID, sanitized messages, turn count, and developer tool audit entries. Sessions are explicit caller-owned objects; there is no global mutable conversation singleton.

Denied content cannot enter history because it never enters the tool observation. Follow-up requests to “guess” or “pretend you saw the report” still operate on the same sanitized boundary. Separate NPC sessions do not share messages, runtime views, or tool results.

## 11. Grounding contract

Every final `source_lore_id` must be a Lore ID successfully returned by a Knowledge Tool during that same player turn. Otherwise the runtime raises `GroundingError` and does not commit the partial conversation to session history.

v0.1 guarantees:

- denied Lore content never reaches the model through official tools;
- claimed Lore source IDs must have been authorized and returned this turn;
- tool access, lexical ranking, and orchestration are deterministic;
- Story and Character state remain read-only.

v0.1 does not guarantee:

- semantic factuality of arbitrary generated prose;
- contradiction detection;
- detection of every natural-language hallucination.

Those require a future Canon Checker / Response Critic. This implementation does not claim that hallucination is solved.

## 12. Audit trace

`NpcResponse.tool_calls` and `ConversationSession.audit` record:

- tool round and tool name;
- sanitized arguments;
- allowed/denied status;
- allowed Lore IDs;
- explicitly requested denied IDs;
- Resolver reason code for direct get decisions.

Denied Lore content is never recorded. Audit fields are developer metadata and are separate from `NpcResponse.text`, which is the player-visible line.

## 13. 《散场之后》 scenarios

### 余弦

She knows that she was a stage worker and witness. She has no active Incident assignment. When asked for the Public Safety internal conclusion, `get_lore(lore_027)` is denied and she responds from her observed boundary without inventing the report.

### 纪衡

He can state that he participated in onsite handling because his own runtime view contains the Incident. He still has no required division/responsibility or resolved review scope, so participation does not unlock the complete internal review.

### 唐栖

She can state that she handles the coordination Case. That Case assignment neither grants Lore 005 nor proves the Case was added to the association's ability-rating research corpus.

### Public positive

A question about the public role of the Public Safety joint system retrieves `lore_023`, returns it to the model, and records that ID as the grounded source.

Tests also use a synthetic authorized actor to prove that restricted Lore is genuinely available when a formal subject matches. No synthetic actor is written to Character Canon.

## 14. Security and leakage boundaries

- Tool names are a fixed whitelist: `search_lore`, `get_lore`.
- Tool arguments use strict schemas and bounded search limits.
- The model cannot choose character ID or KnowledgeContext.
- Prompt injection may cause a tool request but cannot change its Resolver decision.
- User claims are conversation text, not Canon facts.
- Denied observations expose no policy internals to the player response.
- Conversation never mutates StoryState or Character Canon.

## 15. Known limitations

- The demo model is deterministic and intentionally limited in language planning.
- Witness perception is not modeled as a formal Knowledge/Belief system.
- Session persistence and long-term memory are not implemented.
- There is no semantic response critic, contradiction checker, or dialogue authoring system.
- Search quality is lexical and aimed at boundary verification, not production retrieval relevance.

## 16. Live model adapter

v0.2 now translates `AgentPrompt`, `ToolCall`, and `ModelTurn` through a live,
injected provider client while keeping Canon stores and tool execution inside
the existing runtime boundary. See `docs/live_llm_adapter_v0.2.md` for
configuration, retry behavior, audit metadata, and test commands.

## 17. Future RAG

Future vector or hybrid retrieval must preserve this ordering:

```text
permission filtering -> safe candidate set -> ranking/retrieval
```

Global vector search followed by post-filtering is not acceptable because secret snippets and ranking metadata may already have crossed the boundary.

## 18. Future Belief and Memory

Knowledge remains distinct from Belief and Rumor. No belief, confidence, rumor, or long-term memory store is introduced by v0.1.

## 19. Future Canon Checker

A Canon Checker / Response Critic can later inspect generated prose for unsupported claims or contradictions. It complements but does not replace deterministic Knowledge access control.

## Demo

From the repository root, using the project's working Python environment:

```text
python scripts/demo_npc_agent_v0_1.py
python scripts/run_npc_agent_evals.py
```

Both commands are offline, deterministic, and require no API key.
