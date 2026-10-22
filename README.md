# Game AI Agent

**An AI-assisted game design and development framework**

This repository contains a public software demo for structured game-content authoring, validation, and evaluation.

## Public demo scope

Packaged records are synthetic demonstration data. The original project setting, story canon, production character roster, and third-party character reference corpus are excluded. The sample data is intentionally small and does not represent a complete game world.

## Capabilities

- Structured character and skill authoring workflows.
- Bounded retrieval and deterministic validation interfaces.
- Provider adapters and auditable model-call boundaries.
- Experimental web tooling and saved-character workflows.
- Offline combat-design and evaluation prototypes.

Model output is a proposal for human review, not an approval or a write to canonical data. Experimental results are not claims of production readiness or universal model quality.

## Development

Python 3.10 or later is required.

```bash
python -m pip install -e ".[dev]"
game-ai-agent doctor
pytest
```

Some experimental workflows require provider credentials configured through environment variables. Do not commit credentials or local configuration files.

The data under `src/along_street_resources/data/` is synthetic only. This repository intentionally does not include a license declaration; no reuse rights should be inferred from source availability.
