# W4-S5A Cross-Platform Architecture Audit Report

Status: audit and design only. No production code, CI workflow, dependency, or
domain-contract change is included in this slice.

## A. Verdict

W4_S5A_ARCHITECTURE_READY

The current implementation has a credible portability base, but it is not yet
a three-OS product claim. Windows is the current development platform, Linux is
the only remotely verified platform, and macOS remains an implementation target
without repository evidence. The smallest safe next slice is the explicit
portable path/app-data/encoding contract.

## B. Starting State

Branch: `main`

HEAD: `7fcf3792cc2ea9378112f22795d5b11a5ddbafb9`

Remote CI: GREEN, CI run #24

Clean pytest baseline: `1885 passed, 1 skipped, 0 failed`

Frontend baseline: `29` tests passed; typecheck, lint, and build passed

Persistence schema: v4

## C. Engineering Knowledge Preflight

Preflight: `READY_WITH_WARNINGS`; baseline captured before this document was
created.

Queried nodes:

- Web Runtime → `component.web_adapter`
- FastAPI → no exact node; covered by `component.web_adapter` and `src/web`
- Next.js / Frontend → no exact graph node; audited from `web/`
- Persistence Foundation → `component.persistence_foundation`
- SQLite → `component.persistence_foundation` and persistence components
- Character Persistence → `component.character_persistence`
- Character Skill Persistence → `component.character_skill_persistence`
- Historical Report Persistence → `component.historical_report_persistence`
- Saved Character Workspace → `component.saved_character_workspace`
- Engineering Knowledge / Project Graph → graph tooling and `knowledge/project_graph.yaml`
- Live Web Execution → `component.live_execution_job`
- Provider Adapter → `component.openai_compatible_adapter`
- CLI / Packaging / Testing / CI → no exact graph node; audited from repository
  metadata, scripts, tests, and workflow files

Relevant edges:

- Web Adapter `adapts` CharacterGenerationAgent, Saved Character Workspace, and
  Live Execution Job.
- Saved Character Workspace `depends_on` Character Persistence, Character Skill
  Persistence, and Persistence Foundation.
- Character Persistence, Character Skill Persistence, Historical Report
  Persistence, and Skill Artifact Persistence depend on Persistence Foundation.
- Character Skill Persistence owns Binding and Association contracts.
- CharacterKit Persistence owns CharacterKit and CharacterKitAssignment.
- Live Execution Job depends on Provider Protocol and is adapted by Web Adapter.
- OpenAI-compatible Provider Adapter implements Provider Protocol and is
  configured by provider profiles/live settings.

Frozen contracts:

- CharacterDraft
- Character identity and immutable revisions
- SkillDesignArtifact and `artifact_digest`
- CharacterSkillArtifactBinding
- CharacterSkillAssociation
- CharacterSkillDesignContext
- Alignment
- CharacterKit and `kit_digest`
- Canonical SkillKit
- Provider Protocol

Evidence inspected:

- `knowledge/project_graph.yaml`, graph schema, aliases, and query/preflight/
  postflight tooling
- `pyproject.toml`, `.env.example`, `.gitignore`, and README installation/startup
  sections
- `.github/workflows/ci.yml`
- `src/along_street_resources`, `src/knowledge`, `src/reference_corpus`, and
  `src/story` loaders
- `src/persistence/sqlite_store.py`, character/skill/report/workspace stores
- `src/web/app.py`, Web routes/services, live job registry, and Next config
- `scripts/ci/installed_smoke.py`, runtime validation, CLI startup, and benchmark
  scripts
- portability, persistence, CI-quality, and runtime-resource tests

Graph conflicts:

- No ownership, dangling-edge, or machine-local canonical-root conflict was
  found.
- The graph reports the known older v0.8 review base and dirty working-tree
  snapshot warning. This is an Engineering Knowledge snapshot limitation, not
  a new portability conflict.
- There are no exact graph nodes for FastAPI, Next.js, Packaging, CLI, or CI;
  this is a coverage gap for future graph maintenance, not a reason to invent
  parallel runtime nodes in S5A.

