# Game AI Agent

**An AI-Assisted Game Design & Development Framework**

*From Character Creation to Game Systems — Exploring AI-Assisted Game Design.*

**English** | [简体中文](README.zh-CN.md)

[![CI](https://github.com/glt258/game-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/glt258/game-ai-agent/actions/workflows/ci.yml)

Game AI Agent explores how AI can support human designers across game content and systems
design. It began with long-running NPC memory and behavior-consistency problems: retaining
player histories, keeping identities and behavior coherent, and respecting world rules over
time. That work expanded into character authoring, Canon and story context, skill design, and
evaluation. The project is now also exploring combat simulation and balance through an
independent offline prototype.

The goal is an AI-assisted framework that helps designers explore, validate, and iterate on
proposals. Its evolving design direction is **Human Direction → AI Exploration → Structured
Validation → Simulation & Evaluation → Human Decision**. Current tools implement parts of this
loop, but it is not yet one integrated production workflow. Model output remains a proposal,
Canon stays read-only to authoring, and human review remains authoritative. Game AI Agent is
not a prompt wrapper or game engine, and it does not claim fully autonomous game development.

## Project Evolution

1. **NPC Memory & Consistency** — The original problem was keeping NPCs aware of players and
   prior interactions while preserving character identity, behavior, and world rules over
   long-running conversations.
2. **Character Creation Agent** — The work grew into structured, Canon-grounded character authoring with deterministic validation and human review.
3. **Game Design & Combat Systems** — Character and skill design broadened toward role and
   combat concepts; simulation is being explored separately as an offline prototype.
4. **AI Creativity & Evaluation** — The project is exploring how to assess generated designs
   and support comparison and iteration across multiple candidates.

This progression followed problems encountered during development; it was not a plan to build a large game-development platform from the start.

## Project Context

The project began as **Along the Street**, the repository's built-in Canon, test
world, and development setting. It started from a narrower Character Authoring
pipeline: help designers turn a brief into a grounded, reviewable proposal
without letting a model invent world facts or overwrite established story data.
The current structured character-and-skill system is an evolution of that
boundary, not a claim that the repository is already a complete game-production
platform.

The Character Authoring milestone also established age-ambiguous and diverse
life-stage handling without mechanically mapping presentation to school,
occupation, authority, or narrative importance. Exact, legal, and historical
age information remains distinct from current non-student status; see the
[life-stage coverage](docs/character_diversity_life_stage_v0.3.md) and [age
information preservation](docs/character_age_information_preservation_v0.3.md)
contracts.

## What it can do now

- **Implemented authoring workflows:** Turn a designer brief into a structured,
  reviewable `CharacterDraft`; ground it in bounded, read-only Canon and story retrieval.
- **Implemented design and validation:** Project design intent, retrieve Reference Corpus
  precedents, design skills through Semantic IR and deterministic compilation, and evaluate
  canonical `SkillKit` artifacts.
- **Implemented developer tools:** Run deterministic checks with auditable tool/model
  invocations and use the CLI. The local Next.js + FastAPI Studio and its SQLite-backed Saved
  Character workspaces are implemented as an experimental workflow.
- **Experimental and offline:** Explore combat roles, elements, and encounter outcomes in a
  separate prototype; its results are not production balance validation.
- **Planned or exploratory:** Broader story and relationship workflows, systematic creativity evaluation, and multi-candidate design iteration.

## Current Capabilities

### Character Design & Authoring

```text
Designer Brief → intent / plan → bounded Canon retrieval
  → CharacterDraft generation → deterministic validation → CanonChecker
  → at most one permitted repair → human review
```

`CharacterDraft` is a reviewable proposal, not an approval or a Canon write.
The authoring toolbox exposes allowlisted lore, faction, character, world-rule,
and story queries; it does not expose arbitrary files or write operations.

### Character Intelligence

`CharacterDesignIntent`, `CharacterDesignPlan`, and `DesignPatternQuery` provide
structured projections of a brief. The deterministic reference selector finds
relevant precedent and contrast candidates. These are design aids, not hidden
chain-of-thought or a second character schema.

### Narrative & Relationship Design

Character drafts can carry story hooks, relationship data, and bounded links to story context.
This is part of the character-authoring workflow; a standalone narrative-generation or
relationship-simulation agent is not implemented.

### Skill Design

Skill Design v1 (`CS-S2`) supports Main DPS, Sub-DPS, Support, Healer/Reaction,
Control, Defense, and Basic Passive families:

```text
Requirement / context → Semantic IR → IR validation
  → deterministic compiler → canonical SkillKit → parser / reference integrity
  → evaluator → safe diagnostics
```

Semantic repair is limited to one attempt after a validated IR reaches evaluator
failure. Provider, parse, compiler, and reference-integrity failures do not
silently become repaired success. Advanced v2 mechanics remain out of scope;
see the [Skill Design v1 freeze](docs/character_generation/character_skill_design_v1_freeze_v1.0.md).

The `v0.8` release also includes the Manual Skill Playground CLI with
natural-language requirements, role/mode, model and language selection, safe
diagnostics, and one bounded repair opportunity. Human-readable playground text
supports Simplified Chinese and English while machine-readable protocol fields
remain authoritative English values.

### Combat Simulation & Balancing (Experimental)

A separate offline prototype explores six provisional role prototypes, six elements, and
encounter outcomes. It is not integrated with the production character and skill workflows or
the production combat-role contract. Its values are uncalibrated hypotheses, and its simulated
decision policies do not represent real player behavior. Results can inform design review, but
they do not establish that the roles or combat system are balanced.

### Evaluation & Validation

Current authoring workflows combine deterministic schema, Canon-grounding, request-alignment,
representation, and skill checks with evaluation signals. Systematic assessment of creativity
and design quality remains exploratory; the existing checks do not produce an objective,
universal creativity score.

### Canon, Knowledge & Reference Corpus

- `src/knowledge/` and packaged resources provide default-deny, read-only Canon,
  world, faction, lore, character, case, incident, project, and story access.
- `CanonChecker` applies deterministic conflict, authority, grounding, scope,
  and hard-constraint checks.
- `reference-corpus-v0.5` is a frozen corpus of structured facts, sources, and
  analysis for design precedent and evaluation.

The Reference Corpus is not a copy bank, few-shot answer bank, commercial
imitation dataset, RAG claim, or source of Canon authority. Its selector is
bounded and deterministic; its selection metrics do not claim better generation.

The top-level `knowledge/` directory is the Engineering Knowledge Layer and
Project Graph: supporting traceability infrastructure, not a claim of reduced
tool usage or solved agent planning.

The frozen `reference-corpus-v0.5` baseline contains 16 accepted corpus
characters; “production” here means accepted and frozen corpus records, not
production readiness of the overall Agent system. Its production boundary is
declared by the manifest at
`src/along_street_resources/data/reference_corpus/characters/_catalog/corpus_manifest.yaml`.
Runtime code loads only manifest-declared records by default. Temporary
synthetic or external corpora must opt into `manifest_policy="unmanaged"`, and
corpus expansion is gap-driven: a concrete Generator, Canon, Repair, or
evaluation failure must show that an existing precedent is insufficient first.
The [Reference Corpus production baseline](docs/reference_corpus/production_baseline_v0.1.md)
documents this boundary.

Packaged runtime data is resolved from the single
`src/along_street_resources/data/` tree through `data_root()` and
`data_resource()`, independently of the checkout working directory. Explicit
filesystem paths are reserved for callers intentionally supplying external data
or corpus directories.

### Local Studio

The experimental local Studio is layered over the Python runtime:

- `web/`: Next.js App Router, React, TypeScript, and Tailwind CSS frontend.
- `src/web/`: FastAPI adapter and typed DTOs.
- Character Studio: generate, inspect, edit, and revalidate a draft.
- Reference Corpus browser, public-safe Canon Explorer, and Skill Playground.
- Skill Playground includes a Chinese planner view with Design Result, Design
  Checks, and Technical Details tabs; Character context reports skill validity
  and alignment and requires an explicit attach action without auto-approval.
- Saved Character workspaces with revisions, Skill associations, Kit assignments,
  and caller-configured SQLite persistence.
- Offline runs remain synchronous. Explicit live Character/Skill runs use
  bounded process-local jobs and polling; live results remain review-only and
  are never auto-attached to a Character or Kit.

It does not publish Canon, expose raw provider responses or secrets, or provide
arbitrary file access or multi-agent orchestration. The Web API does not use
WebSockets or SSE for live execution; its live job contract is explicit and
polling-based.

### Unified CLI and Studio startup

The installable Python runtime provides diagnostic and source-checkout Studio
commands:

```powershell
game-ai-agent doctor
game-ai-agent doctor --json
game-ai-agent studio --no-browser
```

The wheel contains the core runtime and packaged resources. The Next.js Studio
frontend remains source-checkout-only in v0.1: build `web/.next` first with
`cd web; npm ci; npm run build`. The launcher starts FastAPI and `next start`,
waits for both readiness endpoints, and cleans up both child processes on exit.
See the [CLI and Studio startup contract](docs/cli_and_studio_startup_contract_v0.1.md).

### Provider Layer

The agent API is provider-independent. Current logical profiles include `openai`,
`deepseek`, `opencode_go`, and `openai_compatible` over the implemented OpenAI
Chat Completions transport.

- Offline deterministic fixtures support local development and tests.
- Live execution is credential-gated and capability-profile driven.
- Unknown or unsupported transport choices fail before a request; there is no
  silent fallback.
- Audits expose only sanitized metadata, never keys, raw prompts, raw responses, or unrestricted exception text.

Live observations are bounded evidence for particular configurations, not a
benchmark or universal model-quality claim. See the [provider capability layer](docs/provider_capability_layer.md).

## Evidence / Verified Runs

Current production route: provider `opencode_go`, model `deepseek-v4.1-flash`.
The V4 Flash run below is retained as historical production evidence.

One verified live Character Authoring E2E run used provider `opencode_go` with
model `deepseek-v4-flash`. A Canon-dependent brief required membership in an
existing organization; retrieval selected `faction_005`
(`临洲市公共安全联席体系`) and produced the draft character `方宁舒`, whose
occupation was `临洲市公共安全联席体系大型活动安全组现场协作员`. The draft
contained grounded Canon Basis entries for `faction_005`, `lore_023`,
`lore_024`, `lore_026`, and `char_launch_007`. This is one verified live
example, not a benchmark or a universal model-quality claim.

The repository also preserves sanitized historical provider evidence for
Character Skill, S2, and Hybrid Semantic IR investigations under
[`tests/fixtures/historical_evidence/`](tests/fixtures/historical_evidence/).
These metadata-only fixtures support reproducible validation without causing
provider calls in CI. The [Hybrid Semantic IR success baseline](docs/hybrid_semantic_ir_e2e_success_baseline_v0.1.md)
records the corresponding historical contract.

The hermetic E2E seam injects a deterministic provider for the full
provider-to-evaluator path, while the production/live provider factory remains
credential-gated. A historical clean-checkout CI baseline is recorded in
[GitHub Actions run #17](https://github.com/glt258/game-ai-agent/actions/runs/33238359141);
it is historical evidence, not a current CI-status claim.

## Architecture

The repository separates UI, design intelligence, knowledge, execution, and evaluation without pretending to be a distributed services system.

```mermaid
flowchart LR
    designer[Designer] --> ui[Studio / CLI]
    subgraph intelligence[Design Intelligence]
        character[Character Design] --> intent[Intent / Plan / Pattern Query]
        skill[Skill Design] --> ir[Semantic IR] --> compiler[Deterministic Compiler] --> kit[Canonical SkillKit]
    end
    subgraph knowledge[Knowledge]
        canon[Read-only Canon / Story]
        corpus[Reference Corpus]
    end
    subgraph runtime[Runtime & Evaluation]
        retrieval[Bounded Retrieval] --> validation[Deterministic Validation] --> checker[CanonChecker] --> evaluator[Evaluation] --> review[Reviewable Proposal]
        checker -. permitted failure .-> repair[Bounded Repair] -. re-check .-> checker
    end
    subgraph provider[Provider Layer]
        adapters[Offline fixture / Live provider adapters]
    end
    subgraph persistence[Studio Persistence]
        sqlite[Configured SQLite Saved Workspaces]
    end
    ui --> character
    ui --> skill
    intent --> retrieval
    canon --> retrieval
    corpus --> retrieval
    kit --> validation
    adapters --> character
    adapters --> skill
    review --> sqlite
```

## Project Status

| Area | Status |
| --- | --- |
| Public release | `v0.8` — Skill Design v1 and Manual Skill Playground release |
| Character Authoring | Character Generation V2 is the default production pipeline: concept search and selection, planning, frozen Spec, generation, Canon validation, repair, and evaluation |
| Runtime Baseline | `runtime-v0.6.6` — frozen Character Authoring runtime baseline |
| Character Intelligence | `CI-B1.5` canonical combat-role boundary; V2 concept search, selection, Planner, and frozen Spec are in production |
| Legacy Generation | Research and historical-regression baseline only; not used by production entrypoints |
| Character Skill | `CS-S1.1` — frozen skill interface-design milestone |
| Skill Design | `CS-S2` / Skill Design v1 feature-frozen semantic coverage |
| Reference Corpus | `reference-corpus-v0.5`, frozen expanded baseline |
| Hybrid Semantic IR | `hybrid-semantic-ir-e2e-v0.1` — historical real-provider evaluator PASS baseline |
| Studio | Local Web v0.1 implemented; experimental relative to the `v0.8` release architecture |
| Combat Simulation | Independent offline prototype; provisional roles and uncalibrated values, outside production contracts |
| Repository Knowledge | Engineering Knowledge Layer and Project Graph as supporting infrastructure |

The public `v0.8` release is not retroactively redefined by the experimental Studio and W4 working-tree architecture. See [Versioning](docs/versioning.md) and the [v0.8 release notes](docs/release_notes_v0.8.md).

## Design Principles

### Structured before free-form

Generated text is not a final asset; typed contracts, explicit fields, and machine-checkable relationships come first.

### Canon is evidence, not prompt decoration

Existing world facts must be retrieved and supported. Model memory does not become Canon evidence.

### Deterministic checks where possible

Schema, IDs, relationships, grounding, and semantic contracts are checked by code when a deterministic rule is available. An LLM is not the Canon authority.

### Human authority

Agents propose. Human review owns approval, publication, and future Canon change.

### Models are replaceable

Agent contracts do not depend on a single vendor; capability is negotiated at the adapter boundary.

### Fail closed

Unparseable, unproven, or out-of-contract results fail explicitly rather than quietly filling gaps.

## Quick Start

### Python runtime

```powershell
git clone https://github.com/glt258/game-ai-agent.git
cd game-ai-agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
game-ai-agent doctor
python -m agents.character_generation_cli --scenario valid --model offline
```

The installed authoring entry point is also available as
`along-street-character-author`. Both commands use the same V2 application.
The historical `agents.official_character_authoring` module command forwards to
V2; its legacy demo classes remain available for research and regression tests.
Naming Shadow, Independent Naming Selector, and experimental Naming Search are
not enabled in production.

### Local Studio

From a source checkout with the Python runtime installed:

```powershell
cd web
npm ci
npm run build
cd ..
game-ai-agent studio --no-browser
```

Open <http://localhost:3000>. The launcher starts the FastAPI backend on
`http://127.0.0.1:8000` and the production Next.js frontend on port 3000. Saved
workspaces default to the platform app-data directory; use
`GAME_AI_AGENT_DB_PATH` for an explicit SQLite path.
Studio character generation uses `/api/characters/generate` and the same V2
application as the CLI and Web API.

### Testing

The normal project check is:

```powershell
python -m pytest -q
```

Focused provider, Web, persistence, and evaluation checks live under `tests/` and `scripts/`. Live provider runs are opt-in and credential-gated.

## Repository Layout

```text
src/        core runtime, agents, design intelligence, knowledge, persistence, Web adapter
web/        Next.js Studio frontend
knowledge/  Engineering Knowledge Layer and Project Graph
tests/      deterministic, contract, integration, and regression tests
evals/      evaluation cases, fixtures, and sanitized evidence
docs/       contracts, freezes, architecture notes, and release evidence
scripts/    demos and development / validation tooling
```

Along the Street is the repository's built-in Canon, test world, and development
setting. The architecture is intended to support structured game-content
authoring beyond that single fictional setting.

## Roadmap

### Current development focus

1. Continue Studio UX and productization alongside Character Design Intelligence.
2. Deepen skill and combat design while evaluating the independent offline simulator and its
   provisional six-role, six-element model.
3. Strengthen Canon and story context, request alignment, and character/skill evaluation.
4. Explore human-reviewed iteration across multiple candidate designs.

### Longer-term direction — planned / exploratory

- Validate the combat model and its assumptions; define extension points before adding elements
  or roles beyond the current prototypes.
- Design attribute, equipment, weapon, relic, and enemy-combat systems, then use simulation to
  evaluate skills and team combinations.
- Improve consistency across worldbuilding, Canon, story, and character relationships; explore
  proposal workflows for story and Canon content.
- Develop more systematic creativity evaluation and multi-candidate search and iteration.
- Build a governed data pipeline for future model training, consider specialized small-model
  fine-tuning, and explore multi-agent content design.

These are directions, not claims of completed capabilities; no dates, release promises, or completed stages are implied.

## Known Boundaries

- Not production-ready and not a completed game-development platform.
- No claim of autonomous skill balancing or universal model quality.
- Long-term NPC memory is the project's original motivation, not a currently shipped
  persistent-memory system. Combat simulation remains a separate offline prototype and is not
  part of the production authoring pipeline.
- Canon is read-only to authoring; approval, publishing, and Canon mutation are not implemented.
- The corpus is precedent and analysis, not authoritative lore or imitation data.
- Multi-agent orchestration, Story Generation Agent, broad memory/planning, and specialized fine-tuning are not implemented claims.
- Live evidence is small-sample and configuration-specific; latency and bounded provider attempts can still prevent completion.

At runtime, Canon-dependent claims without successful retrieval grounding,
unknown or malformed Canon IDs, pseudo-tool JSON, and malformed or exhausted
provider interactions fail closed. Finalization receives no tools; repair is at
most one bounded attempt and cannot write Canon, approve a draft, escape its
editable scope, or silently violate hard constraints. Live diagnostics retain
only sanitized provider/model metadata and allowlisted failure details.

## Further Reading

- [Character Generation Agent](docs/character_generation_agent_v0.1.md)
- [Runtime Freeze runtime-v0.6.6](docs/runtime_freeze_v0.6.6.md)
- [Canon Checker](docs/canon_checker_v0.1.md)
- [Character Repair Loop](docs/character_repair_loop_v0.1.md)
- [Provider Capability Layer](docs/provider_capability_layer.md)
- [v0.7.1 Release Notes](docs/release_notes_v0.7.1.md)
- [v0.7.1 Release Scope](docs/v0.7.1_release_scope.md)
- [Reference Corpus Production Baseline v0.1](docs/reference_corpus/production_baseline_v0.1.md)
- [Skill Design v1 Freeze](docs/character_generation/character_skill_design_v1_freeze_v1.0.md)
- [Reference Corpus Baseline](docs/reference_corpus_expanded_baseline_v0.5.md)
- [Studio Web Architecture](docs/web/web_v0.1_architecture.md)
- [Studio Web API Contract](docs/web/web_v0.1_api_contract.md)
- [Live Web execution](docs/live_web_execution_contract_v0.1.md)
- [CLI and Studio startup](docs/cli_and_studio_startup_contract_v0.1.md)
- [Persistence Foundation](docs/persistence_foundation_v0.1.md)
- [Versioning](docs/versioning.md)

## Acknowledgements

Special thanks to Duan Wenhua. Without your love and support, I would not have
made it this far.
