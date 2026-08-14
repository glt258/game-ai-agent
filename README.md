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