Known limitations:

- W4/Web components are experimental relative to the v0.8 graph snapshot.
- Historical report pagination, compaction, and garbage collection remain
  deferred.
- Project Graph and hybrid identity checks require a repository checkout and
  Git; that is acceptable for development/EKL, but not for a future standalone
  product runtime.

## D. Impact Set

Allowed future nodes:

- Portable path and encoding policy
- Platform app-data resolver
- Platform smoke and package-install verification
- CI matrix jobs and final-gate dependencies
- Optional CLI doctor/startup orchestration
- Packaging documentation and explicit runtime-data manifests

Protected nodes:

- CharacterDraft, Character Generation, CanonChecker, Human Review
- SkillDesignArtifact, Binding, Association, CharacterKit, and Evaluators
- Alignment and Role Coverage semantics
- Existing SQLite schema v4 and historical append-only boundaries

Platform-sensitive nodes:

- `src/web/app.py` database-path fallback
- `src/persistence/sqlite_store.py` connection, locking, migration, and file path
  behavior
- `src/web/services/live_jobs.py` threads, timers, TTL, and shutdown
- FastAPI factory/startup and localhost binding
- Provider environment handling and subprocess-adjacent diagnostics

Packaging-sensitive nodes:

- `pyproject.toml` setuptools package discovery and package data
- `src/along_street_resources` importlib-resources boundary
- Repository-only `knowledge/`, `docs/`, `evals/`, and `tests/` data
- Web fixtures used by the Skill Playground
- Project Graph Git/root resolution

CI-sensitive nodes:

- `.github/workflows/ci.yml`
- Python 3.10/3.13/3.14 test matrix
- Wheel build and installed smoke
- Missing frontend and cross-platform jobs

Forbidden dependency directions:

- Platform code must not depend inward on Character/Skill semantic changes.
- Web DTOs must not become a second persistence or domain contract.
- Live jobs must not become persisted state.
- Runtime persistence must not depend on Project Graph or Git.
- Installed runtime must not silently require repository-only `docs`, `evals`, or
  `tests` data.
- API keys must not enter Character DB, Project Graph, saved workspace JSON, or
  Git.

## E. Current Platform Status

Windows: development platform and current local evidence. PowerShell, NTFS
paths, Unicode paths, Python 3.10-compatible code, SQLite persistence, FastAPI
tests, and Next.js checks have been exercised locally. This is not yet a formal
Windows CI claim.

Linux: `ubuntu-latest` is the remote CI platform. CI #24 passed quality, the
3.10/3.13/3.14 tests, build, installed smoke, and `ci-success`.

macOS: no current repository or CI evidence. Treat as target-only until a
macOS smoke job passes.

Current verified platforms: Windows local; Linux GitHub runner.

Current inferred platforms: macOS should work for the pure-Python/path-based
parts, but Apple Silicon, Node native packages, filesystem permissions, and
FastAPI/SQLite startup are not proven.

## F. Python Runtime

Supported versions: `>=3.10` in `pyproject.toml`; no upper bound is declared.

Current CI versions: 3.10, 3.13, and 3.14 on Ubuntu. Ruff and mypy target
Python 3.10. The Python 3.13 job additionally runs runtime-boundary coverage.

Launcher assumptions:

- CI uses `python -m ...`, which is portable inside an activated runner
  environment.
- README examples use Windows `.venv\\Scripts\\python.exe` and `py -m`; live
  benchmark documentation contains `py -3.11`, which is a Windows/developer
  convenience rather than a runtime requirement.
- Several executable scripts carry a `python3` shebang. That is a POSIX
  invocation convention; Windows users normally invoke them through Python.
- The installed smoke recognizes POSIX console scripts and Windows `.exe` /.
  `.cmd` launchers, using `COMSPEC` only for the Windows `.cmd` case.

Path assumptions:

- Most scripts derive the repository from `Path(__file__).resolve()`.
- Resource loading uses `importlib.resources` and remains usable outside the
  repository working directory.
