# Along the Street — Knowledge Resolver

This repository contains the read-only NPC knowledge boundary and authoring
agents for *Along the Street*.

## Character Generation Agent

Generate a Canon-aware, reviewable draft without changing formal Canon:

```bash
py scripts/demo_character_generation_v0_1.py --model offline
py scripts/run_character_generation_evals.py
```

See [docs/character_generation_agent_v0.1.md](docs/character_generation_agent_v0.1.md)
for the request, tool, grounding and limitation details.

## Live providers

The shared OpenAI Chat Completions transport supports the logical providers
`openai`, `deepseek`, `opencode_go`, and `openai_compatible`. OpenCode Go has a
default gateway URL; generic compatible gateways require an explicit Base URL.
See [docs/provider_capability_layer.md](docs/provider_capability_layer.md) for
provider/model/transport separation, capability negotiation, and configuration.
