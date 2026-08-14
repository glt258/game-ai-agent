# Grounded Response Validation v0.3

## Problem

Permission-safe is not the same as fact-grounded. The resolver can correctly
withhold restricted Lore while a generative model still invents incident
details from the limited context it is allowed to see. v0.3 therefore keeps the
existing permission boundary and adds a separate grounding boundary before a
final answer can be committed.

Permission answers **what the NPC may access**. Grounding answers **what the
NPC may assert as fact**. A statement must satisfy both boundaries.

## Architecture

```text
Model candidate
  -> provider-neutral grounded segments
  -> request-local safe evidence builder
  -> deterministic grounding validator
  -> pass ---------------------------> final commit
     unsupported -> one repair -> pass -> final commit
                              -> fail/error -> deterministic fallback -> commit
```

The failed candidate and a failed repair are never written to the conversation
history. Tool observations and the final validated answer are committed
together, preserving the existing transactional turn behavior.

## Permission-safe evidence

`GroundingEvidenceBuilder` receives only objects that are already safe for the
request:

- the NPC's Character View;
- the NPC's Runtime View;
- successful, current-turn Knowledge Tool observations.

It does not receive or query the resolver, full Canon, the Lore repository, or
restricted records. Denied tool observations create no evidence. User messages,
assistant assertions, pretend tool output, previous turns, and other sessions
are not factual evidence.

Evidence IDs are deterministic statement-level identifiers such as
`character:display_name`, `runtime:participation`, and
`lore:lore_023:statement`. Only allowed Lore statements returned in the current
turn can produce the last form. Canon data is not rewritten or rechunked.

## Grounded segment protocol

Final model output is a JSON object containing a non-empty `segments` array.
The adapter converts it into `GroundedResponseSegment` objects; the runtime
constructs player-visible text only by concatenating validated segment text.

The model may propose three kinds:

- `supported_claim`: a project-world assertion with one or more evidence IDs;
- `uncertain`: an explicit approved abstention with no evidence IDs;
- `non_factual`: an approved suggestion or conversational form with no evidence
  IDs.

`unsupported` is a validator result, not a segment kind the model may select.
The runtime rejects missing, duplicate, fake, unavailable, or semantically
unrelated evidence references. Used Lore sources are derived from validated
supported segments, so retrieved-but-unused Lore does not appear in the final
`source_lore_ids`.

## Minimum semantic guard

The repository's Lore unit is already a single core `statement`, so v0.3 uses
statement-level evidence. A supported segment must be an extractive substring
of at least one cited evidence statement after deterministic punctuation and
case normalization. A deterministic polarity check rejects a positive substring
when its occurrence is immediately negated in the evidence (for example,
“not an independent authority” cannot support “an independent authority”).
This is intentionally strict: it prevents a valid evidence ID from being
attached to an unrelated or opposite claim without introducing embeddings,
NLI, or a second LLM judge.

Explicit uncertainty and non-factual text use small allowlists. This prevents a
claim such as “possibly three injuries” from passing merely because it contains
hedging language.

## Single controlled repair

An unsupported candidate triggers exactly one model repair invocation. The
repair receives:

- the original candidate segments;
- the same permission-safe evidence set;
- rejected segment IDs and generic “no available supporting evidence” reasons;
- instructions to remove unsupported facts or use an approved abstention.

Conversation history is omitted and `available_tools` is empty. Repair cannot
search for evidence, execute tools, or learn whether an unavailable ID exists
but is restricted. A tool call, malformed/unsupported repair, or provider error
causes the fixed deterministic safe fallback. There is no repair loop.

Model invocation audit still records each successful provider invocation.
`GroundingAudit` records claim status counts and whether repair or fallback was
used, without storing hidden Lore, prompts, API keys, or chain of thought.

## Provider behavior

Offline and live models use the same internal segment DTOs and runtime
validator. `LiveLLMAdapter` uses strict JSON prompting and a bounded parser; it
does not depend on a provider-private JSON mode. OpenAI-compatible and DeepSeek
tool calls continue through the same whitelist and resolver. DeepSeek thinking
remains explicitly disabled because the runtime does not implement
`reasoning_content` round-tripping.

## Safe fallback

If repair cannot produce a valid answer, the runtime commits only:

> 我目前能确认的信息不足以支持更具体的结论。涉及你问到的细节，我不能在没有依据的情况下补充。

The fallback is deterministic, contains no factual assertion, calls no model or
tool, and itself passes the uncertainty-segment rules.

## Known limitations

v0.3 does not guarantee arbitrary natural-language truthfulness. It enforces
grounding against permission-safe project evidence using the implemented
claim/evidence protocol. It does not solve:

- claims that the model fails to split into sufficiently small units;
- subtle paraphrase or semantic entailment;
- real-world fact checking or common-sense errors;
- mathematical, temporal, or multi-step logical correctness;
- all forms of natural-language hallucination.

The extractive guard can reject correct paraphrases. Future improvements should
prefer finer deterministic fact units over a second-model judge.

## Verification

Run offline verification with:

```powershell
py -m pytest -q
py scripts\run_npc_agent_evals.py
py scripts\demo_npc_agent_v0_1.py --model offline
```

The optional live smoke remains opt-in and may incur provider cost. v0.3 makes
no Canon/Data changes.