- `scripts/benchmark_skill_live_provider.py` passes `Path.cwd()` as `repo_root`;
  it therefore remains a repository-root developer command.
- Hybrid evidence identity and clean-tree enforcement call Git explicitly.

Encoding: runtime YAML/JSON/Markdown loaders and persistence serialization use
explicit UTF-8 or `ensure_ascii=False`. Some subprocess text capture paths omit
an explicit encoding and therefore inherit the platform locale; this is a
medium-risk diagnostic/tooling issue, not a Character semantic issue.

Subprocess: production paths use argument arrays and no `shell=True` or
`os.system` was found. Git subprocesses are development/EKL or hybrid-evidence
identity checks. CI shell syntax is CI-only. The installed smoke has a bounded
Windows `.cmd` compatibility branch.

Risks:

- Python 3.14 dependency/wheel availability must remain covered by CI.
- The minimum Python version has no upper bound and should be reviewed when a
  dependency drops 3.10 support.
- Locale-inherited subprocess decoding can make diagnostics nondeterministic.
- The `Path.cwd()` benchmark root should be made explicit or validated in a
  later tooling slice.

## G. Node / Frontend

Node version: no `engines` field exists in `web/package.json`. Installed
Next.js 16.3.3 declares Node `>=20.9.0`. Local evidence used Node 22.23.2 and
npm 10.9.8. Recommended CI/local canonical line: Node 22.x, while retaining
the dependency minimum of 20.9.0.

Package manager: npm.

Lockfile: `web/package-lock.json`, lockfileVersion 3. CI should use `npm ci`.
Do not introduce pnpm or yarn.

Next.js: 16.3.3 with React 19.2.8; scripts are `next dev`, `next build`,
ESLint, TypeScript, and Node test-runner tests.

Case sensitivity: inspected TypeScript imports, route folders, and static
references match their file names; no mismatch was found. Linux CI is still
required because Windows case-insensitivity can conceal future mistakes.

Environment variables: only `BACKEND_API_URL` is consumed by Next config. It is
server-side rewrite configuration and defaults to `http://127.0.0.1:8000`; no
`NEXT_PUBLIC_*` secret path is present.

Risks:

- The current GitHub workflow has no frontend install, test, typecheck, lint, or
  build job.
- Node 22 should be frozen in the future workflow and documented locally.
- `next build` includes native dependency installation pressure (for example
  `sharp` transitively); Windows/macOS install smoke should cover it before a
  platform support claim.

## H. Paths

Repository root: Graph tooling derives it through `git rev-parse --show-toplevel`
and has a fallback based on the graph location, `pyproject.toml`, and
`knowledge/`. Test/demo scripts generally derive it from `__file__`.

Runtime data: canonical data is packaged below
`src/along_street_resources/data` and accessed through `importlib.resources`.
The package currently contains 69 YAML/Markdown runtime data files. Explicit
filesystem overrides remain supported for loaders.

App data: `GAME_AI_AGENT_DB_PATH` wins; otherwise `LOCALAPPDATA`, then
`XDG_STATE_HOME`, then `Path.home() / ".game-ai-agent"`. The current fallback is
portable in syntax but does not yet follow the desired three-OS data-directory
contract.

Config data: no provider/config directory is currently implemented. Provider
credentials remain process-environment inputs.

Temporary data: runtime/test code uses `tempfile`, `tmp_path`, and temporary
directories. No production `/tmp` or `C:\\Temp` dependency was found.

Machine-local paths: canonical Project Graph `snapshot.project_root` is
repository-relative and validation rejects absolute roots. Absolute Windows
paths occur in historical documentation and negative secrecy tests only; they
are not runtime defaults or graph canonical paths.

Parent escapes: no hardcoded parent escape was found in runtime data lookup.
User-supplied explicit paths remain an input boundary and must be validated by
future doctor/startup code.

Risks:

- Freeze app-data behavior before adding more persistence features.
- Do not place the DB on OneDrive, iCloud, a network share, or a synced folder
  as a supported topology; SQLite locking and partial-sync behavior are not
  covered.
