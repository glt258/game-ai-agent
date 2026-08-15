# Character Generation Agent v0.1

## Purpose

The agent turns a planner's `CharacterDesignRequest` into a reviewable,
Canon-aware `CharacterDraft`. A draft is a proposal, not approval and never
gets written to the formal character, Lore, Story or StoryState data.

## Architecture

```text
CharacterDesignRequest
        ↓
CharacterGenerationAgent
        ↓
AgentModel / LiveLLMAdapter
        ↓
bounded Tool Loop
        ↓
CharacterAuthoringToolbox (read-only)
        ↓
Canon resolver / Story repositories
        ↓
strict CharacterDraft
        ↓
evidence and constraint validation
```

The consumer is a sibling of `NpcConversationAgent`; it is not an NPC and is
not bound to `NpcCharacterView` or an in-world identity.

## Request and tools

`CharacterDesignRequest` preserves the freeform brief while separating hard
constraints, soft preferences, forbidden elements and desired connections.
The fixed tool set is `search_lore`/`get_lore`, `search_factions`/`get_faction`,
`search_characters`/`get_character`, `get_world_rules`, and the generic
`search_story_context`/`get_story_context` pair. All tools are read-only,
strictly schema-validated and return safe summaries before detail views.

## Draft schema

`CharacterDraft` includes a draft-only ID, a null `canonical_character_id`, status, identity/design fields,
high-level combat role, `canon_basis`, `new_design_elements`,
`proposed_new_content`, `open_questions`, `constraint_notes`, and an optional
`story_link`. Canon IDs are strict strings and are never allocated from the
formal character namespace.

The final protocol requires the JSON root itself to be `CharacterDraft`; it
explicitly forbids `character_draft`, `draft`, `result`, `data`, `response`,
`payload`, or any other envelope. The prompt's root example and provider JSON
Schema come from centralized schema metadata. Runtime parsing remains strict:
there is no envelope unwrap, JSON repair, Markdown extraction, or ID coercion.

## Canon vs proposal and grounding

Existing faction, Lore, character, story, case, incident and world-rule facts
must cite source IDs returned by successful authoring tools in this generation
turn. User text is not evidence. Personal names, habits, personality,
high-level ability concepts and other new design details are explicitly
proposal fields and do not require an old Lore source. Unknown or fake IDs,
malformed JSON, forbidden tool calls and out-of-range hard constraints fail
closed.

## Running

```bash
py scripts/demo_character_generation_v0_1.py --model offline
py scripts/demo_character_generation_v0_1.py --model offline --json
py scripts/run_character_generation_evals.py
py -m pytest -q
```

Live mode reuses `LiveLLMAdapter`, OpenAI-compatible transport and the existing
`NPC_LLM_PROVIDER`, `NPC_LLM_MODEL`, `NPC_LLM_API_KEY` and related settings.
DeepSeek keeps thinking disabled through the existing provider configuration.
OpenCode Go should be configured as the logical provider rather than disguised
as direct DeepSeek. See `docs/provider_capability_layer.md`.

## Known limitations

v0.1 does not implement Canon Checker, similarity/conflict analysis, repair
loops, approval/publish, balance numbers, UI, RAG, memory, planning or any
Canon write path. Human review and a future Canon Checker remain necessary.