- Project Graph and Skill Playground fixture paths remain repository-mode.

## I. SQLite

Connection model: one `PersistenceUnitOfWork` owns one SQLite connection and
transaction boundary; request/application services open a unit of work and
close it deterministically.

Locking: schema initialization uses `BEGIN IMMEDIATE`; the default busy timeout
is 5,000 ms. Foreign keys are explicitly enabled and verified.

Busy timeout: 5 seconds, bounded and covered by persistence tests.

Journal mode: SQLite default is retained. WAL is deferred by design.

Migrations: fresh DB creates v4; supported paths are v1→v2→v3→v4,
v2→v3→v4, and v3→v4. Unsupported versions fail closed without reset.

Unicode: JSON uses canonical UTF-8-compatible text with `ensure_ascii=False`;
Chinese directory and persistence round-trip tests exist.

Platform risks:

- Windows open-handle/file-lock behavior can interfere with cleanup and test
  deletion.
- Linux and macOS directory permissions can prevent parent creation or DB
  writes.
- Read-only filesystems, network filesystems, OneDrive, and iCloud sync are not
  supported persistence topologies.
- A DB path containing Chinese characters is already covered; cross-OS CI should
  repeat bootstrap/save/open/restart there.
- Do not enable WAL automatically in S5 without measured workload evidence and
  a rollback plan.

## J. FastAPI

Startup: `src/web/app.py:create_app` is an app factory. It creates services,
opens a persistence unit of work once to bootstrap/migrate schema, and mounts
the API routers.

Shutdown: the app registers live-job shutdown; DB connections are request/unit
of work scoped. There is no unified process supervisor.

Host/port: README documents `127.0.0.1:8000` for local development. The
backend itself is an app factory; host and port are launcher concerns. The
frontend rewrite defaults to the same local backend.

SQLite request safety: per-operation units of work, foreign keys, transactions,
busy timeout, and fail-closed migrations are present.

Platform risks:

- There is no repository-owned `studio` launcher that handles child processes,
  Ctrl+C, Windows signals, POSIX signals, port conflicts, or stale processes.
- `uvicorn --reload` is a developer mode and should not define product-like
  support behavior.
- A future combined launcher must keep backend and frontend logs/errors
  separate and must terminate both children on exit.

## K. Runtime Data Classification

| Asset | Runtime Required? | Package Required? | Repo Only? | Test Only? |
|---|---:|---:|---:|---:|
| `src/along_street_resources/data` Canon/world/story data | Yes | Yes | No | No |
| `src/along_street_resources/data/reference_corpus` | Yes for reference APIs/grounding | Yes | No | No |
| `knowledge/project_graph.yaml` and graph schema | No for normal Studio requests | No | Yes | No |
| `docs/` contracts and reports | No | No | Yes | No |
| `tests/fixtures` | No | No | Yes | Yes |
| `evals/fixtures` and `evals/results` | No for normal runtime | No | Yes | Mostly |
| `data/benchmarks` | No | No | Yes | Development/benchmark |
| `web/` source and package lock | Frontend runtime source | Separate frontend deployment | Yes | No |
| `web/.next` and `web/node_modules` | Generated/local | No | No | No |

Reference Corpus and Canon are correctly separate from Project Graph and test
fixtures. The Python package-data declaration covers packaged Canon/reference
resources, but not repository-only graph/evaluation content.

Runtime-required data: packaged Canon, story, knowledge, faction, location, and
reference-corpus resources.

Package-required data: the same `along_street_resources/data` tree for the
installable Python runtime.

Repo-only data: Project Graph, architecture evidence, docs, scripts, and
development benchmarks.

## L. Packaging

Current package model: setuptools `src/` package with project name
`along-street-knowledge-resolver` and a private Next.js application in `web/`.

Installable outside repo: `PARTIAL`.

Wheel: buildable and checked by CI; package discovery includes Python modules
and declared `along_street_resources` data.

sdist: build metadata exists, but the current CI installed-smoke explicitly
tests only the wheel artifact.

Package data: 69 YAML/Markdown files under `along_street_resources/data` are
validated against the source checkout.

Repository dependency: Project Graph/EKL, hybrid Git identity, Skill Playground
fixtures, and some developer scripts still require a checkout. The installed
smoke itself is invoked from a repository script while ensuring imported Python
modules do not come from the source tree, so it is strong package evidence but
not a complete standalone Studio proof.

Recommended S5 packaging target: source-checkout Studio plus an installable
Python wheel smoke. Do not build a single executable yet; defer PyInstaller,
Nuitka, Electron, and Tauri.

## M. CLI

Existing entry point: `along-street-character-author` via `[project.scripts]`.
Other `scripts/*.py` files are developer/evaluation commands, not registered
console commands.

Current startup: backend and frontend are started separately. The documented
backend command uses `py -m uvicorn web.app:create_app --factory`; the frontend
uses `npm run dev`.

Recommended Studio command: reserve `game-ai-agent studio` for S5D. It should
start a production-like local pair only after `web` has been built: FastAPI
without reload plus `next start`, with explicit host/port/app-data options and
coordinated shutdown. Keep the existing separate developer commands.

Recommended doctor command: `game-ai-agent doctor`.

Doctor checks:

- Python version and importability
- Node and npm versions when frontend checks are requested
- Git availability only when repository/EKL mode is requested
- SQLite availability
- DB/app-data parent writability
- Project Graph schema and evidence resolution in repository mode
- frontend availability/build output
- backend import and health/openapi startup
- provider configuration presence only as `configured`/`missing`

Doctor exit codes: `0` means ready; non-zero means a blocking environment
problem. Warnings are displayed separately. Secrets and secret values must
never be printed.

## N. Existing CI

Workflow: `.github/workflows/ci.yml`, triggered on `main` pushes and pull
requests; all jobs run on `ubuntu-latest`.

Jobs:

- `quality`: Python 3.13, install dev dependencies, pre-commit, packaged runtime
  validation.
- `test`: needs quality; Python 3.10/3.13/3.14 matrix; full pytest on each,
  plus runtime-boundary coverage on 3.13.
- `build`: needs quality and test; builds wheel, runs Twine check, uploads
  `python-dist`.
- `installed-smoke`: needs build; installs the wheel into an isolated venv and
  runs outside the repository checkout.
- `ci-success`: always runs and requires the preceding jobs to succeed.

Python matrix: 3 versions × 1 OS, with fail-fast disabled.

Frontend: not currently present in CI; local evidence is separate.

Build: Python distribution build only; no Next build.

Installed smoke: wheel import/resource/console-script/offline smoke outside the
checkout. It does not prove FastAPI startup, Saved Character Save/Open, or the
Next frontend.

Final gate: `ci-success` checks quality, test, build, and installed-smoke.

Approximate duration: CI #24 completed in 16m 26s. The run was green for HEAD
`7fcf3792`.

## O. Proposed CI Matrix

Quality: Ubuntu, Python 3.13; retain current pre-commit and packaged-resource
checks.

EKL portability: Ubuntu, fast and early. Validate graph schema, repository-
relative paths, machine-local-path rejection, evidence resolution, and
preflight/postflight core. Run in parallel with quality.

Python version matrix: Ubuntu, Python 3.10/3.13/3.14 full suite, retaining the
current coverage step only on 3.13.

Windows portability: `windows-latest`, canonical Python 3.13, targeted platform
smoke plus wheel install. Include a Chinese temporary DB path, schema v4
bootstrap/migration, Character Save/Open/restart, FastAPI import/health, and
console-script smoke.

Linux portability: `ubuntu-latest`, canonical Python 3.13, targeted persistence
and FastAPI localhost smoke. The existing full test matrix remains the broad
Linux evidence.

macOS portability: `macos-latest`, canonical Python 3.13, the same targeted
smoke and wheel install. Do not treat this as Apple Silicon evidence without an
explicit arm64 run.

Frontend: Ubuntu Node 22.x runs `npm ci`, tests, lint, typecheck, and build.
Windows and macOS run a smaller `npm ci` + build smoke to catch package/native
install and case/path failures without adding Node-version dimensions.

Installed package: wheel install smoke on all three OSes using canonical Python
3.13; run import, packaged-resource validation, CLI help/offline mode, and a
minimal backend import/start check.

Browser E2E: Ubuntu Chromium only, full Save/Open/reload/re-save flow. Windows
and macOS use backend/frontend start smoke rather than a second browser matrix.

ci-success: retain the final aggregate gate and add every new required job to
its explicit result checks.

Suggested dependency shape:

```text
quality ───────┐
ekl-portability├──> python-tests ──┐
               └──> platform-smoke ├──> package ──> installed-smoke ──┐
frontend-linux ─────────────────────┘                                  ├──> ci-success
frontend-os-smoke ─────────────────────────────────────────────────────┘
browser-e2e ────────────────────────────────────────────────────────────┘
```

The exact `needs` graph should keep quality/EKL early and parallel, while
expensive browser/package jobs wait only on the checks they consume.

## P. Matrix Cost Control

Jobs avoided:

- 9 full Python jobs from 3 OS × 3 Python versions
- 3 OS × 3 browser-engine full E2E combinations
- Multiple Node versions on every OS
- Repeating the full pytest suite in each platform smoke job

Cartesian-product prevention: Python versions vary on Ubuntu; operating
systems use one canonical Python; frontend uses one canonical Node; browser
coverage is one Ubuntu Chromium path.

Canonical platform Python: 3.13, because it is the existing quality/coverage
version and the middle supported version between 3.10 and 3.14.

Browser strategy: hybrid Option C — Ubuntu Chromium full E2E plus Windows/macOS
API/start/build smoke.

## Q. Platform Smoke Contract

Windows: install dev environment or wheel, use a PowerShell-safe launcher, run
Python import, Project Graph portability checks where applicable, UTF-8 Unicode
path, SQLite migration/save/open/restart, FastAPI health, and console help/offline
mode.

Linux: run the same targeted persistence/FastAPI contract on Ubuntu; the full
Python matrix supplies broad regression evidence.

macOS: run the same targeted contract and explicitly record x86_64 versus arm64
runner identity; no architecture claim is valid without the corresponding run.

SQLite: temporary writable DB, Chinese directory, fresh v4 bootstrap, selected
legacy migrations, foreign keys, busy timeout, save/load after connection
restart, and no WAL assumption.

FastAPI: import `create_app`, bootstrap schema, start localhost once, verify
health/openapi, and stop cleanly.

Frontend: `npm ci`, case-sensitive import/build check, and a production-like
build; only Ubuntu runs the full frontend test suite initially.

Unicode: UTF-8 YAML/JSON/Markdown and Chinese DB path/Character payload.

App-data: resolve the explicit override and platform fallback in a temporary
home/app-data environment; assert the chosen path is writable without exposing
secrets.

## R. Risk Register

BLOCKER:

- None found in the current audited Windows/Linux baseline.

HIGH:

- Windows and macOS have no formal CI evidence yet; a support claim would be
  premature.
- Installed-package support is partial because EKL, hybrid identity, and some
  Web fixtures remain repository-mode.
- Frontend is absent from remote CI, so the remote gate does not cover the
  actual Studio UI build.

MEDIUM:

- App-data fallback uses `XDG_STATE_HOME` and a hidden home directory rather
  than a frozen XDG data directory and explicit macOS Application Support path.
- One live benchmark path uses `Path.cwd()` as repository root.
- Git is required for EKL and hybrid evidence identity, but this boundary is
  not surfaced as a product/runtime mode.
- Some subprocess text capture inherits locale encoding.
- Node minimum is implicit in Next.js dependency metadata, not project metadata.
- SQLite synced/network/read-only filesystem behavior is undefined.

LOW:

- Developer docs mix Windows `py`/PowerShell and POSIX shebang examples.
- LF is the repository text convention; no shell-script line-ending issue was
  found because the repository has no project-owned `.sh`, `.bat`, or `.cmd`
  launcher.

DEFER:

- WAL adoption, single-executable packaging, native desktop shells, full browser
  matrices, secret-manager integration, and all-OS full migration matrices.

## S. Support Contract Proposal

Windows: Windows 11 on NTFS, PowerShell-supported developer path; no older
Windows claim.

Linux: Ubuntu GitHub runner/latest supported LTS target; no claim for every
Linux distribution.

macOS: `macos-latest` CI target; no claim for every macOS release.

CPU architectures: x86_64 first; arm64 only where Python/Node dependencies and
an explicit run pass. Apple Silicon requires a separately recorded arm64
verification.

Python: minimum 3.10; canonical cross-platform smoke 3.13; Linux compatibility
matrix 3.10/3.13/3.14.

Node: dependency minimum `>=20.9.0`; canonical CI/local line Node 22.x.

Package manager: npm with committed lockfile and `npm ci`.

## T. Engineering Knowledge Portability

Current: Project Graph validation already rejects absolute canonical roots,
resolves evidence relative to the checkout, and is exercised indirectly by the
Linux CI test suite. There is no dedicated portability job.

Dedicated job proposal: `ekl-portability`.

Checks:

- Project Graph schema and relation validation
- repository-relative path enforcement
- machine-local path rejection
- evidence and test-path resolution
- preflight topic matching and baseline capture
- postflight core verdict from the captured baseline

Platform: Ubuntu-only is sufficient for graph semantics and keeps the job fast;
the Windows platform smoke should additionally run the same path rejection
checks to expose native path parsing surprises.

Expected runtime: fast, before full Python/package/browser jobs; target under
one minute on a warm runner.

## U. S5 Slice Plan

S5B — Portable Path, App-Data, and Encoding Contract: freeze the three-OS DB
fallback, explicit UTF-8 subprocess/text policy, repository-mode versus
installed-mode flags, and focused tests. Do not change domain semantics.

S5B implementation note: the portable runtime path, app-data, database, CWD,
and UTF-8 contracts are now implemented and documented; cross-platform
execution verification remains deferred to S5C/S5E.

S5C — Cross-Platform CI Matrix: add the minimal quality/EKL/platform/frontend/
package jobs from section O and update `ci-success`.

S5D — CLI, Doctor, and Startup Packaging: add the smallest unified doctor and
product-like Studio launcher only after the path contract is stable.

S5E — Three-Platform Final Verification: run the Windows/Linux/macOS smoke,
wheel install, frontend/build, FastAPI, SQLite Save/Open/restart, and one Ubuntu
Chromium E2E flow; record architecture and runner evidence.

There must be no one-shot cross-platform mega-refactor.

## V. Documentation

Audit doc: `docs/cross_platform_architecture_audit_v0.1.md`.

Project Graph: no new runtime node is required by this audit. A future planned
`Cross-Platform Compatibility` node may be added only if the graph convention
supports planned/backlog nodes and its status is not presented as implemented.

## W. Verification

EKL tests: clean committed candidate targeted set passed, `58 passed`, covering
`tests/test_project_graph.py`, `tests/test_project_preflight.py`,
`tests/test_project_postflight.py`, `tests/test_ci_quality.py`,
`tests/test_cli_startup.py`, and `tests/test_runtime_resources.py`. A duplicate
run in the intentionally dirty primary worktree produced 60 passes and one
pre-existing failure in its modified preflight test; that dirty-tree result is
not authoritative for this audit.

Graph validation: required and included in the targeted test set.

Preflight: `READY_WITH_WARNINGS`; baseline captured at HEAD
`7fcf3792cc2ea9378112f22795d5b11a5ddbafb9`.

Postflight: `IN_SYNC`, with one changed path and no graph-linked knowledge
impact. This audit document is not a graph canonical source.

`git diff --check`: PASS.

## X. Git

Commit: NO

Push: NO

Tag: NO

## Y. Recommended Next Step

Based on audit findings:

W4-S5B — Portable Path, App-Data, and Encoding Contract

Do not automatically implement.
